"""tag category as real foreign key

Revision ID: b1c2d3e4f5a6
Revises: 06b9b4bbf989
Create Date: 2026-09-01 00:00:00.000000

Replaces the string soft-FK ``tags.category`` (matched against
``tag_categories.slug``) with a real ``tags.category_id`` foreign key, and
drops ``tag_categories.slug`` entirely.

Data migration (dialect-agnostic, SQLite + MySQL):
  * add tags.category_id (nullable) + index + FK
  * backfill category_id by matching the old category string to the category
    slug within the same subject; unmatched / "general" tags become NULL
    (NULL = uncategorized)
  * drop tags.category and tag_categories.slug (+ its index and unique
    constraint)

WARNING: not losslessly reversible — the downgrade restores the columns but
cannot recover slugs for categories created after this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = '06b9b4bbf989'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Inline table definitions (do NOT import ORM models: migrations are
# time-frozen and must remain replayable regardless of future model changes).
_tags = sa.table(
    'tags',
    sa.column('id', sa.Integer),
    sa.column('category', sa.String),
    sa.column('category_id', sa.Integer),
    sa.column('subject_id', sa.Integer),
)
_cats = sa.table(
    'tag_categories',
    sa.column('id', sa.Integer),
    sa.column('name', sa.String),
    sa.column('slug', sa.String),
    sa.column('subject_id', sa.Integer),
)


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add category_id nullable first so existing rows don't violate NOT NULL.
    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_tags_category_id'), ['category_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_tags_category_id_tag_categories', 'tag_categories', ['category_id'], ['id']
        )

    # 2. Backfill: match old category string to the category slug within the
    #    same subject. No UPDATE ... JOIN (SQLite unsupported): resolve in Python.
    cat_map = {
        (slug, sid): cid
        for cid, slug, sid in conn.execute(
            sa.select(_cats.c.id, _cats.c.slug, _cats.c.subject_id)
        ).fetchall()
    }
    for tid, category, sid in conn.execute(
        sa.select(_tags.c.id, _tags.c.category, _tags.c.subject_id)
    ).fetchall():
        cid = cat_map.get((category, sid))
        if cid is not None:
            conn.execute(
                sa.update(_tags).where(_tags.c.id == tid).values(category_id=cid)
            )

    # 3. Drop the old category string column.
    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tags_category'))
        batch_op.drop_column('category')

    # 4. Drop tag_categories.slug (+ its unique constraint and index).
    with op.batch_alter_table('tag_categories', schema=None) as batch_op:
        batch_op.drop_constraint('uq_tag_category_subject_slug', type_='unique')
        batch_op.drop_index(batch_op.f('ix_tag_categories_slug'))
        batch_op.drop_column('slug')


def downgrade() -> None:
    conn = op.get_bind()

    # 1. Re-add slug (nullable first for backfill), then a placeholder from id.
    with op.batch_alter_table('tag_categories', schema=None) as batch_op:
        batch_op.add_column(sa.Column('slug', sa.String(length=50), nullable=True))
    conn.execute(
        sa.update(_cats).values(slug=sa.cast(_cats.c.id, sa.String))
    )
    with op.batch_alter_table('tag_categories', schema=None) as batch_op:
        batch_op.alter_column('slug', existing_type=sa.String(length=50), nullable=False)
        batch_op.create_index(batch_op.f('ix_tag_categories_slug'), ['slug'], unique=False)
        batch_op.create_unique_constraint('uq_tag_category_subject_slug', ['subject_id', 'slug'])

    # 2. Re-add tags.category, backfill from category_id -> category slug.
    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category', sa.String(length=50), nullable=True))

    slug_by_id = {
        cid: slug
        for cid, slug in conn.execute(sa.select(_cats.c.id, _cats.c.slug)).fetchall()
    }
    for tid, category_id in conn.execute(
        sa.select(_tags.c.id, _tags.c.category_id)
    ).fetchall():
        conn.execute(
            sa.update(_tags)
            .where(_tags.c.id == tid)
            .values(category=slug_by_id.get(category_id, 'general'))
        )

    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.alter_column('category', existing_type=sa.String(length=50), nullable=False)
        batch_op.create_index(batch_op.f('ix_tags_category'), ['category'], unique=False)
        batch_op.drop_constraint('fk_tags_category_id_tag_categories', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_tags_category_id'))
        batch_op.drop_column('category_id')
