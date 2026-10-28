"""MCP 工具集 —— 把 capability 与少量只读查询暴露给外部 AI 客户端。

- 写路径:`all_capabilities()` 自动映射,inputSchema 由 capability 的 input_model 生成,
  执行仍走 `capabilities.run()`,鉴权与业务逻辑与 REST/聊天完全一致。
- 读路径:capability 层刻意不含读用例(见 capabilities/questions.py 文档),这里按 REST
  端点的同等门禁实现少量只读工具。

适配器只负责「传输层对输入的收敛」,与 REST 端点做的事一一对应:
- 组稿的 `owner_id` 由调用者身份推出(personal → 当前用户),客户端无从伪造;
- `xxx_provided` 标志由「参数里是否出现 xxx」推出,不让模型自己填。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlalchemy import select

from app import capabilities, crud, schemas
from app.capabilities.base import Capability
from app.capabilities.compositions import CompositionScopeInput
from app.capabilities.context import ExecutionContext
from app.capabilities.errors import DomainError, Forbidden, NotFound, status_for
from app.core import permissions
from app.core.api_errors import ErrorCode
from app.core.permissions import Permission
from app.crud import crud_composition
from app.crud.crud_question import is_question_visible
from app.models.composition import ScopeType
from app.models.knowledge_point import KnowledgePoint
from app.models.question import QuestionType
from app.models.subject import Subject
from app.models.tag import Tag
from app.models.tag_category import TagCategory
from app.services import media_service
from app.schemas.composition import (
    CompositionDetail,
    CompositionNodesReplaceResponse,
    CompositionQuestionGroupNodesSyncResponse,
    CompositionQuestionNodesSyncResponse,
    CompositionRead,
    CompositionVersionRead,
    FolderRead,
)

logger = logging.getLogger(__name__)

# 依赖前置的文件抽取流程,外部客户端无法独立构造合法输入,第一期不暴露。
EXCLUDED_CAPABILITIES: frozenset[str] = frozenset({
    "paper_import.preview",
    "paper_import.commit",
})

# capability → 输出类型,与对应 REST 端点的 response_model 一致;None 表示无返回体。
# tests/test_mcp.py 断言每个暴露的 capability 都在此登记。
CAPABILITY_OUTPUT_TYPES: Dict[str, Any] = {
    "question.create": schemas.Question,
    "question.batch_create": List[schemas.Question],
    "question.relation.create": schemas.QuestionRelationRead,
    "question.relation.delete": None,
    "question.derived.create": schemas.Question,
    "question.update": schemas.Question,
    "question.review": schemas.Question,
    "question.delete": schemas.Question,
    "question.batch_delete": dict,
    "question.batch_update": dict,
    "question.batch_confirm": dict,
    "composition.create_folder": FolderRead,
    "composition.update_folder": FolderRead,
    "composition.delete_folder": None,
    "composition.create": CompositionRead,
    "composition.update": CompositionRead,
    "composition.replace_nodes": CompositionNodesReplaceResponse,
    "composition.sync_question_nodes": CompositionQuestionNodesSyncResponse,
    "composition.sync_question_group_nodes": CompositionQuestionGroupNodesSyncResponse,
    "composition.delete": None,
    "composition.restore": CompositionRead,
    "composition.duplicate": CompositionRead,
    "composition.finalize_version": CompositionVersionRead,
    "knowledge_point.create": schemas.KnowledgePoint,
    "tag.create": schemas.Tag,
}

_PROVIDED_SUFFIX = "_provided"
_LIST_LIMIT_MAX = 50

ToolHandler = Callable[[ExecutionContext, Dict[str, Any]], Awaitable[Dict[str, Any]]]


class ToolError(Exception):
    """工具执行失败,payload 原样回给客户端(isError=True)。"""

    def __init__(self, payload: Dict[str, Any]) -> None:
        super().__init__(str(payload.get("detail")))
        self.payload = payload


@dataclass(frozen=True)
class McpTool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: ToolHandler
    read_only: bool
    destructive: bool = False
    capability: Optional[str] = None


def tool_name_for(capability_name: str) -> str:
    # 部分客户端的工具名只允许 [a-zA-Z0-9_-]
    return capability_name.replace(".", "_")


# --------------------------------------------------------------------------- #
# 序列化 / 错误
# --------------------------------------------------------------------------- #
_ADAPTERS: Dict[str, TypeAdapter] = {}


def _adapter(tp: Any) -> TypeAdapter:
    key = repr(tp)
    if key not in _ADAPTERS:
        _ADAPTERS[key] = TypeAdapter(tp)
    return _ADAPTERS[key]


def serialize(tp: Any, value: Any) -> Dict[str, Any]:
    """输出统一成 JSON 对象(MCP 的 structuredContent 要求顶层是对象)。"""
    if tp is None or value is None:
        return {"ok": True}
    if tp is dict:
        data = jsonable_encoder(value)
    else:
        adapter = _adapter(tp)
        data = adapter.dump_python(adapter.validate_python(value, from_attributes=True), mode="json")
    if isinstance(data, dict):
        return data
    return {"items": data}


def error_payload(exc: BaseException) -> Dict[str, Any]:
    if isinstance(exc, ToolError):
        return exc.payload
    if isinstance(exc, DomainError):
        payload: Dict[str, Any] = {"status": status_for(exc), "detail": exc.detail}
        if exc.code:
            payload["code"] = str(exc.code)
        if exc.params:
            payload["params"] = exc.params
        return payload
    if isinstance(exc, HTTPException):
        payload = {"status": exc.status_code, "detail": exc.detail}
        code = getattr(exc, "code", None)
        if code:
            payload["code"] = str(code)
        return payload
    if isinstance(exc, ValidationError):
        return {
            "status": 422,
            "code": ErrorCode.VALIDATION_FAILED.value,
            "detail": [
                {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
                for e in exc.errors()
            ],
        }
    return {"status": 500, "detail": "Internal error while executing the tool"}


# --------------------------------------------------------------------------- #
# capability → 工具
# --------------------------------------------------------------------------- #
# Pydantic 用类 docstring 生成 $defs 的 description;docstring 是中文代码注释,
# 给模型看的版本在这里用英文覆盖。tests/test_mcp.py 断言工具 schema 中不含中文。
_DEF_DESCRIPTIONS: Dict[str, str] = {
    "ScopeType": "Ownership scope: shared (visible to the subject team) or personal (visible only to you).",
    "CompositionNodeKind": "Node category in the composition AST.",
    "CompositionNodeInput": (
        "A single node in an AST replacement. `id` is a client-generated UUID; `position` is not sent by the client. "
        "For question nodes, `question_revision` and the frozen snapshot are managed by the server and client values are ignored. "
        "Reference relations of answer_item nodes are normalized by the server according to the module scope."
    ),
}


def _hidden_fields(cap: Capability) -> set[str]:
    fields = cap.input_model.model_fields
    hidden = {
        name for name in fields
        if name.endswith(_PROVIDED_SUFFIX) and name[: -len(_PROVIDED_SUFFIX)] in fields
    }
    if issubclass(cap.input_model, CompositionScopeInput):
        hidden.add("owner_id")
    return hidden


def _input_schema(cap: Capability) -> Dict[str, Any]:
    schema = cap.input_model.model_json_schema()
    hidden = _hidden_fields(cap)
    props = schema.get("properties", {})
    for name in hidden:
        props.pop(name, None)
    if "required" in schema:
        schema["required"] = [r for r in schema["required"] if r not in hidden]
    for name, definition in schema.get("$defs", {}).items():
        if name in _DEF_DESCRIPTIONS:
            definition["description"] = _DEF_DESCRIPTIONS[name]
    schema["type"] = "object"
    return schema


def prepare_capability_input(cap: Capability, ctx: ExecutionContext, args: Dict[str, Any]) -> BaseModel:
    """把客户端参数收敛成 capability 入参,补上由身份/参数形态推出的隐藏字段。"""
    hidden = _hidden_fields(cap)
    data = {k: v for k, v in args.items() if k not in hidden}
    for name in hidden:
        if name.endswith(_PROVIDED_SUFFIX):
            data[name] = name[: -len(_PROVIDED_SUFFIX)] in args
    if issubclass(cap.input_model, CompositionScopeInput):
        data["owner_id"] = ctx.actor.id if data.get("scope_type") == ScopeType.PERSONAL.value else None
    return cap.input_model.model_validate(data)


# 少数 capability 的通用描述不足以让外部模型正确调用,这里补充面向模型的说明。
_DESCRIPTION_OVERRIDES: Dict[str, str] = {
    "composition.replace_nodes": (
        "LOW-LEVEL: replace the entire node tree (AST) of a composition. Prefer composition_write_nodes, "
        "which builds valid nodes for you; use this only to restructure nodes read via get_composition. "
        "Every node not included is deleted. Rules: `id` is a client-generated UUID (keep existing ids to "
        "keep nodes and their frozen question snapshots); top-level nodes have no parent_id and no slot; "
        "child nodes set parent_id and slot='body'. node_kind/node_type pairs: block = rich_text | heading | "
        "question | page_break | answer_space; module = question_details | question_group; "
        "reference = answer_item (children of question_details, derived by the server). question nodes need "
        "question_id; question_group needs stimulus_id and question children. Order in `items` is layout order. "
        "Requires the current revision as expected_revision."
    ),
}


def _capability_tool(cap: Capability) -> McpTool:
    output_type = CAPABILITY_OUTPUT_TYPES[cap.name]

    async def handler(ctx: ExecutionContext, args: Dict[str, Any]) -> Dict[str, Any]:
        inp = prepare_capability_input(cap, ctx, args)
        subject_id = getattr(inp, "subject_id", None)
        if subject_id is not None:
            ctx = ctx.with_subject(subject_id)
        result = await capabilities.run(cap.name, ctx, inp)
        return serialize(output_type, result)

    return McpTool(
        name=tool_name_for(cap.name),
        description=_DESCRIPTION_OVERRIDES.get(cap.name, cap.description),
        input_schema=_input_schema(cap),
        handler=handler,
        read_only=not cap.mutating,
        destructive="delete" in cap.name,
        capability=cap.name,
    )


# --------------------------------------------------------------------------- #
# 只读工具(门禁与对应 REST 端点一致)
# --------------------------------------------------------------------------- #
def _int_arg(args: Dict[str, Any], name: str) -> int:
    try:
        return int(args[name])
    except (KeyError, TypeError, ValueError):
        raise ToolError({"status": 422, "detail": f"{name} is required and must be an integer"})


def _optional_int(args: Dict[str, Any], name: str) -> Optional[int]:
    if args.get(name) is None:
        return None
    return _int_arg(args, name)


async def _require_subject(ctx: ExecutionContext, args: Dict[str, Any]) -> int:
    subject_id = _int_arg(args, "subject_id")
    if not await crud.subject.get(ctx.db, id=subject_id):
        raise NotFound("Subject not found", ErrorCode.SUBJECT_NOT_FOUND)
    if not permissions.can(ctx.actor, Permission.VIEW_QUESTION, subject_id=subject_id):
        raise Forbidden("The user doesn't have enough privileges", ErrorCode.AUTH_FORBIDDEN)
    return subject_id


def _scope_owner(ctx: ExecutionContext, args: Dict[str, Any]) -> tuple[ScopeType, Optional[int]]:
    try:
        scope_type = ScopeType(args.get("scope_type"))
    except ValueError:
        raise ToolError({"status": 422, "detail": "scope_type must be 'shared' or 'personal'"})
    return scope_type, (ctx.actor.id if scope_type == ScopeType.PERSONAL else None)


def _limit(value: Any, default: int = 20) -> int:
    try:
        limit = int(value) if value is not None else default
    except (TypeError, ValueError):
        limit = default
    return max(1, min(limit, _LIST_LIMIT_MAX))


async def _create_media_upload_url(ctx: ExecutionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    # 延迟导入:uploads 依赖 app.api.deps,顶层导入会让 tools 的加载链变长
    from .auth import current_auth
    from .uploads import create_upload_token

    subject_id = await _require_subject(ctx, args)
    if not permissions.can(ctx.actor, Permission.EDIT_QUESTION, subject_id=subject_id):
        raise Forbidden("The user doesn't have enough privileges", ErrorCode.AUTH_FORBIDDEN)
    auth = current_auth.get()
    if auth is None:
        raise ToolError({"status": 401, "detail": "Not authenticated"})
    token, expires = create_upload_token(user_id=ctx.actor.id, key_id=auth.key_id, subject_id=subject_id)
    upload_url = f"{auth.base_url}/api/mcp/uploads/{token}"
    return {
        "upload_url": upload_url,
        "expires_at": expires.isoformat(),
        "method": "POST",
        "form_field": "file",
        "max_image_mb": media_service.MAX_IMAGE_BYTES // (1024 * 1024),
        "curl": f"curl -sS -F 'file=@/path/to/image.png' '{upload_url}'",
        "accepted_formats": "PNG, JPEG, GIF, WebP images; MP3, M4A, OGG, WAV audio",
    }


async def _check_duplicates(ctx: ExecutionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services import question_dedup

    subject_id = await _require_subject(ctx, args)
    if not args.get("q_type"):
        raise ToolError({"status": 422, "detail": "q_type is required"})
    key = question_dedup.key_from_payload(
        q_type=args["q_type"],
        content=args.get("content"),
        options=args.get("options"),
        stimulus_content=await question_dedup.stimulus_content(
            ctx.db, _optional_int(args, "stimulus_id"), subject_id=subject_id
        ),
    )
    exclude = _optional_int(args, "exclude_question_id")
    found = await question_dedup.find_duplicates(
        ctx.db, viewer=ctx.actor, subject_id=subject_id, key=key, exclude_ids=(exclude,) if exclude else ()
    )
    return {"candidates": question_dedup.candidates_payload(found)}


async def _list_subjects(ctx: ExecutionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    subjects = (await ctx.db.execute(select(Subject).order_by(Subject.id))).scalars().all()
    accessible = permissions.accessible_subject_ids(ctx.actor)
    visible = [s for s in subjects if accessible is None or s.id in accessible]
    return {
        "items": [{"id": s.id, "name": s.name} for s in visible],
        "last_active_subject_id": ctx.actor.last_active_subject_id,
    }


async def _search_questions(ctx: ExecutionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    subject_id = await _require_subject(ctx, args)
    q_type = args.get("q_type") or None
    if q_type is not None and q_type not in {t.value for t in QuestionType}:
        raise ToolError({
            "status": 422,
            "detail": f"Unknown q_type: {q_type}. Allowed: {', '.join(t.value for t in QuestionType)}",
        })
    page = max(1, _optional_int(args, "page") or 1)
    size = _limit(args.get("size"))
    filters = dict(
        subject_id=subject_id,
        keyword=args.get("keyword") or None,
        knowledge_point_ids=args.get("knowledge_point_ids") or None,
        tag_ids=args.get("tag_ids") or None,
        q_type=q_type,
        difficulty=_optional_int(args, "difficulty"),
        status=args.get("status") or None,
        viewer=ctx.actor,
    )
    questions = await crud.question.get_multi_with_filters(
        ctx.db, skip=(page - 1) * size, limit=size, **filters
    )
    total = await crud.question.count_with_filters(ctx.db, **filters)
    return {
        "items": [
            schemas.QuestionListItem.model_validate(q).model_dump(mode="json") for q in questions
        ],
        "total": total,
        "page": page,
        "size": size,
    }


async def _get_question(ctx: ExecutionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    question = await crud.question.get(db=ctx.db, id=_int_arg(args, "id"))
    if not question or not is_question_visible(question, ctx.actor):
        raise NotFound("Question not found", ErrorCode.QUESTION_NOT_FOUND)
    return serialize(schemas.Question, question)


async def _list_knowledge_points(ctx: ExecutionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    subject_id = await _require_subject(ctx, args)
    stmt = select(KnowledgePoint).where(KnowledgePoint.subject_id == subject_id)
    keyword = (args.get("keyword") or "").strip()
    if keyword:
        stmt = stmt.where(KnowledgePoint.name.contains(keyword, autoescape=True))
    rows = (await ctx.db.execute(stmt.order_by(KnowledgePoint.id))).scalars().all()
    return {"items": [{"id": kp.id, "name": kp.name, "parent_id": kp.parent_id} for kp in rows]}


async def _list_tags(ctx: ExecutionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    subject_id = await _require_subject(ctx, args)
    tags = (await ctx.db.execute(
        select(Tag).where(Tag.subject_id == subject_id).order_by(Tag.id)
    )).scalars().all()
    category_ids = {t.category_id for t in tags if t.category_id is not None}
    categories: Dict[int, str] = {}
    if category_ids:
        rows = (await ctx.db.execute(
            select(TagCategory).where(TagCategory.id.in_(category_ids))
        )).scalars().all()
        categories = {c.id: c.name for c in rows}
    return {
        "items": [
            {"id": t.id, "name": t.name, "category": categories.get(t.category_id)}
            for t in tags
        ]
    }


async def _list_folders(ctx: ExecutionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    subject_id = await _require_subject(ctx, args)
    scope_type, owner_id = _scope_owner(ctx, args)
    folders = await crud_composition.folder.list_scoped(
        ctx.db, subject_id=subject_id, scope_type=scope_type, owner_id=owner_id
    )
    return serialize(List[FolderRead], folders)


async def _list_compositions(ctx: ExecutionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    subject_id = await _require_subject(ctx, args)
    scope_type, owner_id = _scope_owner(ctx, args)
    comps = await crud_composition.composition.list_scoped(
        ctx.db,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
        folder_id=_optional_int(args, "folder_id"),
        keyword=args.get("keyword") or None,
    )
    return serialize(List[CompositionRead], comps)


async def _get_composition(ctx: ExecutionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    subject_id = await _require_subject(ctx, args)
    scope_type, owner_id = _scope_owner(ctx, args)
    comp = await crud_composition.composition.get_scoped(
        ctx.db,
        composition_id=_int_arg(args, "composition_id"),
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
        with_nodes=True,
    )
    if comp is None:
        raise NotFound("Composition not found", ErrorCode.COMPOSITION_NOT_FOUND)
    return serialize(CompositionDetail, comp)


async def _write_composition_nodes(ctx: ExecutionContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.capabilities.compositions import CompositionReplaceNodesInput
    from app.schemas.composition import CompositionNodeInput
    from app.services.composition_authoring import AuthoringError, build_nodes

    subject_id = await _require_subject(ctx, args)
    scope_type, owner_id = _scope_owner(ctx, args)
    composition_id = _int_arg(args, "composition_id")
    expected_revision = _int_arg(args, "expected_revision")
    mode = args.get("mode") or "append"
    if mode not in ("append", "replace"):
        raise ToolError({"status": 422, "detail": "mode must be 'append' or 'replace'"})

    try:
        new_items = build_nodes(args.get("nodes") or [])
    except AuthoringError as exc:
        raise ToolError({"status": 422, "code": ErrorCode.VALIDATION_FAILED.value, "detail": str(exc)})
    if not new_items:
        raise ToolError({"status": 422, "detail": "nodes must not be empty"})

    items = list(new_items)
    if mode == "append":
        comp = await crud_composition.composition.get_scoped(
            ctx.db,
            composition_id=composition_id,
            subject_id=subject_id,
            scope_type=scope_type,
            owner_id=owner_id,
            with_nodes=True,
        )
        if comp is None:
            raise NotFound("Composition not found", ErrorCode.COMPOSITION_NOT_FOUND)
        # 现有节点原样回写(保留 id → 保留题目冻结快照),新节点接在末尾。
        # 只有正文/标题的 content 由客户端提供,其余节点的 content 是服务端冻结的快照,回写必须为空。
        authored_content = {"rich_text", "heading"}
        existing = sorted(comp.nodes, key=lambda n: (n.parent_id is not None, n.position))
        kept = [
            CompositionNodeInput(
                id=n.id,
                parent_id=n.parent_id,
                slot=n.slot,
                node_kind=n.node_kind,
                node_type=n.node_type,
                content=n.content if n.node_type in authored_content else None,
                props=n.props if n.node_type != "page_break" else None,
                schema_version=n.schema_version,
                question_id=n.question_id,
                stimulus_id=n.stimulus_id,
                source_question_node_id=n.source_question_node_id,
                anchor_before_node_id=n.anchor_before_node_id,
            )
            for n in existing
        ]
        roots = [it for it in kept if it.parent_id is None]
        children = [it for it in kept if it.parent_id is not None]
        new_roots = [it for it in new_items if it.parent_id is None]
        new_children = [it for it in new_items if it.parent_id is not None]
        items = roots + new_roots + children + new_children

    result = await capabilities.run(
        "composition.replace_nodes",
        ctx.with_subject(subject_id),
        CompositionReplaceNodesInput(
            subject_id=subject_id,
            scope_type=scope_type,
            owner_id=owner_id,
            composition_id=composition_id,
            expected_revision=expected_revision,
            items=items,
        ),
    )
    return {
        "composition_id": composition_id,
        "revision": result.revision,
        "mode": mode,
        "added_nodes": len(new_items),
        "total_nodes": len(result.nodes),
    }


_SHOW_FIELDS = {
    "type": "object",
    "properties": {k: {"type": "boolean"} for k in ("answer", "thinking", "analysis", "summary")},
}

_AUTHORING_NODE = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": ["heading", "rich_text", "question", "question_group", "question_details", "answer_space", "page_break"],
            "description": (
                "heading = section title; rich_text = text paragraphs; question = a question from the bank; "
                "question_group = a material/stimulus with its sub-questions; question_details = answer key module "
                "(lists answers of the questions in the composition); answer_space = blank area for answers; "
                "page_break = page break."
            ),
        },
        "text": {"type": "string", "description": "heading only: plain-text title."},
        "level": {"type": "integer", "minimum": 1, "maximum": 4, "description": "heading only: level, default 2."},
        "markdown": {
            "type": "string",
            "description": (
                "rich_text only: content in Markdown. Supports $inline math$, $$block math$$, lists and tables. "
                "Multiple paragraphs become multiple nodes."
            ),
        },
        "question_id": {"type": "integer", "description": "question only: question ID from search_questions."},
        "score": {"type": "number", "description": "question only: points for this question."},
        "number": {"type": "string", "description": "question only: custom question number."},
        "show": {**_SHOW_FIELDS, "description": "question only: show these fields under the question, e.g. {\"analysis\": true} for worked examples."},
        "stimulus_id": {"type": "integer", "description": "question_group only: the material (stimulus) ID."},
        "question_ids": {
            "type": "array", "items": {"type": "integer"},
            "description": "question_group only: IDs of the sub-questions of that material, in order.",
        },
        "details_scope": {
            "type": "string", "enum": ["all", "before"],
            "description": "question_details only: include all questions or only those before the module. Default all.",
        },
        "details_fields": {**_SHOW_FIELDS, "description": "question_details only: fields to include. Default answer only."},
        "lines": {"type": "integer", "description": "answer_space only: number of lines, default 4."},
        "style": {"type": "string", "enum": ["blank", "lined"], "description": "answer_space only: default lined."},
    },
    "required": ["type"],
}


_SUBJECT_ID = {"type": "integer", "description": "Subject ID, see list_subjects."}
_SCOPE_TYPE = {
    "type": "string",
    "enum": [s.value for s in ScopeType],
    "description": "shared = shared with the subject team; personal = visible only to you.",
}


def _schema(properties: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def _read_tools() -> List[McpTool]:
    return [
        McpTool(
            name="list_subjects",
            description="List the subjects the current user can access. Almost every other tool needs a subject_id, so call this first.",
            input_schema=_schema({}, []),
            handler=_list_subjects,
            read_only=True,
        ),
        McpTool(
            name="search_questions",
            description="Search questions in a subject, paginated. Only questions visible to the current user are returned.",
            input_schema=_schema({
                "subject_id": _SUBJECT_ID,
                "keyword": {"type": "string", "description": "Keyword matched against the question stem."},
                "knowledge_point_ids": {"type": "array", "items": {"type": "integer"}},
                "tag_ids": {"type": "array", "items": {"type": "integer"}},
                "q_type": {"type": "string", "enum": [t.value for t in QuestionType]},
                "difficulty": {"type": "integer"},
                "status": {"type": "string", "description": "draft / pending / published / rejected"},
                "page": {"type": "integer", "minimum": 1, "default": 1},
                "size": {"type": "integer", "minimum": 1, "maximum": _LIST_LIMIT_MAX, "default": 20},
            }, ["subject_id"]),
            handler=_search_questions,
            read_only=True,
        ),
        McpTool(
            name="get_question",
            description="Get the full content of a question by ID: stem, options, answer, explanation, knowledge points and tags.",
            input_schema=_schema({"id": {"type": "integer"}}, ["id"]),
            handler=_get_question,
            read_only=True,
        ),
        McpTool(
            name="check_question_duplicates",
            description=(
                "Check whether the bank already has duplicate or highly similar questions for a draft, without "
                "creating anything. Formatting differences (spaces, punctuation, numbering, LaTeX spacing, option "
                "order) are ignored. level=duplicate means the same question; level=similar with variant=true "
                "means only numbers/formulas differ."
            ),
            input_schema=_schema({
                "subject_id": _SUBJECT_ID,
                "q_type": {"type": "string", "enum": [t.value for t in QuestionType]},
                "content": {"type": "object", "description": "Question stem as a RichDoc (same as question_create)."},
                "options": {"type": "array", "items": {"type": "object"}, "description": "Options as in question_create."},
                "stimulus_id": {"type": "integer", "description": "Material the question belongs to, if any."},
                "exclude_question_id": {"type": "integer", "description": "Ignore this question (when editing it)."},
            }, ["subject_id", "q_type", "content"]),
            handler=_check_duplicates,
            read_only=True,
        ),
        McpTool(
            name="list_knowledge_points",
            description="List the knowledge points of a subject as a flat list (parent_id encodes the hierarchy), optionally filtered by name.",
            input_schema=_schema({
                "subject_id": _SUBJECT_ID,
                "keyword": {"type": "string"},
            }, ["subject_id"]),
            handler=_list_knowledge_points,
            read_only=True,
        ),
        McpTool(
            name="list_tags",
            description="List all tags of a subject with their categories. Use these IDs when tagging questions.",
            input_schema=_schema({"subject_id": _SUBJECT_ID}, ["subject_id"]),
            handler=_list_tags,
            read_only=True,
        ),
        McpTool(
            name="create_media_upload_url",
            description=(
                "Get a short-lived URL (valid for 10 minutes) to upload an image or audio file into a subject's media library. "
                "Upload the local file with a multipart POST, e.g. `curl -sS -F 'file=@plot.png' '<upload_url>'` - "
                "the file never passes through the conversation. The response contains `asset_id` and a ready-to-use `node` "
                "(e.g. {\"type\": \"image\", \"attrs\": {\"src\": \"/api/v1/media/<id>/content\", \"assetId\": <id>}}) "
                "to put into question content (RichDoc), e.g. as a block inside the doc or next to text in a paragraph. "
                "The asset can only be used in questions of the same subject. SVG is not accepted; render charts to PNG first."
            ),
            input_schema=_schema({"subject_id": _SUBJECT_ID}, ["subject_id"]),
            handler=_create_media_upload_url,
            read_only=False,
        ),
        McpTool(
            name="list_composition_folders",
            description="List the composition folders in a subject and scope.",
            input_schema=_schema({
                "subject_id": _SUBJECT_ID,
                "scope_type": _SCOPE_TYPE,
            }, ["subject_id", "scope_type"]),
            handler=_list_folders,
            read_only=True,
        ),
        McpTool(
            name="list_compositions",
            description="List the compositions (draft papers) in a subject and scope.",
            input_schema=_schema({
                "subject_id": _SUBJECT_ID,
                "scope_type": _SCOPE_TYPE,
                "folder_id": {"type": "integer"},
                "keyword": {"type": "string"},
            }, ["subject_id", "scope_type"]),
            handler=_list_compositions,
            read_only=True,
        ),
        McpTool(
            name="composition_write_nodes",
            description=(
                "Add content to a composition (paper) using simple layout nodes: headings, Markdown text, questions "
                "from the bank, material groups, answer spaces, page breaks and an answer key. The server builds the "
                "internal node tree, IDs and question snapshots for you. mode='append' (default) keeps the existing "
                "content and adds the nodes at the end; mode='replace' discards all existing content. "
                "Typical flow: composition_create (revision 1) -> composition_write_nodes. "
                "Requires the current revision as expected_revision; the new revision is returned."
            ),
            input_schema=_schema({
                "subject_id": _SUBJECT_ID,
                "scope_type": _SCOPE_TYPE,
                "composition_id": {"type": "integer"},
                "expected_revision": {"type": "integer", "description": "Current revision (a new composition starts at 1)."},
                "mode": {"type": "string", "enum": ["append", "replace"], "default": "append"},
                "nodes": {"type": "array", "items": _AUTHORING_NODE, "description": "Nodes in top-to-bottom layout order."},
            }, ["subject_id", "scope_type", "composition_id", "expected_revision", "nodes"]),
            handler=_write_composition_nodes,
            read_only=False,
        ),
        McpTool(
            name="get_composition",
            description=(
                "Get the full content of a composition, including its node tree and current revision. "
                "Tools that modify a composition require expected_revision, so read the latest value here first."
            ),
            input_schema=_schema({
                "subject_id": _SUBJECT_ID,
                "scope_type": _SCOPE_TYPE,
                "composition_id": {"type": "integer"},
            }, ["subject_id", "scope_type", "composition_id"]),
            handler=_get_composition,
            read_only=True,
        ),
    ]


_TOOLS: Optional[Dict[str, McpTool]] = None


def all_tools() -> Dict[str, McpTool]:
    global _TOOLS
    if _TOOLS is None:
        tools: Dict[str, McpTool] = {tool.name: tool for tool in _read_tools()}
        for cap in capabilities.all_capabilities():
            if cap.name in EXCLUDED_CAPABILITIES:
                continue
            tool = _capability_tool(cap)
            if tool.name in tools:
                raise RuntimeError(f"Duplicate MCP tool name: {tool.name}")
            tools[tool.name] = tool
        _TOOLS = tools
    return _TOOLS


def to_text(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)
