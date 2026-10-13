from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import generate_refresh_token, hash_password, hash_refresh_token
from app.models import Invitation, Membership, RefreshToken, Tenant, User, UserRole
from app.schemas.organizations import (
    AcceptInvitation,
    InvitationCreated,
    InviteRequest,
    MemberRead,
)
from app.services.accounts import AccountService, issue_account_token
from app.services.auth import AuthService, AuthSession
from app.services.email import queue_email


class OrganizationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def update_profile(self, actor: User, full_name: str) -> User:
        actor.full_name = full_name
        await self.db.commit()
        return actor

    async def _lock_organization(self, tenant_id: UUID) -> Tenant:
        result = await self.db.execute(
            select(Tenant).where(Tenant.id == tenant_id).with_for_update()
        )
        organization = result.scalar_one_or_none()
        if organization is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        return organization

    async def _require_manager(self, actor: User) -> UserRole:
        if not actor.email_verified:
            raise HTTPException(status_code=403, detail="Verify your email first")
        role = await self.db.scalar(
            select(Membership.role)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.user_id == actor.id,
                Membership.tenant_id == actor.tenant_id,
                User.is_active.is_(True),
            )
        )
        if role not in (UserRole.OWNER, UserRole.ADMIN):
            raise HTTPException(status_code=403, detail="Organization manager required")
        return role

    async def rename(self, actor: User, name: str) -> Tenant:
        organization = await self._lock_organization(actor.tenant_id)
        await self._require_manager(actor)
        organization.name = name
        await self.db.commit()
        return organization

    async def members(self, actor: User, limit: int, offset: int) -> list[MemberRead]:
        rows = await self.db.execute(
            select(User, Membership)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.tenant_id == actor.tenant_id,
                User.tenant_id == actor.tenant_id,
                User.is_active.is_(True),
            )
            .order_by(Membership.joined_at, User.id)
            .limit(limit)
            .offset(offset)
        )
        return [
            MemberRead(
                user_id=user.id,
                email=user.email,
                full_name=user.full_name,
                role=membership.role,
                joined_at=membership.joined_at,
            )
            for user, membership in rows
        ]

    async def _target(self, actor: User, user_id: UUID) -> tuple[User, Membership]:
        row = (
            await self.db.execute(
                select(User, Membership)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    User.id == user_id,
                    User.tenant_id == actor.tenant_id,
                    Membership.tenant_id == actor.tenant_id,
                    User.is_active.is_(True),
                )
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Member not found")
        return row[0], row[1]

    async def change_role(self, actor: User, user_id: UUID, role: str) -> MemberRead:
        await self._lock_organization(actor.tenant_id)
        actor_role = await self._require_manager(actor)
        user, membership = await self._target(actor, user_id)
        if actor_role != UserRole.OWNER:
            raise HTTPException(status_code=403, detail="Only the owner can change roles")
        if membership.role == UserRole.OWNER:
            raise HTTPException(status_code=409, detail="Owner membership cannot be changed")
        membership.role = UserRole(role)
        user.role = UserRole(role)
        await self._revoke_invitations(user.id, actor.tenant_id)
        await self.db.commit()
        return MemberRead(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=membership.role,
            joined_at=membership.joined_at,
        )

    async def remove_member(self, actor: User, user_id: UUID) -> None:
        await self._lock_organization(actor.tenant_id)
        actor_role = await self._require_manager(actor)
        user, membership = await self._target(actor, user_id)
        if membership.role == UserRole.OWNER or user.id == actor.id:
            raise HTTPException(status_code=409, detail="Owner or own membership cannot be removed")
        if actor_role == UserRole.ADMIN and membership.role != UserRole.MEMBER:
            raise HTTPException(status_code=403, detail="Admins can remove members only")
        await AccountService(self.db).lock_user(user.id)
        await self.db.execute(
            delete(Membership).where(
                Membership.tenant_id == actor.tenant_id,
                Membership.user_id == user_id,
            )
        )
        user.is_active = False
        await self.db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        await self._revoke_invitations(user.id, actor.tenant_id)
        await self.db.commit()

    async def _revoke_invitations(self, user_id: UUID, tenant_id: UUID) -> None:
        await self.db.execute(
            update(Invitation)
            .where(
                Invitation.created_by == user_id,
                Invitation.tenant_id == tenant_id,
                Invitation.consumed_at.is_(None),
            )
            .values(consumed_at=datetime.now(UTC))
        )

    async def invite(self, actor: User, payload: InviteRequest) -> InvitationCreated:
        await self._lock_organization(actor.tenant_id)
        actor_role = await self._require_manager(actor)
        if payload.role == "admin" and actor_role != UserRole.OWNER:
            raise HTTPException(status_code=403, detail="Only the owner can invite admins")
        email = payload.email.lower()
        if await self.db.scalar(select(User.id).where(User.email == email)) is not None:
            raise HTTPException(status_code=409, detail="Email already has an account")
        await self.db.execute(
            update(Invitation)
            .where(
                Invitation.tenant_id == actor.tenant_id,
                Invitation.email == email,
                Invitation.consumed_at.is_(None),
            )
            .values(consumed_at=datetime.now(UTC))
        )
        token = generate_refresh_token()
        invitation = Invitation(
            tenant_id=actor.tenant_id,
            email=email,
            role=payload.role,
            token_hash=hash_refresh_token(token),
            created_by=actor.id,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        self.db.add(invitation)
        queue_email(
            self.db,
            actor.id,
            "invitation",
            email,
            "Join your CloudVault organization",
            f"You were invited to {actor.tenant.name}. Create your account:\n"
            f"{settings.FRONTEND_URL.rstrip('/')}/join#token={token}\n"
            "You will also need to verify your email after joining.",
        )
        await self.db.commit()
        return InvitationCreated(
            id=invitation.id,
            email=email,
            role=payload.role,
            expires_at=invitation.expires_at,
            token=token,
        )

    async def invitations(self, actor: User, limit: int, offset: int) -> list[Invitation]:
        await self._require_manager(actor)
        rows = await self.db.scalars(
            select(Invitation)
            .where(
                Invitation.tenant_id == actor.tenant_id,
                Invitation.consumed_at.is_(None),
                Invitation.expires_at > datetime.now(UTC),
            )
            .order_by(Invitation.created_at, Invitation.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows)

    async def revoke_invitation(self, actor: User, invitation_id: UUID) -> None:
        await self._lock_organization(actor.tenant_id)
        await self._require_manager(actor)
        result = await self.db.execute(
            update(Invitation)
            .where(
                Invitation.id == invitation_id,
                Invitation.tenant_id == actor.tenant_id,
                Invitation.consumed_at.is_(None),
            )
            .values(consumed_at=datetime.now(UTC))
            .returning(Invitation.id)
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Invitation not found")
        await self.db.commit()

    async def accept(self, payload: AcceptInvitation) -> AuthSession:
        invitation = await self.db.scalar(
            select(Invitation).where(
                Invitation.token_hash == hash_refresh_token(payload.token),
            )
        )
        if invitation is None:
            raise HTTPException(status_code=400, detail="Invalid or expired invitation")
        organization = await self._lock_organization(invitation.tenant_id)
        now = datetime.now(UTC)
        claimed = await self.db.execute(
            update(Invitation)
            .where(
                Invitation.id == invitation.id,
                Invitation.consumed_at.is_(None),
                Invitation.expires_at > now,
            )
            .values(consumed_at=now)
            .returning(Invitation.id)
            .execution_options(synchronize_session=False)
        )
        if claimed.scalar_one_or_none() is None:
            await self.db.rollback()
            raise HTTPException(status_code=400, detail="Invalid or expired invitation")
        user = User(
            tenant=organization,
            email=invitation.email,
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
            role=UserRole(invitation.role),
        )
        self.db.add(user)
        try:
            await self.db.flush()
            self.db.add(
                Membership(
                    tenant_id=organization.id,
                    user_id=user.id,
                    role=user.role,
                )
            )
            await self.db.flush()
            await issue_account_token(self.db, user, "verify", user.email)
            return await AuthService(self.db).issue_session(user)
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(status_code=409, detail="Email already has an account") from exc
