"""知识点与标签的只读 AI 工具。

不迁到 capability 层:纯读、无授权判定、无领域不变量,不满足纳入标准。
"""
from typing import Any, Dict
import logging

from sqlalchemy import select

from app.ai.contracts import ToolResult, ToolSpec
from app.ai.tools.registry import register
from app.capabilities.context import ExecutionContext
from app.models.tag import Tag
from app.models.tag_category import TagCategory
from app.services.kp_retriever import KnowledgePointRetriever

logger = logging.getLogger(__name__)

SEARCH_KNOWLEDGE_POINTS_PARAMS = {
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

GET_AVAILABLE_TAGS_PARAMS = {
    "type": "object",
    "properties": {},
    "required": []
}


async def search_knowledge_points(ctx: ExecutionContext, args: Dict[str, Any]) -> ToolResult:
    query = args.get("query")
    limit = args.get("limit", 5)

    if not query:
        return ToolResult.text("Please provide a query.")

    results = await KnowledgePointRetriever.retrieve(query=query, limit=limit)

    if not results or not results.get("documents") or not results["documents"][0]:
        return ToolResult.text("No knowledge points found.")

    candidates = results["documents"][0]
    distances = results["distances"][0] if results.get("distances") else []

    output = []
    for i, text in enumerate(candidates):
        dist = distances[i] if i < len(distances) else "N/A"
        output.append(f"{i+1}. {text} (Distance: {dist})")

    return ToolResult(content="\n".join(output))


async def get_available_tags(ctx: ExecutionContext, args: Dict[str, Any]) -> ToolResult:
    res_cat = await ctx.db.execute(
        select(TagCategory).where(TagCategory.is_active == True).order_by(TagCategory.sort_order)  # noqa: E712
    )
    categories = res_cat.scalars().all()

    res_tag = await ctx.db.execute(select(Tag))
    tags = res_tag.scalars().all()

    tags_by_cat: Dict[Any, list] = {}
    for tag in tags:
        tags_by_cat.setdefault(tag.category_id, []).append(tag.name)

    tag_context_lines = []
    for cat in categories:
        cat_tags = tags_by_cat.get(cat.id, [])
        if cat_tags:
            tag_context_lines.append(f"- **{cat.name}**: {', '.join(cat_tags)}")

    if not tag_context_lines:
        return ToolResult.text("No tags available.")

    return ToolResult(content="\n".join(tag_context_lines))


register(ToolSpec(
    name="search_knowledge_points",
    description="在向量知识库中搜索相关的知识点。当你需要为题目关联知识点，或者需要了解某个概念在知识库中的具体表述时，使用此工具。",
    parameters=SEARCH_KNOWLEDGE_POINTS_PARAMS,
    handler=search_knowledge_points,
))

register(ToolSpec(
    name="get_available_tags",
    description="获取系统中所有可用的标签列表（按分类分组）。当你需要为题目打标签时，请先调用此工具查看有哪些标签可用，然后选择合适的标签名称。",
    parameters=GET_AVAILABLE_TAGS_PARAMS,
    handler=get_available_tags,
))
