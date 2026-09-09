from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.crud.base import CRUDBase
from app.models.chat import ChatSession, ChatMessage
from app.schemas.chat import ChatSessionCreate, ChatSessionUpdate, ChatMessageCreate, ChatMessageUpdate


def _transcript_only():
    """工具往返(role=tool 与带 tool_calls 的 assistant)只是模型上下文,不进对话记录。"""
    return (ChatMessage.role != "tool") & (ChatMessage.tool_calls.is_(None))

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
            .where(_transcript_only())
            .order_by(desc(ChatMessage.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        return result.scalars().all()

    async def get_transcript(
        self, db: AsyncSession, *, session_id: str
    ) -> List[ChatMessage]:
        """用户可见的对话记录。"""
        query = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .where(_transcript_only())
            .order_by(ChatMessage.created_at)
        )
        result = await db.execute(query)
        return result.scalars().all()

chat_session = CRUDChatSession(ChatSession)
chat_message = CRUDChatMessage(ChatMessage)
