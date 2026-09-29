import json
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.composition import CompositionEvent
from app.models.question import Question, QuestionType, QuestionVisibility
from app.models.stimulus import Stimulus
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


def _question(subject_id: int, actor_id: int, text: str, revision: int = 1, **kwargs) -> Question:
    return Question(
        subject_id=subject_id,
        q_type=QuestionType.FREE_RESPONSE,
        content=json.dumps(_rich_doc(text), ensure_ascii=False),
        content_revision=revision,
        created_by=actor_id,
        **kwargs,
    )


async def _seed_group(db_session, *, extra: int = 0):
    actor = User(username="group-editor", full_name="Group Editor", hashed_password="x")
    subject = Subject(name="语文", slug="group-chinese")
    db_session.add_all([actor, subject])
    await db_session.flush()

    stimulus = Stimulus(
        subject_id=subject.id,
        content=json.dumps(_rich_doc("材料一"), ensure_ascii=False),
        revision=9,
        content_revision=3,
        created_by=actor.id,
    )
    db_session.add(stimulus)
    await db_session.flush()
    specs = [("小题一", 2), ("小题二", 4)] + [(f"小题{3 + i}", 1) for i in range(extra)]
    questions = [
        _question(
            subject.id, actor.id, text, revision,
            stimulus_id=stimulus.id, stimulus_position=position,
        )
        for position, (text, revision) in enumerate(specs)
    ]
    db_session.add_all(questions)
    await db_session.commit()
    return actor, subject, stimulus, questions


