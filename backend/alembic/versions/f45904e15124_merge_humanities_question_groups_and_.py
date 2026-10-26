"""merge humanities question groups and personal ai providers

Revision ID: f45904e15124
Revises: a7b1d4e5f6c8, a9c3d5e7f1b2
Create Date: 2026-10-26 15:14:33.793389

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f45904e15124'
down_revision: Union[str, Sequence[str], None] = ('a7b1d4e5f6c8', 'a9c3d5e7f1b2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
