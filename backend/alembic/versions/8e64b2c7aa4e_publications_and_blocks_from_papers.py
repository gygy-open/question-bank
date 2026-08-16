"""publications and blocks from papers

Revision ID: 8e64b2c7aa4e
Revises: 326519e83a77
Create Date: 2026-08-16 21:56:27.424601

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e64b2c7aa4e'
down_revision: Union[str, Sequence[str], None] = '326519e83a77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: papers -> publications, paper_questions -> publication_blocks."""
    bind = op.get_bind()

    # 1. Rename papers -> publications and add new columns
    op.rename_table('papers', 'publications')
    with op.batch_alter_table('publications', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('pub_type', sa.String(length=50), nullable=False,
                      server_default='exam_paper')
        )
        batch_op.add_column(sa.Column('difficulty', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('meta_data', sa.JSON(), nullable=True))
        batch_op.drop_index('ix_papers_owner_id')
        batch_op.drop_index('ix_papers_id')
        batch_op.create_index(batch_op.f('ix_publications_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_publications_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_publications_pub_type'), ['pub_type'], unique=False)

    # 2. Create publication_blocks
    op.create_table(
        'publication_blocks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('publication_id', sa.Integer(), nullable=False),
        sa.Column('block_type', sa.String(length=50), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('content', sa.JSON(), nullable=True),
        sa.Column('ref_question_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['publication_id'], ['publications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ref_question_id'], ['questions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('publication_blocks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_publication_blocks_id'), ['id'], unique=False)
        batch_op.create_index(
            batch_op.f('ix_publication_blocks_publication_id'), ['publication_id'], unique=False
        )
        batch_op.create_index('ix_pub_block_seq', ['publication_id', 'sequence'], unique=False)

    # 3. Create publication_knowledge_points m2m
    op.create_table(
        'publication_knowledge_points',
        sa.Column('publication_id', sa.Integer(), nullable=False),
        sa.Column('knowledge_point_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['publication_id'], ['publications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['knowledge_point_id'], ['knowledge_points.id'], ),
        sa.PrimaryKeyConstraint('publication_id', 'knowledge_point_id'),
    )

    # 4. Data migration: paper_questions rows -> publication_blocks
    #    A section_title on an item becomes a preceding heading block.
    items = bind.execute(sa.text(
        "SELECT paper_id, question_id, sequence, section_title, score "
        "FROM paper_questions ORDER BY paper_id, sequence"
    )).fetchall()

    blocks_table = sa.table(
        'publication_blocks',
        sa.column('publication_id', sa.Integer),
        sa.column('block_type', sa.String),
        sa.column('sequence', sa.Integer),
        sa.column('content', sa.JSON),
        sa.column('ref_question_id', sa.Integer),
    )

    rows_to_insert = []
    current_paper = None
    seq = 0
    for paper_id, question_id, _old_seq, section_title, score in items:
        if paper_id != current_paper:
            current_paper = paper_id
            seq = 0
        if section_title:
            rows_to_insert.append({
                'publication_id': paper_id,
                'block_type': 'heading',
                'sequence': seq,
                'content': {'text': section_title, 'level': 2},
                'ref_question_id': None,
            })
            seq += 1
        content = {'score': score} if score is not None else None
        rows_to_insert.append({
            'publication_id': paper_id,
            'block_type': 'question',
            'sequence': seq,
            'content': content,
            'ref_question_id': question_id,
        })
        seq += 1

    if rows_to_insert:
        op.bulk_insert(blocks_table, rows_to_insert)

    # 5. Drop legacy paper_questions
    with op.batch_alter_table('paper_questions', schema=None) as batch_op:
        batch_op.drop_index('ix_paper_seq')
        batch_op.drop_index(batch_op.f('ix_paper_questions_paper_id'))
        batch_op.drop_index(batch_op.f('ix_paper_questions_id'))
    op.drop_table('paper_questions')


def downgrade() -> None:
    """Downgrade schema: publications -> papers, restore paper_questions."""
    bind = op.get_bind()

    # 1. Recreate paper_questions
    op.create_table(
        'paper_questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('paper_id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('section_title', sa.String(length=255), nullable=True),
        sa.Column('score', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['paper_id'], ['publications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('paper_questions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_paper_questions_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_paper_questions_paper_id'), ['paper_id'], unique=False)
        batch_op.create_index('ix_paper_seq', ['paper_id', 'sequence'], unique=False)

    # 2. Reconstruct paper_questions from question blocks (best-effort; heading titles
    #    are folded back onto the following question item's section_title).
    blocks = bind.execute(sa.text(
        "SELECT publication_id, block_type, sequence, content, ref_question_id "
        "FROM publication_blocks ORDER BY publication_id, sequence"
    )).fetchall()

    pq_table = sa.table(
        'paper_questions',
        sa.column('paper_id', sa.Integer),
        sa.column('question_id', sa.Integer),
        sa.column('sequence', sa.Integer),
        sa.column('section_title', sa.String),
        sa.column('score', sa.Float),
    )

    import json as _json
    rows = []
    pending_title = None
    current_paper = None
    seq = 0
    for publication_id, block_type, _s, content, ref_question_id in blocks:
        if publication_id != current_paper:
            current_paper = publication_id
            seq = 0
            pending_title = None
        data = content
        if isinstance(data, str):
            try:
                data = _json.loads(data)
            except Exception:
                data = {}
        data = data or {}
        if block_type == 'heading':
            pending_title = data.get('text')
        elif block_type == 'question' and ref_question_id is not None:
            rows.append({
                'paper_id': publication_id,
                'question_id': ref_question_id,
                'sequence': seq,
                'section_title': pending_title,
                'score': data.get('score'),
            })
            pending_title = None
            seq += 1
    if rows:
        op.bulk_insert(pq_table, rows)

    # 3. Drop new tables
    op.drop_table('publication_knowledge_points')
    with op.batch_alter_table('publication_blocks', schema=None) as batch_op:
        batch_op.drop_index('ix_pub_block_seq')
        batch_op.drop_index(batch_op.f('ix_publication_blocks_publication_id'))
        batch_op.drop_index(batch_op.f('ix_publication_blocks_id'))
    op.drop_table('publication_blocks')

    # 4. Revert publications -> papers
    with op.batch_alter_table('publications', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_publications_pub_type'))
        batch_op.drop_index(batch_op.f('ix_publications_owner_id'))
        batch_op.drop_index(batch_op.f('ix_publications_id'))
        batch_op.create_index('ix_papers_owner_id', ['owner_id'], unique=False)
        batch_op.create_index('ix_papers_id', ['id'], unique=False)
        batch_op.drop_column('meta_data')
        batch_op.drop_column('difficulty')
        batch_op.drop_column('pub_type')
    op.rename_table('publications', 'papers')
