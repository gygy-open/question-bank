"""First-admin initialization state.

Database configuration (``is_configured()``) and "the first superuser exists"
are independent: a deployment may ship a pre-configured ``DB_URL`` (Docker)
yet still need its first administrator. This module owns the second state so
every runtime mode can bootstrap the admin through the UI.
"""

import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_user import user as crud_user
from app.db.session import get_sessionmaker
from app.models.user import User
from app.schemas.user import UserCreate

# Only ever flips False -> True: once an active superuser exists the API itself
# refuses to remove the last one, so there is nothing to invalidate.
_admin_ready: bool = False
# Single-process deployments (desktop, `fastapi run`) only; multiple workers
# are not covered by this lock.
_create_lock = asyncio.Lock()


class AdminAlreadyInitialized(Exception):
    pass


class UsernameTaken(Exception):
    pass


async def has_active_superuser(db: AsyncSession) -> bool:
    result = await db.execute(
        select(User.id)
        .where(User.is_superuser.is_(True), User.is_active.is_(True))
        .limit(1)
    )
    return result.first() is not None


async def count_active_superusers(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(User.id)).where(
            User.is_superuser.is_(True), User.is_active.is_(True)
        )
    )
    return int(result.scalar_one())


async def is_admin_ready() -> bool:
    """Cached check used by the request gate; hits the DB until it succeeds."""
    global _admin_ready
    if _admin_ready:
        return True
    async with get_sessionmaker()() as db:
        if await has_active_superuser(db):
            _admin_ready = True
    return _admin_ready


def mark_admin_ready() -> None:
    global _admin_ready
    _admin_ready = True


def reset_admin_ready() -> None:
    global _admin_ready
    _admin_ready = False


async def create_first_superuser(db: AsyncSession, *, username: str, password: str) -> User:
    async with _create_lock:
        if await has_active_superuser(db):
            mark_admin_ready()
            raise AdminAlreadyInitialized()
        if await crud_user.get_by_username(db, username=username):
            raise UsernameTaken()
        created = await crud_user.create(
            db,
            obj_in=UserCreate(
                username=username,
                password=password,
                is_superuser=True,
                is_active=True,
            ),
        )
        mark_admin_ready()
        return created
