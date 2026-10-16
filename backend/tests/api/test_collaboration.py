"""Phase18A contracts. Authored now; run at the combined18A+20 checkpoint.

Storage is the explicit upload unit provider. Release metadata below is a known verdict
fixture; actual scanner/provider/browser acceptance remains a separate checkpoint.
"""

import secrets
from uuid import UUID, uuid4
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, func

from app.models import File, FileVersion, ShareLink, ResourceOwner
from app.services.scans import policy, fingerprint
from tests.api.test_auth import register_user
from tests.api.test_downloads import uploaded
from tests.api.test_folders import create as folder
from tests.api.test_organizations import add_member, bearer
from tests.api.test_permissions import visibility, grant
from tests.api.test_shares import public_storage
from tests.api.test_uploads import storage

__all__ = ["storage", "public_storage"]


async def released_file(client, actor, db_factory):
    fid = await uploaded(client, actor)
    async with db_factory() as db:
        file = await db.get(File, UUID(fid))
        version = await db.scalar(
            select(FileVersion).where(
                FileVersion.file_id == file.id, FileVersion.object_id == file.object_id
            )
        )
        version.scan_status = file.scan_status = "clean"
        version.scan_policy = policy()
        version.scan_fingerprint = fingerprint(version)
        version.scan_engine = "explicit-test-verdict"
        version.scanned_at = file.scanned_at = datetime.now(UTC)
        await db.commit()
    return fid


async def link(client, actor, kind, rid, **options):
    payload = {"request_id": str(uuid4()), "token": secrets.token_urlsafe(32), **options}
    result = await client.post(f"/api/v1/{kind}/{rid}/shares", headers=bearer(actor), json=payload)
    assert result.status_code == 201, result.text
    return result.json(), payload


