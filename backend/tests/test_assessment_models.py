"""通用评测 (Assessment) 领域模型的聚焦测试。

覆盖:身份/版本/条目的层级与不可变约束、投放/参与/作答/评分的唯一约束与
CheckConstraint、ResponseGrade 追加式(supersedes 自引用)、枚举以 value 持久化、
线下 session 默认 (closed + not_started),以及 ORM 级联删除与 SET NULL provenance。
"""
from decimal import Decimal

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.models.assessment import (
    Assessment,
    AssessmentAttempt,
    AssessmentEvent,
    AssessmentItem,
    AssessmentParticipation,
    AssessmentResponse,
    AssessmentSession,
    AssessmentVersion,
    AttemptMode,
    AttemptStatus,
    Classroom,
    ClassroomStudent,
    DeliveryStatus,
    GradeStatus,
    GradingMethod,
    GradingStatus,
    ParticipationStatus,
    ResponseGrade,
    Student,
)
from app.models.subject import Subject
from app.models.user import User


async def _seed_user_subject(db_session):
    user = User(username="alice", full_name="Alice", hashed_password="x")
    subject = Subject(name="数学", slug="math")
    db_session.add_all([user, subject])
    await db_session.flush()
    return user, subject


async def _seed_assessment_version(db_session, subject, user, *, version_no=1):
    assessment = Assessment(subject_id=subject.id, title="期中评测", created_by=user.id)
    db_session.add(assessment)
    await db_session.flush()
    version = AssessmentVersion(
        assessment_id=assessment.id,
        version_no=version_no,
        source_type="composition",
        snapshot={"total_score": "100.00", "item_count": 2},
        total_score=Decimal("100.00"),
        item_count=2,
        created_by=user.id,
    )
    db_session.add(version)
    await db_session.flush()
    return assessment, version


async def _seed_item(db_session, version, *, item_key="q1", position=0, max_score="50.00"):
    item = AssessmentItem(
        version_id=version.id,
        item_key=item_key,
        position=position,
        item_type="free_response",
        max_score=Decimal(max_score),
        prompt_snapshot={"stem": "?"},
        response_spec={"kind": "free_response"},
        scoring_spec={"score": max_score},
    )
    db_session.add(item)
    await db_session.flush()
    return item


async def _seed_session(db_session, version, subject):
    session = AssessmentSession(version_id=version.id, subject_id=subject.id, name="线下期中")
    db_session.add(session)
    await db_session.flush()
    return session


# --------------------------------------------------------------------------- #
# 身份 / 版本 / 条目
# --------------------------------------------------------------------------- #
async def test_assessment_has_no_current_version_id():
    # 契约:身份不持有 current_version_id(避免循环 FK)。
    assert "current_version_id" not in inspect(Assessment).columns.keys()


