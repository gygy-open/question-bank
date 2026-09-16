"""通用评测 (Assessment) 域 CRUD。

提供 scoped 读取:学生/班级名册、组稿定稿版本 provenance、评测身份/版本/条目、
投放 session、作答 attempt(经 participation 推导 session)与 gradebook 所需的带上下文加载。
写路径的事务与领域不变量在 services/assessment_service.py。
"""
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.assessment import (
    Assessment,
    AssessmentAttempt,
    AssessmentEvent,
    AssessmentItem,
    AssessmentParticipation,
    AssessmentResponse,
    AssessmentSession,
    AssessmentVersion,
    Classroom,
    ClassroomStudent,
    Student,
)
from app.models.composition import CompositionVersion


class CRUDAssessment:
    # ----------------------------------------------------------------- #
    # 学生名册
    # ----------------------------------------------------------------- #
    async def get_student(self, db: AsyncSession, *, student_id: int) -> Optional[Student]:
        result = await db.execute(select(Student).where(Student.id == student_id))
        return result.scalars().first()

    async def get_student_by_no(
        self, db: AsyncSession, *, subject_id: int, student_no: str
    ) -> Optional[Student]:
        result = await db.execute(
            select(Student).where(
                Student.subject_id == subject_id, Student.student_no == student_no
            )
        )
        return result.scalars().first()

    async def get_student_by_user(
        self, db: AsyncSession, *, subject_id: int, user_id: int
    ) -> Optional[Student]:
        result = await db.execute(
            select(Student).where(
                Student.subject_id == subject_id, Student.user_id == user_id
            )
        )
        return result.scalars().first()

    async def list_students(
        self,
        db: AsyncSession,
        *,
        subject_id: int,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Student], int]:
        base = select(Student).where(Student.subject_id == subject_id)
        if keyword:
            like = f"%{keyword}%"
            base = base.where(
                (Student.student_no.ilike(like)) | (Student.name.ilike(like))
            )
        total = await db.scalar(
            select(func.count()).select_from(base.order_by(None).subquery())
        )
        rows = await db.execute(
            base.order_by(Student.id).offset((page - 1) * page_size).limit(page_size)
        )
        return list(rows.scalars().all()), int(total or 0)

    async def list_students_by_ids(
        self, db: AsyncSession, *, student_ids: Sequence[int]
    ) -> list[Student]:
        if not student_ids:
            return []
        result = await db.execute(
            select(Student).where(Student.id.in_(list(student_ids)))
        )
        return list(result.scalars().all())

    # ----------------------------------------------------------------- #
    # 班级名册
    # ----------------------------------------------------------------- #
    async def get_classroom(self, db: AsyncSession, *, classroom_id: int) -> Optional[Classroom]:
        result = await db.execute(select(Classroom).where(Classroom.id == classroom_id))
        return result.scalars().first()

    async def get_classroom_by_name(
        self, db: AsyncSession, *, subject_id: int, name: str
    ) -> Optional[Classroom]:
        result = await db.execute(
            select(Classroom).where(
                Classroom.subject_id == subject_id, Classroom.name == name
            )
        )
        return result.scalars().first()

    async def list_classrooms(self, db: AsyncSession, *, subject_id: int) -> list[Classroom]:
        result = await db.execute(
            select(Classroom).where(Classroom.subject_id == subject_id).order_by(Classroom.id)
        )
        return list(result.scalars().all())

    async def list_classroom_members(
        self, db: AsyncSession, *, classroom_id: int
    ) -> list[ClassroomStudent]:
        result = await db.execute(
            select(ClassroomStudent)
            .where(ClassroomStudent.classroom_id == classroom_id)
            .options(selectinload(ClassroomStudent.student))
            .order_by(ClassroomStudent.id)
        )
        return list(result.scalars().all())

    async def list_classroom_students(
        self, db: AsyncSession, *, classroom_id: int
    ) -> list[Student]:
        members = await self.list_classroom_members(db, classroom_id=classroom_id)
        return [m.student for m in members]

    # ----------------------------------------------------------------- #
    # 组稿定稿版本(provenance)
    # ----------------------------------------------------------------- #
    async def get_version_with_composition(
        self, db: AsyncSession, *, version_id: int
    ) -> Optional[CompositionVersion]:
        result = await db.execute(
            select(CompositionVersion)
            .where(CompositionVersion.id == version_id)
            .options(selectinload(CompositionVersion.composition))
        )
        return result.scalars().first()

    # ----------------------------------------------------------------- #
    # 评测身份 / 版本 / 条目
    # ----------------------------------------------------------------- #
    async def get_assessment(
        self, db: AsyncSession, *, assessment_id: int, subject_id: int
    ) -> Optional[Assessment]:
        result = await db.execute(
            select(Assessment)
            .where(Assessment.id == assessment_id, Assessment.subject_id == subject_id)
            .options(selectinload(Assessment.versions).selectinload(AssessmentVersion.items))
        )
        return result.scalars().first()

    async def list_assessments(
        self, db: AsyncSession, *, subject_id: int, status: Optional[str] = None
    ) -> list[Assessment]:
        stmt = select(Assessment).where(Assessment.subject_id == subject_id)
        if status is not None:
            stmt = stmt.where(Assessment.status == status)
        stmt = stmt.order_by(Assessment.created_at.desc(), Assessment.id.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_current_version(
        self, db: AsyncSession, *, assessment_id: int
    ) -> Optional[AssessmentVersion]:
        """当前版本 = version_no 最大的那一版(预载 items)。"""
        result = await db.execute(
            select(AssessmentVersion)
            .where(AssessmentVersion.assessment_id == assessment_id)
            .order_by(AssessmentVersion.version_no.desc())
            .options(selectinload(AssessmentVersion.items))
            .limit(1)
        )
        return result.scalars().first()

    async def get_version(
        self, db: AsyncSession, *, version_id: int
    ) -> Optional[AssessmentVersion]:
        result = await db.execute(
            select(AssessmentVersion)
            .where(AssessmentVersion.id == version_id)
            .options(selectinload(AssessmentVersion.items))
        )
        return result.scalars().first()

    async def max_version_no(self, db: AsyncSession, *, assessment_id: int) -> int:
        value = await db.scalar(
            select(func.max(AssessmentVersion.version_no)).where(
                AssessmentVersion.assessment_id == assessment_id
            )
        )
        return int(value or 0)

    # ----------------------------------------------------------------- #
    # 投放 session
    # ----------------------------------------------------------------- #
    async def get_session_scoped(
        self, db: AsyncSession, *, session_id: int, subject_id: int
    ) -> Optional[AssessmentSession]:
        result = await db.execute(
            select(AssessmentSession).where(
                AssessmentSession.id == session_id,
                AssessmentSession.subject_id == subject_id,
            )
        )
        return result.scalars().first()

    async def get_session_detail(
        self, db: AsyncSession, *, session_id: int, subject_id: int
    ) -> Optional[AssessmentSession]:
        """投放详情:预载 version+items 与参与者+attempts。"""
        result = await db.execute(
            select(AssessmentSession)
            .where(
                AssessmentSession.id == session_id,
                AssessmentSession.subject_id == subject_id,
            )
            .options(
                selectinload(AssessmentSession.version).selectinload(AssessmentVersion.items),
                selectinload(AssessmentSession.version).selectinload(AssessmentVersion.assessment),
                selectinload(AssessmentSession.participations).selectinload(
                    AssessmentParticipation.attempts
                ),
            )
        )
        return result.scalars().first()

    async def get_gradebook_session(
        self, db: AsyncSession, *, session_id: int, subject_id: int
    ) -> Optional[AssessmentSession]:
        """gradebook 完整矩阵:version+items + 参与者 + attempts + responses + 每个 response 的评分历史。"""
        result = await db.execute(
            select(AssessmentSession)
            .where(
                AssessmentSession.id == session_id,
                AssessmentSession.subject_id == subject_id,
            )
            .options(
                selectinload(AssessmentSession.version).selectinload(AssessmentVersion.items),
                selectinload(AssessmentSession.participations)
                .selectinload(AssessmentParticipation.attempts)
                .selectinload(AssessmentAttempt.responses)
                .selectinload(AssessmentResponse.grades),
            )
        )
        return result.scalars().first()

    async def list_sessions(
        self,
        db: AsyncSession,
        *,
        subject_id: int,
        grading_status: Optional[str] = None,
        assessment_id: Optional[int] = None,
    ) -> list[AssessmentSession]:
        stmt = (
            select(AssessmentSession)
            .join(AssessmentVersion, AssessmentSession.version_id == AssessmentVersion.id)
            .where(AssessmentSession.subject_id == subject_id)
            .options(
                selectinload(AssessmentSession.version).selectinload(AssessmentVersion.assessment)
            )
        )
        if grading_status is not None:
            stmt = stmt.where(AssessmentSession.grading_status == grading_status)
        if assessment_id is not None:
            stmt = stmt.where(AssessmentVersion.assessment_id == assessment_id)
        stmt = stmt.order_by(AssessmentSession.created_at.desc(), AssessmentSession.id.desc())
        result = await db.execute(stmt)
        return list(result.scalars().unique().all())

    async def count_session_participations(
        self, db: AsyncSession, *, session_id: int
    ) -> int:
        total = await db.scalar(
            select(func.count())
            .select_from(AssessmentParticipation)
            .where(AssessmentParticipation.session_id == session_id)
        )
        return int(total or 0)

    # ----------------------------------------------------------------- #
    # 作答 attempt(经 participation 推导 session)
    # ----------------------------------------------------------------- #
    async def get_attempt_for_grading(
        self, db: AsyncSession, *, attempt_id: int, subject_id: int
    ) -> Optional[AssessmentAttempt]:
        """录分场景:取 attempt 并预载 participation→session、version+items、responses+grades。"""
        result = await db.execute(
            select(AssessmentAttempt)
            .join(
                AssessmentParticipation,
                AssessmentAttempt.participation_id == AssessmentParticipation.id,
            )
            .join(
                AssessmentSession,
                AssessmentParticipation.session_id == AssessmentSession.id,
            )
            .where(
                AssessmentAttempt.id == attempt_id,
                AssessmentSession.subject_id == subject_id,
            )
            .options(
                selectinload(AssessmentAttempt.participation)
                .selectinload(AssessmentParticipation.session)
                .selectinload(AssessmentSession.version)
                .selectinload(AssessmentVersion.items),
                selectinload(AssessmentAttempt.responses).selectinload(
                    AssessmentResponse.grades
                ),
            )
        )
        return result.scalars().first()

    async def get_event_by_batch(
        self, db: AsyncSession, *, session_id: int, batch_id: str
    ) -> Optional[AssessmentEvent]:
        result = await db.execute(
            select(AssessmentEvent).where(
                AssessmentEvent.session_id == session_id,
                AssessmentEvent.batch_id == batch_id,
            )
        )
        return result.scalars().first()


assessment = CRUDAssessment()
