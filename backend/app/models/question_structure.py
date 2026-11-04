"""题干结构化:把题干拆成「条件」与「设问」,并按学科的元素类型树归类。

规格见 docs/specs/question-structure.md。要点与表结构一一对应:

1. **只拆题干。** 输入是题干(含选项)的纯文本快照 ``stem_text``,不含答案与解析——
   答案会给拆解带来大量噪音。
2. **拆解是快照,不是字段。** 同一道题可以拆多次(AI 拆的、人改的、换模型重拆的),
   每次一条 ``StructRun``,互不覆盖;同一时刻最多一条「已采纳」。
3. **原文定位指向快照。** 条件 / 设问的 ``span_start / span_end`` 是 ``stem_text``
   上的字符区间(允许重叠:一句话拆成两条条件时都指向同一段)。题目被编辑后,
   ``source_revision`` 与题目当前的 ``content_revision`` 不一致,拆解即视为过期。
4. **元素类型由归纳得出、老师确认后生效。** 类型可以为空:AI 找不到合适类型时把它
   的描述写进 ``type_hint``,留给后续归纳。类型树按学科维护,第一层是领域
   (数学:代数 / 几何 / 统计),新增类型只是插一行,不需要发版。
5. **材料可共享。** 材料(``stimuli``)单独拆一次;小题的条件可以通过
   ``ref_element_id`` 引用材料拆解中的条件,不重复拆。
"""

import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import relationship

from .base import Base

# 题干、条件文本可能很长(含公式),MySQL 用 LONGTEXT,SQLite 用 TEXT。
_LongText = LONGTEXT().with_variant(Text(), "sqlite")


class StructTypeKind(str, enum.Enum):
    """元素类型树里的节点用于条件还是设问。两者共用一棵树,用 kind 区分。"""

    CONDITION = "condition"
    ASK = "ask"


class StructTypeStatus(str, enum.Enum):
    """元素类型的状态。只有 active 的类型会提供给 AI、出现在筛选里。"""

    # 待确认:由归纳产生、或老师新建尚未启用。
    CANDIDATE = "candidate"
    ACTIVE = "active"
    # 已停用:保留历史引用,不再提供给 AI。
    DEPRECATED = "deprecated"


class StructTargetType(str, enum.Enum):
    """拆解的对象:一道题,或一份材料。"""

    QUESTION = "question"
    STIMULUS = "stimulus"


class StructOrigin(str, enum.Enum):
    """拆解来自 AI 还是人工修改。"""

    AI = "ai"
    HUMAN = "human"


class StructRunState(str, enum.Enum):
    """一次拆解的审核状态。只有 accepted 参与检索、统计。"""

    DRAFT = "draft"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    # 被同一对象后来采纳的拆解取代。
    SUPERSEDED = "superseded"


class StructFacet(str, enum.Enum):
    """条件的作用(可选检索维度,来自 PR #29 的「作用轴」)。"""

    # 给出一个具体的值:坐标、系数、长度、统计量的值。
    QUANT = "quant"
    # 给出一个关系:平行、相等、单调、相关。
    QUAL = "qual"
    # 有东西在动 / 可变:参数、动点、翻折、抽样过程。
    PROC = "proc"
    # 被研究的对象本身:函数式、图形、样本。
    FORM = "form"