@pytest.mark.asyncio
async def test_lost_response_replay_binds_secret_resource_options_and_password(
    client, db_factory, storage
):
    owner = await register_user(client)
    fid = await released_file(client, owner, db_factory)
    first, payload = await link(client, owner, "files", fid, password="private-password")
    endpoint = f"/api/v1/files/{fid}/shares"
    replay = await client.post(endpoint, headers=bearer(owner), json=payload)
    assert replay.json() == first
    for changed in (
        {"allow_download": False},
        {"password": "other-password"},
        {"token": secrets.token_urlsafe(32)},
    ):
        assert (
            await client.post(endpoint, headers=bearer(owner), json={**payload, **changed})
        ).status_code == 409
    async with db_factory() as db:
        assert await db.scalar(select(func.count()).select_from(ShareLink)) == 1
        stored = await db.get(ShareLink, UUID(first["id"]))
        assert stored.token_hash != payload["token"] and stored.password_hash != payload["password"]
    listing = await client.get(endpoint, headers=bearer(owner))
    assert payload["token"] not in listing.text and "password_hash" not in listing.text
    await client.delete(endpoint + "/" + first["id"], headers=bearer(owner))
    replay = await client.post(endpoint, headers=bearer(owner), json=payload)
    assert replay.json()["id"] == first["id"] and replay.json()["revoked_at"]
    assert (
        await client.post(
            "/api/v1/shares/access",
            json={"token": payload["token"], "password": payload["password"]},
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_named_recipient_requires_verified_matching_account_and_no_membership(
    client, db_factory, storage
):
    owner = await register_user(client)
    recipient = await register_user(client, email="recipient@example.com")
    wrong = await register_user(client, email="wrong@example.com")
    fid = await released_file(client, owner, db_factory)
    _, payload = await link(client, owner, "files", fid, recipient_email="recipient@example.com")
    access = {"token": payload["token"]}
    for headers in ({}, bearer(wrong)):
        denied = await client.post("/api/v1/shares/access", headers=headers, json=access)
        assert denied.status_code == 404 and "Report.txt" not in denied.text
    accepted = await client.post("/api/v1/shares/access", headers=bearer(recipient), json=access)
    assert accepted.status_code == 200 and accepted.json()["name"] == "Report.txt"
    assert (await client.get(f"/api/v1/files/{fid}", headers=bearer(recipient))).status_code == 404
    from app.models import User

    async with db_factory() as db:
        user = await db.get(User, UUID(recipient["user"]["id"]))
        user.email_verified = False
        await db.commit()
    assert (
        await client.post("/api/v1/shares/access", headers=bearer(recipient), json=access)
    ).status_code in (401, 403, 404)


@pytest.mark.asyncio
async def test_folder_current_subtree_new_children_move_out_and_foreign_paths(
    client, db_factory, storage
):
    owner = await register_user(client)
    root = await folder(client, owner, "Shared root")
    _, payload = await link(client, owner, "folders", root["id"])
    child = await folder(client, owner, "New child", root["id"])
    outside = await folder(client, owner, "Outside")
    fid = await released_file(client, owner, db_factory)

    async def move(source, target):
        response = await client.post(
            f"/api/v1/files/{fid}/move",
            headers=bearer(owner),
            json={"source_folder_id": source, "folder_id": target},
        )
        assert response.status_code == 200, response.text

    await move(None, child["id"])
    access = {"token": payload["token"]}
    page = await client.post("/api/v1/shares/access", json=access)
    assert [entry["name"] for entry in page.json()["items"]] == ["New child"]
    nested = await client.post("/api/v1/shares/folder", json={**access, "folder_id": child["id"]})
    assert nested.json()["items"][0]["id"] == fid
    denied = await client.post("/api/v1/shares/folder", json={**access, "folder_id": outside["id"]})
    assert denied.status_code == 404 and "Outside" not in denied.text
    await move(child["id"], outside["id"])
    assert (
        await client.post("/api/v1/shares/download-url", json={**access, "file_id": fid})
    ).status_code == 404
    assert (
        await client.post("/api/v1/shares/folder", json={**access, "folder_id": child["id"]})
    ).json()["items"] == []


@pytest.mark.asyncio
async def test_folder_trash_restore_never_revives_revoked_link(client, storage):
    owner = await register_user(client)
    root = await folder(client, owner, "Shared")
    _, payload = await link(client, owner, "folders", root["id"])
    trashed = await client.post(f"/api/v1/folders/{root['id']}/trash", headers=bearer(owner))
    assert trashed.status_code == 201, trashed.text
    restored = await client.post(
        f"/api/v1/trash/{trashed.json()['id']}/restore", headers=bearer(owner)
    )
    assert restored.status_code == 204, restored.text
    assert (
        await client.post("/api/v1/shares/folder", json={"token": payload["token"]})
    ).status_code == 404


@pytest.mark.asyncio
async def test_transfer_preserves_provenance_revokes_links_and_creator_authority(
    client, db_factory, storage
):
    owner = await register_user(client)
    creator, _ = await add_member(client, owner)
    target, _ = await add_member(client, owner, email="target@example.com")
    fid = await released_file(client, creator, db_factory)
    _, payload = await link(client, creator, "files", fid)
    await visibility(client, creator, "files", fid)
    response = await client.post(
        f"/api/v1/files/{fid}/ownership",
        headers=bearer(creator),
        json={"user_id": target["user"]["id"]},
    )
    assert response.status_code == 204, response.text
    assert (await client.get(f"/api/v1/files/{fid}", headers=bearer(creator))).status_code == 404
    details = await client.get(f"/api/v1/files/{fid}", headers=bearer(target))
    assert details.json()["can_manage"] and details.json()["created_by"] == creator["user"]["id"]
    async with db_factory() as db:
        assert {
            str(v.created_by)
            for v in await db.scalars(select(FileVersion).where(FileVersion.file_id == UUID(fid)))
        } == {creator["user"]["id"]}
        assert str((await db.scalar(select(ResourceOwner))).user_id) == target["user"]["id"]
    assert (
        await client.post("/api/v1/shares/access", json={"token": payload["token"]})
    ).status_code == 404


@pytest.mark.asyncio
async def test_transfer_requires_target_current_ancestors_and_verified_membership(
    client, db_factory, storage
):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    foreign = await register_user(client, email="foreign@example.com")
    parent = await folder(client, owner, "Private parent")
    child = await folder(client, owner, "Child", parent["id"])
    await visibility(client, owner, "folders", parent["id"])
    endpoint = f"/api/v1/folders/{child['id']}/ownership"
    for target, status in ((foreign, 404), (member, 409)):
        assert (
            await client.post(
                endpoint, headers=bearer(owner), json={"user_id": target["user"]["id"]}
            )
        ).status_code == status
    await grant(client, owner, "folders", parent["id"], member, "viewer")
    assert (
        await client.post(endpoint, headers=bearer(owner), json={"user_id": member["user"]["id"]})
    ).status_code == 204
    await client.delete(
        f"/api/v1/organizations/current/members/{member['user']['id']}", headers=bearer(owner)
    )
    assert (
        await client.get(f"/api/v1/folders/{child['id']}/permissions", headers=bearer(member))
    ).status_code in (401, 403, 404)


@pytest.mark.asyncio
async def test_candidate_search_and_grant_names_are_authorized_and_literal(client, storage):
    owner = await register_user(client)
    member, _ = await add_member(client, owner, email="find-me@example.com")
    outsider = await register_user(client, email="foreign@example.com")
    root = await folder(client, owner, "Root")
    endpoint = f"/api/v1/folders/{root['id']}/permission-candidates"
    match = await client.get(endpoint, headers=bearer(owner), params={"q": "find-me"})
    assert [item["user_id"] for item in match.json()["items"]] == [member["user"]["id"]]
    assert (await client.get(endpoint, headers=bearer(owner), params={"q": "%"})).json()[
        "items"
    ] == []
    assert (await client.get(endpoint, headers=bearer(outsider))).status_code == 404
    assert (await client.get(endpoint, headers=bearer(member))).status_code == 403
    await grant(client, owner, "folders", root["id"], member, "viewer")
    grants = await client.get(f"/api/v1/folders/{root['id']}/permissions", headers=bearer(owner))
    assert grants.json()["items"][0]["email"] == "find-me@example.com"


@pytest.mark.asyncio
async def test_parallel_replay_is_one_link_on_postgresql(client, db_factory, storage):
    import asyncio

    async with db_factory() as db:
        if db.bind.dialect.name != "postgresql":
            pytest.skip("Row-lock concurrency acceptance requires disposable PostgreSQL")
    owner = await register_user(client)
    fid = await released_file(client, owner, db_factory)
    payload = {"request_id": str(uuid4()), "token": secrets.token_urlsafe(32)}
    endpoint = f"/api/v1/files/{fid}/shares"
    replies = await asyncio.gather(
        *(client.post(endpoint, headers=bearer(owner), json=payload) for _ in range(2))
    )
    assert [reply.status_code for reply in replies] == [201, 201]
    assert replies[0].json()["share_url"] == replies[1].json()["share_url"]
    assert replies[0].json()["id"] == replies[1].json()["id"]
    async with db_factory() as db:
        assert await db.scalar(select(func.count()).select_from(ShareLink)) == 1


@pytest.mark.asyncio
async def test_resource_transfer_and_member_removal_serialize_on_postgresql(
    client, db_factory, storage
):
    import asyncio

    async with db_factory() as db:
        if db.bind.dialect.name != "postgresql":
            pytest.skip("Transfer/removal row-lock acceptance requires disposable PostgreSQL")
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    fid = await released_file(client, owner, db_factory)
    transferred, removed = await asyncio.gather(
        client.post(
            f"/api/v1/files/{fid}/ownership",
            headers=bearer(owner),
            json={"user_id": member["user"]["id"]},
        ),
        client.delete(
            f"/api/v1/organizations/current/members/{member['user']['id']}", headers=bearer(owner)
        ),
    )
    assert transferred.status_code in (204, 404) and removed.status_code == 204
    assert (await client.get(f"/api/v1/files/{fid}", headers=bearer(member))).status_code in (
        401,
        403,
        404,
    )
    recovered = await client.post(
        f"/api/v1/files/{fid}/ownership",
        headers=bearer(owner),
        json={"user_id": owner["user"]["id"]},
    )
    assert recovered.status_code == 204


@pytest.mark.asyncio
async def test_publisher_losing_private_ancestor_never_keeps_folder_capability(client):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    parent = await folder(client, owner, "Private ancestor")
    await visibility(client, owner, "folders", parent["id"])
    await grant(client, owner, "folders", parent["id"], member, "editor")
    child = await folder(client, member, "Member shared child", parent["id"])
    _, payload = await link(client, member, "folders", child["id"])
    access = {"token": payload["token"]}
    assert (await client.post("/api/v1/shares/folder", json=access)).status_code == 200
    await grant(client, owner, "folders", parent["id"], member, None)
    assert (await client.post("/api/v1/shares/folder", json=access)).status_code == 404
