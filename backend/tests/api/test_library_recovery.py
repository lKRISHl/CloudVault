import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models import File, FileVersion, Folder, TrashEntry, UploadIntent
from app.services.trash_cleanup import TrashCleanupService
from tests.api.test_auth import register_user
from tests.api.test_downloads import uploaded
from tests.api.test_files import reserve
from tests.api.test_folders import create as folder
from tests.api.test_organizations import add_member, bearer
from tests.api.test_shares import create as share
from tests.api.test_trash import trash
from tests.api.test_uploads import DIGEST, start, storage
from tests.test_trash_cleanup import PurgeStore

__all__ = ["storage"]


async def move(client, actor, fid, destination, source=None):
    return await client.post(
        f"/api/v1/files/{fid}/move",
        headers=bearer(actor),
        json={"folder_id": destination, "source_folder_id": source},
    )


async def restore(client, actor, entry, destination=None, name=None):
    data = {"use_original": False, "destination_id": destination}
    if name is not None:
        data["name"] = name
    return await client.post(
        f"/api/v1/trash/{entry['id']}/restore",
        headers=bearer(actor),
        json=data,
    )


@pytest.mark.asyncio
async def test_move_preserves_versions_revokes_links_and_rechecks_source_location(
    client, db_factory, storage
):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    target = await folder(client, owner, "Destination")
    _, token = await share(client, owner, fid)
    async with db_factory() as db:
        original = await db.get(File, UUID(fid))
        identity = original.object_id, original.current_version, original.version_generation
        version = await db.scalar(select(FileVersion).where(FileVersion.file_id == UUID(fid)))
        snapshot_id, snapshot_object = version.id, version.object_id
    result = await move(client, owner, fid, target["id"])
    assert result.status_code == 200, result.text
    assert result.json()["folder_id"] == target["id"]
    assert (await client.post("/api/v1/shares/access", json={"token": token})).status_code == 404
    assert (await move(client, owner, fid, None)).status_code == 409
    async with db_factory() as db:
        file = await db.get(File, UUID(fid))
        version = await db.get(FileVersion, snapshot_id)
        assert (file.object_id, file.current_version, file.version_generation) == identity
        assert version.object_id == snapshot_object
    assert (await move(client, owner, fid, None, target["id"])).status_code == 200


@pytest.mark.asyncio
async def test_move_rejects_foreign_private_read_only_parent_and_name_conflicts(client, storage):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    foreign = await register_user(client, email="move-foreign@example.com")
    fid = await uploaded(client, owner)
    foreign_folder = await folder(client, foreign, "Foreign")
    assert (await move(client, foreign, fid, None)).status_code == 404
    assert (await move(client, owner, fid, foreign_folder["id"])).status_code == 404
    grant = f"/api/v1/files/{fid}/permissions/{member['user']['id']}"
    assert (
        await client.put(grant, headers=bearer(owner), json={"role": "editor"})
    ).status_code == 204
    assert (await move(client, member, fid, None)).status_code == 403
    source = await folder(client, owner, "Source")
    target = await folder(client, owner, "Target")
    member_ticket = await start(client, member, name="Owned.txt", folder_id=None)
    mid = member_ticket["file"]["id"]
    assert (
        await client.post(f"/api/v1/files/{mid}/complete", headers=bearer(member))
    ).status_code == 200
    assert (await move(client, member, mid, target["id"])).status_code == 403
    assert (await move(client, owner, mid, source["id"])).status_code == 200
    assert (await move(client, member, mid, None, source["id"])).status_code == 403
    await client.patch(
        f"/api/v1/folders/{source['id']}/permissions",
        headers=bearer(owner),
        json={"visibility": "private"},
    )
    assert (await move(client, member, mid, None, source["id"])).status_code == 404
    await start(client, owner, folder_id=target["id"])
    assert (await move(client, owner, fid, target["id"])).status_code == 409
    assert (await client.get(f"/api/v1/files/{fid}", headers=bearer(owner))).json()[
        "folder_id"
    ] is None


@pytest.mark.asyncio
async def test_concurrent_moves_have_one_location_winner(client, storage):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    a = await folder(client, owner, "A")
    b = await folder(client, owner, "B")
    responses = await asyncio.gather(
        move(client, owner, fid, a["id"]), move(client, owner, fid, b["id"])
    )
    assert sorted(r.status_code for r in responses) == [200, 409]