class StructType(Base):
    """元素类型树的一个节点(按学科)。"""

    __tablename__ = "struct_types"
    __table_args__ = (
        UniqueConstraint("subject_id", "code", name="uq_struct_types_subject_id_code"),
        Index("ix_struct_types_subject_kind_status", "subject_id", "kind", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    # 父节点;为空表示根(领域,如“代数”,或设问根)。删除节点前须先移走子节点。
    parent_id = Column(Integer, ForeignKey("struct_types.id"), nullable=True, index=True)
    # 取值见 StructTypeKind。
    kind = Column(String(16), nullable=False, default=StructTypeKind.CONDITION.value)
    # 学科内唯一的稳定标识,一经使用不要改名;展示用 name。
    code = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    # 定义与正反例:让 AI 和不同老师对同一个类型理解一致。
    definition = Column(Text, nullable=True)
    # 示例(JSON 数组字符串):[{"text": "...", "positive": true}, ...]
    examples = Column(Text, nullable=True)
    # 取值见 StructTypeStatus。
    status = Column(String(16), nullable=False, default=StructTypeStatus.ACTIVE.value)
    sort_order = Column(Integer, nullable=False, default=0)

    created_by = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class StructRun(Base):
    """对一道题(或一份材料)的一次拆解快照。"""

    __tablename__ = "struct_runs"
    __table_args__ = (
        Index("ix_struct_runs_target_state", "target_type", "target_id", "state"),
        Index("ix_struct_runs_subject_state", "subject_id", "state"),
    )

    id = Column(Integer, primary_key=True, index=True)
    # 取值见 StructTargetType;target 是多态引用(题目 / 材料都是软删除),不设外键。
    target_type = Column(String(16), nullable=False)
    target_id = Column(Integer, nullable=False)
    # 冗余一份学科:按学科检索、统计时不必再 join 题目。
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=True)

    # 拆解时题目 / 材料的 content_revision;与当前值不同即为过期。
    source_revision = Column(Integer, nullable=False, default=1)
    # 拆解时的题干纯文本快照;所有 span 都指向它。
    stem_text = Column(_LongText, nullable=False)

    # 取值见 StructOrigin。
    origin = Column(String(16), nullable=False, default=StructOrigin.AI.value)
    # AI 拆解所用的模型名与提示词版本,便于对比不同模型 / 提示词的效果。
    model = Column(String(128), nullable=True)
    prompt_version = Column(String(32), nullable=True)
    # 生成这次拆解的 job(人工保存时为空)。
    job_id = Column(Integer, nullable=True)

    # 取值见 StructRunState。
    state = Column(String(16), nullable=False, default=StructRunState.DRAFT.value)
    # 自动体检结果(JSON 字符串),见 app/services/structure/check.py。
    check_report = Column(Text, nullable=True)
    # 体检 error / warning 的数量:审核队列按它筛选、把有错误的排在前面。
    check_errors = Column(Integer, nullable=False, default=0)
    check_warnings = Column(Integer, nullable=False, default=0)

    created_by = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    reviewed_by = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    elements = relationship(
        "StructElement",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="StructElement.ordinal",
        foreign_keys="StructElement.run_id",
    )
    asks = relationship(
        "StructAsk", back_populates="run", cascade="all, delete-orphan", order_by="StructAsk.ordinal"
    )
    element_groups = relationship(
        "StructElementGroup",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="StructElementGroup.sort_order",
    )


class StructElement(Base):
    """一条条件:题干拆出来的、只说一件事的已知条件或研究对象。"""

    __tablename__ = "struct_elements"
    __table_args__ = (Index("ix_struct_elements_run_ordinal", "run_id", "ordinal"),)

    id = Column(Integer, primary_key=True, index=True)
    # run_id 的单列查询由 (run_id, ordinal) 复合索引的最左前缀覆盖,不再单建索引。
    run_id = Column(Integer, ForeignKey("struct_runs.id", ondelete="CASCADE"), nullable=False)
    ordinal = Column(Integer, nullable=False, default=0)
    # 规范化后的单命题表述,可以与原文措辞不同。
    content = Column(_LongText, nullable=False)

    # 元素类型;为空表示尚未归类(见 type_hint)。
    type_id = Column(Integer, ForeignKey("struct_types.id", ondelete="SET NULL"), nullable=True, index=True)
    # AI 对未归类条件给出的类型描述,供后续归纳。
    type_hint = Column(String(255), nullable=True)
    # 取值见 StructFacet,可空。
    facet = Column(String(16), nullable=True)

    # 原文证据区间(指向 run.stem_text),允许与别的条件重叠;引用材料条件时可为空。
    span_start = Column(Integer, nullable=True)
    span_end = Column(Integer, nullable=True)

    # 引用材料拆解中的条件(共享,不重复拆)。
    ref_element_id = Column(
        Integer, ForeignKey("struct_elements.id", ondelete="SET NULL"), nullable=True, index=True
    )

    run = relationship("StructRun", back_populates="elements", foreign_keys=[run_id])
    params = relationship("StructParam", back_populates="element", cascade="all, delete-orphan")


class StructAsk(Base):
    """一条设问。设问单独成表:它依赖哪些条件、属于哪种设问类型,都与条件不同。"""

    __tablename__ = "struct_asks"
    __table_args__ = (Index("ix_struct_asks_run_ordinal", "run_id", "ordinal"),)

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("struct_runs.id", ondelete="CASCADE"), nullable=False)
    ordinal = Column(Integer, nullable=False, default=0)
    content = Column(_LongText, nullable=False)

    # 设问类型(struct_types 中 kind=ask 的节点);为空表示尚未归类。
    type_id = Column(Integer, ForeignKey("struct_types.id", ondelete="SET NULL"), nullable=True, index=True)
    type_hint = Column(String(255), nullable=True)

    span_start = Column(Integer, nullable=True)
    span_end = Column(Integer, nullable=True)

    run = relationship("StructRun", back_populates="asks")
    element_links = relationship("StructAskElement", cascade="all, delete-orphan", passive_deletes=True)


