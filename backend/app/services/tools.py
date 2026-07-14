from typing import List, Optional, Dict, Any, Callable, Awaitable
import logging
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.crud_question import question as crud_question
from app.crud.crud_user import user as crud_user
from app.schemas.question import Question, QuestionCreate
from app.models.question import QuestionStatus
from app.core.vector_store import VectorStore
from app.services.ai_provider import get_ai_provider
from app.crud.crud_system_setting import system_setting
from app.models.ai_config import AIModel, AIProvider
from app.models.tag import Tag
from app.models.tag_category import TagCategory
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

# Define Question Schema Properties for reuse
QUESTION_SCHEMA_PROPERTIES = {
    "content": {
        "type": "string",
        "description": "题目内容/题干。支持 Markdown。"
    },
    "q_type": {
        "type": "string",
        "enum": ["single_choice", "multiple_choice", "true_false", "fill_in_the_blank", "free_response"],
        "description": "题目类型。'single_choice' 代表单选题，'multiple_choice' 代表多选题，'true_false' 代表判断题，'fill_in_the_blank' 代表填空题，'free_response' 代表解答题。"
    },
    "options": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "选项标签 (A, B, C, D)"},
                "content": {"type": "string", "description": "选项内容"}
            }
        },
        "description": "选择题的选项。如果是单选题或多选题，则此项必填。"
    },
    "answer": {
        "type": "string",
        "description": "正确答案"
    },
    "thinking": {
        "type": "string",
        "description": "解题思路或思维过程"
    },
    "analysis": {
        "type": "string",
        "description": "答案解析或分析"
    },
    "difficulty": {
        "type": "integer",
        "minimum": 1,
        "maximum": 5,
        "description": "难度等级 (1-5)"
    },
    "summary": {
        "type": "string",
        "description": "总结、名师总结或教研总结等"
    },
    "knowledge_points": {
        "type": "array",
        "items": {
            "type": "string"
        },
        "description": "关联的知识点列表（字符串）。如果AI通过 search_knowledge_points 找到了确切的知识点名称，请在此处提供。如果不提供，系统将尝试根据内容自动匹配。"
    },
    "tags": {
        "type": "array",
        "items": {
            "type": "string"
        },
        "description": "关联的标签列表（字符串）。请使用 get_available_tags 工具获取的准确标签名称。"
    }
}

# Level 3 (Leaf)
level3_props = QUESTION_SCHEMA_PROPERTIES.copy()

# Level 2
level2_props = QUESTION_SCHEMA_PROPERTIES.copy()
level2_props["children"] = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": level3_props,
        "description": "子题目 (Level 3)"
    },
    "description": "子题目列表"
}

# Level 1 (Root)
level1_props = QUESTION_SCHEMA_PROPERTIES.copy()
level1_props["children"] = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": level2_props,
        "description": "子题目 (Level 2)"
    },
    "description": "子题目列表"
}

# Tool Definitions
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_points",
            "description": "在向量知识库中搜索相关的知识点。当你需要为题目关联知识点，或者需要了解某个概念在知识库中的具体表述时，使用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词或查询语句。"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果的数量 (默认为 5)。",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_tags",
            "description": "获取系统中所有可用的标签列表（按分类分组）。当你需要为题目打标签时，请先调用此工具查看有哪些标签可用，然后选择合适的标签名称。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "propose_questions_batch",
            "description": "向用户提议批量导入题目。此工具不会直接发布题目，而是生成一组待确认的提案。当有多个题目需要处理时，必须优先使用此工具而不是逐个提议。",
            "parameters": {
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": level1_props,
                            "required": ["content", "q_type"]
                        }
                    }
                },
                "required": ["questions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "propose_question_draft",
            "description": "向用户提议创建一个新的题目草稿。此工具不会直接发布题目，而是生成一个待确认的提案。仅当用户明确请求“保存”或“导入”时使用。",
            "parameters": {
                "type": "object",
                "properties": level1_props,
                "required": ["content", "q_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_questions",
            "description": "根据关键词和其他筛选条件在题库中搜索题目。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "在题目内容中搜索的关键词。"
                    },
                    "difficulty": {
                        "type": "integer",
                        "description": "难度等级 (1-5)。",
                        "minimum": 1,
                        "maximum": 5
                    },
                    "q_type": {
                        "type": "string",
                        "description": "题目类型。",
                        "enum": ["选择题", "填空题", "解答题"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果的数量 (默认为 5)。",
                        "default": 5
                    }
                },
                "required": ["keyword"]
            }
        }
    }
]

