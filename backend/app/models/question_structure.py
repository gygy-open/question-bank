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
)
from sqlalchemy.orm import relationship

from .base import Base

#: 元素类型的第一坐标：跟着课标领域走，不自造。
ELEMENT_SUBJECTS = ("algebra", "geometry", "stat", "practice")
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
    """元素类型词表：学科 × 作用。

    两个坐标分开存而不是拼成一个枚举值，是为了能单独按任一坐标检索：
    「所有含动点的题」查 action=proc，「所有几何条件」查 subject=geometry。
    """

    __tablename__ = "element_types"
    __table_args__ = (
        UniqueConstraint("subject", "action", name="uq_element_types_subject_action"),
    )

    code = Column(String(32), primary_key=True)
    subject = Column(String(32), nullable=False)  # 见 ELEMENT_SUBJECTS
    action = Column(String(32), nullable=False)  # 见 ELEMENT_ACTIONS
    name = Column(String(64), nullable=False)
    note = Column(String(255), nullable=True)


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
    "ELEMENT_SUBJECTS",
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
]
