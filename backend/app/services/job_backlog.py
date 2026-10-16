"""Operator aggregates only: never return tenant identifiers or delivery payloads."""

from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select

from app.core.config import settings
from app.models import EmailOutbox, File, FileVersion, PreviewJob, TrashEntry, UploadIntent
from app.services.background_jobs import storage_namespace
from app.services.upload_cleanup import UploadCleanupService
from app.services.uploads import utc


async def backlog(factory, name, now=None):
    now = now or datetime.now(UTC)

    async def measure(db, model, date, *conditions):
        count, oldest = (
            await db.execute(
                select(func.count(), func.min(date)).select_from(model).where(*conditions)
            )
        ).one()
        return {
            "count": count,
            "oldest_age_seconds": max(0, (now - utc(oldest)).total_seconds()) if oldest else None,
        }

    async with factory() as db:
        if name == "previews":
            return {
                "due_previews": await measure(
                    db,
                    PreviewJob,
                    PreviewJob.next_attempt_at,
                    PreviewJob.state.in_(("queued", "running")),
                    PreviewJob.expires_at > now,
                    PreviewJob.next_attempt_at <= now,
                ),
                "failed_previews": await measure(
                    db,
                    PreviewJob,
                    PreviewJob.next_attempt_at,
                    PreviewJob.state == "failed",
                    PreviewJob.expires_at > now,
                ),
                "deferred_preview_cleanup": await measure(
                    db, PreviewJob, PreviewJob.cleanup_after, PreviewJob.cleanup_failed.is_(True)
                ),
                "unavailable_namespace_cleanup": await measure(
                    db,
                    PreviewJob,
                    PreviewJob.cleanup_after,
                    PreviewJob.cleanup_after <= now,
                    PreviewJob.namespace != storage_namespace(),
                ),
            }
        if name == "email":
            return {
                "due_deliveries": await measure(
                    db,
                    EmailOutbox,
                    EmailOutbox.next_attempt_at,
                    EmailOutbox.sent_at.is_(None),
                    EmailOutbox.encrypted_payload.is_not(None),
                    EmailOutbox.expires_at > now,
                    EmailOutbox.next_attempt_at <= now,
                    or_(EmailOutbox.lease_until.is_(None), EmailOutbox.lease_until <= now),
                ),
                "retrying_deliveries": await measure(
                    db,
                    EmailOutbox,
                    EmailOutbox.created_at,
                    EmailOutbox.sent_at.is_(None),
                    EmailOutbox.encrypted_payload.is_not(None),
                    EmailOutbox.expires_at > now,
                    EmailOutbox.error_code.is_not(None),
                ),
            }
        if name != "storage":
            raise ValueError("Unknown background job")
        cutoff = UploadCleanupService.cutoff(now)
        return {
            "unconfirmed_expired_uploads": await measure(
                db,
                File,
                File.upload_expires_at,
                File.status == "pending",
                File.storage_bucket == settings.S3_BUCKET_NAME,
                File.upload_expires_at <= cutoff,
                File.upload_cleanup_at.is_(None),
            ),
            "unconfirmed_versions": await measure(
                db,
                FileVersion,
                FileVersion.upload_expires_at,
                FileVersion.storage_bucket == settings.S3_BUCKET_NAME,
                FileVersion.upload_expires_at <= cutoff,
                or_(
                    and_(FileVersion.status == "pending", FileVersion.cleaned_at.is_(None)),
                    and_(FileVersion.prune_not_before <= now, FileVersion.purged_at.is_(None)),
                ),
            ),
            "due_trash": await measure(
                db,
                TrashEntry,
                TrashEntry.trashed_at,
                TrashEntry.restored_at.is_(None),
                TrashEntry.purged_at.is_(None),
                TrashEntry.not_before <= now,
                or_(TrashEntry.purge_requested_at.is_not(None), TrashEntry.retain_until <= now),
            ),
            # Intents are retained and rechecked indefinitely; these are NOT orphan bytes.
            "initialization_recheck_population": await measure(
                db,
                UploadIntent,
                UploadIntent.expires_at,
                UploadIntent.storage_bucket == settings.S3_BUCKET_NAME,
                UploadIntent.expires_at <= cutoff,
            ),
        }
