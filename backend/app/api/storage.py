from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated
from uuid import UUID

from fastapi import Depends

from app.api.folders import WorkspaceUser
from app.storage.base import ObjectStorage
from app.storage.provider import open_storage


async def get_upload_storage(actor: WorkspaceUser) -> AsyncGenerator[ObjectStorage, None]:
    async with open_storage(actor.tenant_id) as storage:
        yield storage


UploadStorage = Annotated[ObjectStorage, Depends(get_upload_storage)]

StorageFactory = Callable[[UUID], AbstractAsyncContextManager[ObjectStorage]]


def get_share_storage_factory() -> StorageFactory:
    return open_storage


ShareStorageFactory = Annotated[StorageFactory, Depends(get_share_storage_factory)]
