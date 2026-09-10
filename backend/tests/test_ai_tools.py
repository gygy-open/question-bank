"""AI 工具层契约与鉴权。

Phase 5 的核心变更:写工具不再直连 CRUD,而是走 `capabilities.run`,
因此 **AI 工具第一次受 RBAC 约束**。此前只要登录就能让 AI 建题。
"""
import json

import pytest

from app.ai import tools as ai_tools
from app.ai.contracts import AgentScene, ToolResult
from app.capabilities.context import ExecutionContext, Surface
from app.crud.crud_user import user as crud_user
from app.models.question import Question, QuestionStatus
from app.models.subject import Subject
from app.models.subject_member import SubjectMember
from app.models.user import User
from sqlalchemy import select

_DRAFT_ARGS = {
    "content": "1 + 1 = ?",
    "q_type": "free_response",
    "answer": "2",
}


async def _ctx_for(db_session, user: User, subject_id: int) -> ExecutionContext:
    # capabilities 判权读 user.subject_memberships,必须走带 selectinload 的取用。
    actor = await crud_user.get_with_memberships(db_session, id=user.id)
    return ExecutionContext(
        db=db_session, actor=actor, surface=Surface.CHAT, subject_id=subject_id
    )


@pytest.fixture
async def ctx(db_session):
    subject = Subject(name="数学", slug="math")
    db_session.add(subject)
    await db_session.commit()
    await db_session.refresh(subject)

    editor = User(username="e", full_name="e", hashed_password="x", is_active=True)
    viewer = User(username="v", full_name="v", hashed_password="x", is_active=True)
    db_session.add_all([editor, viewer])
    await db_session.commit()
    await db_session.refresh(editor)
    await db_session.refresh(viewer)

    db_session.add_all([
        SubjectMember(user_id=editor.id, subject_id=subject.id, role="editor"),
        SubjectMember(user_id=viewer.id, subject_id=subject.id, role="viewer"),
    ])
    await db_session.commit()
    return {"subject": subject, "editor": editor, "viewer": viewer}


# --------------------------------------------------------------------------- #
# 注册表契约
# --------------------------------------------------------------------------- #
def test_registry_exposes_the_expected_tools():
    names = {spec.name for spec in ai_tools.all_tools()}
    assert names == {
        "propose_question_draft",
        "propose_questions_batch",
        "search_questions",
        "search_knowledge_points",
        "get_available_tags",
        "create_composition",
        "write_composition_nodes",
        "open_composition",
    }


def test_client_tools_have_no_server_handler():
    """client 工具由 AgentRunner 推给前端执行,服务端不该有 handler 偷偷跑。"""
    for spec in ai_tools.all_tools():
        if spec.executor == "client":
            assert spec.handler is None, spec.name
            assert not spec.mutating, spec.name


def test_mutating_tools_delegate_to_a_capability():
    """写工具不许自己落库 —— 必须挂到某个 capability 上,才能拿到鉴权与审计。"""
    from app import capabilities

    for spec in ai_tools.all_tools():
        if spec.mutating:
            assert spec.capability, spec.name
            capabilities.get(spec.capability)  # 不存在会抛 LookupError


def test_openai_schemas_are_wellformed():
    for schema in ai_tools.openai_schemas():
        assert schema["type"] == "function"
        params = schema["function"]["parameters"]
        assert params["type"] == "object"
        # Gemini 的 FunctionDeclaration 不吃 $ref/$defs,schema 必须是完全内联的。
        assert "$ref" not in json.dumps(params)


# --------------------------------------------------------------------------- #
# 页面作用域
# --------------------------------------------------------------------------- #
def _names_for(scene):
    return {spec.name for spec in ai_tools.tools_for(scene)}


def test_unscoped_exposes_every_tool():
    """页面没声明场景时行为与引入作用域前一致,不能悄悄少给工具。"""
    assert _names_for(AgentScene.UNSCOPED) == {spec.name for spec in ai_tools.all_tools()}


def test_unknown_scene_falls_back_to_unscoped():
    """前后端版本漂移时不能把聊天打挂。"""
    assert AgentScene.parse("no-such-page") is AgentScene.UNSCOPED
    assert AgentScene.parse(None) is AgentScene.UNSCOPED


def test_composition_editor_drops_the_authoring_tools():
    """两个 propose_* 的嵌套 schema 占全量载荷约 88%,组稿页不该带上它们。"""
    names = _names_for(AgentScene.COMPOSITION_EDITOR)
    assert "propose_question_draft" not in names
    assert "propose_questions_batch" not in names
    assert {"search_questions", "search_knowledge_points", "get_available_tags"} <= names


