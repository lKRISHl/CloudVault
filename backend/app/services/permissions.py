from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, literal, or_, select, update

from app.models import File, Folder, Membership, ResourceGrant, ShareLink, User, UserRole


class PermissionService:
    """Resource-local grants plus mandatory visibility of every containing folder."""

    def __init__(self, db):
        self.db = db

    @staticmethod
    def manages(actor, role, resource):
        return role in (UserRole.OWNER, UserRole.ADMIN) or resource.created_by == actor.id

    @staticmethod
    def writes(actor, role, resource):
        return PermissionService.manages(actor, role, resource) or getattr(
            resource, "_acl_editor", False
        )

    @staticmethod
    def local_read(model, actor, role):
        if role in (UserRole.OWNER, UserRole.ADMIN):
            return literal(True)
        resource_column = ResourceGrant.file_id if model is File else ResourceGrant.folder_id
        grant = (
            select(ResourceGrant.id)
            .where(
                ResourceGrant.tenant_id == actor.tenant_id,
                ResourceGrant.user_id == actor.id,
                resource_column == model.id,
            )
            .exists()
        )
        return or_(model.visibility == "workspace", model.created_by == actor.id, grant)

    @staticmethod
    def visible_folders(actor, role):
        local = PermissionService.local_read(Folder, actor, role)
        visible = (
            select(Folder.id, literal(1).label("depth"))
            .where(
                Folder.tenant_id == actor.tenant_id,
                Folder.parent_id.is_(None),
                local,
            )
            .cte("visible_folders", recursive=True)
        )
        visible = visible.union_all(
            select(Folder.id, (visible.c.depth + 1))
            .join(
                visible,
                Folder.parent_id == visible.c.id,
            )
            .where(Folder.tenant_id == actor.tenant_id, local, visible.c.depth < 64)
        )
        return select(visible.c.id)

    @staticmethod
    def file_read(actor, role):
        return and_(
            File.tenant_id == actor.tenant_id,
            File.upload_cleanup_at.is_(None),
            PermissionService.local_read(File, actor, role),
            or_(
                File.folder_id.is_(None),
                File.folder_id.in_(PermissionService.visible_folders(actor, role)),
            ),
        )

    async def mark(self, actor, resources):
        resources = list(resources)
        if not resources:
            return
        file_ids = [item.id for item in resources if isinstance(item, File)]
        folder_ids = [item.id for item in resources if isinstance(item, Folder)]
        rows = list(
            await self.db.scalars(
                select(ResourceGrant).where(
                    ResourceGrant.tenant_id == actor.tenant_id,
                    ResourceGrant.user_id == actor.id,
                    ResourceGrant.role == "editor",
                    or_(
                        ResourceGrant.file_id.in_(file_ids), ResourceGrant.folder_id.in_(folder_ids)
                    ),
                )
            )
        )
        editors = {(File if row.file_id else Folder, row.file_id or row.folder_id) for row in rows}
        for resource in resources:
            resource._acl_editor = (type(resource), resource.id) in editors

    async def require_file(self, actor, role, file):
        if not await self.db.scalar(
            select(File.id).where(File.id == file.id, self.file_read(actor, role))
        ):
            raise HTTPException(404, "File not found")
        await self.mark(actor, [file])

    async def require_folder(self, actor, role, folder):
        if not await self.db.scalar(
            select(Folder.id).where(
                Folder.id == folder.id,
                Folder.tenant_id == actor.tenant_id,
                Folder.id.in_(self.visible_folders(actor, role)),
            )
        ):
            raise HTTPException(404, "Folder not found")
        await self.mark(actor, [folder])

    async def managed(self, actor, kind, resource_id, write=False):
        # Lazy import keeps the shared read predicates independent of folder operations.
        from app.services.folders import FolderService

        folders = FolderService(self.db)
        role = await folders.authorize(actor, write=write)
        model = File if kind == "files" else Folder
        resource = await self.db.scalar(
            select(model).where(model.id == resource_id, model.tenant_id == actor.tenant_id)
        )
        if resource is None or (kind == "files" and resource.upload_cleanup_at is not None):
            raise HTTPException(404, "Resource not found")
        if kind == "files":
            await self.require_file(actor, role, resource)
        else:
            await self.require_folder(actor, role, resource)
        if not self.manages(actor, role, resource):
            raise HTTPException(
                403, "Only resource creators or workspace managers can manage permissions"
            )
        return resource

    async def listing(self, actor, kind, resource_id, offset):
        from app.schemas.permissions import GrantRead, PermissionPage

        resource = await self.managed(actor, kind, resource_id)
        column = ResourceGrant.file_id if kind == "files" else ResourceGrant.folder_id
        rows = list(
            await self.db.scalars(
                select(ResourceGrant)
                .join(
                    Membership,
                    and_(
                        Membership.tenant_id == ResourceGrant.tenant_id,
                        Membership.user_id == ResourceGrant.user_id,
                    ),
                )
                .where(
                    column == resource.id,
                    ResourceGrant.tenant_id == actor.tenant_id,
                    Membership.revoked_at.is_(None),
                )
                .order_by(ResourceGrant.user_id)
                .offset(offset)
                .limit(26)
            )
        )
        return PermissionPage(
            name=resource.name,
            visibility=resource.visibility,
            items=[GrantRead(user_id=row.user_id, role=row.role) for row in rows[:25]],
            offset=offset,
            has_more=len(rows) > 25,
        )

    async def invalidate_shares(self, actor, kind, resource_id):
        from datetime import UTC, datetime

        condition = ShareLink.file_id == resource_id
        if kind == "folders":
            subtree = (
                select(Folder.id, literal(1).label("depth"))
                .where(
                    Folder.id == resource_id,
                    Folder.tenant_id == actor.tenant_id,
                )
                .cte("changed_subtree", recursive=True)
            )
            subtree = subtree.union_all(
                select(Folder.id, subtree.c.depth + 1)
                .join(
                    subtree,
                    Folder.parent_id == subtree.c.id,
                )
                .where(Folder.tenant_id == actor.tenant_id, subtree.c.depth < 64)
            )
            condition = ShareLink.file_id.in_(
                select(File.id).where(
                    File.tenant_id == actor.tenant_id,
                    File.folder_id.in_(select(subtree.c.id)),
                )
            )
        await self.db.execute(
            update(ShareLink)
            .where(
                ShareLink.tenant_id == actor.tenant_id,
                condition,
                ShareLink.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )

    async def visibility(self, actor, kind, resource_id, visibility, ip):
        from app.services.accounts import AccountService

        await AccountService(self.db).limit(
            "resource-permissions", ip, str(actor.id), max_identity=100, max_ip=500
        )
        resource = await self.managed(actor, kind, resource_id, write=True)
        if resource.visibility != visibility:
            resource.visibility = visibility
            await self.invalidate_shares(actor, kind, resource_id)
        await self.db.commit()

    async def grant(self, actor, kind, resource_id, user_id: UUID, role, ip):
        from app.services.accounts import AccountService

        await AccountService(self.db).limit(
            "resource-permissions", ip, str(actor.id), max_identity=100, max_ip=500
        )
        await self.managed(actor, kind, resource_id, write=True)
        member = await self.db.scalar(
            select(Membership.user_id)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.tenant_id == actor.tenant_id,
                Membership.user_id == user_id,
                Membership.revoked_at.is_(None),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                User.email_verified.is_(True),
            )
        )
        if member is None:
            raise HTTPException(404, "Eligible workspace member not found")
        column = ResourceGrant.file_id if kind == "files" else ResourceGrant.folder_id
        row = await self.db.scalar(
            select(ResourceGrant).where(
                column == resource_id,
                ResourceGrant.tenant_id == actor.tenant_id,
                ResourceGrant.user_id == user_id,
            )
        )
        if role is None:
            if row is not None:
                await self.db.delete(row)
        elif row is not None:
            row.role = role
        else:
            self.db.add(
                ResourceGrant(
                    tenant_id=actor.tenant_id,
                    user_id=user_id,
                    role=role,
                    **{"file_id" if kind == "files" else "folder_id": resource_id},
                )
            )
        await self.invalidate_shares(actor, kind, resource_id)
        await self.db.commit()
