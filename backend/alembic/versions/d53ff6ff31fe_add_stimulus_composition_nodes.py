"""add stimulus-backed question_group composition nodes

Revision ID: d53ff6ff31fe
Revises: 9417bea9971b
Create Date: 2026-09-20 22:27:35.456620

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd53ff6ff31fe'
down_revision: Union[str, Sequence[str], None] = '9417bea9971b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_KIND_CHECK = (
    "(node_kind = 'block' AND node_type IN "
    "('rich_text', 'heading', 'question', 'page_break', 'answer_space')) OR "
    "(node_kind = 'module' AND node_type IN ('question_details', 'question_group')) OR "
    "(node_kind = 'reference' AND node_type = 'answer_item')"
)
_OLD_KIND_CHECK = (
    "(node_kind = 'block' AND node_type IN "
    "('rich_text', 'heading', 'question', 'page_break', 'answer_space')) OR "
    "(node_kind = 'module' AND node_type = 'question_details') OR "
    "(node_kind = 'reference' AND node_type = 'answer_item')"
)
_NEW_SOURCE_CHECK = (
    "(node_type = 'answer_item' AND source_question_node_id IS NOT NULL "
    "AND parent_id IS NOT NULL) OR "
    "(node_type = 'answer_space' AND ((parent_id IS NULL AND "
    "source_question_node_id IS NULL) OR (parent_id IS NOT NULL AND "
    "source_question_node_id IS NOT NULL))) OR "
    "(node_type NOT IN ('answer_item', 'answer_space') AND "
    "source_question_node_id IS NULL)"
)
_OLD_SOURCE_CHECK = (
    "(node_type = 'answer_item' AND source_question_node_id IS NOT NULL "
    "AND parent_id IS NOT NULL) OR "
    "(node_type <> 'answer_item' AND source_question_node_id IS NULL)"
)
_QUESTION_GROUP_CHECK = (
    "(node_type = 'question_group' AND stimulus_id IS NOT NULL AND "
    "stimulus_revision IS NOT NULL AND content IS NOT NULL) OR "
    "(node_type <> 'question_group' AND stimulus_id IS NULL AND "
    "stimulus_revision IS NULL)"
)


def upgrade() -> None:
    """Upgrade schema.

    MySQL DDL is not transactional: a failure midway (e.g. a CHECK rejected by
    legacy rows) leaves the earlier ALTERs applied, so every step must be
    skippable on re-run or the retry dies with "Duplicate column name".
    """
    insp = sa.inspect(op.get_bind())
    table = 'composition_nodes'
    columns = {c['name'] for c in insp.get_columns(table)}
    indexes = {i['name'] for i in insp.get_indexes(table)}
    fks = {fk['name'] for fk in insp.get_foreign_keys(table)}
    checks = {c['name'] for c in insp.get_check_constraints(table)}

    def _ck(name: str) -> bool:
        return f'ck_{table}_{name}' in checks

    with op.batch_alter_table(table, schema=None) as batch_op:
        if 'stimulus_id' not in columns:
            batch_op.add_column(sa.Column('stimulus_id', sa.Integer(), nullable=True))
        if 'stimulus_revision' not in columns:
            batch_op.add_column(sa.Column('stimulus_revision', sa.Integer(), nullable=True))
        if 'ix_composition_nodes_stimulus_id' not in indexes:
            batch_op.create_index(batch_op.f('ix_composition_nodes_stimulus_id'), ['stimulus_id'], unique=False)
        if 'fk_composition_nodes_stimulus_id_stimuli' not in fks:
            batch_op.create_foreign_key(batch_op.f('fk_composition_nodes_stimulus_id_stimuli'), 'stimuli', ['stimulus_id'], ['id'])
        if _ck('kind_matches_type'):
            batch_op.drop_constraint('kind_matches_type', type_='check')
        batch_op.create_check_constraint('kind_matches_type', _NEW_KIND_CHECK)
        if _ck('source_ref_matches_type'):
            batch_op.drop_constraint('source_ref_matches_type', type_='check')
        batch_op.create_check_constraint('source_ref_matches_type', _NEW_SOURCE_CHECK)
        if _ck('question_group_ref_matches_type'):
            batch_op.drop_constraint('question_group_ref_matches_type', type_='check')
        batch_op.create_check_constraint('question_group_ref_matches_type', _QUESTION_GROUP_CHECK)


def downgrade() -> None:
    """Downgrade schema."""
    # FK -> index -> column: the only order both MySQL (1553) and SQLite batch accept.
    with op.batch_alter_table('composition_nodes', schema=None) as batch_op:
        batch_op.drop_constraint('question_group_ref_matches_type', type_='check')
        batch_op.drop_constraint('source_ref_matches_type', type_='check')
        batch_op.create_check_constraint('source_ref_matches_type', _OLD_SOURCE_CHECK)
        batch_op.drop_constraint('kind_matches_type', type_='check')
        batch_op.create_check_constraint('kind_matches_type', _OLD_KIND_CHECK)
        batch_op.drop_constraint(batch_op.f('fk_composition_nodes_stimulus_id_stimuli'), type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_composition_nodes_stimulus_id'))
        batch_op.drop_column('stimulus_revision')
        batch_op.drop_column('stimulus_id')
