"""solution structure, method weights, type-knowledge point map, thinking difficulty

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-11-05 14:00:00.000000

题干结构化三期(规格 docs/specs/question-structure.md §12.3 N7、N8):
解答步骤快照、步骤链接与常见错误;类型权重;类型 ↔ 知识点映射;题目思维量难度。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, Sequence[str], None] = "a5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LongText = mysql.LONGTEXT().with_variant(sa.Text(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("struct_types") as batch_op:
        batch_op.add_column(sa.Column("weight", sa.Float(), nullable=False, server_default="1"))
    with op.batch_alter_table("questions") as batch_op:
        batch_op.add_column(sa.Column("thinking_difficulty", sa.Float(), nullable=True))

    op.create_table(
        "struct_type_knowledge_points",
        sa.Column("type_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["type_id"], ["struct_types.id"], name=op.f("fk_struct_type_knowledge_points_type_id_struct_types"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"], ["knowledge_points.id"],
            name=op.f("fk_struct_type_knowledge_points_knowledge_point_id_knowledge_points"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("type_id", "knowledge_point_id", name=op.f("pk_struct_type_knowledge_points")),
    )

    op.create_table(
        "solution_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("stem_run_id", sa.Integer(), nullable=True),
        sa.Column("solution_no", sa.Integer(), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("solution_text", _LongText, nullable=True),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("thinking_load", sa.Float(), nullable=True),
        sa.Column("check_report", sa.Text(), nullable=True),
        sa.Column("check_errors", sa.Integer(), nullable=False),
        sa.Column("check_warnings", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.id"], name=op.f("fk_solution_runs_question_id_questions"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"], name=op.f("fk_solution_runs_subject_id_subjects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["stem_run_id"], ["struct_runs.id"], name=op.f("fk_solution_runs_stem_run_id_struct_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["user.id"], name=op.f("fk_solution_runs_created_by_user"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["user.id"], name=op.f("fk_solution_runs_reviewed_by_user"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_solution_runs")),
    )
    op.create_index(op.f("ix_solution_runs_id"), "solution_runs", ["id"], unique=False)
    op.create_index("ix_solution_runs_question_state", "solution_runs", ["question_id", "state"], unique=False)
    op.create_index("ix_solution_runs_subject_state", "solution_runs", ["subject_id", "state"], unique=False)

    op.create_table(
        "solution_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("goal", _LongText, nullable=False),
        sa.Column("method_type_id", sa.Integer(), nullable=True),
        sa.Column("method_hint", sa.String(length=255), nullable=True),
        sa.Column("result", _LongText, nullable=True),
        sa.Column("is_key", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["solution_runs.id"], name=op.f("fk_solution_steps_run_id_solution_runs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["method_type_id"], ["struct_types.id"], name=op.f("fk_solution_steps_method_type_id_struct_types"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_solution_steps")),
    )
    op.create_index(op.f("ix_solution_steps_id"), "solution_steps", ["id"], unique=False)
    op.create_index(op.f("ix_solution_steps_method_type_id"), "solution_steps", ["method_type_id"], unique=False)
    op.create_index("ix_solution_steps_run_ordinal", "solution_steps", ["run_id", "ordinal"], unique=False)

    op.create_table(
        "solution_step_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("element_id", sa.Integer(), nullable=True),
        sa.Column("ask_id", sa.Integer(), nullable=True),
        sa.Column("prev_step_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["step_id"], ["solution_steps.id"], name=op.f("fk_solution_step_links_step_id_solution_steps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["element_id"], ["struct_elements.id"], name=op.f("fk_solution_step_links_element_id_struct_elements"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ask_id"], ["struct_asks.id"], name=op.f("fk_solution_step_links_ask_id_struct_asks"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["prev_step_id"], ["solution_steps.id"], name=op.f("fk_solution_step_links_prev_step_id_solution_steps"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_solution_step_links")),
    )
    op.create_index(op.f("ix_solution_step_links_id"), "solution_step_links", ["id"], unique=False)
    op.create_index(op.f("ix_solution_step_links_step_id"), "solution_step_links", ["step_id"], unique=False)

    op.create_table(
        "solution_misconceptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["step_id"], ["solution_steps.id"], name=op.f("fk_solution_misconceptions_step_id_solution_steps"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_solution_misconceptions")),
    )
    op.create_index(op.f("ix_solution_misconceptions_id"), "solution_misconceptions", ["id"], unique=False)
    op.create_index(op.f("ix_solution_misconceptions_step_id"), "solution_misconceptions", ["step_id"], unique=False)


def downgrade() -> None:
    op.drop_table("solution_misconceptions")
    op.drop_table("solution_step_links")
    op.drop_table("solution_steps")
    op.drop_table("solution_runs")
    op.drop_table("struct_type_knowledge_points")
    with op.batch_alter_table("questions") as batch_op:
        batch_op.drop_column("thinking_difficulty")
    with op.batch_alter_table("struct_types") as batch_op:
        batch_op.drop_column("weight")
