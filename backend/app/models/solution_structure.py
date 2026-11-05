"""解答结构(题干结构化三期,规格 §12.3 N7):把一道题的解答拆成步骤。

要点:

1. **解答是快照。** 与题干拆解一样,每次拆解一条 ``SolutionRun``,不覆盖;同一道题的同一种
   解法(``solution_no``)最多一条已采纳。一道题可以有多种解法。
2. **步骤引用题干。** 步骤用到的条件 / 设问指向题干的**已采纳**拆解(``stem_run_id``);
   题干拆解被取代、或题目内容修改后,解答显示为「需复核」(与题干拆解的过期判断同理)。
3. **方法与权重。** 步骤的解题方法复用元素类型树(``kind=method``),权重在类型上由老师维护;
   一次解答的思维量 = 各步骤权重之和(未归类的步骤记 1)。题目的思维量难度取已采纳解法中的最小值。
4. **常见错误挂在步骤上。** 来源分「干扰项」(由选择题选项推出)与「作答」(学情,五期)。
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import relationship

from .base import Base

_LongText = LONGTEXT().with_variant(Text(), "sqlite")


class SolutionLinkRole(str, enum.Enum):
    """步骤与题干 / 前序步骤的关系。"""

    # 步骤用到了这个条件、设问,或前序步骤的结论。
    USES = "uses"
    # 步骤得出了这个设问的答案。
    ANSWERS = "answers"


class MisconceptionSource(str, enum.Enum):
    """常见错误的来源。"""

    DISTRACTOR = "distractor"
    RESPONSE = "response"


class SolutionRun(Base):
    """一道题某种解法的一次步骤拆解快照。"""

    __tablename__ = "solution_runs"
    __table_args__ = (
        Index("ix_solution_runs_question_state", "question_id", "state"),
        Index("ix_solution_runs_subject_state", "subject_id", "state"),
    )

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=True)
    # 引用的题干拆解(拆解时题目已采纳的那一条)。
    stem_run_id = Column(Integer, ForeignKey("struct_runs.id", ondelete="SET NULL"), nullable=True)
    # 第几种解法(从 1 开始)。
    solution_no = Column(Integer, nullable=False, default=1)
    source_revision = Column(Integer, nullable=False, default=1)
    # 拆解依据的参考解答文本(题目解析);没有解析时为空,由 AI 自行解答。
    solution_text = Column(_LongText, nullable=True)

    # 取值同 StructOrigin(ai / human / agent)。
    origin = Column(String(16), nullable=False, default="ai")
    model = Column(String(128), nullable=True)
    prompt_version = Column(String(32), nullable=True)
    job_id = Column(Integer, nullable=True)
    # 取值同 StructRunState。
    state = Column(String(16), nullable=False, default="draft")
    # 各步骤权重之和(保存时计算,类型权重变化时重算)。
    thinking_load = Column(Float, nullable=True)
    check_report = Column(Text, nullable=True)
    check_errors = Column(Integer, nullable=False, default=0)
    check_warnings = Column(Integer, nullable=False, default=0)

    created_by = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    reviewed_by = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    steps = relationship(
        "SolutionStep", back_populates="run", cascade="all, delete-orphan", order_by="SolutionStep.ordinal"
    )


class SolutionStep(Base):
    """解答中的一步:要达成的目标、用的方法、得出的结论。"""

    __tablename__ = "solution_steps"
    __table_args__ = (Index("ix_solution_steps_run_ordinal", "run_id", "ordinal"),)

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("solution_runs.id", ondelete="CASCADE"), nullable=False)
    ordinal = Column(Integer, nullable=False, default=0)
    goal = Column(_LongText, nullable=False)
    # 解题方法(struct_types 中 kind=method 的节点);为空表示未归类(见 method_hint)。
    method_type_id = Column(Integer, ForeignKey("struct_types.id", ondelete="SET NULL"), nullable=True, index=True)
    method_hint = Column(String(255), nullable=True)
    # 这一步得出的中间结论,可被后续步骤引用。
    result = Column(_LongText, nullable=True)
    # 关键步骤(突破口)。
    is_key = Column(Boolean, nullable=False, default=False)

    run = relationship("SolutionRun", back_populates="steps")
    links = relationship(
        "SolutionStepLink",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="SolutionStepLink.step_id",
    )
    misconceptions = relationship(
        "SolutionMisconception", cascade="all, delete-orphan", passive_deletes=True, order_by="SolutionMisconception.id"
    )


class SolutionStepLink(Base):
    """步骤用到 / 得出的对象:题干条件、设问,或前序步骤(三者恰有其一)。"""

    __tablename__ = "solution_step_links"

    id = Column(Integer, primary_key=True, index=True)
    step_id = Column(Integer, ForeignKey("solution_steps.id", ondelete="CASCADE"), nullable=False, index=True)
    # 取值见 SolutionLinkRole。
    role = Column(String(16), nullable=False, default=SolutionLinkRole.USES.value)
    element_id = Column(Integer, ForeignKey("struct_elements.id", ondelete="SET NULL"), nullable=True)
    ask_id = Column(Integer, ForeignKey("struct_asks.id", ondelete="SET NULL"), nullable=True)
    prev_step_id = Column(Integer, ForeignKey("solution_steps.id", ondelete="CASCADE"), nullable=True)


class SolutionMisconception(Base):
    """某一步上的常见错误。"""

    __tablename__ = "solution_misconceptions"

    id = Column(Integer, primary_key=True, index=True)
    step_id = Column(Integer, ForeignKey("solution_steps.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(Text, nullable=False)
    # 取值见 MisconceptionSource。
    source = Column(String(16), nullable=False, default=MisconceptionSource.DISTRACTOR.value)