async def _create_composition(client, subject_id: int, headers: dict) -> dict:
    response = await client.post(
        f"{API}/subjects/{subject_id}/compositions?scope=shared",
        json={"title": "材料题稿"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _module(module_id: str, stimulus_id: int) -> dict:
    return {
        "id": module_id,
        "node_kind": "module",
        "node_type": "question_group",
        "stimulus_id": stimulus_id,
    }


def _child(module_id: str, question_id: int, node_id=None, **extra) -> dict:
    return {
        "id": node_id or _uid(),
        "parent_id": module_id,
        "slot": "body",
        "node_kind": "block",
        "node_type": "question",
        "question_id": question_id,
        **extra,
    }


async def _put_nodes(client, subject_id, composition_id, headers, *, revision, nodes):
    return await client.put(
        f"{API}/subjects/{subject_id}/compositions/{composition_id}/nodes?scope=shared",
        json={"expected_revision": revision, "nodes": nodes},
        headers=headers,
    )


async def _put_group(client, subject_id, composition_id, headers, stimulus_id, question_ids):
    module_id = _uid()
    response = await _put_nodes(
        client, subject_id, composition_id, headers,
        revision=1,
        nodes=[_module(module_id, stimulus_id), *[_child(module_id, qid) for qid in question_ids]],
    )
    assert response.status_code == 200, response.text
    return module_id, response.json()


async def _sync_groups(client, subject_id, composition_id, headers, *, revision, node_ids):
    return await client.post(
        f"{API}/subjects/{subject_id}/compositions/{composition_id}"
        "/question-group-nodes/sync?scope=shared",
        json={"expected_revision": revision, "node_ids": node_ids},
        headers=headers,
    )


async def _group_status(client, subject_id, composition_id, headers):
    response = await client.get(
        f"{API}/subjects/{subject_id}/compositions/{composition_id}"
        "/question-group-revisions?scope=shared",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _ordered_children(nodes: list[dict], module_id: str) -> list[dict]:
    return sorted(
        [node for node in nodes if node["parent_id"] == module_id],
        key=lambda node: node["position"],
    )


def _group_replacement_nodes(module_id: str, stimulus_id: int, nodes: list[dict]) -> list[dict]:
    replacement = [_module(module_id, stimulus_id)]
    for child in _ordered_children(nodes, module_id):
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
    actor, subject, stimulus, questions = await _seed_group(db_session)
    standalone = _question(subject.id, actor.id, "独立题")
    db_session.add(standalone)
    await db_session.commit()
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, frozen = await _put_group(
        client, subject.id, composition["id"], headers, stimulus.id, [q.id for q in questions]
    )
    group_nodes = _group_replacement_nodes(module_id, stimulus.id, frozen["nodes"])
    member_node_ids = [node["id"] for node in group_nodes if node["node_type"] == "question"]
    root_question_id = _uid()
    details_id = _uid()
    response = await _put_nodes(
        client, subject.id, composition["id"], headers,
        revision=2,
        nodes=[
            *group_nodes,
            {
                "id": details_id,
                "node_kind": "module",
                "node_type": "question_details",
                "props": {
                    "scope": "before",
                    "fields": {
                        "answer": True, "thinking": False, "analysis": False, "summary": False,
                    },
                },
            },
            {
                "id": root_question_id,
                "node_kind": "block",
                "node_type": "question",
                "question_id": standalone.id,
            },
        ],
    )
    assert response.status_code == 200, response.text
    answer_items = _ordered_children(response.json()["nodes"], details_id)
    assert [node["source_question_node_id"] for node in answer_items] == member_node_ids
    assert root_question_id not in {node["source_question_node_id"] for node in answer_items}


@pytest.mark.asyncio
async def test_finalize_question_group_snapshot_v3_is_preorder_and_frozen(
    client, db_session, grant_role
):
    actor, subject, stimulus, questions = await _seed_group(db_session)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, frozen = await _put_group(
        client, subject.id, composition["id"], headers, stimulus.id, [q.id for q in questions]
    )
    child_ids = [node["id"] for node in _ordered_children(frozen["nodes"], module_id)]
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
    assert "question_group_id" not in module
    assert (module["stimulus_id"], module["stimulus_revision"]) == (stimulus.id, 3)
    assert module["content"] == _rich_doc("材料一")
    assert [node["question_revision"] for node in snapshot["nodes"][1:]] == [2, 4]


@pytest.mark.asyncio
async def test_revision_status_reports_content_detach_new_questions_and_reorder(
    client, db_session, grant_role
):
    actor, subject, stimulus, questions = await _seed_group(db_session)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, frozen = await _put_group(
        client, subject.id, composition["id"], headers, stimulus.id, [q.id for q in questions]
    )
    frozen_questions = [n for n in _ordered_children(frozen["nodes"], module_id)]

    [fresh] = await _group_status(client, subject.id, composition["id"], headers)
    assert fresh["stale"] is False
    assert fresh["new_question_ids"] == []

    stimulus.status = "published"
    stimulus.revision = 10
    await db_session.commit()
    [meta_only] = await _group_status(client, subject.id, composition["id"], headers)
    assert meta_only["stale"] is False

    stimulus.content_revision = 4
    questions[1].content_revision = 5
    questions[0].stimulus_id = None
    questions[0].stimulus_position = None
    added = _question(
        subject.id, actor.id, "新增小题", stimulus_id=stimulus.id, stimulus_position=2
    )
    db_session.add(added)
    await db_session.commit()

    assert await _group_status(client, subject.id, composition["id"], headers) == [{
        "node_id": module_id,
        "stimulus_id": stimulus.id,
        "stimulus_pinned_revision": 3,
        "stimulus_current_revision": 4,
        "stimulus_available": True,
        "members": [{
            "node_id": frozen_questions[0]["id"],
            "question_id": questions[0].id,
            "pinned_revision": 2,
            "current_revision": None,
            "available": False,
        }, {
            "node_id": frozen_questions[1]["id"],
            "question_id": questions[1].id,
            "pinned_revision": 4,
            "current_revision": 5,
            "available": True,
        }],
        "new_question_ids": [added.id],
        "structure_changed": False,
        "stale": True,
    }]

    questions[0].stimulus_id = stimulus.id
    questions[0].stimulus_position = 3
    await db_session.commit()
    [reordered] = await _group_status(client, subject.id, composition["id"], headers)
    assert reordered["structure_changed"] is True

    stimulus.deleted_at = datetime.utcnow()
    await db_session.commit()
    [gone] = await _group_status(client, subject.id, composition["id"], headers)
    assert gone["stimulus_available"] is False
    assert gone["stimulus_current_revision"] is None
    assert gone["new_question_ids"] == []
    assert all(member["available"] is False for member in gone["members"])


@pytest.mark.parametrize("unavailable_kind", ["private", "cross_subject"])
@pytest.mark.asyncio
async def test_revision_status_hides_inaccessible_stimulus(
    client, db_session, grant_role, unavailable_kind
):
    actor, subject, stimulus, questions = await _seed_group(db_session)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    await _put_group(
        client, subject.id, composition["id"], headers, stimulus.id, [q.id for q in questions]
    )
    if unavailable_kind == "private":
        stimulus.visibility = QuestionVisibility.PRIVATE.value
    else:
        other_subject = Subject(name="历史", slug="group-history")
        db_session.add(other_subject)
        await db_session.flush()
        stimulus.subject_id = other_subject.id
    await db_session.commit()

    [status] = await _group_status(client, subject.id, composition["id"], headers)
    assert status["stimulus_available"] is False
    assert status["stimulus_current_revision"] is None
    assert status["stale"] is True
    assert all(member["available"] is False for member in status["members"])


@pytest.mark.asyncio
async def test_sync_group_preserves_layout_drops_detached_and_follows_material_order(
    client, db_session, grant_role
):
    actor, subject, stimulus, questions = await _seed_group(db_session, extra=1)
    first, second, third = questions
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, frozen = await _put_group(
        client, subject.id, composition["id"], headers, stimulus.id, [q.id for q in questions]
    )
    old_nodes = {
        node["question_id"]: node for node in frozen["nodes"] if node["node_type"] == "question"
    }
    answer_space_id = _uid()
    replacement = [_module(module_id, stimulus.id)]
    for index, question in enumerate(questions):
        replacement.append(
            _child(module_id, question.id, old_nodes[question.id]["id"], props={"score": index + 2})
        )
        if index == 0:
            replacement.append({
                "id": answer_space_id,
                "parent_id": module_id,
                "slot": "body",
                "node_kind": "block",
                "node_type": "answer_space",
                "source_question_node_id": old_nodes[question.id]["id"],
                "props": {"lines": 5, "style": "lined"},
            })
    replaced = await _put_nodes(
        client, subject.id, composition["id"], headers, revision=2, nodes=replacement
    )
    assert replaced.status_code == 200, replaced.text

    added = _question(subject.id, actor.id, "新增小题", 7, stimulus_id=stimulus.id)
    second.stimulus_id = None
    second.stimulus_position = None
    first.stimulus_position = None
    await db_session.flush()
    third.stimulus_position = 0
    first.stimulus_position = 1
    added.stimulus_position = 2
    db_session.add(added)
    stimulus.content = json.dumps(_rich_doc("新材料"), ensure_ascii=False)
    stimulus.content_revision = 4
    first.content = json.dumps(_rich_doc("更新后小题一"), ensure_ascii=False)
    first.content_revision = 8
    await db_session.commit()

    response = await _sync_groups(
        client, subject.id, composition["id"], headers, revision=3, node_ids=[module_id]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == 4
    module = next(node for node in body["nodes"] if node["id"] == module_id)
    assert module["content"] == _rich_doc("新材料")
    assert module["stimulus_revision"] == 4
    children = _ordered_children(body["nodes"], module_id)
    refreshed = [node for node in children if node["node_type"] == "question"]
    assert [node["question_id"] for node in refreshed] == [third.id, first.id]
    assert refreshed[0]["id"] == old_nodes[third.id]["id"]
    assert refreshed[0]["props"] == {"score": 4}
    assert refreshed[1]["id"] == old_nodes[first.id]["id"]
    assert refreshed[1]["props"] == {"score": 2}
    assert refreshed[1]["question_revision"] == 8
    answer_space = next(node for node in children if node["node_type"] == "answer_space")
    assert answer_space["id"] == answer_space_id
    assert answer_space["source_question_node_id"] == old_nodes[first.id]["id"]
    assert answer_space["props"] == {"lines": 5, "style": "lined"}

    event = await db_session.scalar(
        select(CompositionEvent).where(
            CompositionEvent.composition_id == composition["id"],
            CompositionEvent.event_type == "question_group_nodes_synced",
        )
    )
    assert event is not None
    assert event.composition_revision == 4
    summary = event.payload["groups"][0]
    assert summary["removed_question_ids"] == [second.id]
    assert summary["reordered"] is True
    assert (summary["old_stimulus_revision"], summary["new_stimulus_revision"]) == (3, 4)

    [status] = await _group_status(client, subject.id, composition["id"], headers)
    assert status["stale"] is False
    assert status["new_question_ids"] == [added.id]


@pytest.mark.asyncio
async def test_sync_groups_is_atomic_conflicts_and_single_sync_rejects_child(
    client, db_session, grant_role
):
    actor, subject, stimulus, questions = await _seed_group(db_session)
    other = Stimulus(
        subject_id=subject.id,
        content=json.dumps(_rich_doc("材料二"), ensure_ascii=False),
        created_by=actor.id,
    )
    db_session.add(other)
    await db_session.flush()
    other_question = _question(
        subject.id, actor.id, "材料二小题", stimulus_id=other.id, stimulus_position=0
    )
    db_session.add(other_question)
    await db_session.commit()
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_ids = [_uid(), _uid()]
    put = await _put_nodes(
        client, subject.id, composition["id"], headers,
        revision=1,
        nodes=[
            _module(module_ids[0], stimulus.id),
            _child(module_ids[0], questions[0].id),
            _module(module_ids[1], other.id),
            _child(module_ids[1], other_question.id),
        ],
    )
    assert put.status_code == 200, put.text
    first_child = next(
        node for node in put.json()["nodes"]
        if node["parent_id"] == module_ids[0] and node["node_type"] == "question"
    )
    questions[0].content_revision = 9
    other.deleted_at = datetime.utcnow()
    await db_session.commit()

    rejected = await _sync_groups(
        client, subject.id, composition["id"], headers, revision=2, node_ids=module_ids
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
        client, subject.id, composition["id"], headers, revision=1, node_ids=[module_ids[0]]
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
async def test_sync_rejects_group_whose_questions_all_left_the_material(
    client, db_session, grant_role
):
    actor, subject, stimulus, questions = await _seed_group(db_session)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, _ = await _put_group(
        client, subject.id, composition["id"], headers, stimulus.id, [questions[0].id]
    )
    questions[0].stimulus_id = None
    questions[0].stimulus_position = None
    await db_session.commit()
    response = await _sync_groups(
        client, subject.id, composition["id"], headers, revision=2, node_ids=[module_id]
    )
    assert response.status_code == 422, response.text
    assert "remove it instead" in response.json()["detail"]


@pytest.mark.asyncio
async def test_sync_multiple_groups_bumps_composition_revision_once(
    client, db_session, grant_role
):
    actor, subject, stimulus, questions = await _seed_group(db_session)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_ids = [_uid(), _uid()]
    put = await _put_nodes(
        client, subject.id, composition["id"], headers,
        revision=1,
        nodes=[
            _module(module_ids[0], stimulus.id),
            _child(module_ids[0], questions[0].id),
            _module(module_ids[1], stimulus.id),
            _child(module_ids[1], questions[1].id),
        ],
    )
    assert put.status_code == 200, put.text
    stimulus.content_revision = 6
    await db_session.commit()

    response = await _sync_groups(
        client, subject.id, composition["id"], headers, revision=2, node_ids=module_ids
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 3
    modules = {
        node["id"]: node
        for node in response.json()["nodes"]
        if node["node_type"] == "question_group"
    }
    assert modules[module_ids[0]]["stimulus_revision"] == 6
    assert modules[module_ids[1]]["stimulus_revision"] == 6


@pytest.mark.asyncio
async def test_root_question_sync_rejects_question_that_joined_a_material(
    client, db_session, grant_role
):
    actor, subject, stimulus, _questions = await _seed_group(db_session)
    standalone = _question(subject.id, actor.id, "后来归入材料的题")
    db_session.add(standalone)
    await db_session.commit()
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    node_id = _uid()
    put = await _put_nodes(
        client, subject.id, composition["id"], headers,
        revision=1,
        nodes=[{
            "id": node_id,
            "node_kind": "block",
            "node_type": "question",
            "question_id": standalone.id,
        }],
    )
    assert put.status_code == 200, put.text
    standalone.stimulus_id = stimulus.id
    standalone.stimulus_position = 5
    await db_session.commit()

    response = await client.post(
        f"{API}/subjects/{subject.id}/compositions/{composition['id']}"
        "/question-nodes/sync?scope=shared",
        json={"expected_revision": 2, "node_ids": [node_id]},
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert "question_group" in response.json()["detail"]


async def _put_group_with_custom_blocks(client, subject, composition, headers, stimulus, questions):
    """在材料题内插入一个导语块和一个锚定到第二小题的说明块。"""
    module_id, frozen = await _put_group(
        client, subject.id, composition["id"], headers, stimulus.id, [q.id for q in questions]
    )
    question_nodes = {
        node["question_id"]: node["id"]
        for node in frozen["nodes"]
        if node["node_type"] == "question"
    }
    lead_id, mid_id, space_id = _uid(), _uid(), _uid()
    nodes = [
        _module(module_id, stimulus.id),
        {
            "id": lead_id,
            "parent_id": module_id,
            "slot": "body",
            "node_kind": "block",
            "node_type": "rich_text",
            "content": _rich_doc("阅读下面的文字，完成1～2题。"),
        },
        _child(module_id, questions[0].id, question_nodes[questions[0].id]),
        {
            "id": space_id,
            "parent_id": module_id,
            "slot": "body",
            "node_kind": "block",
            "node_type": "answer_space",
            "source_question_node_id": question_nodes[questions[0].id],
            "props": {"lines": 5, "style": "lined"},
        },
        *[_child(module_id, q.id, question_nodes[q.id]) for q in questions[1:]],
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
    ]
    response = await _put_nodes(
        client, subject.id, composition["id"], headers, revision=2, nodes=nodes
    )
    assert response.status_code == 200, response.text
    return module_id, question_nodes, lead_id, mid_id, space_id, response.json()


@pytest.mark.asyncio
async def test_question_group_accepts_custom_blocks_and_normalizes_order(
    client, db_session, grant_role
):
    actor, subject, stimulus, questions = await _seed_group(db_session)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, question_nodes, lead_id, mid_id, space_id, body = (
        await _put_group_with_custom_blocks(
            client, subject, composition, headers, stimulus, questions
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
    actor, subject, stimulus, questions = await _seed_group(db_session)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, _question_nodes, lead_id, mid_id, _space_id, _body = (
        await _put_group_with_custom_blocks(
            client, subject, composition, headers, stimulus, questions
        )
    )

    # 锚点小题(第二题)脱离材料,并让材料正文过期。
    questions[1].stimulus_id = None
    questions[1].stimulus_position = None
    stimulus.content = json.dumps(_rich_doc("新材料"), ensure_ascii=False)
    stimulus.content_revision = 4
    await db_session.commit()

    response = await _sync_groups(
        client, subject.id, composition["id"], headers, revision=3, node_ids=[module_id]
    )
    assert response.status_code == 200, response.text
    children = _ordered_children(response.json()["nodes"], module_id)
    by_id = {node["id"]: node for node in children}

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
    actor, subject, stimulus, questions = await _seed_group(db_session, extra=1)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, _question_nodes, _lead_id, mid_id, _space_id, _body = (
        await _put_group_with_custom_blocks(
            client, subject, composition, headers, stimulus, questions
        )
    )
    # 移除锚点小题(第二题):说明块应顺延锚定到第三题。
    questions[1].stimulus_id = None
    questions[1].stimulus_position = None
    await db_session.commit()
    response = await _sync_groups(
        client, subject.id, composition["id"], headers, revision=3, node_ids=[module_id]
    )
    assert response.status_code == 200, response.text
    children = _ordered_children(response.json()["nodes"], module_id)
    third_node_id = next(
        node["id"] for node in children if node.get("question_id") == questions[2].id
    )
    by_id = {node["id"]: node for node in children}
    assert by_id[mid_id]["anchor_before_node_id"] == third_node_id
    ids = [node["id"] for node in children]
    assert ids.index(mid_id) == ids.index(third_node_id) - 1


@pytest.mark.asyncio
async def test_question_group_rejects_unsupported_child_and_foreign_anchor(
    client, db_session, grant_role
):
    actor, subject, stimulus, questions = await _seed_group(db_session)
    await grant_role(actor, subject)
    headers = _auth(actor)
    composition = await _create_composition(client, subject.id, headers)
    module_id, frozen = await _put_group(
        client, subject.id, composition["id"], headers, stimulus.id, [q.id for q in questions]
    )
    base = _group_replacement_nodes(module_id, stimulus.id, frozen["nodes"])

    page_break = await _put_nodes(
        client, subject.id, composition["id"], headers,
        revision=2,
        nodes=[
            *base,
            {
                "id": _uid(),
                "parent_id": module_id,
                "slot": "body",
                "node_kind": "block",
                "node_type": "page_break",
            },
        ],
    )
    # page_break 在 schema 层就被拦下(必须是 root 节点),不会走到服务层白名单。
    assert page_break.status_code == 422, page_break.text

    foreign_anchor = await _put_nodes(
        client, subject.id, composition["id"], headers,
        revision=2,
        nodes=[
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
    )
    assert foreign_anchor.status_code == 400, foreign_anchor.text
