"""Bounded, retryable trash maintenance; invoked by the Compose cleanup worker."""

import argparse
import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import or_, select

from app.core.config import settings
from app.core.database import async_session_maker
from app.models import TrashEntry
from app.services.trash_cleanup import TrashCleanupService
from app.storage.s3 import S3ObjectStorage

logger = logging.getLogger(__name__)


async def tick(factory=async_session_maker, *, limit=10, report=None):
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("Invalid trash batch size")
    now = datetime.now(UTC)
    async with factory() as db:
        candidates = list(
            await db.execute(
                select(TrashEntry.id, TrashEntry.tenant_id)
                .where(
                    TrashEntry.restored_at.is_(None),
                    or_(TrashEntry.purge_requested_at.is_not(None), TrashEntry.retain_until <= now),
                )
                .order_by(
                    TrashEntry.checked_at.asc().nullsfirst(), TrashEntry.trashed_at, TrashEntry.id
                )
                .limit(limit)
            )
        )
    for entry_id, tenant_id in candidates:
        storage = S3ObjectStorage(settings, tenant_id)
        try:
            async with factory() as db:
                result = await TrashCleanupService(db, storage).sweep(entry_id, tenant_id, now)
                if report is not None:
                    report["inspected"] = report.get("inspected", 0) + 1
                    report["deferred"] = report.get("deferred", 0) + (not result)
        finally:
            await storage.close()
    logger.info("Trash maintenance checked %s batches", len(candidates))


async def main(once=False):
    while True:
        try:
            await tick()
        except Exception:
            logger.error("Trash maintenance unavailable; references retained")
            if once:
                raise RuntimeError("Trash maintenance failed") from None
        if once:
            return
        await asyncio.sleep(settings.UPLOAD_CLEANUP_INTERVAL_SECONDS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main(parser.parse_args().once))
