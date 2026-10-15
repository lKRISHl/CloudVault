from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.models import TrashEntry
from tests.api.test_auth import register_user
from tests.api.test_downloads import uploaded
from tests.api.test_folders import create as folder
from tests.api.test_organizations import add_member, bearer
from tests.api.test_shares import create as share
from tests.api.test_uploads import start, storage

__all__ = ["storage"]


async def trash(client, actor, kind, rid):
    result = await client.post(f"/api/v1/{kind}/{rid}/trash", headers=bearer(actor))
    assert result.status_code == 201, result.text
    return result.json()


@pytest.mark.asyncio
async def test_file_trash_restore_preserves_acl_and_blocks_all_live_paths(client, storage):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    _, token = await share(client, owner, fid)
    entry = await trash(client, owner, "files", fid)
    assert (await client.get(f"/api/v1/files/{fid}", headers=bearer(owner))).status_code == 404
    assert (await client.get("/api/v1/files/search", headers=bearer(owner))).json()["items"] == []
    assert (
        await client.post(f"/api/v1/files/{fid}/download-url", headers=bearer(owner))
    ).status_code == 404
    assert (await client.post("/api/v1/shares/access", json={"token": token})).status_code == 404
    listing = (await client.get("/api/v1/trash", headers=bearer(owner))).json()
    assert [item["id"] for item in listing["items"]] == [entry["id"]] and not listing["has_more"]
    assert (
        await client.post(f"/api/v1/trash/{entry['id']}/restore", headers=bearer(owner))
    ).status_code == 204
    assert (await client.get(f"/api/v1/files/{fid}", headers=bearer(owner))).status_code == 200
    assert (await client.post("/api/v1/shares/access", json={"token": token})).status_code == 404


@pytest.mark.asyncio
async def test_names_reused_and_restore_conflicts_are_atomic(client, storage):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    entry = await trash(client, owner, "files", fid)
    replacement = await start(client, owner)
    assert replacement["file"]["id"] != fid
    response = await client.post(f"/api/v1/trash/{entry['id']}/restore", headers=bearer(owner))
    assert response.status_code == 409
    assert (await client.get(f"/api/v1/files/{fid}", headers=bearer(owner))).status_code == 404


@pytest.mark.asyncio
async def test_folder_batches_keep_independent_trash_and_require_parent_restore(client, storage):
    owner = await register_user(client)
    parent = await folder(client, owner, "Parent")
    child = await folder(client, owner, "Child", parent["id"])
    child_entry = await trash(client, owner, "folders", child["id"])
    parent_entry = await trash(client, owner, "folders", parent["id"])
    assert (await client.get("/api/v1/folders", headers=bearer(owner))).json()["items"] == []
    assert (
        await client.post(f"/api/v1/trash/{child_entry['id']}/restore", headers=bearer(owner))
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/trash/{parent_entry['id']}/restore", headers=bearer(owner))
    ).status_code == 204
    assert (
        await client.get(f"/api/v1/folders/{child['id']}", headers=bearer(owner))
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/trash/{child_entry['id']}/restore", headers=bearer(owner))
    ).status_code == 204


@pytest.mark.asyncio
async def test_trash_management_not_viewer_or_editor_and_pending_is_protected(client, storage):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    fid = await uploaded(client, owner)
    assert (
        await client.post(f"/api/v1/files/{fid}/trash", headers=bearer(member))
    ).status_code == 403
    entry = await trash(client, owner, "files", fid)
    assert (await client.get("/api/v1/trash", headers=bearer(member))).json()["items"] == []
    assert (
        await client.post(f"/api/v1/trash/{entry['id']}/restore", headers=bearer(member))
    ).status_code == 404
    pending = await start(client, owner, name="Pending.txt")
    assert (
        await client.post(f"/api/v1/files/{pending['file']['id']}/trash", headers=bearer(owner))
    ).status_code == 409