def test_question_library_keeps_the_authoring_tools():
    names = _names_for(AgentScene.QUESTION_LIBRARY)
    assert {"propose_question_draft", "propose_questions_batch"} <= names


def test_scoping_actually_shrinks_the_payload():
    """作用域的全部意义就是省下这段 —— 退化成不省了要能被发现。

    实测(7 个工具):unscoped 12746 字符 → composition_editor 4485,约 -65%。
    两个 propose_* 的嵌套 schema 就占了 7922。
    """
    full = len(json.dumps(ai_tools.openai_schemas(AgentScene.UNSCOPED), ensure_ascii=False))
    scoped = len(json.dumps(
        ai_tools.openai_schemas(AgentScene.COMPOSITION_EDITOR), ensure_ascii=False
    ))
    assert scoped < full * 0.5


async def test_out_of_scene_dispatch_is_blocked_without_side_effects(db_session, ctx):
    """光不广播不够 —— 模型可能从历史消息里学到工具名,dispatch 必须自己拦。"""
    ec = await _ctx_for(db_session, ctx["editor"], ctx["subject"].id)
    result = await ai_tools.dispatch(
        "propose_question_draft", ec, dict(_DRAFT_ARGS),
        scene=AgentScene.COMPOSITION_EDITOR,
    )
    assert "not available on the current page" in result.content
    assert result.ui == []
    assert len((await db_session.execute(select(Question))).scalars().all()) == 0


async def test_unknown_tool_returns_error_text(db_session, ctx):
    ec = await _ctx_for(db_session, ctx["editor"], ctx["subject"].id)
    result = await ai_tools.dispatch("nope", ec, {})
    assert isinstance(result, ToolResult)
    assert "not found" in result.content


# --------------------------------------------------------------------------- #
# 鉴权(本期最重要的行为变更)
# --------------------------------------------------------------------------- #
async def test_editor_can_propose_draft(db_session, ctx):
    ec = await _ctx_for(db_session, ctx["editor"], ctx["subject"].id)
    result = await ai_tools.dispatch("propose_question_draft", ec, dict(_DRAFT_ARGS))

    assert result.ui and result.ui[0].kind == "proposal"
    assert result.ui[0].payload["type"] == "single"
    ids = result.ui[0].payload["ids"]
    assert len(ids) == 1

    created = (await db_session.execute(select(Question).where(Question.id == ids[0]))).scalar_one()
    assert created.status == QuestionStatus.DRAFT.value
    assert created.subject_id == ctx["subject"].id


async def test_viewer_cannot_propose_draft(db_session, ctx):
    """viewer 无 EDIT_QUESTION:工具被拒,且不中断对话 —— 错误文本回喂给模型。"""
    ec = await _ctx_for(db_session, ctx["viewer"], ctx["subject"].id)
    result = await ai_tools.dispatch("propose_question_draft", ec, dict(_DRAFT_ARGS))

    assert result.ui == []
    assert "privileges" in result.content

    count = len((await db_session.execute(select(Question))).scalars().all())
    assert count == 0


async def test_viewer_cannot_propose_batch(db_session, ctx):
    ec = await _ctx_for(db_session, ctx["viewer"], ctx["subject"].id)
    result = await ai_tools.dispatch(
        "propose_questions_batch", ec, {"questions": [dict(_DRAFT_ARGS)]}
    )

    assert result.ui == []
    assert "Failed to create any proposals" in result.content
    assert len((await db_session.execute(select(Question))).scalars().all()) == 0


async def test_batch_emits_one_proposal_for_all_ids(db_session, ctx):
    ec = await _ctx_for(db_session, ctx["editor"], ctx["subject"].id)
    result = await ai_tools.dispatch(
        "propose_questions_batch",
        ec,
        {"questions": [dict(_DRAFT_ARGS), dict(_DRAFT_ARGS)]},
    )

    assert len(result.ui) == 1
    assert result.ui[0].payload["type"] == "batch"
    assert len(result.ui[0].payload["ids"]) == 2


def _doc(text: str) -> str:
    return json.dumps(
        {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]},
        ensure_ascii=False,
    )


async def _seed_question(db_session, *, subject_id, created_by, text="抛物线", **kw) -> Question:
    q = Question(
        content=_doc(text),
        q_type=kw.pop("q_type", "free_response"),
        subject_id=subject_id,
        created_by=created_by,
        visibility="public",
        **kw,
    )
    db_session.add(q)
    await db_session.commit()
    await db_session.refresh(q)
    return q


