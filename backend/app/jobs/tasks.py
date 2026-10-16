import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.jobs.celery_app import celery_app
from app.services.background_jobs import BackgroundJobService, read_marker, storage_namespace


async def run_job(name):
    # A fresh engine per task avoids asyncpg pools crossing prefork/event-loop boundaries.
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        if name == "scans":
            from app.jobs.scan_queue import tick as scan_tick

            async def handle_scan(cursor):
                await scan_tick(factory)
                return None

            return await BackgroundJobService(factory).run(name, handle_scan)
        if name == "previews":
            from app.jobs.preview_queue import tick

            async def handle_preview(cursor):
                await tick(factory, turn=cursor["turn"])
                return {"next_turn": cursor["next_turn"]}

            return await BackgroundJobService(factory).run(name, handle_preview)

        async def handle(cursor):
            if name == "email":
                from app.jobs.deliver_email import cleanup_account_records
                from app.services.email import deliver_next

                async with factory() as db:
                    await cleanup_account_records(db)
                # Bounded drain; the next periodic hint discovers remaining durable rows.
                for _ in range(10):
                    async with factory() as db:
                        if not await deliver_next(db):
                            break
                return None
            from app.jobs.cleanup_uploads import tick

            report = {}
            marker = await tick(
                factory=factory,
                marker=read_marker(cursor),
                stage=cursor["_stage"],
                batch_size=settings.STORAGE_STAGE_BATCH_SIZE,
                report=report,
            )
            result = {
                **cursor,
                "namespace": storage_namespace(),
                "marker": list(marker) if marker else None,
                "_report": report,
            }
            if cursor["_stage"] == "orphans":
                deferred = cursor.get("orphan_cycle_deferred", 0) + report.get("deferred", 0)
                result["orphan_cycle_deferred"] = deferred if marker else 0
                if marker is None:
                    result["last_cycle_deferred"] = deferred
            return result

        return await BackgroundJobService(factory).run(name, handle)
    finally:
        await engine.dispose()


def execute(task, name):
    try:
        return asyncio.run(run_job(name))
    except Exception:
        # SDK/SQL/SMTP exception text can contain credentials, recipient or action data.
        try:
            retry = task.retry(
                exc=RuntimeError("Maintenance unavailable; durable records retained"),
                countdown=min(60, 2 ** (task.request.retries + 1)),
                max_retries=5,
                throw=False,
            )
        except Exception:
            raise RuntimeError("Maintenance unavailable; durable records retained") from None
        raise retry from None


@celery_app.task(bind=True, name="cloudvault.maintenance.email")
def email_maintenance(self):
    return execute(self, "email")


@celery_app.task(bind=True, name="cloudvault.maintenance.storage")
def storage_maintenance(self):
    return execute(self, "storage")


@celery_app.task(bind=True, name="cloudvault.maintenance.previews")
def preview_maintenance(self):
    return execute(self, "previews")


@celery_app.task(bind=True, name="cloudvault.maintenance.scans")
def scan_maintenance(self):
    return execute(self, "scans")
