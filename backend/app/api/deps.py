from typing import Generator, Annotated, AsyncGenerator
from urllib.parse import unquote

from fastapi import Depends, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.capabilities.context import ExecutionContext, Surface
from app.core.api_errors import ApiError, ErrorCode
from app.core.config import settings
from app.core import permissions
from app.core.permissions import Permission
from app.crud import crud_user
from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.token import TokenPayload

class _OAuth2Bearer(OAuth2PasswordBearer):
    """缺少 Authorization 头时返回带错误码的 401(FastAPI 默认只有英文 detail)。"""

    def make_not_authenticated_error(self) -> ApiError:
        return ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_NOT_AUTHENTICATED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )


reusable_oauth2 = _OAuth2Bearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session

SessionDep = Annotated[AsyncSession, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]

async def _user_from_token(session: AsyncSession, token: str) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (JWTError, ValidationError):
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.AUTH_TOKEN_INVALID,
            "Could not validate credentials",
        )
    if not token_data.sub:
        raise ApiError(404, ErrorCode.AUTH_USER_NOT_FOUND, "User not found")
        
    user = await crud_user.user.get_with_memberships(session, id=int(token_data.sub))
    if not user:
        raise ApiError(404, ErrorCode.AUTH_USER_NOT_FOUND, "User not found")
    return user


async def get_current_user(session: SessionDep, token: TokenDep) -> User:
    return await _user_from_token(session, token)

CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_active_user_header_or_cookie(
    request: Request, session: SessionDep
) -> User:
    """媒体下发专用:<img>/<audio> 无法带 Authorization 头,同源请求会自动携带 token cookie。"""
    token = None
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        token = unquote(request.cookies.get("token") or "").strip('"')
    if not token:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTH_NOT_AUTHENTICATED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await _user_from_token(session, token)
    if not user.is_active:
        raise ApiError(400, ErrorCode.AUTH_INACTIVE_USER, "Inactive user")
    return user

def get_current_active_user(current_user: CurrentUser) -> User:
    if not current_user.is_active:
        raise ApiError(400, ErrorCode.AUTH_INACTIVE_USER, "Inactive user")
    return current_user

def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise ApiError(
            400, ErrorCode.AUTH_FORBIDDEN, "The user doesn't have enough privileges"
        )
    return current_user


def require(
    user: User,
    permission: Permission,
    *,
    subject_id: int | None = None,
    resource=None,
) -> None:
    """权限断言:不满足则抛 403。端点内联调用,与现有 inline 鉴权风格一致。"""
    if not permissions.can(user, permission, subject_id=subject_id, resource=resource):
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            ErrorCode.AUTH_FORBIDDEN,
            "The user doesn't have enough privileges",
        )


def api_context(
    db: AsyncSession,
    user: User,
    *,
    subject_id: int | None = None,
) -> ExecutionContext:
    """HTTP 入口的能力执行上下文。"""
    return ExecutionContext(db=db, actor=user, surface=Surface.API, subject_id=subject_id)
