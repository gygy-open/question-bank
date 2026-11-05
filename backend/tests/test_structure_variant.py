"""参数槽与变式(规格 §12.3 N1):定位与体检、随快照继承、按位置改写、AI 校验、草稿题与关系。"""
import json

from sqlalchemy import select

from app.models.job import Job
from app.models.question import Question
from app.models.question_relation import QuestionRelation
from app.services.structure.params import DraftParam, check_params, locate_value

from .test_structure import (  # noqa: F401 - 复用题干结构化的夹具与辅助函数
    API,
    CUBIC,
    GOOD_OUTPUT,
    _auth,
    _decompose,
    _question,
    _run_jobs,
    ctx,
    doc,
    fake_ai,
)

CONSTANT = {"name": "常数项", "value": "2", "kind": "numeric", "domain": {"min": 1, "max": 9, "integer": True}}
WITH_PARAM = {
    "conditions": [{**GOOD_OUTPUT["conditions"][0], "params": [CONSTANT]}, GOOD_OUTPUT["conditions"][1]],
    "asks": GOOD_OUTPUT["asks"],
}
VALID = {"valid": True, "problems": [], "answer": "$a<-\\frac{15}{4}$", "analysis": "求导分析可得 $a<-\\frac{15}{4}$"}


# --------------------------------------------------------------------------- #
# 定位与体检(纯函数)
# --------------------------------------------------------------------------- #
def test_locate_value_skips_exponents_and_longer_numbers():
    stem = "$f(x)=x^2+12x+2$"
    span = locate_value(stem, "2", (0, len(stem)))
    assert span == (stem.rindex("2"), stem.rindex("2") + 1)
    assert locate_value(stem, "2", (0, len(stem)), occurrence=2) is None
    assert locate_value("$\\sin a + a$", "a", (0, 12)) == (6, 7)
    # 序号按全部出现计数(4.5 里的 4 算第 2 次)或只数独立出现,都能找到表格里的 4。
    row = "x | 1 | 4\ny | 4.5 | 4"
    assert locate_value(row, "4", (0, len(row)), occurrence=3) == (row.rindex("4"), row.rindex("4") + 1)
    assert locate_value(row, "4", (0, len(row)), occurrence=2) == (row.rindex("4"), row.rindex("4") + 1)


def test_check_params_reports_mismatch_outside_and_overlap():
    stem = "已知 $a=3$，$b=4$"
    element_spans = [(3, 8), (9, 14)]
    params = [
        DraftParam(name="a", value="3", owner="element", owner_index=0),
        DraftParam(name="b", value="9", owner="element", owner_index=1),
        DraftParam(name="x", value="4", owner="element", owner_index=0, span=(12, 13)),
        DraftParam(name="y", value="=3", owner="element", owner_index=0, span=(5, 7)),
    ]
    codes = [(i.code, i.index) for i in check_params(stem, params, element_spans, [])]
    assert params[0].span == (6, 7)
    assert ("param_not_found", 1) in codes and ("param_outside_owner", 2) in codes
    # 重叠记在区间靠后的那个参数上:y 从 5 开始,a 从 6 开始。
    assert ("param_overlap", 0) in codes


# --------------------------------------------------------------------------- #
# 拆解中的参数与继承
# --------------------------------------------------------------------------- #
async def _accepted_with_param(client, db_session, ctx, fake_ai):
    question = await _question(client, ctx)
    fake_ai.outputs = [WITH_PARAM]
    draft = (await _decompose(client, db_session, ctx, question["id"]))["draft"]
    await client.post(
        f"{API}/structure/review", json={"run_ids": [draft["id"]], "action": "accept"}, headers=_auth(ctx["editor"])
    )
    return question, draft


async def test_ai_params_are_located_and_inherited_by_human_edits(client, db_session, ctx, fake_ai):
    question, draft = await _accepted_with_param(client, db_session, ctx, fake_ai)
    param = draft["params"][0]
    assert param["element_id"] == draft["elements"][0]["id"] and param["value"] == "2"
    assert param["span"] == [CUBIC.index("+2$") + 1, CUBIC.index("+2$") + 2]
    assert param["domain"] == {"min": 1, "max": 9, "integer": True} and param["domain_confirmed"] is False

    saved = await client.post(f"{API}/structure/save", json={
        "target_id": question["id"],
        "base_run_id": draft["id"],
        "elements": [{"content": e["content"], "span_start": e["span"][0], "span_end": e["span"][1]} for e in draft["elements"]],
        "asks": [{"content": a["content"], "span_start": a["span"][0], "span_end": a["span"][1], "depends_on": [0, 1]}
                 for a in draft["asks"]],
        "params": [{"owner": "element", "owner_index": 0, "name": "常数项", "value": "2",
                    "span_start": param["span"][0], "span_end": param["span"][1],
                    "domain": param["domain"], "domain_confirmed": True}],
        "accept": True,
    }, headers=_auth(ctx["editor"]))
    assert saved.status_code == 200, saved.text
    accepted = saved.json()["accepted"]
    assert accepted["check_errors"] == 0
    assert accepted["params"][0]["domain_confirmed"] is True and accepted["params"][0]["span"] == param["span"]


