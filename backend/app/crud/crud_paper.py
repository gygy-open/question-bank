from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.paper import Paper, PaperQuestion
from app.models.question import Question
from app.schemas.paper import PaperCreate, PaperUpdate


class CRUDPaper(CRUDBase[Paper, PaperCreate, PaperUpdate]):
    async def create_for_owner(
        self, db: AsyncSession, *, obj_in: PaperCreate, owner_id: int
    ) -> Paper:
        db_obj = Paper(
            title=obj_in.title,
            subject_id=obj_in.subject_id,
            description=obj_in.description,
            owner_id=owner_id,
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj, ["items"])
        return db_obj

    async def get_owned(
        self, db: AsyncSession, *, paper_id: int, owner_id: int
    ) -> Optional[Paper]:
        query = select(Paper).where(Paper.id == paper_id, Paper.owner_id == owner_id)
        result = await db.execute(query)
        return result.scalars().first()

    async def get_detail(
        self, db: AsyncSession, *, paper_id: int, owner_id: int
    ) -> Optional[Paper]:
        query = (
            select(Paper)
            .options(selectinload(Paper.items).selectinload(PaperQuestion.question))
            .where(Paper.id == paper_id, Paper.owner_id == owner_id)
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def get_multi_by_owner(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        subject_id: Optional[int] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        sort: str = "updated_desc",
        skip: int = 0,
        limit: int = 100,
    ) -> List[Paper]:
        query = (
            select(Paper)
            .options(selectinload(Paper.items))
            .where(Paper.owner_id == owner_id)
        )
        if subject_id:
            query = query.where(Paper.subject_id == subject_id)
        if status:
            query = query.where(Paper.status == status)
        if keyword:
            query = query.where(Paper.title.ilike(f"%{keyword}%"))

        if sort == "created_desc":
            query = query.order_by(desc(Paper.created_at))
        elif sort == "title_asc":
            query = query.order_by(Paper.title)
        else:
            query = query.order_by(desc(Paper.updated_at))

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        return result.scalars().all()

    async def _next_sequence(self, db: AsyncSession, *, paper_id: int) -> int:
        query = select(func.max(PaperQuestion.sequence)).where(
            PaperQuestion.paper_id == paper_id
        )
        result = await db.execute(query)
        current_max = result.scalar()
        return 0 if current_max is None else current_max + 1

    async def add_items(
        self, db: AsyncSession, *, paper: Paper, question_ids: List[int]
    ) -> Paper:
        seq = await self._next_sequence(db, paper_id=paper.id)
        for qid in question_ids:
            db.add(PaperQuestion(paper_id=paper.id, question_id=qid, sequence=seq))
            seq += 1
        await db.commit()
        await db.refresh(paper)
        return paper

    async def remove_item(
        self, db: AsyncSession, *, paper_id: int, item_id: int
    ) -> bool:
        query = select(PaperQuestion).where(
            PaperQuestion.id == item_id, PaperQuestion.paper_id == paper_id
        )
        result = await db.execute(query)
        item = result.scalars().first()
        if not item:
            return False
        await db.delete(item)
        await db.commit()
        return True

    async def reorder(
        self, db: AsyncSession, *, paper: Paper, ordered_item_ids: List[int]
    ) -> Paper:
        """按提交的完整有序 item id 列表重写 sequence (幂等)。集合不一致则抛错。"""
        query = select(PaperQuestion).where(PaperQuestion.paper_id == paper.id)
        result = await db.execute(query)
        items = result.scalars().all()

        existing_ids = {item.id for item in items}
        if existing_ids != set(ordered_item_ids):
            raise ValueError("ordered_item_ids must match the paper's item set")

        item_map = {item.id: item for item in items}
        for index, item_id in enumerate(ordered_item_ids):
            item_map[item_id].sequence = index

        await db.commit()
        await db.refresh(paper)
        return paper

    async def get_ordered_questions(
        self, db: AsyncSession, *, paper_id: int
    ) -> List[Question]:
        """按 sequence 返回有序题目 (过滤软删除), 供试卷生成使用。"""
        query = (
            select(Question)
            .join(PaperQuestion, PaperQuestion.question_id == Question.id)
            .where(PaperQuestion.paper_id == paper_id, Question.deleted_at.is_(None))
            .order_by(PaperQuestion.sequence)
        )
        result = await db.execute(query)
        return result.scalars().all()

    async def get_ordered_items(
        self, db: AsyncSession, *, paper_id: int
    ) -> List[PaperQuestion]:
        """按 sequence 返回有序 item (含题目, 过滤软删除), 供导出保留手动分节。"""
        query = (
            select(PaperQuestion)
            .options(selectinload(PaperQuestion.question))
            .join(Question, PaperQuestion.question_id == Question.id)
            .where(PaperQuestion.paper_id == paper_id, Question.deleted_at.is_(None))
            .order_by(PaperQuestion.sequence)
        )
        result = await db.execute(query)
        return result.scalars().all()

    async def update_item(
        self,
        db: AsyncSession,
        *,
        paper_id: int,
        item_id: int,
        section_title: Optional[str] = None,
        score: Optional[float] = None,
        clear_section_title: bool = False,
    ) -> Optional[PaperQuestion]:
        query = select(PaperQuestion).where(
            PaperQuestion.id == item_id, PaperQuestion.paper_id == paper_id
        )
        result = await db.execute(query)
        item = result.scalars().first()
        if not item:
            return None
        if clear_section_title:
            item.section_title = None
        elif section_title is not None:
            item.section_title = section_title
        if score is not None:
            item.score = score
        await db.commit()
        await db.refresh(item)
        return item

    async def duplicate(self, db: AsyncSession, *, paper: Paper) -> Paper:
        new_paper = Paper(
            title=f"{paper.title} (副本)",
            description=paper.description,
            status=paper.status,
            subject_id=paper.subject_id,
            owner_id=paper.owner_id,
        )
        db.add(new_paper)
        await db.flush()

        items_query = (
            select(PaperQuestion)
            .where(PaperQuestion.paper_id == paper.id)
            .order_by(PaperQuestion.sequence)
        )
        result = await db.execute(items_query)
        for item in result.scalars().all():
            db.add(
                PaperQuestion(
                    paper_id=new_paper.id,
                    question_id=item.question_id,
                    sequence=item.sequence,
                    section_title=item.section_title,
                    score=item.score,
                )
            )
        await db.commit()
        await db.refresh(new_paper)
        return new_paper


paper = CRUDPaper(Paper)
