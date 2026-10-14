# Changelog

All notable changes to CloudVault will be documented in this file.

## [Unreleased] - 2026-10-15

### Phase 10 — File Search
- Add current-member tenant-scoped literal filename search, Unicode normalization,
  metadata filters, direct folder/root scope, whitelisted sorting and bounded pagination.
- Exclude cleanup tombstones/private storage references; join folder names by tenant.
- Add partial tenant B-tree and PostgreSQL pg_trgm GIN indexes via 010_file_search,
  preserving data and supporting index-only rollback without dropping shared extensions.
- Add search page/navigation/folder shortcut, submitted filters, page controls, current
  folder links/downloads and workspace/user cache/cancellation guards.
- Verify 214 SQLite/PostgreSQL backend tests, 60 frontend tests, 15 browser journeys,
  schema/data-preserving migrations, synthetic index paths and Docker real search/transfer
  checks. Save an ignored pre-upgrade backup. No benchmark/remote CI/production claim.
- Phase 9 was committed as 0551f25; Phase 10 remains uncommitted.

### Phase 9 — Resumable Uploads
- Add creator-authorized provider-reconciled progress and original-manifest resume.
  Reload recovery uses original chunk size/deadline and transfers only missing parts.
- Add saved-progress UI, reselected-content checks, completion-grace verification and
  safe expired/error handling. Keep bounded retries and credential-free storage transfer.
- Persist initialization intent before provider creation to recover exact keys after
  lost acknowledgements. Retain hidden cleanup references for repeated late-write sweeps.
- Add periodic maintenance in Compose/direct setups: expiry/grace/settling guards,
  provider abort/delete verification, name reclamation and versioned-bucket refusal.
- Add partial name indexes and rollback guards in 009_upload_cleanup, preserving data.
- Address MinIO inventory behavior with durable exact-key recovery; configure local
  stale-upload expiry/hourly scan. Production provider/lifecycle verification remains.
- Pass 206 SQLite/PostgreSQL backend tests with actual storage, 53 frontend tests,
  14 browser journeys, lint/build, migrations and Docker upload/resume/download/maintenance.
- Commit previous phases as 670d2a0; Phase 9 remains uncommitted. No remote CI/push.

## [Unreleased] - 2026-10-14

### Phase 8 — Chunked/Multipart Uploads
- Add creator/tenant/parent-authorized multipart initiation, signed chunk grants,
  independently verified part receipts, conditional completion and explicit cancellation.
- Hash bounded browser slices, transfer directly without account credentials, reconcile
  acknowledgements and retry failed parts up to three times. Same-form retries skip
  confirmed parts; cancelled rows remain visible with reserved names.
- Persist transfer mode/state/private provider identity and part receipts through
  008_multipart, preserving basic uploads and refusing destructive rollback.
- Identify SHA-256 composite checksums explicitly and adapt downloads to provider suffixes.
- Default to 1 GiB maximum, 8 MiB chunks and one-hour deadline; configure bounded limits
  through Compose/environment and separate part-grant/confirmation rate budgets.
- Verify 197 backend tests on SQLite/PostgreSQL with real storage, 49 frontend tests,
  14 browser journeys, lint/build, schema alignment and Docker real SMTP/basic/multipart
  upload/download smoke. Save an ignored pre-upgrade database backup.
- Recover test-server memory/Docker interruptions and rerun complete checks successfully.
  Phase 9 reload resume/automated cleanup is next; remote CI/production gates remain.

### Phase 6 — Basic Upload
- Add creator/workspace/parent-authorized pending reservations and signed length/checksum/conditional direct PUT.
- Persist object identity and verified completion metadata; enforce upload state constraints, idempotency, expiry, retry and persistent rate limits.
- Add upload selection/stages/errors/retry and verified/unscanned file listing, with session-generation guards and no app credentials sent to storage.
- Add public signing endpoint and private exact-origin local storage CORS; migration 007_uploads preserves legacy metadata and guards reference loss.
- Verify 174 backend tests on SQLite/PostgreSQL with real MinIO, 39 frontend tests, 12 Chromium/SMTP/storage journeys, lint/build, migrations and actual Docker API upload smoke.
- Save an ignored pre-upgrade backup and add reliable disposable browser-bucket teardown; fix the upload test destination-render wait. Docker smoke demo data remains.
- Phase 7 remains unstarted. Phases 4–6 remain uncommitted; remote CI and production provider verification remain pending.

