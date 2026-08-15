import os

# Must be set before importing app.core.config so the settings singleton picks a
# stable secret (no config.json write) and boots out of first-run setup mode.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DB_URL", "sqlite+aiosqlite:///:memory:")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Importing the package registers every model on Base.metadata and wires the
# string-based relationships, so create_all builds the full schema.
import app.models  # noqa: F401
from app.models.base import Base


@pytest_asyncio.fixture
async def engine():
    # In-memory SQLite shared across connections via StaticPool so data seeded
    # through db_session is visible to requests made through the API client.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest_asyncio.fixture
async def client(engine):
    # Imported lazily so the settings env above is applied first.
    from app.api import deps
    from app.main import app

    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[deps.get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