async def search_questions(db: AsyncSession, args: Dict[str, Any]) -> str:
    """
    Implementation of search_questions tool.
    """
    keyword = args.get("keyword")
    difficulty = args.get("difficulty")
    q_type = args.get("q_type")
    limit = args.get("limit", 5)

    questions = await crud_question.get_multi_with_filters(
        db,
        keyword=keyword,
        difficulty=difficulty,
        q_type=q_type,
        limit=limit
    )

    if not questions:
        return "No questions found matching the criteria."

    results = []
    for q in questions:
        results.append(f"ID: {q.id}\nType: {q.q_type}\nDifficulty: {q.difficulty}\nContent: {q.content[:200]}...\nAnswer: {q.answer}\n")

    return "\n---\n".join(results)

async def _resolve_tags(db: AsyncSession, tag_names: List[str]) -> List[int]:
    """
    Helper to resolve tag names to IDs.
    """
    if not tag_names:
        return []
    
    # Case-insensitive match
    # Fetch all tags (assuming not too many) or filter by names
    # Since we need case-insensitive, and names might be slightly off, 
    # but the prompt asks for exact names from get_available_tags.
    
    # Let's try exact match first
    stmt = select(Tag).where(Tag.name.in_(tag_names))
    result = await db.execute(stmt)
    tags = result.scalars().all()
    
    tag_ids = [t.id for t in tags]
    
    # If we missed some, maybe try case-insensitive for the rest?
    # For now, just return what we found.
    return tag_ids