@pytest.mark.asyncio
async def test_restore_elsewhere_recovers_missing_parent_name_conflicts_and_keeps_independent_trash(
    client, storage
):
    owner = await register_user(client)
    parent = await folder(client, owner, "Parent")
    child = await folder(client, owner, "Child", parent["id"])
    older = await folder(client, owner, "Older", child["id"])
    old_entry = await trash(client, owner, "folders", older["id"])
    entry = await trash(client, owner, "folders", child["id"])
    parent_entry = await trash(client, owner, "folders", parent["id"])
    assert (
        await client.post(f"/api/v1/trash/{entry['id']}/restore", headers=bearer(owner))
    ).status_code == 404
    await folder(client, owner, "Child")
    assert (await restore(client, owner, entry)).status_code == 409
    assert (await restore(client, owner, entry, name="Recovered")).status_code == 204
    recovered = (await client.get(f"/api/v1/folders/{child['id']}", headers=bearer(owner))).json()
    assert recovered["parent_id"] is None and recovered["name"] == "Recovered"
    assert (
        await client.get(f"/api/v1/folders/{older['id']}", headers=bearer(owner))
    ).status_code == 404
    ids = {
        r["id"] for r in (await client.get("/api/v1/trash", headers=bearer(owner))).json()["items"]
    }
    assert old_entry["id"] in ids and parent_entry["id"] in ids
    assert (await restore(client, owner, old_entry, child["id"])).status_code == 204


@pytest.mark.asyncio
async def test_restore_authority_destination_cycle_and_conflict_rollback(
    client, db_factory, storage
):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    foreign = await register_user(client, email="restore-foreign@example.com")
    fid = await uploaded(client, owner)
    entry = await trash(client, owner, "files", fid)
    foreign_folder = await folder(client, foreign, "Other")
    assert (await restore(client, foreign, entry)).status_code == 404
    assert (await restore(client, member, entry)).status_code == 404
    assert (await restore(client, owner, entry, foreign_folder["id"])).status_code == 404
    await start(client, owner)
    assert (await restore(client, owner, entry)).status_code == 409
    async with db_factory() as db:
        assert (await db.get(TrashEntry, UUID(entry["id"]))).restored_at is None
        assert (await db.get(File, UUID(fid))).trash_id == UUID(entry["id"])
    assert (await restore(client, owner, entry, name="Reclaimed.txt")).status_code == 204
    parent = await folder(client, owner, "Parent")
    child = await folder(client, owner, "Child", parent["id"])
    parent_entry = await trash(client, owner, "folders", parent["id"])
    # Trashed destinations are rejected before they can create cycles.
    assert (await restore(client, owner, parent_entry, child["id"])).status_code == 404
    for name in ["../bad", "x" * 256, "\n"]:
        assert (await restore(client, owner, parent_entry, name=name)).status_code == 422


@pytest.mark.asyncio
async def test_cancel_folder_requires_confirmation_and_preserves_deadline_references_after_restore(
    client, db_factory, storage
):
    owner = await register_user(client)
    parent = await folder(client, owner, "Uploads")
    pending = await start(client, owner, folder_id=parent["id"])
    fid = pending["file"]["id"]
    url = f"/api/v1/folders/{parent['id']}/cancel-uploads-and-trash"
    assert (
        await client.post(url, headers=bearer(owner), json={"confirmation": "DELETE"})
    ).status_code == 422
    assert (
        await client.post(f"/api/v1/folders/{parent['id']}/trash", headers=bearer(owner))
    ).status_code == 409
    response = await client.post(
        url, headers=bearer(owner), json={"confirmation": "CANCEL UPLOADS"}
    )
    assert response.status_code == 201, response.text
    entry = response.json()
    async with db_factory() as db:
        file = await db.get(File, UUID(fid))
        assert file.upload_cancelled_at and file.object_id and file.upload_cleanup_at is None
        assert file.upload_expires_at.isoformat().split("+")[0] in pending["expires_at"]
    assert (await restore(client, owner, entry)).status_code == 204
    assert (
        await client.post(f"/api/v1/files/{fid}/complete", headers=bearer(owner))
    ).status_code == 410
    assert (
        await client.post(
            f"/api/v1/files/{fid}/upload-url",
            headers=bearer(owner),
            json={"checksum_sha256": DIGEST},
        )
    ).status_code == 410
    assert (await client.get(f"/api/v1/files/{fid}", headers=bearer(owner))).json()[
        "upload_cancelled_at"
    ]


