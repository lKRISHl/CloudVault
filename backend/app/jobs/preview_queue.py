"""One bounded render OR cleanup per durable rotation turn."""

from sqlalchemy import select

from app.core.config import settings
from app.models import PreviewJob
from app.services.background_jobs import storage_namespace
from app.services.preview_jobs import PreviewJobService
from app.storage.s3 import S3ObjectStorage


async def tick(factory, turn="render"):
    if turn not in ("render", "cleanup"):
        raise ValueError("Unknown preview turn")
    if turn == "cleanup":
        return await cleanup(factory)
    async with factory() as db:
        service = PreviewJobService(db)
        job = await service.claim()
        if job is None:
            return "idle"
        storage = S3ObjectStorage(settings, job.tenant_id)
        try:
            service.storage = storage
            return await service.process_next(job)
        finally:
            await storage.close()


async def cleanup(factory):
    from datetime import UTC, datetime

    async with factory() as db:
        row = await db.scalar(
            select(PreviewJob)
            .where(
                PreviewJob.cleanup_after <= datetime.now(UTC),
                PreviewJob.namespace == storage_namespace(),
            )
            .order_by(PreviewJob.checked_at.asc().nullsfirst(), PreviewJob.id)
            .limit(1)
        )
        if row:
            job_id, tenant_id = row.id, row.tenant_id
            await db.rollback()
            storage = S3ObjectStorage(settings, tenant_id)
            try:
                return await PreviewJobService(db, storage).cleanup_one(job_id=job_id)
            finally:
                await storage.close()
    return "idle"
