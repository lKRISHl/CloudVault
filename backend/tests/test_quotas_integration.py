"""Real private-provider orphan bytes/parts, bounded pages and confirmed absence."""

import base64
import hashlib
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models import StorageObservation, StorageQuota
from app.services.quota_inventory import QuotaInventory
from app.services.quotas import QuotaService
from app.storage.base import ObjectRef
from tests.api.test_auth import register_user
from tests.test_storage_integration import storage as provider_storage

storage = provider_storage
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.getenv("TEST_S3_ENDPOINT"),
        reason="Explicit disposable storage provider required",
    ),
]


async def test_actual_objects_parts_pagination_and_reclaimed_usage(client, db_factory, storage):
    owner = await register_user(client)
    tid = UUID(owner["user"]["tenant"]["id"])
    storage.tenant_id = tid
    refs = [ObjectRef(tid, uuid4(), uuid4()) for _ in range(3)]
    for ref in refs:
        await storage.put_small(ref, b"abc")
    # A different tenant prefix in the same owned bucket must never enter this usage.
    await storage.call(
        storage.client.put_object, Key=f"tenants/{uuid4()}/unrelated", Body=b"foreign"
    )
    pending = ObjectRef(tid, uuid4(), uuid4())
    upload_id = await storage.create_multipart(pending)
    await storage.call(
        storage.client.upload_part,
        Key=pending.key,
        UploadId=upload_id,
        PartNumber=1,
        Body=b"abc",
        ChecksumSHA256=base64.b64encode(hashlib.sha256(b"abc").digest()).decode(),
    )
    async with db_factory() as db:
        quota = StorageQuota(tenant_id=tid)
        db.add(quota)
        await db.commit()
        phases = []
        for _ in range(6):
            assert await QuotaInventory(db, storage).page(quota, 2) <= 4
            phases.append(quota.quota_inventory["phase"])
            await db.commit()
        usage = await QuotaService(db).usage(tid)
        observed = list(await db.scalars(select(StorageObservation)))
        actual_parts = await storage.list_parts(pending, upload_id)
        assert usage.allocated_bytes == 12, str(
            {
                "phases": phases,
                "observed": [
                    (row.object_id == pending.object_id, row.size_bytes) for row in observed
                ],
                "parts": [part.size_bytes for part in actual_parts],
            }
        )
        assert usage.orphan_bytes == 12
        assert not usage.reconciliation_required
        # Inventory itself never deletes bytes, aborts uploads or grants access.
        assert len(await storage.list_parts(pending, upload_id)) == 1
        assert await storage.read_small(refs[0]) == b"abc"
        await storage.abort_multipart(pending, upload_id)
        for ref in refs:
            await storage.delete(ref)
        for _ in range(6):
            await QuotaInventory(db, storage).page(quota, 2)
            await db.commit()
        assert (await QuotaService(db).usage(tid)).allocated_bytes == 0