### Phase 5 — Object Storage
- Add tenant-scoped S3 protocol/adapter, UUID-only storage keys, safe provider errors and Boto3 dependency.
- Add private bucket provisioning and complete/redacted/validated storage configuration with production HTTPS checks.
- Add conditional small writes, actual metadata inspection, bounded reads with generation/length checks and reliable stream cleanup, plus idempotent local deletion.
- Add configured-adapter Docker smoke and three real disposable-bucket contract tests; CI definitions include these checks.
- Verify 158 backend tests on SQLite/PostgreSQL with actual MinIO, Ruff, Docker rebuild/schema/private-access/storage smoke. Recover an initial Docker export interruption and rerun affected tests separately from builds.
- Phase 5 completion preceded Phase 6; current progress is recorded above. No remote CI or production provider verification was run.

### Phase 4 — File Metadata
- Add tenant-isolated pending file metadata, declared size/type, folder/creator relationships, normalized names, uniqueness and listing/provenance indexes.
- Add internal authorized reservations and paginated read/list APIs; no fake uploads, public metadata creation or download URLs.
- Add pending metadata listing to the folder browser with empty/error/retry and separate pagination states.
- Preserve files across folder moves and creator deletion; add populated downgrade protection and an ignored pre-upgrade backup.
- Verify 131 backend tests on SQLite/PostgreSQL, 31 frontend tests, 11 Chromium journeys, migrations, lint/build and rebuilt Docker at 006_files. Fix an existing browser test race while waiting for workspace listings. Phase 4 remains uncommitted; Phase 5 progress is recorded above.

### Phase 3 — Folder System
- Add tenant-scoped folders with parent/tenant integrity, stable identifiers, normalized sibling names, child-list indexes and timestamps.
- Add create/rename/move/list/detail services and API, breadcrumbs/pagination, depth/cycle protection and concurrent structural serialization.
- Add shared-workspace permissions: verified active members read, creators/owners/admins write; destination parents require write authority.
- Add folder browser and move destination picker, with visible failures/retry and tenant/user-scoped queries. Avoid automatically retrying missing/forbidden resources.
- Preserve organization folders after creator account deletion; guard populated folder downgrade and save a local pre-upgrade backup.
- Verify 113 backend tests on SQLite/PostgreSQL, 28 frontend tests, 11 Chromium journeys, real migrations and updated Docker folder/storage operations. Phase 3 was committed as 5c5bccd before Phase 4.

### Phase 2B — Multiple Organizations and Membership Lifecycle
- Separate global user identity from per-organization roles; migrate existing accounts/passwords and bind valid sessions to their prior workspace.
- Add verified existing-user invitation acceptance, workspace listing/creation/switching, and scoped removal/reactivation without disabling other memberships.
- Add confirmed password-protected ownership transfer, atomic owner replacement and final-owner protection during concurrent removal/demotion/transfer.
- Complete deletion across all memberships; require ownership transfer in every owned organization first.
- Reject stale frontend responses and cross-workspace retries; preserve independent public account actions during session restoration.
- Verify 92 backend tests on SQLite/PostgreSQL, 24 frontend component tests, 9 Chromium/SMTP journeys, migrations, lint/build, and updated Docker/storage runtime.
- Save an ignored pre-upgrade local database backup. Phase 2B was committed as 35d4b58 before Phase 3; no push/remote CI was performed.

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

### Frontend visual design
- Add shared workspace navigation and overview, split authentication layout, responsive controls, SVG icons, content rows, upload/empty/error styling, and desktop/mobile browser verification. See docs/frontend-design.md and ADR-023.

### Phase 7 — Basic Download
- Add current-member authorized, tenant-scoped download tickets for verified uploaded files; provider integrity checks, post-inspection/signing membership checks, grant rate limits and safe error responses.
- Add signed attachment GET with safe Unicode filenames, octet-stream and no-store responses, default five-minute expiry, and native browser download controls with stale-session protection.
- Add real signed GET/tampering and Chromium byte/filename/credential checks. No new database migration. See docs/phases/phase7.md and ADR-024.
