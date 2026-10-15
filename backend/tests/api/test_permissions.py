from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models import ResourceGrant
from tests.api.test_auth import register_user
from tests.api.test_downloads import uploaded
from tests.api.test_folders import create as folder
from tests.api.test_organizations import add_member, bearer
from tests.api.test_shares import create as share
from tests.api.test_uploads import DIGEST, start, storage

__all__ = ["storage"]


async def visibility(client, actor, kind, rid, value="private"):
    response = await client.patch(
        f"/api/v1/{kind}/{rid}/permissions", headers=bearer(actor), json={"visibility": value}
    )
    assert response.status_code == 204, response.text


async def grant(client, actor, kind, rid, member, role):
    response = await client.put(
        f"/api/v1/{kind}/{rid}/permissions/{member['user']['id']}",
        headers=bearer(actor),
        json={"role": role},
    )
    assert response.status_code == 204, response.text


@pytest.mark.asyncio
async def test_private_file_hidden_before_paging_and_viewer_editor_management(client, storage):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    fid = await uploaded(client, owner)
    await visibility(client, owner, "files", fid)
    for endpoint in [f"/files/{fid}", "/files", "/files/search?limit=1"]:
        response = await client.get("/api/v1" + endpoint, headers=bearer(member))
        if endpoint.endswith(fid):
            assert response.status_code == 404
        else:
            assert response.json()["items"] == [] and not response.json()["has_more"]
    assert (
        await client.post(f"/api/v1/files/{fid}/download-url", headers=bearer(member))
    ).status_code == 404
    await grant(client, owner, "files", fid, member, "viewer")
    details = (await client.get(f"/api/v1/files/{fid}", headers=bearer(member))).json()
    assert not details["can_write"] and not details["can_manage"]
    assert (
        await client.patch(f"/api/v1/files/{fid}", headers=bearer(member), json={"name": "No.txt"})
    ).status_code == 403
    await grant(client, owner, "files", fid, member, "editor")
    changed = await client.patch(
        f"/api/v1/files/{fid}", headers=bearer(member), json={"name": "Edited.txt"}
    )
    assert (
        changed.status_code == 200
        and changed.json()["can_write"]
        and not changed.json()["can_manage"]
    )
    for path in [f"/files/{fid}/permissions", f"/files/{fid}/shares"]:
        assert (await client.get("/api/v1" + path, headers=bearer(member))).status_code == 403
    assert (
        await client.post(f"/api/v1/files/{fid}/shares", headers=bearer(member), json={})
    ).status_code == 403
    await grant(client, owner, "files", fid, member, None)
    assert (await client.get(f"/api/v1/files/{fid}", headers=bearer(member))).status_code == 404


@pytest.mark.asyncio
async def test_private_ancestors_gate_search_detail_folder_context_and_uploads(client, storage):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    parent = await folder(client, owner, "Secret parent")
    child = await folder(client, owner, "Child", parent["id"])
    ticket = await start(client, owner, folder_id=child["id"])
    fid = ticket["file"]["id"]
    assert (
        await client.post(f"/api/v1/files/{fid}/complete", headers=bearer(owner))
    ).status_code == 200
    await visibility(client, owner, "folders", parent["id"])
    await grant(client, owner, "files", fid, member, "editor")
    # A direct descendant grant cannot bypass the containing folder boundary.
    for path in [
        f"/files/{fid}",
        f"/folders/{child['id']}",
        f"/files/search?scope=folder&folder_id={child['id']}",
    ]:
        response = await client.get("/api/v1" + path, headers=bearer(member))
        assert response.status_code == 404 and "Secret parent" not in response.text
    result = (await client.get("/api/v1/files/search", headers=bearer(member))).json()
    assert result["items"] == []
    await grant(client, owner, "folders", parent["id"], member, "viewer")
    result = (await client.get("/api/v1/files/search", headers=bearer(member))).json()
    assert result["items"][0]["id"] == fid and result["items"][0]["folder_name"] == "Child"
    assert (
        await client.post(
            "/api/v1/folders",
            headers=bearer(member),
            json={"name": "Denied", "parent_id": parent["id"]},
        )
    ).status_code == 403
    await grant(client, owner, "folders", parent["id"], member, "editor")
    created = await folder(client, member, "Editor-created", parent["id"])
    assert created["created_by"] == member["user"]["id"]
    assert (
        await client.patch(
            f"/api/v1/folders/{parent['id']}", headers=bearer(member), json={"name": "Renamed"}
        )
    ).status_code == 200
    assert (
        await client.post(
            f"/api/v1/folders/{parent['id']}/move", headers=bearer(member), json={"parent_id": None}
        )
    ).status_code == 403
    await grant(client, owner, "folders", parent["id"], member, None)
    assert (
        await client.get(f"/api/v1/folders/{created['id']}", headers=bearer(member))
    ).status_code == 404


@pytest.mark.asyncio
async def test_permission_mutation_revokes_file_and_subtree_external_links(client, storage):
    owner = await register_user(client)
    parent = await folder(client, owner, "Boundary")
    ticket = await start(client, owner, folder_id=parent["id"])
    fid = ticket["file"]["id"]
    assert (
        await client.post(f"/api/v1/files/{fid}/complete", headers=bearer(owner))
    ).status_code == 200
    _, token = await share(client, owner, fid)
    assert (await client.post("/api/v1/shares/access", json={"token": token})).status_code == 200
    await visibility(client, owner, "folders", parent["id"])
    assert (await client.post("/api/v1/shares/access", json={"token": token})).status_code == 404
    _, token = await share(client, owner, fid)
    await visibility(client, owner, "files", fid)
    assert (await client.post("/api/v1/shares/access", json={"token": token})).status_code == 404


