"""组稿 (Composition) AST 模型的聚焦测试。

覆盖:scope/owner 与 question 引用的 CheckConstraint、版本号唯一约束、ORM 级联删除
(含自引用节点),以及 Pydantic node 契约对 scope/owner、kind/type、UUID 与 payload
规则的镜像校验。
"""
import json
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.composition import (
    BODY_SLOT,
    Composition,
    CompositionEvent,
    CompositionNode,
    CompositionNodeKind,
    CompositionVersion,
    Folder,
    NODE_TYPE_ANSWER_ITEM,
    NODE_TYPE_HEADING,
    NODE_TYPE_PAGE_BREAK,
    NODE_TYPE_QUESTION,
    NODE_TYPE_QUESTION_DETAILS,
    NODE_TYPE_RICH_TEXT,
    ScopeType,
)
from app.models.question import Question, QuestionType
from app.models.subject import Subject
from app.models.user import User
from app.schemas.composition import (
    CompositionCreate,
    CompositionNodeInput,
    FolderCreate,
)


def _uid() -> str:
    return str(uuid.uuid4())


def _rich_doc(text: str = "x") -> dict:
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


async def _seed_user_subject(db_session):
    user = User(username="alice", full_name="Alice", hashed_password="x")
    subject = Subject(name="数学", slug="math")
    db_session.add_all([user, subject])
    await db_session.flush()
    return user, subject


async def _seed_question(db_session, *, subject_id: int) -> Question:
    q = Question(
        content=json.dumps(_rich_doc(), ensure_ascii=False),
        q_type=QuestionType.FREE_RESPONSE,
        subject_id=subject_id,
    )
    db_session.add(q)
    await db_session.flush()
    return q


def _make_version(comp, subject, user, version_no=1, snapshot=None):
    return CompositionVersion(
        composition_id=comp.id,
        version_no=version_no,
        source_revision=comp.revision,
        title=comp.title,
        subject_id=subject.id,
        snapshot=snapshot if snapshot is not None else {"nodes": []},
        finalized_by=user.id,
    )


async def test_shared_and_personal_folders_persist(db_session):
    user, subject = await _seed_user_subject(db_session)

    shared = Folder(name="共享", scope_type=ScopeType.SHARED, subject_id=subject.id)
    personal = Folder(
        name="我的", scope_type=ScopeType.PERSONAL, owner_id=user.id, subject_id=subject.id
    )
    db_session.add_all([shared, personal])
    await db_session.commit()

    assert shared.owner_id is None
    assert personal.owner_id == user.id


