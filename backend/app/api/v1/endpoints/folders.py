from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException

from app.api import deps
from app import crud, models
from app.schemas.composition import FolderCreate, FolderUpdate, FolderRead

router = APIRouter()


@router.get("", response_model=List[FolderRead])
async def list_folders(
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
    subject_id: Optional[int] = None,
    scope: Optional[str] = None,
) -> Any:
    if subject_id is None:
        subject_id = current_user.last_active_subject_id or current_user.subject_id

    # personal 空间只看自己的; team 空间全组共享, 不按 owner 过滤
    owner_filter = current_user.id if scope == "personal" else None

    folders = await crud.folder.get_tree(
        db, subject_id=subject_id, scope=scope, owner_id=owner_filter
    )
    return folders


@router.post("", response_model=FolderRead)
async def create_folder(
    *,
    db: deps.SessionDep,
    folder_in: FolderCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    folder = await crud.folder.create(db, obj_in=folder_in, owner_id=current_user.id)
    return folder


@router.patch("/{folder_id}", response_model=FolderRead)
async def update_folder(
    *,
    db: deps.SessionDep,
    folder_id: int,
    folder_in: FolderUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    folder = await crud.folder.get(db, folder_id=folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if folder.scope != "team" and folder.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    folder = await crud.folder.update(db, db_obj=folder, obj_in=folder_in)
    return folder


@router.delete("/{folder_id}")
async def delete_folder(
    *,
    db: deps.SessionDep,
    folder_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    folder = await crud.folder.get(db, folder_id=folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if folder.scope != "team" and folder.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    await crud.folder.delete(db, db_obj=folder)
    return {"ok": True}
