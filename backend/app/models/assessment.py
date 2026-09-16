"""通用评测 (Assessment) 领域模型。

设计要点(与已确认 ADR 对齐):

身份 / 版本 / 条目
- **Assessment** 是可编辑身份:subject/title/description/status + 审计。它本身不含题目,
  题目冻结在不可变的 AssessmentVersion 上。
- **AssessmentVersion** 不可变:(assessment_id, version_no) 唯一;当前版本按 version_no
  查询(不放 current_version_id 以免循环 FK)。可空 composition_version_id 记录 provenance,
  source_type 为字符串、source_ref 为 JSON,可携带 snapshot / total_score / item_count。
- **AssessmentItem** 归属 version:item_key/position/可空 parent_item_id;自有 item_type/
  max_score;source_question_id(SET NULL)/source_question_revision/source_node_id 仅作
  provenance,不作为运行时依赖;prompt_snapshot / response_spec / scoring_spec(私有)/
  metadata_snapshot 均为 JSON。

投放 / 参与 / 作答 / 评分
- **AssessmentSession** 绑定一个 version:subject/name、delivery_status(draft/open/closed)、
  grading_status(not_started/in_progress/finalized)、opens/closes、attempt_limit/settings/
  revision/archive/审计。线下默认 closed + not_started。
- **AssessmentParticipation** 归属 session:participant_key、student_id(SET NULL)/user_id
  (SET NULL)/external_ref/display_name/identifier、attendance_status、status、metadata;
  unique(session, participant_key)。
- **AssessmentAttempt** 只经 participation 推导 session(不冗余 session_id):attempt_no/mode/
  status/revision/total_score/max_score/answered_count/graded_count/时间戳/metadata;
  unique(participation, attempt_no)。
- **AssessmentResponse**:unique(attempt, item);answer_payload(JSON,可空)/schema_version/
  status/时间戳/revision。线下录分允许懒建空 Response。
- **ResponseGrade** 追加式:每次改分新增一行(不 UPDATE 历史);(response_id, revision) 唯一;
  status/outcome/score/max_score/grading_method/grader/scoring_details/feedback/graded_at/
  supersedes_grade_id。
- **AssessmentEvent** 通用追加审计:按 session 作用域,batch_id 幂等。

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
    Text,
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


# --------------------------------------------------------------------------- #
# 枚举(以 value 持久化为字符串,DB 侧不建 native ENUM 以便 MySQL/SQLite 一致)
# --------------------------------------------------------------------------- #
class AssessmentStatus(str, enum.Enum):
    """评测身份生命周期。"""
    ACTIVE = "active"
    ARCHIVED = "archived"


class DeliveryStatus(str, enum.Enum):
    """投放状态。线下默认 closed。"""
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"


class GradingStatus(str, enum.Enum):
    """评分状态。线下默认 not_started;finalized 之后只读。"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    FINALIZED = "finalized"


class AttendanceStatus(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    EXCUSED = "excused"


class ParticipationStatus(str, enum.Enum):
    INVITED = "invited"
    ACTIVE = "active"
    COMPLETED = "completed"
    WITHDRAWN = "withdrawn"


class AttemptMode(str, enum.Enum):
    OFFLINE = "offline"
    ONLINE = "online"


class AttemptStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    GRADING = "grading"
    GRADED = "graded"
    VOID = "void"


class ResponseStatus(str, enum.Enum):
    UNANSWERED = "unanswered"
    ANSWERED = "answered"
    OMITTED = "omitted"


class GradeStatus(str, enum.Enum):
    PENDING = "pending"
    GRADED = "graded"
    INVALIDATED = "invalidated"


class GradeOutcome(str, enum.Enum):
    CORRECT = "correct"
    PARTIAL = "partial"
    INCORRECT = "incorrect"
    UNSCORED = "unscored"


class GradingMethod(str, enum.Enum):
    MANUAL = "manual"
    IMPORTED = "imported"
    AUTOMATIC = "automatic"
    EXTERNAL = "external"


# --------------------------------------------------------------------------- #
# 名册(保留既有表与行为)
# --------------------------------------------------------------------------- #
class Student(Base):
    """学生档案:独立于系统用户(user_id 可空),按学科隔离。"""
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
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


# --------------------------------------------------------------------------- #
# 评测身份 / 版本 / 条目
# --------------------------------------------------------------------------- #
class Assessment(Base):
    """可编辑的评测身份;题目冻结在不可变的 AssessmentVersion 上。"""
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default=AssessmentStatus.ACTIVE.value)
    revision = Column(Integer, nullable=False, default=1)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    subject = relationship("Subject")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    versions = relationship(
        "AssessmentVersion",
        back_populates="assessment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssessmentVersion.version_no",
    )

    __table_args__ = (
        CheckConstraint("revision >= 1", name="assessment_revision_positive"),
        CheckConstraint(
            "status IN ('active', 'archived')", name="assessment_status_valid"
        ),
        Index("ix_assessments_subject_status", "subject_id", "status"),
    )


