from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.composition import (
    Composition,
    CompositionBlock,
    BlockType,
    Folder,
    FolderScope,
)
from app.schemas.composition import CompositionCreate, CompositionUpdate, BlockWrite
from app.crud.crud_folder import folder as crud_folder


class CRUDComposition(CRUDBase[Composition, CompositionCreate, CompositionUpdate]):
    async def _resolve_folder_id(
        self, db: AsyncSession, *, obj_in: CompositionCreate, owner_id: int, subject_id: Optional[int]
    ) -> int:
        if obj_in.folder_id:
            return obj_in.folder_id
        scope = obj_in.scope.value if hasattr(obj_in.scope, "value") else obj_in.scope
        root = await crud_folder.ensure_root(db, owner_id=owner_id, subject_id=subject_id, scope=scope)
        return root.id

    async def create_for_owner(
        self, db: AsyncSession, *, obj_in: CompositionCreate, owner_id: int, subject_id: Optional[int]
    ) -> Composition:
        folder_id = await self._resolve_folder_id(
            db, obj_in=obj_in, owner_id=owner_id, subject_id=subject_id
        )
        db_obj = Composition(
            title=obj_in.title,
            folder_id=folder_id,
            description=obj_in.description,
            difficulty=obj_in.difficulty,
            meta_data=obj_in.meta_data,
            owner_id=owner_id,
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj, ["blocks", "folder"])
        return db_obj

    async def get_owned(
        self, db: AsyncSession, *, comp_id: int, owner_id: int
    ) -> Optional[Composition]:
        """可编辑: 本人创建, 或属于团队共享文件夹 (全组可编辑)。"""
        query = (
            select(Composition)
            .join(Folder, Composition.folder_id == Folder.id)
            .options(selectinload(Composition.folder))
            .where(
                Composition.id == comp_id,
                (Composition.owner_id == owner_id) | (Folder.scope == FolderScope.TEAM.value),
            )
        )
        return (await db.execute(query)).scalars().first()

    async def get_detail(
        self, db: AsyncSession, *, comp_id: int, owner_id: int
    ) -> Optional[Composition]:
        """查看详情: 本人的 or 团队共享的可见。"""
        query = (
            select(Composition)
            .join(Folder, Composition.folder_id == Folder.id)
            .options(
                selectinload(Composition.blocks).selectinload(CompositionBlock.question),
                selectinload(Composition.folder),
            )
            .where(
                Composition.id == comp_id,
                (Composition.owner_id == owner_id) | (Folder.scope == FolderScope.TEAM.value),
            )
        )
        return (await db.execute(query)).scalars().first()

    async def list(
        self,
        db: AsyncSession,
        *,
        owner_id: Optional[int] = None,
        subject_id: Optional[int] = None,
        scope: Optional[str] = None,
        folder_id: Optional[int] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        difficulty: Optional[int] = None,
        is_template: bool = False,
        sort: str = "updated_desc",
        skip: int = 0,
        limit: int = 100,
    ) -> List[Composition]:
        query = (
            select(Composition)
            .join(Folder, Composition.folder_id == Folder.id)
            .options(
                selectinload(Composition.blocks),
                selectinload(Composition.folder),
            )
            .where(Composition.is_template.is_(is_template))
        )
        if subject_id:
            query = query.where(Folder.subject_id == subject_id)
        if scope:
            query = query.where(Folder.scope == scope)
        if owner_id:
            query = query.where(Composition.owner_id == owner_id)
        if folder_id:
            query = query.where(Composition.folder_id == folder_id)
        if status:
            query = query.where(Composition.status == status)
        if difficulty:
            query = query.where(Composition.difficulty == difficulty)
        if keyword:
            query = query.where(Composition.title.ilike(f"%{keyword}%"))

        if sort == "created_desc":
            query = query.order_by(desc(Composition.created_at))
        elif sort == "title_asc":
            query = query.order_by(Composition.title)
        else:
            query = query.order_by(desc(Composition.updated_at))

        query = query.offset(skip).limit(limit)
        return list((await db.execute(query)).scalars().all())

    async def update_composition(
        self, db: AsyncSession, *, db_obj: Composition, obj_in: CompositionUpdate
    ) -> Composition:
        data = obj_in.model_dump(exclude_unset=True)
        for field, value in data.items():
            if field == "status" and value is not None:
                value = value.value if hasattr(value, "value") else value
            setattr(db_obj, field, value)
        await db.commit()
        await db.refresh(db_obj, ["blocks", "folder"])
        return db_obj

    # ------------------------------------------------------------------
    # Blocks
    # ------------------------------------------------------------------
    async def replace_blocks(
        self, db: AsyncSession, *, composition: Composition, blocks: List[BlockWrite]
    ) -> Composition:
        """整表覆写: 删除旧块, 按提交顺序重建。"""
        existing = await db.execute(
            select(CompositionBlock).where(
                CompositionBlock.composition_id == composition.id
            )
        )
        for block in existing.scalars().all():
            await db.delete(block)
        await db.flush()

        for index, block in enumerate(blocks):
            db.add(
                CompositionBlock(
                    composition_id=composition.id,
                    block_type=block.block_type.value,
                    sequence=index,
                    content=block.content,
                    ref_question_id=block.ref_question_id,
                )
            )
        await db.commit()
        await db.refresh(composition)
        return composition

    async def get_ordered_blocks(
        self, db: AsyncSession, *, comp_id: int
    ) -> List[CompositionBlock]:
        """按 sequence 返回有序块 (含题目)，跳过引用已软删除题目的题块。"""
        query = (
            select(CompositionBlock)
            .options(selectinload(CompositionBlock.question))
            .where(CompositionBlock.composition_id == comp_id)
            .order_by(CompositionBlock.sequence)
        )
        blocks = (await db.execute(query)).scalars().all()
        return [
            b
            for b in blocks
            if not (
                b.block_type == BlockType.QUESTION.value
                and (b.question is None or b.question.deleted_at is not None)
            )
        ]

    async def get_render_blocks(
        self, db: AsyncSession, *, comp_id: int
    ) -> List[CompositionBlock]:
        """渲染用: 返回有序块 (所见即所得, 无引用展开)。"""
        return await self.get_ordered_blocks(db, comp_id=comp_id)

    async def _next_block_sequence(self, db: AsyncSession, *, comp_id: int) -> int:
        result = await db.execute(
            select(func.max(CompositionBlock.sequence)).where(
                CompositionBlock.composition_id == comp_id
            )
        )
        current_max = result.scalar()
        return 0 if current_max is None else current_max + 1

    async def append_question_blocks(
        self, db: AsyncSession, *, composition: Composition, question_ids: List[int]
    ) -> Composition:
        """将若干题目作为题块追加到队尾 (试题篮加入题目)。"""
        seq = await self._next_block_sequence(db, comp_id=composition.id)
        for qid in question_ids:
            db.add(
                CompositionBlock(
                    composition_id=composition.id,
                    block_type=BlockType.QUESTION.value,
                    sequence=seq,
                    content=None,
                    ref_question_id=qid,
                )
            )
            seq += 1
        await db.commit()
        await db.refresh(composition)
        return composition

    async def duplicate(
        self,
        db: AsyncSession,
        *,
        composition: Composition,
        title: Optional[str] = None,
        folder_id: Optional[int] = None,
        owner_id: Optional[int] = None,
        is_template: bool = False,
    ) -> Composition:
        """深拷贝一份组稿 (含全部块), 与源解耦; 也用于从模板新建/另存为模板。"""
        new_comp = Composition(
            title=title or f"{composition.title} (副本)",
            folder_id=folder_id or composition.folder_id,
            description=composition.description,
            status=composition.status,
            difficulty=composition.difficulty,
            meta_data=composition.meta_data,
            is_template=is_template,
            owner_id=owner_id or composition.owner_id,
        )
        db.add(new_comp)
        await db.flush()

        blocks = (
            await db.execute(
                select(CompositionBlock)
                .where(CompositionBlock.composition_id == composition.id)
                .order_by(CompositionBlock.sequence)
            )
        ).scalars().all()
        for block in blocks:
            db.add(
                CompositionBlock(
                    composition_id=new_comp.id,
                    block_type=block.block_type,
                    sequence=block.sequence,
                    content=block.content,
                    ref_question_id=block.ref_question_id,
                )
            )
        await db.commit()
        await db.refresh(new_comp, ["blocks", "folder"])
        return new_comp

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------
    async def list_templates(
        self, db: AsyncSession, *, subject_id: int, owner_id: int
    ) -> List[Composition]:
        """自定义模板: 同学科下团队共享的 + 本人个人空间的。"""
        query = (
            select(Composition)
            .join(Folder, Composition.folder_id == Folder.id)
            .options(selectinload(Composition.blocks), selectinload(Composition.folder))
            .where(
                Composition.is_template.is_(True),
                Folder.subject_id == subject_id,
                (Folder.scope == FolderScope.TEAM.value)
                | ((Folder.scope == FolderScope.PERSONAL.value) & (Composition.owner_id == owner_id)),
            )
            .order_by(desc(Composition.updated_at))
        )
        return list((await db.execute(query)).scalars().all())

    async def create_from_system_template(
        self,
        db: AsyncSession,
        *,
        template,
        title: str,
        folder_id: int,
        owner_id: int,
    ) -> Composition:
        """从硬编码系统模板新建: 写入默认设置 + 初始块骨架。"""
        new_comp = Composition(
            title=title,
            folder_id=folder_id,
            meta_data=dict(template.meta_data),
            owner_id=owner_id,
        )
        db.add(new_comp)
        await db.flush()
        for index, block in enumerate(template.blocks):
            db.add(
                CompositionBlock(
                    composition_id=new_comp.id,
                    block_type=block["block_type"],
                    sequence=index,
                    content=block.get("content"),
                    ref_question_id=block.get("ref_question_id"),
                )
            )
        await db.commit()
        await db.refresh(new_comp, ["blocks", "folder"])
        return new_comp


composition = CRUDComposition(Composition)
