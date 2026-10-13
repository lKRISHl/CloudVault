# CloudVault — Current State

Current Phase:
Phase 1 — Authentication (Phase 0–1 corrective work)

Status:
Implementation fixes complete; local checks pass. Full Docker/PostgreSQL verification remains pending a CI run. Phase 2 has not started.

Completed Work:
- Phase 0 foundation: React/TypeScript/Vite/Tailwind/TanStack Query, FastAPI, configuration, PostgreSQL configuration, health checks, Docker Compose, CI, and project documentation.
- Phase 1: registration, login, Argon2id password hashing, JWT access tokens, rotating HttpOnly refresh cookies, logout, current-user endpoint, and protected frontend routes.
- Tenant/user/refresh-token models and initial Alembic migration; authenticated lookups enforce active status and matching tenant ID.
- Atomic conditional refresh-token consumption; replacement insertion and revocation commit together. Concurrent losers receive 401.
- Frontend shares pending refresh requests, including StrictMode session bootstrap and simultaneous unauthorized requests.
- Production startup rejects development signing keys and keys shorter than 32 bytes. JWT decoding requires expiry, subject, tenant, and token type.
- Corrected Compose frontend port and API proxy, added migration startup, and excluded host dependencies/secrets from Docker contexts.
- Restored the complete Phase 0–33 roadmap in DEVELOPMENT_PLAN.md.
- Added PostgreSQL-backed tests, migration round-trip checks, and Docker smoke verification to CI.

Files Changed:
- Backend: app/core/config.py, app/core/security.py, app/models/user.py, app/services/auth.py, .dockerignore.
- Backend tests: tests/conftest.py, tests/api/test_auth.py, tests/api/test_auth_security.py, tests/api/test_health.py, tests/test_migrations.py.
- Frontend: src/auth/AuthContext.tsx, src/services/api.ts, src/__tests__/AuthFlows.test.tsx, nginx.conf, Dockerfile, .dockerignore.
- Infrastructure: docker-compose.yml, .github/workflows/ci.yml.
- Documentation: DEVELOPMENT_PLAN.md, CONTINUE.md, CHANGELOG.md, README.md, SECURITY.md, DECISIONS.md.

Tests Passed:
- Backend: 28 tests passed locally using temporary SQLite databases.
- Security cases: expired/invalid/malformed JWTs, missing expiry, wrong token type, genuine tenant mismatch, disabled user, expired refresh token, concurrent refresh, logout-cookie replay, stored hashes, and production secret validation.
- Real Alembic upgrade, model alignment, downgrade, and re-upgrade passed against SQLite.
- Frontend: 9 tests passed, covering rendering, registration, login success/failure, logout, protected routes, StrictMode session restore, and shared concurrent refresh.
- Ruff and ESLint passed; TypeScript/Vite production build passed.
- React Router emits future-version migration warnings during tests.

Known Issues / Verification Limits:
- Docker and PostgreSQL executables are unavailable here. Full Compose startup and PostgreSQL migration/concurrency checks have not been executed locally or remotely during this work. CI contains those checks; do not claim they passed until a run confirms it.
- Local backend tests use SQLite. TEST_DATABASE_URL enables PostgreSQL tests against a dedicated disposable database; fixtures remove application tables.
- Logout revokes the presented refresh token; existing access tokens remain valid until expiry.
- Shared refresh coordination is within one tab; cross-tab coordination and token-family replay handling remain future security work.
- Rate limiting and broader hardening belong to later phases. No commercial-readiness claim is made.
- Compose uses development credentials and a single-backend migration startup; production migration orchestration is deferred.

Architecture Changes:
- No new application service or phase introduced. Refresh-token consumption now uses an atomic conditional database update.
- Role enum length explicitly matches the existing VARCHAR(20) migration; no new migration is needed.

Important Decisions:
- ADR-006: JWT access tokens plus rotating refresh cookies.
- ADR-007: One tenant per user at registration; organization membership is planned in Phase 2.
- ADR-008: Atomic refresh rotation and shared browser refresh.
- ADR-009: Full roadmap alignment, development startup, and infrastructure verification in CI.

Next Exact Phase:
Phase 2 — Users + Organizations, only on explicit user instruction. Obtain a successful Docker/PostgreSQL CI run before describing Phases 0–1 as fully verified.

Last Verified State:
2026-10-13 — 28 backend tests, 9 frontend tests, Ruff, ESLint, and frontend build passed locally. Infrastructure CI checks pending.

Last Commit:
Phase 0–1 corrective commit: `fix: harden phase 0-1 authentication and align master roadmap` (this commit). Previous Phase 1 commit: bae5096. No push was performed.

Suggested Git Commit:
fix: harden phase 0-1 authentication and align master roadmap
