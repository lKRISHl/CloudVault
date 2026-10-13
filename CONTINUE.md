# CloudVault — Current State

Current Phase:
Phase 2B — Multiple Organizations + Membership Lifecycle

Status:
Implementation and local verification complete on 2026-10-14. The updated Docker app runs at http://localhost:3000 with migration 004_workspaces. Phase 3 has not started. Phase 2B changes are uncommitted; nothing was pushed or dispatched to remote CI.

Completed Work:
- Phase 0–2A foundations remain: FastAPI/React, account authentication/verification/recovery, encrypted SMTP outbox, live revocation, memberships, profile editing and invitations.
- Global user identity stores no tenant/role columns. Memberships independently hold role and revocation per organization, with tenant/user foreign keys and one active owner per organization.
- Workspace listing/creation and explicit switching. Login deterministically selects the earliest active membership or an account-only session if none remain.
- Sessions select one tenant and JWT tenant must match. Switching revokes this session/refresh tokens and issues a replacement without extending the absolute deadline; other browser sessions remain usable in their selected workspace.
- Existing verified accounts explicitly accept addressed invitations while retaining their identity, password and other memberships. New accounts still separately verify email.
- Scoped removal keeps a membership tombstone and revokes only affected workspace sessions/invitations. Reactivation requires a fresh owner-issued invitation, current owner authorization, verified identity and explicit role; old sessions remain revoked.
- Ownership transfer requires current password and literal TRANSFER, promotes a verified active member, demotes the former owner to admin, and invalidates their pending invitations. Tenant/user locks, conditional updates and a partial unique index protect final ownership during concurrent requests.
- Global deletion checks every owned organization, requires transfer first, then removes all memberships/challenges and revokes/redacts account access/profile/mail references. Minimal identity tombstones remain.
- Frontend workspace controls, existing-account joining and ownership forms. Session changes cancel/clear query state and reject old responses; shared-cookie refresh cannot retry an old workspace mutation in another tenant. Public verification/recovery remains independent of session restoration.
- Migration preserves accounts/passwords and existing valid session selections, converts legacy removal disables to revoked membership tombstones, and retains suspensions with intact memberships. Unsafe downgrade refuses incompatible data rather than discarding it.

Important Files:
- backend/migrations/versions/004_global_identity.py
- backend/app/models/user.py, membership.py, account.py, invitation.py; app/services/auth.py, workspaces.py, organizations.py, accounts.py; api/deps.py and organizations.py.
- frontend/src/features/organizations/WorkspaceSwitcher.tsx, SettingsPage.tsx, JoinPage.tsx; auth/AuthContext.tsx, services/api.ts, types/index.ts; home/login/app routes and security text.
- backend/tests/api/test_workspaces.py, tests/test_workspace_migration.py and adjusted organization/migration regressions.
- frontend/e2e/workspaces.pw.ts, src/__tests__/WorkspaceSafety.test.ts and updated organization fixtures.
- docs/phases/phase2b.md and phase index; README, ARCHITECTURE, PROJECT_CONTEXT, DEVELOPMENT_PLAN, SECURITY, DECISIONS, CHANGELOG.

Verification Passed:
- 92 backend tests on SQLite and PostgreSQL, including actual localhost SMTP integration.
- PostgreSQL uses dedicated cloudvault_phase2b_test; the earlier cloudvault_test retained the previous schema and was not counted as a successful verification run. Seeded migration tests create their own disposable PostgreSQL database and remove it afterward.
- Coverage: independent roles, list/create/switch, stable refresh binding/absolute expiry, tenant-session forgery, unrelated workspace denial, verified existing acceptance, replay, scoped removal, owner reactivation, stale sessions, ownership password/confirmation, deletion across memberships, and concurrent transfer versus transfer/removal/demotion.
- Seeded PostgreSQL/SQLite migrations preserve identity/password/email state and live sessions; removed access remains revoked, suspensions stay disabled, and unsafe downgrade preserves multiple memberships by refusing the operation.
- PostgreSQL Alembic upgrade/check/downgrade/re-upgrade passed; SQLite schema/migration checks passed.
- 24 frontend component tests, 9 real Chromium/SMTP journeys, Ruff, ESLint and TypeScript/Vite production build passed.
- Full Docker rebuild/start passed. Application database is at 004_workspaces with no Alembic schema differences. HTTP/API proxy/Mailpit checks and actual storage upload/read/delete passed. Actual Docker registration, SMTP verification, two-workspace create/list/switch and old-session revocation also passed through the frontend proxy. A uniquely named local smoke identity/workspaces remain as development test data; SMTP dispatcher runs.
- Pre-upgrade development database backup: .local/backups/cloudvault-before-phase2b.sql (ignored by Git). Do not overwrite or commit it.

Remaining Limits:
- No file/folder/upload/sharing/AI features yet; Phase 3 is next.
- Remote CI and real production SMTP/from-domain/provider verification remain unrun. No push or dispatch was performed.
- Full tab synchronization and real-time roster updates remain future work. Shared-cookie workspace changes fail closed for stale mutations; reload/sign in to adopt the new selection. Membership/ownership lists are paginated.
- MFA, wider abuse controls, independent security review, deployment hardening, monitoring and backup operations remain later phases.
- SMTP can duplicate after an ambiguous acknowledgement/crash; action links stay single-use. Signing-key rotation affects queued encryption; coordinate API/dispatcher and resend links.
- Deletion retains minimal identity references; no legal-compliance or complete metadata-erasure claim.
- Community MinIO is archived/unmaintained. Local source builds use pinned official commits; production needs a maintained S3 provider/deployment decision.
- Docker/WSL run locally; WSL memory is limited to 4 GB after initial host resource exhaustion. Builds use conservative Go compilation limits.

Decisions:
ADR-017 — Global identity, revoked memberships and workspace-bound sessions.
ADR-018 — Atomic ownership transfer and global deletion.
Earlier ADRs document account actions/outbox and development storage source builds.

Next Exact Phase:
Phase 3 — Folder System, only on explicit instruction. Phase 2B is complete locally; remote CI remains a separate verification gate requiring authorized push/dispatch.

Last Commit:
f79122d — feat: add organizations and verified account lifecycle (Phase 2/2A and Docker fix). Phase 2B is currently uncommitted.

Suggested Commit:
feat: add multiple workspaces and membership lifecycle

Phase reports live in docs/phases/. Read docs/phases/phase2b.md for the full explanation and operating limits.
