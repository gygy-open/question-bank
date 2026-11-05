"""元素组(N2)、整组替换与跨题拼装(N4):一致性校验、候选、草稿题与来源关系。"""
import json

from sqlalchemy import select

from app.models.job import Job
from app.models.question_relation import QuestionRelation
from app.models.question_structure import StructRun
from app.services.structure.compose import consistency_problems

from .test_structure import (  # noqa: F401 - 复用题干结构化的夹具与辅助函数
    API,
    _auth,
    _decompose,
    _question,
    _run_jobs,
    ctx,
    doc,
    fake_ai,
)

G_STEM = "已知函数$g(x)=x^{3}+ax-1$存在3个零点，则$a$的取值范围是（ ）"
G_DOC = doc("已知函数", ("m", "g(x)=x^{3}+ax-1"), "存在3个零点，则", ("m", "a"), "的取值范围是（ ）")
F_DOC = doc("已知函数", ("m", "f(x)=x^{3}+ax+2"), "存在3个零点，则", ("m", "a"), "的取值范围是（ ）")


def _output(fn):
    return {
        "conditions": [
            {"source": f"${fn}$", "content": f"${fn}$", "type": "algebra"},
            {"source": "存在3个零点", "content": f"${fn[:4]}$ 存在 3 个零点", "type": "algebra"},
        ],
        "asks": [{"source": "$a$的取值范围", "content": "求 $a$ 的取值范围", "type": "ask", "depends_on": [0, 1]}],
    }


async def _grouped(client, db_session, ctx, fake_ai, content, fn):
    """建题 → AI 拆解 → 人工把两条条件设为元素组并采纳。"""
    question = await _question(client, ctx, content=content, allow_duplicate=True)
    fake_ai.outputs = [_output(fn)]
    draft = (await _decompose(client, db_session, ctx, question["id"]))["draft"]
    saved = await client.post(f"{API}/structure/save", json={
        "target_id": question["id"], "base_run_id": draft["id"],
        "elements": [{"content": e["content"], "span_start": e["span"][0], "span_end": e["span"][1], "type_id": e["type_id"]}
                     for e in draft["elements"]],
        "asks": [{"content": a["content"], "span_start": a["span"][0], "span_end": a["span"][1], "type_id": a["type_id"],
                  "depends_on": [0, 1]} for a in draft["asks"]],
        "groups": [{"name": "函数与零点", "element_indices": [0, 1]}],
        "accept": True,
    }, headers=_auth(ctx["editor"]))
    assert saved.status_code == 200, saved.text
    return question, saved.json()["accepted"]


def test_consistency_requires_all_inputs_and_no_extra_conditions():
    assert consistency_problems(["$a=1$", "$b=2$"], ["求 $a+b$"], ["$a = 1$", "$b=2$"], ["求 $a+b$"]) == []
    problems = consistency_problems(["$a=1$"], ["求 $a$"], ["$a=1$", "$c=3$"], [])
    assert any("adds a condition" in p for p in problems) and any("ask is missing" in p for p in problems)


async def test_groups_are_saved_and_overlaps_rejected(client, db_session, ctx, fake_ai):
    question, run = await _grouped(client, db_session, ctx, fake_ai, F_DOC, "f(x)=x^{3}+ax+2")
    group = run["groups"][0]
    assert group["name"] == "函数与零点" and group["element_ids"] == [e["id"] for e in run["elements"]]
    assert len(group["type_ids"]) == 2
    bad = await client.post(f"{API}/structure/save", json={
        "target_id": question["id"],
        "elements": [{"content": "x"}, {"content": "y"}],
        "groups": [{"name": "a", "element_indices": [0, 1]}, {"name": "b", "element_indices": [1, 0]}],
    }, headers=_auth(ctx["editor"]))
    assert bad.status_code == 400


