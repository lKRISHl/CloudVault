# Phase 3 — Folder System

Implemented and verified locally on 2026-10-14. Phase 4 has not started.

## A. What we built

- Folder creation, rename, moves and hierarchy browsing in the selected workspace.
- A folder browser at `/app/folders` with breadcrumbs, pagination and a move destination picker.
- Tenant-scoped read/write checks and a central permission foundation.
- Normalized sibling names, database parent/tenant integrity, cycle/depth checks and concurrent write protection.
- Migration, preservation/downgrade tests and complete frontend/backend/browser verification.

## B. Why we built it

Files need stable folder identities and a safe organization hierarchy before metadata
and object storage are attached. Moves preserve a folder's UUID and descendant identity,
so future file references can remain stable while users reorganize their workspace.
The current policy makes the workspace shared and makes edit authority explicit.

## C. Architecture

The `folders` table holds UUID, tenant, nullable parent, creator, display/name key
and timestamps. A null parent represents the virtual root. A composite foreign
key from `(parent_id, tenant_id)` to the parent's `(id, tenant_id)` blocks cross-tenant
edges. A self-parent check prevents direct loops; service validation handles longer
cycles. Child and partial root uniqueness indexes enforce sibling names.

`FolderService` contains authorization, lookup, naming, ancestry and mutation logic.
Routes validate input and delegate. Current verified membership is rechecked after
the tenant write lock; UUID lookups always include the selected tenant.

An adjacency list means a move changes one parent pointer. Bounded ancestor
traversal supplies breadcrumbs and detects invalid paths. A recursive CTE computes
subtree height so a move cannot push descendants beyond the maximum depth of 64.
PostgreSQL serializes structural changes per tenant; SQLite test/development uses
its writer lock before reading the graph. Opposing concurrent moves cannot both win.

## D. Important files

- `backend/app/models/folder.py`: metadata, parent integrity and indexes.
- `backend/migrations/versions/005_folders.py`: schema addition and populated downgrade guard.
- `backend/app/schemas/folders.py`: name validation and response models.
- `backend/app/services/folders.py`: tenant checks, permissions, hierarchy and writes.
- `backend/app/api/folders.py`: list/create/detail/rename/move API.
- `frontend/src/features/folders/FoldersPage.tsx`: folder browser, rename and destination UI.
- `frontend/src/services/api.ts`, `types/index.ts`, `app/App.tsx`: typed requests, routes and bounded query retry policy.
- `backend/tests/api/test_folders.py`, `test_folder_migration.py`: safety, concurrency and real migration coverage.
- `frontend/src/__tests__/FoldersPage.test.tsx`, `frontend/e2e/folders.pw.ts`: component and actual browser journeys.

## E. Technical concepts

**Adjacency lists:** Each folder references its parent. Reads walk parents or list
children; a move preserves identity while replacing the parent. A deep tree can
need several queries, so traversal is bounded. More complex path/closure structures
are an optimization decision for later measured workloads.

**Normalized names:** Input is trimmed and NFC-normalized. Case-folded keys reject
equivalent sibling names, including Unicode cases such as Straße/STRASSE and
composed/decomposed accented names. Separators, control/surrogate characters and
dot-only paths are rejected. Names contain up to 255 characters.

**Permission foundation:** Verified active members can read workspace folders and
create at root. Creators and current owners/admins can rename/move a folder, create
its children or use it as a destination. Client can_write flags help render controls;
the server independently checks authority. Private/shared resource ACLs are Phase 12.

**Transaction safety:** Lock before reading mutable ancestry. Sibling checks and
database uniqueness prevent conflicting names; cycle and subtree-height checks
prevent invalid moves. Failed writes leave the prior tree intact.

## F. Request flows

1. Sign in, select a workspace, verify email and open Browse folders.
2. Listing returns the selected parent, breadcrumbs, child page and has_more.
3. Create validates the name, checks parent authority/depth and sibling uniqueness,
   and commits the new node with the authenticated creator and selected tenant.
4. Rename checks folder write authority and destination-sibling name uniqueness,
   then updates display/key while retaining identity.
5. Move selects a destination, checks source/destination authority, rejects self or
   descendants, checks subtree depth and sibling conflicts, and commits the parent.
