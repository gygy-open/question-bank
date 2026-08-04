"""user last active subject

Revision ID: be950d8c78c6
Revises: 9ed6bbd39e61
Create Date: 2026-08-04 22:14:32.343428

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'be950d8c78c6'
down_revision: Union[str, Sequence[str], None] = '9ed6bbd39e61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_active_subject_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_user_last_active_subject_id', 'subjects', ['last_active_subject_id'], ['id']
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('fk_user_last_active_subject_id', type_='foreignkey')
        batch_op.drop_column('last_active_subject_id')
