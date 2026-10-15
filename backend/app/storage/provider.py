import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from botocore.exceptions import BotoCoreError
from fastapi import HTTPException

from app.core.config import settings
from app.storage.base import ObjectStorage
from app.storage.s3 import S3ObjectStorage


@asynccontextmanager
async def open_storage(tenant_id: UUID) -> AsyncIterator[ObjectStorage]:
    """Build a scoped adapter only after a caller has established resource authority."""
    if not settings.S3_BUCKET_NAME:
        raise HTTPException(503, "File storage is not configured")
    try:
        storage = await asyncio.to_thread(S3ObjectStorage, settings, tenant_id)
    except BotoCoreError:
        raise HTTPException(503, "File storage is unavailable") from None
    try:
        yield storage
    finally:
        await storage.close()
