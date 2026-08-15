from typing import Any, List

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from app.api import deps
from app.crud import crud_user
from app.schemas.user import (
    User,
    UserCreate,
    UserUpdate,
    UserUpdatePassword,
    UserUpdateLastSubject,
    UserImportResult,
)
from app.core import security
from app.services import user_import_service

router = APIRouter()

MAX_IMPORT_SIZE = 5 * 1024 * 1024  # 5 MB

@router.get("", response_model=List[User])
async def read_users(
    session: deps.SessionDep,
    skip: int = 0,
    limit: int = 100,
    subject_id: int | None = None,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Retrieve users.
    """
    users = await crud_user.user.get_multi(session, skip=skip, limit=limit, subject_id=subject_id)
    return users

@router.post("", response_model=User)
async def create_user(
    *,
    session: deps.SessionDep,
    user_in: UserCreate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Create new user.
    """
    user = await crud_user.user.get_by_username(session, username=user_in.username)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )
    user = await crud_user.user.create(session, obj_in=user_in)
    return user

@router.get("/import-template")
async def download_import_template(
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """Download the .xlsx user import template."""
    content = user_import_service.generate_template()
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="users_template.xlsx"'
        },
    )

@router.post("/import", response_model=UserImportResult)
async def import_users(
    *,
    session: deps.SessionDep,
    file: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """Batch import users from an .xlsx file."""
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式的文件")

    content = await file.read()
    if len(content) > MAX_IMPORT_SIZE:
        raise HTTPException(status_code=400, detail="文件过大，请确保文件小于 5MB")

    return await user_import_service.import_excel(session, file_bytes=content)

@router.get("/me", response_model=User)
async def read_user_me(
    session: deps.SessionDep,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get current user.
    """
    return current_user

@router.put("/me", response_model=User)
async def update_user_me(
    *,
    session: deps.SessionDep,
    user_in: UserUpdate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Update own user.
    """
    if user_in.password:
        # Prevent password update via this endpoint if needed, or handle it.
        # The schema UserUpdate allows password.
        # But we have a specific endpoint for password update.
        # Let's allow it here too for consistency, or maybe restrict it.
        # Given the schema, it's allowed.
        pass
        
    user = await crud_user.user.update(session, db_obj=current_user, obj_in=user_in)
    return user

@router.put("/me/last-subject", response_model=User)
async def update_last_subject_me(
    *,
    session: deps.SessionDep,
    body: UserUpdateLastSubject,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Persist the current user's last active (working) subject.
    """
    user_in = UserUpdate(last_active_subject_id=body.subject_id)
    user = await crud_user.user.update(session, db_obj=current_user, obj_in=user_in)
    return user

@router.post("/me/password", response_model=User)
async def update_password_me(
    *,
    session: deps.SessionDep,
    body: UserUpdatePassword,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Update own password.
    """
    if not security.verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect password")
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=400, detail="New password cannot be the same as the current one"
        )
    
    user_in = UserUpdate(password=body.new_password)
    user = await crud_user.user.update(session, db_obj=current_user, obj_in=user_in)
    return user

@router.get("/{user_id}", response_model=User)
async def read_user_by_id(
    user_id: int,
    session: deps.SessionDep,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get a specific user by id.
    """
    user = await crud_user.user.get(session, id=user_id)
    if user == current_user:
        return user
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=400, detail="The user doesn't have enough privileges"
        )
    return user

@router.put("/{user_id}", response_model=User)
async def update_user(
    *,
    session: deps.SessionDep,
    user_id: int,
    user_in: UserUpdate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update a user.
    """
    user = await crud_user.user.get(session, id=user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="The user with this username does not exist in the system",
        )
    if user_in.username and user_in.username != user.username:
        existing_user = await crud_user.user.get_by_username(session, username=user_in.username)
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail="The user with this username already exists in the system.",
            )
    user = await crud_user.user.update(session, db_obj=user, obj_in=user_in)
    return user

@router.delete("/{user_id}", response_model=User)
async def delete_user(
    *,
    session: deps.SessionDep,
    user_id: int,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Delete a user.
    """
    user = await crud_user.user.get(session, id=user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="The user with this username does not exist in the system",
        )
    user = await crud_user.user.remove(session, id=user_id)
    return user
