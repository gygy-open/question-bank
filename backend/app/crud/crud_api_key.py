from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import API_KEY_DISPLAY_LEN, generate_api_key, hash_api_key
from app.crud.base import CRUDBase
from app.models.api_key import ApiKey
from app.schemas.api_key import ApiKeyCreate

# 每次请求都写 last_used_at 太频繁,超过这个间隔才落库
LAST_USED_THROTTLE = timedelta(seconds=60)


class CRUDApiKey(CRUDBase[ApiKey, ApiKeyCreate, ApiKeyCreate]):
    async def create_for_user(
        self, db: AsyncSession, *, user_id: int, obj_in: ApiKeyCreate
    ) -> Tuple[ApiKey, str]:
        """返回 (行, 明文)。明文不入库,调用方只能在此刻拿到。"""
        plaintext = generate_api_key()
        db_obj = ApiKey(
            user_id=user_id,
            name=obj_in.name,
            prefix=plaintext[:API_KEY_DISPLAY_LEN],
            key_hash=hash_api_key(plaintext),
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj, plaintext

    async def count_by_user(self, db: AsyncSession, *, user_id: int) -> int:
        result = await db.execute(
            select(func.count()).select_from(ApiKey).where(ApiKey.user_id == user_id)
        )
        return int(result.scalar_one())

    async def list_by_user(self, db: AsyncSession, *, user_id: int) -> List[ApiKey]:
        result = await db.execute(
            select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc(), ApiKey.id.desc())
        )
        return list(result.scalars().all())

    async def list_all(self, db: AsyncSession) -> List[ApiKey]:
        result = await db.execute(
            select(ApiKey)
            .options(selectinload(ApiKey.user))
            .order_by(ApiKey.created_at.desc(), ApiKey.id.desc())
        )
        return list(result.scalars().all())

    async def get_by_plaintext(self, db: AsyncSession, *, key: str) -> Optional[ApiKey]:
        result = await db.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(key)))
        return result.scalars().first()

    async def touch(self, db: AsyncSession, *, api_key: ApiKey, now: Optional[datetime] = None) -> None:
        now = now or datetime.utcnow()
        if api_key.last_used_at is None or now - api_key.last_used_at >= LAST_USED_THROTTLE:
            api_key.last_used_at = now
            await db.commit()


api_key = CRUDApiKey(ApiKey)
