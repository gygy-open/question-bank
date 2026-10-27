"""Dashboard 统计口径:学科隔离、软删除、私有题可见性、权限与趋势补零。"""
import json
from datetime import datetime, timedelta

import pytest

from app.core.security import create_access_token
from app.models.activity_log import ActivityLog
from app.models.knowledge_point import KnowledgePoint
from app.models.question import Question, QuestionType, QuestionVisibility
from app.models.subject import Subject
from app.models.subject_member import SubjectMember
from app.models.user import User

API = "/api/v1"
_DOC = json.dumps({"type": "doc", "content": [{"type": "paragraph"}]})


def _auth(user: User) -> dict:
    return {"Authorization": "Bearer " + create_access_token(user.id)}


async def _add(db, obj):
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@pytest.fixture
async def ctx(db_session):
    db = db_session
    math = await _add(db, Subject(name="数学", slug="math"))
    phys = await _add(db, Subject(name="物理", slug="phys"))
    editor = await _add(db, User(username="editor", full_name="Ed", hashed_password="x", is_active=True))
    other = await _add(db, User(username="other", hashed_password="x", is_active=True))
    outsider = await _add(db, User(username="outsider", hashed_password="x", is_active=True))
    for u in (editor, other):
        db.add(SubjectMember(user_id=u.id, subject_id=math.id, role="editor"))
    await db.commit()

    kp_a = await _add(db, KnowledgePoint(name="函数", slug="fn", subject_id=math.id))
    kp_b = await _add(db, KnowledgePoint(name="几何", slug="geo", subject_id=math.id))

    def q(**kw):
        base = dict(content=_DOC, q_type=QuestionType.SINGLE_CHOICE, subject_id=math.id,
                    created_by=editor.id, difficulty=2, status="draft")
        base.update(kw)
        return Question(**base)

    now = datetime.utcnow()
    q1 = await _add(db, q(status="published", created_at=now - timedelta(days=60)))
    await _add(db, q(q_type=QuestionType.FREE_RESPONSE, status="pending", difficulty=5))
    await _add(db, q(status="draft", created_by=other.id, created_at=now - timedelta(days=2)))
    # 别人的私有题:editor 不应计入。
    await _add(db, q(created_by=other.id, visibility=QuestionVisibility.PRIVATE.value))
    # 软删除:不计入。
    await _add(db, q(deleted_at=now))
    # 其他学科:不计入。
    await _add(db, q(subject_id=phys.id))

    await db.refresh(q1, ["knowledge_points"])
    q1.knowledge_points.append(kp_a)
    db.add(ActivityLog(user_id=other.id, action="review", resource_type="question", resource_id=q1.id))
    await db.commit()
    return {"math": math, "phys": phys, "editor": editor, "other": other,
            "outsider": outsider, "kp_a": kp_a, "kp_b": kp_b}


async def test_stats_scope_and_visibility(client, ctx):
    r = await client.get(f"{API}/dashboard/stats", params={"subject_id": ctx["math"].id},
                         headers=_auth(ctx["editor"]))
    assert r.status_code == 200, r.text
    data = r.json()
    ov = data["overview"]
    assert ov["total_questions"] == 3
    assert ov["new_questions_7d"] == 2
    assert ov["published"] == 1
    assert ov["pending"] == 1
    assert ov["knowledge_points"] == 2

    dist = data["distribution"]
    q_type = {i["key"]: i["count"] for i in dist["q_type"]}
    assert q_type["single_choice"] == 2 and q_type["free_response"] == 1
    assert [i["key"] for i in dist["difficulty"]] == ["1", "2", "3", "4", "5"]
    assert {i["key"]: i["count"] for i in dist["difficulty"]}["5"] == 1
    assert {i["key"]: i["count"] for i in dist["visibility"]}["private"] == 0

    kc = data["knowledge_coverage"]
    assert kc["total"] == 2 and kc["covered"] == 1
    assert kc["top"] == [{"id": ctx["kp_a"].id, "name": "函数", "count": 1}]
    assert [k["id"] for k in kc["uncovered"]] == [ctx["kp_b"].id]
    assert kc["questions_without_kp"] == 2
    assert kc["questions_without_tag"] == 3

    trend = data["trend"]
    assert len(trend) == 30
    assert trend[0]["total"] == 1  # 60 天前那道题作为基线
    assert trend[-1]["total"] == 3
    assert sum(p["created"] for p in trend) == 2


async def test_private_visible_to_creator(client, ctx):
    r = await client.get(f"{API}/dashboard/stats", params={"subject_id": ctx["math"].id},
                         headers=_auth(ctx["other"]))
    assert r.status_code == 200, r.text
    assert r.json()["overview"]["total_questions"] == 4


async def test_outsider_forbidden(client, ctx):
    for path in ("stats", "contributors"):
        r = await client.get(f"{API}/dashboard/{path}", params={"subject_id": ctx["math"].id},
                             headers=_auth(ctx["outsider"]))
        assert r.status_code == 403, r.text


async def test_contributors(client, ctx):
    r = await client.get(f"{API}/dashboard/contributors",
                         params={"subject_id": ctx["math"].id, "days": 30},
                         headers=_auth(ctx["editor"]))
    assert r.status_code == 200, r.text
    items = {i["username"]: i for i in r.json()["items"]}
    # editor: 近 30 天建了 1 道可见题(60 天前的不算);other: 1 道公开题 + 1 次审核(私有题对 editor 不可见)。
    assert items["editor"]["created"] == 1 and items["editor"]["reviewed"] == 0
    assert items["other"]["created"] == 1 and items["other"]["reviewed"] == 1

    r = await client.get(f"{API}/dashboard/contributors",
                         params={"subject_id": ctx["math"].id, "days": 90},
                         headers=_auth(ctx["editor"]))
    assert {i["username"]: i for i in r.json()["items"]}["editor"]["created"] == 2
