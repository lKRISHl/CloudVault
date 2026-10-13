# CloudVault — Current State

Current Phase:
Phase 2A — Email, Account Recovery + Session Lifecycle

Status:
Implementation and local verification complete. Full Docker Compose development stack now runs, including source-built MinIO and setup client. All 81 backend tests and the migration cycle pass against a disposable PostgreSQL database. HTTP/storage round-trip and registration-to-Mailpit dispatcher checks pass. Real production email-provider verification and remote CI remain pending. Phase 2B and Phase 3 have not started.

Completed Work:
- Phase 0–2 foundations remain: modular FastAPI/React application, authentication, explicit organization memberships, roles, profile editing, invitation onboarding, and tenant isolation.
- Phase 2A adds verification on registration/invitation acceptance, purpose-bound single-use account challenges, generic recovery, password reset, email changes, and current-password reauthentication.
- Organization features require verified email. Invitation possession alone does not verify the recipient's address.
- Stable database login sessions are referenced by JWT sid claims. Refresh preserves the same session and absolute deadline. Logout, reset, email confirmation, and session controls reject subsequent access-token and refresh-cookie use.
- Encrypted SMTP outbox with delivery leases, bounded retry, challenge-aligned deadlines, safe delivery status, and payload clearing. Compose adds Mailpit and a dedicated dispatcher; general Celery infrastructure remains future work.
- Persistent atomic per-IP/per-account rate limits, generic recovery responses, and minimum recovery response duration.
- Verified non-owner deletion requires password and explicit DELETE confirmation. Membership/challenges/access are removed or revoked; profile/incoming invitation addresses are redacted. Owners are protected until Phase 2B ownership transfer.
- Technical maintenance clears expired rate counters and obsolete account/token/session/invitation/outbox records; minimal identity tombstones remain for referential integrity.
- New account recovery/action/security screens, verified-email UI gating, and real Chromium journeys against a disposable migrated database and actual loopback SMTP delivery.
- Upgrade affected frontend dependencies identified by npm audit; preserve the existing stack and use Vitest-specific DOM matcher integration.

Files Changed:
- Backend account models/schemas/API/services: app/models/account.py, app/models/user.py, app/models/refresh_token.py, app/models/__init__.py, app/schemas/accounts.py, app/schemas/auth.py, app/api/accounts.py, app/api/auth.py, app/api/deps.py, app/api/organizations.py, app/api/router.py, app/services/accounts.py, app/services/auth.py, app/services/email.py, app/services/organizations.py, app/core/config.py, app/core/security.py, app/jobs/deliver_email.py.
- Migrations: migrations/versions/002_organizations_memberships.py and 003_account_lifecycle.py.
- Backend tests: tests/api/test_accounts.py, existing auth/organization regression helpers, tests/test_email_delivery.py, tests/test_account_retention.py, tests/test_migrations.py.
- Frontend: src/features/accounts/, src/features/organizations/SettingsPage.tsx, src/auth/AuthContext.tsx, src/services/api.ts, src/types/index.ts, app/routes and login/home links, setupTests.ts, package.json/package-lock.json, vite.config.ts, playwright.config.ts, e2e/accounts.pw.ts.
- Infrastructure/testing: docker-compose.yml, .env.example, .github/workflows/ci.yml, .gitignore, frontend/.dockerignore, scripts/account_e2e_stack.py.
- Documentation: docs/phases/phase2a.md, docs/phases/README.md, README.md, SECURITY.md, ARCHITECTURE.md, PROJECT_CONTEXT.md, DECISIONS.md, CHANGELOG.md, DEVELOPMENT_PLAN.md, CONTINUE.md.

Tests Passed:
- Backend: 81 tests passed locally using SQLite with foreign keys enabled, including real localhost SMTP integration.
- Coverage: purpose/expiry/replacement/replay, generic unknown recovery, email-change password/account binding and uniqueness-race rollback, immediate session revocation, stable refresh sessions, scoped session IDs, owner deletion protection, explicit confirmation/redaction, rate limits, actual SMTP delivery/failure/retry/expiry, concurrent reset, retention preserving active sessions, and legacy migration preservation/revocation.
- Frontend component tests: 20 passed. Real Chromium account journeys: 7 passed against a disposable migrated backend and real localhost SMTP, including verification after session revocation.
- Ruff, ESLint, TypeScript/Vite production build passed. npm audit reports zero known vulnerabilities for the installed graph at verification time.
- Alembic upgrade/check/downgrade/re-upgrade and seeded existing-data tests pass locally. Existing password hashes/identities remain; legacy email addresses become unverified and refresh cookies are revoked.

