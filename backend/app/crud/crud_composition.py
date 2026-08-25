"""组稿 (Composition) 域的 scoped 查询 —— 第二阶段。

职责边界(与 service 层划分):
- 本模块只负责 **带范围约束的读取**:所有 get/list 都强制 subject_id + scope_type + owner_id,
  确保不会先无范围 get 再漏校验(防越权与枚举)。
- 事务、乐观锁、环检测等领域逻辑放在 app/services/composition_service.py。

owner_id 语义:shared → None;personal → 具体用户 id。调用方须据 scope_type 传入正确的 owner_id。
"""
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.composition import (
    Composition,
    CompositionBlock,
    CompositionVersion,
    Folder,
    ScopeType,
)
from app.schemas.composition import (
    CompositionCreate,
    CompositionUpdate,
    FolderCreate,
    FolderUpdate,
)


class CRUDFolder(CRUDBase[Folder, FolderCreate, FolderUpdate]):
    async def get_scoped(
        self,
        db: AsyncSession,
        *,
        folder_id: int,
        subject_id: int,
        scope_type: ScopeType,
        owner_id: Optional[int],
        include_deleted: bool = False,
    ) -> Optional[Folder]:
        query = select(Folder).where(
            Folder.id == folder_id,
            Folder.subject_id == subject_id,
            Folder.scope_type == scope_type,
            Folder.owner_id == owner_id,
        )
        if not include_deleted:
            query = query.where(Folder.deleted_at.is_(None))
        result = await db.execute(query)
        return result.scalars().first()

    async def list_scoped(
        self,
        db: AsyncSession,
        *,
        subject_id: int,
        scope_type: ScopeType,
        owner_id: Optional[int],
        include_deleted: bool = False,
    ) -> List[Folder]:
        query = select(Folder).where(
            Folder.subject_id == subject_id,
            Folder.scope_type == scope_type,
            Folder.owner_id == owner_id,
        )
        if not include_deleted:
            query = query.where(Folder.deleted_at.is_(None))
        query = query.order_by(Folder.name, Folder.id)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def count_active_children(
        self,
        db: AsyncSession,
        *,
        folder_id: int,
    ) -> int:
        """未删除的子文件夹 + 组稿数量。用于软删除前的非空检查。"""
        child_folders = await db.execute(
            select(func.count())
            .select_from(Folder)
            .where(Folder.parent_id == folder_id, Folder.deleted_at.is_(None))
        )
        child_comps = await db.execute(
            select(func.count())
            .select_from(Composition)
            .where(Composition.folder_id == folder_id, Composition.deleted_at.is_(None))
        )
        return int(child_folders.scalar_one()) + int(child_comps.scalar_one())


class CRUDComposition(CRUDBase[Composition, CompositionCreate, CompositionUpdate]):
    async def get_scoped(
        self,
        db: AsyncSession,
        *,
        composition_id: int,
        subject_id: int,
        scope_type: ScopeType,
        owner_id: Optional[int],
        include_deleted: bool = False,
        with_blocks: bool = False,
    ) -> Optional[Composition]:
        query = select(Composition).where(
            Composition.id == composition_id,
            Composition.subject_id == subject_id,
            Composition.scope_type == scope_type,
            Composition.owner_id == owner_id,
        )
        if with_blocks:
            query = query.options(selectinload(Composition.blocks))
        if not include_deleted:
            query = query.where(Composition.deleted_at.is_(None))
        result = await db.execute(query)
        return result.scalars().first()

    async def list_blocks(
        self,
        db: AsyncSession,
        *,
        composition_id: int,
    ) -> List[CompositionBlock]:
        query = (
            select(CompositionBlock)
            .where(CompositionBlock.composition_id == composition_id)
            .order_by(CompositionBlock.sequence)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def list_scoped(
        self,
        db: AsyncSession,
        *,
        subject_id: int,
        scope_type: ScopeType,
        owner_id: Optional[int],
        folder_id: Optional[int] = None,
        root_only: bool = False,
        include_deleted: bool = False,
        only_deleted: bool = False,
    ) -> List[Composition]:
        query = select(Composition).where(
            Composition.subject_id == subject_id,
            Composition.scope_type == scope_type,
            Composition.owner_id == owner_id,
        )
        if only_deleted:
            query = query.where(Composition.deleted_at.is_not(None))
        elif not include_deleted:
            query = query.where(Composition.deleted_at.is_(None))
        if root_only:
            query = query.where(Composition.folder_id.is_(None))
        elif folder_id is not None:
            query = query.where(Composition.folder_id == folder_id)
        query = query.order_by(Composition.updated_at.desc(), Composition.id.desc())
        result = await db.execute(query)
        return list(result.scalars().all())

    async def list_versions(
        self,
        db: AsyncSession,
        *,
        composition_id: int,
    ) -> List[CompositionVersion]:
        """版本列表(轻量,调用方投影到不含 snapshot 的 summary),按 version_no 升序。"""
        query = (
            select(CompositionVersion)
            .where(CompositionVersion.composition_id == composition_id)
            .order_by(CompositionVersion.version_no)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_version(
        self,
        db: AsyncSession,
        *,
        composition_id: int,
        version_no: int,
    ) -> Optional[CompositionVersion]:
        query = select(CompositionVersion).where(
            CompositionVersion.composition_id == composition_id,
            CompositionVersion.version_no == version_no,
        )
        result = await db.execute(query)
        return result.scalars().first()

    async def max_version_no(
        self,
        db: AsyncSession,
        *,
        composition_id: int,
    ) -> int:
        """当前 composition 的最大 version_no;无版本时返回 0(下一个即 1)。"""
        result = await db.execute(
            select(func.max(CompositionVersion.version_no)).where(
                CompositionVersion.composition_id == composition_id
            )
        )
        return int(result.scalar() or 0)


folder = CRUDFolder(Folder)
composition = CRUDComposition(Composition)
