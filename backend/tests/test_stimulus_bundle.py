from sqlalchemy import func, select

from app.models.question import Question
from app.models.stimulus import Stimulus
from tests.test_stimulus_questions import API, _auth, doc, group_ctx  # noqa: F401


def _new(text: str, **extra) -> dict:
    return {"create": {"content": doc(text), "q_type": "free_response", **extra}}


def _base(ctx) -> str:
    return f"{API}/subjects/{ctx['subject'].id}/stimuli"


async def _count(db_session, model, *conditions) -> int:
    return await db_session.scalar(select(func.count()).select_from(model).where(*conditions))


async def test_bundle_create_saves_stimulus_new_and_existing_questions_in_order(
    client, db_session, group_ctx
):
    existing = group_ctx["questions"][0]
    response = await client.post(
        f"{_base(group_ctx)}/bundle",
        json={
            "content": doc("阅读材料"),
            "source": "zz-sandbox",
            "questions": [_new("新小题一"), {"id": existing.id}, _new("新小题二")],
        },
        headers=_auth(group_ctx["owner"]),
    )
    assert response.status_code == 201, response.text
    detail = response.json()
    assert detail["source"] == "zz-sandbox"
    questions = detail["questions"]
    assert [q["stimulus_position"] for q in questions] == [0, 1, 2]
    assert questions[1]["id"] == existing.id
    assert questions[0]["content"] == doc("新小题一")
    assert questions[2]["content"] == doc("新小题二")
    created = await db_session.scalar(select(Question).where(Question.id == questions[0]["id"]))
    assert created.subject_id == group_ctx["subject"].id
    assert created.created_by == group_ctx["owner"].id


async def test_bundle_update_edits_reorders_detaches_and_bumps_revision(
    client, db_session, group_ctx
):
    first, second = group_ctx["questions"][:2]
    created = await client.post(
        f"{_base(group_ctx)}/bundle",
        json={"content": doc("旧材料"), "questions": [{"id": first.id}, {"id": second.id}]},
        headers=_auth(group_ctx["owner"]),
    )
    stimulus = created.json()

    response = await client.put(
        f"{_base(group_ctx)}/{stimulus['id']}/bundle",
        json={
            "expected_revision": stimulus["revision"],
            "content": doc("新材料"),
            "questions": [
                _new("追加小题"),
                {"id": second.id, "update": {"content": doc("改过的第二题")}},
            ],
        },
        headers=_auth(group_ctx["owner"]),
    )
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["content"] == doc("新材料")
    assert detail["revision"] == stimulus["revision"] + 1
    assert detail["content_revision"] == stimulus["content_revision"] + 1
    assert [q["id"] for q in detail["questions"]][1] == second.id
    assert detail["questions"][1]["content"] == doc("改过的第二题")
    detached = await db_session.scalar(
        select(Question).where(Question.id == first.id).execution_options(populate_existing=True)
    )
    assert detached.stimulus_id is None

    stale = await client.put(
        f"{_base(group_ctx)}/{stimulus['id']}/bundle",
        json={"expected_revision": stimulus["revision"], "content": doc("过期写入")},
        headers=_auth(group_ctx["owner"]),
    )
    assert stale.status_code == 409, stale.text


async def test_bundle_rolls_back_everything_when_a_member_is_invalid(
    client, db_session, group_ctx
):
    foreign = group_ctx["questions"][3]
    stimuli_before = await _count(db_session, Stimulus)
    response = await client.post(
        f"{_base(group_ctx)}/bundle",
        json={"content": doc("回滚材料"), "questions": [_new("不应落库"), {"id": foreign.id}]},
        headers=_auth(group_ctx["owner"]),
    )
    assert response.status_code == 422, response.text
    assert await _count(db_session, Stimulus) == stimuli_before
    assert await _count(db_session, Question, Question.content.contains("不应落库")) == 0


async def test_bundle_update_rollback_keeps_existing_stimulus_and_questions(
    client, db_session, group_ctx
):
    first, second = group_ctx["questions"][:2]
    stimulus = (
        await client.post(
            f"{_base(group_ctx)}/bundle",
            json={"content": doc("原材料"), "questions": [{"id": first.id}]},
            headers=_auth(group_ctx["owner"]),
        )
    ).json()
    response = await client.put(
        f"{_base(group_ctx)}/{stimulus['id']}/bundle",
        json={
            "expected_revision": stimulus["revision"],
            "content": doc("不应保存"),
            "questions": [
                {"id": first.id, "update": {"content": doc("不应保存的小题")}},
                {"id": 999999},
            ],
        },
        headers=_auth(group_ctx["owner"]),
    )
    assert response.status_code == 404, response.text
    current = await client.get(
        f"{_base(group_ctx)}/{stimulus['id']}", headers=_auth(group_ctx["owner"])
    )
    body = current.json()
    assert body["revision"] == stimulus["revision"]
    assert body["content"] == doc("原材料")
    assert body["questions"][0]["content"] == doc("第一题")


async def test_bundle_can_switch_stimulus_and_members_to_private_together(client, group_ctx):
    first = group_ctx["questions"][0]
    stimulus = (
        await client.post(
            f"{_base(group_ctx)}/bundle",
            json={"content": doc("材料"), "questions": [{"id": first.id}]},
            headers=_auth(group_ctx["owner"]),
        )
    ).json()
    url = f"{_base(group_ctx)}/{stimulus['id']}/bundle"

    rejected = await client.put(
        url,
        json={
            "expected_revision": stimulus["revision"],
            "content": doc("材料"),
            "visibility": "private",
            "questions": [{"id": first.id}],
        },
        headers=_auth(group_ctx["owner"]),
    )
    assert rejected.status_code == 422, rejected.text

    accepted = await client.put(
        url,
        json={
            "expected_revision": stimulus["revision"],
            "content": doc("材料"),
            "visibility": "private",
            "questions": [{"id": first.id, "update": {"visibility": "private"}}],
        },
        headers=_auth(group_ctx["owner"]),
    )
    assert accepted.status_code == 200, accepted.text
    detail = accepted.json()
    assert detail["visibility"] == "private"
    assert detail["questions"][0]["visibility"] == "private"


async def test_bundle_requires_edit_permission_and_valid_shape(client, group_ctx):
    forbidden = await client.post(
        f"{_base(group_ctx)}/bundle",
        json={"content": doc("材料"), "questions": []},
        headers=_auth(group_ctx["other"]),
    )
    assert forbidden.status_code == 403, forbidden.text

    malformed = await client.post(
        f"{_base(group_ctx)}/bundle",
        json={"content": doc("材料"), "questions": [{"update": {"content": doc("x")}}]},
        headers=_auth(group_ctx["owner"]),
    )
    assert malformed.status_code == 422, malformed.text
