"""成绩录入 (Assessment / Gradebook) 领域模型 —— 第一期基础表。

设计要点(与已确认 ADR 对齐):
- 成绩录入建立在**组稿定稿**之上:一场考试(ExamSession)必须绑定一个不可变的
  CompositionVersion(snapshot v2)。题目清单从该 snapshot 定稿时刻冻结,之后组稿再改
  不影响已开考的考试。
- Student 是独立档案:user_id 可空(校内学生未必是系统用户)。学生按 subject 强上下文
  隔离,student_no 在学科内唯一。
- Classroom 是学科作用域下的班级/群组;ClassroomStudent 为班级成员关系。
- ExamSession 开考时把**当前**班级成员冻结为 ExamParticipant(姓名/学号快照),此后
  班级成员变动不影响已开考的考试。
- ExamQuestion 保存 snapshot v2 中每个 question 节点的定稿投影:composition_node_id /
  q_type / max_score。
- ExamResult 每个参与者一行,携带独立 revision(录入乐观锁 / 审计基准)。
- ExamScoreItem 是逐题事实(participant × question 的得分)。
- ExamEvent 追加式审计,独立于 activity_logs 与 composition_events。

金额/分值一律用 Numeric(6, 2)(Decimal),不用 Float,避免二进制浮点误差。
"""
import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .base import Base

# BigInteger 供 MySQL 大容量自增 PK;SQLite 退化为 INTEGER 以保留 rowid 自增语义。
_BigIntPK = BigInteger().with_variant(Integer(), "sqlite")

# 分值统一精度:最多 6 位、2 位小数(0.00 ~ 9999.99)。
SCORE_PRECISION = 6
SCORE_SCALE = 2


def _score_col(*, nullable: bool) -> Column:
    return Column(Numeric(SCORE_PRECISION, SCORE_SCALE), nullable=nullable)


class ExamSessionStatus(str, enum.Enum):
    """考试生命周期。draft→recording→locked;archived 预留。"""
    DRAFT = "draft"
    RECORDING = "recording"
    LOCKED = "locked"
    ARCHIVED = "archived"


class ExamAttendanceStatus(str, enum.Enum):
    """参与者出勤状态。缺考(absent)在锁定时不要求录满分数。"""
    PRESENT = "present"
    ABSENT = "absent"


def _enum_col(enum_cls: type[enum.Enum]):
    """按仓库惯例:以 value(而非 name)持久化枚举。"""
    from sqlalchemy import Enum

    return Enum(enum_cls, values_callable=lambda obj: [e.value for e in obj])


class Student(Base):
    """学生档案:独立于系统用户(user_id 可空),按学科隔离。"""
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    # 校内学生未必登录系统;绑定系统用户时非空。
    user_id = Column(Integer, ForeignKey("user.id"), nullable=True, index=True)
    student_no = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    subject = relationship("Subject")
    user = relationship("User", foreign_keys=[user_id])
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    __table_args__ = (
        UniqueConstraint("subject_id", "student_no", name="student_no_per_subject"),
        # 同一账号在同一学科内最多映射一个学生档案(user_id 可空,NULL 不参与唯一)。
        UniqueConstraint("subject_id", "user_id", name="student_user_per_subject"),
    )


class Classroom(Base):
    """班级/群组:学科作用域下的学生集合。"""
    __tablename__ = "classrooms"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    subject = relationship("Subject")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    members = relationship(
        "ClassroomStudent",
        back_populates="classroom",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("subject_id", "name", name="classroom_name_per_subject"),
    )


