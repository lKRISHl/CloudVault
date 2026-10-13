from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from jwt import InvalidTokenError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    dummy_password_hash,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.core.slugs import slugify, unique_slug
from app.models import Membership, RefreshToken, Tenant, User, UserRole
from app.models.account import LoginSession
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserRead
from app.services.accounts import AccountService, issue_account_token


@dataclass
class AuthSession:
    user: User
    access_token: str
    refresh_token: str
    expires_in: int

    def to_response(self) -> TokenResponse:
        return TokenResponse(
            access_token=self.access_token,
            expires_in=self.expires_in,
            user=UserRead.model_validate(self.user),
        )


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, payload: RegisterRequest) -> AuthSession:
        existing = await self._get_user_by_email(payload.email)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )

        slug = await self._allocate_slug(payload.tenant_name)
        tenant = Tenant(name=payload.tenant_name.strip(), slug=slug)
        self.db.add(tenant)
        user = User(
            tenant=tenant,
            email=payload.email.lower(),
            full_name=payload.full_name.strip(),
            password_hash=hash_password(payload.password),
            role=UserRole.OWNER,
        )
        self.db.add(user)
        try:
            await self.db.flush()
            self.db.add(Membership(tenant_id=tenant.id, user_id=user.id, role=UserRole.OWNER))
            await self.db.flush()
            await issue_account_token(self.db, user, "verify", user.email)
            return await self.issue_session(user)
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            ) from exc

    async def login(self, payload: LoginRequest) -> AuthSession:
        user = await self._get_user_by_email(payload.email.lower())
        password_hash = user.password_hash if user is not None else dummy_password_hash()
        password_ok = verify_password(payload.password, password_hash)

        if user is None or not password_ok or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        await self.select_default_workspace(user)
        return await self.issue_session(user)

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    async def refresh(self, raw_token: str | None) -> AuthSession:
        if not raw_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token missing",
            )

        token_hash = hash_refresh_token(raw_token)
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        stored = result.scalar_one_or_none()
        now = datetime.now(UTC)

        normalized_revoked_at = (
            self._normalize_datetime(stored.revoked_at) if stored is not None else None
        )
        normalized_expires_at = (
            self._normalize_datetime(stored.expires_at) if stored is not None else None
        )

        if (
            stored is None
            or stored.session_id is None
            or normalized_revoked_at is not None
            or normalized_expires_at is None
            or normalized_expires_at <= now
        ):
            if stored is not None and normalized_revoked_at is None:
                stored.revoked_at = now
                await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        user = await AccountService(self.db).lock_user(stored.user_id)

        # Claim the token atomically. A concurrent refresh/logout wins at most once.
        claimed = await self.db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.id == stored.id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .values(revoked_at=now)
            .returning(RefreshToken.id)
            .execution_options(synchronize_session=False)
        )
        if claimed.scalar_one_or_none() is None:
            await self.db.rollback()
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        session = await self.issue_session(user, stored.session_id)
        return session

    async def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        token_hash = hash_refresh_token(raw_token)
        stored = await self.db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        if stored is not None:
            await self.db.scalar(select(User.id).where(User.id == stored.user_id).with_for_update())
            await self.db.execute(
                update(LoginSession)
                .where(LoginSession.id == stored.session_id)
                .values(revoked_at=datetime.now(UTC))
            )
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await self.db.commit()

    async def get_user_in_tenant(self, user_id: UUID, tenant_id: UUID | None) -> User | None:
        user = await self.db.scalar(
            select(User).where(
                User.id == user_id, User.is_active.is_(True), User.deleted_at.is_(None)
            )
        )
        if user is None:
            return None
        user.tenant = None
        user.role = None
        if tenant_id is not None:
            row = (
                await self.db.execute(
                    select(Tenant, Membership.role)
                    .join(Membership, Membership.tenant_id == Tenant.id)
                    .where(
                        Membership.user_id == user_id,
                        Membership.tenant_id == tenant_id,
                        Membership.revoked_at.is_(None),
                    )
                )
            ).one_or_none()
            if row is None:
                return None
            user.tenant, user.role = row
        return user

    async def select_default_workspace(self, user: User) -> None:
        tenant_id = await self.db.scalar(
            select(Membership.tenant_id)
            .where(Membership.user_id == user.id, Membership.revoked_at.is_(None))
            .order_by(Membership.joined_at, Membership.tenant_id)
            .limit(1)
        )
        await self.get_user_in_tenant(user.id, tenant_id)

    def parse_access_token(self, token: str) -> tuple[UUID, UUID | None, UUID]:
        try:
            payload = decode_access_token(token)
        except InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid access token",
            ) from exc

        if payload.get("typ") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid access token",
            )

        try:
            return (
                UUID(str(payload["sub"])),
                UUID(str(payload["tid"])) if payload["tid"] else None,
                UUID(str(payload["sid"])),
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid access token",
            ) from exc

    async def valid_session(self, user_id: UUID, session_id: UUID, tenant_id: UUID | None) -> bool:
        return (
            await self.db.scalar(
                select(LoginSession.id).where(
                    LoginSession.id == session_id,
                    LoginSession.user_id == user_id,
                    LoginSession.tenant_id == tenant_id,
                    LoginSession.revoked_at.is_(None),
                    LoginSession.expires_at > datetime.now(UTC),
                )
            )
            is not None
        )

    async def issue_session(
        self, user: User, session_id: UUID | None = None, expires_at: datetime | None = None
    ) -> AuthSession:
        user = await AccountService(self.db).lock_user(user.id)
        now = datetime.now(UTC)
        if session_id is None:
            if await self.get_user_in_tenant(user.id, user.tenant_id) is None:
                raise HTTPException(status_code=401, detail="Organization membership required")
            login_session = LoginSession(
                user_id=user.id,
                tenant_id=user.tenant_id,
                expires_at=expires_at or now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            )
            self.db.add(login_session)
            await self.db.flush()
        else:
            login_session = await self.db.scalar(
                select(LoginSession)
                .where(
                    LoginSession.id == session_id,
                    LoginSession.user_id == user.id,
                    LoginSession.revoked_at.is_(None),
                    LoginSession.expires_at > now,
                )
                .with_for_update()
            )
            if login_session is None:
                await self.db.rollback()
                raise HTTPException(status_code=401, detail="Session revoked or expired")
            if await self.get_user_in_tenant(user.id, login_session.tenant_id) is None:
                raise HTTPException(status_code=401, detail="Organization membership required")
        raw_refresh = generate_refresh_token()
        refresh = RefreshToken(
            user_id=user.id,
            session_id=login_session.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=login_session.expires_at,
        )
        self.db.add(refresh)
        await self.db.commit()
        return AuthSession(
            user=user,
            access_token=create_access_token(
                user_id=user.id,
                tenant_id=user.tenant_id,
                role=user.role.value if user.role else "",
                session_id=login_session.id,
            ),
            refresh_token=raw_refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def _get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def _get_user_by_id(self, user_id: UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def _allocate_slug(self, tenant_name: str) -> str:
        base = slugify(tenant_name)
        result = await self.db.execute(select(Tenant.id).where(Tenant.slug == base))
        if result.scalar_one_or_none() is None:
            return base
        for _ in range(8):
            candidate = unique_slug(tenant_name)
            result = await self.db.execute(select(Tenant.id).where(Tenant.slug == candidate))
            if result.scalar_one_or_none() is None:
                return candidate
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to allocate a workspace slug",
        )
