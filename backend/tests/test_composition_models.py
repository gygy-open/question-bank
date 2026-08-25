"""组稿 (Composition) 第一阶段模型的聚焦测试。

覆盖:scope/owner 与 question 引用的 CheckConstraint、版本号唯一约束、ORM 级联删除,
以及 Pydantic schema 对 scope/owner 与 question 引用规则的镜像校验。
"""
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.composition import (
    Composition,
    CompositionBlock,
    CompositionBlockType,
    CompositionEvent,
    CompositionVersion,
    Folder,
    ScopeType,
)
from app.models.subject import Subject
from app.models.user import User
from app.schemas.composition import (
    CompositionBlockCreate,
    CompositionCreate,
    FolderCreate,
)


async def _seed_user_subject(db_session):
    user = User(username="alice", full_name="Alice", hashed_password="x")
    subject = Subject(name="数学", slug="math")
    db_session.add_all([user, subject])
    await db_session.flush()
    return user, subject


def _make_version(comp, subject, user, version_no=1, snapshot=None):
    """构造携带全部必填字段的版本快照。"""
    return CompositionVersion(
        composition_id=comp.id,
        version_no=version_no,
        source_revision=comp.revision,
        title=comp.title,
        subject_id=subject.id,
        snapshot=snapshot if snapshot is not None else {"blocks": []},
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


async def test_non_question_block_with_question_ref_violates_check(db_session):
    _, subject = await _seed_user_subject(db_session)
    comp = Composition(title="稿", scope_type=ScopeType.SHARED, subject_id=subject.id)
    db_session.add(comp)
    await db_session.flush()

    bad = CompositionBlock(
        composition_id=comp.id,
        sequence=0,
        block_type=CompositionBlockType.RICH_TEXT,
        question_id=123,
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_question_block_without_revision_violates_check(db_session):
    _, subject = await _seed_user_subject(db_session)
    comp = Composition(title="稿", scope_type=ScopeType.SHARED, subject_id=subject.id)
    db_session.add(comp)
    await db_session.flush()

    # question block 必须同时携带 question_id 与 question_revision。
    bad = CompositionBlock(
        composition_id=comp.id,
        sequence=0,
        block_type=CompositionBlockType.QUESTION,
        question_id=123,
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_composition_and_block_revision_defaults(db_session):
    _, subject = await _seed_user_subject(db_session)
    comp = Composition(title="稿", scope_type=ScopeType.SHARED, subject_id=subject.id)
    comp.blocks = [
        CompositionBlock(sequence=0, block_type=CompositionBlockType.PAGE_BREAK),
    ]
    db_session.add(comp)
    await db_session.commit()

    assert comp.revision == 1
    assert comp.blocks[0].schema_version == 1


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

    # 缺 finalized_by(NOT NULL)。
    bad = CompositionVersion(
        composition_id=comp.id,
        version_no=1,
        source_revision=comp.revision,
        title=comp.title,
        subject_id=subject.id,
        snapshot={"blocks": []},
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_event_requires_actor_and_summary(db_session):
    _, subject = await _seed_user_subject(db_session)
    comp = Composition(title="稿", scope_type=ScopeType.SHARED, subject_id=subject.id)
    db_session.add(comp)
    await db_session.flush()

    # 缺 actor_id / summary / composition_revision(均 NOT NULL)。
    bad = CompositionEvent(composition_id=comp.id, event_type="created")
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_orm_cascade_deletes_children(db_session):
    user, subject = await _seed_user_subject(db_session)
    comp = Composition(title="稿", scope_type=ScopeType.SHARED, subject_id=subject.id)
    comp.blocks = [
        CompositionBlock(sequence=0, block_type=CompositionBlockType.HEADING, content={"level": 1}),
        CompositionBlock(sequence=1, block_type=CompositionBlockType.PAGE_BREAK),
    ]
    comp.versions = [
        CompositionVersion(
            version_no=1,
            source_revision=1,
            title="稿",
            subject_id=subject.id,
            snapshot={"blocks": []},
            finalized_by=user.id,
        )
    ]
    comp.events = [
        CompositionEvent(
            composition_revision=1,
            event_type="created",
            summary="created",
            actor_id=user.id,
        )
    ]
    db_session.add(comp)
    await db_session.commit()

    await db_session.delete(comp)
    await db_session.commit()

    assert (await db_session.execute(select(CompositionBlock))).scalars().all() == []
    assert (await db_session.execute(select(CompositionVersion))).scalars().all() == []
    assert (await db_session.execute(select(CompositionEvent))).scalars().all() == []


def test_schema_scope_owner_mirror():
    with pytest.raises(ValidationError):
        FolderCreate(name="x", scope_type=ScopeType.SHARED, subject_id=1, owner_id=9)
    with pytest.raises(ValidationError):
        CompositionCreate(title="x", scope_type=ScopeType.PERSONAL, subject_id=1)

    ok = CompositionCreate(title="x", scope_type=ScopeType.PERSONAL, subject_id=1, owner_id=7)
    assert ok.owner_id == 7


def test_schema_block_question_ref_mirror():
    with pytest.raises(ValidationError):
        CompositionBlockCreate(
            sequence=0, block_type=CompositionBlockType.RICH_TEXT, question_id=5
        )

    # question block 缺 revision 也应被拒绝。
    with pytest.raises(ValidationError):
        CompositionBlockCreate(
            sequence=0, block_type=CompositionBlockType.QUESTION, question_id=5
        )

    ok = CompositionBlockCreate(
        sequence=0, block_type=CompositionBlockType.QUESTION, question_id=5, question_revision=2
    )
    assert ok.question_id == 5
    # schema_version 默认为 1。
    assert ok.schema_version == 1
