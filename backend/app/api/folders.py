from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_workspace_user
from app.api.users import Database
from app.models import User
from app.schemas.folders import FolderCreate, FolderMove, FolderName, FolderPage, FolderRead
from app.services.folders import FolderService

router = APIRouter()
WorkspaceUser = Annotated[User, Depends(get_workspace_user)]


@router.get("", response_model=FolderPage)
async def children(
    actor: WorkspaceUser,
    db: Database,
    parent_id: UUID | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
):
    return await FolderService(db).children(actor, parent_id, offset, limit)


@router.post("", response_model=FolderRead, status_code=201)
async def create(payload: FolderCreate, actor: WorkspaceUser, db: Database):
    return await FolderService(db).create(actor, payload.name, payload.parent_id)


@router.get("/{folder_id}", response_model=FolderRead)
async def details(folder_id: UUID, actor: WorkspaceUser, db: Database):
    return await FolderService(db).details(actor, folder_id)


@router.patch("/{folder_id}", response_model=FolderRead)
async def rename(folder_id: UUID, payload: FolderName, actor: WorkspaceUser, db: Database):
    return await FolderService(db).rename(actor, folder_id, payload.name)


@router.post("/{folder_id}/move", response_model=FolderRead)
async def move(folder_id: UUID, payload: FolderMove, actor: WorkspaceUser, db: Database):
    return await FolderService(db).move(actor, folder_id, payload.parent_id)
