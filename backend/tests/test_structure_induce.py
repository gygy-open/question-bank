"""元素归纳(二期):收集未归类条目 → AI 合并成候选 → 新建 / 并入 / 忽略,确认后回填类型。"""
from sqlalchemy import select

from app.models.question_structure import StructAsk, StructElement, StructTypeCandidate
from app.services.structure import induce as induce_svc

from .test_structure import (  # noqa: F401 - 复用题干结构化的夹具与辅助函数
    API,
    GOOD_OUTPUT,
    _auth,
    _decompose,
    _question,
    _run_jobs,
    _types,
    ctx,
    doc,
    fake_ai,
)

UNTYPED = {
    "conditions": [{**c, "type": None} for c in GOOD_OUTPUT["conditions"]],
    "asks": [{**a, "type": None} for a in GOOD_OUTPUT["asks"]],
}


async def _accepted_untyped_questions(client, db_session, ctx, fake_ai, count):
    for index in range(count):
        content = doc("已知函数", ("m", "f(x)=x^{3}+ax+2"), "存在3个零点，则", ("m", "a"), f"的取值范围是（{index}）")
        question = await _question(client, ctx, content=content, allow_duplicate=True)
        fake_ai.outputs = [UNTYPED]
        draft = (await _decompose(client, db_session, ctx, question["id"]))["draft"]
        response = await client.post(
            f"{API}/structure/review", json={"run_ids": [draft["id"]], "action": "accept"}, headers=_auth(ctx["editor"])
        )
        assert response.status_code == 200, response.text


async def _candidates(client, ctx):
    response = await client.get(
        f"{API}/structure/candidates", params={"subject_id": ctx["subject"].id}, headers=_auth(ctx["editor"])
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_group_by_hint_merges_spelling_variants_and_keeps_hintless_items_apart():
    items = [
        induce_svc.Unclassified("condition", 1, "a", "含参 三次函数"),
        induce_svc.Unclassified("condition", 2, "b", "含参  三次函数"),
        induce_svc.Unclassified("condition", 3, "c", None),
        induce_svc.Unclassified("condition", 4, "d", None),
    ]
    groups = induce_svc.group_by_hint(items)
    assert [len(g.items) for g in groups] == [2, 1, 1]
    assert groups[1].label == "c"


async def test_induce_requires_enough_data_and_manager(client, db_session, ctx, fake_ai):
    payload = {"subject_id": ctx["subject"].id}
    denied = await client.post(f"{API}/structure/candidates/induce", json=payload, headers=_auth(ctx["editor"]))
    assert denied.status_code == 403
    too_few = await client.post(f"{API}/structure/candidates/induce", json=payload, headers=_auth(ctx["manager"]))
    assert too_few.status_code == 400 and too_few.json()["code"] == "structure.induce_not_enough_data"


async def test_induce_then_accept_merge_and_ignore(client, db_session, ctx, fake_ai):
    await _accepted_untyped_questions(client, db_session, ctx, fake_ai, induce_svc.MIN_ITEMS)
    listed = await _candidates(client, ctx)
    assert listed["unclassified"] == {"condition": 20, "ask": 10} and listed["items"] == []

    queued = await client.post(
        f"{API}/structure/candidates/induce", json={"subject_id": ctx["subject"].id}, headers=_auth(ctx["manager"])
    )
    assert queued.status_code == 200, queued.text
    # 条件:第一次漏了 g1 → 重试仍漏 → g1 单独成为候选;设问一次成功。
    only_first = {"candidates": [{"name": "含参三次函数", "definition": "带参数的三次函数", "parent": "algebra", "groups": [0]}]}
    fake_ai.calls.clear()
    fake_ai.outputs = [
        only_first,
        only_first,
        {"candidates": [{"name": "求参数范围", "parent": "ask", "similar": "ask", "groups": ["g0"]}]},
    ]
    await _run_jobs(db_session)
    assert len(fake_ai.calls) == 3
    assert "g1 are not assigned" in fake_ai.calls[1]["user"]
    assert "parametric cubic function" in fake_ai.calls[0]["user"]

    items = {c["name"]: c for c in (await _candidates(client, ctx))["items"]}
    assert set(items) == {"含参三次函数", "number of zeros", "求参数范围"}
    assert items["含参三次函数"]["count"] == 10 and items["含参三次函数"]["suggested_parent_path"] == ["代数"]
    assert items["求参数范围"]["similar_type_path"] == ["设问"] and items["求参数范围"]["samples"]

    types = await _types(client, ctx)
    viewer_accept = await client.post(
        f"{API}/structure/candidates/{items['含参三次函数']['id']}/accept", json={}, headers=_auth(ctx["viewer"])
    )
    assert viewer_accept.status_code == 403
    accepted = await client.post(
        f"{API}/structure/candidates/{items['含参三次函数']['id']}/accept",
        json={"name": "三次函数（含参）"},
        headers=_auth(ctx["editor"]),
    )
    assert accepted.status_code == 200, accepted.text
    new_type = accepted.json()
    assert new_type["parent_id"] == types["algebra"]["id"] and new_type["usage"] == 10
    again = await client.post(
        f"{API}/structure/candidates/{items['含参三次函数']['id']}/accept", json={}, headers=_auth(ctx["editor"])
    )
    assert again.status_code == 400 and again.json()["code"] == "structure.candidate_resolved"

    merged = await client.post(
        f"{API}/structure/candidates/{items['求参数范围']['id']}/merge",
        json={"type_id": types["ask"]["id"]}, headers=_auth(ctx["editor"]),
    )
    assert merged.status_code == 200, merged.text
    assert all(t == types["ask"]["id"] for t in (await db_session.execute(select(StructAsk.type_id))).scalars())

    wrong_kind = await client.post(
        f"{API}/structure/candidates/{items['number of zeros']['id']}/merge",
        json={"type_id": types["ask"]["id"]}, headers=_auth(ctx["editor"]),
    )
    assert wrong_kind.status_code == 400
    ignored = await client.post(
        f"{API}/structure/candidates/{items['number of zeros']['id']}/ignore", headers=_auth(ctx["editor"])
    )
    assert ignored.status_code == 200

    after = await _candidates(client, ctx)
    # 忽略的条目保持未归类,但不再参与归纳。
    assert after["items"] == [] and after["unclassified"] == {"condition": 0, "ask": 0}
    untyped = (await db_session.execute(select(StructElement).where(StructElement.type_id.is_(None)))).scalars().all()
    assert len(untyped) == 10
    statuses = sorted((await db_session.execute(select(StructTypeCandidate.status))).scalars())
    assert statuses == ["accepted", "ignored", "merged"]