@pytest.mark.asyncio
async def test_cancelled_folder_purge_waits_for_provider_absence_and_retries(
    client, db_factory, storage
):
    owner = await register_user(client)
    parent = await folder(client, owner, "Uploads")
    pending = await start(client, owner, folder_id=parent["id"])
    result = await client.post(
        f"/api/v1/folders/{parent['id']}/cancel-uploads-and-trash",
        headers=bearer(owner),
        json={"confirmation": "CANCEL UPLOADS"},
    )
    entry = result.json()
    await client.post(
        f"/api/v1/trash/{entry['id']}/purge", headers=bearer(owner), json={"confirmation": "DELETE"}
    )
    provider = PurgeStore()
    tenant, eid = UUID(owner["user"]["tenant"]["id"]), UUID(entry["id"])
    async with db_factory() as db:
        assert not await TrashCleanupService(db, provider).sweep(eid, tenant)
        assert provider.deleted == 0
        later = datetime.now(UTC) + timedelta(days=2)
        provider.fail = True
        assert not await TrashCleanupService(db, provider).sweep(eid, tenant, later)
        provider.fail = False
        assert await TrashCleanupService(db, provider).sweep(eid, tenant, later)
        file = await db.get(File, UUID(pending["file"]["id"]))
        assert file.upload_cleanup_at and file.object_id and file.upload_cancelled_at
        provider.present = True
        assert await TrashCleanupService(db, provider).sweep(
            eid, tenant, later + timedelta(minutes=1)
        )
        assert provider.deleted == 2


@pytest.mark.asyncio
async def test_legacy_discard_is_authorized_retained_and_releases_name_without_inventing_bytes(
    client, db_factory, storage
):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    legacy = await reserve(db_factory, owner, "Legacy.txt")
    root = f"/api/v1/files/{legacy.id}"
    assert (await client.get(root, headers=bearer(owner))).json()["legacy_metadata"]
    assert (
        await client.post(
            root + "/discard-metadata", headers=bearer(member), json={"confirmation": "DISCARD"}
        )
    ).status_code == 403
    assert (
        await client.post(
            root + "/discard-metadata", headers=bearer(owner), json={"confirmation": "DELETE"}
        )
    ).status_code == 422
    assert (
        await client.post(
            root + "/discard-metadata", headers=bearer(owner), json={"confirmation": "DISCARD"}
        )
    ).status_code == 204
    assert (await client.get(root, headers=bearer(owner))).status_code == 404
    async with db_factory() as db:
        row = await db.get(File, legacy.id)
        assert row.upload_cleanup_at and row.upload_cancelled_at and row.object_id is None
    assert (await start(client, owner, name="Legacy.txt"))["file"]["id"] != str(legacy.id)
    referenced = await start(client, owner, name="Has session.txt")
    assert (
        await client.post(
            f"/api/v1/files/{referenced['file']['id']}/discard-metadata",
            headers=bearer(owner),
            json={"confirmation": "DISCARD"},
        )
    ).status_code == 409


