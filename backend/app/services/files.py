from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserRole
from app.models.file import File
from app.schemas.files import FileMetadataCreate, FilePage, FileRead
from app.services.folders import FolderService
from app.services.permissions import PermissionService


class FileService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.folders = FolderService(db)

    @staticmethod
    def read(actor: User, role: UserRole, file: File) -> FileRead:
        return FileRead(
            **{
                field: getattr(file, field)
                for field in FileRead.model_fields
                if field not in ("can_write", "can_manage")
            },
            can_write=PermissionService.writes(actor, role, file),
            can_manage=PermissionService.manages(actor, role, file),
        )

    async def details(self, actor: User, file_id: UUID) -> FileRead:
        role = await self.folders.authorize(actor)
        file = await self.db.scalar(
            select(File).where(
                File.id == file_id,
                File.tenant_id == actor.tenant_id,
                File.upload_cleanup_at.is_(None),
            )
        )
        if file is None:
            raise HTTPException(status_code=404, detail="File not found")
        await self.require_read(actor, role, file)
        return self.read(actor, role, file)

    async def require_read(self, actor, role, file):
        await PermissionService(self.db).require_file(actor, role, file)

    async def rename(self, actor, file_id, name, ip):
        from app.services.accounts import AccountService

        await AccountService(self.db).limit("file-rename", ip, str(actor.id))
        role = await self.folders.authorize(actor, write=True)
        file = await self.db.scalar(
            select(File).where(
                File.id == file_id,
                File.tenant_id == actor.tenant_id,
                File.upload_cleanup_at.is_(None),
            )
        )
        if file is None:
            raise HTTPException(404, "File not found")
        await self.require_read(actor, role, file)
        if not PermissionService.writes(actor, role, file):
            raise HTTPException(403, "Editor access required")
        if file.status != "uploaded":
            raise HTTPException(409, "Only completed files can be renamed")
        file.name, file.name_key = name, name.casefold()
        try:
            await self.db.commit()
            await self.db.refresh(file)
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(409, "File metadata conflict") from None
        await PermissionService(self.db).mark(actor, [file])
        return self.read(actor, role, file)

    async def children(
        self, actor: User, folder_id: UUID | None, offset: int, limit: int
    ) -> FilePage:
        role = await self.folders.authorize(actor)
        await self.folders.ancestors(actor, folder_id)
        rows = list(
            await self.db.scalars(
                select(File)
                .where(
                    PermissionService.file_read(actor, role),
                    File.folder_id == folder_id,
                    File.upload_cleanup_at.is_(None),
                )
                .order_by(File.name, File.id)
                .offset(offset)
                .limit(limit + 1)
            )
        )
        await PermissionService(self.db).mark(actor, rows[:limit])
        return FilePage(
            items=[self.read(actor, role, file) for file in rows[:limit]],
            offset=offset,
            limit=limit,
            has_more=len(rows) > limit,
        )

    async def reserve(self, actor: User, payload: FileMetadataCreate) -> FileRead:
        """Internal pending reservation. UploadService coordinates public uploads."""
        role = await self.folders.authorize(actor, write=True)
        file = await self.allocate(actor, role, payload)
        try:
            await self.db.commit()
            await self.db.refresh(file)
        except IntegrityError as error:
            await self.db.rollback()
            raise HTTPException(status_code=409, detail="File metadata conflict") from error
        return self.read(actor, role, file)

    async def allocate(self, actor: User, role: UserRole, payload: FileMetadataCreate) -> File:
        """Caller must hold the tenant write lock and have rechecked membership."""
        path = await self.folders.ancestors(actor, payload.folder_id)
        if path:
            await self.folders.require_write(actor, role, path[-1])
        if (
            await self.db.scalar(
                select(File.id).where(
                    File.tenant_id == actor.tenant_id,
                    File.folder_id == payload.folder_id,
                    File.name_key == payload.name.casefold(),
                    File.trash_id.is_(None),
                    File.upload_cleanup_at.is_(None),
                )
            )
            is not None
        ):
            raise HTTPException(status_code=409, detail="A file with this name already exists here")
        file = File(
            tenant_id=actor.tenant_id,
            created_by=actor.id,
            name_key=payload.name.casefold(),
            **payload.model_dump(),
        )
        self.db.add(file)
        return file
