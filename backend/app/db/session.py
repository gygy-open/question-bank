from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import get_db_url


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _build_engine_kwargs(url: str) -> dict:
    """Return dialect-specific keyword arguments for create_async_engine."""
    kwargs: dict = {"echo": False, "future": True}
    if _is_sqlite(url):
        # SQLite: allow use across the async threadpool.
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # MySQL / other server databases: pool tuning for long-lived processes.
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 3600
    return kwargs


def _apply_sqlite_pragmas(bound_engine) -> None:
    """Enable WAL and sane concurrency defaults so that the API process and the
    worker process can share a single SQLite file without excessive locking.

    WAL lets readers run concurrently with a single writer; busy_timeout absorbs
    transient write-lock contention instead of raising ``database is locked``.
    """

    @event.listens_for(bound_engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


# Lazily initialised so the app can start in "setup mode" before a database has
# been configured, and so the engine can be rebuilt after the setup wizard runs.
_engine = None
_sessionmaker = None


def init_engine(url: str | None = None):
    """(Re)create the async engine and sessionmaker for the given/resolved URL."""
    global _engine, _sessionmaker
    if url is None:
        url = get_db_url()
    if not url:
        raise RuntimeError(
            "Database is not configured yet. Complete the setup wizard first."
        )
    _engine = create_async_engine(url, **_build_engine_kwargs(url))
    if _is_sqlite(url):
        _apply_sqlite_pragmas(_engine)
    _sessionmaker = sessionmaker(
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        bind=_engine,
        expire_on_commit=False,
    )
    return _engine


def get_engine():
    if _engine is None:
        init_engine()
    return _engine


def get_sessionmaker():
    if _sessionmaker is None:
        init_engine()
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def reset_engine(url: str | None = None):
    """Dispose the current engine and rebuild it (used after the setup wizard)."""
    await dispose_engine()
    return init_engine(url)


class _SessionLocalProxy:
    """Backward-compatible drop-in for the old module-level ``SessionLocal``.

    Existing call-sites do ``SessionLocal()`` / ``async with SessionLocal() as db``;
    this proxy resolves the (lazily created) sessionmaker on each call.
    """

    def __call__(self):
        return get_sessionmaker()()


SessionLocal = _SessionLocalProxy()


def __getattr__(name: str):
    # Lazily resolve ``from app.db.session import engine`` used by scripts.
    if name == "engine":
        return get_engine()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