@pytest.mark.asyncio
async def test_legacy_intent_discard_refuses_and_mixed_creator_cancellation_is_manager_only(
    client, db_factory, storage
):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    parent = await folder(client, member, "Mixed")
    legacy = await reserve(db_factory, member, "Legacy.txt", UUID(parent["id"]))
    async with db_factory() as db:
        db.add(
            UploadIntent(
                file_id=legacy.id,
                tenant_id=UUID(owner["user"]["tenant"]["id"]),
                created_by=UUID(member["user"]["id"]),
                object_id=uuid4(),
                request_id=uuid4(),
                storage_bucket="cv-unit-uploads",
                fingerprint="0" * 64,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        await db.commit()
    assert (
        await client.post(
            f"/api/v1/files/{legacy.id}/discard-metadata",
            headers=bearer(member),
            json={"confirmation": "DISCARD"},
        )
    ).status_code == 409
    await start(client, owner, folder_id=parent["id"])
    url = f"/api/v1/folders/{parent['id']}/cancel-uploads-and-trash"
    assert (
        await client.post(url, headers=bearer(member), json={"confirmation": "CANCEL UPLOADS"})
    ).status_code == 403
    # Manager also fails atomically for an unmatched legacy intent; no pending state is lost.
    assert (
        await client.post(url, headers=bearer(owner), json={"confirmation": "CANCEL UPLOADS"})
    ).status_code == 409
    async with db_factory() as db:
        assert (await db.get(Folder, UUID(parent["id"]))).trash_id is None
        assert (await db.get(File, legacy.id)).upload_cancelled_at is None
        await db.delete(await db.get(UploadIntent, legacy.id))
        db.add(
            FileVersion(
                tenant_id=UUID(owner["user"]["tenant"]["id"]),
                file_id=legacy.id,
                number=1,
                base_generation=1,
                created_by=UUID(member["user"]["id"]),
                request_id=uuid4(),
                object_id=uuid4(),
                storage_bucket="cv-unit-uploads",
                upload_expires_at=datetime.now(UTC) + timedelta(hours=1),
                declared_size_bytes=1,
                expected_checksum_sha256=DIGEST,
            )
        )
        await db.commit()
    assert (
        await client.post(url, headers=bearer(owner), json={"confirmation": "CANCEL UPLOADS"})
    ).status_code == 409
    async with db_factory() as db:
        assert await db.scalar(select(FileVersion.id).where(FileVersion.file_id == legacy.id))
        assert (await db.get(File, legacy.id)).upload_cancelled_at is None


@pytest.mark.asyncio
async def test_cancel_folder_and_complete_serialize_without_reactivating_cancelled_content(
    client, db_factory, storage
):
    owner = await register_user(client)
    parent = await folder(client, owner, "Race")
    ticket = await start(client, owner, folder_id=parent["id"])
    fid = ticket["file"]["id"]
    cancel, complete = await asyncio.gather(
        client.post(
            f"/api/v1/folders/{parent['id']}/cancel-uploads-and-trash",
            headers=bearer(owner),
            json={"confirmation": "CANCEL UPLOADS"},
        ),
        client.post(f"/api/v1/files/{fid}/complete", headers=bearer(owner)),
    )
    assert cancel.status_code == 201
    assert complete.status_code in (200, 404)
    async with db_factory() as db:
        file = await db.get(File, UUID(fid))
        assert file.trash_id == UUID(cancel.json()["id"])
        assert (file.upload_cancelled_at is not None) == (file.status == "pending")


@pytest.mark.asyncio
async def test_explicit_restore_and_purge_race_has_one_safe_winner(client, storage):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    entry = await trash(client, owner, "files", fid)
    a, b = await asyncio.gather(
        restore(client, owner, entry, name="Restored.txt"),
        client.post(
            f"/api/v1/trash/{entry['id']}/purge",
            headers=bearer(owner),
            json={"confirmation": "DELETE"},
        ),
    )
    assert (a.status_code, b.status_code) in [(204, 404), (409, 202)]


@pytest.mark.asyncio
async def test_restore_checks_full_subtree_depth_and_mixed_creator_authority(
    client, db_factory, storage
):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    source = await folder(client, member, "Member root")
    await folder(client, owner, "Manager child", source["id"])
    entry = await trash(client, owner, "folders", source["id"])
    assert (await restore(client, member, entry)).status_code == 403
    async with db_factory() as db:
        parent_id = None
        for depth in range(63):
            item = Folder(
                id=uuid4(),
                tenant_id=UUID(owner["user"]["tenant"]["id"]),
                created_by=UUID(owner["user"]["id"]),
                parent_id=parent_id,
                name=f"Depth {depth}",
                name_key=f"depth {depth}",
            )
            db.add(item)
            await db.flush()
            parent_id = item.id
        await db.commit()
    assert (await restore(client, owner, entry, str(parent_id))).status_code == 409
    assert (await restore(client, owner, entry)).status_code == 204


@pytest.mark.asyncio
async def test_cancel_pending_bound_refuses_atomically_without_losing_metadata(
    client, db_factory, storage
):
    owner = await register_user(client)
    parent = await folder(client, owner, "Many pending")
    async with db_factory() as db:
        for number in range(101):
            db.add(
                File(
                    tenant_id=UUID(owner["user"]["tenant"]["id"]),
                    created_by=UUID(owner["user"]["id"]),
                    folder_id=UUID(parent["id"]),
                    name=f"Pending {number}",
                    name_key=f"pending {number}",
                    declared_size_bytes=1,
                )
            )
        await db.commit()
    response = await client.post(
        f"/api/v1/folders/{parent['id']}/cancel-uploads-and-trash",
        headers=bearer(owner),
        json={"confirmation": "CANCEL UPLOADS"},
    )
    assert response.status_code == 409 and "100 pending" in response.text
    async with db_factory() as db:
        assert (await db.get(Folder, UUID(parent["id"]))).trash_id is None
        assert all(row.upload_cancelled_at is None for row in await db.scalars(select(File)))
