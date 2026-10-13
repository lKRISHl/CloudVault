from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import User
from app.services.auth import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    service = AuthService(db)
    user_id, tenant_id, session_id = service.parse_access_token(credentials.credentials)
    user = await service.get_user_in_tenant(user_id, tenant_id)
    if user is None or not await service.valid_session(user_id, session_id, tenant_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    request.state.session_id = session_id
    return user


async def get_verified_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.email_verified:
        raise HTTPException(
            status_code=403, detail="Verify your email before using organization features"
        )
    return user


async def get_workspace_user(user: Annotated[User, Depends(get_verified_user)]) -> User:
    if user.tenant is None:
        raise HTTPException(status_code=403, detail="Select a workspace first")
    return user