class AssessmentVersion(Base):
    """评测的不可变版本:题目条目冻结于此,provenance 可空。"""
    __tablename__ = "assessment_versions"

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(
        Integer, ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_no = Column(Integer, nullable=False)
    # provenance:可空,不作为运行时依赖(来源被删也不影响冻结投影)。
    composition_version_id = Column(
        Integer,
        ForeignKey("composition_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_type = Column(String(32), nullable=False)
    source_ref = Column(JSON, nullable=True)
    snapshot = Column(JSON, nullable=False)
    total_score = _score_col(nullable=False)
    item_count = Column(Integer, nullable=False)
    schema_version = Column(Integer, nullable=False, default=1)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    assessment = relationship("Assessment", back_populates="versions")
    composition_version = relationship("CompositionVersion")
    creator = relationship("User", foreign_keys=[created_by])
    items = relationship(
        "AssessmentItem",
        back_populates="version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssessmentItem.position",
    )
    sessions = relationship(
        "AssessmentSession",
        back_populates="version",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("assessment_id", "version_no", name="assessment_version_no"),
        CheckConstraint("version_no >= 1", name="assessment_version_no_positive"),
        CheckConstraint("total_score > 0", name="assessment_version_total_positive"),
        CheckConstraint("item_count > 0", name="assessment_version_item_count_positive"),
        CheckConstraint(
            "schema_version >= 1", name="assessment_version_schema_version_positive"
        ),
    )


class AssessmentItem(Base):
    """归属 version 的可评分条目;来源指针仅作 provenance,不作运行时依赖。"""
    __tablename__ = "assessment_items"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(
        Integer, ForeignKey("assessment_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_key = Column(String(64), nullable=False)
    position = Column(Integer, nullable=False)
    # 自引用父指针:嵌套条目;来源版本整体删除时随 version 级联。
    parent_item_id = Column(
        Integer, ForeignKey("assessment_items.id", ondelete="SET NULL"), nullable=True
    )

    item_type = Column(String(64), nullable=False)
    max_score = _score_col(nullable=False)

    # provenance(不作运行时依赖):
    source_question_id = Column(
        Integer, ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )
    source_question_revision = Column(Integer, nullable=True)
    source_node_id = Column(String(36), nullable=True)

    prompt_snapshot = Column(JSON, nullable=False)
    response_spec = Column(JSON, nullable=False)
    # 私有:评分标准不进普通 DTO。
    scoring_spec = Column(JSON, nullable=False)
    metadata_snapshot = Column(JSON, nullable=True)
    schema_version = Column(Integer, nullable=False, default=1)

    version = relationship("AssessmentVersion", back_populates="items")
    source_question = relationship("Question")
    parent = relationship("AssessmentItem", remote_side=[id])

    __table_args__ = (
        UniqueConstraint("version_id", "item_key", name="item_key_per_version"),
        CheckConstraint("max_score > 0", name="assessment_item_max_score_positive"),
        CheckConstraint("position >= 0", name="assessment_item_position_non_negative"),
        CheckConstraint(
            "schema_version >= 1", name="assessment_item_schema_version_positive"
        ),
        Index("ix_assessment_items_version_pos", "version_id", "position"),
    )


# --------------------------------------------------------------------------- #
# 投放 / 参与 / 作答 / 评分
# --------------------------------------------------------------------------- #
class AssessmentSession(Base):
    """一次投放:绑定不可变 version,携带投放/评分状态机。"""
    __tablename__ = "assessment_sessions"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(
        Integer, ForeignKey("assessment_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)

    delivery_status = Column(String(20), nullable=False, default=DeliveryStatus.CLOSED.value)
    grading_status = Column(String(20), nullable=False, default=GradingStatus.NOT_STARTED.value)
    opens_at = Column(DateTime, nullable=True)
    closes_at = Column(DateTime, nullable=True)
    attempt_limit = Column(Integer, nullable=True)
    settings = Column(JSON, nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    archived_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    version = relationship("AssessmentVersion", back_populates="sessions")
    subject = relationship("Subject")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    participations = relationship(
        "AssessmentParticipation",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssessmentParticipation.id",
    )
    events = relationship(
        "AssessmentEvent",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssessmentEvent.id",
    )

    __table_args__ = (
        CheckConstraint("revision >= 1", name="assessment_session_revision_positive"),
        CheckConstraint(
            "attempt_limit IS NULL OR attempt_limit >= 1", name="assessment_session_attempt_limit_positive"
        ),
        CheckConstraint(
            "delivery_status IN ('draft', 'open', 'closed')",
            name="assessment_session_delivery_status_valid",
        ),
        CheckConstraint(
            "grading_status IN ('not_started', 'in_progress', 'finalized')",
            name="assessment_session_grading_status_valid",
        ),
        Index("ix_assessment_sessions_subject_status", "subject_id", "grading_status"),
    )


class AssessmentParticipation(Base):
    """归属 session 的参与者(冻结显示名/标识),名册指针 SET NULL 保留冻结快照。"""
    __tablename__ = "assessment_participations"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("assessment_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    participant_key = Column(String(64), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    external_ref = Column(String(128), nullable=True)
    display_name = Column(String(255), nullable=True)
    identifier = Column(String(128), nullable=True)
    attendance_status = Column(String(20), nullable=False, default=AttendanceStatus.PRESENT.value)
    status = Column(String(20), nullable=False, default=ParticipationStatus.ACTIVE.value)
    # 属性避开 Base.metadata 命名冲突;DB 列名为 metadata。
    participant_metadata = Column("metadata", JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    session = relationship("AssessmentSession", back_populates="participations")
    student = relationship("Student")
    user = relationship("User", foreign_keys=[user_id])
    attempts = relationship(
        "AssessmentAttempt",
        back_populates="participation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AssessmentAttempt.attempt_no",
    )

    __table_args__ = (
        UniqueConstraint("session_id", "participant_key", name="participant_key_per_session"),
        CheckConstraint(
            "attendance_status IN ('present', 'absent', 'excused')",
            name="assessment_participation_attendance_valid",
        ),
        CheckConstraint(
            "status IN ('invited', 'active', 'completed', 'withdrawn')",
            name="assessment_participation_status_valid",
        ),
        Index("ix_assessment_participations_session", "session_id", "id"),
    )


class AssessmentAttempt(Base):
    """一次作答:仅经 participation 推导 session(不冗余 session_id)。"""
    __tablename__ = "assessment_attempts"

    id = Column(Integer, primary_key=True, index=True)
    participation_id = Column(
        Integer,
        ForeignKey("assessment_participations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_no = Column(Integer, nullable=False)
    mode = Column(String(16), nullable=False, default=AttemptMode.OFFLINE.value)
    status = Column(String(20), nullable=False, default=AttemptStatus.NOT_STARTED.value)
    revision = Column(Integer, nullable=False, default=1)
    total_score = _score_col(nullable=True)
    max_score = _score_col(nullable=True)
    answered_count = Column(Integer, nullable=False, default=0)
    graded_count = Column(Integer, nullable=False, default=0)

    started_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    graded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    attempt_metadata = Column("metadata", JSON, nullable=True)

    participation = relationship("AssessmentParticipation", back_populates="attempts")
    responses = relationship(
        "AssessmentResponse",
        back_populates="attempt",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("participation_id", "attempt_no", name="attempt_no_per_participation"),
        CheckConstraint("revision >= 1", name="assessment_attempt_revision_positive"),
        CheckConstraint("attempt_no >= 1", name="assessment_attempt_no_positive"),
        CheckConstraint(
            "answered_count >= 0", name="assessment_attempt_answered_count_non_negative"
        ),
        CheckConstraint(
            "graded_count >= 0", name="assessment_attempt_graded_count_non_negative"
        ),
        CheckConstraint(
            "total_score IS NULL OR total_score >= 0",
            name="assessment_attempt_total_non_negative",
        ),
        CheckConstraint(
            "max_score IS NULL OR max_score >= 0",
            name="assessment_attempt_max_non_negative",
        ),
        CheckConstraint(
            "mode IN ('offline', 'online')", name="assessment_attempt_mode_valid"
        ),
        CheckConstraint(
            "status IN ('not_started', 'in_progress', 'submitted', 'grading', 'graded', 'void')",
            name="assessment_attempt_status_valid",
        ),
        Index("ix_assessment_attempts_participation", "participation_id", "attempt_no"),
    )


class AssessmentResponse(Base):
    """一个 attempt 对一个 item 的作答(线下可懒建空作答)。"""
    __tablename__ = "assessment_responses"

    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(
        Integer, ForeignKey("assessment_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id = Column(
        Integer, ForeignKey("assessment_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    answer_payload = Column(JSON, nullable=True)
    schema_version = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default=ResponseStatus.UNANSWERED.value)
    revision = Column(Integer, nullable=False, default=1)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    attempt = relationship("AssessmentAttempt", back_populates="responses")
    item = relationship("AssessmentItem")
    grades = relationship(
        "ResponseGrade",
        back_populates="response",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ResponseGrade.revision",
    )

    # 跨版本一致性(response.item 必属 attempt 所在 session.version)不再冗余 version_id 字段，
    # 而是由唯一写入的 assessment_service 在录分时校验。
    __table_args__ = (
        UniqueConstraint("attempt_id", "item_id", name="response_per_attempt_item"),
        CheckConstraint("revision >= 1", name="assessment_response_revision_positive"),
        CheckConstraint(
            "schema_version >= 1", name="assessment_response_schema_version_positive"
        ),
        CheckConstraint(
            "status IN ('unanswered', 'answered', 'omitted')",
            name="assessment_response_status_valid",
        ),
    )


class ResponseGrade(Base):
    """追加式评分记录:每次改分新增一行,不 UPDATE 历史。"""
    __tablename__ = "response_grades"

    id = Column(_BigIntPK, primary_key=True)
    response_id = Column(
        Integer, ForeignKey("assessment_responses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default=GradeStatus.GRADED.value)
    outcome = Column(String(20), nullable=True)
    score = _score_col(nullable=True)
    max_score = _score_col(nullable=False)
    grading_method = Column(String(20), nullable=False, default=GradingMethod.MANUAL.value)
    grader_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    scoring_details = Column(JSON, nullable=True)
    feedback = Column(JSON, nullable=True)
    graded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    supersedes_grade_id = Column(
        _BigIntPK, ForeignKey("response_grades.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    response = relationship("AssessmentResponse", back_populates="grades")
    grader = relationship("User", foreign_keys=[grader_id])
    supersedes = relationship("ResponseGrade", remote_side=[id])

    __table_args__ = (
        UniqueConstraint("response_id", "revision", name="grade_revision_per_response"),
        CheckConstraint("revision >= 1", name="response_grade_revision_positive"),
        CheckConstraint("score IS NULL OR score >= 0", name="response_grade_score_non_negative"),
        CheckConstraint("max_score >= 0", name="response_grade_max_score_non_negative"),
        CheckConstraint(
            "score IS NULL OR score <= max_score", name="response_grade_score_le_max"
        ),
        CheckConstraint(
            "status IN ('pending', 'graded', 'invalidated')",
            name="response_grade_status_valid",
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('correct', 'partial', 'incorrect', 'unscored')",
            name="response_grade_outcome_valid",
        ),
        CheckConstraint(
            "grading_method IN ('manual', 'imported', 'automatic', 'external')",
            name="response_grade_method_valid",
        ),
        Index("ix_response_grades_response_rev", "response_id", "revision"),
    )


class AssessmentEvent(Base):
    """评测时间线事件,追加式审计,按 session 作用域,batch_id 幂等。"""
    __tablename__ = "assessment_events"

    id = Column(_BigIntPK, primary_key=True)
    session_id = Column(
        Integer, ForeignKey("assessment_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type = Column(String(50), nullable=False)
    target_type = Column(String(50), nullable=True)
    target_id = Column(String(64), nullable=True)
    summary = Column(String(255), nullable=False)
    payload = Column(JSON, nullable=True)
    batch_id = Column(String(64), nullable=True)

    actor_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("AssessmentSession", back_populates="events")
    actor = relationship("User", foreign_keys=[actor_id])

    __table_args__ = (
        UniqueConstraint("session_id", "batch_id", name="assessment_event_batch_per_session"),
        Index("ix_assessment_events_session", "session_id", "id"),
        Index("ix_assessment_events_actor_created", "actor_id", "created_at"),
    )
