"""组稿域的 AI 工具 —— 只覆盖「生成一份新稿件」这条 server 路径。

刻意不暴露细粒度编辑(移动/删除某个节点):那类操作的对象是用户正在编辑、尚未保存的
会话内文档,有 undo 栈和光标,只能由编辑器自己执行。这里的 `write_composition_nodes`
是**整份写入**,只对刚新建的空稿件才安全 —— 稿件本来就是空的,不存在「模型没复现的
部分被静默丢弃」。工具描述里必须把这点讲清楚。

DomainError 在这里就地翻译成给模型看的中文提示:registry.dispatch 的兜底会把异常压成
`Error executing tool: ...`,那对模型没有可操作性。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app import capabilities
from app.ai.contracts import ToolResult, ToolSpec
from app.capabilities import compositions as composition_caps
from app.capabilities.context import ExecutionContext
from app.capabilities.errors import (
    Conflict,
    DomainError,
    Forbidden,
    Invalid,
    NotFound,
    Unprocessable,
)
from app.ai.tools.registry import register
from app.models.composition import ScopeType
from app.services.composition_authoring import (
    AUTHORABLE_NODE_TYPES,
    AuthoringError,
    build_nodes,
)

_SCOPE_VALUES = [s.value for s in ScopeType]


def _resolve_subject(ctx: ExecutionContext) -> Optional[int]:
    return ctx.subject_id or getattr(ctx.actor, "last_active_subject_id", None)


def _resolve_scope(ctx: ExecutionContext, raw: Optional[str]) -> tuple[ScopeType, Optional[int]]:
    """复刻端点层的 `_resolve_scope`:personal 的 owner 强制为当前用户,模型无从伪造。"""
    scope = ScopeType(raw) if raw else ScopeType.PERSONAL
    return scope, (ctx.actor.id if scope == ScopeType.PERSONAL else None)


def _explain(exc: DomainError) -> str:
    if isinstance(exc, Conflict):
        return (
            f"稿件已被改动,expected_revision 不是最新的({exc.detail})。"
            "请重新确认当前 revision 后再写入,不要直接重试。"
        )
    if isinstance(exc, Unprocessable):
        return (
            f"引用的题目无法写入({exc.detail})。"
            "常见原因:题目不存在、属于其它学科、或把私有题放进了共享稿件。"
            "请改用 search_questions 在当前学科里重新找题。"
        )
    if isinstance(exc, Invalid):
        return f"节点结构不合法({exc.detail})。请调整 nodes 后重试。"
    if isinstance(exc, NotFound):
        return f"找不到目标({exc.detail})。请确认 composition_id 与 scope 是否正确。"
    if isinstance(exc, Forbidden):
        return f"当前用户没有该学科的组稿权限({exc.detail})。"
    return exc.detail


CREATE_COMPOSITION_PARAMS = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "稿件标题。"},
        "description": {"type": "string", "description": "稿件简介,可选。"},
        "scope": {
            "type": "string",
            "enum": _SCOPE_VALUES,
            "description": "personal=只有自己可见(默认);shared=同学科成员都可见。",
        },
        "folder_id": {"type": "integer", "description": "放入的目录 id,可选。"},
    },
    "required": ["title"],
}

# 判别式扁平对象:Gemini 的 FunctionDeclaration 不吃 oneOf/anyOf/$ref,只能靠描述约束。
WRITE_COMPOSITION_NODES_PARAMS = {
    "type": "object",
    "properties": {
        "composition_id": {"type": "integer", "description": "目标稿件 id。"},
        "expected_revision": {
            "type": "integer",
            "description": "稿件当前的 revision(乐观锁)。新建的稿件是 1。",
        },
        "scope": {
            "type": "string",
            "enum": _SCOPE_VALUES,
            "description": "必须与建稿时相同。",
        },
        "nodes": {
            "type": "array",
            "description": "按版面从上到下的顺序排列的节点列表。",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": list(AUTHORABLE_NODE_TYPES),
                        "description": (
                            "heading=小标题;rich_text=正文段落;question=引用题库中的题;"
                            "question_details=参考答案模块;page_break=分页;answer_space=作答区。"
                        ),
                    },
                    "text": {"type": "string", "description": "仅 heading:标题文字(纯文本)。"},
                    "level": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 4,
                        "description": "仅 heading:标题层级,默认 2。",
                    },
                    "markdown": {
                        "type": "string",
                        "description": (
                            "仅 rich_text:正文,用 Markdown 书写。支持 $行内公式$、$$块级公式$$、"
                            "列表与表格。多个段落会自动拆成多个段落节点。"
                        ),
                    },
                    "question_id": {
                        "type": "integer",
                        "description": "仅 question:题库中的题目 id,先用 search_questions 找到。",
                    },
                    "score": {"type": "number", "description": "仅 question:本题分值。"},
                    "number": {"type": "string", "description": "仅 question:自定义题号。"},
                    "show": {
                        "type": "object",
                        "description": (
                            "仅 question:是否在题目下方显示这些字段。"
                            "例题可设 {\"analysis\": true} 显示解析,检测题留空即可隐藏。"
                        ),
                        "properties": {
                            "answer": {"type": "boolean"},
                            "thinking": {"type": "boolean"},
                            "analysis": {"type": "boolean"},
                            "summary": {"type": "boolean"},
                        },
                    },
                    "lines": {
                        "type": "integer",
                        "description": "仅 answer_space:作答区行数,默认 4。",
                    },
                    "style": {
                        "type": "string",
                        "enum": ["blank", "lined"],
                        "description": "仅 answer_space:空白或横线,默认 lined。",
                    },
                    "details_scope": {
                        "type": "string",
                        "enum": ["all", "before"],
                        "description": "仅 question_details:收录全部题目还是模块之前的题目,默认 all。",
                    },
                    "details_fields": {
                        "type": "object",
                        "description": "仅 question_details:统一收录哪些字段,默认只收 answer。",
                        "properties": {
                            "answer": {"type": "boolean"},
                            "thinking": {"type": "boolean"},
                            "analysis": {"type": "boolean"},
                            "summary": {"type": "boolean"},
                        },
                    },
                },
                "required": ["type"],
            },
        },
    },
    "required": ["composition_id", "expected_revision", "nodes"],
}


async def create_composition(ctx: ExecutionContext, args: Dict[str, Any]) -> ToolResult:
    subject_id = _resolve_subject(ctx)
    if not subject_id:
        return ToolResult.text("当前没有选定学科,无法新建稿件。请先让用户在界面上选择学科。")

    title = (args.get("title") or "").strip()
    if not title:
        return ToolResult.text("请提供稿件标题。")

    try:
        scope, owner_id = _resolve_scope(ctx, args.get("scope"))
    except ValueError:
        return ToolResult.text(f"scope 只能是 {' 或 '.join(_SCOPE_VALUES)}。")

    try:
        comp = await capabilities.run(
            "composition.create",
            ctx,
            composition_caps.CompositionCreateInput(
                subject_id=subject_id,
                scope_type=scope,
                owner_id=owner_id,
                title=title,
                description=args.get("description"),
                folder_id=args.get("folder_id"),
            ),
        )
    except DomainError as exc:
        return ToolResult.text(_explain(exc))

    return ToolResult(
        content=(
            f"已新建稿件「{comp.title}」。composition_id={comp.id},"
            f"scope={scope.value},revision={comp.revision}。"
            "接下来用 write_composition_nodes 写入内容。"
        ),
        data={"composition_id": comp.id, "scope": scope.value, "revision": comp.revision},
    )


async def write_composition_nodes(ctx: ExecutionContext, args: Dict[str, Any]) -> ToolResult:
    subject_id = _resolve_subject(ctx)
    if not subject_id:
        return ToolResult.text("当前没有选定学科,无法写入稿件。")

    composition_id = args.get("composition_id")
    expected_revision = args.get("expected_revision")
    if not isinstance(composition_id, int) or not isinstance(expected_revision, int):
        return ToolResult.text("composition_id 与 expected_revision 都必须是整数。")

    try:
        scope, owner_id = _resolve_scope(ctx, args.get("scope"))
    except ValueError:
        return ToolResult.text(f"scope 只能是 {' 或 '.join(_SCOPE_VALUES)}。")

    try:
        items = build_nodes(args.get("nodes") or [])
    except AuthoringError as exc:
        return ToolResult.text(f"节点描述有误:{exc}")

    if not items:
        return ToolResult.text("nodes 为空。整份写入会清空稿件,如果确实要清空请明确告知用户。")

    try:
        result = await capabilities.run(
            "composition.replace_nodes",
            ctx,
            composition_caps.CompositionReplaceNodesInput(
                subject_id=subject_id,
                scope_type=scope,
                owner_id=owner_id,
                composition_id=composition_id,
                expected_revision=expected_revision,
                items=items,
            ),
        )
    except DomainError as exc:
        return ToolResult.text(_explain(exc))

    return ToolResult(
        content=(
            f"已写入 {len(items)} 个节点,稿件当前 revision={result.revision}。"
            "如需继续修改,请使用这个新的 revision。"
        ),
        data={"composition_id": composition_id, "revision": result.revision,
              "node_count": len(items)},
    )


register(ToolSpec(
    name="create_composition",
    description=(
        "在当前学科下新建一份空白稿件(试卷/讲义)。新建后用 write_composition_nodes 写入内容。"
        "仅当用户明确要求生成/制作稿件时使用，不要自作主张新建。"
    ),
    parameters=CREATE_COMPOSITION_PARAMS,
    handler=create_composition,
    capability="composition.create",
    mutating=True,
))

register(ToolSpec(
    name="write_composition_nodes",
    description=(
        "写入稿件的全部内容。"
        "**这是整份替换:调用后稿件里原有的内容会被 nodes 完全取代**,"
        "因此只应在刚新建的空白稿件上使用。"
        "不要用它做局部修改(插入/删除/移动某一题),那些操作请让用户在组稿编辑器里完成。"
        "仅当用户明确要求生成/写入稿件内容时使用。"
    ),
    parameters=WRITE_COMPOSITION_NODES_PARAMS,
    handler=write_composition_nodes,
    capability="composition.replace_nodes",
    mutating=True,
))
