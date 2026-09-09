"""AI 工具层契约与鉴权。

Phase 5 的核心变更:写工具不再直连 CRUD,而是走 `capabilities.run`,
因此 **AI 工具第一次受 RBAC 约束**。此前只要登录就能让 AI 建题。
"""
import json

import pytest

from app.ai import tools as ai_tools
from app.ai.contracts import ToolResult
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
    }


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


async def test_search_questions_uses_actor_as_viewer(db_session, ctx):
    """检索必须套用调用者的可见性,否则 AI 成了越权读取的旁路。"""
    other_subject = Subject(name="物理", slug="phys")
    db_session.add(other_subject)
    await db_session.commit()
    await db_session.refresh(other_subject)

    db_session.add(Question(
        content=json.dumps({"type": "doc", "content": [{"type": "paragraph"}]}),
        q_type="free_response",
        subject_id=other_subject.id,
        created_by=ctx["editor"].id,
        visibility="public",
    ))
    await db_session.commit()

    ec = await _ctx_for(db_session, ctx["editor"], ctx["subject"].id)
    result = await ai_tools.dispatch("search_questions", ec, {"keyword": ""})
    assert result.content == "No questions found matching the criteria."
