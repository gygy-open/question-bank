"""permission v1: subject_members + question visibility

Revision ID: a1b2c3d4e5f6
Revises: c2d3e4f5a6b7
Create Date: 2026-09-07 10:00:00.000000

权限方案 v1(RBAC-lite),纯结构变更:
  * 新建 subject_members(user-学科成员关系,role 存字符串,取值由应用层校验)。
  * questions 增加 visibility 列(public/private),存量行由 server_default 落到 public。

不做任何用户数据迁移:既有 is_superuser 保持不变(创建默认 False,值可信);学科成员
由管理员在成员管理界面按需分配(不从 user.subject_id 回填 —— 该字段已废弃、基本恒为 NULL)。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subject_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"],
            name=op.f("fk_subject_members_user_id_user"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"],
            name=op.f("fk_subject_members_subject_id_subjects"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subject_members")),
        sa.UniqueConstraint("user_id", "subject_id", name="user_subject"),
    )
    op.create_index(
        op.f("ix_subject_members_id"), "subject_members", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_subject_members_user_id"), "subject_members", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_subject_members_subject_id"), "subject_members", ["subject_id"], unique=False
    )

    # server_default 让存量题目落到 public。
    op.add_column(
        "questions",
        sa.Column(
            "visibility",
            sa.String(length=20),
            nullable=False,
            server_default="public",
        ),
    )
    op.create_index(
        op.f("ix_questions_visibility"), "questions", ["visibility"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_questions_visibility"), table_name="questions")
    op.drop_column("questions", "visibility")
    # DROP TABLE 会一并移除其索引与外键;不能先单独 drop FK 依赖的索引(MySQL 报 1553)。
    op.drop_table("subject_members")
