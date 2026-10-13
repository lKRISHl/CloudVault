from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Membership, RefreshToken, Tenant, User, UserRole
from app.models.account import LoginSession
from app.schemas.auth import TenantRead
from app.schemas.organizations import WorkspaceRead
from app.services.accounts import AccountService
from app.services.auth import AuthService, AuthSession


class WorkspaceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, actor: User, offset: int, limit: int):
        rows = await self.db.execute(
            select(Tenant, Membership.role)
            .join(Membership, Membership.tenant_id == Tenant.id)
            .where(Membership.user_id == actor.id, Membership.revoked_at.is_(None))
            .order_by(Membership.joined_at, Tenant.id)
            .offset(offset)
            .limit(limit)
        )
        return [
            WorkspaceRead(tenant=TenantRead.model_validate(tenant), role=role)
            for tenant, role in rows
        ]

    async def switch(self, actor: User, current_session_id: UUID, tenant_id: UUID) -> AuthSession:
        user = await AccountService(self.db).lock_user(actor.id)
        current = await self.db.scalar(
            select(LoginSession)
            .where(
                LoginSession.id == current_session_id,
                LoginSession.user_id == user.id,
                LoginSession.revoked_at.is_(None),
                LoginSession.expires_at > datetime.now(UTC),
            )
            .with_for_update()
        )
        if current is None:
            raise HTTPException(status_code=401, detail="Session revoked or expired")
        if await AuthService(self.db).get_user_in_tenant(user.id, tenant_id) is None:
            raise HTTPException(status_code=403, detail="Workspace membership required")
        current.revoked_at = datetime.now(UTC)
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.session_id == current.id)
            .values(revoked_at=datetime.now(UTC))
        )
        await self.db.flush()
        return await AuthService(self.db).issue_session(user, expires_at=current.expires_at)

    async def create(self, actor: User, current_session_id: UUID, name: str) -> AuthSession:
        user = await AccountService(self.db).lock_user(actor.id)
        tenant = Tenant(name=name, slug=await AuthService(self.db)._allocate_slug(name))
        self.db.add(tenant)
        try:
            await self.db.flush()
            self.db.add(Membership(tenant_id=tenant.id, user_id=user.id, role=UserRole.OWNER))
            await self.db.flush()
            return await self.switch(user, current_session_id, tenant.id)
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=409, detail="Workspace name conflict; try again"
            ) from exc