@pytest.mark.asyncio
async def test_foreign_members_resources_and_privilege_escalation_are_rejected(client, storage):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    outsider = await register_user(client, email="other-permissions@example.com")
    fid = await uploaded(client, owner)
    assert (
        await client.put(
            f"/api/v1/files/{fid}/permissions/{outsider['user']['id']}",
            headers=bearer(owner),
            json={"role": "editor"},
        )
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/files/{fid}/permissions",
            headers=bearer(outsider),
            json={"visibility": "private"},
        )
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/files/{fid}/permissions",
            headers=bearer(member),
            json={"visibility": "private"},
        )
    ).status_code == 403
    for role in ["owner", "admin", "invalid"]:
        assert (
            await client.put(
                f"/api/v1/files/{fid}/permissions/{member['user']['id']}",
                headers=bearer(owner),
                json={"role": role},
            )
        ).status_code == 422
    assert (await client.get(f"/api/v1/files/{fid}/permissions")).status_code == 401
    assert (
        await client.get(f"/api/v1/files/{uuid4()}/permissions", headers=bearer(owner))
    ).status_code == 404


@pytest.mark.asyncio
async def test_removed_member_grants_are_deleted_without_resurrection(client, db_factory, storage):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    fid = await uploaded(client, owner)
    await visibility(client, owner, "files", fid)
    await grant(client, owner, "files", fid, member, "editor")
    assert (
        await client.delete(
            f"/api/v1/organizations/current/members/{member['user']['id']}", headers=bearer(owner)
        )
    ).status_code == 204
    async with db_factory() as db:
        assert (
            await db.scalar(
                select(ResourceGrant.id).where(ResourceGrant.user_id == UUID(member["user"]["id"]))
            )
            is None
        )


@pytest.mark.asyncio
async def test_download_rechecks_acl_during_provider_work(client, db_factory, storage):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    fid = await uploaded(client, owner)
    await visibility(client, owner, "files", fid)
    await grant(client, owner, "files", fid, member, "viewer")

    async def inspect(ref):
        from sqlalchemy import delete

        async with db_factory() as db:
            await db.execute(
                delete(ResourceGrant).where(ResourceGrant.user_id == UUID(member["user"]["id"]))
            )
            await db.commit()
        return storage.info

    async def sign(*args):
        pytest.fail("Revoked ACL must block signing")

    storage.inspect_upload, storage.presign_download = inspect, sign
    assert (
        await client.post(f"/api/v1/files/{fid}/download-url", headers=bearer(member))
    ).status_code == 404


@pytest.mark.asyncio
async def test_concurrent_grant_updates_keep_one_row(client, db_factory, storage):
    import asyncio

    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    fid = await uploaded(client, owner)
    responses = await asyncio.gather(
        *[
            client.put(
                f"/api/v1/files/{fid}/permissions/{member['user']['id']}",
                headers=bearer(owner),
                json={"role": role},
            )
            for role in ("viewer", "editor")
        ]
    )
    assert [response.status_code for response in responses] == [204, 204]
    async with db_factory() as db:
        rows = list(
            await db.scalars(select(ResourceGrant).where(ResourceGrant.file_id == UUID(fid)))
        )
        assert len(rows) == 1 and rows[0].role in ("viewer", "editor")


@pytest.mark.asyncio
async def test_revoked_parent_editor_cannot_complete_or_refresh_pending_upload(client, storage):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    parent = await folder(client, owner, "Private upload destination")
    await visibility(client, owner, "folders", parent["id"])
    await grant(client, owner, "folders", parent["id"], member, "editor")
    ticket = await start(client, member, folder_id=parent["id"])
    fid = ticket["file"]["id"]
    await grant(client, owner, "folders", parent["id"], member, None)
    assert (
        await client.post(f"/api/v1/files/{fid}/complete", headers=bearer(member))
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/files/{fid}/upload-url",
            headers=bearer(member),
            json={"checksum_sha256": DIGEST},
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_hidden_rows_do_not_consume_visible_search_pages(client, db_factory, storage):
    from app.models import File

    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    async with db_factory() as db:
        db.add_all(
            [
                File(
                    tenant_id=UUID(owner["user"]["tenant"]["id"]),
                    created_by=UUID(owner["user"]["id"]),
                    name=name,
                    name_key=name.casefold(),
                    declared_size_bytes=1,
                    visibility="private" if name.startswith("A") else "workspace",
                )
                for name in ("A hidden.txt", "B visible.txt", "C visible.txt")
            ]
        )
        await db.commit()
    first = (await client.get("/api/v1/files/search?limit=1", headers=bearer(member))).json()
    second = (
        await client.get("/api/v1/files/search?limit=1&offset=1", headers=bearer(member))
    ).json()
    assert [item["name"] for item in first["items"]] == ["B visible.txt"] and first["has_more"]
    assert [item["name"] for item in second["items"]] == ["C visible.txt"] and not second[
        "has_more"
    ]
