import json
import uuid

import pytest
from sqlalchemy import delete, select

from app.core.security import create_access_token
from app.models.composition import CompositionEvent
from app.models.question import Question, QuestionType, QuestionVisibility
from app.models.question_group import QuestionGroup, QuestionGroupItem, Stimulus
from app.models.subject import Subject
from app.models.user import User


API = "/api/v1"


def _uid() -> str:
    return str(uuid.uuid4())


def _rich_doc(text: str) -> dict:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


async def _seed_group(db_session):
    actor = User(username="group-editor", full_name="Group Editor", hashed_password="x")
    subject = Subject(name="语文", slug="group-chinese")
    db_session.add_all([actor, subject])
    await db_session.flush()

    stimulus = Stimulus(
        subject_id=subject.id,
        content=json.dumps(_rich_doc("材料一"), ensure_ascii=False),
        revision=3,
        created_by=actor.id,
    )
    questions = [
        Question(
            subject_id=subject.id,
            q_type=QuestionType.FREE_RESPONSE,
            content=json.dumps(_rich_doc(text), ensure_ascii=False),
            content_revision=revision,
            created_by=actor.id,
        )
        for text, revision in (("小题一", 2), ("小题二", 4))
    ]
    db_session.add_all([stimulus, *questions])
    await db_session.flush()
    group = QuestionGroup(
        subject_id=subject.id,
        stimulus_id=stimulus.id,
        revision=5,
        created_by=actor.id,
    )
    db_session.add(group)
    await db_session.flush()
    db_session.add_all(
        QuestionGroupItem(group_id=group.id, question_id=question.id, position=position)
        for position, question in enumerate(questions)
    )
    await db_session.commit()
    return actor, subject, group, stimulus, questions


