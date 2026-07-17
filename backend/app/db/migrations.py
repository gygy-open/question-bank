"""Programmatic Alembic runner.

Used by the first-run setup wizard to apply migrations right after the user
picks a database, and resolves the alembic config in a way that also works from
a frozen (PyInstaller) desktop build where files live under ``sys._MEIPASS``.
"""

import sys
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config


def _base_dir() -> Path:
    """Directory that contains ``alembic.ini`` and the ``alembic/`` folder."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # migrations.py -> app/db/migrations.py, parents[2] == backend/
    return Path(__file__).resolve().parents[2]


def _alembic_config(url: Optional[str] = None) -> Config:
    base = _base_dir()
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    if url:
        cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def run_migrations(url: Optional[str] = None) -> None:
    """Upgrade the database to ``head``.

    Runs synchronously; call it from a worker thread when inside an event loop
    (e.g. ``await run_in_threadpool(run_migrations, url)``).
    """
    command.upgrade(_alembic_config(url), "head")