async def test_group_replacement_creates_a_checked_variant(client, db_session, ctx, fake_ai):
    first, first_run = await _grouped(client, db_session, ctx, fake_ai, F_DOC, "f(x)=x^{3}+ax+2")
    second, second_run = await _grouped(client, db_session, ctx, fake_ai, G_DOC, "g(x)=x^{3}+ax-1")
    group_id, source_id = first_run["groups"][0]["id"], second_run["groups"][0]["id"]

    candidates = (await client.get(f"{API}/structure/groups/{group_id}/candidates", headers=_auth(ctx["editor"]))).json()
    assert [c["group_id"] for c in candidates["items"]] == [source_id]
    assert candidates["items"][0]["question_id"] == second["id"]

    queued = await client.post(
        f"{API}/structure/groups/replace", json={"group_id": group_id, "source_group_id": source_id},
        headers=_auth(ctx["editor"]),
    )
    assert queued.status_code == 200, queued.text
    fake_ai.calls.clear()
    fake_ai.outputs = [
        {"stem": "设函数 $g(x)=x^{3}+ax-1$ 存在3个零点，试求实数 $a$ 的取值范围", "options": [], "analysis": ""},
        _output("g(x)=x^{3}+ax-1"),
        {"valid": True, "analysis": "略"},
    ]
    await _run_jobs(db_session)
    assert "Replaced conditions" in fake_ai.calls[0]["user"]
    job = (await client.get(f"{API}/structure/jobs/{queued.json()['job_id']}", headers=_auth(ctx["editor"]))).json()
    assert job["status"] == "succeeded", job
    new_id = job["progress"]["question_id"]
    relation = (await db_session.execute(select(QuestionRelation).where(QuestionRelation.target_question_id == new_id))).scalars().one()
    assert (relation.source_question_id, relation.relation_type) == (first["id"], "variant_of")
    draft = (await db_session.execute(select(StructRun).where(StructRun.target_id == new_id))).scalars().one()
    assert draft.state == "draft"

    other_user = await client.get(f"{API}/structure/jobs/{queued.json()['job_id']}", headers=_auth(ctx["viewer"]))
    assert other_user.status_code == 404


async def test_compose_across_questions_links_every_source(client, db_session, ctx, fake_ai):
    first, first_run = await _grouped(client, db_session, ctx, fake_ai, F_DOC, "f(x)=x^{3}+ax+2")
    second, second_run = await _grouped(client, db_session, ctx, fake_ai, G_DOC, "g(x)=x^{3}+ax-1")
    payload = {
        "element_ids": [first_run["elements"][0]["id"], second_run["elements"][1]["id"]],
        "ask_ids": [second_run["asks"][0]["id"]],
        "q_type": "free_response",
    }
    viewer = await client.post(f"{API}/structure/compose", json=payload, headers=_auth(ctx["viewer"]))
    assert viewer.status_code == 403
    queued = await client.post(f"{API}/structure/compose", json=payload, headers=_auth(ctx["editor"]))
    assert queued.status_code == 200, queued.text
    assert queued.json()["source_question_ids"] == sorted([first["id"], second["id"]])

    stem = "已知函数$f(x)=x^{3}+ax+2$，$g(x)$ 存在3个零点，求$a$的取值范围"
    decomposition = {
        "conditions": [
            {"source": "$f(x)=x^{3}+ax+2$", "content": "$f(x)=x^{3}+ax+2$", "type": "algebra"},
            {"source": "存在3个零点", "content": "$g(x)$ 存在 3 个零点", "type": "algebra"},
        ],
        "asks": [{"source": "$a$的取值范围", "content": "求 $a$ 的取值范围", "type": "ask", "depends_on": [0, 1]}],
    }
    extra = {**decomposition, "conditions": [*decomposition["conditions"],
                                             {"source": "已知函数", "content": "$x>0$", "type": "algebra"}]}
    fake_ai.calls.clear()
    fake_ai.outputs = [
        {"stem": stem, "options": [], "analysis": ""}, extra,
        {"stem": stem, "options": [], "analysis": ""}, decomposition,
        {"valid": True, "analysis": "略"},
    ]
    await _run_jobs(db_session)
    assert "adds a condition that was not given: $x>0$" in fake_ai.calls[2]["user"]
    job = (await client.get(f"{API}/structure/jobs/{queued.json()['job_id']}", headers=_auth(ctx["editor"]))).json()
    assert job["status"] == "succeeded", job
    new_id = job["progress"]["question_id"]
    relations = (await db_session.execute(
        select(QuestionRelation.source_question_id, QuestionRelation.relation_type)
        .where(QuestionRelation.target_question_id == new_id)
    )).all()
    assert sorted(relations) == sorted([(first["id"], "composed_from"), (second["id"], "composed_from")])


async def test_inconsistent_composition_fails(client, db_session, ctx, fake_ai):
    first, first_run = await _grouped(client, db_session, ctx, fake_ai, F_DOC, "f(x)=x^{3}+ax+2")
    queued = await client.post(f"{API}/structure/compose", json={
        "element_ids": [first_run["elements"][0]["id"]], "ask_ids": [first_run["asks"][0]["id"]],
    }, headers=_auth(ctx["editor"]))
    wrong = {"conditions": [{"source": "已知", "content": "$x>0$"}], "asks": []}
    fake_ai.outputs = [{"stem": "已知 $x>0$", "options": []}, wrong, {"stem": "已知 $x>0$", "options": []}, wrong]
    await _run_jobs(db_session)
    job = await db_session.get(Job, queued.json()["job_id"])
    assert job.status == "failed" and json.loads(job.progress)["error_code"] == "inconsistent"
