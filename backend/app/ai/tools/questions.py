"""题目相关的 AI 工具。

写工具(propose_*)不自己落库 —— 它们只做「模型的松散输出 → 严格入参」的翻译,
然后交给 `question.create` 能力。业务逻辑与鉴权因此与 HTTP 端点完全同一份。
"""
from typing import List, Optional, Dict, Any
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app import capabilities
from app.ai.contracts import AgentScene, ToolResult, ToolSpec, proposal_directive
from app.ai.tools.registry import register
from app.capabilities.context import ExecutionContext
from app.crud.crud_question import question as crud_question
from app.schemas.question import QuestionCreate
from app.models.question import QuestionStatus, QuestionType
from app.services.kp_retriever import KnowledgePointRetriever
from app.services.ai_provider import get_ai_provider
from app.crud.crud_system_setting import system_setting
from app.models.ai_config import AIModel
from app.models.tag import Tag
from app.services.question_legacy_adapter import (
    LegacyQuestionError,
    adapt_legacy_question,
)
from app.services.question_content import parse_json_field
from app.services.question_render import (
    answer_spec_to_plain_text,
    rich_doc_to_plain_text,
)
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

# 工具 schema 与 DB 枚举共用一份真源 —— 二者漂移时 q_type 筛选会在参数绑定期就报错。
_QUESTION_TYPE_VALUES = frozenset(t.value for t in QuestionType)

# Define Question Schema Properties for reuse
QUESTION_SCHEMA_PROPERTIES = {
    "content": {
        "type": "string",
        "description": "题目内容/题干。支持 Markdown。"
    },
    "q_type": {
        "type": "string",
        "enum": sorted(_QUESTION_TYPE_VALUES),
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
        "description": "关联的知识点列表（字符串）。提交前请先调用 search_knowledge_points 搜索题目涉及的知识点，使用搜索结果中的准确名称；仅在确实搜不到时留空，由系统按内容自动匹配（准确率低于人工核实）。"
    },
    "tags": {
        "type": "array",
        "items": {
            "type": "string"
        },
        "description": "关联的标签列表（字符串）。提交前请先调用 get_available_tags 获取系统中实际存在的标签名称，不要凭空编造。"
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
    "description": "子题目列表。只要根题目带有 children，就必须通过 propose_questions_batch 提交（即使只有一个根题目），不要用 propose_question_draft。"
}

# Tool Definitions
PROPOSE_BATCH_PARAMS = {
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

PROPOSE_DRAFT_PARAMS = {
    "type": "object",
    "properties": level1_props,
    "required": ["content", "q_type"]
}

SEARCH_QUESTIONS_PARAMS = {
    "type": "object",
    "properties": {
        "keyword": {
            "type": "string",
            "description": "在题目内容中搜索的关键词。可与知识点/标签筛选组合使用。"
        },
        "knowledge_point_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": (
                "按知识点筛选,取并集(命中任一即可),且自动包含每个知识点的所有下级知识点。"
                "请先用 search_knowledge_points 拿到 id。"
            )
        },
        "tag_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "按标签筛选,取并集(命中任一即可)。请先用 get_available_tags 拿到 id。"
        },
        "difficulty": {
            "type": "integer",
            "description": "难度等级 (1-5),精确匹配。",
            "minimum": 1,
            "maximum": 5
        },
        "q_type": QUESTION_SCHEMA_PROPERTIES["q_type"],
        "status": {
            "type": "string",
            "enum": ["draft", "pending", "published", "archived"],
            "description": "题目状态。不传则不限状态。"
        },
        "limit": {
            "type": "integer",
            "description": "返回结果的数量 (默认 5,最多 50)。",
            "default": 5,
            "minimum": 1,
            "maximum": 50
        }
    },
    "required": []
}

_SEARCH_LIMIT_MAX = 50


