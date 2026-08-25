from typing import List, Optional, Union, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from app.crud.base import CRUDBase
from app.models.question import Question, QuestionStatus, QuestionType
from app.models.tag import Tag
from app.schemas.question import QuestionCreate, QuestionUpdate
from app.crud.crud_knowledge_point import knowledge_point as knowledge_point_crud
from app.services.activity_logger import log_activity
from app.services.question_content import (
    normalize_options,
    parse_json_field,
    serialize_write_fields,
    to_db_json,
    validate_question_domain,
)

from app.models.knowledge_point import KnowledgePoint
from app.models.import_task import ImportTask
from app.models.activity_log import ActivityLog

class CRUDQuestion(CRUDBase[Question, QuestionCreate, QuestionUpdate]):
    async def get(self, db: AsyncSession, id: Any) -> Optional[Question]:
        # Define recursive loading paths
        l1 = selectinload(self.model.children)
        l2 = l1.selectinload(Question.children)
        l3 = l2.selectinload(Question.children)

        stmt = select(self.model).options(
            # Root relationships
            selectinload(self.model.subject),
            selectinload(self.model.tags),
            selectinload(self.model.knowledge_points),
            selectinload(self.model.creator),
            selectinload(self.model.updater),
            selectinload(self.model.review_logs),
            selectinload(self.model.parent), # Load parent
            selectinload(self.model.import_task),
            
            # Level 1 Children relationships
            l1.selectinload(Question.subject),
            l1.selectinload(Question.tags),
            l1.selectinload(Question.knowledge_points),
            l1.selectinload(Question.creator),
            l1.selectinload(Question.updater),
            l1.selectinload(Question.review_logs),

            # Level 2 Children relationships
            l2.selectinload(Question.subject),
            l2.selectinload(Question.tags),
            l2.selectinload(Question.knowledge_points),
            l2.selectinload(Question.creator),
            l2.selectinload(Question.updater),
            l2.selectinload(Question.review_logs),

            # Level 3 Structure (deepest level loaded)
            l3
        ).filter(self.model.id == id, self.model.deleted_at.is_(None))
        result = await db.execute(stmt)
        return result.scalars().first()

    async def _get_filter_query(
        self,
        db: AsyncSession,
        *,
        subject_id: Optional[int] = None,
        knowledge_point_ids: Optional[List[int]] = None,
        tag_ids: Optional[List[int]] = None,
        q_type: Optional[str] = None,
        difficulty: Optional[int] = None,
        status: Optional[str] = None,
        import_task_id: Optional[int] = None,
        import_task_name: Optional[str] = None,
        review_count: Optional[int] = None,
        creator_id: Optional[int] = None,
        reviewer_id: Optional[int] = None,
        keyword: Optional[str] = None,
        id: Optional[int] = None,
        ids: Optional[List[int]] = None,
        source: Optional[str] = None,
        root_only: bool = False
    ):
        # Define recursive loading paths
        l1 = selectinload(self.model.children)
        l2 = l1.selectinload(Question.children)
        l3 = l2.selectinload(Question.children)

        query = select(self.model).options(
            selectinload(self.model.tags), 
            selectinload(self.model.knowledge_points),
            selectinload(self.model.creator),
            selectinload(self.model.updater),
            selectinload(self.model.review_logs),
            selectinload(self.model.subject),
            selectinload(self.model.parent),
            selectinload(self.model.import_task),
            
            # Level 1 Children relationships
            l1.selectinload(Question.tags),
            l1.selectinload(Question.knowledge_points),
            l1.selectinload(Question.review_logs),
            l1.selectinload(Question.subject),
            l1.selectinload(Question.creator),
            l1.selectinload(Question.updater),

            # Level 2 Children relationships
            l2.selectinload(Question.tags),
            l2.selectinload(Question.knowledge_points),
            l2.selectinload(Question.review_logs),
            l2.selectinload(Question.subject),
            l2.selectinload(Question.creator),
            l2.selectinload(Question.updater),

            # Level 3 Structure (deepest level loaded)
            l3
        ).filter(self.model.deleted_at.is_(None))
        
        if id:
            query = query.filter(self.model.id == id)
        
        if ids:
            query = query.filter(self.model.id.in_(ids))

        if keyword:
            query = query.filter(self.model.content.ilike(f"%{keyword}%"))
        
        if subject_id:
            query = query.filter(self.model.subject_id == subject_id)
            
        if knowledge_point_ids:
            # Any selected knowledge point (plus its descendants) is a match.
            kp_ids: set = set()
            for kp_id in knowledge_point_ids:
                kp_ids.update(await knowledge_point_crud.get_descendant_ids(db, kp_id))
            if kp_ids:
                query = query.filter(self.model.knowledge_points.any(KnowledgePoint.id.in_(kp_ids)))
            else:
                query = query.filter(self.model.id == -1)
            
        if tag_ids:
            query = query.filter(self.model.tags.any(Tag.id.in_(tag_ids)))
            
        if q_type:
            query = query.filter(self.model.q_type == q_type)
            
        if difficulty:
            query = query.filter(self.model.difficulty == difficulty)
            
        if status:
            query = query.filter(self.model.status == status)
            
        if import_task_id:
            print(f"Filtering by import_task_id: {import_task_id}")
            query = query.filter(self.model.import_task_id == import_task_id)
            
        if import_task_name:
            query = query.join(self.model.import_task).filter(ImportTask.description.ilike(f"%{import_task_name}%"))
            
        if source:
            query = query.filter(self.model.source.ilike(f"%{source}%"))
            
        if root_only:
            query = query.filter(self.model.parent_id.is_(None))

        if review_count is not None:
            query = query.filter(self.model.review_count == review_count)
            
        if creator_id:
            query = query.filter(self.model.created_by == creator_id)
            
        if reviewer_id:
            # This is complex because reviewer is in ActivityLog
            # We need to join ActivityLog
            subquery = select(ActivityLog.resource_id).filter(
                ActivityLog.user_id == reviewer_id,
                ActivityLog.resource_type == 'question',
                ActivityLog.action == 'review'
            ).distinct()
            query = query.filter(self.model.id.in_(subquery))
            
        return query

    async def get_multi_with_filters(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        subject_id: Optional[int] = None,
        knowledge_point_ids: Optional[List[int]] = None,
        tag_ids: Optional[List[int]] = None,
        q_type: Optional[str] = None,
        difficulty: Optional[int] = None,
        status: Optional[str] = None,
        import_task_id: Optional[int] = None,
        import_task_name: Optional[str] = None,
        review_count: Optional[int] = None,
        creator_id: Optional[int] = None,
        reviewer_id: Optional[int] = None,
        keyword: Optional[str] = None,
        id: Optional[int] = None,
        ids: Optional[List[int]] = None,
        source: Optional[str] = None,
        root_only: bool = False
    ) -> List[Question]:
        query = await self._get_filter_query(
            db,
            subject_id=subject_id,
            knowledge_point_ids=knowledge_point_ids,
            tag_ids=tag_ids,
            q_type=q_type,
            difficulty=difficulty,
            status=status,
            import_task_id=import_task_id,
            import_task_name=import_task_name,
            review_count=review_count,
            creator_id=creator_id,
            reviewer_id=reviewer_id,
            keyword=keyword,
            id=id,
            ids=ids,
            source=source,
            root_only=root_only
        )
        query = query.offset(skip).limit(limit).order_by(self.model.created_at.desc())
        result = await db.execute(query)
        return result.scalars().all()

    async def get_multi_by_ids(self, db: AsyncSession, *, ids: List[int]) -> List[Question]:
        """
        Get multiple questions by IDs.
        """
        if not ids:
            return []
        return await self.get_multi_with_filters(db, ids=ids, limit=len(ids))

    async def count_with_filters(
        self,
        db: AsyncSession,
        *,
        subject_id: Optional[int] = None,
        knowledge_point_ids: Optional[List[int]] = None,
        tag_ids: Optional[List[int]] = None,
        q_type: Optional[str] = None,
        difficulty: Optional[int] = None,
        status: Optional[str] = None,
        import_task_id: Optional[int] = None,
        import_task_name: Optional[str] = None,
        review_count: Optional[int] = None,
        creator_id: Optional[int] = None,
        reviewer_id: Optional[int] = None,
        keyword: Optional[str] = None,
        id: Optional[int] = None,
        ids: Optional[List[int]] = None,
        source: Optional[str] = None,
        root_only: bool = False
    ) -> int:
        query = await self._get_filter_query(
            db,
            subject_id=subject_id,
            knowledge_point_ids=knowledge_point_ids,
            tag_ids=tag_ids,
            q_type=q_type,
            difficulty=difficulty,
            status=status,
            import_task_id=import_task_id,
            import_task_name=import_task_name,
            review_count=review_count,
            creator_id=creator_id,
            reviewer_id=reviewer_id,
            keyword=keyword,
            id=id,
            ids=ids,
            source=source,
            root_only=root_only
        )
        # Use subquery for count to handle joins correctly
        subquery = query.subquery()
        count_query = select(func.count()).select_from(subquery)
        result = await db.execute(count_query)
        return result.scalar_one()

    async def create_with_tags(self, db: AsyncSession, *, obj_in: QuestionCreate, user_id: Optional[int] = None, import_task_id: Optional[int] = None) -> Question:
        obj_in_data = obj_in.model_dump()
        tag_ids = obj_in_data.pop("tag_ids", [])
        knowledge_point_ids = obj_in_data.pop("knowledge_point_ids", [])
        obj_in_data.pop("ai_suggested_tags", None)
        
        # Remove fields that are not in the Question model but are in QuestionCreate for processing
        obj_in_data.pop("children", None)
        obj_in_data.pop("temp_id", None)
        
        # Ensure parent_id is valid (it might be a UUID string from import, which we should ignore/handle elsewhere)
        # If it's a string, we assume it's a temp ID reference and set it to None for now.
        # The caller is responsible for setting the correct parent_id after the parent is created.
        if isinstance(obj_in_data.get("parent_id"), str):
            obj_in_data["parent_id"] = None

        # Centralized v2 JSON boundary: rich-text / answer -> JSON strings; options stays native JSON.
        obj_in_data = serialize_write_fields(obj_in_data)

        db_obj = Question(**obj_in_data)
        if user_id:
            db_obj.created_by = user_id
            db_obj.updated_by = user_id
        
        if import_task_id:
            db_obj.import_task_id = import_task_id
        
        if tag_ids:
            result = await db.execute(select(Tag).filter(Tag.id.in_(tag_ids)))
            tags = result.scalars().all()
            db_obj.tags = list(tags)
            
        if knowledge_point_ids:
            result = await db.execute(select(KnowledgePoint).filter(KnowledgePoint.id.in_(knowledge_point_ids)))
            kps = result.scalars().all()
            db_obj.knowledge_points = list(kps)
            
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        
        # Re-fetch with relationships loaded to avoid MissingGreenlet error
        stmt = select(Question).options(
            selectinload(Question.subject),
            selectinload(Question.tags),
            selectinload(Question.knowledge_points),
            selectinload(Question.creator),
            selectinload(Question.updater),
            selectinload(Question.review_logs),
            selectinload(Question.children),
            selectinload(Question.parent),
            selectinload(Question.import_task)
        ).where(Question.id == db_obj.id)
        
        result = await db.execute(stmt)
        db_obj = result.scalar_one()
        
        # Log activity
        if user_id:
            await log_activity(db, user_id, action="create", resource_type="question", resource_id=db_obj.id, details={"message": f"Created question {db_obj.id}"})
            
        return db_obj

    async def update_with_tags(
        self,
        db: AsyncSession,
        *,
        db_obj: Question,
        obj_in: Union[QuestionUpdate, Dict[str, Any]],
        user_id: Optional[int] = None
    ) -> Question:
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)
            
        tag_ids = update_data.pop("tag_ids", None)
        knowledge_point_ids = update_data.pop("knowledge_point_ids", None)

        # Merge v2 content state (current DB row + overlay), then run full domain validation
        # before persisting. This is the authoritative net for partial updates.
        merged_q_type = update_data.get("q_type", db_obj.q_type)
        if isinstance(merged_q_type, str):
            merged_q_type = QuestionType(merged_q_type)

        merged_content = update_data["content"] if "content" in update_data else parse_json_field(db_obj.content)
        merged_answer = update_data["answer"] if "answer" in update_data else parse_json_field(db_obj.answer)
        merged_options = update_data["options"] if "options" in update_data else db_obj.options
        merged_options = normalize_options(merged_q_type, merged_options)
        merged_status = update_data.get("status", db_obj.status)
        if isinstance(merged_status, str):
            merged_status = QuestionStatus(merged_status)

        if merged_answer and merged_answer.get("kind") == "legacy_unresolved":
            raise ValueError("legacy_unresolved 只读,不允许写入")

        validate_question_domain(
            q_type=merged_q_type,
            status=merged_status,
            content=merged_content,
            options=merged_options,
            answer=merged_answer,
            partial=False,
        )

        # content_revision 生命周期:仅当规范化后的题目内容(content/options/answer/
        # thinking/analysis/summary/q_type)真正变化时 +1;metadata(tag/kp/status/
        # difficulty/source/subject_id/parent_id)变化不递增。
        before_thinking = parse_json_field(db_obj.thinking)
        before_analysis = parse_json_field(db_obj.analysis)
        before_summary = parse_json_field(db_obj.summary)
        after_thinking = (
            parse_json_field(update_data["thinking"])
            if "thinking" in update_data
            else before_thinking
        )
        after_analysis = (
            parse_json_field(update_data["analysis"])
            if "analysis" in update_data
            else before_analysis
        )
        after_summary = (
            parse_json_field(update_data["summary"])
            if "summary" in update_data
            else before_summary
        )
        content_changed = (
            parse_json_field(db_obj.content) != merged_content
            or parse_json_field(db_obj.answer) != merged_answer
            or (db_obj.options or None) != (merged_options or None)
            or db_obj.q_type != merged_q_type
            or before_thinking != after_thinking
            or before_analysis != after_analysis
            or before_summary != after_summary
        )

        db_obj.content = to_db_json(merged_content)
        db_obj.answer = to_db_json(merged_answer)
        db_obj.options = merged_options
        db_obj.q_type = merged_q_type
        for field in ("thinking", "analysis", "summary"):
            if field in update_data:
                setattr(db_obj, field, to_db_json(update_data[field]))
        for field in ("status", "difficulty", "source", "subject_id", "parent_id"):
            if field in update_data:
                setattr(db_obj, field, update_data[field])

        if content_changed:
            db_obj.content_revision = (db_obj.content_revision or 1) + 1

        if user_id:
            db_obj.updated_by = user_id
            
        if tag_ids is not None:
            result = await db.execute(select(Tag).filter(Tag.id.in_(tag_ids)))
            tags = result.scalars().all()
            db_obj.tags = list(tags)
            
        if knowledge_point_ids is not None:
            result = await db.execute(select(KnowledgePoint).filter(KnowledgePoint.id.in_(knowledge_point_ids)))
            kps = result.scalars().all()
            db_obj.knowledge_points = list(kps)
            
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        
        # Re-fetch with relationships loaded
        stmt = select(Question).options(
            selectinload(Question.subject),
            selectinload(Question.tags),
            selectinload(Question.knowledge_points),
            selectinload(Question.creator),
            selectinload(Question.updater),
            selectinload(Question.review_logs),
            selectinload(Question.children),
            selectinload(Question.parent)
        ).where(Question.id == db_obj.id)
        
        result = await db.execute(stmt)
        db_obj = result.scalar_one()
        
        # Log activity
        if user_id:
            await log_activity(db, user_id, action="update", resource_type="question", resource_id=db_obj.id, details={"message": f"Updated question {db_obj.id}"})
            
        return db_obj

    async def remove(self, db: AsyncSession, *, id: int, user_id: Optional[int] = None) -> Optional[Question]:
        obj = await self.get(db, id=id)
        if obj:
            now = datetime.utcnow()
            obj.deleted_at = now
            if user_id:
                obj.updated_by = user_id
            
            # Soft delete children recursively
            def soft_delete_children(q: Question):
                for child in q.children:
                    child.deleted_at = now
                    if user_id:
                        child.updated_by = user_id
                    soft_delete_children(child)
            
            soft_delete_children(obj)

            db.add(obj)
            await db.commit()
            await db.refresh(obj)
            
            # Log activity
            if user_id:
                await log_activity(db, user_id, action="delete", resource_type="question", resource_id=obj.id, details={"message": f"Soft deleted question {obj.id}"})
                
        return obj

    async def restore(self, db: AsyncSession, *, id: int, user_id: Optional[int] = None) -> Optional[Question]:
        stmt = select(self.model).filter(self.model.id == id)
        result = await db.execute(stmt)
        obj = result.scalars().first()
        if obj:
            obj.deleted_at = None
            if user_id:
                obj.updated_by = user_id
            db.add(obj)
            await db.commit()
            await db.refresh(obj)
            
            # Log activity
            if user_id:
                await log_activity(db, user_id, action="restore", resource_type="question", resource_id=obj.id, details={"message": f"Restored question {obj.id}"})
                
        return obj

question = CRUDQuestion(Question)
