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
            comp_type=obj_in.comp_type,
            folder_id=folder_id,
            description=obj_in.description,
            difficulty=obj_in.difficulty,
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
                selectinload(Composition.blocks).selectinload(CompositionBlock.ref_composition),
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
        comp_type: Optional[str] = None,
        folder_id: Optional[int] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        difficulty: Optional[int] = None,
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
        )
        if subject_id:
            query = query.where(Folder.subject_id == subject_id)
        if scope:
            query = query.where(Folder.scope == scope)
        if owner_id:
            query = query.where(Composition.owner_id == owner_id)
        if folder_id:
            query = query.where(Composition.folder_id == folder_id)
        if comp_type:
            query = query.where(Composition.comp_type == comp_type)
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
                    ref_composition_id=block.ref_composition_id,
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
        """渲染用: 将 component_ref 块就地展开为被引题组的有序块 (单层)。"""
        result: List[CompositionBlock] = []
        for b in await self.get_ordered_blocks(db, comp_id=comp_id):
            if b.block_type == BlockType.COMPONENT_REF.value and b.ref_composition_id:
                result.extend(await self.get_ordered_blocks(db, comp_id=b.ref_composition_id))
            else:
                result.append(b)
        return result

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

    async def append_component_ref(
        self, db: AsyncSession, *, composition: Composition, group_id: int
    ) -> Composition:
        """引用式插入: 追加一个指向题组的 component_ref 块 (跟随更新)。"""
        seq = await self._next_block_sequence(db, comp_id=composition.id)
        db.add(
            CompositionBlock(
                composition_id=composition.id,
                block_type=BlockType.COMPONENT_REF.value,
                sequence=seq,
                content=None,
                ref_composition_id=group_id,
            )
        )
        await db.commit()
        await db.refresh(composition)
        return composition

    async def detach_component_ref(
        self, db: AsyncSession, *, composition: Composition, block_id: int
    ) -> Composition:
        """拆开: 把某个 component_ref 块替换为被引题组块的深拷贝 (剥离引用)。"""
        block = (
            await db.execute(
                select(CompositionBlock).where(
                    CompositionBlock.id == block_id,
                    CompositionBlock.composition_id == composition.id,
                )
            )
        ).scalars().first()
        if not block or block.block_type != BlockType.COMPONENT_REF.value or not block.ref_composition_id:
            return composition

        source = await self.get_ordered_blocks(db, comp_id=block.ref_composition_id)
        all_blocks = await self.get_ordered_blocks(db, comp_id=composition.id)

        # 重排: 用深拷贝的子块替换该 component_ref 块的位置
        rebuilt: List[CompositionBlock] = []
        for b in all_blocks:
            if b.id == block.id:
                for s in source:
                    rebuilt.append(
                        CompositionBlock(
                            composition_id=composition.id,
                            block_type=s.block_type,
                            content=s.content,
                            ref_question_id=s.ref_question_id,
                        )
                    )
            else:
                rebuilt.append(b)

        for old in all_blocks:
            await db.delete(old)
        await db.flush()
        for index, nb in enumerate(rebuilt):
            nb.sequence = index
            db.add(nb)
        await db.commit()
        await db.refresh(composition)
        return composition

    async def duplicate(self, db: AsyncSession, *, composition: Composition) -> Composition:
        new_comp = Composition(
            title=f"{composition.title} (副本)",
            comp_type=composition.comp_type,
            folder_id=composition.folder_id,
            description=composition.description,
            status=composition.status,
            difficulty=composition.difficulty,
            meta_data=composition.meta_data,
            owner_id=composition.owner_id,
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
                    ref_composition_id=block.ref_composition_id,
                )
            )
        await db.commit()
        await db.refresh(new_comp, ["blocks", "folder"])
        return new_comp


composition = CRUDComposition(Composition)