async def search_questions(ctx: ExecutionContext, args: Dict[str, Any]) -> ToolResult:
    keyword = args.get("keyword")
    knowledge_point_ids = args.get("knowledge_point_ids")
    tag_ids = args.get("tag_ids")
    difficulty = args.get("difficulty")
    q_type = args.get("q_type")
    status = args.get("status")

    if not (keyword or knowledge_point_ids or tag_ids):
        return ToolResult.text(
            "请至少提供 keyword、knowledge_point_ids、tag_ids 三者之一,否则会返回整个题库。"
        )

    if q_type is not None and q_type not in _QUESTION_TYPE_VALUES:
        return ToolResult.text(
            f"未知的 q_type: {q_type}。可选值为 {', '.join(sorted(_QUESTION_TYPE_VALUES))}。"
        )

    try:
        limit = int(args.get("limit") or 5)
    except (TypeError, ValueError):
        limit = 5
    limit = max(1, min(limit, _SEARCH_LIMIT_MAX))

    # 只在当前学科内检索,否则模型会拿到其它学科的题去组稿。
    subject_id = ctx.subject_id or ctx.actor.last_active_subject_id

    # 套用与题库列表相同的可见性过滤,避免 AI 泄漏他人私有题/越权学科题。
    questions = await crud_question.get_multi_with_filters(
        ctx.db,
        keyword=keyword,
        knowledge_point_ids=knowledge_point_ids,
        tag_ids=tag_ids,
        difficulty=difficulty,
        q_type=q_type,
        status=status,
        subject_id=subject_id,
        limit=limit,
        viewer=ctx.actor,
    )

    if not questions:
        return ToolResult.text("No questions found matching the criteria.")

    results = []
    for q in questions:
        content_text = rich_doc_to_plain_text(parse_json_field(q.content))[:200]
        answer_text = answer_spec_to_plain_text(q.answer, q.options)
        kp_names = "、".join(kp.name for kp in (q.knowledge_points or [])) or "无"
        tag_names = "、".join(t.name for t in (q.tags or [])) or "无"
        results.append(
            f"ID: {q.id}\nType: {q.q_type}\nDifficulty: {q.difficulty}\n"
            f"KnowledgePoints: {kp_names}\nTags: {tag_names}\n"
            f"Content: {content_text}...\nAnswer: {answer_text}\n"
        )

    return ToolResult(
        content="\n---\n".join(results),
        data={"ids": [q.id for q in questions]},
    )


async def resolve_tags(db: AsyncSession, tag_names: List[str]) -> List[int]:
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

