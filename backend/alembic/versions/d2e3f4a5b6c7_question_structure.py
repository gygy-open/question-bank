"""question stem structure: types, runs, elements, asks

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-11-04 15:00:00.000000

题干结构化(规格 docs/specs/question-structure.md 一期):按学科的元素类型树、
拆解快照、条件、设问及设问依赖。不改动 questions / stimuli 的任何字段。
元素类型树的根节点由数据迁移 ``struct_type_roots_v1`` 写入。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql


revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LongText = mysql.LONGTEXT().with_variant(sa.Text(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "struct_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column("examples", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["user.id"], name=op.f("fk_struct_types_created_by_user"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["struct_types.id"], name=op.f("fk_struct_types_parent_id_struct_types")
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"], name=op.f("fk_struct_types_subject_id_subjects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_struct_types")),
        sa.UniqueConstraint("subject_id", "code", name="uq_struct_types_subject_id_code"),
    )
    op.create_index(op.f("ix_struct_types_id"), "struct_types", ["id"], unique=False)
    op.create_index(op.f("ix_struct_types_parent_id"), "struct_types", ["parent_id"], unique=False)
    op.create_index(
        "ix_struct_types_subject_kind_status", "struct_types", ["subject_id", "kind", "status"], unique=False
    )

    op.create_table(
        "struct_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("stem_text", _LongText, nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("check_report", sa.Text(), nullable=True),
        sa.Column("check_errors", sa.Integer(), nullable=False),
        sa.Column("check_warnings", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["user.id"], name=op.f("fk_struct_runs_created_by_user"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["user.id"], name=op.f("fk_struct_runs_reviewed_by_user"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"], name=op.f("fk_struct_runs_subject_id_subjects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_struct_runs")),
    )
    op.create_index(op.f("ix_struct_runs_id"), "struct_runs", ["id"], unique=False)
    op.create_index(
        "ix_struct_runs_target_state", "struct_runs", ["target_type", "target_id", "state"], unique=False
    )
    op.create_index("ix_struct_runs_subject_state", "struct_runs", ["subject_id", "state"], unique=False)

    op.create_table(
        "struct_elements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", _LongText, nullable=False),
        sa.Column("type_id", sa.Integer(), nullable=True),
        sa.Column("type_hint", sa.String(length=255), nullable=True),
        sa.Column("facet", sa.String(length=16), nullable=True),
        sa.Column("span_start", sa.Integer(), nullable=True),
        sa.Column("span_end", sa.Integer(), nullable=True),
        sa.Column("ref_element_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["ref_element_id"], ["struct_elements.id"],
            name=op.f("fk_struct_elements_ref_element_id_struct_elements"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["struct_runs.id"], name=op.f("fk_struct_elements_run_id_struct_runs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["type_id"], ["struct_types.id"], name=op.f("fk_struct_elements_type_id_struct_types"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_struct_elements")),
    )
    op.create_index(op.f("ix_struct_elements_id"), "struct_elements", ["id"], unique=False)
    op.create_index(op.f("ix_struct_elements_type_id"), "struct_elements", ["type_id"], unique=False)
    op.create_index(op.f("ix_struct_elements_ref_element_id"), "struct_elements", ["ref_element_id"], unique=False)
    op.create_index("ix_struct_elements_run_ordinal", "struct_elements", ["run_id", "ordinal"], unique=False)

    op.create_table(
        "struct_asks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", _LongText, nullable=False),
        sa.Column("type_id", sa.Integer(), nullable=True),
        sa.Column("type_hint", sa.String(length=255), nullable=True),
        sa.Column("span_start", sa.Integer(), nullable=True),
        sa.Column("span_end", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["struct_runs.id"], name=op.f("fk_struct_asks_run_id_struct_runs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["type_id"], ["struct_types.id"], name=op.f("fk_struct_asks_type_id_struct_types"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_struct_asks")),
    )
    op.create_index(op.f("ix_struct_asks_id"), "struct_asks", ["id"], unique=False)
    op.create_index(op.f("ix_struct_asks_type_id"), "struct_asks", ["type_id"], unique=False)
    op.create_index("ix_struct_asks_run_ordinal", "struct_asks", ["run_id", "ordinal"], unique=False)

    op.create_table(
        "struct_ask_elements",
        sa.Column("ask_id", sa.Integer(), nullable=False),
        sa.Column("element_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ask_id"], ["struct_asks.id"], name=op.f("fk_struct_ask_elements_ask_id_struct_asks"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["element_id"], ["struct_elements.id"],
            name=op.f("fk_struct_ask_elements_element_id_struct_elements"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ask_id", "element_id", name=op.f("pk_struct_ask_elements")),
    )


def downgrade() -> None:
    op.drop_table("struct_ask_elements")
    op.drop_index("ix_struct_asks_run_ordinal", table_name="struct_asks")
    op.drop_index(op.f("ix_struct_asks_type_id"), table_name="struct_asks")
    op.drop_index(op.f("ix_struct_asks_id"), table_name="struct_asks")
    op.drop_table("struct_asks")
    op.drop_index("ix_struct_elements_run_ordinal", table_name="struct_elements")
    op.drop_index(op.f("ix_struct_elements_ref_element_id"), table_name="struct_elements")
    op.drop_index(op.f("ix_struct_elements_type_id"), table_name="struct_elements")
    op.drop_index(op.f("ix_struct_elements_id"), table_name="struct_elements")
    op.drop_table("struct_elements")
    op.drop_index("ix_struct_runs_subject_state", table_name="struct_runs")
    op.drop_index("ix_struct_runs_target_state", table_name="struct_runs")
    op.drop_index(op.f("ix_struct_runs_id"), table_name="struct_runs")
    op.drop_table("struct_runs")
    op.drop_index("ix_struct_types_subject_kind_status", table_name="struct_types")
    op.drop_index(op.f("ix_struct_types_parent_id"), table_name="struct_types")
    op.drop_index(op.f("ix_struct_types_id"), table_name="struct_types")
    op.drop_table("struct_types")
