from sqlalchemy import select

from app.models import FileVersion
from app.models.file_version import CONTENT_FIELDS


async def record_initial(db, file):
    """Called in the upload transaction; an existing content snapshot is never mutated."""
    if file.status != "uploaded":
        return
    exists = await db.scalar(select(FileVersion.id).where(FileVersion.file_id == file.id))
    if exists:
        return
    db.add(
        FileVersion(
            tenant_id=file.tenant_id,
            file_id=file.id,
            number=1,
            base_generation=1,
            created_by=file.created_by,
            request_id=file.upload_request_id,
            status="uploaded",
            **{field: getattr(file, field) for field in CONTENT_FIELDS},
            purged_at=file.object_purged_at,
        )
    )