class StructAskElement(Base):
    """设问依赖哪些条件。"""

    __tablename__ = "struct_ask_elements"

    ask_id = Column(Integer, ForeignKey("struct_asks.id", ondelete="CASCADE"), primary_key=True)
    element_id = Column(Integer, ForeignKey("struct_elements.id", ondelete="CASCADE"), primary_key=True)


class StructParam(Base):
    """参数槽：元素中可替换的槽位，是「改数/改条件/改问法」变式生成的抓手。

    replaceable=1 表示该槽位可被替换；slot_kind 取 numeric/symbolic/point/region；
    domain 存放允许取值的约束说明。
    """

    __tablename__ = "question_struct_params"

    id = Column(Integer, primary_key=True, index=True)
    element_id = Column(
        Integer, ForeignKey("struct_elements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(64), nullable=False)  # 参数名，如 a / c / 2
    value_text = Column(_LongText, nullable=False)  # 原值，逐字照抄
    slot_kind = Column(String(32), nullable=True)  # numeric | symbolic | point | region
    domain = Column(Text, nullable=True)  # 允许取值范围 / 约束说明
    replaceable = Column(Integer, nullable=False, default=1, server_default="1")

    element = relationship("StructElement", back_populates="params")


class StructElementGroup(Base):
    """可整体替换的元素组：一组元素作为整体可被另一组替换，用于条件重组命题。"""

    __tablename__ = "question_struct_element_groups"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("struct_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    replaceable = Column(Integer, nullable=False, default=1, server_default="1")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")

    run = relationship("StructRun", back_populates="element_groups")
    items = relationship(
        "StructElementGroupItem", cascade="all, delete-orphan", passive_deletes=True, back_populates="group"
    )


class StructElementGroupItem(Base):
    """元素组与元素的多对多关联。"""

    __tablename__ = "question_struct_element_group_items"

    group_id = Column(
        Integer, ForeignKey("question_struct_element_groups.id", ondelete="CASCADE"), primary_key=True
    )
    element_id = Column(
        Integer, ForeignKey("struct_elements.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (
        Index("ix_question_struct_element_group_items_group_id", "group_id"),
        Index("ix_question_struct_element_group_items_element_id", "element_id"),
    )

    group = relationship("StructElementGroup", back_populates="items")
    element = relationship("StructElement")


# 在 StructRun / StructElement 上反向关联由关系字段声明，此处不重复定义。

