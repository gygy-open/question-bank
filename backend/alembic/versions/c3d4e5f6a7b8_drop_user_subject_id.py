"""drop vestigial user.subject_id

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-09-07 18:00:00.000000

user.subject_id 是废弃字段(基本恒 NULL,仅曾作 last_active_subject_id 的兜底读)。
学科归属改由 subject_members 表承载,故删除该列及其外键与索引。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        # 先删外键(否则 MySQL 不允许删被外键引用的列/索引),名称按实际反查。
        fk = bind.execute(
            sa.text(
                "SELECT constraint_name FROM information_schema.key_column_usage "
                "WHERE table_schema=DATABASE() AND table_name='user' "
                "AND column_name='subject_id' AND referenced_table_name='subjects' LIMIT 1"
            )
        ).scalar()
        if fk:
            op.drop_constraint(fk, "user", type_="foreignkey")
        idx = bind.execute(
            sa.text(
                "SELECT index_name FROM information_schema.statistics "
                "WHERE table_schema=DATABASE() AND table_name='user' "
                "AND column_name='subject_id' LIMIT 1"
            )
        ).scalar()
        if idx:
            op.drop_index(idx, table_name="user")
        op.drop_column("user", "subject_id")
    else:
        # SQLite:batch 重建表;需显式先删索引,否则重建时会尝试重建指向已删列的索引。
        with op.batch_alter_table("user", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_user_subject_id"))
            batch_op.drop_column("subject_id")


def downgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("subject_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_user_subject_id"), ["subject_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_user_subject_id_subjects", "subjects", ["subject_id"], ["id"]
        )