6. UI invalidates the workspace's folder queries. Missing/forbidden resources show
   immediately; transient failures receive bounded retries and explicit retry controls.
   Phase 2B stale-response protections continue to guard workspace changes.

## G. Security and privacy

All UUID reads and parent paths are tenant-scoped; foreign folders return 404.
Request schemas forbid tenant/creator injection. Session/membership checks remain
mandatory. SQL constraints block invalid parent links even if service code regresses.
The tree is shared within a workspace, not private per person. Creator account
deletion preserves organizational folder metadata with its pseudonymous creator
reference; current managers can maintain it. No file bytes are stored in PostgreSQL.

## H. Tests and results

- 113 backend tests passed on SQLite and PostgreSQL. PostgreSQL used a fresh
  `cloudvault_phase3_test`; tests never used the application database.
- Folder tests cover hierarchy/breadcrumbs/pagination, name normalization/conflicts,
  validation, stable subtree moves, self/descendant rejection, depth/subtree limits,
  creator/admin/owner permissions, read-only members, cross-tenant access/parents,
  database constraints, creator deletion and concurrent moves/duplicate creation.
- Seeded PostgreSQL/SQLite migration checks preserve existing accounts/hashes and
  folder parent links; populated downgrade is refused with folder data intact.
- Full PostgreSQL Alembic upgrade/check/downgrade/re-upgrade passed on empty test
  schema. Existing account/workspace regressions remain green.
- 28 frontend component tests, ESLint, TypeScript/Vite build and Ruff passed.
- 11 Chromium journeys passed with disposable migrations and real local SMTP,
  including folder creation/rename/move, breadcrumbs, workspace isolation and member policy.
- Docker rebuild/start, `005_folders` current/schema check and HTTP/storage smoke
  passed. Actual Docker folder create/rename/move/breadcrumb/cycle/isolation requests
  passed through the frontend proxy with a real verification email.
- An ignored pre-upgrade local backup is saved at
  `.local/backups/cloudvault-before-phase3.sql`. Unique smoke accounts/workspaces/folders
  remain as development data. No push/remote CI dispatch was performed.

One existing test assumed default login always picked a particular workspace.
SQLite timestamps can tie; the documented UUID tie-breaker still selects deterministically.
The test now explicitly selects the unaffected workspace instead of making that assumption.

## I. Decisions and tradeoffs

ADR-019 records adjacency folders, naming, serialization and permission policy.
Root uniqueness needs its own partial index because ordinary unique constraints
permit multiple null-parent rows. Per-tenant serialization keeps cycle validation
sound without a larger tree schema. Shared-workspace access is a clear foundation
for the later granular permission phase. Nonempty downgrade is guarded against data loss.

## J. Limitations and operation

The running Docker app is migrated and available at `http://localhost:3000/app/folders`.
Use `docker compose up --build -d` after source changes. Direct setups must back up
then apply `alembic upgrade head`. Downgrade cannot discard populated folders;
restore a pre-upgrade backup for rollback. Destructive tests must use disposable databases.

Depth is limited to 64; lists and move destinations use pages of 25 (API maximum 100).
Hierarchy writes serialize within each organization. Folder creation and organization
content persist after a creator leaves or deletes their account.
Private ACLs/viewer-editor sharing arrive in Phase 12; trash/deletion in Phase 13.
File metadata, uploads/downloads, object lifecycle and AI remain upcoming phases.
Remote CI, production SMTP, MFA, broader security review and deployment hardening
remain pending. Community MinIO is archived; production needs maintained storage.
SMTP can duplicate under an ambiguous acknowledgement; action links remain single-use.

## K. Interview questions

**Why adjacency folders?** Stable identities and simple parent changes fit the current
workload; bounded traversal and indexes support child browsing without premature complexity.

**Why both constraints and services?** Foreign keys/indexes protect referential/name
integrity; services enforce membership, write authority, longer cycles and depth.

**How are concurrent cycles prevented?** Both moves must obtain the same tenant lock
before reading ancestry; the second sees the first committed structure and rejects the cycle.

**What happens after creator deletion?** Organization metadata survives, while the
creator loses global access and their identity becomes pseudonymous; managers retain authority.

**Why reject populated downgrade?** Removing the table would silently destroy user
content; a backup restore is the deliberate rollback path instead.

Next phase: Phase 4 — File Metadata, only on explicit instruction. Phase 3 is uncommitted.
