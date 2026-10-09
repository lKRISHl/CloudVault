from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import clear_refresh_cookie, set_refresh_cookie
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserRead
from app.services.auth import AuthService

router = APIRouter()


def _cookie(request: Request) -> str | None:
    return request.cookies.get(settings.REFRESH_COOKIE_NAME)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    session = await AuthService(db).register(payload)
    set_refresh_cookie(response, session.refresh_token)
    return session.to_response()


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    session = await AuthService(db).login(payload)
    set_refresh_cookie(response, session.refresh_token)
    return session.to_response()


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    session = await AuthService(db).refresh(_cookie(request))
    set_refresh_cookie(response, session.refresh_token)
    return session.to_response()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await AuthService(db).logout(_cookie(request))
    clear_refresh_cookie(response)


@router.get("/me", response_model=UserRead)
async def me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user
