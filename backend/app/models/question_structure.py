"""题干结构化：把一道题拆成元素、设问与解题步骤。

设计要点（与表结构一一对应）：

1. **拆解是快照，不是字段。** 同一道题可以有多次拆解（AI 拆的、人改的、换模型
   再拆的），每次是一个 ``QuestionStructRun``。结构化表全部挂在 run 上，互不覆盖。
   把它写成 ``questions`` 上的单值字段，就永远比较不出 AI 和人差在哪。
2. **元素是规范化后的单命题表述，span 是原文证据。** 二者不必相等：原文写「与 x 轴
   交于 A(-1,0)、B(3,0)」是一句，拆成两条元素时两条都指向同一段原文，所以 span
   允许重叠。没有 span 就失去回指能力——审核定位不了、前端高亮不出来。
3. **步骤要能产出事实。** 「f'(x)=3x^2+a，所以需 a<0」里的 a<0 不是题给条件，是
   第 1 步的产物，但第 3 步要用它。只记「依据哪些条件」记不下这一环，所以单列
   ``QuestionStructProduce``，并允许步骤引用别步的产出。
4. **词表用外键，不用数据库枚举。** 元素角色、元素类型、解题方法都是会持续增长
   的数据。做成 MySQL ENUM 就意味着加一个类型要发一次版、写一次 batch_alter；
   做成词表表，加值只是 INSERT。
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    JSON,
)
from sqlalchemy.orm import relationship

from .base import Base

#: 元素类型的第一坐标：跟着课标**领域**走，不自造。
#: 注意与题库的 subjects 表（学科）区分，这里叫 domain。
ELEMENT_DOMAINS = ("algebra", "geometry", "stat", "practice")
#: 元素类型的第二坐标。
#: quant=给值  qual=给关系  proc=在动/可变  form=被研究的对象本身。
ELEMENT_ACTIONS = ("quant", "qual", "proc", "form")


class ElementRole(Base):
    """元素角色词表：对象 / 已知 / 限制 / 设问 / 材料。

    词表由学科老师维护，``code`` 是稳定标识，``name`` 可以改措辞。
    """

    __tablename__ = "element_roles"

    code = Column(String(32), primary_key=True)
    name = Column(String(64), nullable=False)
    note = Column(String(255), nullable=True)


class ElementType(Base):
    """元素类型词表：领域 × 作用，可按 parent_code 组成树。

    ``domain`` 是课标**领域**（数与代数、图形与几何…），不要与题库的 ``subjects``
    表（学科：数学、物理…）混用，所以这里叫 domain 不叫 subject。

    两个坐标分开存而不是拼成一个枚举值，是为了能单独按任一坐标检索：
    「所有含动点的题」查 action=proc，「所有几何条件」查 domain=geometry。

    ``parent_code`` 让类型树可以像知识点那样挂层级；``status`` 为空出「候选」这一态：
    AI 从大量题目里归纳出的新类型先进 candidate，人确认后才变 active，这与
    「AI 只能选不能造」的原则一致——它可以提名，不能直接定名。
    """

    __tablename__ = "element_types"
    __table_args__ = (
        UniqueConstraint("domain", "action", "name", name="uq_element_types_domain_action_name"),
        Index("ix_element_types_parent", "parent_code"),
        Index("ix_element_types_status", "status"),
    )

    code = Column(String(64), primary_key=True)
    domain = Column(String(32), nullable=False)  # 见 ELEMENT_DOMAINS
    action = Column(String(32), nullable=False)  # 见 ELEMENT_ACTIONS
    name = Column(String(64), nullable=False)
    note = Column(String(255), nullable=True)

    parent_code = Column(String(64), ForeignKey("element_types.code"), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    # active 已确认 / candidate AI 提名待确认 / rejected 已否决
    status = Column(String(16), nullable=False, default="active", server_default="active")


class SolvingMethod(Base):
    """解题方法（思维动作）词表。

    ``weight`` 是该动作的思维量权重。普通步骤为 1，构造辅助线、分类讨论、
    举反例这类认知负荷突增的步骤取大于 1 的值。思维量 = 步骤权重之和，
    可复算、可解释，用来替代 1-5 星那种档内差异大于档间差异的刻度。
    """

    __tablename__ = "solving_methods"

    code = Column(String(48), primary_key=True)
    name = Column(String(64), nullable=False)
    parent_code = Column(String(48), ForeignKey("solving_methods.code"), nullable=True)
    weight = Column(Float, nullable=False, default=1.0, server_default="1")


class StructVocabularyMeta(Base):
    """词表版本。``QuestionStructRun.vocabulary_version`` 锁死拆解当时的版本，
    否则词表一改，老拆解全部失效且无法追溯。"""

    __tablename__ = "struct_vocabulary_meta"

    key = Column(String(64), primary_key=True)
    value = Column(String(255), nullable=False)


class QuestionStructRun(Base):
    """一次拆解。同题多版本并存，互不覆盖。"""

    __tablename__ = "question_struct_runs"
    __table_args__ = (
        UniqueConstraint("question_id", "rev", name="uq_question_struct_runs_question_rev"),
        Index("ix_question_struct_runs_subject_state", "subject_id", "state"),
    )

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, index=True)
    # 冗余一份学科，检索按学科过滤时不必再 join questions。
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True)

    rev = Column(Integer, nullable=False, default=1)
    # ai / human / imported
    origin = Column(String(16), nullable=False, default="ai")
    model = Column(String(128), nullable=True)
    prompt_version = Column(String(32), nullable=True)
    vocabulary_version = Column(String(32), nullable=True)

    # draft / reviewed / rejected —— 只有 reviewed 进检索
    state = Column(String(16), nullable=False, default="draft", server_default="draft")

    # 拆解时题干的纯文本快照。**所有 span_start/span_end 都是相对这份文本的字符下标**，
    # 不是相对 questions.content 里的 RichDoc JSON——JSON 里算出来的偏移前端拿来
    # 高亮必然错位。题库的 content 是富文本，必须先把 text 节点拼成纯文本再定 span。
    stem_text = Column(Text, nullable=True)
    # 这份快照的哈希。与题干当前的哈希不一致，说明题目被改过，本次拆解已过期。
    stem_sha256 = Column(String(64), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    materials = relationship(
        "QuestionStructMaterial", back_populates="run", cascade="all, delete-orphan"
    )
    elements = relationship(
        "QuestionStructElement", back_populates="run", cascade="all, delete-orphan"
    )
    asks = relationship("QuestionStructAsk", back_populates="run", cascade="all, delete-orphan")
    steps = relationship("QuestionStructStep", back_populates="run", cascade="all, delete-orphan")


class QuestionStructMaterial(Base):
    """题组共享的材料。不属于任何单题，所以独立一层、可被多个设问引用。"""

    __tablename__ = "question_struct_materials"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(
        Integer, ForeignKey("question_struct_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal = Column(Integer, nullable=False, default=0)
    content = Column(Text, nullable=False)
    span_start = Column(Integer, nullable=True)
    span_end = Column(Integer, nullable=True)
    status = Column(String(16), nullable=False, default="ai", server_default="ai")

    run = relationship("QuestionStructRun", back_populates="materials")


class QuestionStructElementGroup(Base):
    """一组可整体替换的元素，例如「过 A、B 两点」换掉时两条一起换。"""

    __tablename__ = "question_struct_element_groups"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(
        Integer, ForeignKey("question_struct_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal = Column(Integer, nullable=False, default=0)
    label = Column(String(128), nullable=True)
    # replaceable / fixed
    kind = Column(String(16), nullable=False, default="replaceable")


class QuestionStructElement(Base):
    """一条元素：题干拆出来的、只说一件事的条件或对象。"""

    __tablename__ = "question_struct_elements"
    __table_args__ = (
        Index("ix_question_struct_elements_run_ordinal", "run_id", "ordinal"),
        Index("ix_question_struct_elements_type", "element_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    # run_id 的单列查询由 (run_id, ordinal) 的最左前缀覆盖，不再单建索引。
    run_id = Column(
        Integer, ForeignKey("question_struct_runs.id", ondelete="CASCADE"), nullable=False
    )
    ordinal = Column(Integer, nullable=False, default=0)
    content = Column(Text, nullable=False)

    role = Column(String(32), ForeignKey("element_roles.code"), nullable=False, index=True)
    element_type = Column(String(32), ForeignKey("element_types.code"), nullable=True)

    group_id = Column(
        Integer, ForeignKey("question_struct_element_groups.id", ondelete="SET NULL"), nullable=True
    )
    material_id = Column(
        Integer, ForeignKey("question_struct_materials.id", ondelete="SET NULL"), nullable=True
    )

    # 原文证据区间，允许与别的元素重叠
    span_start = Column(Integer, nullable=True)
    span_end = Column(Integer, nullable=True)

    # 原子性体检结果：NULL 未检 / 1 通过 / 0 有问题
    atomic_ok = Column(Boolean, nullable=True)
    status = Column(String(16), nullable=False, default="ai", server_default="ai")

    run = relationship("QuestionStructRun", back_populates="elements")


class QuestionStructAsk(Base):
    """一条设问。设问不并进元素表，因为它要挂作答目标与分值。"""

    __tablename__ = "question_struct_asks"
    __table_args__ = (Index("ix_question_struct_asks_run_ordinal", "run_id", "ordinal"),)

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(
        Integer, ForeignKey("question_struct_runs.id", ondelete="CASCADE"), nullable=False
    )
    ordinal = Column(Integer, nullable=False, default=0)
    content = Column(Text, nullable=False)
    # solve 求值 / prove 证明 / judge 判断 / explain 说明理由
    target = Column(String(16), nullable=False, default="solve")
    # 分值只服务于命题与评卷，不参与检索排序
    points = Column(Float, nullable=True)

    span_start = Column(Integer, nullable=True)
    span_end = Column(Integer, nullable=True)
    status = Column(String(16), nullable=False, default="ai", server_default="ai")

    run = relationship("QuestionStructRun", back_populates="asks")


class QuestionStructAskElement(Base):
    """设问依赖哪些元素。"""

    __tablename__ = "question_struct_ask_elements"

    ask_id = Column(
        Integer, ForeignKey("question_struct_asks.id", ondelete="CASCADE"), primary_key=True
    )
    element_id = Column(
        Integer, ForeignKey("question_struct_elements.id", ondelete="CASCADE"), primary_key=True
    )


class QuestionStructParam(Base):
    """参数槽。变式生成的具体抓手：换哪个值、能换成什么范围。"""

    __tablename__ = "question_struct_params"

    id = Column(Integer, primary_key=True, index=True)
    element_id = Column(
        Integer,
        ForeignKey("question_struct_elements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(32), nullable=False)
    value_text = Column(String(255), nullable=False)
    # numeric / symbolic / point / region
    slot_kind = Column(String(16), nullable=True)
    # 允许替换的取值范围或约束，交给学科老师填
    domain = Column(String(255), nullable=True)
    replaceable = Column(Boolean, nullable=False, default=True, server_default="1")


class QuestionStructStep(Base):
    """一步思维动作。

    存动作而不是存得分点：得分点绑解法，同一题不同解法的得分点表完全不同，
    存下来等于把「一题」变成「多题」。得分点由动作投影生成。
    """

    __tablename__ = "question_struct_steps"
    __table_args__ = (
        Index("ix_question_struct_steps_run_ordinal", "run_id", "ordinal"),
        Index("ix_question_struct_steps_method", "method"),
    )

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(
        Integer, ForeignKey("question_struct_runs.id", ondelete="CASCADE"), nullable=False
    )
    ask_id = Column(
        Integer, ForeignKey("question_struct_asks.id", ondelete="SET NULL"), nullable=True
    )
    ordinal = Column(Integer, nullable=False, default=0)
    method = Column(String(48), ForeignKey("solving_methods.code"), nullable=False)
    note = Column(Text, nullable=True)
    # 突破口：这道题的「想通那一下」
    is_breakthrough = Column(Boolean, nullable=False, default=False, server_default=false())

    span_start = Column(Integer, nullable=True)
    span_end = Column(Integer, nullable=True)
    status = Column(String(16), nullable=False, default="ai", server_default="ai")

    run = relationship("QuestionStructRun", back_populates="steps")


class QuestionStructProduce(Base):
    """一步产出的事实。

    ``kind``：premise 前提约束（如 a<0）/ fact 中间结论 / answer 最终答案。
    后续步骤可以引用，这样整条推导链闭合、能机器复算。
    """

    __tablename__ = "question_struct_produces"

    id = Column(Integer, primary_key=True, index=True)
    step_id = Column(
        Integer,
        ForeignKey("question_struct_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal = Column(Integer, nullable=False, default=0)
    content = Column(Text, nullable=False)
    kind = Column(String(16), nullable=False, default="fact")


class QuestionStructStepElement(Base):
    """某步直接依据哪些元素。"""

    __tablename__ = "question_struct_step_elements"

    step_id = Column(
        Integer, ForeignKey("question_struct_steps.id", ondelete="CASCADE"), primary_key=True
    )
    element_id = Column(
        Integer, ForeignKey("question_struct_elements.id", ondelete="CASCADE"), primary_key=True
    )


class QuestionStructStepProduce(Base):
    """某步引用别步产出的哪个事实。"""

    __tablename__ = "question_struct_step_produces"

    step_id = Column(
        Integer, ForeignKey("question_struct_steps.id", ondelete="CASCADE"), primary_key=True
    )
    produce_id = Column(
        Integer, ForeignKey("question_struct_produces.id", ondelete="CASCADE"), primary_key=True
    )


class QuestionStructMisconception(Base):
    """常见错误。独立成表，因为错的不是条件而是推理，且一个错因可对应多个步骤位置。

    ``source``：exam 真实作答 / option 干扰项。两者是两张不同的表意——
    前者说「哪一步走偏」，后者说「为什么选错」。
    ``error_rate`` 只填真实统计值；没有作答数据时留空，不要让模型编。
    """

    __tablename__ = "question_struct_misconceptions"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, index=True)
    step_id = Column(
        Integer, ForeignKey("question_struct_steps.id", ondelete="SET NULL"), nullable=True
    )
    content = Column(Text, nullable=False)
    source = Column(String(16), nullable=False, default="exam")
    error_rate = Column(Float, nullable=True)
    sample_size = Column(Integer, nullable=True)


__all__ = [
    "ELEMENT_ACTIONS",
    "ELEMENT_DOMAINS",
    "ElementRole",
    "ElementType",
    "QuestionStructAsk",
    "QuestionStructAskElement",
    "QuestionStructElement",
    "QuestionStructElementGroup",
    "QuestionStructMaterial",
    "QuestionStructMisconception",
    "QuestionStructParam",
    "QuestionStructProduce",
    "QuestionStructRun",
    "QuestionStructStep",
    "QuestionStructStepElement",
    "QuestionStructStepProduce",
    "SolvingMethod",
    "StructVocabularyMeta",
    "StudentSheet",
    "StudentAnswer",
    "StepError",
    "QuestionElementKnowledgePoint",
    "StudentElementMastery",
]


class StudentSheet(Base):
    """学生卷子 / 作答批次。sheet_id 是学情溯源的入口。

    一次考试或一次拍照刷题对应一张 sheet，下面挂若干 student_answer。
    """

    __tablename__ = "student_sheets"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    exam_id = Column(Integer, nullable=True, index=True)
    sheet_no = Column(String(64), nullable=True)
    scanned_at = Column(DateTime, nullable=True)
    source = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class StudentAnswer(Base):
    """学生题目作答记录。

    run_id 指向用于出题的结构化拆解版本，这样能知道学生做题时题干是哪个版本。
    """

    __tablename__ = "student_answers"
    __table_args__ = (Index("ix_student_answers_question_run", "question_id", "run_id"),)

    id = Column(Integer, primary_key=True, index=True)
    sheet_id = Column(
        Integer, ForeignKey("student_sheets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, index=True)
    run_id = Column(
        Integer,
        ForeignKey("question_struct_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    answer_content = Column(Text, nullable=True)
    answer_structured = Column(JSON, nullable=True)
    score = Column(Float, nullable=True)
    answered_at = Column(DateTime, default=datetime.utcnow)


class StepError(Base):
    """步骤级错位，是“拍照卷子 → 溯源元素”的最小可用单元。

    教师或 OCR 标注学生在哪个标准步骤走了偏，错什么，错位在步骤内的哪里。
    通过 element_id 可直接追溯到该步骤依赖的核心条件；再通过
    question_element_knowledge_points 可追溯到课标知识点。
    """

    __tablename__ = "step_errors"
    __table_args__ = (
        Index("ix_step_errors_error_type", "error_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    answer_id = Column(
        Integer, ForeignKey("student_answers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id = Column(
        Integer,
        ForeignKey("question_struct_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    element_id = Column(
        Integer,
        ForeignKey("question_struct_elements.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # concept / calculation / reading / omission / format
    error_type = Column(String(32), nullable=False)
    error_detail = Column(Text, nullable=True)
    position_in_step = Column(String(64), nullable=True)
    is_breakthrough_missed = Column(Boolean, nullable=False, default=False, server_default=false())
    created_at = Column(DateTime, default=datetime.utcnow)


class QuestionElementKnowledgePoint(Base):
    """元素 → 知识点映射。

    元素本身是原子条件，不污染知识点体系；通过这张表把元素挂到课标
    知识点上，使“按知识点看薄弱点”成为可能。
    """

    __tablename__ = "question_element_knowledge_points"

    element_id = Column(
        Integer,
        ForeignKey("question_struct_elements.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    knowledge_point_id = Column(
        Integer,
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )


class StudentElementMastery(Base):
    """学生 × 元素掌握状态，长期学情分析用（可延后建表填充）。"""

    __tablename__ = "student_element_mastery"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    element_id = Column(
        Integer,
        ForeignKey("question_struct_elements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_point_id = Column(
        Integer, ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # mastered / partial / not_mastered / unknown
    mastery_level = Column(String(16), nullable=False, default="unknown", server_default="unknown")
    error_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_seen_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "student_id", "element_id", name="uq_student_element_mastery_student_element"
        ),
    )