async def _create_composition(client, subject_id: int, headers: dict) -> dict:
    response = await client.post(
        f"{API}/subjects/{subject_id}/compositions?scope=shared",
        json={"title": "题组稿"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _put_group(client, subject_id: int, composition_id: int, headers: dict, group_id: int):
    module_id = _uid()
    response = await client.put(
        f"{API}/subjects/{subject_id}/compositions/{composition_id}/nodes?scope=shared",
        json={
            "expected_revision": 1,
            "nodes": [{
                "id": module_id,
                "node_kind": "module",
                "node_type": "question_group",
                "question_group_id": group_id,
            }],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return module_id, response.json()


async def _sync_groups(
    client, subject_id: int, composition_id: int, headers: dict, *, revision: int, node_ids: list[str]
):
    return await client.post(
        f"{API}/subjects/{subject_id}/compositions/{composition_id}"
        "/question-group-nodes/sync?scope=shared",
        json={"expected_revision": revision, "node_ids": node_ids},
        headers=headers,
    )


def _group_replacement_nodes(module_id: str, group_id: int, nodes: list[dict]) -> list[dict]:
    replacement = [{
        "id": module_id,
        "node_kind": "module",
        "node_type": "question_group",
        "question_group_id": group_id,
    }]
    for child in sorted(
        [node for node in nodes if node["parent_id"] == module_id],
        key=lambda node: node["position"],
    ):
        replacement.append({
            "id": child["id"],
            "parent_id": module_id,
            "slot": "body",
            "node_kind": "block",
            "node_type": child["node_type"],
            "question_id": child.get("question_id"),
            "source_question_node_id": child.get("source_question_node_id"),
            "props": child.get("props"),
        })
    return replacement


@pytest.mark.asyncio
async def test_question_details_collects_group_members_and_uses_group_root_for_before(
    client, db_session, grant_role
):
    actor, subject, group, _stimulus, questions = await _seed_group(db_session)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, frozen = await _put_group(
        client, subject.id, composition["id"], headers, group.id
    )
    group_nodes = _group_replacement_nodes(module_id, group.id, frozen["nodes"])
    member_node_ids = [node["id"] for node in group_nodes if node["node_type"] == "question"]
    root_question_id = _uid()
    details_id = _uid()
    response = await client.put(
        f"{API}/subjects/{subject.id}/compositions/{composition['id']}/nodes?scope=shared",
        json={
            "expected_revision": 2,
            "nodes": [
                *group_nodes,
                {
                    "id": details_id,
                    "node_kind": "module",
                    "node_type": "question_details",
                    "props": {
                        "scope": "before",
                        "fields": {
                            "answer": True,
                            "thinking": False,
                            "analysis": False,
                            "summary": False,
                        },
                    },
                },
                {
                    "id": root_question_id,
                    "node_kind": "block",
                    "node_type": "question",
                    "question_id": questions[0].id,
                },
            ],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    answer_items = sorted(
        [node for node in response.json()["nodes"] if node["parent_id"] == details_id],
        key=lambda node: node["position"],
    )
    assert [node["source_question_node_id"] for node in answer_items] == member_node_ids
    assert root_question_id not in {node["source_question_node_id"] for node in answer_items}


@pytest.mark.asyncio
async def test_finalize_question_group_snapshot_v3_is_preorder_and_frozen(
    client, db_session, grant_role
):
    actor, subject, group, stimulus, questions = await _seed_group(db_session)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, frozen = await _put_group(
        client, subject.id, composition["id"], headers, group.id
    )
    child_ids = [
        node["id"] for node in sorted(
            [node for node in frozen["nodes"] if node["parent_id"] == module_id],
            key=lambda node: node["position"],
        )
    ]
    response = await client.post(
        f"{API}/subjects/{subject.id}/compositions/{composition['id']}/versions?scope=shared",
        json={"expected_revision": 2},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    snapshot = response.json()["snapshot"]
    assert snapshot["schema_version"] == 3
    assert [node["id"] for node in snapshot["nodes"]] == [module_id, *child_ids]
    module = snapshot["nodes"][0]
    assert module["question_group_revision"] == group.revision
    assert module["stimulus_revision"] == stimulus.revision
    assert module["content"] == _rich_doc("材料一")
    assert [node["question_revision"] for node in snapshot["nodes"][1:]] == [2, 4]


@pytest.mark.asyncio
async def test_question_group_revision_status_reports_stale_structure_and_unavailable(
    client, db_session, grant_role
):
    actor, subject, group, stimulus, questions = await _seed_group(db_session)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, frozen = await _put_group(client, subject.id, composition["id"], headers, group.id)
    frozen_questions = [
        node for node in frozen["nodes"] if node["node_type"] == "question"
    ]

    group.revision = 6
    stimulus.revision = 4
    questions[0].content_revision = 3
    await db_session.execute(
        delete(QuestionGroupItem).where(
            QuestionGroupItem.group_id == group.id,
            QuestionGroupItem.question_id == questions[0].id,
        )
    )
    await db_session.commit()

    response = await client.get(
        f"{API}/subjects/{subject.id}/compositions/{composition['id']}"
        "/question-group-revisions?scope=shared",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json() == [{
        "node_id": module_id,
        "question_group_id": group.id,
        "pinned_revision": 5,
        "current_revision": 6,
        "stimulus_pinned_revision": 3,
        "stimulus_current_revision": 4,
        "members": [{
            "node_id": frozen_questions[0]["id"],
            "question_id": questions[0].id,
            "pinned_revision": 2,
            "current_revision": 3,
            "available": True,
        }, {
            "node_id": frozen_questions[1]["id"],
            "question_id": questions[1].id,
            "pinned_revision": 4,
            "current_revision": 4,
            "available": True,
        }],
        "group_available": True,
        "stimulus_available": True,
        "structure_changed": True,
        "stale": True,
    }]

    group.deleted_at = group.updated_at
    await db_session.commit()
    unavailable = await client.get(
        f"{API}/subjects/{subject.id}/compositions/{composition['id']}"
        "/question-group-revisions?scope=shared",
        headers=headers,
    )
    assert unavailable.status_code == 200
    status = unavailable.json()[0]
    assert status["group_available"] is False
    assert status["current_revision"] is None
    assert status["stimulus_current_revision"] is None
    assert all(member["current_revision"] is None for member in status["members"])


@pytest.mark.parametrize("unavailable_kind", ["private", "cross_subject"])
@pytest.mark.asyncio
async def test_question_group_revision_status_hides_inaccessible_sources(
    client, db_session, grant_role, unavailable_kind
):
    actor, subject, group, _stimulus, _questions = await _seed_group(db_session)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    await _put_group(client, subject.id, composition["id"], headers, group.id)
    if unavailable_kind == "private":
        group.visibility = QuestionVisibility.PRIVATE.value
    else:
        other_subject = Subject(name="历史", slug="group-history")
        db_session.add(other_subject)
        await db_session.flush()
        group.subject_id = other_subject.id
    await db_session.commit()

    response = await client.get(
        f"{API}/subjects/{subject.id}/compositions/{composition['id']}"
        "/question-group-revisions?scope=shared",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    status = response.json()[0]
    assert status["group_available"] is False
    assert status["stimulus_available"] is False
    assert status["current_revision"] is None
    assert status["stimulus_current_revision"] is None
    assert all(member["available"] is False for member in status["members"])


@pytest.mark.asyncio
async def test_sync_group_preserves_layout_answer_space_and_handles_structure_changes(
    client, db_session, grant_role
):
    actor, subject, group, stimulus, questions = await _seed_group(db_session)
    third = Question(
        subject_id=subject.id,
        q_type=QuestionType.FREE_RESPONSE,
        content=json.dumps(_rich_doc("小题三"), ensure_ascii=False),
        content_revision=1,
        created_by=actor.id,
    )
    db_session.add(third)
    await db_session.flush()
    db_session.add(QuestionGroupItem(group_id=group.id, question_id=third.id, position=2))
    await db_session.commit()
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, frozen = await _put_group(client, subject.id, composition["id"], headers, group.id)
    old_questions = {
        node["question_id"]: node
        for node in frozen["nodes"]
        if node["node_type"] == "question"
    }
    answer_space_id = _uid()
    replacement_nodes = [{
        "id": module_id,
        "node_kind": "module",
        "node_type": "question_group",
        "question_group_id": group.id,
    }]
    for index, question in enumerate((*questions, third)):
        old_node = old_questions[question.id]
        replacement_nodes.append({
            "id": old_node["id"],
            "parent_id": module_id,
            "slot": "body",
            "node_kind": "block",
            "node_type": "question",
            "question_id": question.id,
            "props": {"score": index + 2},
        })
        if index == 0:
            replacement_nodes.append({
                "id": answer_space_id,
                "parent_id": module_id,
                "slot": "body",
                "node_kind": "block",
                "node_type": "answer_space",
                "source_question_node_id": old_node["id"],
                "props": {"lines": 5, "style": "lined"},
            })
    replaced = await client.put(
        f"{API}/subjects/{subject.id}/compositions/{composition['id']}/nodes?scope=shared",
        json={"expected_revision": 2, "nodes": replacement_nodes},
        headers=headers,
    )
    assert replaced.status_code == 200, replaced.text

    added = Question(
        subject_id=subject.id,
        q_type=QuestionType.FREE_RESPONSE,
        content=json.dumps(_rich_doc("新增小题"), ensure_ascii=False),
        content_revision=7,
        created_by=actor.id,
    )
    db_session.add(added)
    await db_session.flush()
    await db_session.execute(delete(QuestionGroupItem).where(QuestionGroupItem.group_id == group.id))
    await db_session.flush()
    db_session.add_all([
        QuestionGroupItem(group_id=group.id, question_id=third.id, position=0),
        QuestionGroupItem(group_id=group.id, question_id=questions[0].id, position=1),
        QuestionGroupItem(group_id=group.id, question_id=added.id, position=2),
    ])
    group.revision = 6
    stimulus.content = json.dumps(_rich_doc("新材料"), ensure_ascii=False)
    stimulus.revision = 4
    questions[0].content = json.dumps(_rich_doc("更新后小题一"), ensure_ascii=False)
    questions[0].content_revision = 8
    await db_session.commit()

    response = await _sync_groups(
        client, subject.id, composition["id"], headers, revision=3, node_ids=[module_id]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == 4
    module = next(node for node in body["nodes"] if node["id"] == module_id)
    assert module["content"] == _rich_doc("新材料")
    assert module["question_group_revision"] == 6
    assert module["stimulus_revision"] == 4
    children = sorted(
        [node for node in body["nodes"] if node["parent_id"] == module_id],
        key=lambda node: node["position"],
    )
    refreshed_questions = [node for node in children if node["node_type"] == "question"]
    assert [node["question_id"] for node in refreshed_questions] == [
        third.id, questions[0].id, added.id,
    ]
    assert refreshed_questions[0]["id"] == old_questions[third.id]["id"]
    assert refreshed_questions[0]["props"] == {"score": 4}
    assert refreshed_questions[1]["id"] == old_questions[questions[0].id]["id"]
    assert refreshed_questions[1]["props"] == {"score": 2}
    assert refreshed_questions[1]["question_revision"] == 8
    assert refreshed_questions[2]["id"] not in {
        node["id"] for node in old_questions.values()
    }
    assert refreshed_questions[2]["props"] is None
    assert questions[1].id not in {node["question_id"] for node in refreshed_questions}
    answer_space = next(node for node in children if node["node_type"] == "answer_space")
    assert answer_space["id"] == answer_space_id
    assert answer_space["source_question_node_id"] == old_questions[questions[0].id]["id"]
    assert answer_space["props"] == {"lines": 5, "style": "lined"}

    event = await db_session.scalar(
        select(CompositionEvent).where(
            CompositionEvent.composition_id == composition["id"],
            CompositionEvent.event_type == "question_group_nodes_synced",
        )
    )
    assert event is not None
    assert event.composition_revision == 4
    assert event.payload["old_revision"] == 3
    assert event.payload["new_revision"] == 4
    summary = event.payload["groups"][0]
    assert summary["added_question_ids"] == [added.id]
    assert summary["removed_question_ids"] == [questions[1].id]
    assert summary["reordered"] is True


@pytest.mark.asyncio
async def test_sync_groups_is_atomic_conflicts_and_single_sync_rejects_child(
    client, db_session, grant_role
):
    actor, subject, group, stimulus, questions = await _seed_group(db_session)
    second_group = QuestionGroup(
        subject_id=subject.id,
        stimulus_id=stimulus.id,
        revision=2,
        created_by=actor.id,
    )
    db_session.add(second_group)
    await db_session.flush()
    db_session.add(
        QuestionGroupItem(group_id=second_group.id, question_id=questions[0].id, position=0)
    )
    await db_session.commit()
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_ids = [_uid(), _uid()]
    put = await client.put(
        f"{API}/subjects/{subject.id}/compositions/{composition['id']}/nodes?scope=shared",
        json={
            "expected_revision": 1,
            "nodes": [{
                "id": module_id,
                "node_kind": "module",
                "node_type": "question_group",
                "question_group_id": group_id,
            } for module_id, group_id in zip(module_ids, (group.id, second_group.id))],
        },
        headers=headers,
    )
    assert put.status_code == 200, put.text
    first_child = next(
        node for node in put.json()["nodes"]
        if node["parent_id"] == module_ids[0] and node["node_type"] == "question"
    )
    questions[0].content_revision = 9
    second_group.deleted_at = second_group.updated_at
    await db_session.commit()

    rejected = await _sync_groups(
        client,
        subject.id,
        composition["id"],
        headers,
        revision=2,
        node_ids=module_ids,
    )
    assert rejected.status_code == 422, rejected.text
    detail = await client.get(
        f"{API}/subjects/{subject.id}/compositions/{composition['id']}?scope=shared",
        headers=headers,
    )
    assert detail.json()["revision"] == 2
    unchanged = next(node for node in detail.json()["nodes"] if node["id"] == first_child["id"])
    assert unchanged["question_revision"] == first_child["question_revision"]

    conflict = await _sync_groups(
        client,
        subject.id,
        composition["id"],
        headers,
        revision=1,
        node_ids=[module_ids[0]],
    )
    assert conflict.status_code == 409, conflict.text

    single = await client.post(
        f"{API}/subjects/{subject.id}/compositions/{composition['id']}"
        "/question-nodes/sync?scope=shared",
        json={"expected_revision": 2, "node_ids": [first_child["id"]]},
        headers=headers,
    )
    assert single.status_code == 422, single.text


@pytest.mark.asyncio
async def test_sync_multiple_groups_bumps_composition_revision_once(
    client, db_session, grant_role
):
    actor, subject, group, stimulus, questions = await _seed_group(db_session)
    second_group = QuestionGroup(
        subject_id=subject.id,
        stimulus_id=stimulus.id,
        revision=2,
        created_by=actor.id,
    )
    db_session.add(second_group)
    await db_session.flush()
    db_session.add(
        QuestionGroupItem(group_id=second_group.id, question_id=questions[0].id, position=0)
    )
    await db_session.commit()
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_ids = [_uid(), _uid()]
    put = await client.put(
        f"{API}/subjects/{subject.id}/compositions/{composition['id']}/nodes?scope=shared",
        json={
            "expected_revision": 1,
            "nodes": [{
                "id": module_id,
                "node_kind": "module",
                "node_type": "question_group",
                "question_group_id": group_id,
            } for module_id, group_id in zip(module_ids, (group.id, second_group.id))],
        },
        headers=headers,
    )
    assert put.status_code == 200, put.text
    group.revision = 6
    second_group.revision = 3
    await db_session.commit()

    response = await _sync_groups(
        client,
        subject.id,
        composition["id"],
        headers,
        revision=2,
        node_ids=module_ids,
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 3
    modules = {
        node["id"]: node
        for node in response.json()["nodes"]
        if node["node_type"] == "question_group"
    }
    assert modules[module_ids[0]]["question_group_revision"] == 6
    assert modules[module_ids[1]]["question_group_revision"] == 3


async def _put_group_with_custom_blocks(client, subject, composition, headers, group, questions):
    """在题组内插入一个导语块和一个锚定到第二小题的说明块。"""
    module_id, frozen = await _put_group(client, subject.id, composition["id"], headers, group.id)
    question_nodes = {
        node["question_id"]: node["id"]
        for node in frozen["nodes"]
        if node["node_type"] == "question"
    }
    lead_id, mid_id, space_id = _uid(), _uid(), _uid()
    response = await client.put(
        f"{API}/subjects/{subject.id}/compositions/{composition['id']}/nodes?scope=shared",
        json={
            "expected_revision": 2,
            "nodes": [
                {
                    "id": module_id,
                    "node_kind": "module",
                    "node_type": "question_group",
                    "question_group_id": group.id,
                },
                {
                    "id": lead_id,
                    "parent_id": module_id,
                    "slot": "body",
                    "node_kind": "block",
                    "node_type": "rich_text",
                    "content": _rich_doc("阅读下面的文字，完成1～2题。"),
                },
                {
                    "id": question_nodes[questions[0].id],
                    "parent_id": module_id,
                    "slot": "body",
                    "node_kind": "block",
                    "node_type": "question",
                    "question_id": questions[0].id,
                },
                {
                    "id": space_id,
                    "parent_id": module_id,
                    "slot": "body",
                    "node_kind": "block",
                    "node_type": "answer_space",
                    "source_question_node_id": question_nodes[questions[0].id],
                    "props": {"lines": 5, "style": "lined"},
                },
                {
                    "id": question_nodes[questions[1].id],
                    "parent_id": module_id,
                    "slot": "body",
                    "node_kind": "block",
                    "node_type": "question",
                    "question_id": questions[1].id,
                },
                # 故意放在末尾:规范化应把它移到锚点小题之前。
                {
                    "id": mid_id,
                    "parent_id": module_id,
                    "slot": "body",
                    "node_kind": "block",
                    "node_type": "rich_text",
                    "content": _rich_doc("请结合上述材料作答。"),
                    "anchor_before_node_id": question_nodes[questions[1].id],
                },
            ],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return module_id, question_nodes, lead_id, mid_id, space_id, response.json()


def _ordered_children(nodes: list[dict], module_id: str) -> list[dict]:
    return sorted(
        [node for node in nodes if node["parent_id"] == module_id],
        key=lambda node: node["position"],
    )


@pytest.mark.asyncio
async def test_question_group_accepts_custom_blocks_and_normalizes_order(
    client, db_session, grant_role
):
    actor, subject, group, _stimulus, questions = await _seed_group(db_session)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, question_nodes, lead_id, mid_id, space_id, body = (
        await _put_group_with_custom_blocks(
            client, subject, composition, headers, group, questions
        )
    )
    children = _ordered_children(body["nodes"], module_id)
    assert [node["id"] for node in children] == [
        lead_id,
        question_nodes[questions[0].id],
        space_id,
        mid_id,
        question_nodes[questions[1].id],
    ]
    assert children[0]["anchor_before_node_id"] is None
    assert children[3]["anchor_before_node_id"] == question_nodes[questions[1].id]


@pytest.mark.asyncio
async def test_sync_group_preserves_custom_blocks_and_reanchors_removed_target(
    client, db_session, grant_role
):
    actor, subject, group, stimulus, questions = await _seed_group(db_session)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, question_nodes, lead_id, mid_id, _space_id, _body = (
        await _put_group_with_custom_blocks(
            client, subject, composition, headers, group, questions
        )
    )

    # 把锚点小题(第二题)移出题组,并让材料过期。
    await db_session.execute(
        delete(QuestionGroupItem).where(
            QuestionGroupItem.group_id == group.id,
            QuestionGroupItem.question_id == questions[1].id,
        )
    )
    group.revision = 6
    stimulus.content = json.dumps(_rich_doc("新材料"), ensure_ascii=False)
    stimulus.revision = 4
    await db_session.commit()

    response = await _sync_groups(
        client, subject.id, composition["id"], headers, revision=3, node_ids=[module_id]
    )
    assert response.status_code == 200, response.text
    children = _ordered_children(response.json()["nodes"], module_id)
    by_id = {node["id"]: node for node in children}

    # 用户插入的两个说明块都不能被刷新吞掉。
    assert lead_id in by_id
    assert mid_id in by_id
    assert by_id[lead_id]["content"] == _rich_doc("阅读下面的文字，完成1～2题。")
    # 导语仍在材料之后、首题之前;锚点失效的说明块顺延到末尾。
    assert children[0]["id"] == lead_id
    assert by_id[mid_id]["anchor_before_node_id"] is None
    assert children[-1]["id"] == mid_id
    assert [node["question_id"] for node in children if node["node_type"] == "question"] == [
        questions[0].id
    ]


@pytest.mark.asyncio
async def test_sync_group_reanchors_custom_block_to_next_surviving_question(
    client, db_session, grant_role
):
    actor, subject, group, _stimulus, questions = await _seed_group(db_session)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, question_nodes, _lead_id, mid_id, _space_id, _body = (
        await _put_group_with_custom_blocks(
            client, subject, composition, headers, group, questions
        )
    )
    # 新增第三题排在末尾,再移除锚点小题(第二题):说明块应顺延锚定到第三题。
    third = Question(
        subject_id=subject.id,
        q_type=QuestionType.FREE_RESPONSE,
        content=json.dumps(_rich_doc("小题三"), ensure_ascii=False),
        content_revision=1,
        created_by=actor.id,
    )
    db_session.add(third)
    await db_session.flush()
    db_session.add(QuestionGroupItem(group_id=group.id, question_id=third.id, position=2))
    await db_session.commit()
    first_sync = await _sync_groups(
        client, subject.id, composition["id"], headers, revision=3, node_ids=[module_id]
    )
    assert first_sync.status_code == 200, first_sync.text

    await db_session.execute(
        delete(QuestionGroupItem).where(
            QuestionGroupItem.group_id == group.id,
            QuestionGroupItem.question_id == questions[1].id,
        )
    )
    group.revision = 7
    await db_session.commit()
    response = await _sync_groups(
        client, subject.id, composition["id"], headers, revision=4, node_ids=[module_id]
    )
    assert response.status_code == 200, response.text
    children = _ordered_children(response.json()["nodes"], module_id)
    third_node_id = next(
        node["id"] for node in children if node.get("question_id") == third.id
    )
    by_id = {node["id"]: node for node in children}
    assert by_id[mid_id]["anchor_before_node_id"] == third_node_id
    ids = [node["id"] for node in children]
    assert ids.index(mid_id) == ids.index(third_node_id) - 1


@pytest.mark.asyncio
async def test_question_group_rejects_unsupported_child_and_foreign_anchor(
    client, db_session, grant_role
):
    actor, subject, group, _stimulus, questions = await _seed_group(db_session)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, frozen = await _put_group(client, subject.id, composition["id"], headers, group.id)
    base = _group_replacement_nodes(module_id, group.id, frozen["nodes"])

    page_break = await client.put(
        f"{API}/subjects/{subject.id}/compositions/{composition['id']}/nodes?scope=shared",
        json={
            "expected_revision": 2,
            "nodes": [
                *base,
                {
                    "id": _uid(),
                    "parent_id": module_id,
                    "slot": "body",
                    "node_kind": "block",
                    "node_type": "page_break",
                },
            ],
        },
        headers=headers,
    )
    # page_break 在 schema 层就被拦下(必须是 root 节点),不会走到服务层白名单。
    assert page_break.status_code == 422, page_break.text

    foreign_anchor = await client.put(
        f"{API}/subjects/{subject.id}/compositions/{composition['id']}/nodes?scope=shared",
        json={
            "expected_revision": 2,
            "nodes": [
                *base,
                {
                    "id": _uid(),
                    "parent_id": module_id,
                    "slot": "body",
                    "node_kind": "block",
                    "node_type": "rich_text",
                    "content": _rich_doc("说明"),
                    "anchor_before_node_id": _uid(),
                },
            ],
        },
        headers=headers,
    )
    assert foreign_anchor.status_code == 400, foreign_anchor.text