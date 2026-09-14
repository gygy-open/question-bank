"""成绩录入 (Assessment) 域领域服务 —— 第一期纵向切片。

只实现一条纵向能力:**从一个 shared 组稿定稿版本 + 班级创建 draft 考试**,并在同一事务中:
1. 从 snapshot v2 提取 question 节点 → ExamQuestion(composition_node_id/q_type/max_score);
2. 复制班级当前成员 → ExamParticipant(冻结姓名/学号);
3. 为每个参与者建 ExamResult(独立 revision);
4. 追加一条 ExamEvent。
任一步失败全部回滚。

错误约定(载体是 app.capabilities.errors 的 DomainError):
- 版本/班级不可见(跨学科)→ 404(防枚举)。
- personal 组稿版本 / 未启用评分 / 无题 / 缺分或分值非法 → 400。
- snapshot 结构损坏 → 422。
"""
import hashlib
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.capabilities.errors import Conflict, Invalid, NotFound, Unprocessable
from app.crud import crud_assessment
from app.models.assessment import (
    SCORE_SCALE,
    Classroom,
    ClassroomStudent,
    ExamAttendanceStatus,
    ExamEvent,
    ExamParticipant,
    ExamQuestion,
    ExamResult,
    ExamScoreItem,
    ExamSession,
    ExamSessionStatus,
    Student,
)
from app.models.composition import ScopeType
from app.models.user import User
from app.services import assessment_excel


def _to_score(raw: Any) -> Decimal:
    """把 snapshot 里的原始分值收敛为正的 Decimal;非法值抛 400。"""
    if raw is None or isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise Invalid("每道题必须设置合法的分值")
    score = Decimal(str(raw))
    if score <= 0:
        raise Invalid("题目分值必须大于 0")
    return score


def _extract_exam_questions(snapshot: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Decimal]:
    """从 snapshot v2 提取 question 节点投影与总分。"""
    nodes = snapshot.get("nodes")
    if not isinstance(nodes, list):
        raise Unprocessable("组稿定稿快照损坏:缺少节点列表")

    question_nodes = [n for n in nodes if isinstance(n, dict) and n.get("node_type") == "question"]
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
        items.append(
            {
                "composition_node_id": node_id,
                "q_type": q_type,
                "max_score": score,
                "position": position,
            }
        )

    if total <= 0:
        raise Invalid("组稿定稿版本的题目总分必须大于 0")
    return items, total


async def _write_event(
    db: AsyncSession,
    *,
    exam_session_id: int,
    actor_id: int,
    event_type: str,
    summary: str,
    payload: Dict[str, Any],
    target_type: str = "exam_session",
    target_id: Optional[str] = None,
    batch_id: Optional[str] = None,
) -> None:
    db.add(
        ExamEvent(
            exam_session_id=exam_session_id,
            event_type=event_type,
            target_type=target_type,
            target_id=target_id if target_id is not None else str(exam_session_id),
            summary=summary,
            payload=payload,
            batch_id=batch_id,
            actor_id=actor_id,
        )
    )


