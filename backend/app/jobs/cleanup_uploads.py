"""Periodic scoped upload cleanup, including old unknown initialization uploads."""

import argparse
import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, text

from app.core.config import settings
from app.core.database import async_session_maker
from app.models import File, FileVersion, Tenant, UploadIntent
from app.services.upload_cleanup import UploadCleanupService
from app.services.uploads import utc
from app.storage.base import ObjectNotFoundError, ObjectRef, StorageError
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


async def sweep_orphans(inventory, factory, marker=None, now=None, *, page_size=100, report=None):
    """One provider page per tick, with cursor advanced by the persistent worker."""
    now = now or datetime.now(UTC)
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise ValueError("Invalid inventory page size")
    params = {"Prefix": "", "MaxUploads": page_size}
    if marker:
        params.update(KeyMarker=marker[0], UploadIdMarker=marker[1])
    page = await inventory.call(inventory.client.list_multipart_uploads, **params)
    if len(page.get("Uploads", [])) > page_size:
        raise StorageError("Provider exceeded inventory page limit")
    # Static maximum permitted session + grace, independent of settings decreasing.
    cutoff = now - timedelta(seconds=7200 + 600 + settings.UPLOAD_CLEANUP_SETTLE_SECONDS)
    for upload in page.get("Uploads", []):
        if report is not None:
            report["inspected"] = report.get("inspected", 0) + 1
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
            retained_version = await db.scalar(
                select(FileVersion.id).where(
                    FileVersion.tenant_id == ref.tenant_id,
                    FileVersion.file_id == ref.file_id,
                    FileVersion.object_id == ref.object_id,
                )
            )
            if retained_version is not None:
                continue
        scoped = S3ObjectStorage(settings, ref.tenant_id)
        try:
            await scoped.abort_multipart(ref, upload["UploadId"])
        except StorageError:
            logger.warning("Orphan upload abort unavailable; future scan will retry")
            if report is not None:
                report["deferred"] = report.get("deferred", 0) + 1
        finally:
            await scoped.close()
    if page.get("IsTruncated"):
        next_marker = (page.get("NextKeyMarker", ""), page.get("NextUploadIdMarker", ""))
        if not next_marker[0] or next_marker == marker:
            raise StorageError("Invalid orphan pagination")
        return next_marker
    return None


