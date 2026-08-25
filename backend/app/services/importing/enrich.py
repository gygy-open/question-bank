"""富化阶段:用向量库 + AI rerank 给抽取出的题目回填知识点。

对每题:向量召回候选 → 批量 AI rerank 校验 → 把校验通过的知识点文本映射回 id;
AI 无返回时回退到最近候选。整段可失败不致命(只 log,不影响抽取主流程)。
"""
from __future__ import annotations

import logging
from typing import Any, List

from app.services.ai_provider import AIProvider
from app.services.kp_retriever import KnowledgePointRetriever

logger = logging.getLogger(__name__)


class KnowledgePointEnricher:
    async def enrich(
        self,
        questions: List[Any],
        *,
        subject_id: int | None,
        provider: AIProvider,
        config: dict,
    ) -> None:
        """就地回填 questions[].knowledge_points / knowledge_point_ids。"""
        batch_items = []
        batch_context = {}

        for i, q in enumerate(questions):
            try:
                # Determine query text: use AI-extracted knowledge points if available, otherwise content
                query_text = q.content
                if q.knowledge_points and len(q.knowledge_points) > 0:
                    query_text = " ".join(q.knowledge_points)
                    logger.debug(f"Using AI-extracted knowledge points for vector search: {query_text}")

                # Subject-scoped; returns None when no embedding model is configured.
                results = await KnowledgePointRetriever.retrieve(
                    query=query_text,
                    subject_id=subject_id,
                    limit=5,  # Increase limit to get more candidates for reranking
                )

                if results and results.get("documents") and results["documents"][0]:
                    candidates = results["documents"][0]
                    candidate_ids = results["ids"][0] if "ids" in results and results["ids"] else []
                    distances = results["distances"][0] if "distances" in results and results["distances"] else []

                    # Map text to ID for later retrieval
                    text_to_id = {text.strip(): id_ for text, id_ in zip(candidates, candidate_ids)}

                    # Distance filter (currently lenient: pass all candidates through to AI rerank).
                    filtered_candidates = []
                    if distances:
                        for j, _dist in enumerate(distances):
                            filtered_candidates.append(candidates[j])
                    else:
                        filtered_candidates = candidates

                    batch_items.append({
                        "id": str(i),
                        "content": q.content,
                        "candidates": filtered_candidates,
                    })

                    batch_context[str(i)] = {
                        "question": q,
                        "text_to_id": text_to_id,
                        "filtered_candidates": filtered_candidates,
                    }

            except Exception as vs_e:
                logger.error(f"Vector store search failed: {vs_e}")

        # Batch AI verification / reranking
        verified_results = {}
        if batch_items:
            verified_results = await provider.batch_rerank_knowledge_points(
                items=batch_items,
                config=config,
            )

        # Update questions
        for item in batch_items:
            q_id = item["id"]
            if q_id not in batch_context:
                continue

            ctx = batch_context[q_id]
            q = ctx["question"]
            text_to_id = ctx["text_to_id"]
            filtered_candidates = ctx["filtered_candidates"]

            verified_points = verified_results.get(q_id)

            if verified_points:
                q.knowledge_points = verified_points
                q.knowledge_point_ids = []
                for text in verified_points:
                    normalized_text = text.strip()
                    found_id = None
                    if normalized_text in text_to_id:
                        found_id = text_to_id[normalized_text]
                    else:
                        for cand_text, cand_id in text_to_id.items():
                            if cand_text.lower() == normalized_text.lower():
                                found_id = cand_id
                                break

                    if found_id is not None:
                        try:
                            q.knowledge_point_ids.append(int(found_id))
                        except ValueError:
                            logger.warning(f"Could not convert knowledge point ID to int: {found_id}")
                    else:
                        logger.warning(f"AI returned knowledge point not found in candidates: {text}")

                logger.debug(f"AI verified knowledge points: {q.knowledge_points} (IDs: {q.knowledge_point_ids})")
            else:
                fallback_text = filtered_candidates[0] if filtered_candidates else None
                if fallback_text:
                    q.knowledge_points = [fallback_text]
                    normalized_fallback = fallback_text.strip()
                    if normalized_fallback in text_to_id:
                        try:
                            q.knowledge_point_ids = [int(text_to_id[normalized_fallback])]
                        except ValueError:
                            pass
                else:
                    q.knowledge_points = []
                    q.knowledge_point_ids = []

                logger.debug(f"Fallback to top candidate: {q.knowledge_points}")
