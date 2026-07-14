from typing import List, Optional, Union, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.crud.base import CRUDBase
from app.models.knowledge_point import KnowledgePoint
from app.schemas.knowledge_point import KnowledgePointCreate, KnowledgePointUpdate
from app.services.activity_logger import log_activity
from app.core.vector_store import VectorStore

class CRUDKnowledgePoint(CRUDBase[KnowledgePoint, KnowledgePointCreate, KnowledgePointUpdate]):
    async def _build_path_text(self, db: AsyncSession, kp: KnowledgePoint) -> str:
        """
        Build the full path text for a knowledge point (e.g., "Math > Algebra > Functions").
        """
        path_parts = [kp.name]
        
        # 1. Fetch Subject Name explicitly
        subject_name = ""
        # Check if subject is already loaded to avoid query
        if "subject" in kp.__dict__:
             subject_name = kp.subject.name
        else:
            from app.models.subject import Subject
            # Use scalar query instead of get to be safe in all contexts
            result = await db.execute(select(Subject).where(Subject.id == kp.subject_id))
            subject = result.scalar_one_or_none()
            if subject:
                subject_name = subject.name
        
        # 2. Traverse Parents explicitly
        parent_id = kp.parent_id
        while parent_id:
            # Fetch parent
            result = await db.execute(select(KnowledgePoint).where(KnowledgePoint.id == parent_id))
            parent = result.scalar_one_or_none()
            
            if not parent:
                break
            
            path_parts.insert(0, parent.name)
            parent_id = parent.parent_id
            
        if subject_name:
            path_parts.insert(0, subject_name)
            
        return " > ".join(path_parts)

    async def _sync_to_vector_store(self, db: AsyncSession, kp: KnowledgePoint):
        """
        Sync a knowledge point to the vector store.
        """
        try:
            text = await self._build_path_text(db, kp)
            metadata = {
                "id": kp.id,
                "subject_id": kp.subject_id,
                "name": kp.name,
                "slug": kp.slug
            }
            VectorStore.upsert_knowledge_point(kp.id, text, metadata)
        except Exception as e:
            # Log error but don't fail the transaction
            print(f"Failed to sync knowledge point {kp.id} to vector store: {e}")

    async def create(self, db: AsyncSession, *, obj_in: KnowledgePointCreate, user_id: Optional[int] = None) -> KnowledgePoint:
        db_obj = KnowledgePoint(**obj_in.model_dump())
        if user_id:
            db_obj.created_by = user_id
            db_obj.updated_by = user_id
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        await log_activity(db, user_id, "create", "knowledge_point", db_obj.id, details=obj_in.model_dump())
        await db.commit()
        
        # Sync to vector store
        await self._sync_to_vector_store(db, db_obj)
        
        return db_obj

    async def update(
        self, db: AsyncSession, *, db_obj: KnowledgePoint, obj_in: Union[KnowledgePointUpdate, Dict[str, Any]], user_id: Optional[int] = None
    ) -> KnowledgePoint:
        if user_id:
            db_obj.updated_by = user_id
        updated_obj = await super().update(db, db_obj=db_obj, obj_in=obj_in)
        details = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)
        await log_activity(db, user_id, "update", "knowledge_point", updated_obj.id, details=details)
        await db.commit()
        
        # Sync to vector store
        await self._sync_to_vector_store(db, updated_obj)
        
        return updated_obj

    async def remove(self, db: AsyncSession, *, id: int, user_id: Optional[int] = None) -> KnowledgePoint:
        # Get all descendant IDs before deletion to clean up vector store
        descendant_ids = await self.get_descendant_ids(db, id)
        
        obj = await db.get(self.model, id)
        if obj:
            await db.delete(obj)
            await db.commit()
            await log_activity(db, user_id, "delete", "knowledge_point", id)
            await db.commit()
            
            # Remove from vector store
            for desc_id in descendant_ids:
                VectorStore.delete_knowledge_point(desc_id)
            
        return obj

    async def get_by_subject(self, db: AsyncSession, subject_id: int, skip: int = 0, limit: Optional[int] = 100) -> List[KnowledgePoint]:
        query = select(self.model).filter(self.model.subject_id == subject_id).offset(skip)
        if limit is not None and limit != -1:
            query = query.limit(limit)
        result = await db.execute(query)
        return result.scalars().all()

    async def get_descendant_ids(self, db: AsyncSession, knowledge_point_id: int) -> List[int]:
        root = await self.get(db, knowledge_point_id)
        if not root:
            return []
            
        # Fetch all knowledge points of the same subject to build tree
        # We assume the tree is not massive (e.g. < 10k nodes)
        all_kps = await self.get_by_subject(db, subject_id=root.subject_id, limit=None)
        
        # Build adjacency list
        children_map = {}
        for kp in all_kps:
            pid = kp.parent_id
            if pid not in children_map:
                children_map[pid] = []
            children_map[pid].append(kp.id)
            
        # BFS to find all descendants
        ids = [knowledge_point_id]
        queue = [knowledge_point_id]
        while queue:
            current = queue.pop(0)
            if current in children_map:
                children = children_map[current]
                ids.extend(children)
                queue.extend(children)
                
        return ids

knowledge_point = CRUDKnowledgePoint(KnowledgePoint)
