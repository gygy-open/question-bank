from datetime import timedelta, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.security import OAuth2PasswordRequestForm

from app.api import deps
from app.core import security
from app.core.config import settings
from app.crud import crud_user
from app.schemas.token import Token
from app.schemas.user import User
from app.models.activity_log import ActivityLog

router = APIRouter()

@router.post("/login/access-token", response_model=Token)
async def login_access_token(
    response: Response,
    request: Request,
    session: deps.SessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    user = await crud_user.user.authenticate(
        session, username=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    # Update user login stats
    user.last_login = datetime.utcnow()
    user.login_count = (user.login_count or 0) + 1
    session.add(user)

    # Create activity log
    log = ActivityLog(
        user_id=user.id,
        action="login",
        resource_type="user",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None,
        details={"username": user.username}
    )
    session.add(log)
    await session.commit()

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    
    response.set_cookie(
        key="token",
        value=access_token,
        httponly=False,
        max_age=int(access_token_expires.total_seconds()),
        path="/",
        samesite="lax",
        secure=False,
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
    )

@router.post("/login/test-token", response_model=User)
async def test_token(current_user: Annotated[User, Depends(deps.get_current_user)]) -> User:
    """
    Test access token
    """
    return current_user

@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    session: deps.SessionDep,
    current_user: Annotated[User, Depends(deps.get_current_user)],
):
    """
    Logout user
    """
    # Create activity log
    log = ActivityLog(
        user_id=current_user.id,
        action="logout",
        resource_type="user",
        resource_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        details={"username": current_user.username}
    )
    session.add(log)
    await session.commit()
    
    response.delete_cookie("token")
    return {"message": "Logged out successfully"}
