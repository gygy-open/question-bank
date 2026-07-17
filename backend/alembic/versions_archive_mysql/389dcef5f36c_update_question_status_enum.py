"""update_question_status_enum

Revision ID: 389dcef5f36c
Revises: f6b25e7c3fc4
Create Date: 2025-12-12 10:17:22.874784

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '389dcef5f36c'
down_revision: Union[str, Sequence[str], None] = 'f6b25e7c3fc4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # MySQL requires explicit modification for ENUM columns
    op.execute("ALTER TABLE questions MODIFY COLUMN status ENUM('draft', 'pending', 'published', 'archived') NOT NULL DEFAULT 'published'")


def downgrade() -> None:
    """Downgrade schema."""
    # Revert back to original ENUM values
    # Note: This might fail if there are 'pending' rows. Ideally we should handle that, 
    # but for now we assume this is a dev environment or we won't downgrade with data.
    op.execute("UPDATE questions SET status = 'draft' WHERE status = 'pending'")
    op.execute("ALTER TABLE questions MODIFY COLUMN status ENUM('draft', 'published', 'archived') NOT NULL DEFAULT 'published'")
