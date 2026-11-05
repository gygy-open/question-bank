"""struct type induction candidates

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-11-05 12:00:00.000000

元素归纳(规格 docs/specs/question-structure.md 二期):AI 把未归类的条件 / 设问聚成
候选类型,老师确认后新建或并入类型,并回填组内条目的 type_id。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "struct_type_candidates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column("suggested_parent_id", sa.Integer(), nullable=True),
        sa.Column("similar_type_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("resolved_type_id", sa.Integer(), nullable=True),
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"], name=op.f("fk_struct_type_candidates_subject_id_subjects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["suggested_parent_id"], ["struct_types.id"],
            name=op.f("fk_struct_type_candidates_suggested_parent_id_struct_types"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["similar_type_id"], ["struct_types.id"],
            name=op.f("fk_struct_type_candidates_similar_type_id_struct_types"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_type_id"], ["struct_types.id"],
            name=op.f("fk_struct_type_candidates_resolved_type_id_struct_types"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"], ["user.id"], name=op.f("fk_struct_type_candidates_resolved_by_user"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_struct_type_candidates")),
    )
    op.create_index(op.f("ix_struct_type_candidates_id"), "struct_type_candidates", ["id"], unique=False)
    op.create_index(
        "ix_struct_type_candidates_subject_status", "struct_type_candidates", ["subject_id", "status"], unique=False
    )

    op.create_table(
        "struct_type_candidate_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("element_id", sa.Integer(), nullable=True),
        sa.Column("ask_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["struct_type_candidates.id"],
            name=op.f("fk_struct_type_candidate_items_candidate_id_struct_type_candidates"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["element_id"], ["struct_elements.id"],
            name=op.f("fk_struct_type_candidate_items_element_id_struct_elements"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ask_id"], ["struct_asks.id"],
            name=op.f("fk_struct_type_candidate_items_ask_id_struct_asks"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_struct_type_candidate_items")),
    )
    op.create_index(op.f("ix_struct_type_candidate_items_id"), "struct_type_candidate_items", ["id"], unique=False)
    for column in ("candidate_id", "element_id", "ask_id"):
        op.create_index(
            op.f(f"ix_struct_type_candidate_items_{column}"), "struct_type_candidate_items", [column], unique=False
        )


def downgrade() -> None:
    op.drop_table("struct_type_candidate_items")
    op.drop_table("struct_type_candidates")
