import json
from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.capabilities.errors import Conflict, Forbidden, Invalid, NotFound, Unprocessable
from app.core.security import create_access_token
from app.models.question import Question, QuestionType, QuestionVisibility
from app.models.question_group import (
    QuestionGroup,
    QuestionGroupItem,
    QuestionRelation,
    Stimulus,
)
from app.models.subject import Subject
from app.models.subject_member import SubjectMember
from app.models.user import User
from app.services.question_group_service import create_question_relation


API = "/api/v1"


def doc(text: str) -> dict:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


@pytest.fixture
async def group_ctx(db_session):
    owner = User(
        username="group_owner",
        full_name="Group Owner",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
    )
    other = User(
        username="group_other",
        full_name="Group Other",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
    )
    humanities = Subject(name="历史", slug="history")
    science = Subject(name="物理", slug="physics-groups")
    db_session.add_all([owner, other, humanities, science])
    await db_session.flush()
    db_session.add_all(
        [
            SubjectMember(user_id=owner.id, subject_id=humanities.id, role="editor"),
            SubjectMember(user_id=owner.id, subject_id=science.id, role="editor"),
            SubjectMember(user_id=other.id, subject_id=humanities.id, role="viewer"),
        ]
    )
    questions = [
        Question(
            content=json.dumps(doc("第一题"), ensure_ascii=False),
            q_type=QuestionType.FREE_RESPONSE,
            subject_id=humanities.id,
            created_by=owner.id,
        ),
        Question(
            content=json.dumps(doc("第二题"), ensure_ascii=False),
            q_type=QuestionType.FREE_RESPONSE,
            subject_id=humanities.id,
            created_by=owner.id,
        ),
        Question(
            content=json.dumps(doc("私有题"), ensure_ascii=False),
            q_type=QuestionType.FREE_RESPONSE,
            subject_id=humanities.id,
            visibility=QuestionVisibility.PRIVATE.value,
            created_by=owner.id,
        ),
        Question(
            content=json.dumps(doc("跨学科题"), ensure_ascii=False),
            q_type=QuestionType.FREE_RESPONSE,
            subject_id=science.id,
            created_by=owner.id,
        ),
    ]
    db_session.add_all(questions)
    await db_session.commit()
    return {
        "owner": owner,
        "other": other,
        "subject": humanities,
        "other_subject": science,
        "questions": questions,
    }


