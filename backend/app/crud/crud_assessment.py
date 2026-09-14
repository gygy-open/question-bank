"""成绩录入 (Assessment) 域 CRUD —— 第二期纵向切片。

提供 scoped 读取:学生/班级名册、组稿定稿版本、考试详情、gradebook 与逐题录分所需的
带上下文加载。写路径的事务与领域不变量在 services/assessment_service.py。
"""
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.assessment import (
    Classroom,
    ClassroomStudent,
    ExamEvent,
    ExamParticipant,
    ExamResult,
    ExamSession,
    Student,
)
from app.models.composition import CompositionVersion


class CRUDAssessment:
    # ----------------------------------------------------------------- #
    # 学生名册
    # ----------------------------------------------------------------- #
    async def get_student(
        self, db: AsyncSession, *, student_id: int
    ) -> Optional[Student]:
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
        """学科内学生分页/搜索(按 student_no/name 模糊匹配)。"""
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
    async def get_classroom(
        self, db: AsyncSession, *, classroom_id: int
    ) -> Optional[Classroom]:
        result = await db.execute(
            select(Classroom).where(Classroom.id == classroom_id)
        )
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

    async def list_classrooms(
        self, db: AsyncSession, *, subject_id: int
    ) -> list[Classroom]:
        result = await db.execute(
            select(Classroom)
            .where(Classroom.subject_id == subject_id)
            .order_by(Classroom.id)
        )
        return list(result.scalars().all())

    async def list_classroom_members(
        self, db: AsyncSession, *, classroom_id: int
    ) -> list[ClassroomStudent]:
        """班级当前成员(预载 student 以冻结姓名/学号),按加入顺序。"""
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
        """班级当前成员对应的学生档案,按加入顺序。"""
        members = await self.list_classroom_members(db, classroom_id=classroom_id)
        return [m.student for m in members]

    # ----------------------------------------------------------------- #
    # 组稿定稿版本
    # ----------------------------------------------------------------- #
    async def get_version_with_composition(
        self, db: AsyncSession, *, version_id: int
    ) -> Optional[CompositionVersion]:
        """取组稿定稿版本并预载其 composition(用于判 scope 是否 personal)。"""
        result = await db.execute(
            select(CompositionVersion)
            .where(CompositionVersion.id == version_id)
            .options(selectinload(CompositionVersion.composition))
        )
        return result.scalars().first()

    # ----------------------------------------------------------------- #
    # 考试详情 / 状态流转 / gradebook
    # ----------------------------------------------------------------- #
    async def get_session_detail(
        self, db: AsyncSession, *, exam_session_id: int, subject_id: int
    ) -> Optional[ExamSession]:
        """按学科强上下文取考试详情(预载题目与参与者)。"""
        result = await db.execute(
            select(ExamSession)
            .where(
                ExamSession.id == exam_session_id,
                ExamSession.subject_id == subject_id,
            )
            .options(
                selectinload(ExamSession.questions),
                selectinload(ExamSession.participants),
            )
        )
        return result.scalars().first()

    async def get_session_scoped(
        self, db: AsyncSession, *, exam_session_id: int, subject_id: int
    ) -> Optional[ExamSession]:
        """按学科取考试(不预载,用于状态流转前的存在性校验)。"""
        result = await db.execute(
            select(ExamSession).where(
                ExamSession.id == exam_session_id,
                ExamSession.subject_id == subject_id,
            )
        )
        return result.scalars().first()

    async def list_sessions(
        self,
        db: AsyncSession,
        *,
        subject_id: int,
        status: Optional[str] = None,
        classroom_id: Optional[int] = None,
    ) -> list[ExamSession]:
        """按学科列出考试,支持状态/班级过滤,按创建时间倒序。"""
        stmt = select(ExamSession).where(ExamSession.subject_id == subject_id)
        if status is not None:
            stmt = stmt.where(ExamSession.status == status)
        if classroom_id is not None:
            stmt = stmt.where(ExamSession.classroom_id == classroom_id)
        stmt = stmt.order_by(ExamSession.created_at.desc(), ExamSession.id.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_gradebook_session(
        self, db: AsyncSession, *, exam_session_id: int, subject_id: int
    ) -> Optional[ExamSession]:
        """加载 gradebook 所需的完整矩阵:题目 + 参与者 + 成绩单 + 逐题得分。"""
        result = await db.execute(
            select(ExamSession)
            .where(
                ExamSession.id == exam_session_id,
                ExamSession.subject_id == subject_id,
            )
            .options(
                selectinload(ExamSession.questions),
                selectinload(ExamSession.participants).selectinload(
                    ExamParticipant.result
                ),
                selectinload(ExamSession.results).selectinload(ExamResult.score_items),
            )
        )
        return result.scalars().first()

    async def get_result_for_scoring(
        self, db: AsyncSession, *, result_id: int, exam_session_id: int
    ) -> Optional[ExamResult]:
        """录分场景:取成绩单并预载逐题得分(限定同场次)。"""
        result = await db.execute(
            select(ExamResult)
            .where(
                ExamResult.id == result_id,
                ExamResult.exam_session_id == exam_session_id,
            )
            .options(selectinload(ExamResult.score_items))
        )
        return result.scalars().first()

    async def get_event_by_batch(
        self, db: AsyncSession, *, exam_session_id: int, batch_id: str
    ) -> Optional[ExamEvent]:
        result = await db.execute(
            select(ExamEvent).where(
                ExamEvent.exam_session_id == exam_session_id,
                ExamEvent.batch_id == batch_id,
            )
        )
        return result.scalars().first()

    async def count_participants(
        self, db: AsyncSession, *, exam_session_id: int
    ) -> int:
        total = await db.scalar(
            select(func.count())
            .select_from(ExamParticipant)
            .where(ExamParticipant.exam_session_id == exam_session_id)
        )
        return int(total or 0)


assessment = CRUDAssessment()
