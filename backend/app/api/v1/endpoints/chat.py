from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.api import deps
from app.schemas.chat import ChatRequest, ChatSession, ChatSessionCreate, ChatSessionUpdate, ChatMessageCreate, ChatMessage, ChatSessionSummary, ChatMessageUpdate, ClientToolResult
from app.models.chat import ChatMessage as ChatMessageModel
from app.models.ai_config import AIModel
from app.crud.crud_chat import chat_session, chat_message
from app.db.session import SessionLocal
from app.services.ai_provider import get_ai_provider
from app.ai.adapters.sse import sse_pack, to_sse
from app.ai.events import AssistantTurn, RunFinished, ToolCallFinished
from app.ai.runtime import AgentRunner
from app.ai.contracts import AgentScene
from app.ai import client_channel
from app.models.agent import AgentRun
from app.capabilities.context import ExecutionContext, Surface
from app.services.prompt_utils import render_subject_prompt
from app.services.prompts import CHAT_SYSTEM_PROMPT, render_scene_context
from app.models.subject import Subject
from fastapi.responses import StreamingResponse
import logging
import base64
import aiofiles
from typing import List, Dict, Any, Optional

from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

# 只有最近这么多个 run 的工具结果保留完整内容,更早的截断,防止历史无限膨胀。
_FULL_TOOL_RESULT_RUNS = 2

async def get_image_base64(file_path: str) -> str:
    try:
        # Handle relative paths (assuming they are relative to static/media or uploads)
        # But user requirement says "store file path".
        # If it starts with /, it's absolute or relative to root?
        # Usually uploads return absolute path or relative to project root.
        # Let's assume the path stored is usable.
        # If it's a URL path like /static/media/..., we need to map it to file system.
        
        real_path = file_path
        if file_path.startswith("/static/media/"):
            real_path = f"static/media/{file_path.replace('/static/media/', '')}"
        elif file_path.startswith("/uploads/"): # If we have an uploads dir served
             real_path = f"uploads/{file_path.replace('/uploads/', '')}"
        
        # If it's just a filename or relative path, we might need to adjust.
        # For now, assume the upload endpoint returns a path we can use or map.
        
        async with aiofiles.open(real_path, "rb") as f:
            data = await f.read()
            # Detect mime type? For now assume png or jpeg based on extension or just send bytes
            # The provider expects base64 string.
            # We should probably prepend the data URI scheme if the provider expects it?
            # Gemini provider code:
            # if "," in img_b64: header, data = img_b64.split(",", 1) ...
            # else: data = img_b64; mime_type = "image/png"
            
            b64_data = base64.b64encode(data).decode("utf-8")
            
            # Try to guess mime type from extension
            mime_type = "image/png"
            if real_path.lower().endswith(".jpg") or real_path.lower().endswith(".jpeg"):
                mime_type = "image/jpeg"
            elif real_path.lower().endswith(".webp"):
                mime_type = "image/webp"
                
            return f"data:{mime_type};base64,{b64_data}"
    except Exception as e:
        logger.error(f"Error reading image file {file_path}: {e}")
        return None

async def generate_session_title(session_id: str, messages: List[Dict], provider, config):
    # 背景任务:请求级 db 在 yield 依赖 teardown 后就关了,这里必须自建会话。
    try:
        # Create a prompt for title generation
        prompt = "Generate a short, concise title (max 5-7 words) for this conversation based on the first user message and assistant response. Do not use quotes. Language: Chinese."
        
        # Construct a simple message history for the title generator
        title_messages = [
            {"role": "user", "content": f"{messages[0]['content']}\n\n---\n\n{messages[1]['content']}\n\n---\n\n{prompt}"}
        ]
        
        # We use a non-streaming call if available, or just consume the stream
        title = ""
        async for chunk in provider.chat_stream(title_messages, config):
            if isinstance(chunk, str):
                title += chunk
        
        title = title.strip()
        if not title:
            return
        async with SessionLocal() as db:
            session = await chat_session.get(db, id=session_id)
            if session:
                await chat_session.update(db, db_obj=session, obj_in={"title": title})
    except Exception as e:
        logger.error(f"Error generating title for session {session_id}: {e}")

