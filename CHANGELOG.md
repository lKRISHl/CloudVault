# Changelog

All notable changes to CloudVault will be documented in this file.

## [Unreleased] - 2026-10-14

### Phase 2B — Multiple Organizations and Membership Lifecycle
- Separate global user identity from per-organization roles; migrate existing accounts/passwords and bind valid sessions to their prior workspace.
- Add verified existing-user invitation acceptance, workspace listing/creation/switching, and scoped removal/reactivation without disabling other memberships.
- Add confirmed password-protected ownership transfer, atomic owner replacement and final-owner protection during concurrent removal/demotion/transfer.
- Complete deletion across all memberships; require ownership transfer in every owned organization first.
- Reject stale frontend responses and cross-workspace retries; preserve independent public account actions during session restoration.
- Verify 92 backend tests on SQLite/PostgreSQL, 24 frontend component tests, 9 Chromium/SMTP journeys, migrations, lint/build, and updated Docker/storage runtime.
- Save an ignored pre-upgrade local database backup. Phase 3 remains unstarted; no commit/push/remote CI was performed for Phase 2B.

## [Unreleased] - 2026-10-13

### Development Infrastructure
- Install Docker Desktop/WSL and run PostgreSQL 16.15, Redis and Mailpit locally.
- Verify all 81 backend tests and full migration upgrade/check/downgrade/re-upgrade against a separate PostgreSQL test database.
- Replace unavailable MinIO server/client images with builds from pinned official source commits, keeping existing volumes and bucket configuration.
- Add a repeatable Docker HTTP/storage round-trip smoke check and include it in CI.
- Record archived MinIO community maintenance status as a production storage decision.

### Phase 2A — Account Lifecycle and Email Delivery
- Add verified-email gates, expiring single-use account challenges, password recovery, verified email changes, and current-password reauthentication.
- Add stable login sessions and live revocation checks; logout/recovery/session controls revoke access tokens as well as refresh cookies.
- Add an encrypted SMTP outbox, bounded retries/leases/deadlines, delivery status, Mailpit development configuration, and account-record retention maintenance.
- Add verified non-owner account deletion with explicit confirmation, profile/invitation redaction, token removal, and owner protection.
- Add persistent account/IP rate limits and generic recovery responses.
- Add account security/recovery/action screens and seven real Chromium journeys against a disposable backend and real localhost SMTP.
- Migration 003_accounts marks legacy addresses unverified and revokes old refresh cookies without replacing users/passwords.
- Update vulnerable frontend tooling/runtime packages; adapt Vitest matcher integration. Final npm audit reports zero known vulnerabilities at verification time.
- Local Docker/PostgreSQL verification passed in follow-up infrastructure work; remote CI and real production email-provider verification remain pending. Phase 2B has not started.

### Roadmap Extensions (Planned)
- Add Phase 2A for real email delivery, verification, password recovery, email changes, session revocation, and account deletion.
- Add Phase 2B for multiple organizations, workspace switching, existing-account invitations, ownership transfer, and removed-member reactivation.
- Add Phase 25A for provider-backed billing, subscription lifecycle, backend entitlements, and quota/AI usage enforcement.
- Define completion criteria and dependencies; keep PostgreSQL/Docker CI verification as an immediate pending gate. These are planning changes, not implemented features.

### Phase 2 — Users and Organizations
- Add self-service profile editing, organization display-name editing, paginated members, basic roles, and member removal.
- Add explicit memberships with tenant foreign-key constraints and role validation. Migration `002_memberships` backfills existing active users without replacing their accounts.
- Add private, expiring, revocable invitation links for new accounts; acceptance atomically creates the account, membership, and session.
- Enforce membership on login, refresh, and protected requests; role changes take effect using database permissions even with stale JWTs.
- Add settings and invitation acceptance screens, scoped query caching, auth cache clearing, and browser flow tests.
- Add tenant-isolation, role escalation, removal/revocation, replay, concurrent acceptance, rollback, and migration-backfill tests.
- PostgreSQL/Docker runtime verification remains pending CI; local database checks use SQLite with foreign keys enabled.

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
