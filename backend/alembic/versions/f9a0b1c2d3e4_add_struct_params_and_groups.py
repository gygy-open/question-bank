"""add struct params and element groups

Revision ID: f9a0b1c2d3e4
Revises: d2e3f4a5b6c7
Create Date: 2026-11-04 16:00:00.000000

补回上游 feat/question-structure 缺失的两张表，用于「旋钮」式条件重组与原创命题：

- question_struct_params：参数槽，标记元素中哪些是可替换的（改数/改条件/改问法）
- question_struct_element_groups / question_struct_element_group_items：可整体替换的元素组

不改动 questions / struct_runs / struct_elements / struct_asks 的任何字段，全部旁挂。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- 参数槽：变式生成的抓手 ----------
    op.create_table(
        "question_struct_params",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("element_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=False),
        sa.Column("slot_kind", sa.String(length=32), nullable=True),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("replaceable", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["element_id"],
            ["struct_elements.id"],
            name=op.f("fk_question_struct_params_element_id_struct_elements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_struct_params")),
    )
    op.create_index(op.f("ix_question_struct_params_id"), "question_struct_params", ["id"], unique=False)
    op.create_index(
        op.f("ix_question_struct_params_element_id"),
        "question_struct_params",
        ["element_id"],
        unique=False,
    )

    # ---------- 可整体替换的元素组 ----------
    op.create_table(
        "question_struct_element_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("replaceable", sa.Integer(), server_default="1", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["struct_runs.id"],
            name=op.f("fk_question_struct_element_groups_run_id_struct_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_struct_element_groups")),
    )
    op.create_index(op.f("ix_question_struct_element_groups_id"), "question_struct_element_groups", ["id"], unique=False)
    op.create_index(
        op.f("ix_question_struct_element_groups_run_id"),
        "question_struct_element_groups",
        ["run_id"],
        unique=False,
    )

    # ---------- 元素组与元素的多对多关联 ----------
    op.create_table(
        "question_struct_element_group_items",
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("element_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["question_struct_element_groups.id"],
            name=op.f("fk_question_struct_element_group_items_group_id_question_struct_element_groups"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["element_id"],
            ["struct_elements.id"],
            name=op.f("fk_question_struct_element_group_items_element_id_struct_elements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("group_id", "element_id", name=op.f("pk_question_struct_element_group_items")),
    )
    op.create_index(
        op.f("ix_question_struct_element_group_items_group_id"),
        "question_struct_element_group_items",
        ["group_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_question_struct_element_group_items_element_id"),
        "question_struct_element_group_items",
        ["element_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_question_struct_element_group_items_element_id"), table_name="question_struct_element_group_items")
    op.drop_index(op.f("ix_question_struct_element_group_items_group_id"), table_name="question_struct_element_group_items")
    op.drop_table("question_struct_element_group_items")
    op.drop_index(op.f("ix_question_struct_element_groups_run_id"), table_name="question_struct_element_groups")
    op.drop_index(op.f("ix_question_struct_element_groups_id"), table_name="question_struct_element_groups")
    op.drop_table("question_struct_element_groups")
    op.drop_index(op.f("ix_question_struct_params_element_id"), table_name="question_struct_params")
    op.drop_index(op.f("ix_question_struct_params_id"), table_name="question_struct_params")
    op.drop_table("question_struct_params")
