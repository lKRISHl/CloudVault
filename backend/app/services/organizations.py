from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import generate_refresh_token, hash_password, hash_refresh_token
from app.models import Invitation, Membership, RefreshToken, Tenant, User, UserRole
from app.models.account import LoginSession
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
        actor = await AccountService(self.db).lock_user(actor.id)
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
                Membership.revoked_at.is_(None),
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
                Membership.revoked_at.is_(None),
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
                    Membership.revoked_at.is_(None),
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
        manager = Membership.__table__.alias("manager")
        authorized = (
            select(manager.c.user_id)
            .where(
                manager.c.user_id == actor.id,
                manager.c.tenant_id == actor.tenant_id,
                manager.c.role == UserRole.OWNER,
                manager.c.revoked_at.is_(None),
            )
            .exists()
        )
        changed = await self.db.scalar(
            update(Membership)
            .where(
                Membership.tenant_id == actor.tenant_id,
                Membership.user_id == user_id,
                Membership.revoked_at.is_(None),
                Membership.role != UserRole.OWNER,
                authorized,
            )
            .values(role=UserRole(role))
            .returning(Membership.user_id)
            .execution_options(synchronize_session="fetch")
        )
        if changed is None:
            raise HTTPException(status_code=409, detail="Membership or authority changed; reload")
        from app.models import ShareLink

        await self.db.execute(
            update(ShareLink)
            .where(
                ShareLink.tenant_id == actor.tenant_id,
                ShareLink.created_by == user_id,
                ShareLink.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
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
        manager = Membership.__table__.alias("manager")
        authorized = (
            select(manager.c.user_id)
            .where(
                manager.c.user_id == actor.id,
                manager.c.tenant_id == actor.tenant_id,
                manager.c.revoked_at.is_(None),
                or_(
                    manager.c.role == UserRole.OWNER,
                    and_(manager.c.role == UserRole.ADMIN, Membership.role == UserRole.MEMBER),
                ),
            )
            .correlate(Membership)
            .exists()
        )
        removed = await self.db.scalar(
            update(Membership)
            .where(
                Membership.tenant_id == actor.tenant_id,
                Membership.user_id == user_id,
                Membership.revoked_at.is_(None),
                Membership.role != UserRole.OWNER,
                authorized,
            )
            .values(revoked_at=datetime.now(UTC))
            .returning(Membership.user_id)
            .execution_options(synchronize_session="fetch")
        )
        if removed is None:
            raise HTTPException(status_code=409, detail="Membership or authority changed; reload")
        from sqlalchemy import delete

        from app.models import GroupMember, ResourceGrant

        await self.db.execute(
            delete(GroupMember).where(
                GroupMember.tenant_id == actor.tenant_id, GroupMember.user_id == user_id
            )
        )
        await self.db.execute(
            delete(ResourceGrant).where(
                ResourceGrant.tenant_id == actor.tenant_id,
                ResourceGrant.user_id == user_id,
            )
        )
        await self.db.execute(
            update(LoginSession)
            .where(LoginSession.user_id == user_id, LoginSession.tenant_id == actor.tenant_id)
            .values(revoked_at=datetime.now(UTC))
        )
        await self.db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.session_id.in_(
                    select(LoginSession.id).where(LoginSession.tenant_id == actor.tenant_id)
                ),
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        from app.models import ShareLink

        await self.db.execute(
            update(ShareLink)
            .where(
                ShareLink.tenant_id == actor.tenant_id,
                ShareLink.created_by == user_id,
                ShareLink.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        await self._revoke_invitations(user.id, actor.tenant_id)
        await self.db.execute(
            update(Invitation)
            .where(Invitation.tenant_id == actor.tenant_id, Invitation.email == user.email)
            .values(consumed_at=datetime.now(UTC))
        )
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
        existing = await self.db.scalar(select(User).where(User.email == email))
        membership = (
            await self.db.get(Membership, (actor.tenant_id, existing.id)) if existing else None
        )
        if membership and membership.revoked_at is None:
            raise HTTPException(status_code=409, detail="Already a member of this organization")
        if membership and actor_role != UserRole.OWNER:
            raise HTTPException(
                status_code=403, detail="Only the owner can re-invite removed members"
            )
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
            reactivation=membership is not None,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        self.db.add(invitation)
        queue_email(
            self.db,
            actor.id,
            "invitation",
            email,
            "Join your CloudVault organization",
            f"You were invited to {actor.tenant.name}. Sign in or create your account:\n"
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
        await self._check_issuer(invitation)
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

    async def _check_issuer(self, invitation: Invitation) -> None:
        role = await self.db.scalar(
            select(Membership.role)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.tenant_id == invitation.tenant_id,
                Membership.user_id == invitation.created_by,
                Membership.revoked_at.is_(None),
                User.is_active.is_(True),
                User.email_verified.is_(True),
            )
        )
        if role not in (UserRole.OWNER, UserRole.ADMIN) or (
            (invitation.role == "admin" or invitation.reactivation) and role != UserRole.OWNER
        ):
            raise HTTPException(status_code=400, detail="Invitation is no longer authorized")

    async def accept_existing(self, actor: User, token: str) -> Tenant:
        invitation = await self.db.scalar(
            select(Invitation).where(Invitation.token_hash == hash_refresh_token(token))
        )
        if invitation is None:
            raise HTTPException(status_code=400, detail="Invalid or expired invitation")
        organization = await self._lock_organization(invitation.tenant_id)
        user = await AccountService(self.db).lock_user(actor.id)
        if not user.email_verified or user.email != invitation.email:
            raise HTTPException(
                status_code=403,
                detail="Sign in with the verified email addressed by this invitation",
            )
        await self._check_issuer(invitation)
        membership = await self.db.get(Membership, (organization.id, user.id))
        if membership and membership.revoked_at is None:
            raise HTTPException(status_code=409, detail="Already a member of this organization")
        if membership and not invitation.reactivation:
            raise HTTPException(
                status_code=400, detail="Ask the owner for a new reactivation invitation"
            )
        claimed = await self.db.scalar(
            update(Invitation)
            .where(
                Invitation.id == invitation.id,
                Invitation.consumed_at.is_(None),
                Invitation.expires_at > datetime.now(UTC),
            )
            .values(consumed_at=datetime.now(UTC))
            .returning(Invitation.id)
            .execution_options(synchronize_session=False)
        )
        if claimed is None:
            raise HTTPException(status_code=400, detail="Invalid or expired invitation")
        if membership:
            membership.revoked_at = None
            membership.role = UserRole(invitation.role)
            membership.joined_at = datetime.now(UTC)
        else:
            self.db.add(
                Membership(
                    tenant_id=organization.id, user_id=user.id, role=UserRole(invitation.role)
                )
            )
        await self.db.commit()
        return organization

    async def transfer(self, actor: User, target_id: UUID, password: str) -> None:
        await self._lock_organization(actor.tenant_id)
        if await self._require_manager(actor) != UserRole.OWNER:
            raise HTTPException(status_code=403, detail="Only the owner can transfer ownership")
        if target_id == actor.id:
            raise HTTPException(status_code=409, detail="Choose another active member")
        await self._target(actor, target_id)
        # Tenant before users; stable user ordering avoids inverse pair locks.
        for user_id in sorted((actor.id, target_id), key=str):
            await AccountService(self.db).lock_user(user_id)
        AccountService.reauthenticate(actor, password)
        target, membership = await self._target(actor, target_id)
        if not target.email_verified:
            raise HTTPException(status_code=409, detail="The new owner must verify their email")
        demoted = await self.db.scalar(
            update(Membership)
            .where(
                Membership.tenant_id == actor.tenant_id,
                Membership.user_id == actor.id,
                Membership.role == UserRole.OWNER,
                Membership.revoked_at.is_(None),
            )
            .values(role=UserRole.ADMIN)
            .returning(Membership.user_id)
            .execution_options(synchronize_session=False)
        )
        if demoted is None:
            await self.db.rollback()
            raise HTTPException(status_code=403, detail="Ownership changed; reload and try again")
        promoted = await self.db.scalar(
            update(Membership)
            .where(
                Membership.tenant_id == actor.tenant_id,
                Membership.user_id == target_id,
                Membership.revoked_at.is_(None),
            )
            .values(role=UserRole.OWNER)
            .returning(Membership.user_id)
            .execution_options(synchronize_session=False)
        )
        if promoted is None:
            await self.db.rollback()
            raise HTTPException(status_code=409, detail="Target membership changed; try again")
        from app.models import ShareLink

        await self.db.execute(
            update(ShareLink)
            .where(
                ShareLink.tenant_id == actor.tenant_id,
                ShareLink.created_by.in_([actor.id, target_id]),
                ShareLink.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        await self._revoke_invitations(actor.id, actor.tenant_id)
        await self.db.commit()