async def _enrich_question_with_knowledge_points(db: AsyncSession, question_data: Dict[str, Any], subject_id: Optional[int] = None) -> Dict[str, Any]:
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
                results = await KnowledgePointRetriever.retrieve(
                    query=kp_text,
                    subject_id=subject_id,
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
        
        results = await KnowledgePointRetriever.retrieve(
            query=query_text,
            subject_id=subject_id,
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

async def _build_question_create(
    ctx: ExecutionContext,
    data: Dict[str, Any],
    *,
    subject_id: Optional[int],
    parent_id: Optional[int] = None,
) -> QuestionCreate:
    """模型给的松散字段 → 严格 v2 入参。无法解析答案时抛 LegacyQuestionError。"""
    data = await _enrich_question_with_knowledge_points(ctx.db, data, subject_id=subject_id)
    tag_ids = await resolve_tags(ctx.db, data.get("tags")) if data.get("tags") else []

    v2_fields = adapt_legacy_question(
        q_type=data.get("q_type"),
        status=QuestionStatus.DRAFT,
        content=data.get("content"),
        options=data.get("options"),
        answer=data.get("answer"),
        thinking=data.get("thinking"),
        analysis=data.get("analysis"),
        summary=data.get("summary"),
    )
    return QuestionCreate(
        content=v2_fields["content"],
        q_type=data.get("q_type"),
        options=v2_fields["options"],
        answer=v2_fields["answer"],
        thinking=v2_fields["thinking"],
        analysis=v2_fields["analysis"],
        summary=v2_fields["summary"],
        difficulty=data.get("difficulty", 1),
        status=v2_fields["status"],
        subject_id=subject_id,
        knowledge_point_ids=data.get("knowledge_point_ids", []),
        tag_ids=tag_ids,
        parent_id=parent_id,
    )


async def propose_question_draft(ctx: ExecutionContext, args: Dict[str, Any]) -> ToolResult:
    subject_id = ctx.subject_id or ctx.actor.last_active_subject_id
    try:
        obj_in = await _build_question_create(ctx, args, subject_id=subject_id)
    except LegacyQuestionError as adapt_err:
        return ToolResult.text(f"Failed to create proposal: {adapt_err}")

    question = await capabilities.run("question.create", ctx, obj_in)

    content_preview = str(args.get("content", ""))[:100].replace("\n", " ") + "..."
    return ToolResult(
        content=f"Proposal created: {content_preview}\nPlease ask user to confirm.",
        data={"question_ids": [question.id]},
        ui=[proposal_directive("single", [question.id])],
    )


async def propose_questions_batch(ctx: ExecutionContext, args: Dict[str, Any]) -> ToolResult:
    questions_data = args.get("questions", [])
    if not questions_data:
        return ToolResult.text("No questions provided.")

    subject_id = ctx.subject_id or ctx.actor.last_active_subject_id
    created_ids: List[int] = []
    summaries: List[str] = []
    failed_count = 0

    async def create_recursive(q_data: Dict[str, Any], parent_id: Optional[int] = None) -> List[int]:
        obj_in = await _build_question_create(
            ctx, q_data, subject_id=subject_id, parent_id=parent_id
        )
        question = await capabilities.run("question.create", ctx, obj_in)
        all_ids = [question.id]
        for child_data in q_data.get("children", []) or []:
            all_ids.extend(await create_recursive(child_data, parent_id=question.id))
        return all_ids

    for q_data in questions_data:
        try:
            q_ids = await create_recursive(q_data)
            created_ids.extend(q_ids)
            content_preview = str(q_data.get("content", ""))[:50].replace("\n", " ") + "..."
            summaries.append(f"{len(created_ids)}. [{q_data.get('q_type')}] {content_preview}")
        except Exception as e:
            logger.error(f"Error creating question in batch: {e}")
            failed_count += 1

    if not created_ids:
        return ToolResult.text(f"Failed to create any proposals. Errors: {failed_count}")

    summary_text = "\n".join(summaries)
    return ToolResult(
        content=(
            f"Batch proposal created for {len(created_ids)} questions:\n{summary_text}\n\n"
            "Please ask user to confirm."
        ),
        data={"question_ids": created_ids},
        ui=[proposal_directive("batch", created_ids)],
    )


# 两个 propose_* 的嵌套 schema 占全量工具载荷约 88%，只在真正会建题的页面暴露。
_AUTHORING_SCENES = frozenset({AgentScene.QUESTION_LIBRARY, AgentScene.IMPORT_REVIEW})

register(ToolSpec(
    name="propose_question_draft",
    description=(
        "向用户提议创建一个新的题目草稿。此工具不会直接发布题目，而是生成一个待确认的提案。仅当用户明确请求“保存”或“导入”时使用。"
        "若题目带有子题目(children)，请改用 propose_questions_batch。"
        "录入时必须原样保留用户提供的 answer/thinking/analysis/summary，不得修改或摘要。"
    ),
    parameters=PROPOSE_DRAFT_PARAMS,
    handler=propose_question_draft,
    capability="question.create",
    mutating=True,
    scenes=_AUTHORING_SCENES,
))

register(ToolSpec(
    name="propose_questions_batch",
    description=(
        "向用户提议批量导入题目。此工具不会直接发布题目，而是生成一组待确认的提案。"
        "仅当用户明确请求“保存”或“导入”时使用。"
        "当有多个题目需要处理，或题目带有子题目(children，即使只有一个根题目)时，必须使用此工具而不是逐个调用 propose_question_draft。"
        "录入时必须原样保留用户提供的 answer/thinking/analysis/summary，不得修改或摘要。"
    ),
    parameters=PROPOSE_BATCH_PARAMS,
    handler=propose_questions_batch,
    capability="question.create",
    mutating=True,
    scenes=_AUTHORING_SCENES,
))

register(ToolSpec(
    name="search_questions",
    description="根据关键词、知识点、标签等筛选条件在题库中搜索题目。只返回当前学科、且当前用户有权查看的题目。",
    parameters=SEARCH_QUESTIONS_PARAMS,
    handler=search_questions,
))
