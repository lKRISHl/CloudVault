# CloudVault — Current State

Current Phase:
Phase 1 — Authentication

Status:
Complete

Completed:
- User and Tenant domain models with SQLAlchemy 2.0 async mapped classes
- Initial Alembic migration `001_auth_tenants_users.py` creating `tenants`, `users`, and `refresh_tokens` tables with foreign keys and unique indexes
- Argon2id password hashing via `argon2-cffi` with constant-time dummy verify fallback on login misses
- Dual-token auth system: 15-minute JWT access tokens carrying `sub`, `tid` (tenant ID), and `role`; rotating 7-day refresh tokens delivered via HttpOnly, SameSite=lax cookies
- Database persistence of SHA-256 refresh token fingerprints with explicit revocation timestamps
- FastAPI authentication API under `/api/v1/auth`:
  - `POST /register`: Atomic workspace & owner creation with slug generation
  - `POST /login`: Timing-safe authentication returning bearer token and refresh cookie
  - `POST /refresh`: Rotating refresh token validation and re-issuance
  - `POST /logout`: Refresh token revocation and cookie clearing
  - `GET /me`: Tenant-scoped user profile retrieval
- Reusable FastAPI dependencies (`get_current_user`, `get_current_tenant_id`) enforcing active user status and tenant boundary
- Frontend authentication layer (`frontend/src/auth/`):
  - `AuthContext` providing user state, login, registration, and logout
  - Silent session bootstrap on app startup via refresh cookie
  - Axios/Fetch interceptors automatically attaching Bearer access token
  - Responsive, Tailwind-styled `LoginPage` and `RegisterPage` with form validation and error handling
  - Protected navigation in `App.tsx` with authenticated user profile and logout controls

Tests:
- Backend: 15 passed, 0 warnings (100% pass rate)
  - `test_register_creates_owner_and_sets_refresh_cookie`: PASS
  - `test_register_rejects_duplicate_email`: PASS
  - `test_register_rejects_short_password`: PASS
  - `test_login_and_me`: PASS
  - `test_login_rejects_bad_password`: PASS
  - `test_me_requires_auth`: PASS
  - `test_refresh_rotates_cookie`: PASS
  - `test_logout_revokes_refresh_token`: PASS
  - `test_access_token_is_tenant_scoped`: PASS
  - `test_access_token_rejects_wrong_type`: PASS
  - `test_liveness_returns_ok`: PASS
  - `test_liveness_content_type`: PASS
  - `test_readiness_structure`: PASS
  - `test_readiness_db_down_without_postgres`: PASS
  - `test_root_endpoint`: PASS
- Frontend: 3 passed (100% pass rate)
  - `LoginPage > shows sign-in controls`: PASS
  - `App > renders without crashing`: PASS
  - `App > displays the correct tagline`: PASS
- Linters:
  - Backend: `ruff check .` — All checks passed!
  - Frontend: `npm run lint` — ESLint 0 warnings, 0 errors!
- Build:
  - Frontend: `npm run build` — Clean production bundle in `dist/`

Known Issues:
- Docker daemon is not installed on the local Windows host; local verification runs directly on Python 3.13 and Node 24.
- In Vitest, `--pool=forks --no-file-parallelism` is configured for stable test execution on Node 24 on Windows.

Architecture Changes:
- Established `/api/v1/auth` endpoints.
- Bound tenant identification directly into JWT access token claims (`tid`) to enforce multi-tenant isolation at the authorization layer.
- Added `refresh_tokens` table to enable instant server-side revocation of sessions without storing raw secret material.

Important Decisions:
- ADR-006: JWT Access Tokens + Rotating Refresh Cookies (tokens in memory, refresh in HttpOnly cookie, hashed fingerprint in DB).
- ADR-007: One Tenant per User at Registration (owner workspace initialized immediately).

Next Exact Phase:
Phase 2 — Users + Organizations

Last Verified State:
2026-10-09T19:12:00+05:30 (Pytest: 15 passed, Vitest: 3 passed, Ruff: clean, ESLint: clean, Vite Build: successful)

Last Commit:
Pending Phase 1 commit
