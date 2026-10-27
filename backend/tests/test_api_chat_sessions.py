"""会话接口:读取/删除带消息的会话不能在 async 下触发懒加载(MissingGreenlet)。"""
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.crud.crud_chat import chat_message
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.schemas.chat import ChatMessageCreate


async def test_delete_session_with_messages(client, db_session):
    user = User(username="deleter", full_name="deleter", hashed_password="x", is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    created = (await client.post("/api/v1/chat/sessions", json={"title": "t"}, headers=headers)).json()
    db_session.add_all([
        ChatMessage(session_id=created["id"], role="user", content="hi"),
        ChatMessage(session_id=created["id"], role="assistant", content="hello"),
    ])
    await db_session.commit()

    resp = await client.delete(f"/api/v1/chat/sessions/{created['id']}", headers=headers)
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    assert await db_session.get(ChatSession, created["id"]) is None
    remaining = await db_session.scalar(
        select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == created["id"])
    )
    assert remaining == 0


async def test_get_session_with_messages(client, db_session):
    user = User(username="reader", full_name="reader", hashed_password="x", is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    created = (await client.post("/api/v1/chat/sessions", json={"title": "t"}, headers=headers)).json()
    # 用户消息走 CRUDBase.create,会显式传 tool_calls=None;必须存成 SQL NULL 才能通过 transcript 过滤
    await chat_message.create(db_session, obj_in={
        **ChatMessageCreate(role="user", content="hi").model_dump(), "session_id": created["id"],
    })
    db_session.add(ChatMessage(session_id=created["id"], role="assistant", content="hello"))
    await db_session.commit()

    resp = await client.get(f"/api/v1/chat/sessions/{created['id']}", headers=headers)
    assert resp.status_code == 200, resp.text
    assert [m["role"] for m in resp.json()["messages"]] == ["user", "assistant"]
