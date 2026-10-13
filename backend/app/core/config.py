from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "CloudVault API"
    APP_VERSION: str = "0.1.0"
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

    S3_ENDPOINT: str | None = None
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None
    S3_BUCKET_NAME: str | None = None
    S3_REGION: str | None = None

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