async def test_version_no_unique_per_assessment(db_session):
    user, subject = await _seed_user_subject(db_session)
    assessment, _ = await _seed_assessment_version(db_session, subject, user, version_no=1)
    db_session.add(
        AssessmentVersion(
            assessment_id=assessment.id,
            version_no=1,
            source_type="composition",
            snapshot={"total_score": "100.00", "item_count": 2},
            total_score=Decimal("100.00"),
            item_count=2,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_item_key_unique_per_version(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, version = await _seed_assessment_version(db_session, subject, user)
    await _seed_item(db_session, version, item_key="dup", position=0)
    db_session.add(
        AssessmentItem(
            version_id=version.id,
            item_key="dup",
            position=1,
            item_type="free_response",
            max_score=Decimal("1.00"),
            prompt_snapshot={"stem": "?"},
            response_spec={"kind": "free_response"},
            scoring_spec={"score": "1.00"},
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_item_negative_max_score_rejected(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, version = await _seed_assessment_version(db_session, subject, user)
    db_session.add(
        AssessmentItem(
            version_id=version.id,
            item_key="neg",
            position=0,
            item_type="free_response",
            max_score=Decimal("-1.00"),
            prompt_snapshot={"stem": "?"},
            response_spec={"kind": "free_response"},
            scoring_spec={"score": "-1.00"},
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_item_zero_max_score_rejected(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, version = await _seed_assessment_version(db_session, subject, user)
    db_session.add(
        AssessmentItem(
            version_id=version.id,
            item_key="zero",
            position=0,
            item_type="free_response",
            max_score=Decimal("0.00"),
            prompt_snapshot={"stem": "?"},
            response_spec={"kind": "free_response"},
            scoring_spec={"score": "0.00"},
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_version_null_snapshot_rejected(db_session):
    user, subject = await _seed_user_subject(db_session)
    assessment = Assessment(subject_id=subject.id, title="缺快照", created_by=user.id)
    db_session.add(assessment)
    await db_session.flush()
    # 不提供 snapshot 列 -> SQL NULL -> 触发 NOT NULL。
    db_session.add(
        AssessmentVersion(
            assessment_id=assessment.id,
            version_no=1,
            source_type="composition",
            total_score=Decimal("100.00"),
            item_count=2,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_version_zero_total_score_rejected(db_session):
    user, subject = await _seed_user_subject(db_session)
    assessment = Assessment(subject_id=subject.id, title="零分版本", created_by=user.id)
    db_session.add(assessment)
    await db_session.flush()
    db_session.add(
        AssessmentVersion(
            assessment_id=assessment.id,
            version_no=1,
            source_type="composition",
            snapshot={"total_score": "0.00", "item_count": 1},
            total_score=Decimal("0.00"),
            item_count=1,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_assessment_invalid_status_rejected(db_session):
    user, subject = await _seed_user_subject(db_session)
    db_session.add(
        Assessment(
            subject_id=subject.id,
            title="非法状态",
            status="bogus",
            created_by=user.id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_parent_item_set_null_on_delete(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, version = await _seed_assessment_version(db_session, subject, user)
    parent = await _seed_item(db_session, version, item_key="parent", position=0)
    child = await _seed_item(db_session, version, item_key="child", position=1)
    child.parent_item_id = parent.id
    await db_session.flush()

    await db_session.delete(parent)
    await db_session.flush()
    await db_session.refresh(child)
    assert child.parent_item_id is None


async def test_deleting_assessment_cascades_versions_and_items(db_session):
    user, subject = await _seed_user_subject(db_session)
    assessment, version = await _seed_assessment_version(db_session, subject, user)
    await _seed_item(db_session, version, item_key="q1", position=0)

    await db_session.delete(assessment)
    await db_session.flush()

    remaining_versions = (
        await db_session.execute(select(AssessmentVersion))
    ).scalars().all()
    remaining_items = (await db_session.execute(select(AssessmentItem))).scalars().all()
    assert remaining_versions == []
    assert remaining_items == []


# --------------------------------------------------------------------------- #
# 投放 / 参与 / 作答
# --------------------------------------------------------------------------- #
async def test_offline_session_defaults_closed_not_started(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, version = await _seed_assessment_version(db_session, subject, user)
    session = await _seed_session(db_session, version, subject)
    await db_session.refresh(session)
    assert session.delivery_status == DeliveryStatus.CLOSED.value
    assert session.grading_status == GradingStatus.NOT_STARTED.value
    assert session.revision == 1


async def test_session_invalid_delivery_status_rejected(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, version = await _seed_assessment_version(db_session, subject, user)
    db_session.add(
        AssessmentSession(
            version_id=version.id,
            subject_id=subject.id,
            name="非法投放",
            delivery_status="bogus",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_participant_key_unique_per_session(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, version = await _seed_assessment_version(db_session, subject, user)
    session = await _seed_session(db_session, version, subject)
    db_session.add(
        AssessmentParticipation(session_id=session.id, participant_key="p1", display_name="甲")
    )
    await db_session.flush()
    db_session.add(
        AssessmentParticipation(session_id=session.id, participant_key="p1", display_name="乙")
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_participation_metadata_maps_to_metadata_column(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, version = await _seed_assessment_version(db_session, subject, user)
    session = await _seed_session(db_session, version, subject)
    part = AssessmentParticipation(
        session_id=session.id,
        participant_key="p1",
        participant_metadata={"seat": "A1"},
    )
    db_session.add(part)
    await db_session.flush()
    assert inspect(AssessmentParticipation).columns["participant_metadata"].name == "metadata"
    assert part.status == ParticipationStatus.ACTIVE.value


async def test_participation_student_set_null_on_delete(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, version = await _seed_assessment_version(db_session, subject, user)
    session = await _seed_session(db_session, version, subject)
    student = Student(subject_id=subject.id, student_no="S001", name="张三")
    db_session.add(student)
    await db_session.flush()
    part = AssessmentParticipation(
        session_id=session.id, participant_key="p1", student_id=student.id
    )
    db_session.add(part)
    await db_session.flush()

    await db_session.delete(student)
    await db_session.flush()
    await db_session.refresh(part)
    assert part.student_id is None


async def test_attempt_no_unique_per_participation(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, version = await _seed_assessment_version(db_session, subject, user)
    session = await _seed_session(db_session, version, subject)
    part = AssessmentParticipation(session_id=session.id, participant_key="p1")
    db_session.add(part)
    await db_session.flush()
    db_session.add(AssessmentAttempt(participation_id=part.id, attempt_no=1))
    await db_session.flush()
    db_session.add(AssessmentAttempt(participation_id=part.id, attempt_no=1))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_attempt_offline_defaults(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, version = await _seed_assessment_version(db_session, subject, user)
    session = await _seed_session(db_session, version, subject)
    part = AssessmentParticipation(session_id=session.id, participant_key="p1")
    db_session.add(part)
    await db_session.flush()
    attempt = AssessmentAttempt(participation_id=part.id, attempt_no=1)
    db_session.add(attempt)
    await db_session.flush()
    await db_session.refresh(attempt)
    assert attempt.mode == AttemptMode.OFFLINE.value
    assert attempt.status == AttemptStatus.NOT_STARTED.value
    assert attempt.answered_count == 0
    assert attempt.graded_count == 0
    # 契约:attempt 不冗余 session_id,只经 participation 推导。
    assert "session_id" not in inspect(AssessmentAttempt).columns.keys()


async def test_response_unique_per_attempt_item(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, version = await _seed_assessment_version(db_session, subject, user)
    item = await _seed_item(db_session, version)
    session = await _seed_session(db_session, version, subject)
    part = AssessmentParticipation(session_id=session.id, participant_key="p1")
    db_session.add(part)
    await db_session.flush()
    attempt = AssessmentAttempt(participation_id=part.id, attempt_no=1)
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(AssessmentResponse(attempt_id=attempt.id, item_id=item.id))
    await db_session.flush()
    db_session.add(AssessmentResponse(attempt_id=attempt.id, item_id=item.id))
    with pytest.raises(IntegrityError):
        await db_session.flush()


# --------------------------------------------------------------------------- #
# 追加式评分
# --------------------------------------------------------------------------- #
async def _seed_response(db_session, subject, user):
    _, version = await _seed_assessment_version(db_session, subject, user)
    item = await _seed_item(db_session, version)
    session = await _seed_session(db_session, version, subject)
    part = AssessmentParticipation(session_id=session.id, participant_key="p1")
    db_session.add(part)
    await db_session.flush()
    attempt = AssessmentAttempt(participation_id=part.id, attempt_no=1)
    db_session.add(attempt)
    await db_session.flush()
    response = AssessmentResponse(attempt_id=attempt.id, item_id=item.id)
    db_session.add(response)
    await db_session.flush()
    return session, response


async def test_grade_revision_unique_and_append_only(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, response = await _seed_response(db_session, subject, user)
    first = ResponseGrade(
        response_id=response.id,
        revision=1,
        score=Decimal("10.00"),
        max_score=Decimal("50.00"),
        grading_method=GradingMethod.MANUAL.value,
    )
    db_session.add(first)
    await db_session.flush()
    second = ResponseGrade(
        response_id=response.id,
        revision=2,
        score=Decimal("20.00"),
        max_score=Decimal("50.00"),
        supersedes_grade_id=first.id,
    )
    db_session.add(second)
    await db_session.flush()
    await db_session.refresh(second)
    assert second.status == GradeStatus.GRADED.value
    assert second.supersedes_grade_id == first.id
    # 契约:追加式,无 updated_at。
    assert "updated_at" not in inspect(ResponseGrade).columns.keys()

    dup = ResponseGrade(
        response_id=response.id, revision=2, max_score=Decimal("50.00")
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_grade_negative_score_rejected(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, response = await _seed_response(db_session, subject, user)
    db_session.add(
        ResponseGrade(
            response_id=response.id,
            revision=1,
            score=Decimal("-1.00"),
            max_score=Decimal("50.00"),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_grade_score_exceeds_max_rejected(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, response = await _seed_response(db_session, subject, user)
    db_session.add(
        ResponseGrade(
            response_id=response.id,
            revision=1,
            score=Decimal("60.00"),
            max_score=Decimal("50.00"),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_grade_invalid_outcome_rejected(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, response = await _seed_response(db_session, subject, user)
    db_session.add(
        ResponseGrade(
            response_id=response.id,
            revision=1,
            outcome="bogus",
            score=Decimal("10.00"),
            max_score=Decimal("50.00"),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_grade_supersedes_set_null_on_delete(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, response = await _seed_response(db_session, subject, user)
    first = ResponseGrade(response_id=response.id, revision=1, max_score=Decimal("50.00"))
    db_session.add(first)
    await db_session.flush()
    second = ResponseGrade(
        response_id=response.id,
        revision=2,
        max_score=Decimal("50.00"),
        supersedes_grade_id=first.id,
    )
    db_session.add(second)
    await db_session.flush()

    await db_session.delete(first)
    await db_session.flush()
    await db_session.refresh(second)
    assert second.supersedes_grade_id is None


# --------------------------------------------------------------------------- #
# 事件
# --------------------------------------------------------------------------- #
async def test_event_batch_id_unique_per_session(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, version = await _seed_assessment_version(db_session, subject, user)
    session = await _seed_session(db_session, version, subject)
    db_session.add(
        AssessmentEvent(
            session_id=session.id,
            event_type="recording_started",
            summary="开始录分",
            batch_id="batch-1",
            actor_id=user.id,
        )
    )
    await db_session.flush()
    db_session.add(
        AssessmentEvent(
            session_id=session.id,
            event_type="score_changed",
            summary="重复批次",
            batch_id="batch-1",
            actor_id=user.id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_deleting_session_cascades_participations_and_events(db_session):
    user, subject = await _seed_user_subject(db_session)
    _, version = await _seed_assessment_version(db_session, subject, user)
    session = await _seed_session(db_session, version, subject)
    db_session.add(AssessmentParticipation(session_id=session.id, participant_key="p1"))
    db_session.add(
        AssessmentEvent(
            session_id=session.id, event_type="e", summary="s", actor_id=user.id
        )
    )
    await db_session.flush()

    await db_session.delete(session)
    await db_session.flush()

    parts = (await db_session.execute(select(AssessmentParticipation))).scalars().all()
    events = (await db_session.execute(select(AssessmentEvent))).scalars().all()
    assert parts == []
    assert events == []


# --------------------------------------------------------------------------- #
# 名册(保留既有行为)
# --------------------------------------------------------------------------- #
async def test_classroom_student_membership_unique(db_session):
    user, subject = await _seed_user_subject(db_session)
    classroom = Classroom(subject_id=subject.id, name="一班")
    student = Student(subject_id=subject.id, student_no="S001", name="张三")
    db_session.add_all([classroom, student])
    await db_session.flush()
    db_session.add(ClassroomStudent(classroom_id=classroom.id, student_id=student.id))
    await db_session.flush()
    db_session.add(ClassroomStudent(classroom_id=classroom.id, student_id=student.id))
    with pytest.raises(IntegrityError):
        await db_session.flush()
