"""题干结构化模型的行为测试。

覆盖四件容易做错的事：级联删除、同题多版本并存、词表外键、跨步引用产出。
最后一条是这套表存在的理由——推导链必须能机器复算。
"""

import hashlib
import importlib.util
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations

import app.models as models  # noqa: F401
from app.models import Base
from app.models.question_structure import (
    ElementRole,
    ElementType,
    QuestionStructAsk,
    QuestionStructAskElement,
    QuestionStructElement,
    QuestionStructParam,
    QuestionStructProduce,
    QuestionStructRun,
    QuestionStructStep,
    QuestionStructStepProduce,
    SolvingMethod,
)

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/b3e8c1d7a402_question_structure.py"
)

NEW_TABLES = [
    "question_struct_misconceptions",
    "question_struct_step_produces",
    "question_struct_step_elements",
    "question_struct_produces",
    "question_struct_steps",
    "question_struct_params",
    "question_struct_ask_elements",
    "question_struct_asks",
    "question_struct_elements",
    "question_struct_element_groups",
    "question_struct_materials",
    "question_struct_runs",
    "struct_vocabulary_meta",
    "solving_methods",
    "element_types",
    "element_roles",
]

def _sha(text: str) -> str:
    """与上游 question_dedup 保持同一口径：utf-8 + sha256 十六进制。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


ROLES = [
    ("object", "对象"),
    ("given", "已知"),
    ("constraint", "限制"),
    ("ask", "设问"),
    ("material", "材料"),
]


async def _seed_subject_and_question(session: AsyncSession, question_id: int) -> None:
    """结构化表的 question_id 是 NOT NULL 外键，测试里必须先有一道题。"""
    from app.models.question import Question
    from app.models.subject import Subject

    subject = (await session.execute(select(Subject))).scalars().first()
    if subject is None:
        subject = Subject(name="数学", slug="math")
        session.add(subject)
        await session.flush()
    if await session.get(Question, question_id) is None:
        session.add(
            Question(
                id=question_id,
                content='{"type":"doc","content":[]}',
                q_type="free_response",
                subject_id=subject.id,
            )
        )
        await session.flush()


async def _seed_vocabulary(session: AsyncSession) -> None:
    for code, name in ROLES:
        session.add(ElementRole(code=code, name=name))
    session.add(ElementType(code="dom_algebra", domain="algebra", action="form", name="数与代数"))
    session.add(
        ElementType(
            code="alg_form", domain="algebra", action="form", name="式结构",
            parent_code="dom_algebra",
        )
    )
    session.add(ElementType(code="alg_quant", domain="algebra", action="quant", name="代数量"))
    session.add(SolvingMethod(code="deriv", name="求导判断单调与极值", weight=1.0))
    session.add(SolvingMethod(code="classify", name="分类讨论", weight=1.5))
    await session.flush()


async def _make_run(session: AsyncSession, question_id: int = 1, rev: int = 1, **kw):
    await _seed_subject_and_question(session, question_id)
    kw.setdefault("origin", "human")
    run = QuestionStructRun(question_id=question_id, rev=rev, **kw)
    session.add(run)
    await session.flush()
    return run


class TestCascade:
    async def test_deleting_run_removes_children(self, db_session: AsyncSession):
        await _seed_vocabulary(db_session)
        run = await _make_run(db_session)
        db_session.add(
            QuestionStructElement(
                run_id=run.id, ordinal=1, content="f(x)=x^3+ax+2", role="object",
                element_type="alg_form",
            )
        )
        db_session.add(
            QuestionStructAsk(run_id=run.id, ordinal=1, content="求 a 的范围", target="solve")
        )
        await db_session.flush()

        await db_session.delete(run)
        await db_session.flush()

        assert (await db_session.execute(select(QuestionStructElement))).scalars().all() == []
        assert (await db_session.execute(select(QuestionStructAsk))).scalars().all() == []


class TestVersioning:
    async def test_same_question_keeps_multiple_revisions(self, db_session: AsyncSession):
        await _make_run(db_session, question_id=7, rev=1, origin="human", state="reviewed")
        await _make_run(db_session, question_id=7, rev=2, origin="ai", state="draft")

        rows = (
            (await db_session.execute(select(QuestionStructRun).where(QuestionStructRun.question_id == 7)))
            .scalars()
            .all()
        )
        assert {r.rev for r in rows} == {1, 2}

    async def test_duplicate_revision_is_rejected(self, db_session: AsyncSession):
        await _make_run(db_session, question_id=8, rev=1)
        with pytest.raises(Exception):
            # _make_run 内部会 flush，唯一约束在这一步就抛
            await _make_run(db_session, question_id=8, rev=1)
        await db_session.rollback()


class TestVocabularyForeignKeys:
    async def test_unknown_role_is_rejected(self, db_session: AsyncSession):
        await _seed_vocabulary(db_session)
        run = await _make_run(db_session)
        db_session.add(
            QuestionStructElement(run_id=run.id, ordinal=1, content="x", role="not_a_role")
        )
        with pytest.raises(Exception):
            await db_session.flush()
        await db_session.rollback()

    async def test_vocabulary_can_grow_without_a_migration(self, db_session: AsyncSession):
        """词表是数据不是模式：新增类型只是 INSERT，不需要改 schema。"""
        await _seed_vocabulary(db_session)
        run = await _make_run(db_session)
        db_session.add(
            ElementType(code="geo_proc", domain="geometry", action="proc", name="动形")
        )
        await db_session.flush()
        db_session.add(
            QuestionStructElement(
                run_id=run.id, ordinal=1, content="点 P 在抛物线上运动", role="constraint",
                element_type="geo_proc",
            )
        )
        await db_session.flush()
        assert (
            await db_session.execute(
                select(QuestionStructElement).where(QuestionStructElement.element_type == "geo_proc")
            )
        ).scalars().all()


class TestRetrieval:
    async def test_find_questions_by_element_type(self, db_session: AsyncSession):
        await _seed_vocabulary(db_session)
        run = await _make_run(db_session, question_id=11)
        db_session.add(
            QuestionStructElement(
                run_id=run.id, ordinal=1, content="动点 P", role="constraint",
                element_type="alg_quant",
            )
        )
        await db_session.flush()

        stmt = select(QuestionStructRun.question_id).join(
            QuestionStructElement, QuestionStructElement.run_id == QuestionStructRun.id
        ).where(QuestionStructElement.element_type == "alg_quant")
        assert (await db_session.execute(stmt)).scalars().all() == [11]

    async def test_replaceable_param_slots_for_variants(self, db_session: AsyncSession):
        await _seed_vocabulary(db_session)
        run = await _make_run(db_session, question_id=12)
        element = QuestionStructElement(
            run_id=run.id, ordinal=1, content="f(x)=x^3+ax+2", role="object",
            element_type="alg_form",
        )
        db_session.add(element)
        await db_session.flush()
        db_session.add(QuestionStructParam(element_id=element.id, name="a", value_text="a",
                                           slot_kind="symbolic", replaceable=False))
        db_session.add(QuestionStructParam(element_id=element.id, name="c", value_text="2",
                                           slot_kind="numeric", domain="c>0", replaceable=True))
        await db_session.flush()

        stmt = select(QuestionStructParam.name).where(QuestionStructParam.replaceable.is_(True))
        assert (await db_session.execute(stmt)).scalars().all() == ["c"]


class TestDerivationChain:
    """这套表存在的理由：某步产出的事实，后续步骤要能引用。"""

    async def test_step_can_reference_earlier_produce(self, db_session: AsyncSession):
        await _seed_vocabulary(db_session)
        run = await _make_run(db_session, question_id=13)
        ask = QuestionStructAsk(run_id=run.id, ordinal=1, content="求 a 的范围", target="solve")
        db_session.add(ask)
        await db_session.flush()

        step1 = QuestionStructStep(run_id=run.id, ask_id=ask.id, ordinal=1, method="deriv")
        db_session.add(step1)
        await db_session.flush()
        produced = QuestionStructProduce(
            step_id=step1.id, ordinal=1, content="需 a<0", kind="premise"
        )
        db_session.add(produced)
        await db_session.flush()

        step2 = QuestionStructStep(run_id=run.id, ask_id=ask.id, ordinal=2, method="classify")
        db_session.add(step2)
        await db_session.flush()
        db_session.add(QuestionStructStepProduce(step_id=step2.id, produce_id=produced.id))
        await db_session.flush()

        # 「谁产出 a<0，哪一步用了它」
        stmt = (
            select(QuestionStructStep.ordinal)
            .join(
                QuestionStructStepProduce,
                QuestionStructStepProduce.step_id == QuestionStructStep.id,
            )
            .join(
                QuestionStructProduce,
                QuestionStructProduce.id == QuestionStructStepProduce.produce_id,
            )
            .where(QuestionStructProduce.content == "需 a<0")
        )
        users = (await db_session.execute(stmt)).scalars().all()
        assert users == [2]

    async def test_ask_links_elements(self, db_session: AsyncSession):
        await _seed_vocabulary(db_session)
        run = await _make_run(db_session, question_id=14)
        ask = QuestionStructAsk(run_id=run.id, ordinal=1, content="求 b、c", target="solve")
        element = QuestionStructElement(
            run_id=run.id, ordinal=1, content="y=-x^2+bx+c", role="object", element_type="alg_form"
        )
        db_session.add_all([ask, element])
        await db_session.flush()
        db_session.add(QuestionStructAskElement(ask_id=ask.id, element_id=element.id))
        await db_session.flush()

        assert (await db_session.execute(select(QuestionStructAskElement))).scalars().all()


class TestMigrationMatchesModels:
    """迁移跑完之后，库结构必须和模型一模一样；回滚也必须干净。"""

    def test_upgrade_then_downgrade(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            for table in NEW_TABLES:
                conn.exec_driver_sql("DROP TABLE %s" % table)

        spec = importlib.util.spec_from_file_location("mig_under_test", MIGRATION)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.upgrade()

        from sqlalchemy import inspect

        present = set(inspect(engine).get_table_names())
        assert not [t for t in NEW_TABLES if t not in present]

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            diff = compare_metadata(ctx, Base.metadata)
        assert diff == []

        with engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                migration.downgrade()
        left = [t for t in NEW_TABLES if t in set(inspect(engine).get_table_names())]
        assert left == []


class TestElementTypeTree:
    """作者的用法清单要求「元素类型树选择器，同知识点」，所以要能按父子查。"""

    async def test_children_of_a_domain_node(self, db_session: AsyncSession):
        await _seed_vocabulary(db_session)
        stmt = select(ElementType.code).where(ElementType.parent_code == "dom_algebra")
        children = (await db_session.execute(stmt)).scalars().all()
        assert "alg_form" in children

    async def test_candidate_status_for_ai_nominations(self, db_session: AsyncSession):
        """AI 归纳出的新类型进 candidate，人确认后才 active——它能提名，不能定名。"""
        await _seed_vocabulary(db_session)
        db_session.add(
            ElementType(
                code="geo_aux_circle", domain="geometry", action="qual",
                name="辅助圆", status="candidate",
            )
        )
        await db_session.flush()
        pending = (
            await db_session.execute(
                select(ElementType.code).where(ElementType.status == "candidate")
            )
        ).scalars().all()
        assert pending == ["geo_aux_circle"]

    async def test_active_types_exclude_candidates(self, db_session: AsyncSession):
        await _seed_vocabulary(db_session)
        db_session.add(
            ElementType(
                code="geo_aux_circle", domain="geometry", action="qual",
                name="辅助圆", status="candidate",
            )
        )
        await db_session.flush()
        active = (
            await db_session.execute(select(ElementType.code).where(ElementType.status == "active"))
        ).scalars().all()
        assert "geo_aux_circle" not in active


class TestStemSnapshot:
    """span 必须相对题干纯文本快照算；快照哈希用来判「已过期」。"""

    async def test_span_is_relative_to_stem_text(self, db_session: AsyncSession):
        await _seed_vocabulary(db_session)
        stem = "已知函数 f(x)=x^3+ax+2 有三个零点。"
        run = await _make_run(
            db_session, question_id=21, stem_text=stem, stem_sha256=_sha(stem)
        )
        start = stem.find("f(x)=x^3+ax+2")
        db_session.add(
            QuestionStructElement(
                run_id=run.id, ordinal=1, content="f(x)=x^3+ax+2", role="object",
                span_start=start, span_end=start + len("f(x)=x^3+ax+2"),
            )
        )
        await db_session.flush()

        element = (
            await db_session.execute(select(QuestionStructElement))
        ).scalars().one()
        assert run.stem_text[element.span_start:element.span_end] == "f(x)=x^3+ax+2"

    async def test_changed_stem_marks_run_stale(self, db_session: AsyncSession):
        """题干改了哈希就对不上，旧拆解即为过期——这是「已过期」状态的唯一依据。"""
        original = "已知函数 f(x)=x^3+ax+2 有三个零点。"
        run = await _make_run(
            db_session, question_id=22, stem_text=original, stem_sha256=_sha(original)
        )
        edited = "已知函数 f(x)=x^3+ax+2 有三个不同零点。"
        assert run.stem_sha256 != _sha(edited)

    async def test_same_stem_keeps_run_fresh(self, db_session: AsyncSession):
        stem = "已知函数 f(x)=x^3+ax+2 有三个零点。"
        run = await _make_run(
            db_session, question_id=23, stem_text=stem, stem_sha256=_sha(stem)
        )
        assert run.stem_sha256 == _sha(stem)
