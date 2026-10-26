"""Personal AI providers, per-user model preferences, encrypted API keys.

Revision ID: a9c3d5e7f1b2
Revises: e5f6a7b8c9d0
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9c3d5e7f1b2"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_providers") as batch_op:
        batch_op.drop_index("ix_ai_providers_name")
        batch_op.create_index("ix_ai_providers_name", ["name"], unique=False)
        batch_op.alter_column(
            "api_key", existing_type=sa.String(255), type_=sa.String(512), existing_nullable=False
        )
        batch_op.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_ai_providers_owner_id", ["owner_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_ai_providers_owner_id_user", "user", ["owner_id"], ["id"], ondelete="CASCADE"
        )

    op.create_table(
        "user_ai_preferences",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("text_model_id", sa.Integer(), sa.ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True),
        sa.Column("vision_model_id", sa.Integer(), sa.ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True),
    )

    from app.core.secrets import encrypt_secret

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, api_key FROM ai_providers")).fetchall()
    for row_id, api_key in rows:
        encrypted = encrypt_secret(api_key or "")
        if encrypted != api_key:
            bind.execute(
                sa.text("UPDATE ai_providers SET api_key = :k WHERE id = :i"),
                {"k": encrypted, "i": row_id},
            )


def downgrade() -> None:
    from app.core.secrets import decrypt_secret

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, api_key FROM ai_providers")).fetchall()
    for row_id, api_key in rows:
        bind.execute(
            sa.text("UPDATE ai_providers SET api_key = :k WHERE id = :i"),
            {"k": decrypt_secret(api_key), "i": row_id},
        )
    bind.execute(sa.text("DELETE FROM ai_models WHERE provider_id IN (SELECT id FROM ai_providers WHERE owner_id IS NOT NULL)"))
    bind.execute(sa.text("DELETE FROM ai_providers WHERE owner_id IS NOT NULL"))

    op.drop_table("user_ai_preferences")
    with op.batch_alter_table("ai_providers") as batch_op:
        batch_op.drop_constraint("fk_ai_providers_owner_id_user", type_="foreignkey")
        batch_op.drop_index("ix_ai_providers_owner_id")
        batch_op.drop_column("owner_id")
        batch_op.alter_column(
            "api_key", existing_type=sa.String(512), type_=sa.String(255), existing_nullable=False
        )
        batch_op.drop_index("ix_ai_providers_name")
        batch_op.create_index("ix_ai_providers_name", ["name"], unique=True)
