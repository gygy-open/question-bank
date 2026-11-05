"""解答结构与思维量难度(规格 §12.3 N7)、类型 ↔ 知识点映射(N8)。"""
from sqlalchemy import select

from app.models.knowledge_point import KnowledgePoint
from app.models.question import Question

from .test_structure import (  # noqa: F401 - 复用题干结构化的夹具与辅助函数
    API,
    _auth,
    _decompose,
    _question,
    _run_jobs,
    _types,
    ctx,
    doc,
    fake_ai,
)

TWO_STEPS = {
    "steps": [
        {"goal": "求导", "method": "derivative", "uses": ["C1"], "result": "$f'(x)=3x^2+a$"},
        {"goal": "由零点个数确定 $a$ 的范围", "method": None, "method_hint": "数形结合", "uses": ["C2", "S1"],
         "answers": ["Q1"], "result": "$a<-3$", "key": True,
         "misconceptions": [{"description": "忽略极值点异号的条件，误选 B", "source": "distractor"}]},
    ]
}


async def _accepted_stem(client, db_session, ctx):
    question = await _question(client, ctx)
    draft = (await _decompose(client, db_session, ctx, question["id"]))["draft"]
    await client.post(
        f"{API}/structure/review", json={"run_ids": [draft["id"]], "action": "accept"}, headers=_auth(ctx["editor"])
    )
    return question, draft


async def _method_type(client, ctx, weight=2):
    types = await _types(client, ctx)
    response = await client.post(f"{API}/structure/types", json={
        "subject_id": ctx["subject"].id, "name": "求导", "code": "derivative",
        "parent_id": types["method"]["id"], "weight": weight,
    }, headers=_auth(ctx["editor"]))
    assert response.status_code == 200, response.text
    return response.json()


async def _solution(client, ctx, question_id):
    response = await client.get(f"{API}/structure/solutions/questions/{question_id}", headers=_auth(ctx["editor"]))
    assert response.status_code == 200, response.text
    return response.json()


async def test_solution_needs_an_accepted_stem(client, db_session, ctx, fake_ai):
    question = await _question(client, ctx)
    response = await client.post(
        f"{API}/structure/solutions/decompose", json={"question_ids": [question["id"]]}, headers=_auth(ctx["editor"])
    )
    assert response.json() == {"queued": [], "skipped": [question["id"]]}


async def test_solution_steps_thinking_load_and_difficulty(client, db_session, ctx, fake_ai):
    question, stem = await _accepted_stem(client, db_session, ctx)
    method = await _method_type(client, ctx, weight=2)
    assert method["kind"] == "method" and method["weight"] == 2

    response = await client.post(
        f"{API}/structure/solutions/decompose", json={"question_ids": [question["id"]]}, headers=_auth(ctx["editor"])
    )
    assert response.json()["queued"] == [question["id"]]
    fake_ai.calls.clear()
    fake_ai.outputs = [TWO_STEPS]
    await _run_jobs(db_session)
    assert "C1. $f(x)=x^{3}+ax+2$" in fake_ai.calls[0]["user"] and "- derivative: 求导 (weight 2)" in fake_ai.calls[0]["system"]

    view = await _solution(client, ctx, question["id"])
    draft = view["solutions"][0]["draft"]
    assert draft["check_errors"] == 0 and draft["thinking_load"] == 3
    first, second = draft["steps"]
    assert first["uses_elements"] == [stem["elements"][0]["id"]] and first["method_path"] == ["方法", "求导"]
    assert second["uses_steps"] == [0] and second["answers"] == [stem["asks"][0]["id"]] and second["is_key"]
    assert second["method_hint"] == "数形结合" and second["misconceptions"][0]["source"] == "distractor"

    reviewed = await client.post(
        f"{API}/structure/solutions/review", json={"run_ids": [draft["id"]], "action": "accept"},
        headers=_auth(ctx["editor"]),
    )
    assert reviewed.json() == {"updated": [draft["id"]], "skipped": []}
    assert (await _solution(client, ctx, question["id"]))["thinking_difficulty"] == 3

    other = await _question(client, ctx, content=doc("计算 1+1"), allow_duplicate=True)
    listed = (await client.get(
        f"{API}/questions", params={"subject_id": ctx["subject"].id, "thinking_min": 3, "sort": "thinking_desc"},
        headers=_auth(ctx["editor"]),
    )).json()
    assert [q["id"] for q in listed["items"]] == [question["id"]] and listed["items"][0]["thinking_difficulty"] == 3
    ordered = (await client.get(
        f"{API}/questions", params={"subject_id": ctx["subject"].id, "sort": "thinking_asc"}, headers=_auth(ctx["editor"]),
    )).json()
    assert [q["id"] for q in ordered["items"]] == [question["id"], other["id"]]

    # 方法权重变化:已采纳解答与题目难度一并重算。
    await client.patch(f"{API}/structure/types/{method['id']}", json={"weight": 3.5}, headers=_auth(ctx["editor"]))
    db_session.expire_all()
    assert (await db_session.get(Question, question["id"])).thinking_difficulty == 4.5