async def _enrich_question_with_knowledge_points(db: AsyncSession, question_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Helper to enrich question data with knowledge points from Vector Store using AI reranking.
    Similar logic to DocProcessor._call_ai_for_questions.
    """
    content = question_data.get("content", "")
    provided_kps = question_data.get("knowledge_points", [])
    
    # If AI provided explicit knowledge points, try to resolve them to IDs first
    if provided_kps:
        kp_ids = []
        for kp_text in provided_kps:
            # Try to find exact match in VectorStore or DB
            # For simplicity, we use VectorStore search with limit 1 and check similarity/exact match
            # Or better, just search by text in DB if we had a CRUD for KnowledgePoint by name
            # Here we use VectorStore search as a proxy
            try:
                results = await asyncio.to_thread(
                    VectorStore.search_similar,
                    query=kp_text,
                    limit=1
                )
                if results and results.get('documents') and results['documents'][0]:
                    candidate = results['documents'][0][0]
                    candidate_id = results['ids'][0][0]
                    # If the text is very similar or identical, use it
                    # Since we don't have strict equality check easily without DB, we trust VectorStore's top result
                    # if the query was specific enough.
                    # But to be safe, maybe we only accept if it's a close match?
                    # For now, let's assume AI is smart and provided a valid name found via search_knowledge_points
                    try:
                        kp_ids.append(int(candidate_id))
                    except ValueError:
                        pass
            except Exception as e:
                logger.warning(f"Failed to resolve provided KP '{kp_text}': {e}")
        
        if kp_ids:
            question_data["knowledge_point_ids"] = list(set(kp_ids))
            return question_data

    if not content:
        return question_data

    try:
        # 1. Vector Search
        # Use content or thinking/analysis if available for better context
        query_text = content
        if question_data.get("thinking"):
            query_text += " " + question_data["thinking"]
        
        results = await asyncio.to_thread(
            VectorStore.search_similar,
            query=query_text,
            limit=5
        )
        
        if not results or not results.get('documents') or not results['documents'][0]:
            return question_data

        candidates = results['documents'][0]
        candidate_ids = results['ids'][0] if 'ids' in results and results['ids'] else []
        
        # Map text to ID
        text_to_id = {text.strip(): id_ for text, id_ in zip(candidates, candidate_ids)}
        
        # 2. Get AI Provider for Reranking
        # We need to get the active text model config
        setting = await system_setting.get_by_key(db, "AI_TEXT_MODEL_ID")
        if not setting or not setting.value:
            # Fallback: just take top 1
            top_candidate = candidates[0]
            if top_candidate in text_to_id:
                question_data["knowledge_point_ids"] = [int(text_to_id[top_candidate])]
            return question_data

        try:
            model_id = int(setting.value)
            stmt = select(AIModel).options(selectinload(AIModel.provider)).where(AIModel.id == model_id)
            result = await db.execute(stmt)
            model = result.scalar_one_or_none()
            
            if not model:
                return question_data
                
            provider_name = model.provider.interface_type
            config = {
                "API_KEY": model.provider.api_key,
                "BASE_URL": model.provider.base_url,
                "MODEL_NAME": model.name,
            }
            
            provider = get_ai_provider(provider_name)
            
            # 3. Rerank
            batch_items = [{
                "id": "1",
                "content": content,
                "candidates": candidates
            }]
            
            verified_results = await provider.batch_rerank_knowledge_points(
                items=batch_items,
                config=config
            )
            
            verified_points = verified_results.get("1")
            
            if verified_points:
                kp_ids = []
                for text in verified_points:
                    normalized_text = text.strip()
                    found_id = None
                    if normalized_text in text_to_id:
                        found_id = text_to_id[normalized_text]
                    else:
                        # Case-insensitive match
                        for cand_text, cand_id in text_to_id.items():
                            if cand_text.lower() == normalized_text.lower():
                                found_id = cand_id
                                break
                    
                    if found_id is not None:
                        try:
                            kp_ids.append(int(found_id))
                        except ValueError:
                            pass
                
                if kp_ids:
                    question_data["knowledge_point_ids"] = kp_ids
            else:
                # Fallback to top 1
                top_candidate = candidates[0]
                if top_candidate in text_to_id:
                    try:
                        question_data["knowledge_point_ids"] = [int(text_to_id[top_candidate])]
                    except ValueError:
                        pass

        except Exception as e:
            logger.warning(f"AI reranking failed in tool: {e}")
            # Fallback to top 1
            if candidates:
                top_candidate = candidates[0]
                if top_candidate in text_to_id:
                    try:
                        question_data["knowledge_point_ids"] = [int(text_to_id[top_candidate])]
                    except ValueError:
                        pass

    except Exception as e:
        logger.error(f"Error enriching question with knowledge points: {e}")
    
    return question_data

async def propose_question_draft(db: AsyncSession, args: Dict[str, Any]) -> str:
    """
    Implementation of propose_question_draft tool.
    """
    # Extract user_id injected by the caller
    user_id = args.pop("_user_id", None)
    
    subject_id = None
    if user_id:
        user = await crud_user.get(db, id=user_id)
        if user:
            subject_id = user.subject_id

    try:
        # Enrich with knowledge points
        args = await _enrich_question_with_knowledge_points(db, args)
        
        # Resolve tags
        tag_ids = []
        if args.get("tags"):
            tag_ids = await _resolve_tags(db, args.get("tags"))

        obj_in = QuestionCreate(
            content=args.get("content"),
            q_type=args.get("q_type"),
            options=args.get("options"),
            answer=args.get("answer"),
            thinking=args.get("thinking"),
            analysis=args.get("analysis"),
            summary=args.get("summary"),
            difficulty=args.get("difficulty", 1),
            status=QuestionStatus.DRAFT, # Use DRAFT status for proposals
            subject_id=subject_id,
            knowledge_point_ids=args.get("knowledge_point_ids", []),
            tag_ids=tag_ids
        )
        
        question = await crud_question.create_with_tags(db, obj_in=obj_in, user_id=user_id)
        
        # Return a special tag for frontend to render a confirmation card
        content_preview = args.get("content", "")[:100].replace("\n", " ") + "..."
        return f"Proposal created: {content_preview}\nPlease ask user to confirm. [CONFIRM_IMPORT:{question.id}]"
    except Exception as e:
        logger.error(f"Error creating question proposal: {e}", exc_info=True)
        return f"Failed to create proposal: {str(e)}"

async def propose_questions_batch(db: AsyncSession, args: Dict[str, Any]) -> str:
    """
    Implementation of propose_questions_batch tool.
    """
    user_id = args.pop("_user_id", None)
    questions_data = args.get("questions", [])
    
    if not questions_data:
        return "No questions provided."

    subject_id = None
    if user_id:
        user = await crud_user.get(db, id=user_id)
        if user:
            subject_id = user.subject_id
            
    created_ids = []
    summaries = []
    failed_count = 0
    
    # Process questions in parallel for efficiency? 
    # For now, sequential to avoid overwhelming DB/AI provider if many
    # But we can optimize later.
    
    # Helper function for recursive creation
    async def create_recursive(q_data: Dict[str, Any], parent_id: Optional[int] = None) -> List[int]:
        # Enrich with knowledge points
        q_data = await _enrich_question_with_knowledge_points(db, q_data)
        
        # Resolve tags
        tag_ids = []
        if q_data.get("tags"):
            tag_ids = await _resolve_tags(db, q_data.get("tags"))

        # Extract children
        children_data = q_data.get("children", [])
        
        obj_in = QuestionCreate(
            content=q_data.get("content"),
            q_type=q_data.get("q_type"),
            options=q_data.get("options"),
            answer=q_data.get("answer"),
            thinking=q_data.get("thinking"),
            analysis=q_data.get("analysis"),
            summary=q_data.get("summary"),
            difficulty=q_data.get("difficulty", 1),
            status=QuestionStatus.DRAFT, # Use DRAFT status for proposals
            subject_id=subject_id,
            knowledge_point_ids=q_data.get("knowledge_point_ids", []),
            tag_ids=tag_ids,
            parent_id=parent_id
        )
        question = await crud_question.create_with_tags(db, obj_in=obj_in, user_id=user_id)
        
        all_ids = [question.id]
        
        # Process children recursively
        for child_data in children_data:
            child_ids = await create_recursive(child_data, parent_id=question.id)
            all_ids.extend(child_ids)
            
        return all_ids

    for q_data in questions_data:
        try:
            q_ids = await create_recursive(q_data)
            created_ids.extend(q_ids)
            
            content_preview = q_data.get("content", "")[:50].replace("\n", " ") + "..."
            summaries.append(f"{len(created_ids)}. [{q_data.get('q_type')}] {content_preview}")
        except Exception as e:
            logger.error(f"Error creating question in batch: {e}")
            failed_count += 1
            
    if created_ids:
        # Return a special tag for frontend to render a batch confirmation card
        ids_str = ",".join(map(str, created_ids))
        summary_text = "\n".join(summaries)
        return f"Batch proposal created for {len(created_ids)} questions:\n{summary_text}\n\nPlease ask user to confirm. [CONFIRM_IMPORT_BATCH:{ids_str}]"
        
    return f"Failed to create any proposals. Errors: {failed_count}"

async def search_knowledge_points(db: AsyncSession, args: Dict[str, Any]) -> str:
    """
    Implementation of search_knowledge_points tool.
    """
    query = args.get("query")
    limit = args.get("limit", 5)

    if not query:
        return "Please provide a query."

    try:
        results = await asyncio.to_thread(
            VectorStore.search_similar,
            query=query,
            limit=limit
        )
        
        if not results or not results.get('documents') or not results['documents'][0]:
            return "No knowledge points found."

        candidates = results['documents'][0]
        distances = results['distances'][0] if 'distances' in results and results['distances'] else []
        
        output = []
        for i, text in enumerate(candidates):
            dist = distances[i] if i < len(distances) else "N/A"
            output.append(f"{i+1}. {text} (Distance: {dist})")
            
        return "\n".join(output)
    except Exception as e:
        logger.error(f"Error searching knowledge points: {e}")
        return f"Error searching knowledge points: {str(e)}"

async def get_available_tags(db: AsyncSession, args: Dict[str, Any]) -> str:
    """
    Implementation of get_available_tags tool.
    """
    try:
        # Fetch categories
        stmt_cat = select(TagCategory).where(TagCategory.is_active == True).order_by(TagCategory.sort_order)
        res_cat = await db.execute(stmt_cat)
        categories = res_cat.scalars().all()
        
        # Fetch tags
        stmt_tag = select(Tag)
        res_tag = await db.execute(stmt_tag)
        tags = res_tag.scalars().all()
        
        # Group tags by category
        tags_by_cat = {}
        for tag in tags:
            if tag.category not in tags_by_cat:
                tags_by_cat[tag.category] = []
            tags_by_cat[tag.category].append(tag.name)
        
        # Build Markdown
        tag_context_lines = []
        for cat in categories:
            cat_tags = tags_by_cat.get(cat.slug, [])
            if cat_tags:
                tag_context_lines.append(f"- **{cat.name} ({cat.slug})**: {', '.join(cat_tags)}")
        
        if not tag_context_lines:
            return "No tags available."
            
        return "\n".join(tag_context_lines)
    except Exception as e:
        logger.error(f"Error fetching tags: {e}")
        return f"Error fetching tags: {str(e)}"

# Tool Registry
TOOL_MAP: Dict[str, Callable[[AsyncSession, Dict[str, Any]], Awaitable[str]]] = {
    "search_questions": search_questions,
    "search_knowledge_points": search_knowledge_points,
    "get_available_tags": get_available_tags,
    "propose_question_draft": propose_question_draft,
    "propose_questions_batch": propose_questions_batch
}
