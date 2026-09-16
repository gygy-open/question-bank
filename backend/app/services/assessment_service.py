"""通用评测 (Assessment) 域领域服务。

覆盖纵向能力:
1. 名册:学生 / 班级 / 班级成员整体替换。
2. **从 shared 组稿定稿版本 + 班级创建评测**(单事务冻结):Assessment → v1 → items →
   session(线下 closed + not_started)→ classroom participants → 每人一个 offline attempt →
   event。任一步失败全回滚。
3. 评分状态机:grading/start(not_started→in_progress)、grading/finalize(→finalized),
   均以 session.revision 做乐观锁 CAS。
4. **追加式评分**:PATCH attempt grades —— attempt.revision CAS;逐条 item 懒建 Response +
   追加 ResponseGrade(不 UPDATE 历史);重算 attempt 缓存;finalized 只读。
5. gradebook 分页读取与 item 统计。

错误约定(app.capabilities.errors 的 DomainError):
- 版本/班级/session/attempt 不可见(跨学科)→ 404(防枚举)。
- personal 组稿版本 / 未启用评分 / 无题 / 缺分或分值非法 → 400。
- snapshot 结构损坏 → 422。
- 状态/版本冲突、finalized 只读 → 409。
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

import hashlib

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.capabilities.errors import Conflict, Invalid, NotFound, Unprocessable
from app.crud import crud_assessment
from app.models.assessment import (
    SCORE_SCALE,
    Assessment,
    AssessmentAttempt,
    AssessmentEvent,
    AssessmentItem,
    AssessmentParticipation,
    AssessmentResponse,
    AssessmentSession,
    AssessmentStatus,
    AssessmentVersion,
    AttemptMode,
    AttemptStatus,
    AttendanceStatus,
    Classroom,
    ClassroomStudent,
    DeliveryStatus,
    GradeOutcome,
    GradeStatus,
    GradingMethod,
    GradingStatus,
    ParticipationStatus,
    ResponseGrade,
    ResponseStatus,
    Student,
)
from app.models.composition import ScopeType
from app.models.user import User
from app.services import assessment_excel

# provenance 里 prompt_snapshot 不携带的私密字段(答案/解析)。
_PRIVATE_QUESTION_KEYS = ("answer", "analysis", "solution")


# --------------------------------------------------------------------------- #
# 分值 / snapshot 提取
# --------------------------------------------------------------------------- #
def _to_score(raw: Any) -> Decimal:
    if raw is None or isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise Invalid("每道题必须设置合法的分值")
    score = Decimal(str(raw))
    if score <= 0:
        raise Invalid("题目分值必须大于 0")
    return score


def _extract_items(snapshot: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Decimal]:
    """从 snapshot v2 的 question 节点提取评测条目投影与总分。"""
    nodes = snapshot.get("nodes")
    if not isinstance(nodes, list):
        raise Unprocessable("组稿定稿快照损坏:缺少节点列表")

    question_nodes = [
        n for n in nodes if isinstance(n, dict) and n.get("node_type") == "question"
    ]
    if not question_nodes:
        raise Invalid("组稿定稿版本没有任何题目")

    items: List[Dict[str, Any]] = []
    total = Decimal("0")
    for position, node in enumerate(question_nodes):
        node_id = node.get("id")
        question = node.get("question")
        if not node_id or not isinstance(question, dict):
            raise Unprocessable("组稿定稿快照损坏:题目节点缺少 id 或题目投影")
        q_type = question.get("q_type")
        if not q_type:
            raise Unprocessable("组稿定稿快照损坏:题目节点缺少 q_type")
        score = _to_score((node.get("props") or {}).get("score"))
        total += score

        prompt = {k: v for k, v in question.items() if k not in _PRIVATE_QUESTION_KEYS}
        scoring = {k: question.get(k) for k in _PRIVATE_QUESTION_KEYS if k in question}
        scoring["score"] = str(score)

        items.append(
            {
                "item_key": str(node_id),
                "position": position,
                "item_type": q_type,
                "max_score": score,
                "source_question_id": node.get("question_id"),
                "source_question_revision": node.get("question_revision"),
                "source_node_id": str(node_id),
                "prompt_snapshot": prompt,
                "response_spec": {"kind": q_type},
                "scoring_spec": scoring,
                "metadata_snapshot": None,
            }
        )

    if total <= 0:
        raise Invalid("组稿定稿版本的题目总分必须大于 0")
    return items, total


def _item_read(item: AssessmentItem) -> Dict[str, Any]:
    """公开条目投影 —— 不含私有 scoring_spec。"""
    return {
        "id": item.id,
        "item_key": item.item_key,
        "position": item.position,
        "item_type": item.item_type,
        "max_score": item.max_score,
        "parent_item_id": item.parent_item_id,
        "source_question_id": item.source_question_id,
        "source_question_revision": item.source_question_revision,
    }


def _session_read(session: AssessmentSession) -> Dict[str, Any]:
    """投放列表投影(附评测身份 id/标题,便于列表直接展示)。"""
    version = session.version
    assessment = version.assessment if version is not None else None
    return {
        "id": session.id,
        "assessment_id": version.assessment_id if version is not None else None,
        "assessment_title": assessment.title if assessment is not None else None,
        "version_id": session.version_id,
        "subject_id": session.subject_id,
        "name": session.name,
        "delivery_status": session.delivery_status,
        "grading_status": session.grading_status,
        "revision": session.revision,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def _session_detail(session: AssessmentSession) -> Dict[str, Any]:
    """投放详情投影(version 冻结条目 + 参与者 + 每人 attempts)。"""
    version = session.version
    assessment = version.assessment if version is not None else None
    participants: List[Dict[str, Any]] = []
    for p in session.participations:
        participants.append(
            {
                "id": p.id,
                "participant_key": p.participant_key,
                "student_id": p.student_id,
                "user_id": p.user_id,
                "display_name": p.display_name,
                "identifier": p.identifier,
                "attendance_status": p.attendance_status,
                "status": p.status,
                "attempts": [
                    {
                        "attempt_id": a.id,
                        "attempt_no": a.attempt_no,
                        "mode": a.mode,
                        "status": a.status,
                        "revision": a.revision,
                        "total_score": a.total_score,
                        "max_score": a.max_score,
                        "answered_count": a.answered_count,
                        "graded_count": a.graded_count,
                    }
                    for a in p.attempts
                ],
            }
        )
    return {
        "id": session.id,
        "assessment_id": version.assessment_id,
        "assessment_title": assessment.title if assessment is not None else None,
        "version_id": session.version_id,
        "version_no": version.version_no,
        "subject_id": session.subject_id,
        "name": session.name,
        "delivery_status": session.delivery_status,
        "grading_status": session.grading_status,
        "opens_at": session.opens_at,
        "closes_at": session.closes_at,
        "attempt_limit": session.attempt_limit,
        "revision": session.revision,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "total_score": version.total_score,
        "item_count": version.item_count,
        "items": [_item_read(item) for item in version.items],
        "participants": participants,
    }


async def get_session_detail(
    db: AsyncSession, *, subject_id: int, session_id: int
) -> Dict[str, Any]:
    session = await crud_assessment.assessment.get_session_detail(
        db, session_id=session_id, subject_id=subject_id
    )
    if session is None:
        raise NotFound("Assessment session not found")
    return _session_detail(session)


async def list_sessions(
    db: AsyncSession,
    *,
    subject_id: int,
    grading_status: Optional[str] = None,
    assessment_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    sessions = await crud_assessment.assessment.list_sessions(
        db,
        subject_id=subject_id,
        grading_status=grading_status,
        assessment_id=assessment_id,
    )
    return [_session_read(session) for session in sessions]


async def get_assessment_detail(
    db: AsyncSession, *, subject_id: int, assessment_id: int
) -> Dict[str, Any]:
    assessment = await crud_assessment.assessment.get_assessment(
        db, assessment_id=assessment_id, subject_id=subject_id
    )
    if assessment is None:
        raise NotFound("Assessment not found")
    versions = sorted(assessment.versions, key=lambda v: v.version_no)
    current = versions[-1] if versions else None
    return {
        "id": assessment.id,
        "subject_id": assessment.subject_id,
        "title": assessment.title,
        "description": assessment.description,
        "status": assessment.status,
        "created_at": assessment.created_at,
        "updated_at": assessment.updated_at,
        "versions": [
            {
                "id": v.id,
                "assessment_id": v.assessment_id,
                "version_no": v.version_no,
                "composition_version_id": v.composition_version_id,
                "source_type": v.source_type,
                "total_score": v.total_score,
                "item_count": v.item_count,
                "created_at": v.created_at,
            }
            for v in versions
        ],
        "current_items": [
            _item_read(item) for item in (current.items if current else [])
        ],
    }


async def _write_event(
    db: AsyncSession,
    *,
    session_id: int,
    actor_id: int,
    event_type: str,
    summary: str,
    payload: Dict[str, Any],
    target_type: str = "assessment_session",
    target_id: Optional[str] = None,
    batch_id: Optional[str] = None,
) -> None:
    db.add(
        AssessmentEvent(
            session_id=session_id,
            event_type=event_type,
            target_type=target_type,
            target_id=target_id if target_id is not None else str(session_id),
            summary=summary,
            payload=payload,
            batch_id=batch_id,
            actor_id=actor_id,
        )
    )


# --------------------------------------------------------------------------- #
# 从组稿定稿创建评测(单事务)
# --------------------------------------------------------------------------- #
async def create_from_composition(
    db: AsyncSession,
    *,
    subject_id: int,
    composition_version_id: int,
    classroom_id: int,
    title: str,
    session_name: Optional[str] = None,
    actor: User,
) -> AssessmentSession:
    """从一个 shared 组稿定稿版本 + 班级创建评测(单事务,失败全回滚)。"""
    version = await crud_assessment.assessment.get_version_with_composition(
        db, version_id=composition_version_id
    )
    if version is None or version.subject_id != subject_id:
        raise NotFound("Composition version not found")

    composition = version.composition
    if composition is None or composition.scope_type != ScopeType.SHARED:
        raise Invalid("只能基于共享(shared)组稿定稿版本创建评测")

    classroom = await crud_assessment.assessment.get_classroom(
        db, classroom_id=classroom_id
    )
    if classroom is None or classroom.subject_id != subject_id:
        raise NotFound("Classroom not found")

    snapshot = version.snapshot
    if not isinstance(snapshot, dict):
        raise Unprocessable("组稿定稿快照损坏")
    if not snapshot.get("scoring_enabled"):
        raise Invalid("组稿定稿版本未启用赋分,无法创建评测")

    item_specs, total_score = _extract_items(snapshot)
    members = await crud_assessment.assessment.list_classroom_members(
        db, classroom_id=classroom_id
    )

    try:
        assessment = Assessment(
            subject_id=subject_id,
            title=title,
            status=AssessmentStatus.ACTIVE.value,
            created_by=actor.id,
            updated_by=actor.id,
        )
        db.add(assessment)
        await db.flush()

        version_row = AssessmentVersion(
            assessment_id=assessment.id,
            version_no=1,
            composition_version_id=version.id,
            source_type="composition",
            source_ref={
                "composition_id": version.composition_id,
                "composition_version_id": version.id,
                "version_no": version.version_no,
            },
            snapshot={"total_score": str(total_score), "item_count": len(item_specs)},
            total_score=total_score,
            item_count=len(item_specs),
            created_by=actor.id,
        )
        db.add(version_row)
        await db.flush()

        items: List[AssessmentItem] = []
        for spec in item_specs:
            item = AssessmentItem(version_id=version_row.id, **spec)
            db.add(item)
            items.append(item)
        await db.flush()

        session = AssessmentSession(
            version_id=version_row.id,
            subject_id=subject_id,
            name=session_name or title,
            delivery_status=DeliveryStatus.CLOSED.value,
            grading_status=GradingStatus.NOT_STARTED.value,
            revision=1,
            created_by=actor.id,
            updated_by=actor.id,
        )
        db.add(session)
        await db.flush()

        for member in members:
            student = member.student
            participation = AssessmentParticipation(
                session_id=session.id,
                participant_key=str(student.id),
                student_id=member.student_id,
                display_name=student.name,
                identifier=student.student_no,
                attendance_status="present",
                status=ParticipationStatus.ACTIVE.value,
            )
            db.add(participation)
            await db.flush()
            db.add(
                AssessmentAttempt(
                    participation_id=participation.id,
                    attempt_no=1,
                    mode=AttemptMode.OFFLINE.value,
                    status=AttemptStatus.NOT_STARTED.value,
                    revision=1,
                    max_score=total_score,
                    answered_count=0,
                    graded_count=0,
                )
            )

        await _write_event(
            db,
            session_id=session.id,
            actor_id=actor.id,
            event_type="created",
            summary=f"Created assessment from composition version {version.version_no}",
            payload={
                "assessment_id": assessment.id,
                "version_id": version_row.id,
                "composition_version_id": version.id,
                "classroom_id": classroom.id,
                "item_count": len(item_specs),
                "participation_count": len(members),
                "total_score": str(total_score),
            },
        )

        await db.commit()
    except Exception:
        await db.rollback()
        raise

    detail = await crud_assessment.assessment.get_session_detail(
        db, session_id=session.id, subject_id=subject_id
    )
    assert detail is not None
    return _session_detail(detail)


# --------------------------------------------------------------------------- #
# 学生 / 班级名册
# --------------------------------------------------------------------------- #
async def create_student(
    db: AsyncSession,
    *,
    subject_id: int,
    student_no: str,
    name: str,
    user_id: Optional[int],
    actor: User,
) -> Student:
    if await crud_assessment.assessment.get_student_by_no(
        db, subject_id=subject_id, student_no=student_no
    ):
        raise Conflict("学号在本学科内已存在")
    if user_id is not None:
        if await db.get(User, user_id) is None:
            raise Invalid("绑定的用户不存在")
        if await crud_assessment.assessment.get_student_by_user(
            db, subject_id=subject_id, user_id=user_id
        ):
            raise Conflict("该用户已在本学科绑定学生")
    student = Student(
        subject_id=subject_id,
        student_no=student_no,
        name=name,
        user_id=user_id,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(student)
    await db.commit()
    await db.refresh(student)
    return student


async def create_classroom(
    db: AsyncSession, *, subject_id: int, name: str, actor: User
) -> Classroom:
    if await crud_assessment.assessment.get_classroom_by_name(
        db, subject_id=subject_id, name=name
    ):
        raise Conflict("班级名在本学科内已存在")
    classroom = Classroom(
        subject_id=subject_id, name=name, created_by=actor.id, updated_by=actor.id
    )
    db.add(classroom)
    await db.commit()
    await db.refresh(classroom)
    return classroom


async def replace_classroom_members(
    db: AsyncSession,
    *,
    subject_id: int,
    classroom_id: int,
    student_ids: Sequence[int],
    actor: User,
) -> List[Student]:
    classroom = await crud_assessment.assessment.get_classroom(
        db, classroom_id=classroom_id
    )
    if classroom is None or classroom.subject_id != subject_id:
        raise NotFound("Classroom not found")

    unique_ids = list(dict.fromkeys(student_ids))
    students = await crud_assessment.assessment.list_students_by_ids(
        db, student_ids=unique_ids
    )
    found = {s.id: s for s in students}
    for sid in unique_ids:
        student = found.get(sid)
        if student is None or student.subject_id != subject_id:
            raise Unprocessable("学生不存在或不属于该学科")

    try:
        await db.execute(
            delete(ClassroomStudent).where(
                ClassroomStudent.classroom_id == classroom_id
            )
        )
        for sid in unique_ids:
            db.add(ClassroomStudent(classroom_id=classroom_id, student_id=sid))
        classroom.updated_by = actor.id
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return [found[sid] for sid in unique_ids]


# --------------------------------------------------------------------------- #
# 评分状态机(session.revision 乐观锁)
# --------------------------------------------------------------------------- #
async def _transition_grading(
    db: AsyncSession,
    *,
    session: AssessmentSession,
    from_status: GradingStatus,
    to_status: GradingStatus,
    actor: User,
) -> None:
    upd = await db.execute(
        update(AssessmentSession)
        .where(
            AssessmentSession.id == session.id,
            AssessmentSession.grading_status == from_status.value,
            AssessmentSession.revision == session.revision,
        )
        .values(
            grading_status=to_status.value,
            revision=AssessmentSession.revision + 1,
            updated_by=actor.id,
        )
    )
    if upd.rowcount == 0:
        raise Conflict("评测状态已变更,请刷新后重试")


async def start_grading(
    db: AsyncSession, *, subject_id: int, session_id: int, actor: User
) -> AssessmentSession:
    """not_started → in_progress:要求至少一个参与者与一个条目。"""
    session = await crud_assessment.assessment.get_session_detail(
        db, session_id=session_id, subject_id=subject_id
    )
    if session is None:
        raise NotFound("Assessment session not found")
    if session.grading_status != GradingStatus.NOT_STARTED.value:
        raise Conflict("只有未开始评分的投放可以开始录分")
    if not session.participations:
        raise Invalid("投放没有参与者,无法开始录分")
    if not session.version.items:
        raise Invalid("投放没有条目,无法开始录分")

    new_revision = session.revision + 1
    try:
        await _transition_grading(
            db,
            session=session,
            from_status=GradingStatus.NOT_STARTED,
            to_status=GradingStatus.IN_PROGRESS,
            actor=actor,
        )
        await _write_event(
            db,
            session_id=session.id,
            actor_id=actor.id,
            event_type="grading_started",
            summary="Started grading",
            payload={
                "from": "not_started",
                "to": "in_progress",
                "revision": new_revision,
            },
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    detail = await crud_assessment.assessment.get_session_detail(
        db, session_id=session_id, subject_id=subject_id
    )
    assert detail is not None
    return _session_detail(detail)


def _attempt_graded_count(
    attempt: Optional[AssessmentAttempt], items: List[AssessmentItem]
) -> int:
    """某次作答中「已完整评分(GRADED 且有分)」的条目数,直接从评分历史重算。"""
    if attempt is None:
        return 0
    item_ids = {item.id for item in items}
    responses = {r.item_id: r for r in attempt.responses if r.item_id in item_ids}
    graded = 0
    for item in items:
        response = responses.get(item.id)
        latest = _latest_grade(response) if response is not None else None
        if (
            latest is not None
            and latest.status == GradeStatus.GRADED.value
            and latest.score is not None
        ):
            graded += 1
    return graded


# 定稿完整性校验时排除的出勤状态:缺考 / 请假不参与评分。
_UNGRADED_ATTENDANCE = frozenset(
    {AttendanceStatus.ABSENT.value, AttendanceStatus.EXCUSED.value}
)


async def finalize_grading(
    db: AsyncSession, *, subject_id: int, session_id: int, actor: User
) -> AssessmentSession:
    """in_progress → finalized。要求每个应评参与者已完整评分;finalized 之后写入被拒。"""
    session = await crud_assessment.assessment.get_gradebook_session(
        db, session_id=session_id, subject_id=subject_id
    )
    if session is None:
        raise NotFound("Assessment session not found")
    if session.grading_status != GradingStatus.IN_PROGRESS.value:
        raise Conflict("只有评分中的投放可以定稿")

    items = list(session.version.items)
    item_count = len(items)
    incomplete: List[str] = []
    for participation in session.participations:
        if participation.attendance_status in _UNGRADED_ATTENDANCE:
            continue
        if participation.status == ParticipationStatus.WITHDRAWN.value:
            continue
        attempt = participation.attempts[-1] if participation.attempts else None
        if _attempt_graded_count(attempt, items) < item_count:
            incomplete.append(participation.participant_key)
    if incomplete:
        raise Conflict(f"仍有 {len(incomplete)} 名应评参与者未完整评分,无法定稿")

    new_revision = session.revision + 1
    try:
        await _transition_grading(
            db,
            session=session,
            from_status=GradingStatus.IN_PROGRESS,
            to_status=GradingStatus.FINALIZED,
            actor=actor,
        )
        await _write_event(
            db,
            session_id=session.id,
            actor_id=actor.id,
            event_type="grading_finalized",
            summary="Finalized grading",
            payload={
                "from": "in_progress",
                "to": "finalized",
                "revision": new_revision,
            },
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    detail = await crud_assessment.assessment.get_session_detail(
        db, session_id=session_id, subject_id=subject_id
    )
    assert detail is not None
    return _session_detail(detail)


# --------------------------------------------------------------------------- #
# 追加式评分(attempt.revision 乐观锁)
# --------------------------------------------------------------------------- #
def _validate_score(score: Decimal, max_score: Decimal) -> Decimal:
    if score < 0:
        raise Invalid("分值不能为负")
    if score > max_score:
        raise Invalid(f"分值不能超过该条目满分 {max_score}")
    exponent = score.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -SCORE_SCALE:
        raise Invalid("分值精度最多两位小数")
    return score


def _default_outcome(score: Optional[Decimal], max_score: Decimal) -> str:
    """默认判定:full=correct、zero=incorrect、middle=partial、无分/满分为0=unscored。"""
    if score is None or max_score <= 0:
        return GradeOutcome.UNSCORED.value
    if score >= max_score:
        return GradeOutcome.CORRECT.value
    if score <= 0:
        return GradeOutcome.INCORRECT.value
    return GradeOutcome.PARTIAL.value


def _latest_grade(response: AssessmentResponse) -> Optional[ResponseGrade]:
    if not response.grades:
        return None
    return max(response.grades, key=lambda g: g.revision)


def _attempt_read(
    attempt: AssessmentAttempt, items: List[AssessmentItem]
) -> Dict[str, Any]:
    item_ids = {item.id for item in items}
    responses = {r.item_id: r for r in attempt.responses if r.item_id in item_ids}
    grade_rows: List[Dict[str, Any]] = []
    for item in items:
        response = responses.get(item.id)
        grade = _latest_grade(response) if response is not None else None
        grade_rows.append(
            {
                "item_id": item.id,
                "item_key": item.item_key,
                "max_score": item.max_score,
                "response_id": response.id if response is not None else None,
                "score": grade.score if grade is not None else None,
                "outcome": grade.outcome if grade is not None else None,
                "grade_revision": grade.revision if grade is not None else 0,
                "status": response.status if response is not None else "unanswered",
            }
        )
    return {
        "attempt_id": attempt.id,
        "participation_id": attempt.participation_id,
        "attempt_no": attempt.attempt_no,
        "status": attempt.status,
        "revision": attempt.revision,
        "total_score": attempt.total_score,
        "max_score": attempt.max_score,
        "answered_count": attempt.answered_count,
        "graded_count": attempt.graded_count,
        "grades": grade_rows,
    }


async def _apply_grades_to_attempt(
    db: AsyncSession,
    *,
    attempt: AssessmentAttempt,
    version: AssessmentVersion,
    expected_revision: int,
    normalized: List[
        Tuple[int, Optional[Decimal], Optional[str], Optional[Dict[str, Any]], str]
    ],
    actor: User,
) -> List[Dict[str, Any]]:
    """低层录分工作单元:attempt.revision CAS + 逐条懒建 Response + 追加 ResponseGrade +
    重算 attempt 缓存。**不写事件、不 commit**,由调用方负责事务与审计。"""
    cas = await db.execute(
        update(AssessmentAttempt)
        .where(
            AssessmentAttempt.id == attempt.id,
            AssessmentAttempt.revision == expected_revision,
        )
        .values(revision=AssessmentAttempt.revision + 1)
    )
    if cas.rowcount == 0:
        raise Conflict("成绩版本冲突,请刷新后重试")

    item_map = {item.id: item for item in version.items}
    responses = {r.item_id: r for r in attempt.responses}
    changes: List[Dict[str, Any]] = []
    # 本轮新增评分按 item 记录,重算缓存时优先取它,避免对新建 Response 触发懒加载。
    new_grade_by_item: Dict[int, ResponseGrade] = {}
    for item_id, score, outcome, feedback, method in normalized:
        item = item_map[item_id]
        response = responses.get(item_id)
        if response is None:
            # 线下懒建空 Response。
            response = AssessmentResponse(
                attempt_id=attempt.id,
                item_id=item_id,
                status=ResponseStatus.ANSWERED.value,
                revision=1,
            )
            db.add(response)
            await db.flush()
            responses[item_id] = response
            prev_grade_id = None
            next_rev = 1
        else:
            prev = _latest_grade(response)
            prev_grade_id = prev.id if prev is not None else None
            next_rev = (prev.revision + 1) if prev is not None else 1
            response.status = ResponseStatus.ANSWERED.value
            response.revision = response.revision + 1

        grade = ResponseGrade(
            response_id=response.id,
            revision=next_rev,
            status=GradeStatus.GRADED.value
            if score is not None
            else GradeStatus.PENDING.value,
            outcome=outcome,
            score=score,
            max_score=item.max_score,
            grading_method=method,
            grader_id=actor.id,
            feedback=feedback,
            supersedes_grade_id=prev_grade_id,
        )
        db.add(grade)
        new_grade_by_item[item_id] = grade
        changes.append(
            {
                "item_id": item_id,
                "score": str(score) if score is not None else None,
                "outcome": outcome,
                "revision": next_rev,
            }
        )

    await db.flush()

    # 重算 attempt 缓存:仅统计已 GRADED 且有分的最新评分。
    graded_total = Decimal("0")
    graded_count = 0
    answered_count = 0
    for item in version.items:
        response = responses.get(item.id)
        if response is None:
            continue
        if response.status == ResponseStatus.ANSWERED.value:
            answered_count += 1
        # 本轮改动的 item 用新评分;未改动的 item 走 eager 加载的历史(不触发 IO)。
        latest = new_grade_by_item.get(item.id)
        if latest is None:
            latest = _latest_grade(response)
        if (
            latest is not None
            and latest.status == GradeStatus.GRADED.value
            and latest.score is not None
        ):
            graded_total += latest.score
            graded_count += 1

    item_count = len(version.items)
    # version.total_score 理论上为 NOT NULL;若遇损坏行则拒绝录分,绝不把 max_score 覆盖为 None。
    if version.total_score is None:
        raise Unprocessable("评测版本满分缺失,数据损坏,无法录分")
    attempt.total_score = graded_total if graded_count > 0 else None
    attempt.max_score = version.total_score
    attempt.answered_count = answered_count
    attempt.graded_count = graded_count
    attempt.revision = expected_revision + 1
    if graded_count >= item_count and item_count > 0:
        attempt.status = AttemptStatus.GRADED.value
        attempt.graded_at = datetime.utcnow()
    elif graded_count > 0:
        attempt.status = AttemptStatus.GRADING.value
    else:
        attempt.status = AttemptStatus.IN_PROGRESS.value

    return changes


async def append_grades(
    db: AsyncSession,
    *,
    subject_id: int,
    attempt_id: int,
    expected_revision: int,
    batch_id: Optional[str],
    items: List[Dict[str, Any]],
    actor: User,
) -> Dict[str, Any]:
    """追加式录分:attempt.revision CAS + 逐条懒建 Response + 追加 ResponseGrade + 重算缓存。"""
    attempt = await crud_assessment.assessment.get_attempt_for_grading(
        db, attempt_id=attempt_id, subject_id=subject_id
    )
    if attempt is None:
        raise NotFound("Assessment attempt not found")

    session = attempt.participation.session
    version = session.version
    if session.grading_status == GradingStatus.FINALIZED.value:
        raise Conflict("评测已定稿,不能再修改成绩")
    if session.grading_status != GradingStatus.IN_PROGRESS.value:
        raise Conflict("只有评分中的投放可以录分")

    item_map = {item.id: item for item in version.items}

    # 校验 items:去重、条目须属于本版本、分值范围与精度。
    seen: set[int] = set()
    normalized: List[
        Tuple[int, Optional[Decimal], Optional[str], Optional[Dict[str, Any]], str]
    ] = []
    for raw in items:
        item_id = raw["item_id"]
        if item_id in seen:
            raise Invalid("同一次录分中条目 id 不能重复")
        seen.add(item_id)
        item = item_map.get(item_id)
        if item is None:
            raise Unprocessable("条目不属于该评测版本")
        score = raw.get("score")
        if score is not None:
            score = _validate_score(Decimal(str(score)), item.max_score)
        outcome = raw.get("outcome") or _default_outcome(score, item.max_score)
        method = raw.get("grading_method") or GradingMethod.MANUAL.value
        feedback = raw.get("feedback")
        normalized.append((item_id, score, outcome, feedback, method))

    requested = [
        {"item_id": iid, "score": str(s) if s is not None else None, "outcome": o}
        for iid, s, o, _f, _m in normalized
    ]

    # batch_id 只允许重放完全相同的请求。
    if batch_id is not None:
        existing = await crud_assessment.assessment.get_event_by_batch(
            db, session_id=session.id, batch_id=batch_id
        )
        if existing is not None:
            payload = existing.payload or {}
            if (
                existing.target_type != "assessment_attempt"
                or existing.target_id != str(attempt.id)
                or payload.get("expected_revision") != expected_revision
                or payload.get("requested_items") != requested
            ):
                raise Conflict("batch_id 已用于其他录分请求")
            return _attempt_read(attempt, version.items)

    try:
        changes = await _apply_grades_to_attempt(
            db,
            attempt=attempt,
            version=version,
            expected_revision=expected_revision,
            normalized=normalized,
            actor=actor,
        )

        await _write_event(
            db,
            session_id=session.id,
            actor_id=actor.id,
            event_type="grades_appended",
            summary=f"Appended grades for attempt {attempt.id}",
            payload={
                "batch_id": batch_id,
                "expected_revision": expected_revision,
                "new_revision": attempt.revision,
                "total_score": str(attempt.total_score)
                if attempt.total_score is not None
                else None,
                "requested_items": requested,
                "changes": changes,
            },
            target_type="assessment_attempt",
            target_id=str(attempt.id),
            batch_id=batch_id,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    # 起始加载时 attempt.responses 已被 eager 载入(可能为空);清出身份映射,
    # 确保重新读取拿到刚追加的 Response / Grade(不依赖 expire_on_commit 行为)。
    db.expunge_all()
    refreshed = await crud_assessment.assessment.get_attempt_for_grading(
        db, attempt_id=attempt_id, subject_id=subject_id
    )
    assert refreshed is not None
    return _attempt_read(refreshed, refreshed.participation.session.version.items)


# --------------------------------------------------------------------------- #
# gradebook 读取 / item 统计
# --------------------------------------------------------------------------- #
async def get_gradebook(
    db: AsyncSession,
    *,
    subject_id: int,
    session_id: int,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    session = await crud_assessment.assessment.get_gradebook_session(
        db, session_id=session_id, subject_id=subject_id
    )
    if session is None:
        raise NotFound("Assessment session not found")

    items = list(session.version.items)
    participations = list(session.participations)
    total = len(participations)
    start = (page - 1) * page_size
    page_slice = participations[start : start + page_size]

    rows: List[Dict[str, Any]] = []
    for participation in page_slice:
        attempt = participation.attempts[-1] if participation.attempts else None
        responses = (
            {r.item_id: r for r in attempt.responses} if attempt is not None else {}
        )
        scores: List[Dict[str, Any]] = []
        for item in items:
            response = responses.get(item.id)
            grade = _latest_grade(response) if response is not None else None
            scores.append(
                {
                    "item_id": item.id,
                    "score": grade.score if grade is not None else None,
                    "outcome": grade.outcome if grade is not None else None,
                }
            )
        rows.append(
            {
                "participation_id": participation.id,
                "participant_key": participation.participant_key,
                "display_name": participation.display_name,
                "identifier": participation.identifier,
                "attendance_status": participation.attendance_status,
                "participation_status": participation.status,
                "attempt_id": attempt.id if attempt is not None else None,
                "attempt_revision": attempt.revision if attempt is not None else 0,
                "attempt_status": attempt.status if attempt is not None else None,
                "total_score": attempt.total_score if attempt is not None else None,
                "graded_count": attempt.graded_count if attempt is not None else 0,
                "scores": scores,
            }
        )

    return {
        "session_id": session.id,
        "grading_status": session.grading_status,
        "delivery_status": session.delivery_status,
        "revision": session.revision,
        "total_score": session.version.total_score,
        "item_count": len(items),
        "items": [_item_read(item) for item in items],
        "participants": rows,
        "page": page,
        "page_size": page_size,
        "total": total,
    }


async def get_item_statistics(
    db: AsyncSession, *, subject_id: int, session_id: int
) -> Dict[str, Any]:
    """按条目聚合:分母为该条目已评分(有分)的作答数。"""
    session = await crud_assessment.assessment.get_gradebook_session(
        db, session_id=session_id, subject_id=subject_id
    )
    if session is None:
        raise NotFound("Assessment session not found")

    items = list(session.version.items)
    graded_by_item: Dict[int, List[Decimal]] = {item.id: [] for item in items}
    # 分母:排除缺考/请假与已退出参与者,且只计有分的最新评分(未评分不进分母)。
    counted = 0
    for participation in session.participations:
        if participation.attendance_status in _UNGRADED_ATTENDANCE:
            continue
        if participation.status == ParticipationStatus.WITHDRAWN.value:
            continue
        counted += 1
        attempt = participation.attempts[-1] if participation.attempts else None
        if attempt is None:
            continue
        for response in attempt.responses:
            if response.item_id not in graded_by_item:
                continue
            latest = _latest_grade(response)
            if (
                latest is not None
                and latest.status == GradeStatus.GRADED.value
                and latest.score is not None
            ):
                graded_by_item[response.item_id].append(latest.score)

    stats: List[Dict[str, Any]] = []
    for item in items:
        scores = graded_by_item[item.id]
        denominator = len(scores)
        if denominator:
            avg = (sum(scores, Decimal("0")) / Decimal(denominator)).quantize(
                Decimal("0.01")
            )
            full_marks = sum(1 for s in scores if s >= item.max_score)
            incorrect = sum(1 for s in scores if s <= 0)
            # 失分率:未拿满分的比例(相对已评分作答)。
            error_rate = (
                Decimal(denominator - full_marks) / Decimal(denominator)
            ).quantize(Decimal("0.0001"))
            stats.append(
                {
                    "item_id": item.id,
                    "item_key": item.item_key,
                    "position": item.position,
                    "max_score": item.max_score,
                    "graded_count": denominator,
                    "average_score": avg,
                    "min_score": min(scores),
                    "max_score_awarded": max(scores),
                    "full_marks_count": full_marks,
                    "incorrect_count": incorrect,
                    "error_rate": error_rate,
                }
            )
        else:
            stats.append(
                {
                    "item_id": item.id,
                    "item_key": item.item_key,
                    "position": item.position,
                    "max_score": item.max_score,
                    "graded_count": 0,
                    "average_score": None,
                    "min_score": None,
                    "max_score_awarded": None,
                    "full_marks_count": 0,
                    "incorrect_count": 0,
                    "error_rate": None,
                }
            )

    return {
        "session_id": session.id,
        "grading_status": session.grading_status,
        "participation_count": counted,
        "items": stats,
    }


# --------------------------------------------------------------------------- #
# 成绩册 Excel:导出 / 预览 / 应用
# --------------------------------------------------------------------------- #
async def export_gradebook(
    db: AsyncSession, *, subject_id: int, session_id: int
) -> bytes:
    """导出教师成绩册(当前最新评分快照)。"""
    session = await crud_assessment.assessment.get_gradebook_session(
        db, session_id=session_id, subject_id=subject_id
    )
    if session is None:
        raise NotFound("Assessment session not found")
    return assessment_excel.generate_gradebook(session)


def _import_errors_payload(
    errors: List[assessment_excel.ScoreImportIssue],
) -> List[Dict[str, Any]]:
    return [{"row": e.row, "field": e.field, "message": e.message} for e in errors]


async def preview_grade_import(
    db: AsyncSession, *, subject_id: int, session_id: int, file_bytes: bytes
) -> Dict[str, Any]:
    """预览成绩册导入:验证结构、聚合行错误、计算变更统计,不写库。"""
    session = await crud_assessment.assessment.get_gradebook_session(
        db, session_id=session_id, subject_id=subject_id
    )
    if session is None:
        raise NotFound("Assessment session not found")

    parsed = assessment_excel.parse_gradebook(file_bytes, session)
    return {
        "session_id": session.id,
        "valid": not parsed.errors,
        "total_rows": len(parsed.rows),
        "changed_rows": parsed.changed_rows,
        "changed_scores": parsed.changed_scores,
        "unchanged_rows": parsed.unchanged_rows,
        "errors": _import_errors_payload(parsed.errors),
    }


def _import_result(
    session_id: int,
    batch_id: Optional[str],
    *,
    changed_rows: int,
    changed_scores: int,
    unchanged_rows: int,
    applied_attempts: int,
    replayed: bool,
) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "batch_id": batch_id,
        "changed_rows": changed_rows,
        "changed_scores": changed_scores,
        "unchanged_rows": unchanged_rows,
        "applied_attempts": applied_attempts,
        "replayed": replayed,
    }


async def apply_grade_import(
    db: AsyncSession,
    *,
    subject_id: int,
    session_id: int,
    file_bytes: bytes,
    batch_id: Optional[str],
    actor: User,
) -> Dict[str, Any]:
    """应用成绩册导入:先 parse,任一错误全拒绝;单事务逐 attempt 追加评分,只写一条导入事件。

    幂等:同 session + batch_id + 同文件 sha256 的重放返回原结果;不同文件复用 batch_id → 409。
    """
    session = await crud_assessment.assessment.get_gradebook_session(
        db, session_id=session_id, subject_id=subject_id
    )
    if session is None:
        raise NotFound("Assessment session not found")
    if session.grading_status == GradingStatus.FINALIZED.value:
        raise Conflict("评测已定稿,不能再修改成绩")
    if session.grading_status != GradingStatus.IN_PROGRESS.value:
        raise Conflict("只有评分中的投放可以导入成绩")

    file_sha256 = hashlib.sha256(file_bytes).hexdigest()

    # batch_id 幂等:同文件重放返回原结果;不同文件复用同一 batch_id → 冲突。
    if batch_id is not None:
        existing = await crud_assessment.assessment.get_event_by_batch(
            db, session_id=session.id, batch_id=batch_id
        )
        if existing is not None:
            payload = existing.payload or {}
            if (
                payload.get("kind") != "grade_import"
                or payload.get("file_sha256") != file_sha256
            ):
                raise Conflict("batch_id 已用于其他成绩导入请求")
            return _import_result(
                session.id,
                batch_id,
                changed_rows=int(payload.get("changed_rows", 0)),
                changed_scores=int(payload.get("changed_scores", 0)),
                unchanged_rows=int(payload.get("unchanged_rows", 0)),
                applied_attempts=int(payload.get("applied_attempts", 0)),
                replayed=True,
            )

    parsed = assessment_excel.parse_gradebook(file_bytes, session)
    if parsed.errors:
        raise Unprocessable(
            f"成绩册存在 {len(parsed.errors)} 处错误,请先预览并修正后再导入"
        )

    version = session.version
    item_by_id = {item.id: item for item in version.items}
    attempts_by_id: Dict[int, AssessmentAttempt] = {}
    for participation in session.participations:
        for attempt in participation.attempts:
            attempts_by_id[attempt.id] = attempt

    try:
        applied_attempts = 0
        for row in parsed.rows:
            attempt = attempts_by_id[row.attempt_id]
            existing: Dict[int, Optional[Decimal]] = {}
            for response in attempt.responses:
                latest = _latest_grade(response)
                if (
                    latest is not None
                    and latest.status == GradeStatus.GRADED.value
                    and latest.score is not None
                ):
                    existing[response.item_id] = latest.score
            normalized: List[
                Tuple[
                    int, Optional[Decimal], Optional[str], Optional[Dict[str, Any]], str
                ]
            ] = []
            for item_id, score in row.scores.items():
                if existing.get(item_id) == score:
                    continue  # 未变更的条目不追加新评分,避免噪声历史。
                item = item_by_id[item_id]
                outcome = _default_outcome(score, item.max_score)
                normalized.append(
                    (item_id, score, outcome, None, GradingMethod.IMPORTED.value)
                )
            if not normalized:
                continue
            await _apply_grades_to_attempt(
                db,
                attempt=attempt,
                version=version,
                expected_revision=row.attempt_revision,
                normalized=normalized,
                actor=actor,
            )
            applied_attempts += 1

        await _write_event(
            db,
            session_id=session.id,
            actor_id=actor.id,
            event_type="grades_imported",
            summary=f"Imported gradebook ({applied_attempts} attempts)",
            payload={
                "kind": "grade_import",
                "file_sha256": file_sha256,
                "changed_rows": parsed.changed_rows,
                "changed_scores": parsed.changed_scores,
                "unchanged_rows": parsed.unchanged_rows,
                "applied_attempts": applied_attempts,
            },
            batch_id=batch_id,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return _import_result(
        session.id,
        batch_id,
        changed_rows=parsed.changed_rows,
        changed_scores=parsed.changed_scores,
        unchanged_rows=parsed.unchanged_rows,
        applied_attempts=applied_attempts,
        replayed=False,
    )
