import ipaddress
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "CloudVault API"
    APP_VERSION: str = "0.1.0"
    PREVIEW_SOCKET: str = "/preview/renderer.sock"
    CLAMD_HOST: str = "clamav"
    CLAMD_PORT: int = Field(default=3310, ge=1, le=65535)
    SCAN_MAX_BYTES: int = Field(default=100 * 1024**2, ge=1, le=100 * 1024**2)
    SCAN_TIMEOUT_SECONDS: int = Field(default=90, ge=5, le=120)
    SCAN_DEFINITION_MAX_AGE_SECONDS: int = Field(default=86400, ge=3600, le=172800)
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    API_V1_PREFIX: str = "/api/v1"

    CORS_ORIGINS: list[str] = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
    ]
    CORS_ALLOW_CREDENTIALS: bool = True

    DATABASE_URL: str = "postgresql+asyncpg://cloudvault:cloudvault@localhost:5432/cloudvault"
    DATABASE_ECHO: bool = False

    REDIS_URL: str = "redis://localhost:6379/0"
    JOB_LEASE_SECONDS: int = Field(default=300, ge=240, le=900)
    STORAGE_STAGE_BATCH_SIZE: int = Field(default=5, ge=1, le=10)

    S3_ENDPOINT: str | None = None
    S3_PUBLIC_ENDPOINT: str | None = None
    UPLOAD_MAX_BYTES: int = Field(default=100 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)
    MULTIPART_MAX_BYTES: int = Field(default=1024 * 1024 * 1024, ge=1, le=5 * 1024**3)
    MULTIPART_PART_BYTES: int = Field(
        default=8 * 1024 * 1024, ge=5 * 1024 * 1024, le=32 * 1024 * 1024
    )
    MULTIPART_UPLOAD_SECONDS: int = Field(default=3600, ge=60, le=7200)
    UPLOAD_URL_SECONDS: int = Field(default=900, ge=60, le=1800)
    DOWNLOAD_URL_SECONDS: int = Field(default=300, ge=30, le=900)
    UPLOAD_COMPLETION_GRACE_SECONDS: int = Field(default=300, ge=0, le=600)
    UPLOAD_CLEANUP_INTERVAL_SECONDS: int = Field(default=60, ge=5, le=3600)
    UPLOAD_CLEANUP_SETTLE_SECONDS: int = Field(default=300, ge=60, le=86400)
    S3_ACCESS_KEY: SecretStr | None = None
    S3_SECRET_KEY: SecretStr | None = None
    S3_BUCKET_NAME: str | None = None
    S3_REGION: str = "us-east-1"
    S3_ADDRESSING_STYLE: Literal["path", "virtual", "auto"] = "path"
    S3_CONNECT_TIMEOUT_SECONDS: int = Field(default=3, ge=1, le=30)
    S3_READ_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=60)

    @model_validator(mode="after")
    def validate_storage(self) -> "Settings":
        if not self.S3_BUCKET_NAME:
            if any(
                (self.S3_ENDPOINT, self.S3_PUBLIC_ENDPOINT, self.S3_ACCESS_KEY, self.S3_SECRET_KEY)
            ):
                raise ValueError("Storage configuration requires S3_BUCKET_NAME")
            return self
        bucket = self.S3_BUCKET_NAME
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket) or any(
            part in bucket for part in ("..", ".-", "-.")
        ):
            raise ValueError("S3_BUCKET_NAME must be a DNS-compatible bucket name")
        try:
            ipaddress.ip_address(bucket)
        except ValueError:
            pass
        else:
            raise ValueError("S3_BUCKET_NAME cannot be an IP address")
        if bool(self.S3_ACCESS_KEY) != bool(self.S3_SECRET_KEY) or any(
            value is not None and not value.get_secret_value().strip()
            for value in (self.S3_ACCESS_KEY, self.S3_SECRET_KEY)
        ):
            raise ValueError("S3 credentials must be a complete nonempty pair")
        for origin in (self.S3_ENDPOINT, self.S3_PUBLIC_ENDPOINT):
            if not origin:
                continue
            endpoint = urlsplit(origin)
            if (
                endpoint.scheme not in ("http", "https")
                or not endpoint.hostname
                or endpoint.username
                or endpoint.password
                or endpoint.query
                or endpoint.fragment
                or endpoint.path not in ("", "/")
            ):
                raise ValueError("S3_ENDPOINT must be an HTTP(S) origin without credentials")
            if self.is_production and endpoint.scheme != "https":
                raise ValueError("Production storage requires HTTPS")
            if not self.S3_ACCESS_KEY:
                raise ValueError("Custom S3 endpoints require explicit credentials")
        if (
            self.is_production
            and self.S3_SECRET_KEY
            and self.S3_SECRET_KEY.get_secret_value() == "minioadmin"
        ):
            raise ValueError("Production storage requires non-default credentials")
        return self

    SECRET_KEY: str = "change-me-in-development-only-32bytes-min"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_COOKIE_NAME: str = "cv_refresh"
    FRONTEND_URL: str = "http://localhost:3000"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = Field(default=1025, ge=1, le=65535)
    SMTP_STARTTLS: bool = False
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAIL_FROM: str = "CloudVault <noreply@cloudvault.local>"
    ACCOUNT_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=1)
    RATE_LIMIT_MAX: int = Field(default=10, ge=1)
    RATE_LIMIT_IP_MAX: int = Field(default=100, ge=1)
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=900, ge=1)
    RECOVERY_RESPONSE_SECONDS: float = Field(default=0.2, ge=0, le=5)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        hide_input_in_errors=True,
    )

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @model_validator(mode="after")
    def validate_production_secret(self) -> "Settings":
        if self.is_production and (
            len(self.SECRET_KEY.encode("utf-8")) < 32
            or self.SECRET_KEY.lower().startswith("change-me")
        ):
            raise ValueError("Production requires a non-default SECRET_KEY of at least 32 bytes")
        if self.is_production and (
            not self.SMTP_STARTTLS or not self.FRONTEND_URL.startswith("https://")
        ):
            raise ValueError("Production requires SMTP STARTTLS and an HTTPS FRONTEND_URL")
        return self


settings = Settings()
