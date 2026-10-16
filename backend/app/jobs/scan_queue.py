"""One durable exact-version scan per argument-free maintenance hint."""

from app.core.config import settings
from app.services.scans import ScanService
from app.storage.s3 import S3ObjectStorage


async def tick(factory):
    async with factory() as db:
        service = ScanService(db)
        job = await service.claim()
        if job is None:
            return "idle"
        storage = S3ObjectStorage(settings, job.tenant_id)
        try:
            service.storage = storage
            return await service.process(job)
        finally:
            await storage.close()
