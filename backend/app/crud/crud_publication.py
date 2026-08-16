from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.publication import (
    Publication,
    PublicationBlock,
    PublicationType,
    BlockType,
    publication_knowledge_points,
)
from app.models.knowledge_point import KnowledgePoint
from app.models.question import Question
from app.schemas.publication import PublicationCreate, PublicationUpdate, BlockWrite


class CRUDPublication(CRUDBase[Publication, PublicationCreate, PublicationUpdate]):
    async def _load_knowledge_points(
        self, db: AsyncSession, ids: List[int]
    ) -> List[KnowledgePoint]:
        if not ids:
            return []
        result = await db.execute(
            select(KnowledgePoint).where(KnowledgePoint.id.in_(ids))
        )
        return result.scalars().all()

    async def create_for_owner(
        self, db: AsyncSession, *, obj_in: PublicationCreate, owner_id: int
    ) -> Publication:
        db_obj = Publication(
            title=obj_in.title,
            pub_type=obj_in.pub_type.value if obj_in.pub_type else PublicationType.EXAM_PAPER.value,
            subject_id=obj_in.subject_id,
            description=obj_in.description,
            difficulty=obj_in.difficulty,
            owner_id=owner_id,
        )
        if obj_in.knowledge_point_ids:
            db_obj.knowledge_points = await self._load_knowledge_points(
                db, obj_in.knowledge_point_ids
            )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj, ["blocks", "knowledge_points"])
        return db_obj

    async def get_owned(
        self, db: AsyncSession, *, pub_id: int, owner_id: int
    ) -> Optional[Publication]:
        query = select(Publication).where(
            Publication.id == pub_id, Publication.owner_id == owner_id
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def get_detail(
        self, db: AsyncSession, *, pub_id: int, owner_id: int
    ) -> Optional[Publication]:
        query = (
            select(Publication)
            .options(
                selectinload(Publication.blocks).selectinload(PublicationBlock.question),
                selectinload(Publication.knowledge_points),
            )
            .where(Publication.id == pub_id, Publication.owner_id == owner_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def get_multi_by_owner(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        pub_type: Optional[str] = None,
        subject_id: Optional[int] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        knowledge_point_ids: Optional[List[int]] = None,
        difficulty: Optional[int] = None,
        sort: str = "updated_desc",
        skip: int = 0,
        limit: int = 100,
    ) -> List[Publication]:
        query = (
            select(Publication)
            .options(
                selectinload(Publication.blocks),
                selectinload(Publication.knowledge_points),
            )
            .where(Publication.owner_id == owner_id)
        )
        if pub_type:
            query = query.where(Publication.pub_type == pub_type)
        if subject_id:
            query = query.where(Publication.subject_id == subject_id)
        if status:
            query = query.where(Publication.status == status)
        if difficulty:
            query = query.where(Publication.difficulty == difficulty)
        if keyword:
            query = query.where(Publication.title.ilike(f"%{keyword}%"))
        if knowledge_point_ids:
            query = query.where(
                Publication.knowledge_points.any(KnowledgePoint.id.in_(knowledge_point_ids))
            )

        if sort == "created_desc":
            query = query.order_by(desc(Publication.created_at))
        elif sort == "title_asc":
            query = query.order_by(Publication.title)
        else:
            query = query.order_by(desc(Publication.updated_at))

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        return result.scalars().all()

    async def update_with_relations(
        self, db: AsyncSession, *, db_obj: Publication, obj_in: PublicationUpdate
    ) -> Publication:
        data = obj_in.model_dump(exclude_unset=True)
        kp_ids = data.pop("knowledge_point_ids", None)
        for field, value in data.items():
            if field == "status" and value is not None:
                value = value.value if hasattr(value, "value") else value
            setattr(db_obj, field, value)
        if kp_ids is not None:
            db_obj.knowledge_points = await self._load_knowledge_points(db, kp_ids)
        await db.commit()
        await db.refresh(db_obj, ["blocks", "knowledge_points"])
        return db_obj

    async def replace_blocks(
        self, db: AsyncSession, *, publication: Publication, blocks: List[BlockWrite]
    ) -> Publication:
        """整表覆写: 删除旧块, 按提交顺序重建。"""
        existing = await db.execute(
            select(PublicationBlock).where(
                PublicationBlock.publication_id == publication.id
            )
        )
        for block in existing.scalars().all():
            await db.delete(block)
        await db.flush()

        for index, block in enumerate(blocks):
            db.add(
                PublicationBlock(
                    publication_id=publication.id,
                    block_type=block.block_type.value,
                    sequence=index,
                    content=block.content,
                    ref_question_id=block.ref_question_id,
                )
            )
        await db.commit()
        await db.refresh(publication)
        return publication

    async def get_ordered_blocks(
        self, db: AsyncSession, *, pub_id: int
    ) -> List[PublicationBlock]:
        """按 sequence 返回有序块 (含题目)，跳过引用已软删除题目的题块。"""
        query = (
            select(PublicationBlock)
            .options(selectinload(PublicationBlock.question))
            .where(PublicationBlock.publication_id == pub_id)
            .order_by(PublicationBlock.sequence)
        )
        result = await db.execute(query)
        blocks = result.scalars().all()
        return [
            b
            for b in blocks
            if not (
                b.block_type == BlockType.QUESTION.value
                and (b.question is None or b.question.deleted_at is not None)
            )
        ]

    async def import_group_blocks(
        self, db: AsyncSession, *, target: Publication, group: Publication
    ) -> Publication:
        """柔性解包: 将题组的块深拷贝追加到目标出版物队尾 (剥离原 id)。"""
        source = await self.get_ordered_blocks(db, pub_id=group.id)
        next_seq = await self._next_block_sequence(db, pub_id=target.id)
        for block in source:
            db.add(
                PublicationBlock(
                    publication_id=target.id,
                    block_type=block.block_type,
                    sequence=next_seq,
                    content=block.content,
                    ref_question_id=block.ref_question_id,
                )
            )
            next_seq += 1
        await db.commit()
        await db.refresh(target)
        return target

    async def _next_block_sequence(self, db: AsyncSession, *, pub_id: int) -> int:
        query = select(func.max(PublicationBlock.sequence)).where(
            PublicationBlock.publication_id == pub_id
        )
        result = await db.execute(query)
        current_max = result.scalar()
        return 0 if current_max is None else current_max + 1

    async def append_question_blocks(
        self, db: AsyncSession, *, publication: Publication, question_ids: List[int]
    ) -> Publication:
        """将若干题目作为题块追加到队尾 (试题篮加入题目)。"""
        seq = await self._next_block_sequence(db, pub_id=publication.id)
        for qid in question_ids:
            db.add(
                PublicationBlock(
                    publication_id=publication.id,
                    block_type=BlockType.QUESTION.value,
                    sequence=seq,
                    content=None,
                    ref_question_id=qid,
                )
            )
            seq += 1
        await db.commit()
        await db.refresh(publication)
        return publication

    async def duplicate(self, db: AsyncSession, *, publication: Publication) -> Publication:
        new_pub = Publication(
            title=f"{publication.title} (副本)",
            pub_type=publication.pub_type,
            description=publication.description,
            status=publication.status,
            difficulty=publication.difficulty,
            meta_data=publication.meta_data,
            subject_id=publication.subject_id,
            owner_id=publication.owner_id,
        )
        kp_rows = await db.execute(
            select(KnowledgePoint)
            .join(
                publication_knowledge_points,
                publication_knowledge_points.c.knowledge_point_id == KnowledgePoint.id,
            )
            .where(publication_knowledge_points.c.publication_id == publication.id)
        )
        new_pub.knowledge_points = kp_rows.scalars().all()
        db.add(new_pub)
        await db.flush()

        blocks_query = (
            select(PublicationBlock)
            .where(PublicationBlock.publication_id == publication.id)
            .order_by(PublicationBlock.sequence)
        )
        result = await db.execute(blocks_query)
        for block in result.scalars().all():
            db.add(
                PublicationBlock(
                    publication_id=new_pub.id,
                    block_type=block.block_type,
                    sequence=block.sequence,
                    content=block.content,
                    ref_question_id=block.ref_question_id,
                )
            )
        await db.commit()
        await db.refresh(new_pub, ["blocks", "knowledge_points"])
        return new_pub


publication = CRUDPublication(Publication)
