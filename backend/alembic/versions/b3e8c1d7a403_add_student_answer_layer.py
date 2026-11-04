"""add student answer layer

Revision ID: b3e8c1d7a403
Revises: b3e8c1d7a402
Create Date: 2026-11-04 10:00:00.000000

学生作答 / 学情溯源层。在题库结构化 16 张表之上，补齐：

- student_sheets：学生卷子 / 作答批次，sheet_id 是溯源入口
- student_answers：学生题目作答记录，关联 question_struct_runs.id（用哪版拆解做的题）
- step_errors：步骤级错位，拍照卷子 → 溯源元素 → 溯源知识点的最小可用单元
- question_element_knowledge_points：元素 → 知识点映射，让原子条件挂上课标体系
- student_element_mastery：学生 × 元素掌握状态，长期学情分析用（可延后填充）

与 `questions` 表无任何字段改动，全部旁挂。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3e8c1d7a403"
down_revision: Union[str, Sequence[str], None] = "b3e8c1d7a402"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- student_sheets ----------
    op.create_table(
        "student_sheets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=True),
        sa.Column("sheet_no", sa.String(length=64), nullable=True),
        sa.Column("scanned_at", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["user.id"],
            name=op.f("fk_student_sheets_student_id_user"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_student_sheets")),
    )
    op.create_index(op.f("ix_student_sheets_id"), "student_sheets", ["id"], unique=False)
    op.create_index(
        op.f("ix_student_sheets_student_id"), "student_sheets", ["student_id"], unique=False
    )
    op.create_index(
        op.f("ix_student_sheets_exam_id"), "student_sheets", ["exam_id"], unique=False
    )

    # ---------- student_answers ----------
    op.create_table(
        "student_answers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sheet_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("answer_content", sa.Text(), nullable=True),
        sa.Column("answer_structured", sa.JSON(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("answered_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["sheet_id"],
            ["student_sheets.id"],
            name=op.f("fk_student_answers_sheet_id_student_sheets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_student_answers_question_id_questions"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["question_struct_runs.id"],
            name=op.f("fk_student_answers_run_id_question_struct_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_student_answers")),
    )
    op.create_index(op.f("ix_student_answers_id"), "student_answers", ["id"], unique=False)
    op.create_index(
        op.f("ix_student_answers_sheet_id"),
        "student_answers",
        ["sheet_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_answers_question_id"),
        "student_answers",
        ["question_id"],
        unique=False,
    )
    op.create_index(
        "ix_student_answers_run_id",
        "student_answers",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_student_answers_question_run",
        "student_answers",
        ["question_id", "run_id"],
        unique=False,
    )

    # ---------- step_errors ----------
    op.create_table(
        "step_errors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("answer_id", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=False),
        sa.Column("element_id", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(length=32), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("position_in_step", sa.String(length=64), nullable=True),
        sa.Column("is_breakthrough_missed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["answer_id"],
            ["student_answers.id"],
            name=op.f("fk_step_errors_answer_id_student_answers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["step_id"],
            ["question_struct_steps.id"],
            name=op.f("fk_step_errors_step_id_question_struct_steps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["element_id"],
            ["question_struct_elements.id"],
            name=op.f("fk_step_errors_element_id_question_struct_elements"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_step_errors")),
    )
    op.create_index(op.f("ix_step_errors_id"), "step_errors", ["id"], unique=False)
    op.create_index(
        op.f("ix_step_errors_answer_id"),
        "step_errors",
        ["answer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_step_errors_step_id"), "step_errors", ["step_id"], unique=False
    )
    op.create_index(
        op.f("ix_step_errors_element_id"),
        "step_errors",
        ["element_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_step_errors_error_type"),
        "step_errors",
        ["error_type"],
        unique=False,
    )

    # ---------- question_element_knowledge_points ----------
    op.create_table(
        "question_element_knowledge_points",
        sa.Column("element_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["element_id"],
            ["question_struct_elements.id"],
            name=op.f("fk_qek_element_id_question_struct_elements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"],
            ["knowledge_points.id"],
            name=op.f("fk_qek_kp_id_knowledge_points"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "element_id",
            "knowledge_point_id",
            name=op.f("pk_question_element_knowledge_points"),
        ),
    )

    # ---------- student_element_mastery ----------
    op.create_table(
        "student_element_mastery",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("element_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=True),
        sa.Column("mastery_level", sa.String(length=16), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["user.id"],
            name=op.f("fk_student_element_mastery_student_id_user"),
        ),
        sa.ForeignKeyConstraint(
            ["element_id"],
            ["question_struct_elements.id"],
            name=op.f("fk_student_element_mastery_element_id_question_struct_elements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"],
            ["knowledge_points.id"],
            name=op.f("fk_student_element_mastery_kp_id_knowledge_points"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_student_element_mastery")),
        sa.UniqueConstraint(
            "student_id",
            "element_id",
            name=op.f("uq_student_element_mastery_student_element"),
        ),
    )
    op.create_index(
        op.f("ix_student_element_mastery_id"),
        "student_element_mastery",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_element_mastery_student_id"),
        "student_element_mastery",
        ["student_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_element_mastery_element_id"),
        "student_element_mastery",
        ["element_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_element_mastery_knowledge_point_id"),
        "student_element_mastery",
        ["knowledge_point_id"],
        unique=False,
    )


def downgrade() -> None:
    for table in (
        "student_element_mastery",
        "question_element_knowledge_points",
        "step_errors",
        "student_answers",
        "student_sheets",
    ):
        op.drop_table(table)
