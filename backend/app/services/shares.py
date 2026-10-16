import asyncio
import hashlib
import json
import secrets
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import literal, select, text, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, hash_refresh_token, verify_password
from app.models import File, Folder, Membership, ShareLink, Tenant, User, UserRole
from app.schemas.shares import (
    ShareAccess,
    ShareCreate,
    ShareCreated,
    SharedDownload,
    SharedEntry,
    SharedFile,
    SharedFolder,
    SharePage,
    ShareRead,
)
from app.services.accounts import AccountService
from app.services.downloads import DownloadService
from app.services.files import FileService
from app.services.permissions import PermissionService
from app.storage.base import ObjectStorage


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ShareService:
    def __init__(
        self,
        db: AsyncSession,
        storage: ObjectStorage | None = None,
        storage_factory: Callable[[UUID], AbstractAsyncContextManager[ObjectStorage]] | None = None,
    ):
        self.db, self.storage = db, storage
        self.storage_factory = storage_factory
        self.files = FileService(db)

    @staticmethod
    def read(link: ShareLink) -> ShareRead:
        return ShareRead(
            **{
                key: getattr(link, key)
                for key in ShareRead.model_fields
                if key != "password_required"
            },
            password_required=bool(link.password_hash),
        )

    async def managed_file(self, actor: User, file_id: UUID, write=False) -> File:
        role = await self.files.folders.authorize(actor, write=write)
        file = await self.db.scalar(
            select(File).where(
                File.id == file_id,
                File.tenant_id == actor.tenant_id,
                File.upload_cleanup_at.is_(None),
            )
        )
        if file is None:
            raise HTTPException(404, "File not found")
        await self.files.require_read(actor, role, file)
        if role not in (UserRole.OWNER, UserRole.ADMIN) and not PermissionService.manages(
            actor, role, file
        ):
            raise HTTPException(
                403, "Only the file owner or workspace managers can share this file"
            )
        await self.files.folders.ancestors(actor, file.folder_id)
        if file.status != "uploaded":
            raise HTTPException(409, "Only completed files can be shared")
        return file

    async def create(
        self, actor: User, file_id: UUID, payload: ShareCreate, ip: str, kind="files"
    ) -> ShareCreated:
        await AccountService(self.db).limit("share-create", ip, str(actor.id))
        password_hash = (
            await asyncio.to_thread(hash_password, payload.password) if payload.password else None
        )
        if kind == "files":
            file = await self.managed_file(actor, file_id, write=True)
            from app.services.scans import require_released

            await require_released(self.db, file)
        else:
            await PermissionService(self.db).managed(actor, kind, file_id, write=True)
        raw = payload.token or secrets.token_urlsafe(32)
        # Replay proves possession of the original client secret; only its digest is persisted.
        options = payload.model_dump(mode="json", exclude={"token", "password", "request_id"})
        fingerprint = hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()
        if payload.request_id:
            existing = await self.db.scalar(
                select(ShareLink).where(
                    ShareLink.tenant_id == actor.tenant_id,
                    ShareLink.created_by == actor.id,
                    ShareLink.request_id == payload.request_id,
                )
            )
            if existing:
                same_password = (not existing.password_hash and not payload.password) or (
                    existing.password_hash
                    and payload.password
                    and await asyncio.to_thread(
                        verify_password, payload.password, existing.password_hash
                    )
                )
                if (
                    existing.file_id != (file_id if kind == "files" else None)
                    or existing.folder_id != (file_id if kind == "folders" else None)
                    or existing.token_hash != hash_refresh_token(raw)
                    or existing.request_fingerprint != fingerprint
                    or not same_password
                ):
                    raise HTTPException(409, "Creation request already used with different options")
                return ShareCreated(
                    **self.read(existing).model_dump(),
                    share_url=f"{settings.FRONTEND_URL}/share#token={raw}",
                )
        link = ShareLink(
            file_id=file_id if kind == "files" else None,
            folder_id=file_id if kind == "folders" else None,
            recipient_email=str(payload.recipient_email).lower()
            if payload.recipient_email
            else None,
            request_id=payload.request_id,
            request_fingerprint=fingerprint,
            tenant_id=actor.tenant_id,
            created_by=actor.id,
            token_hash=hash_refresh_token(raw),
            password_hash=password_hash,
            expires_at=datetime.now(UTC) + timedelta(hours=payload.expires_in_hours),
            allow_download=payload.allow_download,
            max_downloads=payload.max_downloads,
        )
        self.db.add(link)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                409, "Share creation conflicts with an existing request or token"
            ) from None
        await self.db.refresh(link)
        return ShareCreated(
            **self.read(link).model_dump(),
            share_url=f"{settings.FRONTEND_URL.rstrip('/')}/share#token={raw}",
        )

    async def listing(self, actor: User, file_id: UUID, offset: int, kind="files") -> SharePage:
        file = (
            await self.managed_file(actor, file_id)
            if kind == "files"
            else await PermissionService(self.db).managed(actor, kind, file_id)
        )
        column = ShareLink.file_id if kind == "files" else ShareLink.folder_id
        rows = list(
            await self.db.scalars(
                select(ShareLink)
                .where(
                    column == file_id,
                    ShareLink.tenant_id == actor.tenant_id,
                )
                .order_by(ShareLink.created_at.desc(), ShareLink.id.desc())
                .offset(offset)
                .limit(26)
            )
        )
        return SharePage(
            file_name=file.name,
            items=[self.read(link) for link in rows[:25]],
            offset=offset,
            has_more=len(rows) > 25,
        )

    async def revoke(self, actor: User, file_id: UUID, link_id: UUID, ip: str, kind="files"):
        await AccountService(self.db).limit("share-revoke", ip, str(actor.id))
        if kind == "files":
            await self.managed_file(actor, file_id, write=True)
        else:
            await PermissionService(self.db).managed(actor, kind, file_id, write=True)
        column = ShareLink.file_id if kind == "files" else ShareLink.folder_id
        link = await self.db.scalar(
            select(ShareLink).where(
                ShareLink.id == link_id,
                column == file_id,
                ShareLink.tenant_id == actor.tenant_id,
            )
        )
        if link is None:
            raise HTTPException(404, "Share link not found")
        link.revoked_at = link.revoked_at or datetime.now(UTC)
        await self.db.commit()

    async def access(
        self, payload: ShareAccess, ip: str, download=False, recipient=None, browse=False
    ) -> SharedFile | SharedDownload | SharedFolder:
        digest = hash_refresh_token(payload.token)
        # Persist budgets before checking any secret or doing expensive password work.
        await AccountService(self.db).limit(
            "share-public", ip, digest, max_identity=100, max_ip=100
        )
        denied = HTTPException(404, "Share unavailable or credentials incorrect")
        if self.db.bind.dialect.name == "sqlite":
            await self.db.execute(text("BEGIN IMMEDIATE"))
        link = await self.db.scalar(select(ShareLink).where(ShareLink.token_hash == digest))
        if link is None:
            raise denied
        # All grants and mutations serialize with tenant membership/removal writes.
        await self.db.scalar(select(Tenant.id).where(Tenant.id == link.tenant_id).with_for_update())
        await self.db.refresh(link)
        if link.recipient_email:
            recipient = (
                None
                if recipient is None
                else await self.db.scalar(
                    select(User)
                    .where(
                        User.id == recipient.id,
                        User.is_active.is_(True),
                        User.deleted_at.is_(None),
                        User.email_verified.is_(True),
                    )
                    .execution_options(populate_existing=True)
                )
            )
            if recipient is None or recipient.email.lower() != link.recipient_email:
                raise denied
            from app.services.auth import AuthService

            if not await AuthService(self.db).valid_session(
                recipient.id,
                getattr(recipient, "_share_session_id", None),
                getattr(recipient, "_share_tenant_id", None),
            ):
                raise denied
        file = await self.db.scalar(
            select(File).where(
                File.id == (payload.file_id if link.folder_id else link.file_id),
                File.tenant_id == link.tenant_id,
                File.status == "uploaded",
                File.upload_cleanup_at.is_(None),
            )
        )
        publisher_role = await self.db.scalar(
            select(Membership.role)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.tenant_id == link.tenant_id,
                Membership.user_id == link.created_by,
                Membership.revoked_at.is_(None),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                User.email_verified.is_(True),
            )
        )
        if (
            link.revoked_at
            or utc(link.expires_at) <= datetime.now(UTC)
            or (link.file_id is not None and file is None)
            or publisher_role is None
        ):
            raise denied
        if link.password_hash and not await asyncio.to_thread(
            verify_password, payload.password, link.password_hash
        ):
            raise denied
        from types import SimpleNamespace

        publisher = SimpleNamespace(id=link.created_by, tenant_id=link.tenant_id)
        try:
            permissions = PermissionService(self.db)
            if link.folder_id:
                root = await self.db.get(Folder, link.folder_id)
                if root is None:
                    raise denied
                await permissions.require_folder(publisher, publisher_role, root)
                if not permissions.manages(publisher, publisher_role, root):
                    raise denied
                current_id = (
                    file.folder_id if download and file else (payload.folder_id or link.folder_id)
                )
                current = await self.shared_folder(
                    publisher, publisher_role, current_id, link.folder_id
                )
                if not download:
                    return await self.folder_page(
                        publisher, publisher_role, current, link, payload.offset
                    )
                if file is None:
                    raise denied
            elif (
                browse or payload.folder_id or (payload.file_id and payload.file_id != link.file_id)
            ):
                raise denied
            await permissions.require_file(publisher, publisher_role, file)
            if link.file_id and not permissions.manages(publisher, publisher_role, file):
                raise denied
            from app.services.scans import require_released

            await require_released(self.db, file)
        except HTTPException:
            raise denied from None
        if utc(link.expires_at) <= datetime.now(UTC):
            raise denied
        remaining = (
            None
            if link.max_downloads is None
            else max(0, link.max_downloads - link.download_grants)
        )
        if not download:
            return SharedFile(
                name=file.name,
                size_bytes=file.size_bytes,
                expires_at=link.expires_at,
                allow_download=link.allow_download and remaining != 0,
                grants_remaining=remaining,
            )
        if not link.allow_download or remaining == 0:
            raise HTTPException(403, "Downloads disabled or grant limit reached")
        issued = datetime.now(UTC)
        ttl = min(
            settings.DOWNLOAD_URL_SECONDS, int((utc(link.expires_at) - issued).total_seconds())
        )
        if ttl < 1:
            raise denied
        if self.storage is not None:
            url = await DownloadService(self.db, self.storage).checked_url(
                file, ttl, deadline=utc(link.expires_at)
            )
        else:
            async with self.storage_factory(link.tenant_id) as storage:
                url = await DownloadService(self.db, storage).checked_url(
                    file, ttl, deadline=utc(link.expires_at)
                )
        # Provider operations may take time. Never return an already-expired share.
        if utc(link.expires_at) <= datetime.now(UTC):
            raise denied
        link.download_grants += 1
        await self.db.commit()
        return SharedDownload(
            download_url=url, expires_at=issued + timedelta(seconds=ttl), name=file.name
        )

    async def shared_folder(self, publisher, role, current_id, root_id):
        """Current ancestry, never a stale saved subtree or a path supplied by a guest."""
        current = None
        seen = set()
        while current_id is not None and len(seen) < 64 and current_id not in seen:
            seen.add(current_id)
            folder = await self.db.scalar(
                select(Folder).where(
                    Folder.id == current_id, Folder.tenant_id == publisher.tenant_id
                )
            )
            if folder is None:
                break
            await PermissionService(self.db).require_folder(publisher, role, folder)
            current = current or folder
            if folder.id == root_id:
                return current
            current_id = folder.parent_id
        raise HTTPException(404, "Share unavailable or credentials incorrect")

    async def folder_page(self, publisher, role, folder, link, offset):
        permissions = PermissionService(self.db)
        folders = select(
            Folder.id.label("id"),
            Folder.name.label("name"),
            literal("folder").label("kind"),
            literal(None).label("size_bytes"),
        ).where(
            Folder.tenant_id == link.tenant_id,
            Folder.parent_id == folder.id,
            Folder.id.in_(permissions.visible_folders(publisher, role)),
        )
        files = select(File.id, File.name, literal("file"), File.size_bytes).where(
            File.folder_id == folder.id,
            permissions.file_read(publisher, role),
            File.status == "uploaded",
            File.scan_status == "clean",
        )
        entries = union_all(folders, files).subquery()
        rows = list(
            (
                await self.db.execute(
                    select(entries)
                    .order_by(entries.c.name, entries.c.id, entries.c.kind)
                    .offset(offset)
                    .limit(26)
                )
            ).mappings()
        )
        safe_rows = []
        from app.services.scans import require_released

        for row in rows[:25]:
            if row["kind"] == "file":
                file = await self.db.get(File, row["id"])
                try:
                    await require_released(self.db, file)
                except HTTPException:
                    continue
            safe_rows.append(SharedEntry(**row))
        if utc(link.expires_at) <= datetime.now(UTC):
            raise HTTPException(404, "Share unavailable or credentials incorrect")
        return SharedFolder(
            name=folder.name,
            folder_id=folder.id,
            items=safe_rows,
            offset=offset,
            has_more=len(rows) > 25,
            expires_at=link.expires_at,
            allow_download=link.allow_download
            and (link.max_downloads is None or link.download_grants < link.max_downloads),
            grants_remaining=None
            if link.max_downloads is None
            else max(0, link.max_downloads - link.download_grants),
        )
