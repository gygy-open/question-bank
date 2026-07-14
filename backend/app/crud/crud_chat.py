from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from app.crud.base import CRUDBase
from app.models.chat import ChatSession, ChatMessage
from app.schemas.chat import ChatSessionCreate, ChatSessionUpdate, ChatMessageCreate, ChatMessageUpdate

class CRUDChatSession(CRUDBase[ChatSession, ChatSessionCreate, ChatSessionUpdate]):
    async def get_multi_by_user(
        self, db: AsyncSession, *, user_id: int, skip: int = 0, limit: int = 100
    ) -> List[ChatSession]:
        query = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(desc(ChatSession.updated_at))
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        return result.scalars().all()

    async def get_with_messages(self, db: AsyncSession, *, id: str) -> Optional[ChatSession]:
        query = (
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == id)
        )
        result = await db.execute(query)
        return result.scalars().first()

class CRUDChatMessage(CRUDBase[ChatMessage, ChatMessageCreate, ChatMessageUpdate]):
    async def get_by_session(
        self, db: AsyncSession, *, session_id: str, skip: int = 0, limit: int = 100
    ) -> List[ChatMessage]:
        query = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        return result.scalars().all()

    async def get_by_session_desc(
        self, db: AsyncSession, *, session_id: str, skip: int = 0, limit: int = 20
    ) -> List[ChatMessage]:
        query = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(desc(ChatMessage.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        return result.scalars().all()

chat_session = CRUDChatSession(ChatSession)
chat_message = CRUDChatMessage(ChatMessage)
