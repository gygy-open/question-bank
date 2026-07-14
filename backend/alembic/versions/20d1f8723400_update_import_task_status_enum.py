"""update_import_task_status_enum

Revision ID: 20d1f8723400
Revises: cb5af9252eaf
Create Date: 2025-12-17 23:15:26.431340

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20d1f8723400'
down_revision: Union[str, Sequence[str], None] = 'cb5af9252eaf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE import_tasks MODIFY COLUMN status ENUM('pending', 'processing', 'completed', 'failed', 'cancelled') DEFAULT 'pending'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE import_tasks MODIFY COLUMN status ENUM('pending', 'processing', 'completed', 'failed') DEFAULT 'pending'")