# --------------------------------------------------------------------------- #
# 变式
# --------------------------------------------------------------------------- #
async def _variant_job(db_session, question_id):
    return (await db_session.execute(
        select(Job).where(Job.type == "structure.variant", Job.target_id == question_id).order_by(Job.id.desc())
    )).scalars().first()


async def test_variant_replaces_by_position_and_creates_a_linked_draft(client, db_session, ctx, fake_ai):
    question, draft = await _accepted_with_param(client, db_session, ctx, fake_ai)
    param_id = draft["params"][0]["id"]
    response = await client.post(
        f"{API}/structure/variants",
        json={"question_id": question["id"], "values": [{"param_id": param_id, "value": "$5$"}]},
        headers=_auth(ctx["editor"]),
    )
    assert response.status_code == 200, response.text
    running = await client.post(
        f"{API}/structure/variants",
        json={"question_id": question["id"], "values": [{"param_id": param_id, "value": "6"}]},
        headers=_auth(ctx["editor"]),
    )
    assert running.status_code == 409 and running.json()["code"] == "structure.variant_running"

    fake_ai.calls.clear()
    fake_ai.outputs = [VALID]
    await _run_jobs(db_session)
    assert "x^{3}+ax+5" in fake_ai.calls[0]["user"] and "x^{3}+ax+2" in fake_ai.calls[0]["user"]

    status = (await client.get(
        f"{API}/structure/questions/{question['id']}/variant-job", headers=_auth(ctx["editor"])
    )).json()["job"]
    assert status["status"] == "succeeded", status
    new_id = status["progress"]["question_id"]
    assert status["progress"]["changes"] == {"常数项": ["2", "5"]}
    created = await db_session.get(Question, new_id)
    assert created.status == "draft"
    content = json.loads(created.content) if isinstance(created.content, str) else created.content
    latex = [n["attrs"]["latex"] for n in content["content"][0]["content"] if n["type"] == "inlineMath"]
    assert latex == ["f(x)=x^{3}+ax+5", "a"]
    relation = (await db_session.execute(select(QuestionRelation))).scalars().one()
    assert (relation.source_question_id, relation.target_question_id, relation.relation_type) == (
        question["id"], new_id, "variant_of"
    )
    relations = (await client.get(f"{API}/questions/{question['id']}/relations", headers=_auth(ctx["editor"]))).json()
    assert [t["relation_type"] for t in relations["targets"]] == ["variant_of"]


async def test_invalid_variant_fails_without_creating_a_question(client, db_session, ctx, fake_ai):
    question, draft = await _accepted_with_param(client, db_session, ctx, fake_ai)
    await client.post(
        f"{API}/structure/variants",
        json={"question_id": question["id"], "values": [{"param_id": draft["params"][0]["id"], "value": "7"}]},
        headers=_auth(ctx["editor"]),
    )
    fake_ai.outputs = [{"valid": False, "problems": ["没有满足条件的 a"]}]
    before = len((await db_session.execute(select(Question.id))).all())
    await _run_jobs(db_session)
    job = await _variant_job(db_session, question["id"])
    assert job.status == "failed" and job.error == "没有满足条件的 a"
    assert json.loads(job.progress)["error_code"] == "variant_invalid"
    assert len((await db_session.execute(select(Question.id))).all()) == before


