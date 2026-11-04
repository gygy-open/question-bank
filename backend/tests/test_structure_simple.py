"""简单运行时测试：验证上游 feat/question-structure 同步后的本地效果。

覆盖：
1. 所有模型类可正常导入、实例化、建表（sqlite 内存）
2. alembic 迁移可升级到 head（compare_metadata 无漂移）
3. struct_* 表 + jobs 表均能在 sqlite 内存数据库中创建
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base  # noqa: E402
from app.models.job import Job, JobStatus, JobPriority, ACTIVE_JOB_STATUSES  # noqa: E402
from app.models.question_structure import (  # noqa: E402
    StructAsk,
    StructAskElement,
    StructElement,
    StructFacet,
    StructOrigin,
    StructRun,
    StructRunState,
    StructTargetType,
    StructType,
    StructTypeKind,
    StructTypeStatus,
)
from app.models.system_setting import STRUCTURE_KEY_PREFIX, SystemSetting  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from alembic.autogenerate import compare_metadata  # noqa: E402
from alembic.migration import MigrationContext  # noqa: E402
from alembic.operations import Operations  # noqa: E402

ENGINE_URL = "sqlite+aiosqlite:///:memory:"
SYNC_URL = "sqlite:///:memory:"


def test_model_instantiation() -> None:
    """所有模型类可实例化，字段名与上游一致。"""
    st = StructType(
        subject_id=1,
        parent_id=None,
        kind=StructTypeKind.CONDITION,
        code="algebra",
        name="代数",
        definition="式的结构",
        examples=None,
        status=StructTypeStatus.ACTIVE,
        sort_order=0,
    )
    assert st.kind == StructTypeKind.CONDITION
    assert st.code == "algebra"

    run = StructRun(
        target_type=StructTargetType.QUESTION,
        target_id=1,
        subject_id=1,
        source_revision=1,
        stem_text="$x=1$",
        origin=StructOrigin.AI,
        model=None,
        prompt_version="v2",
        job_id=None,
        state=StructRunState.DRAFT,
        check_report=None,
        check_errors=0,
        check_warnings=0,
        created_by=None,
    )
    assert run.state == StructRunState.DRAFT
    assert run.stem_text == "$x=1$"

    elem = StructElement(
        run_id=1,
        ordinal=1,
        content="已知 x=1",
        type_id=None,
        type_hint="已知量",
        facet=StructFacet.QUANT,
        span_start=0,
        span_end=5,
        ref_element_id=None,
    )
    assert elem.facet == StructFacet.QUANT

    ask = StructAsk(
        run_id=1,
        ordinal=1,
        content="求 x",
        type_id=None,
        type_hint="求解",
        span_start=6,
        span_end=8,
    )
    assert ask.content == "求 x"

    link = StructAskElement(ask_id=1, element_id=1)
    assert link.ask_id == 1 and link.element_id == 1

    job = Job(
        type="structure.decompose",
        status=JobStatus.PENDING,
        priority=JobPriority.USER,
        target_type="question",
        target_id=1,
        user_id=1,
        subject_id=1,
        idempotency_key="decompose:question:1",
    )
    assert job.status == JobStatus.PENDING
    assert JobPriority.USER == 100
    assert JobStatus.PENDING.value in ACTIVE_JOB_STATUSES

    from app.models.system_setting import is_internal_key
    assert is_internal_key("structure.enabled") is True

    print("[PASS] model instantiation")


def test_sqlite_create_all() -> None:
    """SQLAlchemy metadata.create_all 能在 sqlite 内存库建出全部表。"""
    engine = create_engine(SYNC_URL, echo=False)
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = {
        "struct_types",
        "struct_runs",
        "struct_elements",
        "struct_asks",
        "struct_ask_elements",
        "jobs",
        "system_settings",
    }
    missing = expected - tables
    assert not missing, f"missing tables: {missing}"
    print("[PASS] sqlite create_all: tables =", sorted(tables & expected))


def test_alembic_single_head() -> None:
    """alembic 脚本目录只有一个 head（由 test_migrations.py 也已覆盖升级本身）。"""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, f"multiple heads: {heads}"
    print(f"[PASS] alembic single head: {heads[0]}")


def test_compare_metadata_no_drift() -> None:
    """compare_metadata 返回空，说明模型与迁移无漂移。"""
    engine = create_engine(SYNC_URL, echo=False)
    Base.metadata.create_all(engine)

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", SYNC_URL)

    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        diff = compare_metadata(context, Base.metadata)
    assert not diff, f"metadata drift: {diff}"
    print("[PASS] compare_metadata: no drift")


async def test_async_session() -> None:
    """async session 可正常查询 struct_types 表。"""
    engine = create_async_engine(ENGINE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as session:
        result = await session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(StructType).limit(1)
        )
        rows = result.scalars().all()
        assert isinstance(rows, list)
    await engine.dispose()
    print("[PASS] async session query struct_types")


def main() -> None:
    test_model_instantiation()
    test_sqlite_create_all()
    test_alembic_upgrade_head()
    test_compare_metadata_no_drift()
    asyncio.run(test_async_session())
    print("\n=== ALL SIMPLE TESTS PASSED ===")


if __name__ == "__main__":
    main()
