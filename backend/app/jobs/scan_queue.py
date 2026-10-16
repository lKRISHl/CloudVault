"""One durable exact-version scan per argument-free maintenance hint."""

from app.core.config import settings
from app.scanning.clamd import ClamdScanner
from app.services.scans import ScanService
from app.storage.s3 import S3ObjectStorage


async def tick(factory):
    # Dependency outages must not exhaust a version's finite processing attempts.
    # Probe outside the DB transaction; process() still verifies freshness per scan.
    await ClamdScanner().version()
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
