import asyncio
from collections.abc import AsyncGenerator
from typing import Annotated

from botocore.exceptions import BotoCoreError
from fastapi import Depends, HTTPException

from app.api.folders import WorkspaceUser
from app.core.config import settings
from app.storage.base import ObjectStorage
from app.storage.s3 import S3ObjectStorage


async def get_upload_storage(actor: WorkspaceUser) -> AsyncGenerator[ObjectStorage, None]:
    if not settings.S3_BUCKET_NAME:
        raise HTTPException(status_code=503, detail="File storage is not configured")
    try:
        storage = await asyncio.to_thread(S3ObjectStorage, settings, actor.tenant_id)
    except BotoCoreError:
        raise HTTPException(status_code=503, detail="File storage is unavailable") from None
    try:
        yield storage
    finally:
        await storage.close()


UploadStorage = Annotated[ObjectStorage, Depends(get_upload_storage)]
