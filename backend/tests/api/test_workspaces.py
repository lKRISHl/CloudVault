import asyncio
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token
from app.models import Membership, User, UserRole
from app.models.account import LoginSession
from app.services.auth import AuthService
from app.services.organizations import OrganizationService
from tests.api.test_auth import REGISTER_PAYLOAD, register_user
from tests.api.test_organizations import PREFIX, add_member, bearer

ROOT = "/api/v1/organizations"


async def join_existing(client, owner, member, role="member"):
    invitation = await client.post(
        f"{PREFIX}/invitations",
        headers=bearer(owner),
        json={"email": member["user"]["email"], "role": role},
    )
    assert invitation.status_code == 201, invitation.text
    accepted = await client.post(
        f"{ROOT}/invitations/accept-existing",
        headers=bearer(member),
        json={"token": invitation.json()["token"]},
    )
    assert accepted.status_code == 200, accepted.text
    return invitation.json()


async def switch(client, session, tenant_id):
    response = await client.post(f"{ROOT}/{tenant_id}/switch", headers=bearer(session))
    assert response.status_code == 200, response.text
    return response.json()


def sid(session):
    return UUID(jwt.decode(session["access_token"], options={"verify_signature": False})["sid"])


@pytest.mark.asyncio
async def test_existing_join_roles_switch_revocation_refresh_and_scoped_lists(client, db_factory):
    owner = await register_user(client)
    other = await register_user(client, email="other@example.com", tenant_name="Other")
    old_cookie = client.cookies[settings.REFRESH_COOKIE_NAME]
    await join_existing(client, owner, other)
    rows = (await client.get(ROOT, headers=bearer(other))).json()
    assert {row["role"] for row in rows} == {"owner", "member"}
    assert len((await client.get(ROOT, headers=bearer(owner))).json()) == 1
    switched = await switch(client, other, owner["user"]["tenant"]["id"])
    assert switched["user"]["role"] == "member"
    assert sid(other) != sid(switched)
    assert (await client.get("/api/v1/auth/me", headers=bearer(other))).status_code == 401
    assert (
        await client.patch(PREFIX, headers=bearer(switched), json={"name": "Denied"})
    ).status_code == 403
    async with db_factory() as db:
        previous, current = (
            await db.get(LoginSession, sid(other)),
            await db.get(LoginSession, sid(switched)),
        )
        assert previous.revoked_at is not None and current.expires_at == previous.expires_at
    refresh_cookie = client.cookies[settings.REFRESH_COOKIE_NAME]
    client.cookies.set(
        settings.REFRESH_COOKIE_NAME, old_cookie, domain="test.local", path="/api/v1/auth"
    )
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    client.cookies.set(
        settings.REFRESH_COOKIE_NAME, refresh_cookie, domain="test.local", path="/api/v1/auth"
    )
    refreshed = await client.post("/api/v1/auth/refresh")
    assert (
        refreshed.status_code == 200
        and refreshed.json()["user"]["tenant"]["id"] == owner["user"]["tenant"]["id"]
    )
    assert sid(refreshed.json()) == sid(switched)


@pytest.mark.asyncio
async def test_unrelated_workspace_and_session_tenant_forgery_are_rejected(client):
    first = await register_user(client)
    other = await register_user(client, email="other@example.com", tenant_name="Other")
    for tenant_id in (other["user"]["tenant"]["id"], str(uuid4())):
        assert (
            await client.post(f"{ROOT}/{tenant_id}/switch", headers=bearer(first))
        ).status_code == 403
    assert (await client.get("/api/v1/auth/me", headers=bearer(first))).status_code == 200
    await join_existing(client, other, first)
    forged = create_access_token(
        user_id=UUID(first["user"]["id"]),
        tenant_id=UUID(other["user"]["tenant"]["id"]),
        role="owner",
        session_id=sid(first),
    )
    assert (
        await client.get(PREFIX, headers={"Authorization": f"Bearer {forged}"})
    ).status_code == 401


@pytest.mark.asyncio
async def test_create_workspace_verified_gate_and_preserves_other_browser_session(client):
    owner = await register_user(client)
    login = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": owner["user"]["email"], "password": REGISTER_PAYLOAD["password"]},
        )
    ).json()
    created = await client.post(ROOT, headers=bearer(owner), json={"name": "Second Workspace"})
    assert created.status_code == 201
    assert (
        created.json()["user"]["role"] == "owner"
        and created.json()["user"]["tenant"]["name"] == "Second Workspace"
    )
    assert (await client.get(PREFIX, headers=bearer(login))).status_code == 200
    assert (await client.get(PREFIX, headers=bearer(owner))).status_code == 401
    pending = (
        await client.post(
            "/api/v1/auth/register", json={**REGISTER_PAYLOAD, "email": "pending@example.com"}
        )
    ).json()
    assert (
        await client.post(ROOT, headers=bearer(pending), json={"name": "Denied"})
    ).status_code == 403