async def build_provider_messages(
    db: AsyncSession,
    *,
    session_id: str,
    subject: Optional[Subject],
    scene: Optional[str] = None,
    scene_context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """把落库的会话重建成 provider 的 messages。

    工具调用与工具结果都在库里(role=assistant 带 tool_calls / role=tool),成对还原,
    模型才看得见自己上一轮做过什么。此前它们只活在内存、重建时被整条跳过,
    导致多轮对话里 AI 反复重复同一次工具调用。

    上下文压缩:只有最近 _FULL_TOOL_RESULT_RUNS 个 run 保留完整工具结果,
    更早的截断成一行占位,避免历史无限膨胀。
    """
    # 工具调用策略与已注册工具强耦合，硬编码随代码演进，不做成用户可编辑配置。
    system_prompt = render_subject_prompt(CHAT_SYSTEM_PROMPT, subject)
    scene_block = render_scene_context(scene, scene_context)
    if scene_block:
        system_prompt = f"{system_prompt}\n\n{scene_block}"
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    history = await chat_message.get_by_session(db, session_id=session_id)
    recent_runs = _recent_run_ids(history)

    for msg in history:
        if msg.role == "tool":
            content = msg.content or ""
            if msg.run_id not in recent_runs:
                content = "[工具已执行，结果已省略]"
            messages.append({
                "role": "tool",
                "tool_call_id": msg.tool_call_id,
                "content": content,
            })
            continue

        message_dict: Dict[str, Any] = {"role": msg.role, "content": msg.content}
        if msg.tool_calls:
            message_dict["tool_calls"] = msg.tool_calls
        if msg.images:
            images_b64 = []
            for img_path in msg.images:
                b64 = await get_image_base64(img_path)
                if b64:
                    images_b64.append(b64)
            if images_b64:
                message_dict["images"] = images_b64
        messages.append(message_dict)

    return messages


def _recent_run_ids(history: List[ChatMessageModel]) -> set:
    seen = []
    for msg in reversed(history):
        if msg.run_id and msg.run_id not in seen:
            seen.append(msg.run_id)
        if len(seen) >= _FULL_TOOL_RESULT_RUNS:
            break
    return set(seen)


async def chat_generator(session_id: str, new_user_message: ChatMessageCreate, model_id: int, db: AsyncSession, current_user: User, background_tasks: BackgroundTasks, subject_id: Optional[int] = None, scene: Optional[str] = None, scene_context: Optional[Dict[str, Any]] = None):
    user_msg_data = new_user_message.model_dump()
    user_msg_data["session_id"] = session_id
    user_msg = await chat_message.create(db, obj_in=user_msg_data)
    yield sse_pack("message_meta", {"role": "user", "id": user_msg.id})

    history_len = len(await chat_message.get_by_session(db, session_id=session_id))

    subject = None
    if subject_id:
        subj_res = await db.execute(select(Subject).where(Subject.id == subject_id))
        subject = subj_res.scalar_one_or_none()

    ai_messages = await build_provider_messages(
        db,
        session_id=session_id,
        subject=subject,
        scene=scene,
        scene_context=scene_context,
    )

    result = await db.execute(
        select(AIModel)
        .options(selectinload(AIModel.provider))
        .where(AIModel.id == model_id)
        .with_for_update()
    )
    ai_model = result.scalars().first()
    if not ai_model:
        yield "Error: Model not found"
        return

    provider_config = {
        "MODEL_NAME": ai_model.name,
        "API_KEY": ai_model.provider.api_key,
    }
    if ai_model.provider.base_url:
        provider_config["BASE_URL"] = ai_model.provider.base_url

    service_provider = get_ai_provider(ai_model.provider.interface_type)
    runner = AgentRunner(service_provider, provider_config)
    ctx = ExecutionContext(
        db=db, actor=current_user, surface=Surface.CHAT, subject_id=subject_id
    )

    final_text = ""
    async for event in runner.run(
        ctx,
        ai_messages,
        session_id=session_id,
        model_id=model_id,
        model_name=ai_model.name,
        provider_name=ai_model.provider.name,
        scene=AgentScene.parse(scene),
    ):
        # 工具往返落库,供下一轮重建上下文;它们不进用户可见的对话记录(见 API 层过滤)。
        if isinstance(event, AssistantTurn):
            await chat_message.create(db, obj_in={
                "session_id": session_id,
                "role": "assistant",
                "content": event.text or None,
                "tool_calls": event.tool_calls,
                "run_id": event.run_id,
            })
        elif isinstance(event, ToolCallFinished):
            await chat_message.create(db, obj_in={
                "session_id": session_id,
                "role": "tool",
                "content": event.content,
                "tool_call_id": event.tool_call_id,
                "run_id": event.run_id,
            })
        elif isinstance(event, RunFinished):
            final_text = event.text if event.stop_reason == "completed" else ""

        for frame in to_sse(event):
            yield frame

    if final_text:
        assistant_msg = await chat_message.create(db, obj_in={
            "session_id": session_id,
            "role": "assistant",
            "content": final_text,
        })
        yield sse_pack("message_meta", {"role": "assistant", "id": assistant_msg.id})

    yield sse_pack("done", {})

    # 首轮问答后自动起标题(此时库里只有刚存的那条用户消息)。
    if history_len == 1:
        msgs_for_title = [
            {"role": "user", "content": user_msg.content},
            {"role": "assistant", "content": final_text},
        ]
        background_tasks.add_task(generate_session_title, session_id, msgs_for_title, service_provider, provider_config)


@router.post("/sessions", response_model=ChatSessionSummary)
async def create_session(
    session_in: ChatSessionCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Create a new chat session."""
    session = await chat_session.create(db, obj_in={**session_in.model_dump(), "user_id": current_user.id})
    return session

@router.get("/sessions", response_model=List[ChatSessionSummary])
async def list_sessions(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """List chat sessions."""
    return await chat_session.get_multi_by_user(db, user_id=current_user.id, skip=skip, limit=limit)

@router.get("/sessions/{session_id}", response_model=ChatSession)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get a chat session."""
    session = await chat_session.get(db, id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    session.messages = await chat_message.get_transcript(db, session_id=session_id)
    return session

@router.patch("/sessions/{session_id}", response_model=ChatSessionSummary)
async def update_session(
    session_id: str,
    session_in: ChatSessionUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Update a chat session."""
    session = await chat_session.get(db, id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return await chat_session.update(db, db_obj=session, obj_in=session_in)

@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Delete a chat session."""
    session = await chat_session.get(db, id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    await chat_session.remove(db, id=session_id)
    return {"ok": True}

@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessage])
async def get_session_messages(
    session_id: str,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Get messages for a chat session with pagination."""
    session = await chat_session.get(db, id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    messages = await chat_message.get_by_session_desc(db, session_id=session_id, skip=skip, limit=limit)
    return list(reversed(messages))

@router.post("/sessions/{session_id}/messages")
async def create_message(
    session_id: str,
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Add a message to a session and get AI response."""
    session = await chat_session.get(db, id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    return StreamingResponse(
        chat_generator(session_id, request.message, request.model_id, db, current_user, background_tasks, request.subject_id, request.scene, request.scene_context),
        media_type="text/event-stream"
    )


@router.post("/runs/{run_id}/client-tool-result", status_code=204)
async def submit_client_tool_result(
    run_id: str,
    payload: ClientToolResult,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """前端执行完 client 工具后回传结果,唤醒仍挂在 SSE 上的那个 run。

    票据本身不可猜且一次性,但仍要校验 run 归属 —— 注册表是任何已登录请求都能打到的内存。
    """
    run = await db.get(AgentRun, run_id)
    if run is None or run.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")

    if not client_channel.resolve(payload.ticket, run_id, payload.model_dump()):
        # 票据不存在/已消费/不属于该 run:多半是超时之后才回来的。
        raise HTTPException(status_code=409, detail="Ticket is no longer pending")
    return None

@router.patch("/messages/{message_id}", response_model=ChatMessage)
async def update_message(
    message_id: int,
    message_in: ChatMessageUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Update a chat message.
    """
    message = await chat_message.get(db, id=message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Verify user owns the session of this message
    session = await chat_session.get(db, id=message.session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    message = await chat_message.update(db, db_obj=message, obj_in=message_in)
    return message

@router.delete("/messages/{message_id}", response_model=ChatMessage)
async def delete_message(
    message_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Delete a chat message.
    """
    message = await chat_message.get(db, id=message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
        
    # Verify user owns the session of this message
    session = await chat_session.get(db, id=message.session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    message = await chat_message.remove(db, id=message_id)
    return message
