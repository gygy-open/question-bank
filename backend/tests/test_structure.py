"""题干结构化端到端:类型树、AI 拆解 job、人工保存与审核、过期、检索筛选、同结构题、
自动入队、材料共享、审核队列、统计与开关。AI 调用用脚本化的假 provider 代替。"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.permissions import SubjectRole
from app.core.secrets import encrypt_secret
from app.core.security import create_access_token
from app.models.ai_config import AIModel, AIProvider
from app.models.job import Job
from app.models.question_structure import StructRun
from app.models.subject import Subject
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.services import ai_provider as ai_provider_module
from app.services.jobs import job_service, run_job
from app.services.structure import service as struct_service
from app.services.structure.decompose import PROMPT_VERSION

API = "/api/v1"
CUBIC = "已知函数$f(x)=x^{3}+ax+2$存在3个零点，则$a$的取值范围是（ ）"
OPTIONS = ["$(-\\infty,-2)$", "$(-\\infty,-3)$"]


def doc(*parts):
    """段落 RichDoc:字符串是文本,("m", latex) 是行内公式。"""
    content = []
    for part in parts:
        if isinstance(part, tuple):
            content.append({"type": "inlineMath", "attrs": {"latex": part[1]}})
        else:
            content.append({"type": "text", "text": part})
    return {"type": "doc", "content": [{"type": "paragraph", "content": content}]}


CUBIC_DOC = doc("已知函数", ("m", "f(x)=x^{3}+ax+2"), "存在3个零点，则", ("m", "a"), "的取值范围是（ ）")


def _auth(user):
    return {"Authorization": "Bearer " + create_access_token(user.id)}


class FakeProvider:
    """按脚本依次返回拆解结果,记录收到的提示词。"""

    def __init__(self):
        self.outputs = []
        self.calls = []

    async def generate_json(self, system, user, config):
        self.calls.append({"system": system, "user": user})
        outcome = self.outputs.pop(0) if self.outputs else GOOD_OUTPUT
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


GOOD_OUTPUT = {
    "conditions": [
        {"source": "$f(x)=x^{3}+ax+2$", "content": "$f(x)=x^{3}+ax+2$", "type": "algebra",
         "type_hint": "parametric cubic function", "facet": "form"},
        {"source": "存在3个零点", "content": "$f(x)$ 存在 3 个零点", "type": "algebra",
         "type_hint": "number of zeros", "facet": "qual"},
    ],
    "asks": [
        {"source": "$a$的取值范围", "content": "求 $a$ 的取值范围", "type": "ask",
         "type_hint": "find range", "depends_on": [0, 1]},
    ],
}


@pytest.fixture
def fake_ai(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(ai_provider_module, "get_ai_provider", lambda name: fake)
    return fake


@pytest.fixture
async def ctx(db_session, grant_role):
    editor = User(username="s_editor", full_name="Editor", hashed_password="x", is_active=True)
    viewer = User(username="s_viewer", full_name="Viewer", hashed_password="x", is_active=True)
    manager = User(username="s_manager", full_name="Manager", hashed_password="x", is_active=True)
    subject = Subject(name="数学", slug="math-structure")
    db_session.add_all([editor, viewer, manager, subject])
    await db_session.commit()
    await grant_role(editor, subject, SubjectRole.EDITOR)
    await grant_role(viewer, subject, SubjectRole.VIEWER)
    await grant_role(manager, subject, SubjectRole.MANAGER)
    for user in (editor, viewer, manager):
        user.last_active_subject_id = subject.id
    provider = AIProvider(name="global", interface_type="openai", api_key=encrypt_secret("sk-x"))
    model = AIModel(provider=provider, name="chat")
    db_session.add_all([provider, model])
    await db_session.flush()
    db_session.add(SystemSetting(key="AI_TEXT_MODEL_ID", value=str(model.id)))
    await db_session.commit()
    return {"editor": editor, "viewer": viewer, "manager": manager, "subject": subject, "provider": provider}


async def _question(client, ctx, content=CUBIC_DOC, **extra):
    payload = {"content": content, "q_type": "free_response", "subject_id": ctx["subject"].id, **extra}
    response = await client.post(f"{API}/questions", json=payload, headers=_auth(ctx["editor"]))
    assert response.status_code == 200, response.text
    return response.json()


async def _run_jobs(db):
    """像 worker 一样用独立会话把排队的 job 全部执行完(失败路径的回滚不影响测试会话里的对象)。"""
    maker = async_sessionmaker(bind=db.bind, class_=AsyncSession, expire_on_commit=False)
    async with maker() as worker_db:
        while (job := await job_service.claim_next(worker_db, use_row_lock=False)) is not None:
            await run_job(worker_db, job, cancel_poll_seconds=None)


async def _decompose(client, db, ctx, question_id):
    response = await client.post(
        f"{API}/structure/decompose", json={"target_ids": [question_id]}, headers=_auth(ctx["editor"])
    )
    assert response.status_code == 200, response.text
    await _run_jobs(db)
    view = await client.get(f"{API}/structure/targets/question/{question_id}", headers=_auth(ctx["editor"]))
    assert view.status_code == 200, view.text
    return view.json()


async def _types(client, ctx):
    response = await client.get(
        f"{API}/structure/types", params={"subject_id": ctx["subject"].id}, headers=_auth(ctx["editor"])
    )
    assert response.status_code == 200, response.text
    return {t["code"]: t for t in response.json()["items"]}


# --------------------------------------------------------------------------- #
# 类型树
# --------------------------------------------------------------------------- #
async def test_math_subject_gets_domain_roots_and_types_can_grow(client, ctx):
    types = await _types(client, ctx)
    assert set(types) == {"algebra", "geometry", "statistics", "ask", "method"}
    assert types["ask"]["kind"] == "ask" and types["algebra"]["parent_id"] is None
    assert types["method"]["kind"] == "method" and types["method"]["weight"] == 1

    created = await client.post(
        f"{API}/structure/types",
        json={"subject_id": ctx["subject"].id, "name": "Cubic function", "parent_id": types["algebra"]["id"]},
        headers=_auth(ctx["editor"]),
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["code"] == "cubic_function" and body["kind"] == "condition"

    # 设问类型不能挂到条件类型下面
    wrong = await client.patch(
        f"{API}/structure/types/{body['id']}", json={"parent_id": types["ask"]["id"]}, headers=_auth(ctx["editor"])
    )
    assert wrong.status_code == 400 and wrong.json()["code"] == "structure.type_invalid_parent"

    exported = (await client.get(
        f"{API}/structure/types/export", params={"subject_id": ctx["subject"].id}, headers=_auth(ctx["editor"])
    )).json()
    codes = [e["code"] for e in exported]
    # 导出时父节点一定排在子节点前面,导入时才能逐个解析父节点。
    assert codes.index("algebra") < codes.index("cubic_function")
    assert exported[codes.index("cubic_function")]["parent_code"] == "algebra"


async def test_viewer_cannot_change_types(client, ctx):
    types = await _types(client, ctx)
    response = await client.post(
        f"{API}/structure/types",
        json={"subject_id": ctx["subject"].id, "name": "x", "parent_id": types["algebra"]["id"]},
        headers=_auth(ctx["viewer"]),
    )
    assert response.status_code == 403


async def test_import_types_resolves_parents_in_any_order(client, ctx):
    await _types(client, ctx)
    response = await client.post(
        f"{API}/structure/types/import",
        json={"subject_id": ctx["subject"].id, "items": [
            {"code": "zeros", "name": "零点个数", "parent_code": "function"},
            {"code": "function", "name": "函数", "parent_code": "algebra"},
        ]},
        headers=_auth(ctx["editor"]),
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"created": 2, "updated": 0}
    types = await _types(client, ctx)
    assert types["zeros"]["parent_id"] == types["function"]["id"]


# --------------------------------------------------------------------------- #
# AI 拆解 job
# --------------------------------------------------------------------------- #
async def test_decompose_job_saves_a_checked_draft(client, db_session, ctx, fake_ai):
    question = await _question(client, ctx)
    view = await _decompose(client, db_session, ctx, question["id"])

    draft = view["draft"]
    assert view["accepted"] is None and view["job"] is None
    assert draft["origin"] == "ai" and draft["prompt_version"] == PROMPT_VERSION and draft["model"] == "chat"
    assert draft["stem_text"] == CUBIC
    assert [e["content"] for e in draft["elements"]] == ["$f(x)=x^{3}+ax+2$", "$f(x)$ 存在 3 个零点"]
    assert draft["elements"][0]["span"] == [CUBIC.index("$f"), CUBIC.index("存在")]
    assert draft["elements"][0]["type_path"] == ["代数"] and draft["elements"][0]["type_hint"] == "parametric cubic function"
    assert draft["asks"][0]["type_path"] == ["设问"]
    assert draft["asks"][0]["depends_on"] == [e["id"] for e in draft["elements"]]
    assert draft["check_errors"] == 0

    # 只给题干:提示词里带上了类型树,输入里没有答案
    assert "- algebra: 代数" in fake_ai.calls[0]["system"]
    assert CUBIC in fake_ai.calls[0]["user"]


async def test_check_errors_trigger_one_retry_with_feedback(client, db_session, ctx, fake_ai):
    missing_param = {"conditions": [{"source": "存在3个零点", "content": "有3个零点"}],
                     "asks": [{"source": "$a$的取值范围", "content": "求 $a$ 的取值范围", "depends_on": [0]}]}
    fake_ai.outputs = [missing_param, GOOD_OUTPUT]
    question = await _question(client, ctx)
    view = await _decompose(client, db_session, ctx, question["id"])

    assert len(fake_ai.calls) == 2
    assert "symbol `a`" in fake_ai.calls[1]["user"]
    assert view["draft"]["check_errors"] == 0 and len(view["draft"]["elements"]) == 2


async def test_missing_model_pauses_the_job(client, db_session, ctx, fake_ai):
    await db_session.execute(SystemSetting.__table__.delete())
    await db_session.commit()
    question = await _question(client, ctx)
    view = await _decompose(client, db_session, ctx, question["id"])
    assert view["job"]["status"] == "paused" and view["job"]["paused_reason"] == "model"
    assert fake_ai.calls == []


async def test_document_error_fails_only_that_job(client, db_session, ctx, fake_ai):
    fake_ai.outputs = [ValueError("not json")]
    question = await _question(client, ctx)
    await _decompose(client, db_session, ctx, question["id"])
    job = (await db_session.execute(select(Job).where(Job.target_id == question["id"]))).scalars().one()
    assert job.status == "failed" and '"error_code": "ai_document"' in job.progress


# --------------------------------------------------------------------------- #
# 审核、人工修改、过期
# --------------------------------------------------------------------------- #
async def test_review_accept_then_edit_question_marks_stale(client, db_session, ctx, fake_ai):
    question = await _question(client, ctx)
    draft = (await _decompose(client, db_session, ctx, question["id"]))["draft"]

    accepted = await client.post(
        f"{API}/structure/review", json={"run_ids": [draft["id"]], "action": "accept"}, headers=_auth(ctx["editor"])
    )
    assert accepted.json() == {"updated": [draft["id"]], "skipped": []}

    update = await client.put(
        f"{API}/questions/{question['id']}",
        json={"content": doc("已知函数", ("m", "f(x)=x^{3}+ax+5"), "存在3个零点，则", ("m", "a"), "的取值范围是（ ）")},
        headers=_auth(ctx["editor"]),
    )
    assert update.status_code == 200, update.text
    view = (await client.get(f"{API}/structure/targets/question/{question['id']}", headers=_auth(ctx["editor"]))).json()
    assert view["accepted"]["stale"] is True and view["draft"] is None

    listed = (await client.get(
        f"{API}/questions", params={"subject_id": ctx["subject"].id, "struct_state": "stale"}, headers=_auth(ctx["editor"])
    )).json()
    assert [q["id"] for q in listed["items"]] == [question["id"]]
    assert listed["items"][0]["struct_state"] == "stale"


async def test_human_edit_is_a_new_snapshot_and_can_be_accepted(client, db_session, ctx, fake_ai):
    question = await _question(client, ctx)
    ai_draft = (await _decompose(client, db_session, ctx, question["id"]))["draft"]
    types = await _types(client, ctx)

    saved = await client.post(f"{API}/structure/save", json={
        "target_id": question["id"],
        "base_run_id": ai_draft["id"],
        "elements": [
            {"content": "$f(x)=x^{3}+ax+2$", "source": "$f(x)=x^{3}+ax+2$", "type_id": types["algebra"]["id"]},
            {"content": "$f(x)$ 有 3 个零点", "source": "存在3个零点", "type_id": types["algebra"]["id"]},
        ],
        "asks": [{"content": "求 $a$ 的取值范围", "source": "$a$的取值范围", "type_id": types["ask"]["id"], "depends_on": [0, 1]}],
        "accept": True,
    }, headers=_auth(ctx["editor"]))
    assert saved.status_code == 200, saved.text
    view = saved.json()
    assert view["accepted"]["origin"] == "human" and view["draft"] is None
    runs = (await db_session.execute(select(StructRun).order_by(StructRun.id))).scalars().all()
    assert [r.state for r in runs] == ["superseded", "accepted"]

    viewer_save = await client.post(
        f"{API}/structure/save", json={"target_id": question["id"], "elements": [], "asks": []},
        headers=_auth(ctx["viewer"]),
    )
    assert viewer_save.status_code == 403


async def test_save_rejects_types_from_another_kind(client, ctx):
    question = await _question(client, ctx)
    types = await _types(client, ctx)
    response = await client.post(f"{API}/structure/save", json={
        "target_id": question["id"],
        "elements": [{"content": "x", "type_id": types["ask"]["id"]}],
    }, headers=_auth(ctx["editor"]))
    assert response.status_code == 400 and response.json()["code"] == "structure.type_not_found"


# --------------------------------------------------------------------------- #
# 检索、同结构题、统计、分布
# --------------------------------------------------------------------------- #
async def _accept_all(client, db_session, ctx, question_ids):
    for question_id in question_ids:
        draft = (await _decompose(client, db_session, ctx, question_id))["draft"]
        await client.post(
            f"{API}/structure/review", json={"run_ids": [draft["id"]], "action": "accept"}, headers=_auth(ctx["editor"])
        )


async def test_filter_similar_stats_and_distribution(client, db_session, ctx, fake_ai):
    first = await _question(client, ctx)
    second = await _question(
        client, ctx, content=doc("已知函数", ("m", "f(x)=x^{3}+ax+2"), "存在3个零点，则", ("m", "a"), "的取值范围为?"),
        allow_duplicate=True,
    )
    plain = await _question(client, ctx, content=doc("计算 1+1"), allow_duplicate=True)
    await _accept_all(client, db_session, ctx, [first["id"], second["id"]])
    types = await _types(client, ctx)

    by_type = (await client.get(
        f"{API}/questions",
        params={"subject_id": ctx["subject"].id, "struct_type_ids": [types["algebra"]["id"]]},
        headers=_auth(ctx["editor"]),
    )).json()
    assert {q["id"] for q in by_type["items"]} == {first["id"], second["id"]}
    none = (await client.get(
        f"{API}/questions", params={"subject_id": ctx["subject"].id, "struct_state": "none"}, headers=_auth(ctx["editor"])
    )).json()
    assert [q["id"] for q in none["items"]] == [plain["id"]]

    similar = (await client.get(
        f"{API}/structure/questions/{first['id']}/similar", headers=_auth(ctx["editor"])
    )).json()["items"]
    assert [s["question_id"] for s in similar] == [second["id"]] and similar[0]["score"] == 1.0
    same_source = (await client.get(
        f"{API}/structure/questions/{first['id']}/similar", params={"mode": "elements"}, headers=_auth(ctx["editor"])
    )).json()["items"]
    assert [s["question_id"] for s in same_source] == [second["id"]]
    assert same_source[0]["shared_count"] == 2 and same_source[0]["shared_elements"][0] == "$f(x)=x^{3}+ax+2$"

    stats = (await client.get(
        f"{API}/structure/stats", params={"subject_id": ctx["subject"].id}, headers=_auth(ctx["editor"])
    )).json()
    assert stats["total"] == 3 and stats["states"] == {"draft": 0, "accepted": 2, "stale": 0, "none": 1}
    assert stats["top_types"][0]["count"] == 2
    assert stats["origins"] == {"ai": 2, "human": 0, "agent": 0}

    distribution = (await client.post(
        f"{API}/structure/distribution", json={"question_ids": [first["id"], plain["id"]]}, headers=_auth(ctx["editor"])
    )).json()
    assert distribution["questions"] == 2 and distribution["structured"] == 1
    assert {d["name"]: d["count"] for d in distribution["domains"]} == {"代数": 1, "设问": 1}


async def test_review_queue_lists_drafts_with_errors_first(client, db_session, ctx, fake_ai):
    fake_ai.outputs = [GOOD_OUTPUT, {"conditions": [], "asks": [{"source": "$a$的取值范围", "content": "求 $a$"}]},
                       {"conditions": [], "asks": [{"source": "$a$的取值范围", "content": "求 $a$"}]}]
    clean = await _question(client, ctx)
    broken = await _question(
        client, ctx, content=doc("已知函数", ("m", "f(x)=x^{3}+ax+2"), "存在3个零点，则", ("m", "a"), "的取值范围为?"),
        allow_duplicate=True,
    )
    await _decompose(client, db_session, ctx, clean["id"])
    await _decompose(client, db_session, ctx, broken["id"])

    queue = (await client.get(
        f"{API}/structure/review-queue", params={"subject_id": ctx["subject"].id}, headers=_auth(ctx["editor"])
    )).json()
    assert [item["target_id"] for item in queue["items"]] == [broken["id"], clean["id"]]
    assert queue["items"][0]["check_errors"] > 0
    only_clean = (await client.get(
        f"{API}/structure/review-queue", params={"subject_id": ctx["subject"].id, "check": "clean"},
        headers=_auth(ctx["editor"]),
    )).json()
    assert [item["target_id"] for item in only_clean["items"]] == [clean["id"]]


# --------------------------------------------------------------------------- #
# 开关与自动入队
# --------------------------------------------------------------------------- #
async def test_auto_decompose_is_off_by_default_and_follows_subject_setting(client, db_session, ctx, fake_ai):
    await _question(client, ctx)
    assert (await db_session.execute(select(Job))).scalars().all() == []

    denied = await client.put(
        f"{API}/structure/subjects/{ctx['subject'].id}/settings", json={"auto_decompose": True},
        headers=_auth(ctx["editor"]),
    )
    assert denied.status_code == 403
    allowed = await client.put(
        f"{API}/structure/subjects/{ctx['subject'].id}/settings", json={"auto_decompose": True},
        headers=_auth(ctx["manager"]),
    )
    assert allowed.status_code == 200

    created = await _question(client, ctx, content=doc("计算 2+2"), allow_duplicate=True)
    jobs = (await db_session.execute(select(Job))).scalars().all()
    assert [(j.type, j.target_id, j.priority) for j in jobs] == [("structure.decompose", created["id"], 50)]


async def test_disabled_structure_rejects_new_decompositions(client, db_session, ctx):
    admin = User(username="s_admin", hashed_password="x", is_active=True, is_superuser=True)
    db_session.add(admin)
    await db_session.commit()
    # 非超级管理员:与其他超管接口一致返回 400 + auth.forbidden
    denied = await client.put(f"{API}/structure/settings", json={"enabled": False}, headers=_auth(ctx["editor"]))
    assert denied.status_code == 400 and denied.json()["code"] == "auth.forbidden"
    assert (await client.put(f"{API}/structure/settings", json={"enabled": False}, headers=_auth(admin))).status_code == 200

    question = await _question(client, ctx)
    response = await client.post(
        f"{API}/structure/decompose", json={"target_ids": [question["id"]]}, headers=_auth(ctx["editor"])
    )
    assert response.status_code == 403 and response.json()["code"] == "structure.disabled"


async def test_backfill_queues_undecomposed_questions_at_lowest_priority(client, db_session, ctx):
    first = await _question(client, ctx)
    second = await _question(client, ctx, content=doc("计算 3+3"), allow_duplicate=True)
    response = await client.post(
        f"{API}/structure/backfill", json={"subject_id": ctx["subject"].id}, headers=_auth(ctx["manager"])
    )
    assert response.json() == {"queued": 2}
    jobs = (await db_session.execute(select(Job).order_by(Job.target_id))).scalars().all()
    assert [(j.target_id, j.priority) for j in jobs] == [(first["id"], 10), (second["id"], 10)]
    again = await client.post(
        f"{API}/structure/backfill", json={"subject_id": ctx["subject"].id}, headers=_auth(ctx["manager"])
    )
    assert again.json() == {"queued": 0}


# --------------------------------------------------------------------------- #
# 材料共享
# --------------------------------------------------------------------------- #
async def test_sub_question_references_material_conditions(client, db_session, ctx, fake_ai):
    bundle = await client.post(
        f"{API}/subjects/{ctx['subject'].id}/stimuli/bundle",
        json={
            "content": doc("数列", ("m", "\\{a_n\\}"), "满足", ("m", "a_1=1")),
            "questions": [{"create": {"content": doc("(1) 求", ("m", "a_2")), "q_type": "free_response",
                                      "subject_id": ctx["subject"].id}}],
        },
        headers=_auth(ctx["editor"]),
    )
    assert bundle.status_code == 201, bundle.text
    stimulus_id = bundle.json()["id"]
    question = {"id": bundle.json()["questions"][0]["id"]}

    fake_ai.outputs = [
        {"conditions": [{"source": "$a_1=1$", "content": "$a_1=1$", "type": "algebra"}], "asks": []},
        {"conditions": [], "asks": [{"source": "求$a_2$", "content": "求 $a_2$", "type": "ask", "material_refs": [0]}]},
    ]
    view = await _decompose(client, db_session, ctx, question["id"])

    material = (await client.get(f"{API}/structure/targets/stimulus/{stimulus_id}", headers=_auth(ctx["editor"]))).json()
    shared = view["draft"]["elements"][0]
    assert shared["ref_element_id"] == material["draft"]["elements"][0]["id"]
    assert shared["shared_from_stimulus_id"] == stimulus_id and shared["span"] is None
    assert view["draft"]["asks"][0]["depends_on"] == [shared["id"]]
    assert view["draft"]["check_errors"] == 0
    assert "Shared material conditions" in fake_ai.calls[1]["user"]


# --------------------------------------------------------------------------- #
# 同源检索:条件内容签名
# --------------------------------------------------------------------------- #
def test_content_signature_ignores_formatting_differences():
    from app.services.structure.signature import content_signature

    assert content_signature("$f(x)=\\dfrac{1}{2}x$，") == content_signature("$f(x) = \\frac{1}{2} x$")
    assert content_signature("$a=1$") != content_signature("$a=2$")
    assert content_signature("  ") is None


async def test_signature_backfill_fills_missing_values(client, db_session, ctx, fake_ai):
    from app.models.question_structure import StructElement
    from app.services.structure.signature import backfill, content_signature

    question = await _question(client, ctx)
    await _decompose(client, db_session, ctx, question["id"])
    await db_session.execute(StructElement.__table__.update().values(content_sig=None))
    await db_session.commit()
    assert await backfill(db_session) == 2
    rows = (await db_session.execute(select(StructElement.content, StructElement.content_sig))).all()
    assert all(sig == content_signature(content) for content, sig in rows)
