"""Operator-only scheduler execution health; not a claim that the backlog is empty."""

import argparse
import asyncio
import json
from uuid import UUID

from redis import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.services.background_jobs import JOBS, BackgroundJobService
from app.services.job_backlog import backlog
from app.storage.s3 import S3ObjectStorage


async def storage_dependency():
    if not settings.S3_BUCKET_NAME:
        return "unconfigured"
    storage = None
    try:
        storage = S3ObjectStorage(settings, UUID(int=0))
        await storage.check_bucket()
        versioning = await storage.call(storage.client.get_bucket_versioning)
        return (
            "versioning_refused" if versioning.get("Status") in ("Enabled", "Suspended") else "ok"
        )
    except Exception:
        return "unavailable"
    finally:
        if storage is not None:
            await storage.close()


async def inspect(names):
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        service = BackgroundJobService(factory)
        results = []
        for name in names:
            result = await service.health(name)
            result["backlog"] = await backlog(factory, name)
            if (
                name == "email"
                and result["state"] == "ok"
                and result["backlog"]["retrying_deliveries"]["count"]
            ):
                result["state"] = "degraded"
            if (
                name == "previews"
                and any(
                    result["backlog"][key]["count"]
                    for key in (
                        "failed_previews",
                        "deferred_preview_cleanup",
                        "unavailable_namespace_cleanup",
                    )
                )
                and result["state"] == "ok"
            ):
                result["state"] = "degraded"
            if name in ("storage", "previews"):
                result["storage_dependency"] = await storage_dependency()
                if result["storage_dependency"] != "ok":
                    result["state"] = "dependency_unavailable"
            results.append(result)
        return results
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", choices=sorted(JOBS), action="append")
    names = parser.parse_args().job or sorted(JOBS)
    try:
        with Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2
        ) as client:
            client.ping()
        results = asyncio.run(inspect(names))
    except Exception:
        print(json.dumps({"state": "dependency_unavailable"}))
        raise SystemExit(1) from None
    print(
        json.dumps(
            {
                "jobs": results,
                "meaning": "best-effort counts/stage health; not byte purge or SMTP delivery proof",
            }
        )
    )
    raise SystemExit(0 if all(item["state"] == "ok" for item in results) else 1)


if __name__ == "__main__":
    main()
