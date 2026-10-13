from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas.auth import UserRead
from app.schemas.organizations import ProfileUpdate
from app.services.organizations import OrganizationService

router = APIRouter()
CurrentUser = Annotated[User, Depends(get_current_user)]
Database = Annotated[AsyncSession, Depends(get_db)]


@router.get("/me", response_model=UserRead)
async def profile(actor: CurrentUser) -> User:
    return actor


@router.patch("/me", response_model=UserRead)
async def update_profile(payload: ProfileUpdate, actor: CurrentUser, db: Database) -> User:
    return await OrganizationService(db).update_profile(actor, payload.full_name)
