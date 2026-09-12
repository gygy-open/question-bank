"""generate_session_title 的可靠性契约。

该后台任务此前复用请求级 db —— FastAPI 的 yield 依赖会在后台任务执行前 teardown,
那个会话很可能已关闭,导致标题静默不写库。现在它自建 SessionLocal 会话,
这些测试把 chat.SessionLocal 指向测试引擎后,验证成功/空/失败三条路径。
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1.endpoints import chat as chat_endpoint
from app.crud.crud_chat import chat_session
from app.models.chat import ChatSession
from app.models.user import User


class _ScriptedProvider:
    """按脚本逐块吐 chunk;raises=True 时在流中抛错,模拟 provider 失败。"""

    def __init__(self, chunks, *, raises=False):
        self._chunks = chunks
        self._raises = raises

    async def chat_stream(self, messages, config, tools=None):
        for chunk in self._chunks:
            yield chunk
        if self._raises:
            raise RuntimeError("provider blew up")


@pytest.fixture
def patch_session_local(engine, monkeypatch):
    """让 chat.generate_session_title 自建的 SessionLocal 命中测试引擎。"""
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(chat_endpoint, "SessionLocal", maker)
    return maker


async def _seed_session(db_session) -> str:
    user = User(username="titler", full_name="titler", hashed_password="x", is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    session = ChatSession(user_id=user.id, title=None)
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session.id


_MSGS = [
    {"role": "user", "content": "什么是导数?"},
    {"role": "assistant", "content": "导数是变化率。"},
]


async def test_title_written_to_own_session(db_session, patch_session_local):
    session_id = await _seed_session(db_session)
    provider = _ScriptedProvider(["导数", "的定义"])

    await chat_endpoint.generate_session_title(session_id, _MSGS, provider, {})

    async with patch_session_local() as verify:
        refreshed = await chat_session.get(verify, id=session_id)
        assert refreshed.title == "导数的定义"


async def test_blank_title_is_not_written(db_session, patch_session_local):
    session_id = await _seed_session(db_session)
    provider = _ScriptedProvider(["   ", "\n"])

    await chat_endpoint.generate_session_title(session_id, _MSGS, provider, {})

    async with patch_session_local() as verify:
        refreshed = await chat_session.get(verify, id=session_id)
        assert refreshed.title is None


async def test_provider_failure_is_swallowed(db_session, patch_session_local):
    session_id = await _seed_session(db_session)
    provider = _ScriptedProvider(["partial"], raises=True)

    # 不应抛出:后台任务失败只记日志,标题保持未生成。
    await chat_endpoint.generate_session_title(session_id, _MSGS, provider, {})

    async with patch_session_local() as verify:
        refreshed = await chat_session.get(verify, id=session_id)
        assert refreshed.title is None
