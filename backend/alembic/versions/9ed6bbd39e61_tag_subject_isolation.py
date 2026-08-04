"""tag subject isolation

Revision ID: 9ed6bbd39e61
Revises: cd840eec8ffb
Create Date: 2026-08-04 22:12:08.495195

This migration makes tags subject-scoped:
  * adds tags.subject_id
  * splits cross-subject tags into per-subject copies and redirects the
    question_tags associations accordingly
  * assigns orphan tags (unused, or only used by questions without a subject)
    to the first subject
  * replaces the global unique(name) with unique(subject_id, name)

The data migration is dialect-agnostic (works on both SQLite and MySQL):
  * no multi-table UPDATE ... JOIN (SQLite unsupported)
  * inserted_primary_key instead of driver-specific lastrowid
  * batch_alter_table for the SQLite ALTER limitations
  * inline sa.table() definitions instead of importing ORM models

WARNING: this migration is NOT losslessly reversible (cross-subject tags are
cloned, and downgrade cannot restore the original global names without
conflicts). Back up the database before upgrading.
"""
from typing import Sequence, Union
from collections import defaultdict

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9ed6bbd39e61'
down_revision: Union[str, Sequence[str], None] = 'cd840eec8ffb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema + migrate data."""
    conn = op.get_bind()

    # 1. Add the column as nullable first so existing rows don't violate NOT NULL.
    op.add_column('tags', sa.Column('subject_id', sa.Integer(), nullable=True))

    # 2. Inline table definitions (do NOT import ORM models: migrations are
    #    time-frozen and must remain replayable regardless of future model changes).
    tags = sa.table(
        'tags',
        sa.column('id', sa.Integer),
        sa.column('name', sa.String),
        sa.column('category', sa.String),
        sa.column('color', sa.String),
        sa.column('subject_id', sa.Integer),
    )
    qt = sa.table(
        'question_tags',
        sa.column('question_id', sa.Integer),
        sa.column('tag_id', sa.Integer),
    )
    questions = sa.table(
        'questions',
        sa.column('id', sa.Integer),
        sa.column('subject_id', sa.Integer),
    )

    # 3. Determine which subjects each tag is actually used by.
    rows = conn.execute(
        sa.select(qt.c.tag_id, questions.c.subject_id)
        .select_from(qt.join(questions, qt.c.question_id == questions.c.id))
        .where(questions.c.subject_id.isnot(None))
        .distinct()
    ).fetchall()

    tag_subjects: dict = defaultdict(set)
    for tag_id, sid in rows:
        tag_subjects[tag_id].add(sid)

    for tag_id, sids in tag_subjects.items():
        first, *rest = list(sids)
        # Single-subject tag (or the first subject of a cross-subject tag):
        # reuse the original tag row.
        conn.execute(
            tags.update().where(tags.c.id == tag_id).values(subject_id=first)
        )
        # Cross-subject tag: clone a dedicated copy per remaining subject and
        # redirect that subject's question associations to the clone.
        for sid in rest:
            src = conn.execute(
                sa.select(tags.c.name, tags.c.category, tags.c.color)
                .where(tags.c.id == tag_id)
            ).fetchone()
            res = conn.execute(
                tags.insert().values(
                    name=src.name,
                    category=src.category,
                    color=src.color,
                    subject_id=sid,
                )
            )
            new_id = res.inserted_primary_key[0]

            # Redirect per-question (avoid the multi-table UPDATE ... JOIN that
            # SQLite does not support): first collect the question ids, then IN().
            q_ids = [
                r[0]
                for r in conn.execute(
                    sa.select(questions.c.id).where(questions.c.subject_id == sid)
                ).fetchall()
            ]
            if q_ids:
                conn.execute(
                    qt.update()
                    .where(sa.and_(qt.c.tag_id == tag_id, qt.c.question_id.in_(q_ids)))
                    .values(tag_id=new_id)
                )

    # 4. Orphan tags (never used, or only used by subject-less questions)
    #    -> assign to the first subject.
    subjects = sa.table('subjects', sa.column('id', sa.Integer))
    default_sid = conn.execute(
        sa.select(subjects.c.id).order_by(subjects.c.id).limit(1)
    ).scalar()
    if default_sid is not None:
        conn.execute(
            tags.update().where(tags.c.subject_id.is_(None)).values(subject_id=default_sid)
        )

    # 5. Tighten constraints. batch mode handles SQLite's ALTER limitations
    #    (rebuild table) and degrades to plain ALTER on MySQL.
    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.alter_column('subject_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_index(batch_op.f('ix_tags_name'))
        batch_op.create_index(batch_op.f('ix_tags_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_tags_subject_id'), ['subject_id'], unique=False)
        batch_op.create_unique_constraint('uq_tag_subject_name', ['subject_id', 'name'])
        batch_op.create_foreign_key('fk_tags_subject_id', 'subjects', ['subject_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema.

    Note: cloned per-subject tags are left in place; restoring the global
    unique(name) index may fail if duplicate names now exist. This migration is
    intentionally not losslessly reversible.
    """
    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.drop_constraint('fk_tags_subject_id', type_='foreignkey')
        batch_op.drop_constraint('uq_tag_subject_name', type_='unique')
        batch_op.drop_index(batch_op.f('ix_tags_subject_id'))
        batch_op.drop_index(batch_op.f('ix_tags_name'))
        batch_op.create_index(batch_op.f('ix_tags_name'), ['name'], unique=True)
        batch_op.drop_column('subject_id')