async def test_ai_values_need_a_confirmed_domain_and_are_checked(client, db_session, ctx, fake_ai):
    question, draft = await _accepted_with_param(client, db_session, ctx, fake_ai)
    param_id = draft["params"][0]["id"]
    unconfirmed = await client.post(
        f"{API}/structure/variants", json={"question_id": question["id"], "auto_param_ids": [param_id]},
        headers=_auth(ctx["editor"]),
    )
    assert unconfirmed.status_code == 400 and unconfirmed.json()["code"] == "structure.param_domain_unconfirmed"
    viewer = await client.post(
        f"{API}/structure/variants", json={"question_id": question["id"], "values": [{"param_id": param_id, "value": "3"}]},
        headers=_auth(ctx["viewer"]),
    )
    assert viewer.status_code == 403

    p = draft["params"][0]
    saved = (await client.post(f"{API}/structure/save", json={
        "target_id": question["id"], "base_run_id": draft["id"],
        "elements": [{"content": e["content"], "span_start": e["span"][0], "span_end": e["span"][1]} for e in draft["elements"]],
        "asks": [{"content": a["content"], "span_start": a["span"][0], "span_end": a["span"][1]} for a in draft["asks"]],
        "params": [{"owner": "element", "owner_index": 0, "name": "常数项", "value": "2",
                    "span_start": p["span"][0], "span_end": p["span"][1], "domain": p["domain"], "domain_confirmed": True}],
        "accept": True,
    }, headers=_auth(ctx["editor"]))).json()
    confirmed_id = saved["accepted"]["params"][0]["id"]

    # AI 取了范围外的值:任务失败。
    await client.post(
        f"{API}/structure/variants", json={"question_id": question["id"], "auto_param_ids": [confirmed_id]},
        headers=_auth(ctx["editor"]),
    )
    fake_ai.outputs = [{"values": {str(confirmed_id): "12"}}]
    await _run_jobs(db_session)
    job = await _variant_job(db_session, question["id"])
    assert job.status == "failed" and json.loads(job.progress)["error_code"] == "out_of_domain"

    await client.post(
        f"{API}/structure/variants", json={"question_id": question["id"], "auto_param_ids": [confirmed_id]},
        headers=_auth(ctx["editor"]),
    )
    fake_ai.outputs = [{"values": {str(confirmed_id): "4"}}, VALID]
    await _run_jobs(db_session)
    job = await _variant_job(db_session, question["id"])
    assert job.status == "succeeded", job.error


async def test_stale_structure_cannot_make_variants(client, db_session, ctx, fake_ai):
    question, draft = await _accepted_with_param(client, db_session, ctx, fake_ai)
    await client.put(
        f"{API}/questions/{question['id']}",
        json={"content": doc("已知函数", ("m", "f(x)=x^{3}+ax+9"), "存在3个零点，则", ("m", "a"), "的取值范围是（ ）")},
        headers=_auth(ctx["editor"]),
    )
    response = await client.post(
        f"{API}/structure/variants",
        json={"question_id": question["id"], "values": [{"param_id": draft["params"][0]["id"], "value": "5"}]},
        headers=_auth(ctx["editor"]),
    )
    assert response.status_code == 400 and response.json()["code"] == "structure.run_stale"


async def test_similar_by_params_finds_the_same_question_with_other_numbers(client, db_session, ctx, fake_ai):
    question, draft = await _accepted_with_param(client, db_session, ctx, fake_ai)
    await client.post(
        f"{API}/structure/variants",
        json={"question_id": question["id"], "values": [{"param_id": draft["params"][0]["id"], "value": "5"}]},
        headers=_auth(ctx["editor"]),
    )
    fake_ai.outputs = [VALID]
    await _run_jobs(db_session)
    new_id = (await _variant_job(db_session, question["id"])).progress
    new_id = json.loads(new_id)["question_id"]
    variant_output = {
        "conditions": [{**WITH_PARAM["conditions"][0], "source": "$f(x)=x^{3}+ax+5$", "content": "$f(x)=x^{3}+ax+5$",
                        "params": [{**CONSTANT, "value": "5"}]}, GOOD_OUTPUT["conditions"][1]],
        "asks": GOOD_OUTPUT["asks"],
    }
    fake_ai.outputs = [variant_output]
    variant_draft = (await _decompose(client, db_session, ctx, new_id))["draft"]
    await client.post(
        f"{API}/structure/review", json={"run_ids": [variant_draft["id"]], "action": "accept"}, headers=_auth(ctx["editor"])
    )
    items = (await client.get(
        f"{API}/structure/questions/{question['id']}/similar", params={"mode": "params"}, headers=_auth(ctx["editor"])
    )).json()["items"]
    assert [i["question_id"] for i in items] == [new_id] and items[0]["shared_params"] == ["常数项"]


def test_replace_options_keeps_labels_and_requires_the_same_count():
    from app.services.structure.variant import replace_options

    options = [{"label": "A", "content": {"type": "doc"}}, {"label": "B", "content": {"type": "doc"}}]
    replaced, changed = replace_options(options, ["$\\frac{1}{2}$", "$1$"])
    assert changed and [o["label"] for o in replaced] == ["A", "B"]
    assert replaced[0]["content"]["content"][0]["content"][0]["attrs"]["latex"] == "\\frac{1}{2}"
    assert replace_options(options, ["only one"]) == (options, False)


def test_guard_rejects_choice_variants_without_a_correct_option():
    from app.services.structure.variant import guard_verdict

    options = [{"label": "A"}, {"label": "B"}]
    assert guard_verdict({"valid": True}, "single_choice", options)["valid"] is False
    assert guard_verdict({"valid": True, "correct_options": ["C"]}, "single_choice", options)["valid"] is False
    assert guard_verdict({"valid": True, "correct_options": ["A", "B"]}, "single_choice", options)["valid"] is False
    assert guard_verdict({"valid": True, "correct_options": ["B"]}, "single_choice", options)["valid"] is True
    assert guard_verdict({"valid": True}, "free_response", None)["valid"] is True