Known Issues / Verification Limits:
- Docker Desktop 4.95.0 (Engine 29.8.2, Compose v5.6.0) and Microsoft WSL 2.7.13 are installed. PostgreSQL 16.15, Redis and Mailpit are running through Compose; Mailpit returns HTTP 200 at localhost:8025. PostgreSQL tests use separate cloudvault_test, never cloudvault. All 81 backend tests and Alembic upgrade/check/downgrade/re-upgrade pass on PostgreSQL. Remote CI remains unrun; no push or dispatch was performed.
- Unavailable public MinIO images are replaced by source builds from pinned official commits in infra/minio/Dockerfile. Full `docker compose up --build -d` succeeds. MinIO bucket setup exits 0; API waits for it. scripts/docker_smoke.py passes HTTP checks plus actual object upload/read/delete. Registration through the frontend proxy queues a verification email delivered once to Mailpit by the Compose dispatcher. Smoke data uses a uniquely named development account/workspace.
- Initial builds exhausted Windows virtual-memory capacity. WSL is limited to 4 GB in the host's .wslconfig; Go builds use one worker and a conservative memory budget. Upstream community MinIO repositories are archived/unmaintained; production needs a maintained S3 deployment/provider decision.
- Production SMTP delivery requires real provider/TLS/from-address configuration; local SMTP acceptance and inbox delivery do not establish production inbox placement.
- Migration 003_accounts intentionally requires existing users to sign in again and verify their email. Legacy JWTs without session IDs are rejected; no legacy address is assumed verified.
- One organization per account. Ownership transfer, multiple workspaces, existing-account invitations, reactivation, and complete multi-organization deletion belong to Phase 2B.
- SMTP can duplicate a message after an ambiguous acknowledgement/crash. Account actions are single-use; no exactly-once email guarantee is claimed.
- Outbox encryption is derived from SECRET_KEY. Coordinate key rotation across API/dispatcher and resend affected pending links.
- Generic recovery and a minimum duration reduce enumeration signals; response timing is not formally constant under all database load.
- No MFA or recovery without access to the bound mailbox; broader abuse controls, token-family replay response, cross-tab coordination, and independent security review remain future work.
- Deletion redacts personal fields but retains minimal IDs/timestamps/role and tenant references for integrity; no legal-compliance or complete-metadata-erasure claim is made.

Architecture Changes:
- Add account_tokens, login_sessions, email_outbox, rate_limits, email verification/deletion fields, and refresh-to-session linkage.
- Account changes and their queued emails share database transactions. Protected access now depends on live session state as well as membership.
- Email delivery/maintenance is a small dedicated process, not general Celery infrastructure. Runtime uses shared database state rather than process-local auth/rate counters.

Important Decisions:
- ADR-010/011: existing tenant organization model, explicit membership, invitations, and serialized management.
- ADR-013: verified account actions and live session revocation; conservative legacy migration.
- ADR-014: encrypted SMTP outbox, bounded delivery, technical retention, and at-least-once transport limitations.
- ADR-015: actual browser/SMTP verification and dependency security updates.

Next Exact Phase:
Phase 2B — Multiple Organizations + Membership Lifecycle, only on explicit instruction. Local PostgreSQL/Docker verification is complete; remote CI requires authorized push/dispatch. Phase 3 remains unstarted.

Last Verified State:
2026-10-13 — 81 backend tests pass on PostgreSQL as well as prior SQLite checks; PostgreSQL migration cycle, full Docker startup, HTTP/storage smoke and Compose registration email delivery pass. Prior 20 frontend component tests, 7 Chromium/SMTP journeys, Ruff, ESLint, production build and npm audit passed. Production provider and remote CI checks remain pending.

Commit Checkpoint:
This checkpoint records completed Phase 2, Phase 2A and verified Docker storage startup work before Phase 2B. Previous checkpoint: def0420 — fix: harden phase 0-1 authentication and align master roadmap. Nothing was pushed.

Checkpoint Commit Message:
feat: add organizations and verified account lifecycle

Phase reports live in docs/phases/, named phase2.md, phase2a.md, phase2b.md, etc. Add completed reports to docs/phases/README.md; do not create placeholders for unimplemented phases.
