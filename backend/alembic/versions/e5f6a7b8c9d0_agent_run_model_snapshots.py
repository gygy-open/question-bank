"""Preserve AI model identity when model configuration is deleted.

Revision ID: e5f6a7b8c9d0
Revises: b7c1e94d2a35
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "b7c1e94d2a35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_NAME = "fk_agent_runs_model_id_ai_models"


def _replace_model_fk(*, ondelete: str | None) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("agent_runs") as batch_op:
            batch_op.drop_constraint(_FK_NAME, type_="foreignkey")
            batch_op.create_foreign_key(
                _FK_NAME,
                "ai_models",
                ["model_id"],
                ["id"],
                ondelete=ondelete,
            )
        return

    op.drop_constraint(_FK_NAME, "agent_runs", type_="foreignkey")
    op.create_foreign_key(
        _FK_NAME,
        "agent_runs",
        "ai_models",
        ["model_id"],
        ["id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("model_name", sa.String(100), nullable=True))
    op.add_column("agent_runs", sa.Column("provider_name", sa.String(100), nullable=True))
    op.execute(
        """
        UPDATE agent_runs
           SET model_name = (
                   SELECT ai_models.name
                     FROM ai_models
                    WHERE ai_models.id = agent_runs.model_id
               ),
               provider_name = (
                   SELECT ai_providers.name
                     FROM ai_providers
                     JOIN ai_models ON ai_models.provider_id = ai_providers.id
                    WHERE ai_models.id = agent_runs.model_id
               )
         WHERE model_id IS NOT NULL
        """
    )
    _replace_model_fk(ondelete="SET NULL")


def downgrade() -> None:
    _replace_model_fk(ondelete=None)
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_column("provider_name")
        batch_op.drop_column("model_name")