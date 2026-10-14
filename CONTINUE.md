# CloudVault — Current State

Current Phase:
Phase 3 — Folder System

Status:
Implementation and local verification complete on 2026-10-14. The updated Docker app runs at http://localhost:3000 with migration 005_folders; folder browser is /app/folders. Phase 4 has not started. Phase 3 changes are uncommitted; no push or remote CI dispatch was performed.

Completed Work:
- Phase 0–2B foundations remain: global verified accounts, multiple memberships/roles, explicit workspace sessions, invitation/reactivation, ownership transfer, recovery and global deletion.
- Add tenant-scoped folders with stable IDs, parent/creator metadata, normalized display/name key and timestamps. Composite parent/tenant FK prevents cross-tenant edges; self-parent and sibling/root uniqueness constraints protect structure.
- Create, rename, move, detail and paginated child-list API through a central FolderService. Breadcrumbs provide hierarchy navigation; source/destination writes, cycles, conflicting names and maximum depth are checked before mutation.
- Shared-workspace permission foundation: verified active members read and create at root. Creators and current owners/admins rename/move and write within parent folders. Granular resource ACLs remain Phase 12; returned can_write is informational.
- Hierarchy writes serialize per PostgreSQL tenant; SQLite test/development uses BEGIN IMMEDIATE before graph reads. Opposing moves cannot produce cycles; duplicate root creation has one winner. Subtree-height CTE keeps moves within depth 64.
- Folder browser with root/child navigation, breadcrumbs, pagination, rename and a browsable move destination. Scoped query keys and existing session-generation protection prevent workspace leakage; client errors show immediately and transient failures have bounded/manual retry.
- Creator account deletion retains organizational folder metadata with a pseudonymous creator reference; current managers can maintain it. No file bytes are stored in PostgreSQL.
- Migration 005_folders preserves accounts/memberships and refuses populated downgrade; empty-schema upgrade/check/downgrade/re-upgrade works. Local pre-upgrade backup saved and ignored.

Important Files:
- backend/app/models/folder.py, schemas/folders.py, services/folders.py, api/folders.py; model/API registration.
- backend/migrations/versions/005_folders.py.
- frontend/src/features/folders/FoldersPage.tsx, types/index.ts, services/api.ts, app/App.tsx, pages/HomePage.tsx.
- backend/tests/api/test_folders.py, tests/test_folder_migration.py; existing workspace default-selection test fixed to avoid timestamp tie assumptions.
- frontend/src/__tests__/FoldersPage.test.tsx, e2e/folders.pw.ts; workspace browser test similarly handles deterministic timestamp ties.
- docs/phases/phase3.md and phase index; README, DEVELOPMENT_PLAN, ARCHITECTURE, SECURITY, PROJECT_CONTEXT, DECISIONS, CHANGELOG.

Verification Passed:
- 113 backend tests on SQLite and PostgreSQL, including earlier real localhost SMTP and membership/session regressions.
- PostgreSQL uses fresh disposable cloudvault_phase3_test, never application data. Seeded migration tests create/drop their own temporary PostgreSQL databases.
- Folder coverage: hierarchy/breadcrumbs/pagination, Unicode/case-folded sibling names, input validation, rename/move identity, self/descendant/depth rejection, creator/manager/read-only policy, parent writes, cross-tenant reads/parents, DB uniqueness/self-parent/FK constraints, creator deletion, concurrent cycle/duplicate creation protection.
- Real PostgreSQL/SQLite folder migrations preserve existing accounts/password hashes, preserve folder links, and reject nonempty downgrade without losing data. PostgreSQL upgrade/check/downgrade/re-upgrade passed on empty test schema.
- 28 frontend component tests, 11 real Chromium/SMTP journeys, Ruff, ESLint and TypeScript/Vite production build passed.
- Full Docker rebuild/start passed. Application is at 005_folders with no Alembic schema differences. HTTP/API proxy/Mailpit checks and actual storage upload/read/delete passed; dispatcher runs.
- Actual Docker registration/SMTP verification and folder create/rename/move/breadcrumbs/cycle rejection/workspace isolation passed through the frontend proxy. Unique smoke identity/workspaces/folders remain as development data.
- Pre-upgrade backup: .local/backups/cloudvault-before-phase3.sql (ignored). Preserve it; do not overwrite or commit it. Earlier Phase 2B backup remains.

Remaining Limits:
- Folder hierarchy depth 64, names up to 255 characters, pages of 25 (API max 100). Structural writes serialize per organization; optimize later with measured workloads.
- Workspace folders are shared-readable, not private per person. Granular viewer/editor/private/shared ACLs are Phase 12; deletion/trash is Phase 13.
- File metadata is Phase 4, object lifecycle/uploads/downloads follow afterward; AI features remain later phases.
- Remote CI and real production SMTP/from-domain/provider verification are unrun. No push or dispatch was performed.
- Real-time roster/folder updates and full cross-tab synchronization remain future work; stale requests fail closed and reload/sign in may be needed after another tab switches.
- MFA, broader abuse controls, independent security review, deployment hardening, monitoring and backup operations remain later work.
- SMTP can duplicate after ambiguous acknowledgement; account actions stay single-use. Signing-key rotation affects queued encryption; coordinate API/dispatcher and resend links.
- Deletion retains minimal identity references and organization-owned folder content; no legal-compliance or complete metadata-erasure claim.
- Community MinIO is archived/unmaintained; production needs maintained S3 storage. Local builds use pinned official sources; WSL is limited to 4 GB after earlier host resource exhaustion.

Decisions:
ADR-019 — Tenant-scoped adjacency folders and shared-workspace permission foundation.
ADR-017/018 — Global membership/workspace sessions and atomic ownership/global deletion.

Next Exact Phase:
Phase 4 — File Metadata, only on explicit instruction. Remote CI remains a separate verification gate requiring authorized push/dispatch.

Last Commit:
35d4b58 — Phase 2b complete. Phase 3 is currently uncommitted.

Suggested Commit:
feat: add tenant-isolated folder hierarchy and permissions foundation

Read docs/phases/phase3.md for the complete explanation, tested behavior and operating limits.
