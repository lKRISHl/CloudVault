from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, literal, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Membership, Tenant, User, UserRole
from app.models.folder import Folder
from app.schemas.folders import FolderPage, FolderRead

MAX_DEPTH = 64


class FolderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def authorize(self, actor: User, write=False) -> UserRole:
        if write:
            if self.db.bind.dialect.name == "sqlite":
                # Test/direct-development SQLite has no row locks. Acquire its
                # database writer lock before reading the mutable hierarchy.
                await self.db.execute(text("BEGIN IMMEDIATE"))
            await self.db.scalar(
                select(Tenant.id).where(Tenant.id == actor.tenant_id).with_for_update()
            )
        role = await self.db.scalar(
            select(Membership.role)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.tenant_id == actor.tenant_id,
                Membership.user_id == actor.id,
                Membership.revoked_at.is_(None),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                User.email_verified.is_(True),
            )
        )
        if role is None:
            raise HTTPException(
                status_code=403, detail="Active verified workspace membership required"
            )
        return role

    @staticmethod
    def can_write(actor: User, role: UserRole, folder: Folder) -> bool:
        return role in (UserRole.OWNER, UserRole.ADMIN) or folder.created_by == actor.id

    def require_write(self, actor: User, role: UserRole, folder: Folder) -> None:
        if not self.can_write(actor, role, folder):
            raise HTTPException(
                status_code=403,
                detail="Only the folder creator or organization managers can modify this folder",
            )

    @staticmethod
    def read(actor: User, role: UserRole, folder: Folder) -> FolderRead:
        return FolderRead(
            id=folder.id,
            tenant_id=folder.tenant_id,
            parent_id=folder.parent_id,
            created_by=folder.created_by,
            name=folder.name,
            created_at=folder.created_at,
            updated_at=folder.updated_at,
            can_write=FolderService.can_write(actor, role, folder),
        )

    async def folder(self, actor: User, folder_id: UUID) -> Folder:
        folder = await self.db.scalar(
            select(Folder)
            .where(Folder.id == folder_id, Folder.tenant_id == actor.tenant_id)
            .execution_options(populate_existing=True)
        )
        if folder is None:
            raise HTTPException(status_code=404, detail="Folder not found")
        return folder

    async def ancestors(self, actor: User, folder_id: UUID | None) -> list[Folder]:
        chain, seen = [], set()
        while folder_id is not None:
            if folder_id in seen or len(chain) >= MAX_DEPTH:
                raise HTTPException(
                    status_code=409, detail="Invalid folder hierarchy or maximum depth exceeded"
                )
            seen.add(folder_id)
            folder = await self.folder(actor, folder_id)
            chain.append(folder)
            folder_id = folder.parent_id
        return list(reversed(chain))

    async def children(
        self, actor: User, parent_id: UUID | None, offset: int, limit: int
    ) -> FolderPage:
        role = await self.authorize(actor)
        path = await self.ancestors(actor, parent_id)
        rows = list(
            await self.db.scalars(
                select(Folder)
                .where(Folder.tenant_id == actor.tenant_id, Folder.parent_id == parent_id)
                .order_by(Folder.name, Folder.id)
                .offset(offset)
                .limit(limit + 1)
            )
        )
        return FolderPage(
            parent=self.read(actor, role, path[-1]) if path else None,
            breadcrumbs=[self.read(actor, role, folder) for folder in path],
            items=[self.read(actor, role, folder) for folder in rows[:limit]],
            offset=offset,
            limit=limit,
            has_more=len(rows) > limit,
        )

    async def details(self, actor: User, folder_id: UUID) -> FolderRead:
        role = await self.authorize(actor)
        return self.read(actor, role, await self.folder(actor, folder_id))

    async def ensure_name(
        self, actor: User, parent_id: UUID | None, name: str, exclude: UUID | None = None
    ) -> None:
        statement = select(Folder.id).where(
            Folder.tenant_id == actor.tenant_id,
            Folder.parent_id == parent_id,
            Folder.name_key == name.casefold(),
        )
        if exclude:
            statement = statement.where(Folder.id != exclude)
        if await self.db.scalar(statement) is not None:
            raise HTTPException(
                status_code=409, detail="A folder with this name already exists here"
            )

    async def save(self, actor: User, role: UserRole, folder: Folder) -> FolderRead:
        try:
            await self.db.commit()
            await self.db.refresh(folder)
            return self.read(actor, role, folder)
        except IntegrityError as error:
            await self.db.rollback()
            raise HTTPException(
                status_code=409, detail="Folder conflicts with an existing folder"
            ) from error

    async def create(self, actor: User, name: str, parent_id: UUID | None) -> FolderRead:
        role = await self.authorize(actor, write=True)
        path = await self.ancestors(actor, parent_id)
        if path:
            self.require_write(actor, role, path[-1])
        if len(path) + 1 > MAX_DEPTH:
            raise HTTPException(status_code=409, detail="Maximum folder depth exceeded")
        await self.ensure_name(actor, parent_id, name)
        folder = Folder(
            tenant_id=actor.tenant_id,
            parent_id=parent_id,
            created_by=actor.id,
            name=name,
            name_key=name.casefold(),
        )
        self.db.add(folder)
        return await self.save(actor, role, folder)

    async def rename(self, actor: User, folder_id: UUID, name: str) -> FolderRead:
        role = await self.authorize(actor, write=True)
        folder = await self.folder(actor, folder_id)
        self.require_write(actor, role, folder)
        await self.ensure_name(actor, folder.parent_id, name, exclude=folder.id)
        folder.name, folder.name_key = name, name.casefold()
        return await self.save(actor, role, folder)

    async def move(self, actor: User, folder_id: UUID, parent_id: UUID | None) -> FolderRead:
        role = await self.authorize(actor, write=True)
        folder = await self.folder(actor, folder_id)
        self.require_write(actor, role, folder)
        path = await self.ancestors(actor, parent_id)
        if any(item.id == folder.id for item in path):
            raise HTTPException(
                status_code=409, detail="Cannot move a folder into itself or its descendants"
            )
        if path:
            self.require_write(actor, role, path[-1])
        subtree = (
            select(Folder.id, literal(1).label("depth"))
            .where(Folder.id == folder.id, Folder.tenant_id == actor.tenant_id)
            .cte("subtree", recursive=True)
        )
        subtree = subtree.union_all(
            select(Folder.id, (subtree.c.depth + 1).label("depth"))
            .join(subtree, Folder.parent_id == subtree.c.id)
            .where(Folder.tenant_id == actor.tenant_id, subtree.c.depth < MAX_DEPTH + 1)
        )
        height = await self.db.scalar(select(func.max(subtree.c.depth)))
        if len(path) + height > MAX_DEPTH:
            raise HTTPException(status_code=409, detail="Maximum folder depth exceeded")
        await self.ensure_name(actor, parent_id, folder.name, exclude=folder.id)
        folder.parent_id = parent_id
        return await self.save(actor, role, folder)