async def tick(factory=async_session_maker, marker=None, *, stage=None, batch_size=50, report=None):
    from app.services.background_jobs import STORAGE_STAGES

    if stage is not None and stage not in STORAGE_STAGES:
        raise ValueError("Unknown maintenance stage")
    if type(batch_size) is not int or not 1 <= batch_size <= 50:
        raise ValueError("Invalid maintenance batch size")
    report = report if report is not None else {}
    if not settings.S3_BUCKET_NAME:
        raise StorageError("Storage maintenance is not configured")
    inventory = S3ObjectStorage(settings, uuid4())
    try:
        # Delete markers cannot prove reclamation; versioned providers fail closed.
        versioning = await inventory.call(inventory.client.get_bucket_versioning)
        if versioning.get("Status") in ("Enabled", "Suspended"):
            raise StorageError("Upload cleanup requires an unversioned bucket")
        now = datetime.now(UTC)
        candidates, cleaned = [], 0
        from app.services.version_cleanup import VersionCleanupService
        from app.services.version_policy import apply_policy

        if stage in (None, "uploads"):
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
                        .limit(batch_size)
                    )
                )
            cleaned = 0
            for file_id, tenant_id in candidates:
                scoped = S3ObjectStorage(settings, tenant_id)
                try:
                    async with factory() as db:
                        result = await UploadCleanupService(db, scoped).sweep(
                            file_id, tenant_id, now
                        )
                        cleaned += result
                        report["inspected"] = report.get("inspected", 0) + 1
                        report["deferred"] = report.get("deferred", 0) + (not result)
                finally:
                    await scoped.close()
        if stage in (None, "intents"):
            async with factory() as db:
                intents = list(
                    await db.scalars(
                        select(UploadIntent)
                        .where(
                            UploadIntent.storage_bucket == settings.S3_BUCKET_NAME,
                            UploadIntent.expires_at <= UploadCleanupService.cutoff(now),
                        )
                        .order_by(
                            UploadIntent.checked_at.asc().nullsfirst(), UploadIntent.expires_at
                        )
                        .limit(batch_size)
                    )
                )
            for intent in intents:
                report["inspected"] = report.get("inspected", 0) + 1
                scoped = S3ObjectStorage(settings, intent.tenant_id)
                try:
                    async with factory() as db:
                        await db.scalar(
                            select(Tenant.id).where(Tenant.id == intent.tenant_id).with_for_update()
                        )
                        file = await db.scalar(
                            select(File).where(
                                File.id == intent.file_id,
                                File.tenant_id == intent.tenant_id,
                                File.object_id == intent.object_id,
                            )
                        )
                        retained = await db.scalar(
                            select(FileVersion.id).where(
                                FileVersion.tenant_id == intent.tenant_id,
                                FileVersion.file_id == intent.file_id,
                                FileVersion.object_id == intent.object_id,
                            )
                        )
                        if file is None and retained is None:
                            ref = ObjectRef(intent.tenant_id, intent.file_id, intent.object_id)
                            for upload_id in await scoped.pending_for_object(ref):
                                await scoped.abort_multipart(ref, upload_id)
                            # No public completion path exists without a file record.
                            await scoped.delete(ref)
                            if await scoped.pending_for_object(ref):
                                raise StorageError("Initialization parts still retained")
                            try:
                                await scoped.inspect_upload(ref)
                            except ObjectNotFoundError:
                                current = await db.get(UploadIntent, intent.file_id)
                                current.cleaned_at = now
                            else:
                                raise StorageError("Initialization object still retained")
                        current = await db.get(UploadIntent, intent.file_id)
                        current.checked_at = now
                        await db.commit()
                except StorageError:
                    logger.warning("Initialization cleanup unavailable; intent retained")
                    report["deferred"] = report.get("deferred", 0) + 1
                    async with factory() as db:
                        current = await db.get(UploadIntent, intent.file_id)
                        if current is not None:
                            current.checked_at = now
                            await db.commit()
                finally:
                    await scoped.close()
        if stage in (None, "orphans"):
            marker = await sweep_orphans(
                inventory,
                factory,
                marker,
                now,
                page_size=batch_size if stage else 100,
                report=report,
            )
        if stage in (None, "policies"):
            async with factory() as db:
                policies = list(
                    await db.execute(
                        select(File.id, File.tenant_id)
                        .where(
                            File.version_keep_last.is_not(None),
                            File.trash_id.is_(None),
                            File.status == "uploaded",
                        )
                        .order_by(File.version_policy_checked_at.asc().nullsfirst(), File.id)
                        .limit(min(batch_size, 25))
                    )
                )
            for file_id, tenant_id in policies:
                report["inspected"] = report.get("inspected", 0) + 1
                async with factory() as db:
                    if db.bind.dialect.name == "sqlite":
                        await db.execute(text("BEGIN IMMEDIATE"))
                    await db.scalar(
                        select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()
                    )
                    file = await db.scalar(
                        select(File).where(File.id == file_id, File.tenant_id == tenant_id)
                    )
                    if file:
                        await apply_policy(db, file, now)
                    await db.commit()

        if stage in (None, "versions"):
            async with factory() as db:
                expired_versions = list(
                    await db.execute(
                        select(FileVersion.id, FileVersion.tenant_id)
                        .where(
                            or_(
                                FileVersion.status == "pending",
                                and_(
                                    FileVersion.prune_requested_at.is_not(None),
                                    FileVersion.prune_not_before <= now,
                                ),
                            ),
                            FileVersion.storage_bucket == settings.S3_BUCKET_NAME,
                            FileVersion.upload_expires_at <= UploadCleanupService.cutoff(now),
                        )
                        .order_by(FileVersion.checked_at.asc().nullsfirst(), FileVersion.id)
                        .limit(batch_size)
                    )
                )
            for version_id, tenant_id in expired_versions:
                scoped = S3ObjectStorage(settings, tenant_id)
                try:
                    async with factory() as db:
                        result = await VersionCleanupService(db, scoped).sweep(
                            version_id, tenant_id, now
                        )
                        report["inspected"] = report.get("inspected", 0) + 1
                        report["deferred"] = report.get("deferred", 0) + (not result)
                finally:
                    await scoped.close()
        if stage in (None, "trash"):
            from app.jobs.cleanup_trash import tick as trash_tick

            await trash_tick(factory, limit=min(batch_size, 10), report=report)
        if stage in (None, "quotas"):
            from app.services.quota_inventory import tick as quota_tick

            inspected = await quota_tick(
                factory, lambda tid: S3ObjectStorage(settings, tid), min(batch_size, 10)
            )
            report["inspected"] = report.get("inspected", 0) + inspected
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
