import shutil
import uuid
import logging
import asyncio
from pathlib import Path
from typing import BinaryIO
import pypandoc
from app.core.config import settings
from app.crud.crud_system_setting import system_setting
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.ai_provider import get_ai_provider
from app.models.ai_config import AIModel, AIProvider
from app.models.tag import Tag
from app.models.tag_category import TagCategory
from app.core.vector_store import VectorStore
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

class DocProcessor:
    def __init__(self):
        self.client = None

    async def _get_active_provider_config(self, db: AsyncSession, is_vision: bool = False) -> tuple[AIProvider, AIModel]:
        # Get active model ID
        setting_key = "AI_VISION_MODEL_ID" if is_vision else "AI_TEXT_MODEL_ID"
        setting = await system_setting.get_by_key(db, setting_key)
        
        if not setting or not setting.value:
            return None, None

        try:
            model_id = int(setting.value)
        except ValueError:
            return None, None
        
        stmt = select(AIModel).options(selectinload(AIModel.provider)).where(AIModel.id == model_id)
        result = await db.execute(stmt)
        model = result.scalar_one_or_none()
        
        if not model:
            return None, None
            
        return model.provider, model

    async def _call_ai_for_questions(self, content: str, db: AsyncSession, image_data: bytes = None, filename: str = None, mode: str = "extract") -> list[dict]:
        """
        Call AI Provider to extract questions from content or image.
        
        Args:
            content: Text content (markdown/text)
            db: Database session
            image_data: Optional image bytes for vision API
            filename: Optional filename to provide context
            mode: Processing mode ("extract" or "solve")
        
        Returns:
            List of extracted questions
        """
        extracted_questions = []
        
        # Try to get new dynamic config first
        provider_db, model_db = await self._get_active_provider_config(db, is_vision=bool(image_data))
        
        config = {}
        provider_name = "gemini" # Default fallback
        
        if provider_db and model_db:
            provider_name = provider_db.interface_type
            config = {
                "API_KEY": provider_db.api_key,
                "BASE_URL": provider_db.base_url,
                "MODEL_NAME": model_db.name,
            }
            # Fetch prompts
            prompt_key = "AI_SOLVE_PROMPT" if mode == "solve" else "AI_EXTRACT_PROMPT"
            prompts = await system_setting.get_map_by_keys(db, [prompt_key])
            
            if prompt_key in prompts:
                config["AI_EXTRACT_PROMPT"] = prompts[prompt_key]

            # Fetch Tags and Categories for Prompt Context
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
                        tag_context_lines.append(f"    - **{cat.name} ({cat.slug})**: {', '.join(cat_tags)}")
                
                tag_context = "\n".join(tag_context_lines)
                
                # Replace placeholder or append
                if "AI_EXTRACT_PROMPT" in config:
                    if "{tags}" in config["AI_EXTRACT_PROMPT"]:
                        config["AI_EXTRACT_PROMPT"] = config["AI_EXTRACT_PROMPT"].replace("{tags}", tag_context)
                    else:
                        config["AI_EXTRACT_PROMPT"] += tag_context
                    
            except Exception as e:
                logger.warning(f"Failed to fetch tag context for AI prompt: {e}")

        else:
            logger.warning("No active AI provider configuration found.")
            return extracted_questions
        
        provider = get_ai_provider(provider_name)
        
        # Prepend filename to content if available
        final_content = content
        if filename:
            final_content = f"文件名: {filename}\n\n{content}"
        
        try:
            questions = await provider.extract_questions(final_content, image_data, config)
            
            # Enhance with Knowledge Points from Vector Store
            batch_items = []
            batch_context = {}

            for i, q in enumerate(questions):
                try:
                    # Determine query text: use AI-extracted knowledge points if available, otherwise content
                    query_text = q.content
                    if q.knowledge_points and len(q.knowledge_points) > 0:
                        query_text = " ".join(q.knowledge_points)
                        logger.debug(f"Using AI-extracted knowledge points for vector search: {query_text}")

                    # Use asyncio.to_thread to avoid blocking the event loop
                    results = await asyncio.to_thread(
                        VectorStore.search_similar,
                        query=query_text,
                        limit=5  # Increase limit to get more candidates for reranking
                    )
                    
                    if results and results.get('documents') and results['documents'][0]:
                        candidates = results['documents'][0]
                        candidate_ids = results['ids'][0] if 'ids' in results and results['ids'] else []
                        distances = results['distances'][0] if 'distances' in results and results['distances'] else []
                        
                        # Map text to ID for later retrieval
                        text_to_id = {text.strip(): id_ for text, id_ in zip(candidates, candidate_ids)}

                        # 1. Distance Filter (Simple heuristic)
                        # If we have distances, filter out those that are too far compared to the best match
                        filtered_candidates = []
                        if distances:
                            best_dist = distances[0]
                            # Threshold: e.g., within 50% worse than best, or absolute threshold if known
                            # Since we don't know the scale, we'll be lenient or just take top N if close
                            for j, dist in enumerate(distances):
                                # Heuristic: if distance is > 1.5x the best distance, maybe it's not good
                                # But for very small best_dist (e.g. 0.1), 0.2 is fine.
                                # Let's just pass top 5 to AI for now, or filter if dist > 1.0 (assuming cosine/l2 normalized)
                                filtered_candidates.append(candidates[j])
                        else:
                            filtered_candidates = candidates

                        # Add to batch
                        batch_items.append({
                            "id": str(i),
                            "content": q.content,
                            "candidates": filtered_candidates
                        })
                        
                        batch_context[str(i)] = {
                            "question": q,
                            "text_to_id": text_to_id,
                            "filtered_candidates": filtered_candidates
                        }

                except Exception as vs_e:
                    logger.error(f"Vector store search failed: {vs_e}")

            # 2. Batch AI Verification / Reranking
            verified_results = {}
            if batch_items:
                verified_results = await provider.batch_rerank_knowledge_points(
                    items=batch_items,
                    config=config
                )

            # 3. Update questions
            for item in batch_items:
                q_id = item['id']
                if q_id not in batch_context:
                    continue
                    
                ctx = batch_context[q_id]
                q = ctx["question"]
                text_to_id = ctx["text_to_id"]
                filtered_candidates = ctx["filtered_candidates"]
                
                verified_points = verified_results.get(q_id)
                
                if verified_points:
                    q.knowledge_points = verified_points
                    # Map back to IDs
                    q.knowledge_point_ids = []
                    for text in verified_points:
                        normalized_text = text.strip()
                        found_id = None
                        if normalized_text in text_to_id:
                            found_id = text_to_id[normalized_text]
                        else:
                            # Try case-insensitive match
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
                    # Fallback to top 1 if AI returns nothing (or failed), or keep original logic
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

            # Convert Pydantic models to dicts for compatibility
            extracted_questions = [q.model_dump() for q in questions]
            
            # Post-process to assign temp_ids and handle recursion
            def process_recursive(items, parent_temp_id=None):
                processed = []
                for item in items:
                    # Assign temp_id if not present
                    if 'id' not in item or not item['id']:
                        item['id'] = str(uuid.uuid4())
                    
                    # Assign parent_id if provided
                    if parent_temp_id:
                        item['parent_id'] = parent_temp_id
                        
                    # Process children recursively
                    if 'children' in item and item['children']:
                        item['children'] = process_recursive(item['children'], item['id'])
                    
                    processed.append(item)
                return processed

            extracted_questions = process_recursive(extracted_questions)

        except Exception as e:
            logger.error(f"AI Provider error: {e}")
            raise e
        
        return extracted_questions

    async def process_markdown(self, content: str, db: AsyncSession, filename: str = None, task_id: str = None, mode: str = "extract") -> dict:
        """
        Process markdown content directly and extract questions.
        
        Args:
            content: Markdown text content
            db: Database session
            filename: Optional filename
            task_id: Optional task ID (if not provided, a new one will be generated)
            mode: Processing mode ("extract" or "solve")
        
        Returns:
            Dict with task_id, content, and extracted questions
        """
        if not task_id:
            task_id = str(uuid.uuid4())
        
        # Save markdown to uploads directory for reference
        task_dir = settings.UPLOAD_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = task_dir / "content.md"
        await asyncio.to_thread(output_path.write_text, content, encoding='utf-8')
        
        # Extract questions using AI
        extracted_questions = await self._call_ai_for_questions(content, db, filename=filename, mode=mode)
        
        return {
            "task_id": task_id,
            "content": content,
            "questions": extracted_questions
        }

    async def process_image(self, image_file: BinaryIO, db: AsyncSession, task_id: str = None, mode: str = "extract") -> dict:
        """
        Process image file and extract questions using Gemini Vision.
        
        Args:
            image_file: Image file object
            db: Database session
            task_id: Optional task ID
            mode: Processing mode ("extract" or "solve")
        
        Returns:
            Dict with task_id, image_url, and extracted questions
        """
        if not task_id:
            task_id = str(uuid.uuid4())
        
        # Save image to media directory
        media_dir = settings.MEDIA_DIR / task_id
        media_dir.mkdir(parents=True, exist_ok=True)
        
        image_filename = "uploaded_image.png"
        image_path = media_dir / image_filename
        
        # Read and save image
        image_data = await asyncio.to_thread(image_file.read)
        
        def save_image():
            with open(image_path, "wb") as f:
                f.write(image_data)
        
        await asyncio.to_thread(save_image)
        
        # Extract questions using AI Vision
        extracted_questions = await self._call_ai_for_questions("", db, image_data=image_data, mode=mode)
        
        return {
            "task_id": task_id,
            "image_url": f"/static/media/{task_id}/{image_filename}",
            "questions": extracted_questions
        }

    async def process_docx(self, file_path: Path, db: AsyncSession = None, task_id: str = None, mode: str = "extract") -> dict:
        """
        Convert docx to markdown, extract media, and parse questions using Gemini.
        """
        if not task_id:
            task_id = str(uuid.uuid4())
        
        # Define directories
        task_dir = settings.UPLOAD_DIR / task_id
        media_dir = settings.MEDIA_DIR / task_id
        
        task_dir.mkdir(parents=True, exist_ok=True)
        media_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = task_dir / "content.md"
        
        # Convert using pypandoc
        try:
            await asyncio.to_thread(
                pypandoc.convert_file,
                str(file_path),
                'markdown',
                outputfile=str(output_path),
                extra_args=[
                    f'--extract-media={str(task_dir)}',
                    '--mathml'
                ]
            )
        except Exception as e:
            raise RuntimeError(f"Pandoc conversion failed: {str(e)}")

        # Read the converted markdown
        if not output_path.exists():
             raise RuntimeError("Conversion output file not found")
             
        content = await asyncio.to_thread(output_path.read_text, encoding='utf-8')
        
        # Handle media files
        def handle_media_and_update_content(content_str):
            generated_media_folder = task_dir / "media"
            if generated_media_folder.exists():
                for item in generated_media_folder.iterdir():
                    if item.is_file():
                        shutil.move(str(item), str(media_dir / item.name))
                
                shutil.rmtree(str(generated_media_folder))
                
                # Replace paths in content
                pandoc_media_prefix = f"{str(task_dir)}/media/"
                public_media_url = f"/static/media/{task_id}/"
                content_str = content_str.replace(pandoc_media_prefix, public_media_url)
                
                output_path.write_text(content_str, encoding='utf-8')
            return content_str

        content = await asyncio.to_thread(handle_media_and_update_content, content)

        # Extract questions using AI
        extracted_questions = await self._call_ai_for_questions(content, db, filename=file_path.name, mode=mode)
        
        return {
            "task_id": task_id,
            "content": content,
            "questions": extracted_questions
        }

doc_processor = DocProcessor()
