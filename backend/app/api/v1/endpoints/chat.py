from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.api import deps
from app.schemas.chat import ChatRequest, ChatSession, ChatSessionCreate, ChatSessionUpdate, ChatMessageCreate, ChatMessage, ChatSessionSummary, ChatMessageUpdate
from app.models.chat import ChatSession as ChatSessionModel, ChatMessage as ChatMessageModel
from app.models.ai_config import AIModel
from app.crud.crud_chat import chat_session, chat_message
from app.crud.crud_system_setting import system_setting
from app.services.ai_provider import get_ai_provider, ToolCall
from app.services.tools import TOOLS_SCHEMA, TOOL_MAP
from fastapi.responses import StreamingResponse
import json
import logging
import base64
import aiofiles
from typing import List, Dict, Any

from app.models.user import User

import re

logger = logging.getLogger(__name__)
router = APIRouter()

def sse_pack(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

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

async def generate_session_title(session_id: str, messages: List[Dict], db: AsyncSession, provider, config):
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
        if title:
            session = await chat_session.get(db, id=session_id)
            if session:
                await chat_session.update(db, db_obj=session, obj_in={"title": title})
    except Exception as e:
        logger.error(f"Error generating title for session {session_id}: {e}")

async def chat_generator(session_id: str, new_user_message: ChatMessageCreate, model_id: int, db: AsyncSession, current_user: User, background_tasks: BackgroundTasks):
    # 1. Save user message
    user_msg_data = new_user_message.model_dump()
    user_msg_data["session_id"] = session_id
    user_msg = await chat_message.create(db, obj_in=user_msg_data)
    
    # Send user message ID to frontend
    yield sse_pack("message_meta", {"role": "user", "id": user_msg.id})
    
    # 2. Fetch history
    # We need to fetch all messages for the session to send context
    # But we should probably limit context window? For now, send all.
    history = await chat_message.get_by_session(db, session_id=session_id)
    
    # 3. Prepare messages for AI
    ai_messages = []
    
    # Inject System Prompt to control tool usage
    sys_prompt_setting = await system_setting.get_by_key(db, "CHAT_SYSTEM_PROMPT")
    default_sys_prompt = """You are a helpful assistant for a Question Bank system.
Tools Usage Policy:
- You have access to tools like `search_questions`, `create_question_draft`, and `create_questions_batch`.
- ONLY use these tools when the user EXPLICITLY requests an action (e.g., "search for...", "save to database", "import these").
- Do NOT use tools if the user is just asking for information, explanations, or generating content for review without asking to save it.
- If the user asks to "generate a question", just generate the text. Only call `create_question_draft` if they add "and save it" or "add to bank".
"""
    system_prompt = sys_prompt_setting.value if sys_prompt_setting and sys_prompt_setting.value else default_sys_prompt
    ai_messages.append({"role": "system", "content": system_prompt})

    for msg in history:
        # Skip messages with tool_calls because we don't save the corresponding tool responses
        # This prevents the "tool_calls must be followed by tool messages" error
        if msg.tool_calls:
            continue
            
        message_dict = {
            "role": msg.role,
            "content": msg.content,
        }
        if msg.images:
            # Convert file paths to base64
            images_b64 = []
            for img_path in msg.images:
                b64 = await get_image_base64(img_path)
                if b64:
                    images_b64.append(b64)
            if images_b64:
                message_dict["images"] = images_b64
        
        if msg.tool_calls:
             message_dict["tool_calls"] = msg.tool_calls
             
        # If this message has tool calls, we MUST skip it if we don't have the corresponding tool responses
        # Because we decided NOT to save tool responses to DB.
        # So if we load a message with tool_calls from DB, the next messages in DB will NOT be the tool responses.
        # This breaks the conversation history for the AI provider (it expects tool_calls -> tool response).
        
        # Solution: If we encounter a message with tool_calls in history, we should probably filter it out 
        # OR we should have saved the tool responses.
        # Since the user requested NOT to save tool responses, we must also NOT save the tool call request itself to DB
        # to maintain consistency.
        
        # Let's check where we save the assistant message with tool calls.
        # It's in the loop below: `await chat_message.create(db, obj_in=assistant_msg_data)`
        
        # We should modify that part to NOT save if it has tool calls.
        
        ai_messages.append(message_dict)

    # 4. Get Provider
    result = await db.execute(
        select(AIModel)
        .options(selectinload(AIModel.provider))
        .where(AIModel.id == model_id)
    )
    ai_model = result.scalars().first()
    if not ai_model:
        yield "Error: Model not found"
        return

    provider_config = {}
    provider_config["MODEL_NAME"] = ai_model.name
    provider_config["API_KEY"] = ai_model.provider.api_key
    if ai_model.provider.base_url:
        provider_config["BASE_URL"] = ai_model.provider.base_url
    
    service_provider = get_ai_provider(ai_model.provider.interface_type)

    # 5. Stream response
    content_buffer = ""
    tool_calls = []
    
    # Limit max turns to prevent infinite loops
    for _ in range(5):
        tool_calls = []
        current_content_buffer = ""
        
        async for chunk in service_provider.chat_stream(ai_messages, provider_config, tools=TOOLS_SCHEMA):
            if isinstance(chunk, str):
                content_buffer += chunk
                current_content_buffer += chunk
                yield sse_pack("message", chunk)
            elif isinstance(chunk, ToolCall):
                tool_calls.append(chunk)
        
        if not tool_calls:
            break
            
        # Handle tool calls (same as before)
        # ... (omitted for brevity, but should be included if we support tools in sessions)
        # For now, let's assume we just want basic chat, but if tools are used, we need to save them too.
        
        # Save assistant message with tool calls
        assistant_msg_data = {
            "session_id": session_id,
            "role": "assistant",
            "content": current_content_buffer if current_content_buffer else None,
            "tool_calls": [tc.model_dump() for tc in tool_calls]
        }
        # DO NOT Save assistant message with tool calls to DB as per user request
        # await chat_message.create(db, obj_in=assistant_msg_data)
        
        # Add to ai_messages for next turn
        ai_messages.append({
            "role": "assistant",
            "content": current_content_buffer,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments
                    },
                    "metadata": tc.metadata
                } for tc in tool_calls
            ]
        })

        # Execute tools
        for tc in tool_calls:
            # Notify frontend about action start
            try:
                args_obj = json.loads(tc.arguments)
            except:
                args_obj = tc.arguments
            
            yield sse_pack("action", {"tool": tc.name, "input": args_obj})

            tool_func = TOOL_MAP.get(tc.name)
            if tool_func:
                try:
                    args = json.loads(tc.arguments)
                    args["_user_id"] = current_user.id
                    result = await tool_func(db, args)
                except Exception as e:
                    logger.error(f"Tool execution error: {e}")
                    result = f"Error executing tool: {str(e)}"
            else:
                result = f"Error: Tool {tc.name} not found"
            
            # Check for proposal tags in result
            str_result = str(result)
            
            # Parse [CONFIRM_IMPORT:id]
            single_match = re.search(r"\[CONFIRM_IMPORT:(\d+)\]", str_result)
            if single_match:
                yield sse_pack("proposal", {"type": "single", "ids": [int(single_match.group(1))]})
                
            # Parse [CONFIRM_IMPORT_BATCH:ids]
            batch_match = re.search(r"\[CONFIRM_IMPORT_BATCH:([\d,]+)\]", str_result)
            if batch_match:
                ids = [int(x) for x in batch_match.group(1).split(",")]
                yield sse_pack("proposal", {"type": "batch", "ids": ids})

            # Notify frontend about action result
            # We might want to truncate result if it's too long for the UI log
            preview_result = str_result[:200] + "..." if len(str_result) > 200 else str_result
            yield sse_pack("action_result", {"tool": tc.name, "output": preview_result})

            # DO NOT Save tool result to DB as per user request
            # We only keep it in memory for the current turn context
            
            ai_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result)
            })

    # 6. Save final assistant message (if no tools or after tools)
    # If we had tool calls, we already saved the intermediate messages.
    # If we didn't have tool calls, we need to save the content.
    # Or if we finished the loop.
    
    # Actually, the loop logic above saves assistant message ONLY if there are tool calls.
    # We need to save the final response.
    
    if content_buffer and not tool_calls:
         assistant_msg = await chat_message.create(db, obj_in={
            "session_id": session_id,
            "role": "assistant",
            "content": content_buffer
        })
         yield sse_pack("message_meta", {"role": "assistant", "id": assistant_msg.id})
    
    yield sse_pack("done", {})

    # 7. Generate Title if needed
    # Check if this is the first exchange (2 messages: 1 user, 1 assistant)
    # We can check the length of history before we added the new user message.
    # If history was empty, then now we have 1 user + 1 assistant (after this finishes).
    if len(history) == 1: # history includes the user message we just added? No, get_by_session was called after adding user msg.
        # So history has 1 message (the user message).
        # After this response, we have 2.
        # So we can trigger title generation.
        # We need to pass the messages to the background task.
        # The messages are: history[0] (user) and the content_buffer (assistant).
        
        # We need to reconstruct the messages for the title generator
        msgs_for_title = [
            {"role": "user", "content": history[0].content},
            {"role": "assistant", "content": content_buffer}
        ]
        background_tasks.add_task(generate_session_title, session_id, msgs_for_title, db, service_provider, provider_config)


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
    session = await chat_session.get_with_messages(db, id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
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
        chat_generator(session_id, request.message, request.model_id, db, current_user, background_tasks),
        media_type="text/event-stream"
    )

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
