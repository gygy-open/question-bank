from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.composition import Folder, FolderScope


class CRUDFolder:
    async def ensure_root(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        subject_id: int,
        scope: str = FolderScope.PERSONAL.value,
    ) -> Folder:
        """找到或创建根文件夹 (parent_id 为空).

        personal: 按 (subject_id, owner_id, scope) 唯一; team: 按 (subject_id, scope) 全组共用一个。
        """
        query = select(Folder).where(
            Folder.parent_id.is_(None),
            Folder.subject_id == subject_id,
            Folder.scope == scope,
        )
        if scope == FolderScope.PERSONAL.value:
            query = query.where(Folder.owner_id == owner_id)

        existing = (await db.execute(query)).scalars().first()
        if existing:
            return existing

        name = "团队共享" if scope == FolderScope.TEAM.value else "我的空间"
        folder = Folder(
            name=name, parent_id=None,
            subject_id=subject_id, owner_id=owner_id, scope=scope, sequence=0,
        )
        db.add(folder)
        await db.commit()
        await db.refresh(folder)
        return folder

    async def get(self, db: AsyncSession, *, folder_id: int) -> Optional[Folder]:
        return (
            await db.execute(select(Folder).where(Folder.id == folder_id))
        ).scalars().first()

    async def get_tree(
        self,
        db: AsyncSession,
        *,
        subject_id: int,
        scope: Optional[str] = None,
        owner_id: Optional[int] = None,
    ) -> List[Folder]:
        query = select(Folder).where(Folder.subject_id == subject_id)
        if scope is not None:
            query = query.where(Folder.scope == scope)
        if owner_id is not None:
            query = query.where(Folder.owner_id == owner_id)
        
        query = query.order_by(Folder.sequence, Folder.name)
        return list((await db.execute(query)).scalars().all())

    async def create(self, db: AsyncSession, *, obj_in, owner_id: int) -> Folder:
        folder = Folder(
            name=obj_in.name,
            subject_id=obj_in.subject_id,
            parent_id=obj_in.parent_id,
            scope=obj_in.scope,
            owner_id=owner_id,
        )
        db.add(folder)
        await db.commit()
        await db.refresh(folder)
        return folder

    async def update(self, db: AsyncSession, *, db_obj: Folder, obj_in) -> Folder:
        data = obj_in.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(db_obj, field, value)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def delete(self, db: AsyncSession, *, db_obj: Folder) -> None:
        await db.delete(db_obj)
        await db.commit()


folder = CRUDFolder()
