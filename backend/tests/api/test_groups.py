"""Group authorization acceptance, queued for the paired18A+20 checkpoint."""

from uuid import UUID

import pytest
from sqlalchemy import select

from app.models import GroupMember, GroupGrant
from tests.api.test_auth import register_user
from tests.api.test_folders import create as folder
from tests.api.test_organizations import add_member, bearer
from tests.api.test_permissions import visibility


async def create_group(client, actor, name="Design"):
    response = await client.post("/api/v1/groups", headers=bearer(actor), json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def membership(client, actor, gid, member, present=True):
    response = await client.put(
        f"/api/v1/groups/{gid}/members/{member['user']['id']}",
        headers=bearer(actor),
        json={"present": present},
    )
    assert response.status_code == 204, response.text


async def grant_group(client, actor, folder_id, gid, role):
    response = await client.put(
        f"/api/v1/folders/{folder_id}/group-permissions/{gid}",
        headers=bearer(actor),
        json={"role": role},
    )
    assert response.status_code == 204, response.text


@pytest.mark.asyncio
async def test_groups_manager_only_names_and_foreign_members_are_scoped(client):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    foreign = await register_user(client, email="foreign-group@example.com")
    gid = await create_group(client, owner)
    assert (
        await client.post("/api/v1/groups", headers=bearer(owner), json={"name": " design "})
    ).status_code == 409
    assert (
        await client.post("/api/v1/groups", headers=bearer(member), json={"name": "Escalation"})
    ).status_code == 403
    assert (
        await client.get(f"/api/v1/groups/{gid}/members", headers=bearer(foreign))
    ).status_code == 404
    assert (
        await client.put(
            f"/api/v1/groups/{gid}/members/{foreign['user']['id']}",
            headers=bearer(owner),
            json={"present": True},
        )
    ).status_code == 404
    assert (await client.get("/api/v1/groups", headers=bearer(foreign))).json()["items"] == []
    assert (
        await client.get(f"/api/v1/groups/{gid}/members", headers=bearer(member))
    ).status_code == 403
    assert (await client.get("/api/v1/groups?q=%25", headers=bearer(owner))).json()["items"] == []


@pytest.mark.asyncio
async def test_group_viewer_editor_cannot_bypass_private_ancestor_or_inherit_edit(client):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    gid = await create_group(client, owner)
    await membership(client, owner, gid, member)
    parent = await folder(client, owner, "Private parent")
    child = await folder(client, owner, "Private child", parent["id"])
    await visibility(client, owner, "folders", parent["id"])
    await visibility(client, owner, "folders", child["id"])
    await grant_group(client, owner, child["id"], gid, "viewer")
    endpoint = f"/api/v1/folders/{child['id']}/children"
    # Normal directory listing enforces every ancestor before producing breadcrumbs.
    endpoint = f"/api/v1/folders?parent_id={child['id']}"
    assert (await client.get(endpoint, headers=bearer(member))).status_code == 404
    await grant_group(client, owner, parent["id"], gid, "editor")
    assert (await client.get(endpoint, headers=bearer(member))).status_code == 200
    assert (
        await client.patch(
            f"/api/v1/folders/{child['id']}",
            headers=bearer(member),
            json={"name": "No inheritance"},
        )
    ).status_code == 403
    await grant_group(client, owner, child["id"], gid, "editor")
    changed = await client.patch(
        f"/api/v1/folders/{child['id']}", headers=bearer(member), json={"name": "Edited by group"}
    )
    assert (
        changed.status_code == 200
        and changed.json()["can_write"]
        and not changed.json()["can_manage"]
    )
    await membership(client, owner, gid, member, False)
    assert (await client.get(endpoint, headers=bearer(member))).status_code == 404


@pytest.mark.asyncio
async def test_group_delete_revokes_links_and_removes_grants_atomically(client, db_factory):
    owner = await register_user(client)
    gid = await create_group(client, owner)
    root = await folder(client, owner, "Root")
    await grant_group(client, owner, root["id"], gid, "viewer")
    created = await client.post(
        f"/api/v1/folders/{root['id']}/shares", headers=bearer(owner), json={}
    )
    token = created.json()["share_url"].split("#token=")[1]
    assert (await client.delete(f"/api/v1/groups/{gid}", headers=bearer(owner))).status_code == 204
    assert (await client.post("/api/v1/shares/folder", json={"token": token})).status_code == 404
    async with db_factory() as db:
        assert (
            await db.scalar(select(GroupGrant.id).where(GroupGrant.group_id == UUID(gid))) is None
        )


@pytest.mark.asyncio
async def test_workspace_departure_clears_group_membership(client, db_factory):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    gid = await create_group(client, owner)
    await membership(client, owner, gid, member)
    assert (
        await client.delete(
            f"/api/v1/organizations/current/members/{member['user']['id']}", headers=bearer(owner)
        )
    ).status_code == 204
    async with db_factory() as db:
        assert await db.get(GroupMember, (UUID(gid), UUID(member["user"]["id"]))) is None