@pytest.mark.asyncio
async def test_existing_invitation_requires_verified_matching_identity_and_no_replay(
    client, db_factory
):
    owner = await register_user(client)
    other = await register_user(client, email="other@example.com")
    pending = (
        await client.post(
            "/api/v1/auth/register", json={**REGISTER_PAYLOAD, "email": "pending@example.com"}
        )
    ).json()
    invitation = (
        await client.post(
            f"{PREFIX}/invitations",
            headers=bearer(owner),
            json={"email": pending["user"]["email"], "role": "member"},
        )
    ).json()
    payload = {"token": invitation["token"]}
    assert (
        await client.post(
            f"{ROOT}/invitations/accept-existing", headers=bearer(other), json=payload
        )
    ).status_code == 403
    assert (
        await client.post(
            f"{ROOT}/invitations/accept-existing", headers=bearer(pending), json=payload
        )
    ).status_code == 403
    from tests.api.test_auth import verify_test_account

    await verify_test_account(client, pending["user"]["email"])
    assert (
        await client.post(
            f"{ROOT}/invitations/accept-existing", headers=bearer(pending), json=payload
        )
    ).status_code == 200
    assert (
        await client.post(
            f"{ROOT}/invitations/accept-existing", headers=bearer(pending), json=payload
        )
    ).status_code in (400, 409)
    async with db_factory() as db:
        user = await db.get(User, UUID(pending["user"]["id"]))
        assert user.full_name == REGISTER_PAYLOAD["full_name"]


@pytest.mark.asyncio
async def test_removal_preserves_other_workspace_and_owner_reactivation_never_revives_old_session(
    client, db_factory
):
    owner = await register_user(client)
    other = await register_user(client, email="other@example.com", tenant_name="Other")
    invitation = await join_existing(client, owner, other)
    active = await switch(client, other, owner["user"]["tenant"]["id"])
    separate = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "other@example.com", "password": REGISTER_PAYLOAD["password"]},
        )
    ).json()
    assert separate["user"]["tenant"]["name"] == "Other"
    admin, _ = await add_member(client, owner, "admin@example.com", "admin")
    assert (
        await client.delete(f"{PREFIX}/members/{other['user']['id']}", headers=bearer(owner))
    ).status_code == 204
    assert (await client.get(PREFIX, headers=bearer(active))).status_code == 401
    assert (await client.get(PREFIX, headers=bearer(separate))).status_code == 200
    assert (
        await client.post(
            f"{ROOT}/{owner['user']['tenant']['id']}/switch", headers=bearer(separate)
        )
    ).status_code == 403
    assert (
        await client.post(
            f"{ROOT}/invitations/accept-existing",
            headers=bearer(separate),
            json={"token": invitation["token"]},
        )
    ).status_code == 400
    assert (
        await client.post(
            f"{PREFIX}/invitations",
            headers=bearer(admin),
            json={"email": "other@example.com", "role": "member"},
        )
    ).status_code == 403
    await join_existing(client, owner, separate, "admin")
    restored = await switch(client, separate, owner["user"]["tenant"]["id"])
    assert restored["user"]["role"] == "admin"
    assert (await client.get(PREFIX, headers=bearer(active))).status_code == 401
    async with db_factory() as db:
        assert (await db.get(User, UUID(other["user"]["id"]))).is_active


@pytest.mark.asyncio
async def test_transfer_confirmation_password_eligibility_and_stale_role(client):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    payload = {"user_id": member["user"]["id"], "password": "wrong", "confirmation": "TRANSFER"}
    assert (
        await client.post(f"{PREFIX}/ownership", headers=bearer(owner), json=payload)
    ).status_code == 403
    payload["password"] = REGISTER_PAYLOAD["password"]
    assert (
        await client.post(
            f"{PREFIX}/ownership", headers=bearer(owner), json={**payload, "confirmation": "no"}
        )
    ).status_code == 422
    assert (
        await client.post(
            f"{PREFIX}/ownership",
            headers=bearer(owner),
            json={**payload, "user_id": owner["user"]["id"]},
        )
    ).status_code == 409
    assert (
        await client.post(
            f"{PREFIX}/ownership", headers=bearer(owner), json={**payload, "user_id": str(uuid4())}
        )
    ).status_code == 404
    assert (
        await client.post(f"{PREFIX}/ownership", headers=bearer(owner), json=payload)
    ).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=bearer(owner))).json()["role"] == "admin"
    assert (await client.get("/api/v1/auth/me", headers=bearer(member))).json()["role"] == "owner"
    assert (
        await client.post(f"{PREFIX}/ownership", headers=bearer(owner), json=payload)
    ).status_code == 403
    assert (
        await client.delete(f"{PREFIX}/members/{member['user']['id']}", headers=bearer(owner))
    ).status_code == 409


