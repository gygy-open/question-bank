"""组稿 AI 工具的端到端契约。

覆盖:建稿 → 写节点的完整链路、系统拥有字段不可被模型伪造、
Phase A 门禁在工具通道上同样生效、以及各类失败是否给了模型可操作的提示。
"""
import json

import pytest
from sqlalchemy import select

from app.ai import tools as ai_tools
from app.capabilities.context import ExecutionContext, Surface
from app.crud.crud_user import user as crud_user
from app.models.composition import Composition, CompositionNode, ScopeType
from app.models.question import Question, QuestionType
from app.models.subject import Subject
from app.models.subject_member import SubjectMember
from app.models.user import User

_DOC = json.dumps({"type": "doc", "content": [{"type": "paragraph"}]}, ensure_ascii=False)


async def _ctx_for(db_session, user, subject_id):
    actor = await crud_user.get_with_memberships(db_session, id=user.id)
    return ExecutionContext(
        db=db_session, actor=actor, surface=Surface.CHAT, subject_id=subject_id
    )


@pytest.fixture
async def ctx(db_session):
    subject = Subject(name="数学", slug="math")
    other_subject = Subject(name="物理", slug="phys")
    db_session.add_all([subject, other_subject])
    await db_session.commit()
    await db_session.refresh(subject)
    await db_session.refresh(other_subject)

    editor = User(username="e", full_name="e", hashed_password="x", is_active=True)
    outsider = User(username="o", full_name="o", hashed_password="x", is_active=True)
    db_session.add_all([editor, outsider])
    await db_session.commit()
    await db_session.refresh(editor)
    await db_session.refresh(outsider)

    db_session.add(SubjectMember(user_id=editor.id, subject_id=subject.id, role="editor"))
    await db_session.commit()

    question = Question(
        content=_DOC, q_type=QuestionType.FREE_RESPONSE, subject_id=subject.id,
        created_by=editor.id, visibility="public",
    )
    db_session.add(question)
    await db_session.commit()
    await db_session.refresh(question)

    return {
        "subject": subject, "other_subject": other_subject,
        "editor": editor, "outsider": outsider, "question": question,
    }


async def _create(db_session, ctx, actor="editor", **args):
    ec = await _ctx_for(db_session, ctx[actor], ctx["subject"].id)
    return await ai_tools.dispatch("create_composition", ec, {"title": "期中卷", **args})


# --------------------------------------------------------------------------- #
# 建稿
# --------------------------------------------------------------------------- #
async def test_create_composition_returns_id_and_revision(db_session, ctx):
    result = await _create(db_session, ctx)
    assert result.data["composition_id"]
    # 新建稿件恒为 revision 1,模型下一步写入要用它。
    assert result.data["revision"] == 1
    assert "revision=1" in result.content


async def test_create_defaults_to_personal_and_forces_owner(db_session, ctx):
    """模型不能伪造 owner_id;personal 的 owner 强制是调用者本人。"""
    result = await _create(db_session, ctx, owner_id=99999)
    comp = await db_session.get(Composition, result.data["composition_id"])
    assert comp.scope_type == ScopeType.PERSONAL
    assert comp.owner_id == ctx["editor"].id


async def test_create_shared_has_no_owner(db_session, ctx):
    result = await _create(db_session, ctx, scope="shared")
    comp = await db_session.get(Composition, result.data["composition_id"])
    assert comp.scope_type == ScopeType.SHARED
    assert comp.owner_id is None


async def test_non_member_cannot_create(db_session, ctx):
    """Phase A 的门禁必须在工具通道上同样生效。"""
    result = await _create(db_session, ctx, actor="outsider")
    assert "权限" in result.content
    assert result.data is None
    assert (await db_session.execute(select(Composition))).scalars().all() == []


async def test_create_without_subject_is_explained(db_session, ctx):
    actor = await crud_user.get_with_memberships(db_session, id=ctx["editor"].id)
    ec = ExecutionContext(db=db_session, actor=actor, surface=Surface.CHAT, subject_id=None)
    result = await ai_tools.dispatch("create_composition", ec, {"title": "x"})
    assert "没有选定学科" in result.content


