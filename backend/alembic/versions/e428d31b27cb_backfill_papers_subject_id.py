"""backfill papers subject id

Revision ID: e428d31b27cb
Revises: d6dad2112494
Create Date: 2026-08-08 16:43:32.710783

Data-only migration: `papers.subject_id` already exists (nullable) since
cd840eec8ffb, but legacy rows (created before per-subject isolation, or via
the quick-paper/legacy-basket flow) were never given one. This backfills
those rows so the "我的试卷" list can start filtering by the global subject
context without silently hiding pre-existing papers.

Backfill target per paper: owner's last_active_subject_id, else owner's
legacy subject_id, else the system's first subject (orphan fallback, mirrors
the tag/tag_category subject-isolation migrations). No column is added or
altered, and NULLs are left in place if a system has no subjects at all —
fully backward compatible and reversible (a no-op downgrade).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e428d31b27cb'
down_revision: Union[str, Sequence[str], None] = 'd6dad2112494'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Backfill NULL papers.subject_id from owner's subject, or system default."""
    conn = op.get_bind()

    # Inline table definitions (do NOT import ORM models: migrations are
    # time-frozen and must stay replayable regardless of future model changes).
    papers = sa.table(
        'papers',
        sa.column('id', sa.Integer),
        sa.column('owner_id', sa.Integer),
        sa.column('subject_id', sa.Integer),
    )
    users = sa.table(
        'user',
        sa.column('id', sa.Integer),
        sa.column('subject_id', sa.Integer),
        sa.column('last_active_subject_id', sa.Integer),
    )
    subjects = sa.table('subjects', sa.column('id', sa.Integer))

    # 1. Backfill from each owner's current subject (last active, else legacy).
    owners = conn.execute(
        sa.select(users.c.id, users.c.last_active_subject_id, users.c.subject_id)
    ).fetchall()
    for owner_id, last_sid, sid in owners:
        target = last_sid or sid
        if target is not None:
            conn.execute(
                papers.update()
                .where(sa.and_(papers.c.owner_id == owner_id, papers.c.subject_id.is_(None)))
                .values(subject_id=target)
            )

    # 2. Orphans (owner has no subject at all) -> system's first subject.
    default_sid = conn.execute(
        sa.select(subjects.c.id).order_by(subjects.c.id).limit(1)
    ).scalar()
    if default_sid is not None:
        conn.execute(
            papers.update().where(papers.c.subject_id.is_(None)).values(subject_id=default_sid)
        )
    # If the system has zero subjects, rows are left NULL — nothing to assign yet.


def downgrade() -> None:
    """No-op: reverting a data backfill would require distinguishing rows that
    were genuinely NULL before from newly-created ones, which isn't tracked."""
    pass