async def test_search_questions_uses_actor_as_viewer(db_session, ctx):
    """检索必须套用调用者的可见性,否则 AI 成了越权读取的旁路。"""
    other_subject = Subject(name="物理", slug="phys")
    db_session.add(other_subject)
    await db_session.commit()
    await db_session.refresh(other_subject)

    await _seed_question(
        db_session, subject_id=other_subject.id, created_by=ctx["editor"].id, text="抛物线"
    )

    ec = await _ctx_for(db_session, ctx["editor"], ctx["subject"].id)
    result = await ai_tools.dispatch("search_questions", ec, {"keyword": "抛物线"})
    assert result.content == "No questions found matching the criteria."


async def test_search_questions_requires_at_least_one_filter(db_session, ctx):
    """没有任何筛选条件时不能把整个题库倒给模型。"""
    ec = await _ctx_for(db_session, ctx["editor"], ctx["subject"].id)
    result = await ai_tools.dispatch("search_questions", ec, {})
    assert "至少提供" in result.content


async def test_search_questions_q_type_uses_db_enum_values(db_session, ctx):
    """q_type 必须用 DB 枚举值;历史 schema 给的是中文标签,绑定期就会炸。"""
    await _seed_question(
        db_session, subject_id=ctx["subject"].id, created_by=ctx["editor"].id,
        text="抛物线", q_type="single_choice",
    )
    ec = await _ctx_for(db_session, ctx["editor"], ctx["subject"].id)

    hit = await ai_tools.dispatch(
        "search_questions", ec, {"keyword": "抛物线", "q_type": "single_choice"}
    )
    assert "ID:" in hit.content

    miss = await ai_tools.dispatch(
        "search_questions", ec, {"keyword": "抛物线", "q_type": "free_response"}
    )
    assert miss.content == "No questions found matching the criteria."

    bad = await ai_tools.dispatch(
        "search_questions", ec, {"keyword": "抛物线", "q_type": "选择题"}
    )
    assert "未知的 q_type" in bad.content


async def test_search_questions_scopes_to_current_subject(db_session, ctx):
    """同一道题只在其所属学科的上下文里可见。"""
    other_subject = Subject(name="物理", slug="phys")
    db_session.add(other_subject)
    await db_session.commit()
    await db_session.refresh(other_subject)
    db_session.add(
        SubjectMember(user_id=ctx["editor"].id, subject_id=other_subject.id, role="editor")
    )
    await db_session.commit()

    await _seed_question(
        db_session, subject_id=ctx["subject"].id, created_by=ctx["editor"].id, text="抛物线"
    )

    in_scope = await _ctx_for(db_session, ctx["editor"], ctx["subject"].id)
    assert "ID:" in (await ai_tools.dispatch(
        "search_questions", in_scope, {"keyword": "抛物线"}
    )).content

    out_scope = await _ctx_for(db_session, ctx["editor"], other_subject.id)
    assert (await ai_tools.dispatch(
        "search_questions", out_scope, {"keyword": "抛物线"}
    )).content == "No questions found matching the criteria."


async def test_search_questions_filters_by_knowledge_point_with_descendants(db_session, ctx):
    """知识点筛选自动含下级 —— 传父节点应能命中挂在子节点上的题。"""
    from app.models.knowledge_point import KnowledgePoint

    parent = KnowledgePoint(name="函数", slug="func", subject_id=ctx["subject"].id)
    db_session.add(parent)
    await db_session.commit()
    await db_session.refresh(parent)
    child = KnowledgePoint(
        name="二次函数", slug="quadratic", subject_id=ctx["subject"].id, parent_id=parent.id
    )
    db_session.add(child)
    await db_session.commit()
    await db_session.refresh(child)

    q = await _seed_question(
        db_session, subject_id=ctx["subject"].id, created_by=ctx["editor"].id, text="抛物线"
    )
    await db_session.refresh(q, attribute_names=["knowledge_points"])
    q.knowledge_points.append(child)
    await db_session.commit()

    ec = await _ctx_for(db_session, ctx["editor"], ctx["subject"].id)
    result = await ai_tools.dispatch(
        "search_questions", ec, {"knowledge_point_ids": [parent.id]}
    )
    assert f"ID: {q.id}" in result.content
    assert "二次函数" in result.content


async def test_search_questions_clamps_limit(db_session, ctx):
    """模型可以传 limit: 100000,服务端必须钳住。"""
    for i in range(3):
        await _seed_question(
            db_session, subject_id=ctx["subject"].id, created_by=ctx["editor"].id,
            text=f"抛物线{i}",
        )
    ec = await _ctx_for(db_session, ctx["editor"], ctx["subject"].id)
    result = await ai_tools.dispatch(
        "search_questions", ec, {"keyword": "抛物线", "limit": 100000}
    )
    assert len(result.data["ids"]) == 3
