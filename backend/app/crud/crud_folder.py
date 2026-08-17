from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.composition import Folder, CompositionScope


class CRUDFolder:
    async def ensure_root(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        subject_id: int,
        kind: str,
        scope: Optional[str] = None,
    ) -> Folder:
        """找到或创建 (owner, subject, kind, scope) 的根文件夹 (parent_id 为空)。

        component 树全员共享: 忽略 owner 维度, scope 恒 NULL。
        """
        query = select(Folder).where(
            Folder.parent_id.is_(None),
            Folder.subject_id == subject_id,
            Folder.kind == kind,
        )
        if kind == "component":
            scope = None
            query = query.where(Folder.scope.is_(None))
        else:
            scope = scope or CompositionScope.PERSONAL.value
            query = query.where(Folder.scope == scope, Folder.owner_id == owner_id)

        existing = (await db.execute(query)).scalars().first()
        if existing:
            return existing

        name = "题组库" if kind == "component" else ("团队作品" if scope == "team" else "我的作品")
        folder = Folder(
            name=name, parent_id=None, kind=kind, scope=scope,
            subject_id=subject_id, owner_id=owner_id, sequence=0,
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
        kind: str,
        scope: Optional[str] = None,
        owner_id: Optional[int] = None,
    ) -> List[Folder]:
        query = select(Folder).where(Folder.subject_id == subject_id, Folder.kind == kind)
        if kind == "component":
            query = query.where(Folder.scope.is_(None))
        else:
            if scope:
                query = query.where(Folder.scope == scope)
            if scope == CompositionScope.PERSONAL.value and owner_id is not None:
                query = query.where(Folder.owner_id == owner_id)
        query = query.order_by(Folder.sequence, Folder.name)
        return (await db.execute(query)).scalars().all()

    async def create(self, db: AsyncSession, *, obj_in, owner_id: int) -> Folder:
        folder = Folder(
            name=obj_in.name,
            kind=obj_in.kind,
            scope=obj_in.scope if obj_in.kind != "component" else None,
            subject_id=obj_in.subject_id,
            parent_id=obj_in.parent_id,
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
