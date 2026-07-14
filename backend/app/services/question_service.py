from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app import crud, models, schemas
from app.models.question import QuestionType, QuestionStatus
from app.models.tag import Tag

class QuestionService:
    async def process_ai_tags(
        self, 
        db: AsyncSession, 
        ai_suggested_tags: Dict[str, List[str]], 
        user_id: Optional[int]
    ) -> List[int]:
        """
        Process AI suggested tags: find existing or create new tags.
        Returns a list of tag IDs.
        """
        if not ai_suggested_tags:
            return []

        tag_ids = []
        
        # Pre-fetch all tag categories to validate slugs if needed, 
        # but for now we just trust the keys in ai_suggested_tags as categories
        
        for cat_slug, tags_list in ai_suggested_tags.items():
            if not tags_list:
                continue
                
            # Ensure tags_list is a list
            if not isinstance(tags_list, list):
                tags_list = [tags_list]

            for tag_name in tags_list:
                if not tag_name: 
                    continue
                
                tag_name = str(tag_name).strip()
                
                # Find tag (do not create if missing)
                stmt = select(models.Tag).where(models.Tag.name == tag_name)
                result = await db.execute(stmt)
                tag = result.scalar_one_or_none()
                
                if tag:
                    tag_ids.append(tag.id)
                
        return tag_ids

    async def create_question(
        self,
        db: AsyncSession,
        question_in: schemas.QuestionCreate,
        user_id: Optional[int],
        import_task_id: Optional[int] = None
    ) -> models.Question:
        """
        Create a question with AI suggested tags processing.
        """
        # 1. Process AI Suggested Tags
        if question_in.ai_suggested_tags:
            new_tag_ids = await self.process_ai_tags(db, question_in.ai_suggested_tags, user_id)
            
            if question_in.tag_ids is None:
                question_in.tag_ids = []
            
            # Add new tags, avoiding duplicates
            existing_ids = set(question_in.tag_ids)
            for tid in new_tag_ids:
                if tid not in existing_ids:
                    question_in.tag_ids.append(tid)
                    existing_ids.add(tid)

        # 2. Create Question using CRUD
        question = await crud.question.create_with_tags(
            db=db, 
            obj_in=question_in, 
            user_id=user_id,
            import_task_id=import_task_id
        )
        
        return question

question_service = QuestionService()