async def create_exam_session(
    db: AsyncSession,
    *,
    subject_id: int,
    composition_version_id: int,
    classroom_id: int,
    name: str,
    actor: User,
) -> ExamSession:
    """从一个 shared 组稿定稿版本 + 班级创建 draft 考试(单事务,失败全回滚)。"""
    version = await crud_assessment.assessment.get_version_with_composition(
        db, version_id=composition_version_id
    )
    # 跨学科/不存在一律 404(防枚举):route subject 与 version subject 必须一致。
    if version is None or version.subject_id != subject_id:
        raise NotFound("Composition version not found")

    # personal 组稿版本被拒绝。CompositionVersion 无 scope 字段,经 version.composition 判定。
    composition = version.composition
    if composition is None or composition.scope_type != ScopeType.SHARED:
        raise Invalid("只能基于共享(shared)组稿定稿版本创建考试")

    classroom = await crud_assessment.assessment.get_classroom(db, classroom_id=classroom_id)
    # 班级 subject 也必须与 route/version 一致,否则 404。
    if classroom is None or classroom.subject_id != subject_id:
        raise NotFound("Classroom not found")

    snapshot = version.snapshot
    if not isinstance(snapshot, dict):
        raise Unprocessable("组稿定稿快照损坏")
    if not snapshot.get("scoring_enabled"):
        raise Invalid("组稿定稿版本未启用赋分,无法创建考试")

    question_items, total_score = _extract_exam_questions(snapshot)
    members = await crud_assessment.assessment.list_classroom_members(
        db, classroom_id=classroom_id
    )

    try:
        session = ExamSession(
            subject_id=subject_id,
            composition_version_id=version.id,
            classroom_id=classroom.id,
            name=name,
            status=ExamSessionStatus.DRAFT.value,
            total_score=total_score,
            created_by=actor.id,
            updated_by=actor.id,
        )
        db.add(session)
        # 拿到 session.id 供后续 FK / 事件使用。
        await db.flush()

        for item in question_items:
            db.add(ExamQuestion(exam_session_id=session.id, **item))

        for member in members:
            student = member.student
            participant = ExamParticipant(
                exam_session=session,
                student_id=member.student_id,
                name=student.name,
                student_no=student.student_no,
            )
            db.add(participant)
            db.add(ExamResult(exam_session=session, participant=participant, revision=1))

        await _write_event(
            db,
            exam_session_id=session.id,
            actor_id=actor.id,
            event_type="created",
            summary=f"Created exam session from composition version {version.version_no}",
            payload={
                "composition_version_id": version.id,
                "classroom_id": classroom.id,
                "question_count": len(question_items),
                "participant_count": len(members),
                "total_score": str(total_score),
            },
        )

        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return await crud_assessment.assessment.get_session_detail(
        db, exam_session_id=session.id, subject_id=subject_id
    )


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
    """在学科下创建学生档案。student_no 学科内唯一;user_id 若给出须存在且未被占用。"""
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
    """整体替换班级成员(原子)。去重;跨学科/缺失学生 422;班级不存在/跨学科 404。"""
    classroom = await crud_assessment.assessment.get_classroom(
        db, classroom_id=classroom_id
    )
    if classroom is None or classroom.subject_id != subject_id:
        raise NotFound("Classroom not found")

    # 去重并保留顺序。
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
# 考试状态流转
# --------------------------------------------------------------------------- #
async def _transition_status(
    db: AsyncSession,
    *,
    session: ExamSession,
    from_status: ExamSessionStatus,
    to_status: ExamSessionStatus,
    actor: User,
) -> None:
    """乐观锁状态转换:条件 UPDATE 命中 0 行(状态或 revision 已变)则 409。"""
    upd = await db.execute(
        update(ExamSession)
        .where(
            ExamSession.id == session.id,
            ExamSession.status == from_status.value,
            ExamSession.revision == session.revision,
        )
        .values(
            status=to_status.value,
            revision=ExamSession.revision + 1,
            updated_by=actor.id,
        )
    )
    if upd.rowcount == 0:
        raise Conflict("考试状态已变更,请刷新后重试")