# --------------------------------------------------------------------------- #
# 写节点
# --------------------------------------------------------------------------- #
async def _write(db_session, ctx, comp_id, nodes, *, revision=1, actor="editor", scope=None):
    ec = await _ctx_for(db_session, ctx[actor], ctx["subject"].id)
    args = {"composition_id": comp_id, "expected_revision": revision, "nodes": nodes}
    if scope:
        args["scope"] = scope
    return await ai_tools.dispatch("write_composition_nodes", ec, args)


async def test_write_nodes_end_to_end(db_session, ctx):
    created = await _create(db_session, ctx)
    cid = created.data["composition_id"]

    result = await _write(db_session, ctx, cid, [
        {"type": "heading", "text": "一、例题", "level": 2},
        {"type": "rich_text", "markdown": "先看这道题。\n\n注意定义域。"},
        {"type": "question", "question_id": ctx["question"].id, "score": 5,
         "show": {"analysis": True}},
        {"type": "question_details", "details_scope": "all"},
    ])

    assert result.data["revision"] == 2, result.content
    rows = (await db_session.execute(
        select(CompositionNode).where(CompositionNode.composition_id == cid)
    )).scalars().all()
    types = [r.node_type for r in rows]
    assert types.count("rich_text") == 2  # 两个段落各自成节点
    assert "heading" in types and "question" in types and "question_details" in types
    # answer_item 由服务端按 module scope 派生,AI 并没有发。
    assert "answer_item" in types


async def test_question_snapshot_is_frozen_by_the_server(db_session, ctx):
    """AI 只给 question_id,内容快照必须由服务端从题库实时生成。"""
    created = await _create(db_session, ctx)
    cid = created.data["composition_id"]
    await _write(db_session, ctx, cid, [
        {"type": "question", "question_id": ctx["question"].id},
    ])
    node = (await db_session.execute(
        select(CompositionNode).where(
            CompositionNode.composition_id == cid,
            CompositionNode.node_type == "question",
        )
    )).scalar_one()
    assert node.content is not None
    assert node.question_revision == ctx["question"].content_revision


async def test_revision_mismatch_is_actionable(db_session, ctx):
    created = await _create(db_session, ctx)
    cid = created.data["composition_id"]
    result = await _write(db_session, ctx, cid, [{"type": "page_break"}], revision=99)
    assert "revision" in result.content
    assert "不要直接重试" in result.content
    assert result.data is None


async def test_cross_subject_question_is_actionable(db_session, ctx):
    other_q = Question(
        content=_DOC, q_type=QuestionType.FREE_RESPONSE,
        subject_id=ctx["other_subject"].id, created_by=ctx["editor"].id, visibility="public",
    )
    db_session.add(other_q)
    await db_session.commit()
    await db_session.refresh(other_q)

    created = await _create(db_session, ctx)
    cid = created.data["composition_id"]
    result = await _write(db_session, ctx, cid, [
        {"type": "question", "question_id": other_q.id},
    ])
    assert "search_questions" in result.content


async def test_bad_node_spec_is_explained_not_swallowed(db_session, ctx):
    """dispatch 的兜底会压成无用的 'Error executing tool',工具必须自己先解释。"""
    created = await _create(db_session, ctx)
    cid = created.data["composition_id"]
    result = await _write(db_session, ctx, cid, [{"type": "toc"}])
    assert "节点描述有误" in result.content
    assert "Error executing tool" not in result.content


async def test_empty_nodes_is_refused(db_session, ctx):
    """整份写入语义下,空列表等于清空稿件 —— 不能默默照做。"""
    created = await _create(db_session, ctx)
    result = await _write(db_session, ctx, created.data["composition_id"], [])
    assert "清空" in result.content


async def test_non_member_cannot_write(db_session, ctx):
    created = await _create(db_session, ctx)
    cid = created.data["composition_id"]
    result = await _write(db_session, ctx, cid, [{"type": "page_break"}], actor="outsider")
    assert result.data is None
    assert (await db_session.execute(
        select(CompositionNode).where(CompositionNode.composition_id == cid)
    )).scalars().all() == []
