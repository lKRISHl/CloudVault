# Changelog

All notable changes to CloudVault will be documented in this file.

## [0.2.0] - 2026-10-08

### Added
- Tenant and user models with Alembic migration
- Register, login, refresh, logout, and current-user auth API
- JWT access tokens and rotating HttpOnly refresh cookies
- Frontend login/register flow with session restore and protected routes

### Security
- Argon2id password hashing
- Tenant id bound into access tokens and checked on every authenticated request

## [0.1.0] - 2026-10-08

### Added
- Project foundation and repository structure
- FastAPI backend skeleton with health check endpoints
- React + TypeScript + Vite frontend skeleton
- PostgreSQL database configuration with async SQLAlchemy
- Alembic migration setup
- Docker Compose development environment
- Tailwind CSS styling
- TanStack Query integration
- Initial test suites (backend pytest, frontend vitest)
- Project documentation (AGENTS.md, ARCHITECTURE.md, etc.)
- GitHub Actions CI pipeline
- Environment configuration with Pydantic Settings