@pytest.mark.asyncio
async def test_permanent_delete_queues_and_disables_restore_including_nested_trash(client, storage):
    owner = await register_user(client)
    parent = await folder(client, owner, "Parent")
    child = await folder(client, owner, "Child", parent["id"])
    child_entry = await trash(client, owner, "folders", child["id"])
    parent_entry = await trash(client, owner, "folders", parent["id"])
    url = f"/api/v1/trash/{parent_entry['id']}/purge"
    assert (
        await client.post(url, headers=bearer(owner), json={"confirmation": "wrong"})
    ).status_code == 422
    for _ in range(2):
        assert (
            await client.post(url, headers=bearer(owner), json={"confirmation": "DELETE"})
        ).status_code == 202
    assert (
        await client.post(f"/api/v1/trash/{child_entry['id']}/restore", headers=bearer(owner))
    ).status_code == 409


@pytest.mark.asyncio
async def test_retention_expiry_prevents_restore_and_private_ancestors_hide_trash(
    client, db_factory, storage
):
    owner = await register_user(client)
    fid = await uploaded(client, owner)
    entry = await trash(client, owner, "files", fid)
    async with db_factory() as db:
        item = await db.get(TrashEntry, UUID(entry["id"]))
        item.retain_until = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    assert (
        await client.post(f"/api/v1/trash/{entry['id']}/restore", headers=bearer(owner))
    ).status_code == 409


@pytest.mark.asyncio
async def test_private_ancestor_removal_hides_creator_trash_before_pagination(client, storage):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    parent = await folder(client, owner, "Private container")
    base = f"/api/v1/folders/{parent['id']}/permissions"
    assert (
        await client.patch(base, headers=bearer(owner), json={"visibility": "private"})
    ).status_code == 204
    assert (
        await client.put(
            f"{base}/{member['user']['id']}", headers=bearer(owner), json={"role": "editor"}
        )
    ).status_code == 204
    ticket = await start(client, member, folder_id=parent["id"])
    fid = ticket["file"]["id"]
    assert (
        await client.post(f"/api/v1/files/{fid}/complete", headers=bearer(member))
    ).status_code == 200
    entry = await trash(client, member, "files", fid)
    assert (
        await client.put(
            f"{base}/{member['user']['id']}", headers=bearer(owner), json={"role": None}
        )
    ).status_code == 204
    listing = (await client.get("/api/v1/trash", headers=bearer(member))).json()
    assert listing["items"] == [] and not listing["has_more"]
    assert (
        await client.post(f"/api/v1/trash/{entry['id']}/restore", headers=bearer(member))
    ).status_code == 404


@pytest.mark.asyncio
async def test_nonmanager_cannot_trash_another_creators_subtree_and_folder_conflicts_roll_back(
    client, storage
):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    parent = await folder(client, member, "Shared container")
    ticket = await start(client, owner, folder_id=parent["id"])
    fid = ticket["file"]["id"]
    assert (
        await client.post(f"/api/v1/files/{fid}/complete", headers=bearer(owner))
    ).status_code == 200
    assert (
        await client.post(f"/api/v1/folders/{parent['id']}/trash", headers=bearer(member))
    ).status_code == 403
    entry = await trash(client, owner, "folders", parent["id"])
    await folder(client, owner, "Shared container")
    assert (
        await client.post(f"/api/v1/trash/{entry['id']}/restore", headers=bearer(owner))
    ).status_code == 409
    assert (await client.get(f"/api/v1/files/{fid}", headers=bearer(owner))).status_code == 404


@pytest.mark.asyncio
async def test_concurrent_restore_and_purge_have_one_irreversible_outcome(
    client, db_factory, storage
):
    import asyncio

    owner = await register_user(client)
    fid = await uploaded(client, owner)
    entry = await trash(client, owner, "files", fid)
    responses = await asyncio.gather(
        client.post(f"/api/v1/trash/{entry['id']}/restore", headers=bearer(owner)),
        client.post(
            f"/api/v1/trash/{entry['id']}/purge",
            headers=bearer(owner),
            json={"confirmation": "DELETE"},
        ),
    )
    assert [response.status_code for response in responses] in ([204, 404], [409, 202])
    async with db_factory() as db:
        item = await db.get(TrashEntry, UUID(entry["id"]))
        assert bool(item.restored_at) != bool(item.purge_requested_at)
