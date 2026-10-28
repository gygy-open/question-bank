"""API Key 管理(目前仅用于 MCP 接入)与 MCP 服务开关。

Key 的权限完全继承所属用户;这里只管生命周期:创建(明文仅返回一次)、列出、撤销。
"""
from typing import Any, List

from fastapi import APIRouter, Depends, Request, status

from app import models
from app.api import deps
from app.core.api_errors import ApiError, ErrorCode
from app.crud.crud_api_key import api_key as crud_api_key
from app.mcp_server import MCP_PATH
from app.schemas.api_key import (
    ApiKeyAdminRead,
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyRead,
    McpInfo,
    McpSettingsUpdate,
)
from app.services.activity_logger import log_activity
from app.services.mcp_settings import is_mcp_enabled, set_mcp_enabled

router = APIRouter()

MAX_KEYS_PER_USER = 20


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/mcp-info", response_model=McpInfo)
async def read_mcp_info(
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return McpInfo(enabled=await is_mcp_enabled(db), path=MCP_PATH)


@router.put("/mcp-settings", response_model=McpInfo)
async def update_mcp_settings(
    body: McpSettingsUpdate,
    request: Request,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    await log_activity(
        db, current_user.id, "update", "mcp_settings", details={"enabled": body.enabled},
        ip_address=_client_ip(request),
    )
    await set_mcp_enabled(db, body.enabled)
    return McpInfo(enabled=body.enabled, path=MCP_PATH)


@router.get("", response_model=List[ApiKeyRead])
async def list_my_api_keys(
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await crud_api_key.list_by_user(db, user_id=current_user.id)


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyCreate,
    request: Request,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    if await crud_api_key.count_by_user(db, user_id=current_user.id) >= MAX_KEYS_PER_USER:
        raise ApiError(
            400,
            ErrorCode.API_KEY_LIMIT_REACHED,
            f"At most {MAX_KEYS_PER_USER} API keys per user",
            params={"limit": MAX_KEYS_PER_USER},
        )
    row, plaintext = await crud_api_key.create_for_user(db, user_id=current_user.id, obj_in=body)
    await log_activity(
        db, current_user.id, "create", "api_key", row.id,
        details={"name": row.name, "prefix": row.prefix}, ip_address=_client_ip(request),
    )
    await db.commit()
    return ApiKeyCreated(**ApiKeyRead.model_validate(row).model_dump(), key=plaintext)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_api_key(
    key_id: int,
    request: Request,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> None:
    row = await crud_api_key.get(db, id=key_id)
    # 他人的 Key 一律按不存在处理,不暴露其存在性
    if row is None or row.user_id != current_user.id:
        raise ApiError(404, ErrorCode.API_KEY_NOT_FOUND, "API key not found")
    await _revoke(db, row, actor=current_user, ip=_client_ip(request))


@router.get("/all", response_model=List[ApiKeyAdminRead])
async def list_all_api_keys(
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    rows = await crud_api_key.list_all(db)
    return [
        ApiKeyAdminRead(
            **ApiKeyRead.model_validate(row).model_dump(),
            user_id=row.user_id,
            username=row.user.username,
            full_name=row.user.full_name,
        )
        for row in rows
    ]


@router.delete("/all/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_any_api_key(
    key_id: int,
    request: Request,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> None:
    row = await crud_api_key.get(db, id=key_id)
    if row is None:
        raise ApiError(404, ErrorCode.API_KEY_NOT_FOUND, "API key not found")
    await _revoke(db, row, actor=current_user, ip=_client_ip(request))


async def _revoke(db, row: models.ApiKey, *, actor: models.User, ip: str | None) -> None:
    await log_activity(
        db, actor.id, "delete", "api_key", row.id,
        details={"name": row.name, "prefix": row.prefix, "owner_id": row.user_id}, ip_address=ip,
    )
    await db.delete(row)
    await db.commit()
