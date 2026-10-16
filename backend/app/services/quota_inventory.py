"""One tenant/provider inventory page per maintenance turn; never deletes provider data."""

import hashlib
import re
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select

from app.models import StorageObservation, StorageQuota, Tenant
from app.services.background_jobs import storage_namespace
from app.storage.base import ObjectNotFoundError, StorageError

KEY = re.compile(r"tenants/([^/]+)/files/([^/]+)/objects/([^/]+)")


class QuotaInventory:
    def __init__(self, db, storage):
        self.db, self.storage = db, storage

    async def observe(self, tenant_id, key, now):
        prefix = f"tenants/{tenant_id}/"
        if not isinstance(key, str) or not key.startswith(prefix) or len(key) > 1024:
            raise StorageError("Invalid quota inventory scope")
        file_id = object_id = uuid5(NAMESPACE_URL, key)
        match = KEY.fullmatch(key)
        if match:
            try:
                parsed_tenant, file_id, object_id = (UUID(part) for part in match.groups())
            except ValueError:
                raise StorageError("Invalid quota object identity") from None
            if parsed_tenant != tenant_id:
                raise StorageError("Invalid quota inventory scope")
            if key != f"tenants/{tenant_id}/files/{file_id}/objects/{object_id}":
                file_id = object_id = uuid5(NAMESPACE_URL, key)
        amount = 0
        try:
            info = await self.storage.call(self.storage.client.head_object, Key=key)
            amount = info["ContentLength"]
        except ObjectNotFoundError:
            pass
        if type(amount) is not int or amount < 0:
            raise StorageError("Invalid quota object size")
        uploads = await self.storage.call(
            self.storage.client.list_multipart_uploads,
            Prefix=key,
            MaxUploads=2,
        )
        # Unknown/excessive manifests are not guessed or silently exempted from quota.
        if uploads.get("IsTruncated") or len(uploads.get("Uploads", [])) > 2:
            amount = None
        else:
            for upload in uploads.get("Uploads", []):
                if upload["Key"] != key:
                    continue
                try:
                    parts = await self.storage.call(
                        self.storage.client.list_parts,
                        Key=key,
                        UploadId=upload["UploadId"],
                        MaxParts=1000,
                    )
                except ObjectNotFoundError:
                    continue
                manifest = parts.get("Parts", [])
                if parts.get("IsTruncated") and len(manifest) <= 1000:
                    marker = parts.get("NextPartNumberMarker", 0)
                    if type(marker) is not int or marker <= 0:
                        raise StorageError("Invalid quota part cursor")
                    tail = await self.storage.call(
                        self.storage.client.list_parts,
                        Key=key,
                        UploadId=upload["UploadId"],
                        PartNumberMarker=marker,
                        MaxParts=24,
                    )
                    manifest = [*manifest, *tail.get("Parts", [])]
                    parts = tail
                if parts.get("IsTruncated") or len(manifest) > 1024:
                    amount = None
                    break
                sizes = [part.get("Size") for part in manifest]
                if any(type(size) is not int or size < 0 for size in sizes):
                    raise StorageError("Invalid quota multipart size")
                amount += sum(sizes)
        identity = (tenant_id, storage_namespace(), hashlib.sha256(key.encode()).hexdigest())
        row = await self.db.get(StorageObservation, identity)
        if row is None:
            row = StorageObservation(
                tenant_id=tenant_id,
                namespace=identity[1],
                key_hash=identity[2],
                storage_key=key,
                storage_bucket=self.storage.bucket,
                file_id=file_id,
                object_id=object_id,
                checked_at=now,
            )
            self.db.add(row)
        row.size_bytes, row.checked_at = amount, now

    async def page(self, tenant, limit):
        namespace = storage_namespace()
        state = tenant.quota_inventory or {}
        if state.get("namespace") != namespace:
            state = {"namespace": namespace, "phase": "objects"}
        phase = state.get("phase", "objects")
        prefix = f"tenants/{tenant.id}/"
        now = datetime.now(UTC)
        params = {"Prefix": prefix}
        if phase == "objects":
            if state.get("marker"):
                params["ContinuationToken"] = state["marker"]
            page = await self.storage.call(
                self.storage.client.list_objects_v2, MaxKeys=limit, **params
            )
            rows = page.get("Contents", [])
            following = {"namespace": namespace, "phase": "uploads"}
            if page.get("IsTruncated"):
                marker = page.get("NextContinuationToken")
                if not marker or marker == state.get("marker"):
                    raise StorageError("Invalid quota object cursor")
                following = {"namespace": namespace, "phase": "objects", "marker": marker}
        elif phase == "uploads":
            # Local MinIO omits live uploads for a directory Prefix even though the
            # bucket inventory and exact-key lookup expose them. Page the privileged
            # bucket inventory, then apply tenant scope before recording anything.
            params["Prefix"] = ""
            if state.get("key_marker"):
                params.update(KeyMarker=state["key_marker"], UploadIdMarker=state["upload_marker"])
            page = await self.storage.call(
                self.storage.client.list_multipart_uploads, MaxUploads=limit, **params
            )
            rows = page.get("Uploads", [])
            following = {"namespace": namespace, "phase": "objects"}
            if page.get("IsTruncated"):
                key, upload = page.get("NextKeyMarker"), page.get("NextUploadIdMarker", "")
                if not key or (key, upload) == (
                    state.get("key_marker"),
                    state.get("upload_marker"),
                ):
                    raise StorageError("Invalid quota multipart cursor")
                following.update(phase="uploads", key_marker=key, upload_marker=upload)
        else:
            raise StorageError("Invalid quota inventory phase")
        if len(rows) > limit:
            raise StorageError("Provider exceeded quota inventory page bound")
        keys = {row["Key"] for row in rows if row["Key"].startswith(prefix)}
        # Recheck retained evidence too: absence in a page is not proof of deletion.
        prior = await self.db.scalars(
            select(StorageObservation.storage_key)
            .where(
                StorageObservation.tenant_id == tenant.id,
                StorageObservation.namespace == namespace,
            )
            .order_by(StorageObservation.checked_at, StorageObservation.key_hash)
            .limit(limit)
        )
        keys.update(prior)
        for key in keys:
            await self.observe(tenant.id, key, now)
        tenant.quota_inventory = following
        return len(keys)


