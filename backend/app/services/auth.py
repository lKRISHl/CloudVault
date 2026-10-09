from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
from app.models import RefreshToken, Tenant, User, UserRole
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserRead


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
        user = User(
            tenant=tenant,
            email=payload.email.lower(),
            full_name=payload.full_name.strip(),
            password_hash=hash_password(payload.password),
            role=UserRole.OWNER,
        )
        self.db.add(user)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            ) from exc

        user = await self._get_user_by_id(user.id)
        assert user is not None
        return await self._issue_session(user)

    async def login(self, payload: LoginRequest) -> AuthSession:
        user = await self._get_user_by_email(payload.email.lower())
        password_hash = user.password_hash if user is not None else dummy_password_hash()
        password_ok = verify_password(payload.password, password_hash)

        if user is None or not password_ok or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        return await self._issue_session(user)

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
            select(RefreshToken)
            .options(selectinload(RefreshToken.user).selectinload(User.tenant))
            .where(RefreshToken.token_hash == token_hash)
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
            or normalized_revoked_at is not None
            or normalized_expires_at is None
            or normalized_expires_at <= now
            or not stored.user.is_active
        ):
            if stored is not None and normalized_revoked_at is None:
                stored.revoked_at = now
                await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        stored.revoked_at = now
        session = await self._issue_session(stored.user)
        await self.db.commit()
        return session

    async def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        token_hash = hash_refresh_token(raw_token)
        query = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        result = await self.db.execute(query)
        stored = result.scalar_one_or_none()
        if stored is not None and stored.revoked_at is None:
            stored.revoked_at = datetime.now(UTC)
            await self.db.commit()

    async def get_user_in_tenant(self, user_id: UUID, tenant_id: UUID) -> User | None:
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.tenant))
            .where(User.id == user_id, User.tenant_id == tenant_id, User.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    def parse_access_token(self, token: str) -> tuple[UUID, UUID]:
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
            return UUID(str(payload["sub"])), UUID(str(payload["tid"]))
        except (KeyError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid access token",
            ) from exc

    async def _issue_session(self, user: User) -> AuthSession:
        raw_refresh = generate_refresh_token()
        refresh = RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        self.db.add(refresh)
        await self.db.commit()
        return AuthSession(
            user=user,
            access_token=create_access_token(
                user_id=user.id, tenant_id=user.tenant_id, role=user.role.value
            ),
            refresh_token=raw_refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def _get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).options(selectinload(User.tenant)).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def _get_user_by_id(self, user_id: UUID) -> User | None:
        result = await self.db.execute(
            select(User).options(selectinload(User.tenant)).where(User.id == user_id)
        )
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
