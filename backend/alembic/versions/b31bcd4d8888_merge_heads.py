"""merge_heads

Revision ID: b31bcd4d8888
Revises: 2a482b053acb, 389dcef5f36c
Create Date: 2025-12-12 10:48:59.003114

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b31bcd4d8888'
down_revision: Union[str, Sequence[str], None] = ('2a482b053acb', '389dcef5f36c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
