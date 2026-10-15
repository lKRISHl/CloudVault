from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, literal, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models import File, FileVersion, Folder, TrashEntry, UserRole
from app.schemas.trash import RestoreRequest, TrashPage, TrashRead
from app.services.accounts import AccountService
from app.services.folders import FolderService
from app.services.permissions import PermissionService
from app.services.uploads import utc


def subtree(tenant_id, root_id):
    tree = (
        select(Folder.id, literal(1).label("depth"))
        .where(
            Folder.tenant_id == tenant_id,
            Folder.id == root_id,
        )
        .cte("trash_subtree", recursive=True)
    )
    tree = tree.union_all(
        select(Folder.id, tree.c.depth + 1)
        .join(tree, Folder.parent_id == tree.c.id)
        .where(
            Folder.tenant_id == tenant_id,
            tree.c.depth < 64,
        )
    )
    return select(tree.c.id)


def file_scope(entry):
    if entry.kind == "files":
        return File.id == entry.root_id
    return File.folder_id.in_(subtree(entry.tenant_id, entry.root_id))


class TrashService:
    def __init__(self, db):
        self.db = db
        self.folders = FolderService(db)
        self.permissions = PermissionService(db)

    @staticmethod
    def read(entry, name):
        return TrashRead(
            id=entry.id,
            resource_id=entry.root_id,
            kind=entry.kind,
            name=name,
            trashed_at=entry.trashed_at,
            retain_until=entry.retain_until,
            not_before=entry.not_before,
            purge_requested_at=entry.purge_requested_at,
        )

    async def parent_write(self, actor, role, resource):
        parent_id = resource.folder_id if isinstance(resource, File) else resource.parent_id
        path = await self.folders.ancestors(actor, parent_id)
        if path:
            await self.folders.require_write(actor, role, path[-1])

    async def require_subtree_owner(self, actor, role, folder_id):
        if role in (UserRole.OWNER, UserRole.ADMIN):
            return
        ids = subtree(actor.tenant_id, folder_id)
        others = await self.db.scalar(
            select(
                exists().where(
                    Folder.tenant_id == actor.tenant_id,
                    Folder.id.in_(ids),
                    Folder.created_by != actor.id,
                    or_(
                        Folder.trash_id.is_(None),
                        Folder.trash_id.in_(
                            select(TrashEntry.id).where(TrashEntry.purged_at.is_(None))
                        ),
                    ),
                )
            )
        ) or await self.db.scalar(
            select(
                exists().where(
                    File.tenant_id == actor.tenant_id,
                    File.folder_id.in_(ids),
                    File.created_by != actor.id,
                    File.upload_cleanup_at.is_(None),
                    File.object_purged_at.is_(None),
                )
            )
        )
        if others:
            raise HTTPException(
                403, "Workspace managers must handle folders containing other creators' resources"
            )

    async def move_to_trash(self, actor, kind, resource_id, ip, cancel_uploads=False):
        await AccountService(self.db).limit(
            "trash-mutate", ip, str(actor.id), max_identity=100, max_ip=500
        )
        resource = await self.permissions.managed(actor, kind, resource_id, write=True)
        role = await self.folders.authorize(actor)
        await self.parent_write(actor, role, resource)
        scope = File.id == resource_id
        if kind == "folders":
            await self.require_subtree_owner(actor, role, resource_id)
            scope = File.folder_id.in_(subtree(actor.tenant_id, resource_id))
        files = list(
            await self.db.scalars(
                select(File).where(
                    File.tenant_id == actor.tenant_id,
                    scope,
                    File.trash_id.is_(None),
                    File.upload_cleanup_at.is_(None),
                )
            )
        )
        pending = [file for file in files if file.status != "uploaded"]
        if pending and not cancel_uploads:
            raise HTTPException(
                409, "Finish uploads or wait for cancelled-upload cleanup before trashing"
            )
        if len(pending) > 100:
            raise HTTPException(
                409,
                "At most 100 pending transfers can be cancelled per folder operation; "
                "handle smaller subfolders first",
            )
        now = datetime.now(UTC)
        for file in pending:
            file.upload_cancelled_at = file.upload_cancelled_at or now
            if file.upload_method == "multipart":
                file.multipart_state = "aborted"
            if file.object_id is None:
                from app.models import UploadIntent

                if await self.db.get(UploadIntent, file.id) or await self.db.scalar(
                    select(FileVersion.id).where(FileVersion.file_id == file.id)
                ):
                    raise HTTPException(
                        409,
                        "Legacy metadata has retained upload references; "
                        "operator reconciliation required",
                    )
                file.upload_cleanup_at = now
        latest = await self.db.scalar(
            select(func.max(File.upload_expires_at)).where(
                File.tenant_id == actor.tenant_id,
                scope,
            )
        )
        deadline = max(now, utc(latest)) if latest else now
        version_deadline = await self.db.scalar(
            select(func.max(FileVersion.upload_expires_at)).where(
                FileVersion.tenant_id == actor.tenant_id,
                FileVersion.file_id.in_(
                    select(File.id).where(File.tenant_id == actor.tenant_id, scope)
                ),
            )
        )
        if version_deadline:
            deadline = max(deadline, utc(version_deadline))
        entry = TrashEntry(
            tenant_id=actor.tenant_id,
            root_id=resource_id,
            kind=kind,
            trashed_by=actor.id,
            trashed_at=now,
            retain_until=now + timedelta(days=30),
            not_before=deadline
            + timedelta(
                seconds=settings.UPLOAD_COMPLETION_GRACE_SECONDS
                + settings.UPLOAD_CLEANUP_SETTLE_SECONDS
            ),
        )
        self.db.add(entry)
        await self.db.flush()
        await self.permissions.invalidate_shares(actor, kind, resource_id)
        for file in files:
            file.trash_id = entry.id
        if kind == "folders":
            await self.db.execute(
                update(Folder)
                .where(
                    Folder.tenant_id == actor.tenant_id,
                    Folder.id.in_(subtree(actor.tenant_id, resource_id)),
                    Folder.trash_id.is_(None),
                )
                .values(trash_id=entry.id)
                .execution_options(synchronize_session=False)
            )
        await self.db.commit()
        return self.read(entry, resource.name)

    def permitted(self, actor, role, model):
        manages = (
            literal(True)
            if role in (UserRole.OWNER, UserRole.ADMIN)
            else model.created_by == actor.id
        )
        if model is File:
            return and_(manages, PermissionService.file_read(actor, role, include_trash=True))
        return and_(
            manages,
            Folder.tenant_id == actor.tenant_id,
            Folder.id.in_(PermissionService.visible_folders(actor, role, include_trash=True)),
        )

    async def listing(self, actor, offset):
        role = await self.folders.authorize(actor)
        # A union keeps authorization before global ordering and pagination for both resource types.
        parts = []
        for kind, model in (("files", File), ("folders", Folder)):
            parts.append(
                select(
                    TrashEntry.id.label("entry_id"), model.name.label("name"), TrashEntry.trashed_at
                )
                .join(
                    model,
                    and_(
                        model.id == TrashEntry.root_id,
                        model.tenant_id == TrashEntry.tenant_id,
                        model.trash_id == TrashEntry.id,
                    ),
                )
                .where(
                    TrashEntry.tenant_id == actor.tenant_id,
                    TrashEntry.kind == kind,
                    TrashEntry.purged_at.is_(None),
                    TrashEntry.restored_at.is_(None),
                    self.permitted(actor, role, model),
                )
            )
        allowed = parts[0].union_all(parts[1]).subquery()
        rows = list(
            await self.db.execute(
                select(TrashEntry, allowed.c.name)
                .join(
                    allowed,
                    allowed.c.entry_id == TrashEntry.id,
                )
                .order_by(TrashEntry.trashed_at.desc(), TrashEntry.id.desc())
                .offset(offset)
                .limit(26)
            )
        )
        return TrashPage(
            items=[self.read(entry, name) for entry, name in rows[:25]],
            offset=offset,
            has_more=len(rows) > 25,
        )

    async def entry(self, actor, entry_id):
        role = await self.folders.authorize(actor, write=True)
        entry = await self.db.scalar(
            select(TrashEntry).where(
                TrashEntry.id == entry_id,
                TrashEntry.tenant_id == actor.tenant_id,
                TrashEntry.purged_at.is_(None),
                TrashEntry.restored_at.is_(None),
            )
        )
        if entry is None:
            raise HTTPException(404, "Trash entry not found")
        model = File if entry.kind == "files" else Folder
        resource = await self.db.scalar(
            select(model).where(
                model.id == entry.root_id,
                model.tenant_id == actor.tenant_id,
                model.trash_id == entry.id,
                self.permitted(actor, role, model),
            )
        )
        if resource is None:
            raise HTTPException(404, "Trash entry not found")
        return entry, resource, role

    async def restore(self, actor, entry_id, ip, payload=None):
        await AccountService(self.db).limit(
            "trash-mutate", ip, str(actor.id), max_identity=100, max_ip=500
        )
        entry, resource, role = await self.entry(actor, entry_id)
        if entry.purge_requested_at or utc(entry.retain_until) <= datetime.now(UTC):
            raise HTTPException(409, "Retention expired or permanent deletion has begun")
        payload = payload or RestoreRequest()
        parent_id = resource.folder_id if entry.kind == "files" else resource.parent_id
        destination = parent_id if payload.use_original else payload.destination_id
        path = await self.folders.ancestors(actor, destination)
        if path:
            await self.folders.require_write(actor, role, path[-1])
        if entry.kind == "folders":
            await self.require_subtree_owner(actor, role, resource.id)
            ids = subtree(actor.tenant_id, resource.id).subquery()
            if destination is not None and await self.db.scalar(
                select(ids.c.id).where(ids.c.id == destination)
            ):
                raise HTTPException(409, "Cannot restore a folder inside its own subtree")
            tree = (
                select(Folder.id, literal(1).label("depth"))
                .where(Folder.id == resource.id, Folder.tenant_id == actor.tenant_id)
                .cte("restore_height", recursive=True)
            )
            tree = tree.union_all(
                select(Folder.id, tree.c.depth + 1)
                .join(tree, Folder.parent_id == tree.c.id)
                .where(Folder.tenant_id == actor.tenant_id, tree.c.depth < 65)
            )
            height = await self.db.scalar(select(func.max(tree.c.depth)))
            if len(path) + height > 64:
                raise HTTPException(409, "Maximum folder depth exceeded")
        if entry.kind == "files":
            resource.folder_id = destination
        else:
            resource.parent_id = destination
        if payload.name is not None:
            resource.name, resource.name_key = payload.name, payload.name.casefold()
        # A parent is restored first. Clearing only this batch never resurrects older trash.
        try:
            for model in (File, Folder):
                await self.db.execute(
                    update(model)
                    .where(model.tenant_id == actor.tenant_id, model.trash_id == entry.id)
                    .values(trash_id=None)
                    .execution_options(synchronize_session=False)
                )
            entry.restored_at = datetime.now(UTC)
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                409,
                "Original names are occupied; choose another destination or name before restoring",
            ) from None

    async def purge(self, actor, entry_id, ip):
        await AccountService(self.db).limit(
            "trash-mutate", ip, str(actor.id), max_identity=100, max_ip=500
        )
        entry, resource, role = await self.entry(actor, entry_id)
        if entry.kind == "folders":
            await self.require_subtree_owner(actor, role, resource.id)
        await queue_purge(self.db, entry, datetime.now(UTC))
        await self.db.commit()


async def queue_purge(db, entry, now):
    scope = TrashEntry.id == entry.id
    if entry.kind == "folders":
        ids = subtree(entry.tenant_id, entry.root_id)
        scope = or_(
            scope,
            and_(TrashEntry.kind == "folders", TrashEntry.root_id.in_(ids)),
            and_(
                TrashEntry.kind == "files",
                TrashEntry.root_id.in_(
                    select(File.id).where(
                        File.tenant_id == entry.tenant_id, File.folder_id.in_(ids)
                    )
                ),
            ),
        )
    await db.execute(
        update(TrashEntry)
        .where(
            TrashEntry.tenant_id == entry.tenant_id,
            scope,
            TrashEntry.purge_requested_at.is_(None),
            TrashEntry.restored_at.is_(None),
        )
        .values(purge_requested_at=now)
        .execution_options(synchronize_session=False)
    )
