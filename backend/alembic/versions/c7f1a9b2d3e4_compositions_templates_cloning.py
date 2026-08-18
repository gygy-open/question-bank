"""compositions: drop comp_type & component_ref, add is_template

Revision ID: c7f1a9b2d3e4
Revises: b08b1727b16a
Create Date: 2026-08-18

去枚举化与模板/克隆改造:
- 存量 component_ref 块就地展开为深拷贝的普通块 (单层), 随后移除 ref_composition_id。
- 删除 compositions.comp_type (及索引)。
- 新增 compositions.is_template (模板库标记)。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7f1a9b2d3e4'
down_revision = 'b08b1727b16a'
branch_labels = None
depends_on = None


def _expand_component_refs(conn) -> None:
    """把 component_ref 块替换为被引组稿的有序块深拷贝 (单层)。"""
    comp_ids = [
        r[0]
        for r in conn.execute(
            sa.text(
                "SELECT DISTINCT composition_id FROM composition_blocks "
                "WHERE block_type = 'component_ref'"
            )
        ).fetchall()
    ]
    for comp_id in comp_ids:
        blocks = conn.execute(
            sa.text(
                "SELECT block_type, content, ref_question_id, ref_composition_id "
                "FROM composition_blocks WHERE composition_id = :c ORDER BY sequence"
            ),
            {"c": comp_id},
        ).fetchall()

        expanded = []
        for bt, content, ref_q, ref_c in blocks:
            if bt == 'component_ref' and ref_c:
                sub = conn.execute(
                    sa.text(
                        "SELECT block_type, content, ref_question_id "
                        "FROM composition_blocks "
                        "WHERE composition_id = :c AND block_type != 'component_ref' "
                        "ORDER BY sequence"
                    ),
                    {"c": ref_c},
                ).fetchall()
                for s_bt, s_content, s_rq in sub:
                    expanded.append((s_bt, s_content, s_rq))
            else:
                expanded.append((bt, content, ref_q))

        conn.execute(
            sa.text("DELETE FROM composition_blocks WHERE composition_id = :c"),
            {"c": comp_id},
        )
        for seq, (bt, content, rq) in enumerate(expanded):
            conn.execute(
                sa.text(
                    "INSERT INTO composition_blocks "
                    "(composition_id, block_type, sequence, content, ref_question_id, ref_composition_id) "
                    "VALUES (:c, :bt, :seq, :content, :rq, NULL)"
                ),
                {"c": comp_id, "bt": bt, "seq": seq, "content": content, "rq": rq},
            )


def upgrade() -> None:
    conn = op.get_bind()
    _expand_component_refs(conn)

    with op.batch_alter_table('composition_blocks') as batch_op:
        batch_op.drop_constraint(
            'fk_composition_blocks_ref_composition_id_compositions', type_='foreignkey'
        )
        batch_op.drop_column('ref_composition_id')

    with op.batch_alter_table('compositions') as batch_op:
        batch_op.drop_index('ix_compositions_comp_type')
        batch_op.drop_column('comp_type')
        batch_op.add_column(
            sa.Column('is_template', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.create_index('ix_compositions_is_template', ['is_template'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('compositions') as batch_op:
        batch_op.drop_index('ix_compositions_is_template')
        batch_op.drop_column('is_template')
        batch_op.add_column(
            sa.Column('comp_type', sa.String(length=50), nullable=False, server_default='exam_paper')
        )
        batch_op.create_index('ix_compositions_comp_type', ['comp_type'], unique=False)

    with op.batch_alter_table('composition_blocks') as batch_op:
        batch_op.add_column(sa.Column('ref_composition_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_composition_blocks_ref_composition_id_compositions',
            'compositions', ['ref_composition_id'], ['id'],
        )