class ClassroomStudent(Base):
    """班级-学生成员关系。"""
    __tablename__ = "classroom_students"

    id = Column(Integer, primary_key=True, index=True)
    classroom_id = Column(
        Integer, ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id = Column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    classroom = relationship("Classroom", back_populates="members")
    student = relationship("Student")

    __table_args__ = (
        UniqueConstraint("classroom_id", "student_id", name="student_per_classroom"),
    )


class ExamSession(Base):
    """一场考试:绑定不可变的组稿定稿版本,面向某个班级。"""
    __tablename__ = "exam_sessions"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    # 必须绑定组稿定稿版本(snapshot v2);题目清单由该 snapshot 冻结。
    composition_version_id = Column(
        Integer, ForeignKey("composition_versions.id"), nullable=False, index=True
    )
    classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=False, index=True)

    name = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default=ExamSessionStatus.DRAFT.value)
    # 状态机乐观锁:每次状态转换自增,防并发重复推进。
    revision = Column(Integer, nullable=False, default=1)
    # 定稿题目分值合计(创建时按 snapshot 计算冻结)。
    total_score = _score_col(nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    subject = relationship("Subject")
    composition_version = relationship("CompositionVersion")
    classroom = relationship("Classroom")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    questions = relationship(
        "ExamQuestion",
        back_populates="exam_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ExamQuestion.position",
    )
    participants = relationship(
        "ExamParticipant",
        back_populates="exam_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ExamParticipant.id",
    )
    results = relationship(
        "ExamResult",
        back_populates="exam_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    events = relationship(
        "ExamEvent",
        back_populates="exam_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ExamEvent.id",
    )

    __table_args__ = (
        CheckConstraint("total_score > 0", name="total_score_positive"),
        CheckConstraint("revision >= 1", name="exam_session_revision_positive"),
        Index("ix_exam_sessions_subject_classroom", "subject_id", "classroom_id"),
    )


class ExamQuestion(Base):
    """考试题目:snapshot v2 中每个 question 节点的定稿投影。"""
    __tablename__ = "exam_questions"

    id = Column(Integer, primary_key=True, index=True)
    exam_session_id = Column(
        Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # snapshot 内 question 节点的稳定 id(String(36) UUID),定位定稿题目。
    composition_node_id = Column(String(36), nullable=False)
    q_type = Column(String(64), nullable=False)
    max_score = _score_col(nullable=False)
    # 定稿前序展平后的题目序号(0-based)。
    position = Column(Integer, nullable=False)

    exam_session = relationship("ExamSession", back_populates="questions")
    score_items = relationship(
        "ExamScoreItem",
        back_populates="exam_question",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("max_score > 0", name="max_score_positive"),
        CheckConstraint("position >= 0", name="position_non_negative"),
        UniqueConstraint("exam_session_id", "composition_node_id", name="question_per_session"),
        Index("ix_exam_questions_session_pos", "exam_session_id", "position"),
    )


class ExamParticipant(Base):
    """考试参与者:开考时冻结的学生姓名/学号快照。"""
    __tablename__ = "exam_participants"

    id = Column(Integer, primary_key=True, index=True)
    exam_session_id = Column(
        Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 保留档案指针便于回溯;学生档案删除后置空,但冻结的姓名/学号仍留存。
    student_id = Column(Integer, ForeignKey("students.id", ondelete="SET NULL"), nullable=True)
    # 冻结快照:开考时刻的姓名与学号,不随档案后续变更而变。
    name = Column(String(255), nullable=False)
    student_no = Column(String(64), nullable=False)
    # 出勤状态:首期默认 present;缺考者锁定时不要求录满分数。
    attendance_status = Column(
        String(20), nullable=False, default=ExamAttendanceStatus.PRESENT.value
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    exam_session = relationship("ExamSession", back_populates="participants")
    student = relationship("Student")
    result = relationship(
        "ExamResult",
        back_populates="participant",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("exam_session_id", "student_id", name="participant_per_session"),
        Index("ix_exam_participants_session", "exam_session_id", "id"),
    )


class ExamResult(Base):
    """一名参与者的成绩单:携带独立 revision(录入乐观锁 / 审计基准)。"""
    __tablename__ = "exam_results"

    id = Column(Integer, primary_key=True, index=True)
    exam_session_id = Column(
        Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    participant_id = Column(
        Integer, ForeignKey("exam_participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 独立于 ExamSession:每次录入变更自增,用于乐观锁与审计。
    revision = Column(Integer, nullable=False, default=1)
    # 逐题得分合计;未录入时为 NULL。
    total_score = _score_col(nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    exam_session = relationship("ExamSession", back_populates="results")
    participant = relationship("ExamParticipant", back_populates="result")
    score_items = relationship(
        "ExamScoreItem",
        back_populates="exam_result",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        UniqueConstraint("participant_id", name="result_per_participant"),
    )


class ExamScoreItem(Base):
    """逐题事实:一名参与者在一道题上的得分。"""
    __tablename__ = "exam_score_items"

    id = Column(Integer, primary_key=True, index=True)
    exam_result_id = Column(
        Integer, ForeignKey("exam_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exam_question_id = Column(
        Integer, ForeignKey("exam_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 未录入时为 NULL。
    score = _score_col(nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    exam_result = relationship("ExamResult", back_populates="score_items")
    exam_question = relationship("ExamQuestion", back_populates="score_items")

    __table_args__ = (
        CheckConstraint("score IS NULL OR score >= 0", name="score_non_negative"),
        UniqueConstraint("exam_result_id", "exam_question_id", name="score_per_result_question"),
    )


class ExamEvent(Base):
    """考试时间线事件,追加式审计,独立于 activity_logs / composition_events。"""
    __tablename__ = "exam_events"

    id = Column(_BigIntPK, primary_key=True)
    exam_session_id = Column(
        Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type = Column(String(50), nullable=False)
    target_type = Column(String(50), nullable=True)
    target_id = Column(String(64), nullable=True)
    summary = Column(String(255), nullable=False)
    payload = Column(JSON, nullable=True)
    # 幂等键:同一 (session, batch_id) 只允许一条事件(NULL 不参与唯一,可重复)。
    batch_id = Column(String(64), nullable=True)

    actor_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    exam_session = relationship("ExamSession", back_populates="events")
    actor = relationship("User", foreign_keys=[actor_id])

    __table_args__ = (
        UniqueConstraint("exam_session_id", "batch_id", name="exam_event_batch_per_session"),
        Index("ix_exam_events_session_id", "exam_session_id", "id"),
        Index("ix_exam_events_actor_created", "actor_id", "created_at"),
    )