async def test_check_errors_retry_and_stale_after_stem_changes(client, db_session, ctx, fake_ai):
    question, stem = await _accepted_stem(client, db_session, ctx)
    broken = {"steps": [{"goal": "分析", "uses": ["S2"], "result": "..."}, {"goal": "求导", "uses": ["C1"]}]}
    await client.post(
        f"{API}/structure/solutions/decompose", json={"question_ids": [question["id"]]}, headers=_auth(ctx["editor"])
    )
    fake_ai.calls.clear()
    fake_ai.outputs = [broken, TWO_STEPS]
    await _run_jobs(db_session)
    assert "Q1 is not answered" in fake_ai.calls[1]["user"] and "uses later steps" in fake_ai.calls[1]["user"]
    draft = (await _solution(client, ctx, question["id"]))["solutions"][0]["draft"]
    assert draft["check_errors"] == 0 and draft["stale"] is False

    # 人工修改并采纳;之后题干拆解被新采纳的版本取代 → 解答需复核。
    saved = await client.post(f"{API}/structure/solutions/save", json={
        "question_id": question["id"],
        "steps": [{"goal": "直接分析", "uses_elements": [e["id"] for e in stem["elements"]],
                   "answers": [stem["asks"][0]["id"]]}],
        "accept": True,
    }, headers=_auth(ctx["editor"]))
    assert saved.status_code == 200, saved.text
    accepted = saved.json()["solutions"][0]["accepted"]
    assert accepted["origin"] == "human" and accepted["thinking_load"] == 1 and saved.json()["thinking_difficulty"] == 1

    new_stem = (await _decompose(client, db_session, ctx, question["id"]))["draft"]
    await client.post(
        f"{API}/structure/review", json={"run_ids": [new_stem["id"]], "action": "accept"}, headers=_auth(ctx["editor"])
    )
    assert (await _solution(client, ctx, question["id"]))["solutions"][0]["accepted"]["stale"] is True

    viewer = await client.post(f"{API}/structure/solutions/save", json={
        "question_id": question["id"], "steps": [{"goal": "x"}],
    }, headers=_auth(ctx["viewer"]))
    assert viewer.status_code == 403


async def test_types_map_to_knowledge_points_and_suggest_them(client, db_session, ctx, fake_ai):
    question, _ = await _accepted_stem(client, db_session, ctx)
    kp = KnowledgePoint(name="函数的零点", slug="zeros", subject_id=ctx["subject"].id)
    db_session.add(kp)
    await db_session.commit()
    types = await _types(client, ctx)
    patched = await client.patch(
        f"{API}/structure/types/{types['algebra']['id']}", json={"knowledge_point_ids": [kp.id]},
        headers=_auth(ctx["editor"]),
    )
    assert patched.status_code == 200 and patched.json()["knowledge_point_ids"] == [kp.id]
    assert (await _types(client, ctx))["algebra"]["knowledge_point_ids"] == [kp.id]

    suggestions = (await client.get(
        f"{API}/structure/questions/{question['id']}/knowledge-suggestions", headers=_auth(ctx["editor"])
    )).json()
    assert suggestions == {"items": [{"id": kp.id, "name": "函数的零点", "matches": 1}], "current_ids": []}

    wrong = await client.patch(
        f"{API}/structure/types/{types['algebra']['id']}", json={"knowledge_point_ids": [999999]},
        headers=_auth(ctx["editor"]),
    )
    assert wrong.status_code == 400
    rows = (await db_session.execute(select(KnowledgePoint.id))).scalars().all()
    assert rows == [kp.id]


async def test_existing_subjects_get_a_method_root_once(db_session, ctx):
    from app.models.question_structure import StructType
    from app.services.structure import types as type_svc

    subject_id = ctx["subject"].id
    db_session.add(StructType(subject_id=subject_id, kind="condition", code="algebra", name="代数"))
    await db_session.commit()
    await type_svc.ensure_roots(db_session, subject_id)
    await type_svc.ensure_roots(db_session, subject_id)
    codes = sorted((await db_session.execute(select(StructType.code).where(StructType.subject_id == subject_id))).scalars())
    # 一期建好的学科只补方法根,不会把老师删掉的其他根再建出来。
    assert codes == ["algebra", "method"]