async def _create_stimulus(client, ctx, *, visibility="public") -> dict:
    response = await client.post(
        f"{API}/subjects/{ctx['subject'].id}/stimuli",
        json={"content": doc("阅读材料"), "visibility": visibility},
        headers=_auth(ctx["owner"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _load_actor(db_session, user_id: int) -> User:
    return await db_session.scalar(
        select(User)
        .options(selectinload(User.subject_memberships))
        .where(User.id == user_id)
    )


async def test_group_create_update_order_and_stimulus_reuse(client, group_ctx):
    stimulus = await _create_stimulus(client, group_ctx)
    first, second = group_ctx["questions"][:2]
    create = await client.post(
        f"{API}/subjects/{group_ctx['subject'].id}/question-groups",
        json={
            "stimulus_id": stimulus["id"],
            "items": [
                {"question_id": first.id, "position": 4},
                {"question_id": second.id, "position": 1},
            ],
        },
        headers=_auth(group_ctx["owner"]),
    )
    assert create.status_code == 201, create.text
    group = create.json()
    assert [item["question_id"] for item in group["items"]] == [second.id, first.id]

    reused = await client.post(
        f"{API}/subjects/{group_ctx['subject'].id}/question-groups",
        json={
            "stimulus_id": stimulus["id"],
            "items": [{"question_id": first.id, "position": 0}],
        },
        headers=_auth(group_ctx["owner"]),
    )
    assert reused.status_code == 201, reused.text
    assert reused.json()["stimulus_id"] == stimulus["id"]

    updated = await client.put(
        f"{API}/subjects/{group_ctx['subject'].id}/question-groups/{group['id']}",
        json={
            "expected_revision": group["revision"],
            "items": [{"question_id": second.id, "position": 7}],
        },
        headers=_auth(group_ctx["owner"]),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 2
    assert [(item["question_id"], item["position"]) for item in updated.json()["items"]] == [
        (second.id, 7)
    ]


async def test_group_update_is_atomic_on_cross_subject_failure(client, group_ctx):
    stimulus = await _create_stimulus(client, group_ctx)
    local, _, _, foreign = group_ctx["questions"]
    created = await client.post(
        f"{API}/subjects/{group_ctx['subject'].id}/question-groups",
        json={
            "stimulus_id": stimulus["id"],
            "items": [{"question_id": local.id, "position": 0}],
        },
        headers=_auth(group_ctx["owner"]),
    )
    group = created.json()

    failed = await client.put(
        f"{API}/subjects/{group_ctx['subject'].id}/question-groups/{group['id']}",
        json={
            "expected_revision": group["revision"],
            "items": [{"question_id": foreign.id, "position": 1}],
        },
        headers=_auth(group_ctx["owner"]),
    )
    assert failed.status_code == 422, failed.text

    unchanged = await client.get(
        f"{API}/subjects/{group_ctx['subject'].id}/question-groups/{group['id']}",
        headers=_auth(group_ctx["owner"]),
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["revision"] == 1
    assert unchanged.json()["items"][0]["question_id"] == local.id


async def test_public_group_rejects_private_material_and_question(client, group_ctx):
    private_stimulus = await _create_stimulus(client, group_ctx, visibility="private")
    public_question, _, private_question, _ = group_ctx["questions"]
    base_url = f"{API}/subjects/{group_ctx['subject'].id}/question-groups"

    private_material = await client.post(
        base_url,
        json={
            "stimulus_id": private_stimulus["id"],
            "items": [{"question_id": public_question.id, "position": 0}],
        },
        headers=_auth(group_ctx["owner"]),
    )
    assert private_material.status_code == 422

    public_stimulus = await _create_stimulus(client, group_ctx)
    private_member = await client.post(
        base_url,
        json={
            "stimulus_id": public_stimulus["id"],
            "items": [{"question_id": private_question.id, "position": 0}],
        },
        headers=_auth(group_ctx["owner"]),
    )
    assert private_member.status_code == 422


async def test_group_delete_removes_membership_not_questions(client, db_session, group_ctx):
    stimulus = await _create_stimulus(client, group_ctx)
    question = group_ctx["questions"][0]
    created = await client.post(
        f"{API}/subjects/{group_ctx['subject'].id}/question-groups",
        json={
            "stimulus_id": stimulus["id"],
            "items": [{"question_id": question.id, "position": 0}],
        },
        headers=_auth(group_ctx["owner"]),
    )
    group = created.json()

    deleted = await client.delete(
        f"{API}/subjects/{group_ctx['subject'].id}/question-groups/{group['id']}",
        params={"expected_revision": group["revision"]},
        headers=_auth(group_ctx["owner"]),
    )
    assert deleted.status_code == 204, deleted.text
    assert await db_session.scalar(
        select(func.count()).select_from(QuestionGroupItem).where(
            QuestionGroupItem.group_id == group["id"]
        )
    ) == 0
    persisted = await db_session.get(Question, question.id)
    assert persisted is not None
    assert persisted.deleted_at is None


async def test_database_enforces_item_position_constraints(db_session, group_ctx):
    stimulus = Stimulus(
        subject_id=group_ctx["subject"].id,
        content=json.dumps(doc("约束材料")),
        created_by=group_ctx["owner"].id,
    )
    db_session.add(stimulus)
    await db_session.flush()
    group = QuestionGroup(subject_id=group_ctx["subject"].id, stimulus_id=stimulus.id)
    db_session.add(group)
    await db_session.commit()
    group_id = group.id
    first_id, second_id = [question.id for question in group_ctx["questions"][:2]]
    db_session.add(
        QuestionGroupItem(
            group_id=group_id,
            question_id=first_id,
            position=-1,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    db_session.add_all(
        [
            QuestionGroupItem(group_id=group_id, question_id=first_id, position=0),
            QuestionGroupItem(group_id=group_id, question_id=second_id, position=0),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    db_session.add_all(
        [
            QuestionGroupItem(group_id=group_id, question_id=first_id, position=0),
            QuestionGroupItem(group_id=group_id, question_id=first_id, position=1),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_subject_permissions_and_private_stimulus_access(client, group_ctx):
    denied = await client.post(
        f"{API}/subjects/{group_ctx['subject'].id}/stimuli",
        json={"content": doc("无权创建")},
        headers=_auth(group_ctx["other"]),
    )
    assert denied.status_code == 403

    private_stimulus = await _create_stimulus(client, group_ctx, visibility="private")
    hidden = await client.get(
        f"{API}/subjects/{group_ctx['subject'].id}/stimuli/{private_stimulus['id']}",
        headers=_auth(group_ctx["other"]),
    )
    assert hidden.status_code == 404


async def test_relation_rejects_self_duplicate_and_directed_cycle(db_session, group_ctx):
    source, middle, target = group_ctx["questions"][:3]
    actor = await _load_actor(db_session, group_ctx["owner"].id)
    with pytest.raises(Invalid, match="itself"):
        await create_question_relation(
            db_session,
            source_question_id=source.id,
            target_question_id=source.id,
            actor=actor,
        )
    await create_question_relation(
        db_session,
        source_question_id=source.id,
        target_question_id=middle.id,
        actor=actor,
    )
    with pytest.raises(Conflict, match="already exists"):
        await create_question_relation(
            db_session,
            source_question_id=source.id,
            target_question_id=middle.id,
            actor=actor,
        )
    await create_question_relation(
        db_session,
        source_question_id=middle.id,
        target_question_id=target.id,
        actor=actor,
    )
    with pytest.raises(Invalid, match="cycle"):
        await create_question_relation(
            db_session,
            source_question_id=target.id,
            target_question_id=source.id,
            actor=actor,
        )


async def test_relation_requires_edit_permission_and_private_visibility(db_session, group_ctx):
    source, _, private, foreign = group_ctx["questions"]
    owner = await _load_actor(db_session, group_ctx["owner"].id)
    with pytest.raises(Unprocessable, match="share a subject"):
        await create_question_relation(
            db_session,
            source_question_id=source.id,
            target_question_id=foreign.id,
            actor=owner,
        )

    viewer = await _load_actor(db_session, group_ctx["other"].id)

    with pytest.raises(Forbidden):
        await create_question_relation(
            db_session,
            source_question_id=source.id,
            target_question_id=private.id,
            actor=viewer,
        )

    editor = User(
        username="relation_editor",
        full_name="Relation Editor",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(editor)
    await db_session.flush()
    db_session.add(
        SubjectMember(
            user_id=editor.id,
            subject_id=group_ctx["subject"].id,
            role="editor",
        )
    )
    await db_session.commit()
    editor = await _load_actor(db_session, editor.id)

    with pytest.raises(NotFound, match="Question not found"):
        await create_question_relation(
            db_session,
            source_question_id=source.id,
            target_question_id=private.id,
            actor=editor,
        )


async def test_question_subject_change_checks_target_permission_and_existing_links(
    client, db_session, group_ctx
):
    source, target = group_ctx["questions"][:2]
    actor = await _load_actor(db_session, group_ctx["owner"].id)
    await create_question_relation(
        db_session,
        source_question_id=source.id,
        target_question_id=target.id,
        actor=actor,
    )

    linked = await client.put(
        f"{API}/questions/{source.id}",
        json={"subject_id": group_ctx["other_subject"].id},
        headers=_auth(group_ctx["owner"]),
    )
    assert linked.status_code == 422, linked.text

    grouped_question = Question(
        content=json.dumps(doc("题组独立题"), ensure_ascii=False),
        q_type=QuestionType.FREE_RESPONSE,
        subject_id=group_ctx["subject"].id,
        created_by=group_ctx["owner"].id,
    )
    db_session.add(grouped_question)
    await db_session.commit()
    stimulus = await _create_stimulus(client, group_ctx)
    grouped = await client.post(
        f"{API}/subjects/{group_ctx['subject'].id}/question-groups",
        json={
            "stimulus_id": stimulus["id"],
            "items": [{"question_id": grouped_question.id, "position": 0}],
        },
        headers=_auth(group_ctx["owner"]),
    )
    assert grouped.status_code == 201, grouped.text
    grouped_change = await client.put(
        f"{API}/questions/{grouped_question.id}",
        json={"subject_id": group_ctx["other_subject"].id},
        headers=_auth(group_ctx["owner"]),
    )
    assert grouped_change.status_code == 422, grouped_change.text

    restricted = Subject(name="化学", slug="chemistry-groups")
    standalone = Question(
        content=json.dumps(doc("独立题"), ensure_ascii=False),
        q_type=QuestionType.FREE_RESPONSE,
        subject_id=group_ctx["subject"].id,
        created_by=group_ctx["owner"].id,
    )
    db_session.add_all([restricted, standalone])
    await db_session.commit()
    denied = await client.put(
        f"{API}/questions/{standalone.id}",
        json={"subject_id": restricted.id},
        headers=_auth(group_ctx["owner"]),
    )
    assert denied.status_code == 403, denied.text
    await db_session.refresh(standalone)
    assert standalone.subject_id == group_ctx["subject"].id


async def test_deleted_question_cannot_be_added_to_group(client, db_session, group_ctx):
    stimulus = await _create_stimulus(client, group_ctx)
    question = group_ctx["questions"][0]
    question.deleted_at = datetime.utcnow()
    await db_session.commit()
    response = await client.post(
        f"{API}/subjects/{group_ctx['subject'].id}/question-groups",
        json={
            "stimulus_id": stimulus["id"],
            "items": [{"question_id": question.id, "position": 0}],
        },
        headers=_auth(group_ctx["owner"]),
    )
    assert response.status_code == 422