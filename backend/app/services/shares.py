import asyncio
import secrets
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, hash_refresh_token, verify_password
from app.models import File, Membership, ShareLink, Tenant, User, UserRole
from app.schemas.shares import (
    ShareAccess,
    ShareCreate,
    ShareCreated,
    SharedDownload,
    SharedFile,
    SharePage,
    ShareRead,
)
from app.services.accounts import AccountService
from app.services.downloads import DownloadService
from app.services.files import FileService
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
        if role not in (UserRole.OWNER, UserRole.ADMIN) and file.created_by != actor.id:
            raise HTTPException(
                403, "Only the file creator or workspace managers can share this file"
            )
        await self.files.folders.ancestors(actor, file.folder_id)
        if file.status != "uploaded":
            raise HTTPException(409, "Only completed files can be shared")
        return file

    async def create(
        self, actor: User, file_id: UUID, payload: ShareCreate, ip: str
    ) -> ShareCreated:
        await AccountService(self.db).limit("share-create", ip, str(actor.id))
        password_hash = (
            await asyncio.to_thread(hash_password, payload.password) if payload.password else None
        )
        await self.managed_file(actor, file_id, write=True)
        raw = secrets.token_urlsafe(32)
        link = ShareLink(
            file_id=file_id,
            tenant_id=actor.tenant_id,
            created_by=actor.id,
            token_hash=hash_refresh_token(raw),
            password_hash=password_hash,
            expires_at=datetime.now(UTC) + timedelta(hours=payload.expires_in_hours),
            allow_download=payload.allow_download,
            max_downloads=payload.max_downloads,
        )
        self.db.add(link)
        await self.db.commit()
        await self.db.refresh(link)
        return ShareCreated(
            **self.read(link).model_dump(),
            share_url=f"{settings.FRONTEND_URL.rstrip('/')}/share#token={raw}",
        )

    async def listing(self, actor: User, file_id: UUID, offset: int) -> SharePage:
        file = await self.managed_file(actor, file_id)
        rows = list(
            await self.db.scalars(
                select(ShareLink)
                .where(
                    ShareLink.file_id == file_id,
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

    async def revoke(self, actor: User, file_id: UUID, link_id: UUID, ip: str):
        await AccountService(self.db).limit("share-revoke", ip, str(actor.id))
        await self.managed_file(actor, file_id, write=True)
        link = await self.db.scalar(
            select(ShareLink).where(
                ShareLink.id == link_id,
                ShareLink.file_id == file_id,
                ShareLink.tenant_id == actor.tenant_id,
            )
        )
        if link is None:
            raise HTTPException(404, "Share link not found")
        link.revoked_at = link.revoked_at or datetime.now(UTC)
        await self.db.commit()

    async def access(
        self, payload: ShareAccess, ip: str, download=False
    ) -> SharedFile | SharedDownload:
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
        file = await self.db.scalar(
            select(File).where(
                File.id == link.file_id,
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
            or file is None
            or publisher_role is None
            or (
                publisher_role not in (UserRole.OWNER, UserRole.ADMIN)
                and file.created_by != link.created_by
            )
        ):
            raise denied
        if link.password_hash and not await asyncio.to_thread(
            verify_password, payload.password, link.password_hash
        ):
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
