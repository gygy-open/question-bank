import json
from datetime import datetime

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.capabilities.errors import Conflict, Forbidden, Invalid, NotFound, Unprocessable
from app.core.security import create_access_token
from app.models.question import Question, QuestionType, QuestionVisibility
from app.models.question_relation import QuestionRelation
from app.models.stimulus import Stimulus
from app.models.subject import Subject
from app.models.subject_member import SubjectMember
from app.models.user import User
from app.services.question_relation_service import create_question_relation


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
    admin = User(
        username="group_admin",
        full_name="Group Admin",
        hashed_password="x",
        is_active=True,
        is_superuser=True,
    )
    stranger = User(
        username="group_stranger",
        full_name="Group Stranger",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
    )
    humanities = Subject(name="历史", slug="history")
    science = Subject(name="物理", slug="physics-groups")
    db_session.add_all([owner, other, admin, stranger, humanities, science])
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
        "admin": admin,
        "stranger": stranger,
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


async def _attach(client, ctx, stimulus: dict, question_ids, *, user=None) -> dict:
    response = await client.put(
        f"{API}/subjects/{ctx['subject'].id}/stimuli/{stimulus['id']}/questions",
        json={"expected_revision": stimulus["revision"], "question_ids": list(question_ids)},
        headers=_auth(user or ctx["owner"]),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_stimulus_questions_set_order_detach_and_revision(
    client, db_session, group_ctx
):
    stimulus = await _create_stimulus(client, group_ctx)
    first, second = group_ctx["questions"][:2]

    detail = await _attach(client, group_ctx, stimulus, [second.id, first.id])
    assert [q["id"] for q in detail["questions"]] == [second.id, first.id]
    assert [q["stimulus_position"] for q in detail["questions"]] == [0, 1]
    assert detail["revision"] == stimulus["revision"] + 1
    assert detail["content_revision"] == stimulus["content_revision"]

    stale = await client.put(
        f"{API}/subjects/{group_ctx['subject'].id}/stimuli/{stimulus['id']}/questions",
        json={"expected_revision": stimulus["revision"], "question_ids": [first.id]},
        headers=_auth(group_ctx["owner"]),
    )
    assert stale.status_code == 409, stale.text

    shrunk = await _attach(client, group_ctx, detail, [first.id])
    assert [q["id"] for q in shrunk["questions"]] == [first.id]
    await db_session.refresh(second)
    assert second.stimulus_id is None and second.stimulus_position is None

    fetched = await client.get(
        f"{API}/subjects/{group_ctx['subject'].id}/stimuli/{stimulus['id']}",
        headers=_auth(group_ctx["owner"]),
    )
    assert [q["id"] for q in fetched.json()["questions"]] == [first.id]

    attached = await client.get(
        f"{API}/questions",
        params={"subject_id": group_ctx["subject"].id, "has_stimulus": "true"},
        headers=_auth(group_ctx["owner"]),
    )
    assert [item["id"] for item in attached.json()["items"]] == [first.id]
    assert attached.json()["items"][0]["stimulus_id"] == stimulus["id"]
    by_stimulus = await client.get(
        f"{API}/questions",
        params={"stimulus_id": stimulus["id"]},
        headers=_auth(group_ctx["owner"]),
    )
    assert by_stimulus.json()["total"] == 1


async def test_stimulus_questions_reject_invalid_members_atomically(
    client, db_session, group_ctx
):
    stimulus = await _create_stimulus(client, group_ctx)
    other_stimulus = await _create_stimulus(client, group_ctx)
    local, spare, _, foreign = group_ctx["questions"]
    stimulus = await _attach(client, group_ctx, stimulus, [local.id])
    base = f"{API}/subjects/{group_ctx['subject'].id}/stimuli/{stimulus['id']}/questions"

    cross_subject = await client.put(
        base,
        json={"expected_revision": stimulus["revision"], "question_ids": [local.id, foreign.id]},
        headers=_auth(group_ctx["owner"]),
    )
    assert cross_subject.status_code == 422, cross_subject.text

    await _attach(client, group_ctx, other_stimulus, [spare.id])
    taken = await client.put(
        base,
        json={"expected_revision": stimulus["revision"], "question_ids": [spare.id]},
        headers=_auth(group_ctx["owner"]),
    )
    assert taken.status_code == 422, taken.text
    assert "其他材料" in taken.json()["detail"]

    spare.deleted_at = datetime.utcnow()
    await db_session.commit()
    deleted = await client.put(
        base,
        json={"expected_revision": stimulus["revision"], "question_ids": [spare.id]},
        headers=_auth(group_ctx["owner"]),
    )
    assert deleted.status_code == 404, deleted.text

    await db_session.refresh(local)
    assert (local.stimulus_id, local.stimulus_position) == (stimulus["id"], 0)


async def test_public_question_cannot_sit_under_private_stimulus(client, group_ctx):
    public_question, second, private_question, _ = group_ctx["questions"]
    private_stimulus = await _create_stimulus(client, group_ctx, visibility="private")
    rejected = await client.put(
        f"{API}/subjects/{group_ctx['subject'].id}/stimuli/{private_stimulus['id']}/questions",
        json={
            "expected_revision": private_stimulus["revision"],
            "question_ids": [public_question.id],
        },
        headers=_auth(group_ctx["owner"]),
    )
    assert rejected.status_code == 422, rejected.text

    private_stimulus = await _attach(client, group_ctx, private_stimulus, [private_question.id])
    made_public = await client.put(
        f"{API}/questions/{private_question.id}",
        json={"visibility": "public"},
        headers=_auth(group_ctx["owner"]),
    )
    assert made_public.status_code == 422, made_public.text

    public_stimulus = await _create_stimulus(client, group_ctx)
    public_stimulus = await _attach(client, group_ctx, public_stimulus, [second.id])
    hide = await client.put(
        f"{API}/subjects/{group_ctx['subject'].id}/stimuli/{public_stimulus['id']}",
        json={"expected_revision": public_stimulus["revision"], "visibility": "private"},
        headers=_auth(group_ctx["owner"]),
    )
    assert hide.status_code == 422, hide.text

    made_private = await client.put(
        f"{API}/questions/{second.id}",
        json={"visibility": "private"},
        headers=_auth(group_ctx["owner"]),
    )
    assert made_private.status_code == 200, made_private.text
    assert made_private.json()["visibility"] == "private"


async def test_content_revision_only_tracks_material_body(client, group_ctx):
    stimulus = await _create_stimulus(client, group_ctx)
    base = f"{API}/subjects/{group_ctx['subject'].id}/stimuli/{stimulus['id']}"
    meta = await client.put(
        base,
        json={"expected_revision": stimulus["revision"], "source": "新来源", "status": "published"},
        headers=_auth(group_ctx["owner"]),
    )
    assert meta.status_code == 200, meta.text
    assert meta.json()["revision"] == stimulus["revision"] + 1
    assert meta.json()["content_revision"] == 1

    same_body = await client.put(
        base,
        json={"expected_revision": meta.json()["revision"], "content": doc("阅读材料")},
        headers=_auth(group_ctx["owner"]),
    )
    assert same_body.json()["content_revision"] == 1

    changed = await client.put(
        base,
        json={"expected_revision": same_body.json()["revision"], "content": doc("改写后的材料")},
        headers=_auth(group_ctx["owner"]),
    )
    assert changed.json()["content_revision"] == 2


async def test_stimulus_delete_requires_no_active_questions_and_can_restore(
    client, db_session, group_ctx
):
    stimulus = await _create_stimulus(client, group_ctx)
    question = group_ctx["questions"][0]
    current = await _attach(client, group_ctx, stimulus, [question.id])
    base = f"{API}/subjects/{group_ctx['subject'].id}/stimuli/{stimulus['id']}"

    stale_delete = await client.delete(
        base, params={"expected_revision": stimulus["revision"]}, headers=_auth(group_ctx["owner"])
    )
    assert stale_delete.status_code == 409, stale_delete.text
    blocked = await client.delete(
        base, params={"expected_revision": current["revision"]}, headers=_auth(group_ctx["owner"])
    )
    assert blocked.status_code == 422, blocked.text

    removed = await client.delete(f"{API}/questions/{question.id}", headers=_auth(group_ctx["owner"]))
    assert removed.status_code == 200, removed.text
    refreshed = await client.get(base, headers=_auth(group_ctx["owner"]))
    assert refreshed.json()["questions"] == []
    deleted = await client.delete(
        base,
        params={"expected_revision": refreshed.json()["revision"]},
        headers=_auth(group_ctx["owner"]),
    )
    assert deleted.status_code == 204, deleted.text

    recycle_bin = await client.get(
        f"{API}/subjects/{group_ctx['subject'].id}/stimuli",
        params={"only_deleted": True},
        headers=_auth(group_ctx["owner"]),
    )
    deleted_stimulus = recycle_bin.json()["items"][0]
    assert deleted_stimulus["id"] == stimulus["id"]
    assert deleted_stimulus["deleted_at"] is not None
    denied = await client.post(
        f"{base}/restore",
        json={"expected_revision": deleted_stimulus["revision"]},
        headers=_auth(group_ctx["other"]),
    )
    assert denied.status_code == 403, denied.text
    restored = await client.post(
        f"{base}/restore",
        json={"expected_revision": deleted_stimulus["revision"]},
        headers=_auth(group_ctx["owner"]),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["deleted_at"] is None
    assert restored.json()["revision"] == deleted_stimulus["revision"] + 1


async def test_question_soft_delete_releases_slot_and_restore_appends(
    client, db_session, group_ctx
):
    from app.crud.crud_question import question as crud_question

    stimulus = await _create_stimulus(client, group_ctx)
    first, second = group_ctx["questions"][:2]
    await _attach(client, group_ctx, stimulus, [first.id, second.id])

    removed = await client.delete(f"{API}/questions/{first.id}", headers=_auth(group_ctx["owner"]))
    assert removed.status_code == 200, removed.text
    await db_session.refresh(first)
    assert (first.stimulus_id, first.stimulus_position) == (stimulus["id"], None)

    await crud_question.restore(db_session, id=first.id)
    await db_session.refresh(first)
    assert (first.stimulus_id, first.stimulus_position) == (stimulus["id"], 2)

    await client.delete(f"{API}/questions/{first.id}", headers=_auth(group_ctx["owner"]))
    await client.delete(f"{API}/questions/{second.id}", headers=_auth(group_ctx["owner"]))
    material = await db_session.get(Stimulus, stimulus["id"])
    await db_session.refresh(material)
    material.deleted_at = datetime.utcnow()
    await db_session.commit()
    await crud_question.restore(db_session, id=first.id)
    await db_session.refresh(first)
    assert (first.stimulus_id, first.stimulus_position) == (None, None)


async def test_member_edit_keeps_hidden_private_questions_of_others(
    client, db_session, group_ctx
):
    owner = group_ctx["owner"]
    public_question = group_ctx["questions"][0]
    stimulus = await _create_stimulus(client, group_ctx)
    await _attach(client, group_ctx, stimulus, [public_question.id])

    peer = User(username="peer_editor", full_name="Peer", hashed_password="x", is_active=True)
    db_session.add(peer)
    await db_session.flush()
    db_session.add(SubjectMember(user_id=peer.id, subject_id=group_ctx["subject"].id, role="editor"))
    peer_private = Question(
        content=json.dumps(doc("他人私有小题"), ensure_ascii=False),
        q_type=QuestionType.FREE_RESPONSE,
        subject_id=group_ctx["subject"].id,
        visibility=QuestionVisibility.PRIVATE.value,
        created_by=peer.id,
    )
    db_session.add(peer_private)
    await db_session.commit()
    current = (await client.get(
        f"{API}/subjects/{group_ctx['subject'].id}/stimuli/{stimulus['id']}",
        headers=_auth(peer),
    )).json()
    await _attach(client, group_ctx, current, [public_question.id, peer_private.id], user=peer)

    owner_view = (await client.get(
        f"{API}/subjects/{group_ctx['subject'].id}/stimuli/{stimulus['id']}",
        headers=_auth(owner),
    )).json()
    assert [q["id"] for q in owner_view["questions"]] == [public_question.id]
    await _attach(client, group_ctx, owner_view, [])

    await db_session.refresh(peer_private)
    await db_session.refresh(public_question)
    assert (peer_private.stimulus_id, peer_private.stimulus_position) == (stimulus["id"], 0)
    assert public_question.stimulus_id is None


async def test_question_subject_change_is_blocked_by_its_stimulus(client, group_ctx):
    stimulus = await _create_stimulus(client, group_ctx)
    question = group_ctx["questions"][0]
    await _attach(client, group_ctx, stimulus, [question.id])
    moved = await client.put(
        f"{API}/questions/{question.id}",
        json={"subject_id": group_ctx["other_subject"].id},
        headers=_auth(group_ctx["owner"]),
    )
    assert moved.status_code == 422, moved.text


async def test_database_enforces_stimulus_position_constraints(db_session, group_ctx):
    stimulus = Stimulus(
        subject_id=group_ctx["subject"].id,
        content=json.dumps(doc("约束材料")),
        created_by=group_ctx["owner"].id,
    )
    db_session.add(stimulus)
    await db_session.commit()
    stimulus_id = stimulus.id
    first_id, second_id = [question.id for question in group_ctx["questions"][:2]]

    async def place(question_id: int, position):
        await db_session.execute(
            update(Question)
            .where(Question.id == question_id)
            .values(stimulus_id=stimulus_id, stimulus_position=position)
        )

    with pytest.raises(IntegrityError):
        await place(first_id, -1)
    await db_session.rollback()

    await place(first_id, 0)
    with pytest.raises(IntegrityError):
        await place(second_id, 0)
        await db_session.commit()
    await db_session.rollback()

    await place(first_id, None)
    await place(second_id, None)
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

    stimulus = await _create_stimulus(client, group_ctx)
    viewer_edit = await client.put(
        f"{API}/subjects/{group_ctx['subject'].id}/stimuli/{stimulus['id']}/questions",
        json={"expected_revision": stimulus["revision"], "question_ids": []},
        headers=_auth(group_ctx["other"]),
    )
    assert viewer_edit.status_code == 403


async def test_stimulus_list_filters_paginate_and_count_active_questions(
    client, db_session, group_ctx
):
    owner = group_ctx["owner"]
    other = group_ctx["other"]
    subject = group_ctx["subject"]
    foreign_subject = group_ctx["other_subject"]
    first, second, private_question, _ = group_ctx["questions"]
    older = datetime(2025, 1, 1)
    newer = datetime(2025, 1, 2)
    stimuli = [
        Stimulus(
            subject_id=subject.id,
            content=json.dumps(doc("older searchable passage")),
            source="archive",
            status="published",
            created_by=owner.id,
            updated_at=older,
        ),
        Stimulus(
            subject_id=subject.id,
            content=json.dumps(doc("newer passage")),
            source="searchable source",
            visibility=QuestionVisibility.PRIVATE.value,
            created_by=owner.id,
            updated_at=newer,
        ),
        Stimulus(
            subject_id=subject.id,
            content=json.dumps(doc("hidden passage")),
            visibility=QuestionVisibility.PRIVATE.value,
            created_by=group_ctx["stranger"].id,
        ),
        Stimulus(
            subject_id=subject.id,
            content=json.dumps(doc("deleted passage")),
            created_by=owner.id,
            deleted_at=datetime.utcnow(),
        ),
        Stimulus(
            subject_id=foreign_subject.id,
            content=json.dumps(doc("foreign passage")),
            created_by=owner.id,
        ),
    ]
    db_session.add_all(stimuli)
    await db_session.flush()
    first.stimulus_id, first.stimulus_position = stimuli[0].id, 0
    second.stimulus_id, second.stimulus_position = stimuli[0].id, None
    second.deleted_at = datetime.utcnow()
    private_question.stimulus_id, private_question.stimulus_position = stimuli[1].id, 0
    await db_session.commit()

    stimulus_page = await client.get(
        f"{API}/subjects/{subject.id}/stimuli",
        params={"page": 1, "size": 1},
        headers=_auth(owner),
    )
    assert stimulus_page.status_code == 200, stimulus_page.text
    assert stimulus_page.json()["total"] == 2
    assert stimulus_page.json()["pages"] == 2
    assert stimulus_page.json()["items"][0]["id"] == stimuli[1].id
    assert stimulus_page.json()["items"][0]["question_count"] == 1

    keyword = await client.get(
        f"{API}/subjects/{subject.id}/stimuli",
        params={"keyword": "searchable", "size": 10},
        headers=_auth(owner),
    )
    assert {item["id"] for item in keyword.json()["items"]} == {
        stimuli[0].id,
        stimuli[1].id,
    }

    public_only = await client.get(
        f"{API}/subjects/{subject.id}/stimuli",
        params={"status": "published", "visibility": "public", "size": 10},
        headers=_auth(owner),
    )
    assert [item["id"] for item in public_only.json()["items"]] == [stimuli[0].id]
    assert public_only.json()["items"][0]["question_count"] == 1

    viewer_page = await client.get(
        f"{API}/subjects/{subject.id}/stimuli",
        params={"size": 10},
        headers=_auth(other),
    )
    assert [item["id"] for item in viewer_page.json()["items"]] == [stimuli[0].id]

    admin_page = await client.get(
        f"{API}/subjects/{subject.id}/stimuli",
        params={"size": 10},
        headers=_auth(group_ctx["admin"]),
    )
    assert admin_page.json()["total"] == 3

    denied = await client.get(
        f"{API}/subjects/{subject.id}/stimuli",
        headers=_auth(group_ctx["stranger"]),
    )
    assert denied.status_code == 403
    missing = await client.get(
        f"{API}/subjects/999999/stimuli",
        headers=_auth(group_ctx["admin"]),
    )
    assert missing.status_code == 404


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


async def test_relation_read_returns_visible_one_hop_sources_and_targets(
    client, db_session, group_ctx
):
    source, target, private, _ = group_ctx["questions"]
    actor = await _load_actor(db_session, group_ctx["owner"].id)
    await create_question_relation(
        db_session,
        source_question_id=source.id,
        target_question_id=target.id,
        actor=actor,
    )
    await create_question_relation(
        db_session,
        source_question_id=private.id,
        target_question_id=target.id,
        actor=actor,
    )

    owner_response = await client.get(
        f"{API}/questions/{target.id}/relations",
        headers=_auth(group_ctx["owner"]),
    )
    assert owner_response.status_code == 200, owner_response.text
    owner_body = owner_response.json()
    assert owner_body["question_id"] == target.id
    assert {item["question"]["id"] for item in owner_body["sources"]} == {
        source.id,
        private.id,
    }
    assert owner_body["targets"] == []

    viewer_response = await client.get(
        f"{API}/questions/{target.id}/relations",
        headers=_auth(group_ctx["other"]),
    )
    assert viewer_response.status_code == 200, viewer_response.text
    viewer_body = viewer_response.json()
    assert [item["question"]["id"] for item in viewer_body["sources"]] == [source.id]

    source_response = await client.get(
        f"{API}/questions/{source.id}/relations",
        headers=_auth(group_ctx["other"]),
    )
    assert source_response.status_code == 200, source_response.text
    assert [item["question"]["id"] for item in source_response.json()["targets"]] == [
        target.id
    ]

    question_page = await client.get(
        f"{API}/questions",
        params={"subject_id": group_ctx["subject"].id, "size": 10},
        headers=_auth(group_ctx["other"]),
    )
    assert question_page.status_code == 200, question_page.text
    counts = {
        item["id"]: (item["incoming_relation_count"], item["outgoing_relation_count"])
        for item in question_page.json()["items"]
    }
    assert counts[target.id] == (1, 0)
    assert counts[source.id] == (0, 1)


async def test_relation_api_links_and_unlinks_without_deleting_questions(
    client, db_session, group_ctx
):
    source, target = group_ctx["questions"][:2]
    created = await client.post(
        f"{API}/questions/{source.id}/relations",
        json={"target_question_id": target.id},
        headers=_auth(group_ctx["owner"]),
    )
    assert created.status_code == 201, created.text
    assert created.json()["source_question_id"] == source.id
    assert created.json()["target_question_id"] == target.id

    removed = await client.delete(
        f"{API}/questions/{source.id}/relations/{target.id}",
        headers=_auth(group_ctx["owner"]),
    )
    assert removed.status_code == 204, removed.text
    assert await db_session.get(Question, source.id) is not None
    assert await db_session.get(Question, target.id) is not None
    relation_count = await db_session.scalar(select(func.count(QuestionRelation.id)))
    assert relation_count == 0


async def test_derived_question_api_creates_question_and_relation_atomically(
    client, db_session, group_ctx
):
    source = group_ctx["questions"][0]
    response = await client.post(
        f"{API}/questions/{source.id}/derived-questions",
        json={
            "content": doc("新派生题"),
            "q_type": QuestionType.FREE_RESPONSE.value,
            "subject_id": group_ctx["other_subject"].id,
        },
        headers=_auth(group_ctx["owner"]),
    )
    assert response.status_code == 201, response.text
    derived = response.json()
    assert derived["subject_id"] == source.subject_id
    assert "parent_id" not in derived

    relation = await db_session.scalar(
        select(QuestionRelation).where(
            QuestionRelation.source_question_id == source.id,
            QuestionRelation.target_question_id == derived["id"],
        )
    )
    assert relation is not None


async def test_ordinary_question_writes_reject_legacy_relation_fields(
    client, group_ctx
):
    payload = {
        "content": doc("普通题"),
        "q_type": QuestionType.FREE_RESPONSE.value,
        "subject_id": group_ctx["subject"].id,
    }
    create_with_parent = await client.post(
        f"{API}/questions",
        json={**payload, "parent_id": group_ctx["questions"][0].id},
        headers=_auth(group_ctx["owner"]),
    )
    assert create_with_parent.status_code == 422

    create_with_children = await client.post(
        f"{API}/questions",
        json={**payload, "children": [payload]},
        headers=_auth(group_ctx["owner"]),
    )
    assert create_with_children.status_code == 422

    update_with_parent = await client.put(
        f"{API}/questions/{group_ctx['questions'][0].id}",
        json={"parent_id": None},
        headers=_auth(group_ctx["owner"]),
    )
    assert update_with_parent.status_code == 422


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

