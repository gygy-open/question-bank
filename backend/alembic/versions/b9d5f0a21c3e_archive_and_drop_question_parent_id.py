"""archive and drop question parent id

Revision ID: b9d5f0a21c3e
Revises: a8c4e7f19b2d
Create Date: 2026-09-21 00:00:00.000000

"""
from collections.abc import Sequence
import logging
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9d5f0a21c3e"
down_revision: Union[str, Sequence[str], None] = "a8c4e7f19b2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ARCHIVE_TABLE = "legacy_question_parent_audits"
_LOG = logging.getLogger("alembic.runtime.migration")


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return any(item["name"] == column for item in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_ARCHIVE_TABLE):
        op.create_table(
            _ARCHIVE_TABLE,
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("child_question_id", sa.Integer(), nullable=False),
            sa.Column("parent_question_id", sa.Integer(), nullable=False),
            sa.Column("child_subject_id", sa.Integer(), nullable=True),
            sa.Column("parent_subject_id", sa.Integer(), nullable=True),
            sa.Column("child_deleted_at", sa.DateTime(), nullable=True),
            sa.Column("parent_deleted_at", sa.DateTime(), nullable=True),
            sa.Column("is_self_reference", sa.Boolean(), nullable=False),
            sa.Column("is_parent_missing", sa.Boolean(), nullable=False),
            sa.Column("is_cross_subject", sa.Boolean(), nullable=False),
            sa.Column("has_soft_delete_mismatch", sa.Boolean(), nullable=False),
            sa.Column("relation_id", sa.Integer(), nullable=True),
            sa.Column("was_converted", sa.Boolean(), nullable=False),
            sa.Column("archived_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_legacy_question_parent_audits")),
            sa.UniqueConstraint(
                "child_question_id", name="uq_legacy_question_parent_audits_child"
            ),
        )

    inspector = sa.inspect(bind)
    if not _has_column(inspector, "questions", "parent_id"):
        return

    op.execute(sa.text("""
        INSERT INTO legacy_question_parent_audits (
            child_question_id, parent_question_id,
            child_subject_id, parent_subject_id,
            child_deleted_at, parent_deleted_at,
            is_self_reference, is_parent_missing, is_cross_subject,
            has_soft_delete_mismatch, relation_id, was_converted, archived_at
        )
        SELECT
            child.id, child.parent_id,
            child.subject_id, parent.subject_id,
            child.deleted_at, parent.deleted_at,
            CASE WHEN child.parent_id = child.id THEN 1 ELSE 0 END,
            CASE WHEN parent.id IS NULL THEN 1 ELSE 0 END,
            CASE WHEN parent.id IS NOT NULL AND NOT (
                parent.subject_id = child.subject_id OR
                (parent.subject_id IS NULL AND child.subject_id IS NULL)
            ) THEN 1 ELSE 0 END,
            CASE WHEN parent.id IS NOT NULL AND (
                (child.deleted_at IS NULL AND parent.deleted_at IS NOT NULL) OR
                (child.deleted_at IS NOT NULL AND parent.deleted_at IS NULL)
            ) THEN 1 ELSE 0 END,
            relation.id,
            CASE WHEN relation.id IS NOT NULL THEN 1 ELSE 0 END,
            CURRENT_TIMESTAMP
        FROM questions AS child
        LEFT JOIN questions AS parent ON parent.id = child.parent_id
        LEFT JOIN question_relations AS relation
          ON relation.source_question_id = child.parent_id
         AND relation.target_question_id = child.id
         AND relation.relation_type = 'decomposed_from'
        WHERE child.parent_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM legacy_question_parent_audits AS archived
              WHERE archived.child_question_id = child.id
          )
    """))

    # Keep this predicate identical to 9417bea9971b.
    op.execute(sa.text("""
        INSERT INTO question_relations
            (source_question_id, target_question_id, relation_type, created_at, created_by)
        SELECT parent_id, id, 'decomposed_from', CURRENT_TIMESTAMP, created_by
        FROM questions AS child
        WHERE parent_id IS NOT NULL
          AND parent_id <> id
          AND EXISTS (
              SELECT 1 FROM questions AS parent
              WHERE parent.id = child.parent_id
                AND (
                    parent.subject_id = child.subject_id OR
                    (parent.subject_id IS NULL AND child.subject_id IS NULL)
                )
          )
          AND NOT EXISTS (
              SELECT 1 FROM question_relations AS relation
              WHERE relation.source_question_id = child.parent_id
                AND relation.target_question_id = child.id
                AND relation.relation_type = 'decomposed_from'
          )
    """))
    op.execute(sa.text("""
        UPDATE legacy_question_parent_audits
        SET relation_id = (
                SELECT MIN(relation.id) FROM question_relations AS relation
                WHERE relation.source_question_id = parent_question_id
                  AND relation.target_question_id = child_question_id
                  AND relation.relation_type = 'decomposed_from'
            ),
            was_converted = CASE WHEN EXISTS (
                SELECT 1 FROM question_relations AS relation
                WHERE relation.source_question_id = parent_question_id
                  AND relation.target_question_id = child_question_id
                  AND relation.relation_type = 'decomposed_from'
            ) THEN 1 ELSE 0 END
    """))

    counts = bind.execute(sa.text("""
        SELECT COUNT(*) AS total,
               SUM(is_self_reference) AS self_refs,
               SUM(is_parent_missing) AS missing_parents,
               SUM(is_cross_subject) AS cross_subjects,
               SUM(has_soft_delete_mismatch) AS soft_delete_mismatches,
               SUM(was_converted) AS converted
        FROM legacy_question_parent_audits
    """)).one()
    _LOG.info(
        "Archived legacy question parent edges: total=%s converted=%s self=%s missing=%s cross_subject=%s soft_delete_mismatch=%s",
        *(value or 0 for value in (counts.total, counts.converted, counts.self_refs,
                                   counts.missing_parents, counts.cross_subjects,
                                   counts.soft_delete_mismatches)),
    )

    inspector = sa.inspect(bind)
    foreign_keys = [
        fk for fk in inspector.get_foreign_keys("questions")
        if fk.get("constrained_columns") == ["parent_id"] and fk.get("name")
    ]
    indexes = [
        index for index in inspector.get_indexes("questions")
        if index.get("column_names") == ["parent_id"]
    ]
    with op.batch_alter_table("questions", schema=None) as batch_op:
        for foreign_key in foreign_keys:
            batch_op.drop_constraint(foreign_key["name"], type_="foreignkey")
        for index in indexes:
            batch_op.drop_index(index["name"])
        batch_op.drop_column("parent_id")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, "questions", "parent_id"):
        with op.batch_alter_table("questions", schema=None) as batch_op:
            batch_op.add_column(sa.Column("parent_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_questions_parent_id_questions",
                "questions",
                ["parent_id"],
                ["id"],
            )
            batch_op.create_index("ix_questions_parent_id", ["parent_id"], unique=False)

    if sa.inspect(bind).has_table(_ARCHIVE_TABLE):
        op.execute(sa.text("""
            UPDATE questions
            SET parent_id = (
                SELECT archived.parent_question_id
                FROM legacy_question_parent_audits AS archived
                WHERE archived.child_question_id = questions.id
                  AND EXISTS (
                      SELECT 1 FROM questions AS parent
                      WHERE parent.id = archived.parent_question_id
                  )
            )
            WHERE EXISTS (
                SELECT 1 FROM legacy_question_parent_audits AS archived
                WHERE archived.child_question_id = questions.id
                  AND EXISTS (
                      SELECT 1 FROM questions AS parent
                      WHERE parent.id = archived.parent_question_id
                  )
            )
        """))
        op.drop_table(_ARCHIVE_TABLE)
