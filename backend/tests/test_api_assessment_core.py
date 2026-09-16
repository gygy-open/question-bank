"""通用评测 (Assessment) 核心 API 的紧凑纵向测试。

覆盖第二切片核心链路:
- 组稿定稿 → 评测/投放的原子冻结 + 题目 provenance;
- 新 URL 生效、旧 Exam API 已下线;
- start grading;
- 追加式录分产生评分历史与默认判定;
- 乐观锁 stale revision 409;
- finalize:未完整评分拒绝、完整后接受、缺考排除;
- finalized 后写入拒绝;
- 跨学科 404;
- 权限矩阵;
- item 统计分母。

名册与状态流转的组稿构建走真实 API,评分/出勤边界用 db_session 直接注入。
"""
import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models.assessment import (
    AssessmentParticipation,
    AttendanceStatus,
    Classroom,
    ClassroomStudent,
    ResponseGrade,
    Student,
)
from app.models.question import Question, QuestionType
from app.models.subject import Subject
from app.models.subject_member import SubjectMember
from app.models.user import User

API = "/api/v1"


def _uid() -> str:
    return str(uuid.uuid4())


def _rich_doc(text: str) -> dict:
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


# --------------------------------------------------------------------------- #
# seed helpers
# --------------------------------------------------------------------------- #
async def _seed_user(db_session, *, username: str, is_superuser: bool = False) -> User:
    user = User(
        username=username, full_name=username, hashed_password="x",
        is_active=True, is_superuser=is_superuser,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _seed_subject(db_session, *, name="数学", slug="math") -> Subject:
    subject = Subject(name=name, slug=slug)
    db_session.add(subject)
    await db_session.commit()
    await db_session.refresh(subject)
    return subject


async def _grant(db_session, user, subject, role) -> None:
    db_session.add(SubjectMember(user_id=user.id, subject_id=subject.id, role=role))
    await db_session.commit()


async def _seed_question(db_session, *, subject_id: int, stem="1+1=?") -> Question:
    q = Question(
        content=json.dumps(_rich_doc(stem), ensure_ascii=False),
        options=[
            {"id": "opt_a", "label": "A", "content": _rich_doc("2")},
            {"id": "opt_b", "label": "B", "content": _rich_doc("3")},
        ],
        answer=json.dumps({"kind": "single_choice", "correct": "opt_a"}, ensure_ascii=False),
        analysis=json.dumps(_rich_doc("因为 1+1=2"), ensure_ascii=False),
        q_type=QuestionType.SINGLE_CHOICE,
        subject_id=subject_id,
        difficulty=3,
        source="seed",
        content_revision=1,
    )
    db_session.add(q)
    await db_session.commit()
    await db_session.refresh(q)
    return q


async def _seed_classroom(db_session, *, subject_id: int, name="一班", students=2) -> Classroom:
    classroom = Classroom(subject_id=subject_id, name=name)
    db_session.add(classroom)
    await db_session.commit()
    await db_session.refresh(classroom)
    for i in range(students):
        student = Student(subject_id=subject_id, student_no=f"{name}-{i:03d}", name=f"学生{i}")
        db_session.add(student)
        await db_session.commit()
        await db_session.refresh(student)
        db_session.add(ClassroomStudent(classroom_id=classroom.id, student_id=student.id))
    await db_session.commit()
    return classroom


async def _finalized_version(client, sid, headers, *, q_ids, scores, scope="shared"):
    r = await client.post(
        f"{API}/subjects/{sid}/compositions?scope={scope}",
        json={"title": "稿件"}, headers=headers,
    )
    assert r.status_code == 201, r.text
    comp = r.json()
    r = await client.patch(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope={scope}",
        json={"expected_revision": comp["revision"], "numbering_enabled": True, "scoring_enabled": True},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    comp = r.json()
    rev = comp["revision"]
    nodes = [
        {
            "id": _uid(), "node_kind": "block", "node_type": "question",
            "question_id": qid, "props": ({} if score is None else {"score": score}),
        }
        for qid, score in zip(q_ids, scores)
    ]
    r = await client.put(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/nodes?scope={scope}",
        json={"expected_revision": rev, "nodes": nodes}, headers=headers,
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/versions?scope={scope}",
        json={"expected_revision": rev + 1}, headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _create_assessment(client, sid, headers, *, version_id, classroom_id, title="期中评测"):
    r = await client.post(
        f"{API}/subjects/{sid}/assessments",
        json={"title": title, "composition_version_id": version_id, "classroom_id": classroom_id},
        headers=headers,
    )
    return r


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
async def ctx(db_session):
    admin = await _seed_user(db_session, username="admin", is_superuser=True)
    subject = await _seed_subject(db_session)
    subject2 = await _seed_subject(db_session, name="物理", slug="phys")
    editor = await _seed_user(db_session, username="editor")
    viewer = await _seed_user(db_session, username="viewer")
    manager = await _seed_user(db_session, username="manager")
    outsider = await _seed_user(db_session, username="outsider")
    for u, role in [(editor, "editor"), (viewer, "viewer"), (manager, "manager")]:
        await _grant(db_session, u, subject, role)
    await _grant(db_session, manager, subject2, "manager")
    return {
        "admin": admin, "subject": subject, "subject2": subject2,
        "editor": editor, "viewer": viewer, "manager": manager, "outsider": outsider,
    }


async def _make_session(client, ctx, db_session, *, students=2, scores=(40, 60), title="期中评测"):
    """建 shared 定稿 + 班级 + 评测,返回创建后的 SessionDetail。"""
    sid = ctx["subject"].id
    h = _auth(ctx["manager"])
    qs = [await _seed_question(db_session, subject_id=sid, stem=f"Q{i}") for i in range(len(scores))]
    classroom = await _seed_classroom(db_session, subject_id=sid, students=students)
    version = await _finalized_version(client, sid, h, q_ids=[q.id for q in qs], scores=list(scores))
    r = await _create_assessment(client, sid, h, version_id=version["id"], classroom_id=classroom.id, title=title)
    assert r.status_code == 201, r.text
    return sid, h, qs, version, r.json()


async def _grade_attempt(client, sid, headers, attempt, item_scores, *, expected_revision=None):
    body = {
        "expected_revision": attempt["revision"] if expected_revision is None else expected_revision,
        "items": [{"item_id": iid, "score": s} for iid, s in item_scores],
    }
    return await client.patch(
        f"{API}/subjects/{sid}/assessment-attempts/{attempt['attempt_id']}/grades",
        json=body, headers=headers,
    )


# --------------------------------------------------------------------------- #
# 原子创建 + provenance + 新旧 URL
# --------------------------------------------------------------------------- #
async def test_create_freezes_session_with_provenance(client, ctx, db_session):
    sid, h, qs, version, session = await _make_session(client, ctx, db_session, scores=(40, 60))
    assert session["grading_status"] == "not_started"
    assert session["delivery_status"] == "closed"
    assert Decimal(session["total_score"]) == Decimal("100")
    assert session["item_count"] == 2
    assert len(session["participants"]) == 2
    # provenance:条目冻结 source_question_id / revision,且不泄漏 scoring_spec 私有字段。
    src_ids = {item["source_question_id"] for item in session["items"]}
    assert src_ids == {q.id for q in qs}
    for item in session["items"]:
        assert "scoring_spec" not in item
        assert item["source_question_revision"] is not None
    # 每个参与者一个 offline attempt。
    for p in session["participants"]:
        assert len(p["attempts"]) == 1
        assert p["attempts"][0]["mode"] == "offline"


async def test_old_exam_api_is_gone(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["manager"])
    r = await client.get(f"{API}/subjects/{sid}/exam-sessions", headers=h)
    assert r.status_code == 404


async def test_new_session_urls_resolve(client, ctx, db_session):
    sid, h, qs, version, session = await _make_session(client, ctx, db_session)
    r = await client.get(f"{API}/subjects/{sid}/assessment-sessions", headers=h)
    assert r.status_code == 200 and len(r.json()) == 1
    r = await client.get(f"{API}/subjects/{sid}/assessment-sessions/{session['id']}", headers=h)
    assert r.status_code == 200 and r.json()["id"] == session["id"]
    r = await client.get(f"{API}/subjects/{sid}/assessments/{session['assessment_id']}", headers=h)
    assert r.status_code == 200
    assert len(r.json()["current_items"]) == 2


async def test_session_read_exposes_assessment_identity(client, ctx, db_session):
    """列表投影与详情都携带 assessment_id / assessment_title,便于列表直接展示。"""
    sid, h, qs, version, session = await _make_session(client, ctx, db_session, title="期中评测")
    # 列表投影
    r = await client.get(f"{API}/subjects/{sid}/assessment-sessions", headers=h)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["assessment_id"] == session["assessment_id"]
    assert row["assessment_title"] == "期中评测"
    # 详情投影
    r = await client.get(f"{API}/subjects/{sid}/assessment-sessions/{session['id']}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["assessment_title"] == "期中评测"


async def test_gradebook_row_exposes_participation_status(client, ctx, db_session):
    """gradebook 行投影携带 participation_status,前端据此禁编辑已退出者。"""
    sid, h, qs, version, session = await _make_session(client, ctx, db_session, students=2)
    await client.post(f"{API}/subjects/{sid}/assessment-sessions/{session['id']}/grading/start", headers=h)
    # 将第二名参与者标记为已退出。
    p1_id = session["participants"][1]["id"]
    part = await db_session.get(AssessmentParticipation, p1_id)
    part.status = "withdrawn"
    await db_session.commit()

    r = await client.get(
        f"{API}/subjects/{sid}/assessment-sessions/{session['id']}/gradebook", headers=h
    )
    assert r.status_code == 200, r.text
    rows = {row["participation_id"]: row for row in r.json()["participants"]}
    assert rows[session["participants"][0]["id"]]["participation_status"] == "active"
    assert rows[p1_id]["participation_status"] == "withdrawn"


# --------------------------------------------------------------------------- #
# 组稿约束
# --------------------------------------------------------------------------- #
async def test_personal_version_rejected(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["manager"])
    q = await _seed_question(db_session, subject_id=sid)
    classroom = await _seed_classroom(db_session, subject_id=sid, students=1)
    version = await _finalized_version(client, sid, h, q_ids=[q.id], scores=[10], scope="personal")
    r = await _create_assessment(client, sid, h, version_id=version["id"], classroom_id=classroom.id)
    assert r.status_code == 400


async def test_cross_subject_version_rejected(client, ctx, db_session):
    sid = ctx["subject"].id
    sid2 = ctx["subject2"].id
    h = _auth(ctx["manager"])
    q2 = await _seed_question(db_session, subject_id=sid2)
    version = await _finalized_version(client, sid2, h, q_ids=[q2.id], scores=[10])
    classroom = await _seed_classroom(db_session, subject_id=sid, students=1)
    r = await _create_assessment(client, sid, h, version_id=version["id"], classroom_id=classroom.id)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# start grading + 追加式录分
# --------------------------------------------------------------------------- #
async def test_start_grading(client, ctx, db_session):
    sid, h, qs, version, session = await _make_session(client, ctx, db_session)
    r = await client.post(
        f"{API}/subjects/{sid}/assessment-sessions/{session['id']}/grading/start", headers=h
    )
    assert r.status_code == 200
    assert r.json()["grading_status"] == "in_progress"


async def test_append_grade_creates_history_and_default_outcome(client, ctx, db_session):
    sid, h, qs, version, session = await _make_session(client, ctx, db_session, scores=(40, 60))
    await client.post(f"{API}/subjects/{sid}/assessment-sessions/{session['id']}/grading/start", headers=h)
    items = session["items"]
    attempt = session["participants"][0]["attempts"][0]

    # 满分 → correct;部分 → partial。
    r = await _grade_attempt(client, sid, h, attempt, [(items[0]["id"], 40), (items[1]["id"], 30)])
    assert r.status_code == 200, r.text
    body = r.json()
    outcomes = {g["item_id"]: g["outcome"] for g in body["grades"]}
    assert outcomes[items[0]["id"]] == "correct"
    assert outcomes[items[1]["id"]] == "partial"
    assert Decimal(body["total_score"]) == Decimal("70")
    assert body["revision"] == attempt["revision"] + 1

    # 再次改分:追加历史,不 UPDATE 旧行。
    r2 = await _grade_attempt(
        client, sid, h, attempt, [(items[1]["id"], 60)], expected_revision=body["revision"]
    )
    assert r2.status_code == 200, r2.text
    assert Decimal(r2.json()["total_score"]) == Decimal("100")
    grade_count = await db_session.scalar(select(func.count()).select_from(ResponseGrade))
    assert grade_count == 3  # item0 一次 + item1 两次


async def test_stale_revision_conflict(client, ctx, db_session):
    sid, h, qs, version, session = await _make_session(client, ctx, db_session)
    await client.post(f"{API}/subjects/{sid}/assessment-sessions/{session['id']}/grading/start", headers=h)
    items = session["items"]
    attempt = session["participants"][0]["attempts"][0]
    r = await _grade_attempt(client, sid, h, attempt, [(items[0]["id"], 40)])
    assert r.status_code == 200
    # 用过期的 revision 再写 → 409。
    r2 = await _grade_attempt(client, sid, h, attempt, [(items[1]["id"], 60)], expected_revision=attempt["revision"])
    assert r2.status_code == 409


# --------------------------------------------------------------------------- #
# finalize:完整性 + 缺考排除 + 定稿只读
# --------------------------------------------------------------------------- #
async def test_finalize_rejects_incomplete_then_accepts(client, ctx, db_session):
    sid, h, qs, version, session = await _make_session(client, ctx, db_session, scores=(40, 60))
    await client.post(f"{API}/subjects/{sid}/assessment-sessions/{session['id']}/grading/start", headers=h)
    items = session["items"]
    a0 = session["participants"][0]["attempts"][0]
    a1 = session["participants"][1]["attempts"][0]

    # 只评了第一个学生 → 定稿被拒。
    await _grade_attempt(client, sid, h, a0, [(items[0]["id"], 40), (items[1]["id"], 60)])
    r = await client.post(
        f"{API}/subjects/{sid}/assessment-sessions/{session['id']}/grading/finalize", headers=h
    )
    assert r.status_code == 409

    # 补齐第二个学生 → 接受。
    await _grade_attempt(client, sid, h, a1, [(items[0]["id"], 20), (items[1]["id"], 10)])
    r = await client.post(
        f"{API}/subjects/{sid}/assessment-sessions/{session['id']}/grading/finalize", headers=h
    )
    assert r.status_code == 200
    assert r.json()["grading_status"] == "finalized"

    # 定稿后写入被拒。
    r = await _grade_attempt(client, sid, h, a0, [(items[0]["id"], 10)], expected_revision=99)
    assert r.status_code == 409


async def test_finalize_excludes_absent(client, ctx, db_session):
    sid, h, qs, version, session = await _make_session(client, ctx, db_session, students=2, scores=(40, 60))
    await client.post(f"{API}/subjects/{sid}/assessment-sessions/{session['id']}/grading/start", headers=h)
    items = session["items"]
    a0 = session["participants"][0]["attempts"][0]
    p1_id = session["participants"][1]["id"]

    # 第二个学生缺考 → 不要求评分。
    part = await db_session.get(AssessmentParticipation, p1_id)
    part.attendance_status = AttendanceStatus.ABSENT.value
    await db_session.commit()

    await _grade_attempt(client, sid, h, a0, [(items[0]["id"], 40), (items[1]["id"], 60)])
    r = await client.post(
        f"{API}/subjects/{sid}/assessment-sessions/{session['id']}/grading/finalize", headers=h
    )
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- #
# 跨学科 404
# --------------------------------------------------------------------------- #
async def test_cross_subject_session_404(client, ctx, db_session):
    sid, h, qs, version, session = await _make_session(client, ctx, db_session)
    sid2 = ctx["subject2"].id
    hm2 = _auth(ctx["manager"])  # manager 同时是 subject2 的 manager
    r = await client.get(f"{API}/subjects/{sid2}/assessment-sessions/{session['id']}", headers=hm2)
    assert r.status_code == 404
    r = await client.get(f"{API}/subjects/{sid2}/assessment-sessions/{session['id']}/gradebook", headers=hm2)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# 权限矩阵
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("actor,expected", [("manager", 201), ("editor", 403), ("viewer", 403)])
async def test_create_permission_matrix(client, ctx, db_session, actor, expected):
    sid = ctx["subject"].id
    q = await _seed_question(db_session, subject_id=sid)
    classroom = await _seed_classroom(db_session, subject_id=sid, students=1)
    version = await _finalized_version(client, sid, _auth(ctx["manager"]), q_ids=[q.id], scores=[10])
    r = await _create_assessment(
        client, sid, _auth(ctx[actor]), version_id=version["id"], classroom_id=classroom.id
    )
    assert r.status_code == expected


async def test_grading_permission_matrix(client, ctx, db_session):
    sid, h, qs, version, session = await _make_session(client, ctx, db_session)
    await client.post(f"{API}/subjects/{sid}/assessment-sessions/{session['id']}/grading/start", headers=h)
    items = session["items"]
    attempt = session["participants"][0]["attempts"][0]

    # viewer 角色仅有 VIEW_QUESTION,无 VIEW_ASSESSMENT/EDIT_SCORE:录分与看册均 403。
    r = await _grade_attempt(client, sid, _auth(ctx["viewer"]), attempt, [(items[0]["id"], 10)])
    assert r.status_code == 403
    r = await client.get(
        f"{API}/subjects/{sid}/assessment-sessions/{session['id']}/gradebook", headers=_auth(ctx["viewer"])
    )
    assert r.status_code == 403
    # editor:可录分、可看册。
    r = await _grade_attempt(client, sid, _auth(ctx["editor"]), attempt, [(items[0]["id"], 10)])
    assert r.status_code == 200
    r = await client.get(
        f"{API}/subjects/{sid}/assessment-sessions/{session['id']}/gradebook", headers=_auth(ctx["editor"])
    )
    assert r.status_code == 200
    # outsider:无成员身份,读 gradebook 403。
    r = await client.get(
        f"{API}/subjects/{sid}/assessment-sessions/{session['id']}/gradebook", headers=_auth(ctx["outsider"])
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# item 统计分母
# --------------------------------------------------------------------------- #
async def test_item_statistics_denominator(client, ctx, db_session):
    sid, h, qs, version, session = await _make_session(client, ctx, db_session, students=3, scores=(40, 60))
    await client.post(f"{API}/subjects/{sid}/assessment-sessions/{session['id']}/grading/start", headers=h)
    items = session["items"]
    a0 = session["participants"][0]["attempts"][0]
    a1 = session["participants"][1]["attempts"][0]
    p2_id = session["participants"][2]["id"]

    # 前两名评分,第三名缺考(排除出分母)。
    await _grade_attempt(client, sid, h, a0, [(items[0]["id"], 40), (items[1]["id"], 60)])
    await _grade_attempt(client, sid, h, a1, [(items[0]["id"], 0), (items[1]["id"], 30)])
    part = await db_session.get(AssessmentParticipation, p2_id)
    part.attendance_status = AttendanceStatus.ABSENT.value
    await db_session.commit()

    r = await client.get(
        f"{API}/subjects/{sid}/assessment-sessions/{session['id']}/item-statistics", headers=h
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["participation_count"] == 2  # 缺考排除
    stat0 = next(s for s in body["items"] if s["item_id"] == items[0]["id"])
    assert stat0["graded_count"] == 2
    assert stat0["full_marks_count"] == 1  # 40 满分一人,0 分一人
    assert stat0["incorrect_count"] == 1
    assert Decimal(stat0["error_rate"]) == Decimal("0.5000")