@pytest.mark.asyncio
async def test_delete_checks_ownership_across_all_memberships_and_revokes_every_session(
    client, db_factory
):
    first = await register_user(client)
    second = await register_user(client, email="second@example.com", tenant_name="Second")
    member, _ = await add_member(client, first)
    await join_existing(client, second, member, "admin")
    member_second = await switch(client, member, second["user"]["tenant"]["id"])
    transfer = {
        "user_id": member["user"]["id"],
        "password": REGISTER_PAYLOAD["password"],
        "confirmation": "TRANSFER",
    }
    assert (
        await client.post(f"{PREFIX}/ownership", headers=bearer(first), json=transfer)
    ).status_code == 204
    deletion = {"password": REGISTER_PAYLOAD["password"], "confirmation": "DELETE"}
    assert (
        await client.request(
            "DELETE", "/api/v1/account", headers=bearer(member_second), json=deletion
        )
    ).status_code == 409
    in_first = await switch(client, member_second, first["user"]["tenant"]["id"])
    transfer["user_id"] = first["user"]["id"]
    assert (
        await client.post(f"{PREFIX}/ownership", headers=bearer(in_first), json=transfer)
    ).status_code == 204
    assert (
        await client.request("DELETE", "/api/v1/account", headers=bearer(in_first), json=deletion)
    ).status_code == 204
    async with db_factory() as db:
        assert not (
            await db.scalars(
                select(Membership).where(Membership.user_id == UUID(member["user"]["id"]))
            )
        ).all()
        sessions = (
            await db.scalars(
                select(LoginSession).where(LoginSession.user_id == UUID(member["user"]["id"]))
            )
        ).all()
        assert all(row.revoked_at is not None for row in sessions)


@pytest.mark.asyncio
async def test_concurrent_transfers_only_one_owner_survives(client, db_factory):
    owner = await register_user(client)
    first, _ = await add_member(client, owner, "first@example.com")
    second, _ = await add_member(client, owner, "second@example.com")

    async def transfer(target):
        async with db_factory() as db:
            actor = await AuthService(db).get_user_in_tenant(
                UUID(owner["user"]["id"]), UUID(owner["user"]["tenant"]["id"])
            )
            try:
                await OrganizationService(db).transfer(
                    actor, UUID(target["user"]["id"]), REGISTER_PAYLOAD["password"]
                )
                return 204
            except HTTPException as error:
                return error.status_code

    results = await asyncio.wait_for(asyncio.gather(transfer(first), transfer(second)), timeout=20)
    assert sorted(results) == [204, 403]
    async with db_factory() as db:
        owners = (
            await db.scalars(
                select(Membership).where(
                    Membership.tenant_id == UUID(owner["user"]["tenant"]["id"]),
                    Membership.role == UserRole.OWNER,
                    Membership.revoked_at.is_(None),
                )
            )
        ).all()
        assert len(owners) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["remove", "demote"])
async def test_transfer_racing_member_changes_cannot_remove_final_owner(client, db_factory, action):
    owner = await register_user(client)
    member, _ = await add_member(client, owner)
    tenant_id = UUID(owner["user"]["tenant"]["id"])

    async def attempt(transfer):
        async with db_factory() as db:
            actor = await AuthService(db).get_user_in_tenant(UUID(owner["user"]["id"]), tenant_id)
            service = OrganizationService(db)
            try:
                if transfer:
                    await service.transfer(
                        actor, UUID(member["user"]["id"]), REGISTER_PAYLOAD["password"]
                    )
                elif action == "remove":
                    await service.remove_member(actor, UUID(member["user"]["id"]))
                else:
                    await service.change_role(actor, UUID(member["user"]["id"]), "admin")
                return 204
            except HTTPException as error:
                return error.status_code

    results = await asyncio.wait_for(asyncio.gather(attempt(True), attempt(False)), timeout=20)
    assert all(result in (204, 403, 404, 409) for result in results)
    async with db_factory() as db:
        owners = (
            await db.scalars(
                select(Membership).where(
                    Membership.tenant_id == tenant_id,
                    Membership.role == UserRole.OWNER,
                    Membership.revoked_at.is_(None),
                )
            )
        ).all()
        assert len(owners) == 1