async def start_recording(
    db: AsyncSession, *, subject_id: int, exam_session_id: int, actor: User
) -> ExamSession:
    """draft → recording:要求至少一个参与者与一个题目。"""
    session = await crud_assessment.assessment.get_session_detail(
        db, exam_session_id=exam_session_id, subject_id=subject_id
    )
    if session is None:
        raise NotFound("Exam session not found")
    if session.status != ExamSessionStatus.DRAFT.value:
        raise Conflict("只有草稿状态的考试可以开始录入")
    if not session.participants:
        raise Invalid("考试没有参与者,无法开始录入")
    if not session.questions:
        raise Invalid("考试没有题目,无法开始录入")

    new_revision = session.revision + 1
    try:
        await _transition_status(
            db,
            session=session,
            from_status=ExamSessionStatus.DRAFT,
            to_status=ExamSessionStatus.RECORDING,
            actor=actor,
        )
        await _write_event(
            db,
            exam_session_id=session.id,
            actor_id=actor.id,
            event_type="recording_started",
            summary="Started recording",
            payload={"from": "draft", "to": "recording", "revision": new_revision},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return await crud_assessment.assessment.get_session_detail(
        db, exam_session_id=exam_session_id, subject_id=subject_id
    )


async def lock_exam_session(
    db: AsyncSession, *, subject_id: int, exam_session_id: int, actor: User
) -> ExamSession:
    """recording → locked:要求所有非缺考参与者每题均已录分(total_score 非空)。"""
    session = await crud_assessment.assessment.get_gradebook_session(
        db, exam_session_id=exam_session_id, subject_id=subject_id
    )
    if session is None:
        raise NotFound("Exam session not found")
    if session.status != ExamSessionStatus.RECORDING.value:
        raise Conflict("只有录入中的考试可以锁定")

    for participant in session.participants:
        if participant.attendance_status == ExamAttendanceStatus.ABSENT.value:
            continue
        result = participant.result
        if result is None or result.total_score is None:
            raise Invalid("存在未录满成绩的参与者,无法锁定")

    new_revision = session.revision + 1
    try:
        await _transition_status(
            db,
            session=session,
            from_status=ExamSessionStatus.RECORDING,
            to_status=ExamSessionStatus.LOCKED,
            actor=actor,
        )
        await _write_event(
            db,
            exam_session_id=session.id,
            actor_id=actor.id,
            event_type="locked",
            summary="Locked exam session",
            payload={"from": "recording", "to": "locked", "revision": new_revision},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return await crud_assessment.assessment.get_session_detail(
        db, exam_session_id=exam_session_id, subject_id=subject_id
    )


# --------------------------------------------------------------------------- #
# gradebook 读取
# --------------------------------------------------------------------------- #
def _question_read(question: ExamQuestion) -> Dict[str, Any]:
    return {
        "id": question.id,
        "composition_node_id": question.composition_node_id,
        "q_type": question.q_type,
        "max_score": question.max_score,
        "position": question.position,
    }


async def get_gradebook(
    db: AsyncSession, *, subject_id: int, exam_session_id: int
) -> Dict[str, Any]:
    """返回题目列 + 每个参与者的成绩矩阵(单班完整矩阵,结构便于未来分页)。"""
    session = await crud_assessment.assessment.get_gradebook_session(
        db, exam_session_id=exam_session_id, subject_id=subject_id
    )
    if session is None:
        raise NotFound("Exam session not found")

    questions = list(session.questions)
    rows: List[Dict[str, Any]] = []
    for participant in session.participants:
        result = participant.result
        scored = (
            {si.exam_question_id: si.score for si in result.score_items}
            if result is not None
            else {}
        )
        rows.append(
            {
                "participant_id": participant.id,
                "student_id": participant.student_id,
                "name": participant.name,
                "student_no": participant.student_no,
                "attendance_status": participant.attendance_status,
                "result_id": result.id if result is not None else None,
                "revision": result.revision if result is not None else 0,
                "total_score": result.total_score if result is not None else None,
                "is_complete": result is not None and result.total_score is not None,
                "scores": [
                    {"exam_question_id": q.id, "score": scored.get(q.id)}
                    for q in questions
                ],
            }
        )

    return {
        "exam_session_id": session.id,
        "status": session.status,
        "revision": session.revision,
        "total_score": session.total_score,
        "questions": [_question_read(q) for q in questions],
        "participants": rows,
    }


async def export_gradebook(
    db: AsyncSession, *, subject_id: int, exam_session_id: int
) -> bytes:
    session = await crud_assessment.assessment.get_gradebook_session(
        db, exam_session_id=exam_session_id, subject_id=subject_id
    )
    if session is None:
        raise NotFound("Exam session not found")
    return assessment_excel.generate_workbook(session)


async def preview_score_import(
    db: AsyncSession, *, subject_id: int, exam_session_id: int, file_bytes: bytes
) -> Dict[str, Any]:
    session = await crud_assessment.assessment.get_gradebook_session(
        db, exam_session_id=exam_session_id, subject_id=subject_id
    )
    if session is None:
        raise NotFound("Exam session not found")
    try:
        parsed = assessment_excel.parse_workbook(file_bytes, session)
    except ValueError as exc:
        raise Unprocessable(str(exc)) from exc
    return {
        "valid": not parsed.errors,
        "changed_rows": parsed.changed_rows,
        "changed_scores": parsed.changed_scores,
        "unchanged_rows": parsed.unchanged_rows,
        "errors": [error.__dict__ for error in parsed.errors],
    }


async def apply_score_import(
    db: AsyncSession,
    *,
    subject_id: int,
    exam_session_id: int,
    file_bytes: bytes,
    batch_id: str,
    actor: User,
) -> Dict[str, Any]:
    session = await crud_assessment.assessment.get_gradebook_session(
        db, exam_session_id=exam_session_id, subject_id=subject_id
    )
    if session is None:
        raise NotFound("Exam session not found")
    if session.status != ExamSessionStatus.RECORDING.value:
        raise Conflict("只有录入中的考试可以导入成绩")

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    existing_event = await crud_assessment.assessment.get_event_by_batch(
        db, exam_session_id=exam_session_id, batch_id=batch_id
    )
    if existing_event is not None:
        payload = existing_event.payload or {}
        if existing_event.event_type != "scores_imported" or payload.get("file_sha256") != file_hash:
            raise Conflict("batch_id 已用于其他成绩导入请求")
        return {
            "batch_id": batch_id,
            "updated_rows": payload["updated_rows"],
            "updated_scores": payload["updated_scores"],
        }

    try:
        parsed = assessment_excel.parse_workbook(file_bytes, session)
    except ValueError as exc:
        raise Unprocessable(str(exc)) from exc
    if parsed.errors:
        first = parsed.errors[0]
        raise Unprocessable(f"第 {first.row} 行 {first.field}: {first.message}")

    results = {participant.result.id: participant.result for participant in session.participants}
    try:
        for imported in parsed.rows:
            result = results[imported.result_id]
            existing_scores = {item.exam_question_id: item for item in result.score_items}
            changed = any(
                (existing_scores.get(question_id).score if existing_scores.get(question_id) else None) != score
                for question_id, score in imported.scores.items()
            )
            if not changed:
                continue
            revision_update = await db.execute(
                update(ExamResult)
                .where(
                    ExamResult.id == result.id,
                    ExamResult.revision == imported.expected_revision,
                )
                .values(revision=ExamResult.revision + 1)
            )
            if revision_update.rowcount == 0:
                raise Conflict("成绩版本冲突，请重新导出模板")
            for question_id, score in imported.scores.items():
                item = existing_scores.get(question_id)
                if item is None:
                    item = ExamScoreItem(
                        exam_result_id=result.id,
                        exam_question_id=question_id,
                        score=score,
                    )
                    db.add(item)
                    existing_scores[question_id] = item
                else:
                    item.score = score
            values = list(imported.scores.values())
            result.total_score = sum(values, Decimal("0")) if all(value is not None for value in values) else None
            result.revision = imported.expected_revision + 1

        await _write_event(
            db,
            exam_session_id=exam_session_id,
            actor_id=actor.id,
            event_type="scores_imported",
            summary="Imported scores from Excel",
            payload={
                "file_sha256": file_hash,
                "updated_rows": parsed.changed_rows,
                "updated_scores": parsed.changed_scores,
            },
            batch_id=batch_id,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {
        "batch_id": batch_id,
        "updated_rows": parsed.changed_rows,
        "updated_scores": parsed.changed_scores,
    }


# --------------------------------------------------------------------------- #
# 逐题成绩保存
# --------------------------------------------------------------------------- #
def _validate_item_score(score: Decimal, max_score: Decimal) -> Decimal:
    if score < 0:
        raise Invalid("分值不能为负")
    if score > max_score:
        raise Invalid(f"分值不能超过该题满分 {max_score}")
    exponent = score.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -SCORE_SCALE:
        raise Invalid("分值精度最多两位小数")
    return score


def _result_read(
    result: ExamResult, questions: List[ExamQuestion], scores_by_q: Dict[int, Optional[Decimal]]
) -> Dict[str, Any]:
    return {
        "result_id": result.id,
        "participant_id": result.participant_id,
        "revision": result.revision,
        "total_score": result.total_score,
        "is_complete": result.total_score is not None,
        "scores": [
            {"exam_question_id": q.id, "score": scores_by_q.get(q.id)}
            for q in questions
        ],
    }


async def save_scores(
    db: AsyncSession,
    *,
    subject_id: int,
    exam_session_id: int,
    result_id: int,
    expected_revision: int,
    batch_id: Optional[str],
    items: List[Dict[str, Any]],
    actor: User,
) -> Dict[str, Any]:
    """逐题录分(单事务,乐观锁 + batch_id 幂等)。"""
    session = await crud_assessment.assessment.get_session_detail(
        db, exam_session_id=exam_session_id, subject_id=subject_id
    )
    if session is None:
        raise NotFound("Exam session not found")

    result = await crud_assessment.assessment.get_result_for_scoring(
        db, result_id=result_id, exam_session_id=exam_session_id
    )
    if result is None:
        raise NotFound("Exam result not found")

    if session.status != ExamSessionStatus.RECORDING.value:
        raise Conflict("只有录入中的考试可以录入成绩")

    questions = list(session.questions)
    question_map = {q.id: q for q in questions}

    # 校验 items:去重、题目须属于本场次、分值范围与精度。
    seen: set[int] = set()
    normalized: List[Tuple[int, Optional[Decimal]]] = []
    for item in items:
        qid = item["exam_question_id"]
        if qid in seen:
            raise Invalid("同一次保存中题目 id 不能重复")
        seen.add(qid)
        question = question_map.get(qid)
        if question is None:
            raise Unprocessable("题目不属于该考试场次")
        score = item.get("score")
        if score is not None:
            score = _validate_item_score(Decimal(str(score)), question.max_score)
        normalized.append((qid, score))

    requested_items = [
        {
            "exam_question_id": qid,
            "score": str(score) if score is not None else None,
        }
        for qid, score in normalized
    ]

    # batch_id 只允许重放完全相同的请求，不能跨成绩行或换 payload 复用。
    if batch_id is not None:
        existing_event = await crud_assessment.assessment.get_event_by_batch(
            db, exam_session_id=exam_session_id, batch_id=batch_id
        )
        if existing_event is not None:
            payload = existing_event.payload or {}
            if (
                existing_event.target_type != "exam_result"
                or existing_event.target_id != str(result.id)
                or payload.get("expected_revision") != expected_revision
                or payload.get("requested_items") != requested_items
            ):
                raise Conflict("batch_id 已用于其他成绩保存请求")
            scores_by_q = {q.id: None for q in questions}
            for si in result.score_items:
                scores_by_q[si.exam_question_id] = si.score
            return _result_read(result, questions, scores_by_q)

    try:
        # 乐观锁:条件 UPDATE 命中 0 行则版本冲突。
        upd = await db.execute(
            update(ExamResult)
            .where(
                ExamResult.id == result.id,
                ExamResult.revision == expected_revision,
            )
            .values(revision=ExamResult.revision + 1)
        )
        if upd.rowcount == 0:
            raise Conflict("成绩版本冲突,请刷新后重试")

        existing_items = {si.exam_question_id: si for si in result.score_items}
        changes: List[Dict[str, Any]] = []
        for qid, score in normalized:
            si = existing_items.get(qid)
            old = si.score if si is not None else None
            if score is None:
                if si is not None:
                    si.score = None
            else:
                if si is None:
                    si = ExamScoreItem(
                        exam_result_id=result.id, exam_question_id=qid, score=score
                    )
                    db.add(si)
                    existing_items[qid] = si
                else:
                    si.score = score
            changes.append(
                {
                    "exam_question_id": qid,
                    "old": str(old) if old is not None else None,
                    "new": str(score) if score is not None else None,
                }
            )

        # 只有每题都已录才求和,否则 total 为 NULL。
        scores_by_q: Dict[int, Optional[Decimal]] = {}
        for question in questions:
            si = existing_items.get(question.id)
            scores_by_q[question.id] = si.score if si is not None else None
        if all(v is not None for v in scores_by_q.values()):
            total: Optional[Decimal] = sum(scores_by_q.values(), Decimal("0"))
        else:
            total = None

        new_revision = expected_revision + 1
        result.revision = new_revision
        result.total_score = total

        await _write_event(
            db,
            exam_session_id=exam_session_id,
            actor_id=actor.id,
            event_type="scores_saved",
            summary=f"Saved scores for result {result.id}",
            payload={
                "batch_id": batch_id,
                "expected_revision": expected_revision,
                "new_revision": new_revision,
                "total_score": str(total) if total is not None else None,
                "requested_items": requested_items,
                "changes": changes,
            },
            target_type="exam_result",
            target_id=str(result.id),
            batch_id=batch_id,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return _result_read(result, questions, scores_by_q)
