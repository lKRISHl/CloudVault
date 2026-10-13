# Changelog

All notable changes to CloudVault will be documented in this file.

## [Unreleased] - 2026-10-13

### Fixed
- Correct Docker frontend port mapping and preserve API paths through Nginx.
- Apply migrations before development backend startup; exclude host dependencies and secrets from Docker build contexts.
- Atomically consume refresh tokens and share concurrent browser refresh requests.
- Reject unsafe production signing secrets and access tokens missing required claims.
- Align role column length with the existing migration.
- Restore the full Phase 0–33 roadmap and correct current-state documentation.

### Testing
- Add expired/invalid JWT, disabled-user, cross-tenant, stored-hash, expired-refresh, and concurrent-refresh coverage.
- Replay the saved logout cookie to verify server-side revocation.
- Add browser registration/login/logout, protected-route, session restore, and concurrent refresh tests.
- Verify actual Alembic upgrade, schema alignment, downgrade, and re-upgrade locally using SQLite.
- Add PostgreSQL-backed tests and migrations plus Docker/frontend/API registration smoke checks to CI; those infrastructure checks have not run on this host.

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