async def tick(factory, storage_factory, limit):
    # Persist selection before I/O so one failing tenant cannot starve later tenants.
    async with factory() as db:
        tenant = await db.scalar(
            select(Tenant.id)
            .outerjoin(StorageQuota, StorageQuota.tenant_id == Tenant.id)
            .order_by(
                StorageQuota.quota_checked_at.asc().nullsfirst(),
                Tenant.id,
            )
            .with_for_update(of=Tenant, skip_locked=True)
            .limit(1)
        )
        if tenant is None:
            return 0
        tenant_id = tenant
        tenant = await db.get(StorageQuota, tenant_id)
        if tenant is None:
            tenant = StorageQuota(tenant_id=tenant_id)
            db.add(tenant)
        tenant.quota_checked_at = datetime.now(UTC)
        tenant.quota_inventory = {**(tenant.quota_inventory or {}), "failed": True}
        await db.commit()
    storage = storage_factory(tenant_id)
    try:
        async with factory() as db:
            await db.scalar(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())
            tenant = await db.get(StorageQuota, tenant_id, populate_existing=True)
            versioning = await storage.call(storage.client.get_bucket_versioning)
            if versioning.get("Status") in ("Enabled", "Suspended"):
                raise StorageError("Quota inventory requires unversioned provider accounting")
            inspected = await QuotaInventory(db, storage).page(tenant, limit)
            await db.commit()
            return inspected
    finally:
        await storage.close()
