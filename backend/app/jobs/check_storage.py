"""Operator smoke: unique object round trip through the real configured adapter."""

import asyncio
from uuid import uuid4

from app.core.config import settings
from app.storage.base import ObjectNotFoundError, ObjectRef
from app.storage.s3 import S3ObjectStorage


async def main():
    ref = ObjectRef(uuid4(), uuid4(), uuid4())
    storage = S3ObjectStorage(settings, ref.tenant_id)
    created = False
    try:
        await storage.check_bucket()
        # Attempt cleanup even if a write acknowledgement is lost.
        created = True
        await storage.put_small(ref, b"cloudvault-adapter-smoke")
        info = await storage.head(ref)
        assert info.size_bytes == len(b"cloudvault-adapter-smoke")
        assert await storage.read_small(ref) == b"cloudvault-adapter-smoke"
        await storage.delete(ref)
        created = False
        try:
            await storage.head(ref)
        except ObjectNotFoundError:
            pass
        else:
            raise RuntimeError("Storage deletion verification failed")
        print("S3 adapter bucket/put/head/read/delete verified")
    finally:
        try:
            if created:
                await storage.delete(ref)
        finally:
            await storage.close()


if __name__ == "__main__":
    asyncio.run(main())
