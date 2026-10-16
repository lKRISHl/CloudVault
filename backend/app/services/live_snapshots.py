"""Read bounded authorized state; emit opaque change signals, never names or file bytes.

Database observation intentionally coalesces transitions. This is not a durable event log.
No provider reads, presigned grants, native rendering or mutation runs in this service.
"""

import hashlib
import json

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select

from app.models import File, FileVersion, VersionPart
from app.models.upload_part import UploadPart
from app.services.files import FileService
from app.services.folders import FolderService
from app.services.organizations import OrganizationService
from app.services.permissions import PermissionService
from app.services.preview_jobs import PreviewJobService
from app.services.search import FileSearchService
from app.services.shares import ShareService
from app.services.trash import TrashService
from app.services.versions import VersionService
from app.services.workspaces import WorkspaceService


def digest(value):
    return hashlib.sha256(
        json.dumps(jsonable_encoder(value), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class LiveSnapshots:
    def __init__(self, db):
        self.db = db

    async def observe(self, actor, topic):
        if actor.tenant_id is None and topic.kind != "workspaces":
            raise HTTPException(403, "Select a workspace")
        progress = []
        if topic.kind == "folders":
            value = await FolderService(self.db).children(actor, topic.parent_id, topic.offset, 25)
        elif topic.kind == "files":
            value = await FileService(self.db).children(actor, topic.parent_id, topic.offset, 25)
            # Receipt counts belong only to this principal's visible pending originals.
            own = [
                row.id
                for row in value.items
                if row.status == "pending" and row.created_by == actor.id
            ]
            if own:
                rows = await self.db.execute(
                    select(UploadPart.file_id, func.sum(UploadPart.size_bytes))
                    .join(File, File.id == UploadPart.file_id)
                    .where(
                        UploadPart.file_id.in_(own),
                        File.tenant_id == actor.tenant_id,
                        File.created_by == actor.id,
                        UploadPart.confirmed_at.is_not(None),
                    )
                    .group_by(UploadPart.file_id)
                )
                amounts = dict(rows.all())
                progress = [{"id": str(fid), "bytes": int(amounts.get(fid, 0))} for fid in own]
        elif topic.kind == "file":
            value = await FileService(self.db).details(actor, topic.resource_id)
        elif topic.kind == "version":
            versions = VersionService(self.db)
            file, _ = await versions.access(actor, topic.resource_id)
            version = await versions.find(actor, file, topic.version_id)
            if version.status != "uploaded" and version.created_by != actor.id:
                raise HTTPException(404, "Version not found")
            value = versions.read(version, file, actor)
        elif topic.kind == "versions":
            value = await VersionService(self.db).listing(actor, topic.resource_id, topic.offset)
            own = [
                row.id
                for row in value.items
                if row.status == "pending" and row.created_by == actor.id
            ]
            if own:
                rows = await self.db.execute(
                    select(VersionPart.version_id, func.sum(VersionPart.size_bytes))
                    .join(FileVersion, FileVersion.id == VersionPart.version_id)
                    .where(
                        VersionPart.version_id.in_(own),
                        FileVersion.tenant_id == actor.tenant_id,
                        FileVersion.created_by == actor.id,
                        VersionPart.confirmed_at.is_not(None),
                    )
                    .group_by(VersionPart.version_id)
                )
                amounts = dict(rows.all())
                progress = [{"id": str(vid), "bytes": int(amounts.get(vid, 0))} for vid in own]
        elif topic.kind == "members":
            value = await OrganizationService(self.db).members(actor, 25, topic.offset)
        elif topic.kind == "invitations":
            value = await OrganizationService(self.db).invitations(actor, 25, topic.offset)
        elif topic.kind == "workspaces":
            value = await WorkspaceService(self.db).list(actor, topic.offset, 25)
        elif topic.kind == "trash":
            value = await TrashService(self.db).listing(actor, topic.offset)
        elif topic.kind == "permissions":
            value = await PermissionService(self.db).listing(
                actor, topic.resource_kind, topic.resource_id, topic.offset
            )
        elif topic.kind == "shares":
            value = await ShareService(self.db).listing(
                actor, topic.resource_id, topic.offset, kind=topic.resource_kind or "files"
            )
        elif topic.kind == "search":
            value = await FileSearchService(self.db).search(actor, topic.search, observe=True)
        else:
            previews = PreviewJobService(self.db)
            job = await previews.owned(actor, topic.resource_id, topic.job_id)
            await previews.authority(job)
            value = {"state": job.state, "expires_at": job.expires_at, "digest": job.digest}
        return digest({"value": value, "progress": progress}), progress