async def test_shared_folder_with_owner_violates_check(db_session):
    _, subject = await _seed_user_subject(db_session)
    user2 = User(username="bob", hashed_password="x")
    db_session.add(user2)
    await db_session.flush()

    bad = Folder(
        name="非法", scope_type=ScopeType.SHARED, owner_id=user2.id, subject_id=subject.id
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_personal_composition_without_owner_violates_check(db_session):
    _, subject = await _seed_user_subject(db_session)

    bad = Composition(
        title="缺 owner", scope_type=ScopeType.PERSONAL, subject_id=subject.id
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_non_question_node_with_question_ref_violates_check(db_session):
    _, subject = await _seed_user_subject(db_session)
    comp = Composition(title="稿", scope_type=ScopeType.SHARED, subject_id=subject.id)
    db_session.add(comp)
    await db_session.flush()
    q = await _seed_question(db_session, subject_id=subject.id)

    bad = CompositionNode(
        id=_uid(),
        composition_id=comp.id,
        position=0,
        node_kind=CompositionNodeKind.BLOCK,
        node_type=NODE_TYPE_RICH_TEXT,
        question_id=q.id,
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_question_node_without_question_id_violates_check(db_session):
    _, subject = await _seed_user_subject(db_session)
    comp = Composition(title="稿", scope_type=ScopeType.SHARED, subject_id=subject.id)
    db_session.add(comp)
    await db_session.flush()

    bad = CompositionNode(
        id=_uid(),
        composition_id=comp.id,
        position=0,
        node_kind=CompositionNodeKind.BLOCK,
        node_type=NODE_TYPE_QUESTION,
        question_id=None,
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_composition_and_node_defaults(db_session):
    _, subject = await _seed_user_subject(db_session)
    comp = Composition(title="稿", scope_type=ScopeType.SHARED, subject_id=subject.id)
    db_session.add(comp)
    await db_session.flush()
    node = CompositionNode(
        id=_uid(),
        composition_id=comp.id,
        position=0,
        node_kind=CompositionNodeKind.BLOCK,
        node_type=NODE_TYPE_PAGE_BREAK,
    )
    db_session.add(node)
    await db_session.commit()

    assert comp.revision == 1
    assert node.schema_version == 1
    assert node.parent_id is None


async def test_self_referential_parent_persists(db_session):
    _, subject = await _seed_user_subject(db_session)
    comp = Composition(title="稿", scope_type=ScopeType.SHARED, subject_id=subject.id)
    db_session.add(comp)
    await db_session.flush()

    module_id = _uid()
    module = CompositionNode(
        id=module_id,
        composition_id=comp.id,
        position=0,
        node_kind=CompositionNodeKind.MODULE,
        node_type=NODE_TYPE_QUESTION_DETAILS,
        props={"scope": "all", "fields": {"answer": True}},
    )
    db_session.add(module)
    await db_session.flush()  # 父先落库,满足自引用 FK。

    child = CompositionNode(
        id=_uid(),
        composition_id=comp.id,
        parent_id=module_id,
        slot=BODY_SLOT,
        position=0,
        node_kind=CompositionNodeKind.BLOCK,
        node_type=NODE_TYPE_HEADING,
        content=_rich_doc("小标题"),
        props={"level": 2},
    )
    db_session.add(child)
    await db_session.commit()

    assert child.parent_id == module_id
    assert child.slot == BODY_SLOT


async def test_version_no_unique_per_composition(db_session):
    user, subject = await _seed_user_subject(db_session)
    comp = Composition(title="稿", scope_type=ScopeType.SHARED, subject_id=subject.id)
    db_session.add(comp)
    await db_session.flush()

    db_session.add(_make_version(comp, subject, user, version_no=1, snapshot={"a": 1}))
    await db_session.commit()

    db_session.add(_make_version(comp, subject, user, version_no=1, snapshot={"b": 2}))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_version_requires_finalized_by(db_session):
    _, subject = await _seed_user_subject(db_session)
    comp = Composition(title="稿", scope_type=ScopeType.SHARED, subject_id=subject.id)
    db_session.add(comp)
    await db_session.flush()

    bad = CompositionVersion(
        composition_id=comp.id,
        version_no=1,
        source_revision=comp.revision,
        title=comp.title,
        subject_id=subject.id,
        snapshot={"nodes": []},
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_event_requires_actor_and_summary(db_session):
    _, subject = await _seed_user_subject(db_session)
    comp = Composition(title="稿", scope_type=ScopeType.SHARED, subject_id=subject.id)
    db_session.add(comp)
    await db_session.flush()

    bad = CompositionEvent(composition_id=comp.id, event_type="created")
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_orm_cascade_deletes_children(db_session):
    user, subject = await _seed_user_subject(db_session)
    comp = Composition(title="稿", scope_type=ScopeType.SHARED, subject_id=subject.id)
    db_session.add(comp)
    await db_session.flush()

    q = await _seed_question(db_session, subject_id=subject.id)
    question_node_id = _uid()
    module_id = _uid()
    # root 层节点先落库(含 module 与 question)。
    db_session.add_all(
        [
            CompositionNode(
                id=question_node_id, composition_id=comp.id, position=0,
                node_kind=CompositionNodeKind.BLOCK, node_type=NODE_TYPE_QUESTION,
                question_id=q.id, question_revision=1, content={"q_type": "free_response"},
            ),
            CompositionNode(
                id=module_id, composition_id=comp.id, position=1,
                node_kind=CompositionNodeKind.MODULE, node_type=NODE_TYPE_QUESTION_DETAILS,
                props={"scope": "all", "fields": {}},
            ),
        ]
    )
    await db_session.flush()
    # module 子节点后落库(自引用 FK)。
    db_session.add(
        CompositionNode(
            id=_uid(), composition_id=comp.id, parent_id=module_id, slot=BODY_SLOT, position=0,
            node_kind=CompositionNodeKind.REFERENCE, node_type=NODE_TYPE_ANSWER_ITEM,
            source_question_node_id=question_node_id,
            props={"included": True, "overrides": {}},
        )
    )
    db_session.add(
        CompositionVersion(
            composition_id=comp.id, version_no=1, source_revision=1, title="稿",
            subject_id=subject.id, snapshot={"nodes": []}, finalized_by=user.id,
        )
    )
    db_session.add(
        CompositionEvent(
            composition_id=comp.id, composition_revision=1, event_type="created",
            summary="created", actor_id=user.id,
        )
    )
    await db_session.commit()

    await db_session.delete(comp)
    await db_session.commit()

    assert (await db_session.execute(select(CompositionNode))).scalars().all() == []
    assert (await db_session.execute(select(CompositionVersion))).scalars().all() == []
    assert (await db_session.execute(select(CompositionEvent))).scalars().all() == []


def test_schema_scope_owner_mirror():
    with pytest.raises(ValidationError):
        FolderCreate(name="x", scope_type=ScopeType.SHARED, subject_id=1, owner_id=9)
    with pytest.raises(ValidationError):
        CompositionCreate(title="x", scope_type=ScopeType.PERSONAL, subject_id=1)

    ok = CompositionCreate(title="x", scope_type=ScopeType.PERSONAL, subject_id=1, owner_id=7)
    assert ok.owner_id == 7


def test_schema_node_requires_valid_uuid():
    with pytest.raises(ValidationError):
        CompositionNodeInput(
            id="not-a-uuid", node_kind=CompositionNodeKind.BLOCK, node_type=NODE_TYPE_PAGE_BREAK
        )


def test_schema_node_kind_type_mismatch_rejected():
    # block 不能声明 module 的 node_type。
    with pytest.raises(ValidationError):
        CompositionNodeInput(
            id=_uid(), node_kind=CompositionNodeKind.BLOCK, node_type=NODE_TYPE_QUESTION_DETAILS
        )


def test_schema_question_node_requires_question_id():
    with pytest.raises(ValidationError):
        CompositionNodeInput(
            id=_uid(), node_kind=CompositionNodeKind.BLOCK, node_type=NODE_TYPE_QUESTION
        )
    ok = CompositionNodeInput(
        id=_uid(), node_kind=CompositionNodeKind.BLOCK, node_type=NODE_TYPE_QUESTION, question_id=5
    )
    assert ok.question_id == 5
    assert ok.schema_version == 1


def test_schema_child_slot_and_root_slot_rules():
    # root 节点携带 slot → 非法。
    with pytest.raises(ValidationError):
        CompositionNodeInput(
            id=_uid(), slot=BODY_SLOT, node_kind=CompositionNodeKind.BLOCK,
            node_type=NODE_TYPE_PAGE_BREAK,
        )
    # answer_item(子节点)必须有父 + slot=body。
    with pytest.raises(ValidationError):
        CompositionNodeInput(
            id=_uid(), node_kind=CompositionNodeKind.REFERENCE, node_type=NODE_TYPE_ANSWER_ITEM,
            source_question_node_id=_uid(),
        )
    ok = CompositionNodeInput(
        id=_uid(), parent_id=_uid(), slot=BODY_SLOT,
        node_kind=CompositionNodeKind.REFERENCE, node_type=NODE_TYPE_ANSWER_ITEM,
        source_question_node_id=_uid(),
        props={"included": True, "overrides": {
            "answer": None, "thinking": None, "analysis": None, "summary": None,
        }},
    )
    assert ok.slot == BODY_SLOT


def test_schema_question_details_props_validation():
    with pytest.raises(ValidationError):
        CompositionNodeInput(
            id=_uid(), node_kind=CompositionNodeKind.MODULE, node_type=NODE_TYPE_QUESTION_DETAILS,
            props={"scope": "sometimes", "fields": {}},
        )
    ok = CompositionNodeInput(
        id=_uid(), node_kind=CompositionNodeKind.MODULE, node_type=NODE_TYPE_QUESTION_DETAILS,
        props={"scope": "before", "fields": {
            "answer": True, "thinking": False, "analysis": False, "summary": False,
        }},
    )
    assert ok.props["scope"] == "before"
