"""成绩录入第一条纵向切片的聚焦测试:从组稿定稿创建考试。

覆盖:
- 成功创建(题目清单 + 参与者快照冻结、总分、事件)
- personal 组稿版本拒绝
- 未启用赋分 / 缺分 拒绝
- 跨学科(version / classroom)拒绝 → 404
- 权限矩阵(viewer/editor/manager/admin/outsider)
- 快照稳定性(定稿后改题库不影响已建考试)
- 原子回滚(事件写入失败时全回滚)
"""
import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models.assessment import (
    Classroom,
    ClassroomStudent,
    ExamParticipant,
    ExamQuestion,
    ExamResult,
    ExamSession,
    Student,
)
from app.models.composition import CompositionVersion
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


async def _seed_full_question(db_session, *, subject_id: int, stem="1+1=?", content_revision=1) -> Question:
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
        content_revision=content_revision,
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
        student = Student(
            subject_id=subject_id,
            student_no=f"{name}-{i:03d}",
            name=f"学生{i}",
        )
        db_session.add(student)
        await db_session.commit()
        await db_session.refresh(student)
        db_session.add(ClassroomStudent(classroom_id=classroom.id, student_id=student.id))
    await db_session.commit()
    return classroom


# --------------------------------------------------------------------------- #
# 通过 API 组稿 → 定稿,产出一个 shared/personal 的定稿版本
# --------------------------------------------------------------------------- #
async def _create_composition(client, sid, headers, *, scope="shared", scoring=True, with_score=True):
    r = await client.post(
        f"{API}/subjects/{sid}/compositions?scope={scope}",
        json={"title": "稿件"}, headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _enable_scoring(client, sid, comp, headers, *, scope="shared"):
    r = await client.patch(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope={scope}",
        json={"expected_revision": comp["revision"], "numbering_enabled": True, "scoring_enabled": True},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _put_question_nodes(client, sid, comp_id, headers, *, expected_revision, q_ids, scores, scope="shared"):
    nodes = []
    for qid, score in zip(q_ids, scores):
        props = {} if score is None else {"score": score}
        nodes.append({
            "id": _uid(), "node_kind": "block", "node_type": "question",
            "question_id": qid, "props": props,
        })
    r = await client.put(
        f"{API}/subjects/{sid}/compositions/{comp_id}/nodes?scope={scope}",
        json={"expected_revision": expected_revision, "nodes": nodes},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _finalize(client, sid, comp_id, headers, *, expected_revision, scope="shared"):
    r = await client.post(
        f"{API}/subjects/{sid}/compositions/{comp_id}/versions?scope={scope}",
        json={"expected_revision": expected_revision}, headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _finalized_version(
    client, sid, headers, *, q_ids, scores, scope="shared", scoring=True
):
    """组稿 → (可选开赋分) → 放题 → 定稿,返回定稿版本 json。"""
    comp = await _create_composition(client, sid, headers, scope=scope)
    rev = comp["revision"]
    if scoring:
        comp = await _enable_scoring(client, sid, comp, headers, scope=scope)
        rev = comp["revision"]
    await _put_question_nodes(
        client, sid, comp["id"], headers, expected_revision=rev, q_ids=q_ids, scores=scores, scope=scope
    )
    return await _finalize(client, sid, comp["id"], headers, expected_revision=rev + 1, scope=scope)


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
    # manager 也管另一学科,便于跨学科用例定位到 404 而非 403。
    await _grant(db_session, manager, subject2, "manager")

    return {
        "admin": admin, "subject": subject, "subject2": subject2,
        "editor": editor, "viewer": viewer, "manager": manager, "outsider": outsider,
    }


# --------------------------------------------------------------------------- #
# 成功创建
# --------------------------------------------------------------------------- #
async def test_create_exam_session_success(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["manager"])
    q1 = await _seed_full_question(db_session, subject_id=sid, stem="Q1")
    q2 = await _seed_full_question(db_session, subject_id=sid, stem="Q2")
    classroom = await _seed_classroom(db_session, subject_id=sid, students=3)

    version = await _finalized_version(client, sid, h, q_ids=[q1.id, q2.id], scores=[40, 60])

    r = await client.post(
        f"{API}/subjects/{sid}/exam-sessions",
        json={"composition_version_id": version["id"], "classroom_id": classroom.id, "name": "期中考"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["name"] == "期中考"
    assert data["status"] == "draft"
    assert Decimal(str(data["total_score"])) == Decimal("100")
    assert data["composition_version_id"] == version["id"]
    assert data["classroom_id"] == classroom.id

    # 题目清单:两题,分值与顺序冻结。
    questions = data["questions"]
    assert len(questions) == 2
    assert [Decimal(str(q["max_score"])) for q in questions] == [Decimal("40"), Decimal("60")]
    assert [q["position"] for q in questions] == [0, 1]
    assert all(q["q_type"] == "single_choice" for q in questions)

    # 参与者快照:三名学生冻结姓名/学号。
    participants = data["participants"]
    assert len(participants) == 3
    assert {p["student_no"] for p in participants} == {"一班-000", "一班-001", "一班-002"}

    # 每个参与者一条 ExamResult;一条 created 事件。
    result_count = await db_session.scalar(
        select(func.count()).select_from(ExamResult).where(ExamResult.exam_session_id == data["id"])
    )
    assert result_count == 3
    for res in (await db_session.execute(select(ExamResult).where(ExamResult.exam_session_id == data["id"]))).scalars():
        assert res.revision == 1

    # GET 详情可复现题目与参与者。
    g = await client.get(f"{API}/subjects/{sid}/exam-sessions/{data['id']}", headers=h)
    assert g.status_code == 200, g.text
    assert len(g.json()["questions"]) == 2
    assert len(g.json()["participants"]) == 3


# --------------------------------------------------------------------------- #
# personal 组稿版本拒绝
# --------------------------------------------------------------------------- #
async def test_personal_version_rejected(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["manager"])
    q = await _seed_full_question(db_session, subject_id=sid)
    classroom = await _seed_classroom(db_session, subject_id=sid)

    version = await _finalized_version(client, sid, h, q_ids=[q.id], scores=[100], scope="personal")

    r = await client.post(
        f"{API}/subjects/{sid}/exam-sessions",
        json={"composition_version_id": version["id"], "classroom_id": classroom.id, "name": "考"},
        headers=h,
    )
    assert r.status_code == 400, r.text


# --------------------------------------------------------------------------- #
# 未启用赋分 / 缺分 拒绝
# --------------------------------------------------------------------------- #
async def test_scoring_disabled_rejected(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["manager"])
    q = await _seed_full_question(db_session, subject_id=sid)
    classroom = await _seed_classroom(db_session, subject_id=sid)

    # scoring=False:不开赋分定稿。
    version = await _finalized_version(client, sid, h, q_ids=[q.id], scores=[None], scoring=False)

    r = await client.post(
        f"{API}/subjects/{sid}/exam-sessions",
        json={"composition_version_id": version["id"], "classroom_id": classroom.id, "name": "考"},
        headers=h,
    )
    assert r.status_code == 400, r.text


async def test_missing_question_score_rejected(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["manager"])
    q1 = await _seed_full_question(db_session, subject_id=sid, stem="Q1")
    q2 = await _seed_full_question(db_session, subject_id=sid, stem="Q2")
    classroom = await _seed_classroom(db_session, subject_id=sid)

    # 开赋分但第二题不给分。
    version = await _finalized_version(client, sid, h, q_ids=[q1.id, q2.id], scores=[50, None])

    r = await client.post(
        f"{API}/subjects/{sid}/exam-sessions",
        json={"composition_version_id": version["id"], "classroom_id": classroom.id, "name": "考"},
        headers=h,
    )
    assert r.status_code == 400, r.text


# --------------------------------------------------------------------------- #
# 跨学科拒绝 → 404(防枚举)
# --------------------------------------------------------------------------- #
async def test_cross_subject_version_rejected(client, ctx, db_session):
    sid = ctx["subject"].id
    sid2 = ctx["subject2"].id
    h = _auth(ctx["manager"])
    q = await _seed_full_question(db_session, subject_id=sid)
    classroom = await _seed_classroom(db_session, subject_id=sid2)

    # version 属于 subject,classroom 属于 subject2;从 subject2 路由创建 → version 不可见。
    version = await _finalized_version(client, sid, h, q_ids=[q.id], scores=[100])

    r = await client.post(
        f"{API}/subjects/{sid2}/exam-sessions",
        json={"composition_version_id": version["id"], "classroom_id": classroom.id, "name": "考"},
        headers=h,
    )
    assert r.status_code == 404, r.text


async def test_cross_subject_classroom_rejected(client, ctx, db_session):
    sid = ctx["subject"].id
    sid2 = ctx["subject2"].id
    h = _auth(ctx["manager"])
    q = await _seed_full_question(db_session, subject_id=sid)
    classroom_other = await _seed_classroom(db_session, subject_id=sid2)

    version = await _finalized_version(client, sid, h, q_ids=[q.id], scores=[100])

    r = await client.post(
        f"{API}/subjects/{sid}/exam-sessions",
        json={"composition_version_id": version["id"], "classroom_id": classroom_other.id, "name": "考"},
        headers=h,
    )
    assert r.status_code == 404, r.text


# --------------------------------------------------------------------------- #
# 权限矩阵
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "actor, expected",
    [("manager", 201), ("admin", 201), ("editor", 403), ("viewer", 403), ("outsider", 403)],
)
async def test_create_permission_matrix(client, ctx, db_session, actor, expected):
    sid = ctx["subject"].id
    # 用 manager 组稿定稿(需 EDIT_QUESTION),再以各角色尝试创建考试。
    hm = _auth(ctx["manager"])
    q = await _seed_full_question(db_session, subject_id=sid)
    classroom = await _seed_classroom(db_session, subject_id=sid)
    version = await _finalized_version(client, sid, hm, q_ids=[q.id], scores=[100])

    r = await client.post(
        f"{API}/subjects/{sid}/exam-sessions",
        json={"composition_version_id": version["id"], "classroom_id": classroom.id, "name": "考"},
        headers=_auth(ctx[actor]),
    )
    assert r.status_code == expected, r.text


@pytest.mark.parametrize(
    "actor, expected",
    [("manager", 200), ("admin", 200), ("editor", 200), ("viewer", 403), ("outsider", 403)],
)
async def test_view_permission_matrix(client, ctx, db_session, actor, expected):
    sid = ctx["subject"].id
    hm = _auth(ctx["manager"])
    q = await _seed_full_question(db_session, subject_id=sid)
    classroom = await _seed_classroom(db_session, subject_id=sid)
    version = await _finalized_version(client, sid, hm, q_ids=[q.id], scores=[100])
    created = await client.post(
        f"{API}/subjects/{sid}/exam-sessions",
        json={"composition_version_id": version["id"], "classroom_id": classroom.id, "name": "考"},
        headers=hm,
    )
    exam_id = created.json()["id"]

    r = await client.get(f"{API}/subjects/{sid}/exam-sessions/{exam_id}", headers=_auth(ctx[actor]))
    assert r.status_code == expected, r.text


# --------------------------------------------------------------------------- #
# 快照稳定性:定稿后改题库不影响已建考试
# --------------------------------------------------------------------------- #
async def test_snapshot_is_stable_after_source_changes(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["manager"])
    q = await _seed_full_question(db_session, subject_id=sid, stem="原始题")
    classroom = await _seed_classroom(db_session, subject_id=sid, students=1)
    version = await _finalized_version(client, sid, h, q_ids=[q.id], scores=[100])

    created = await client.post(
        f"{API}/subjects/{sid}/exam-sessions",
        json={"composition_version_id": version["id"], "classroom_id": classroom.id, "name": "考"},
        headers=h,
    )
    exam_id = created.json()["id"]
    q_type_before = created.json()["questions"][0]["q_type"]

    # 事后修改题库 + 新增班级成员:都不应影响已建考试。
    q.q_type = QuestionType.FREE_RESPONSE
    q.content = json.dumps(_rich_doc("被改动"), ensure_ascii=False)
    db_session.add(q)
    new_student = Student(subject_id=sid, student_no="new-999", name="新生")
    db_session.add(new_student)
    await db_session.commit()
    await db_session.refresh(new_student)
    db_session.add(ClassroomStudent(classroom_id=classroom.id, student_id=new_student.id))
    await db_session.commit()

    g = await client.get(f"{API}/subjects/{sid}/exam-sessions/{exam_id}", headers=h)
    assert g.json()["questions"][0]["q_type"] == q_type_before == "single_choice"
    assert len(g.json()["participants"]) == 1  # 仍是开考时冻结的成员


# --------------------------------------------------------------------------- #
# 原子回滚:事件写入失败时,session/questions/participants 全回滚
# --------------------------------------------------------------------------- #
async def test_atomic_rollback_on_failure(client, ctx, db_session, monkeypatch):
    from app.services import assessment_service

    sid = ctx["subject"].id
    h = _auth(ctx["manager"])
    q = await _seed_full_question(db_session, subject_id=sid)
    classroom = await _seed_classroom(db_session, subject_id=sid, students=2)
    version_json = await _finalized_version(client, sid, h, q_ids=[q.id], scores=[100])

    async def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(assessment_service, "_write_event", _boom)

    admin = ctx["admin"]
    with pytest.raises(RuntimeError):
        await assessment_service.create_exam_session(
            db_session,
            subject_id=sid,
            composition_version_id=version_json["id"],
            classroom_id=classroom.id,
            name="考",
            actor=admin,
        )

    # 全回滚:没有任何 session / question / participant 落库。
    assert await db_session.scalar(select(func.count()).select_from(ExamSession)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ExamQuestion)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ExamParticipant)) == 0
