"""Periodic scoped upload cleanup, including old unknown initialization uploads."""

import argparse
import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_maker
from app.models import File, UploadIntent
from app.services.upload_cleanup import UploadCleanupService
from app.services.uploads import utc
from app.storage.base import ObjectRef, StorageError
from app.storage.s3 import S3ObjectStorage

logger = logging.getLogger(__name__)
KEY = re.compile(r"tenants/([^/]+)/files/([^/]+)/objects/([^/]+)")


def managed_ref(key):
    match = KEY.fullmatch(key)
    if not match:
        return None
    try:
        ref = ObjectRef(*(UUID(value) for value in match.groups()))
    except ValueError:
        return None
    return ref if ref.key == key else None


async def sweep_orphans(inventory, factory, marker=None, now=None):
    """One provider page per tick, with cursor advanced by the persistent worker."""
    now = now or datetime.now(UTC)
    params = {"Prefix": "", "MaxUploads": 100}
    if marker:
        params.update(KeyMarker=marker[0], UploadIdMarker=marker[1])
    page = await inventory.call(inventory.client.list_multipart_uploads, **params)
    # Static maximum permitted session + grace, independent of settings decreasing.
    cutoff = now - timedelta(seconds=7200 + 600 + settings.UPLOAD_CLEANUP_SETTLE_SECONDS)
    for upload in page.get("Uploads", []):
        ref = managed_ref(upload["Key"])
        if ref is None or utc(upload["Initiated"]) > cutoff:
            continue
        async with factory() as db:
            file = await db.scalar(
                select(File).where(File.tenant_id == ref.tenant_id, File.id == ref.file_id)
            )
            # Even expired known sessions are handled only by the locked tombstone sweeper.
            if (
                file is not None
                and file.object_id == ref.object_id
                and file.multipart_upload_id == upload["UploadId"]
            ):
                continue
        scoped = S3ObjectStorage(settings, ref.tenant_id)
        try:
            await scoped.abort_multipart(ref, upload["UploadId"])
        except StorageError:
            logger.warning("Orphan upload abort unavailable; future scan will retry")
        finally:
            await scoped.close()
    if page.get("IsTruncated"):
        next_marker = (page.get("NextKeyMarker", ""), page.get("NextUploadIdMarker", ""))
        if not next_marker[0] or next_marker == marker:
            raise StorageError("Invalid orphan pagination")
        return next_marker
    return None


async def tick(factory=async_session_maker, marker=None):
    if not settings.S3_BUCKET_NAME:
        return marker
    inventory = S3ObjectStorage(settings, uuid4())
    try:
        # Delete markers cannot prove reclamation; versioned providers fail closed.
        versioning = await inventory.call(inventory.client.get_bucket_versioning)
        if versioning.get("Status") in ("Enabled", "Suspended"):
            raise StorageError("Upload cleanup requires an unversioned bucket")
        now = datetime.now(UTC)
        async with factory() as db:
            candidates = list(
                await db.execute(
                    select(File.id, File.tenant_id)
                    .where(
                        File.status == "pending",
                        File.storage_bucket == settings.S3_BUCKET_NAME,
                        File.upload_expires_at <= UploadCleanupService.cutoff(now),
                    )
                    .order_by(
                        File.upload_cleanup_checked_at.asc().nullsfirst(),
                        File.upload_expires_at,
                        File.id,
                    )
                    .limit(50)
                )
            )
        cleaned = 0
        for file_id, tenant_id in candidates:
            scoped = S3ObjectStorage(settings, tenant_id)
            try:
                async with factory() as db:
                    cleaned += await UploadCleanupService(db, scoped).sweep(file_id, tenant_id, now)
            finally:
                await scoped.close()
        async with factory() as db:
            intents = list(
                await db.scalars(
                    select(UploadIntent)
                    .where(
                        UploadIntent.storage_bucket == settings.S3_BUCKET_NAME,
                        UploadIntent.expires_at <= UploadCleanupService.cutoff(now),
                    )
                    .order_by(UploadIntent.checked_at.asc().nullsfirst(), UploadIntent.expires_at)
                    .limit(50)
                )
            )
        for intent in intents:
            scoped = S3ObjectStorage(settings, intent.tenant_id)
            try:
                async with factory() as db:
                    file = await db.scalar(
                        select(File).where(
                            File.id == intent.file_id,
                            File.tenant_id == intent.tenant_id,
                            File.object_id == intent.object_id,
                        )
                    )
                    if file is None:
                        ref = ObjectRef(intent.tenant_id, intent.file_id, intent.object_id)
                        for upload_id in await scoped.pending_for_object(ref):
                            await scoped.abort_multipart(ref, upload_id)
                        # No public completion path exists without a file record.
                        await scoped.delete(ref)
                    current = await db.get(UploadIntent, intent.file_id)
                    current.checked_at = now
                    await db.commit()
            except StorageError:
                logger.warning("Initialization cleanup unavailable; intent retained")
                async with factory() as db:
                    current = await db.get(UploadIntent, intent.file_id)
                    if current is not None:
                        current.checked_at = now
                        await db.commit()
            finally:
                await scoped.close()
        marker = await sweep_orphans(inventory, factory, marker, now)
        logger.info("Upload maintenance checked %s records; reclaimed %s", len(candidates), cleaned)
        return marker
    finally:
        await inventory.close()


async def main(once=False):
    marker = None
    while True:
        try:
            marker = await tick(marker=marker)
        except Exception:
            # Raw SDK/SQL exceptions may contain sensitive values; log no exception payload.
            logger.error("Upload maintenance unavailable; records retained for retry")
            if once:
                raise RuntimeError("Upload maintenance failed") from None
        if once:
            return
        await asyncio.sleep(settings.UPLOAD_CLEANUP_INTERVAL_SECONDS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main(parser.parse_args().once))
