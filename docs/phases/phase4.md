# Phase 4 — File Metadata

Implemented and locally verified on 2026-10-14. Phase 5 has not started.

## A. What we built

- Organization-owned file metadata with stable IDs, folder/creator references,
  normalized names, declared size/type, pending state and timestamps.
- Tenant/folder integrity constraints, name uniqueness and listing/provenance indexes.
- Internal metadata reservations with current membership and parent permission checks.
- Paginated listing and detail APIs; a Files section in the folder browser.
- Preservation, concurrency, authorization, database and browser verification.

## B. Why we built it

The storage/upload phases need an authoritative relational identity for each file.
A filename or object key alone cannot establish organization membership, parent
relationships or ownership. This phase builds that foundation before accepting bytes.
Pending records explicitly distinguish declarations from a successfully stored object.

## C. Architecture

The `files` table stores metadata only. Each file belongs to one tenant, has a
nullable folder ID for virtual-root placement and references its creator's global
identity. A composite `(folder_id, tenant_id)` foreign key prevents cross-tenant
placement. Folder moves preserve their UUID, so their files remain attached.

Separate child and partial root uniqueness constraints enforce normalized file
names per location. Files and folders have independent name namespaces. A listing
index covers tenant/folder/name/id; another index covers tenant/creator. No object
bytes, download URLs or storage credentials enter the table or responses.

FileService delegates membership, tenant locking and parent authority to the
existing folder service. Internal reservation commits one metadata transaction;
the upload phase must coordinate reservation with its upload session and object
lifecycle. No public creation endpoint exists until that flow can validate objects.
GET routes delegate to the service and have bounded pagination.

## D. Important files

- `backend/app/models/file.py`: table, relationships, constraints and indexes.
- `backend/app/schemas/files.py`: declaration validation and read/page schemas.
- `backend/app/services/files.py`: internal reservation, tenant-scoped reads and policy.
- `backend/app/api/files.py`: listing and details.
- `backend/migrations/versions/006_files.py`: additive schema and downgrade guard.
- `backend/tests/api/test_files.py`, `tests/test_file_migration.py`: coverage.
- `frontend/src/features/folders/FileList.tsx`: metadata listing within folder browsing.
- `frontend/src/types/index.ts`, `services/api.ts`: typed metadata/page requests.
- `frontend/src/__tests__/FileList.test.tsx`, `e2e/folders.pw.ts`: UI checks.

## E. Technical concepts

**Metadata versus content:** PostgreSQL records identity and declarations. Object
storage will hold bytes in Phase 5 onward. Declared size/type cannot establish actual
object length, safe MIME, malware clearance or download availability.

**Organization ownership versus provenance:** The organization owns shared content;
created_by records who introduced it. Creator departure or global account deletion
does not erase organizational metadata. Current managers retain stewardship while
deleted identities remain pseudonymous references.

**Pending lifecycle:** Pending is the only permitted state. A database check also
rejects a forged ready state. Phase 6 must introduce verified object attributes and
valid state transitions; later scanning, trash, versions and AI build on that flow.

**Normalized naming:** File names reuse the folder policy: trim, NFC normalization,
case-folded uniqueness, maximum 255 characters and no separators, control/surrogate
characters or dot-only paths. Declared MIME accepts a bounded type/subtype token,
without header injection. It remains untrusted. Declared size is a strict integer
from zero through 9007199254740991, preserving JavaScript numeric precision; this
is a metadata representation bound, not an actual upload allowance or storage quota.

## F. Request flows

1. A verified member selects a workspace and opens `/app/folders`.
2. After the parent folder loads, the Files section requests that folder's metadata
   page, or root metadata. Query keys include tenant, user, folder and offset.
3. GET `/api/v1/files` checks current membership and selected parent ancestry,
   then returns an ordered page with has_more. GET `/api/v1/files/{id}` always
   looks up the UUID within the authenticated tenant.
4. An internal reservation validates declarations, locks the tenant, rechecks
   verified membership and parent authority, checks name conflict and commits
   the authenticated creator/tenant with pending state. Concurrent duplicates have
   one winner. There is no public POST route or frontend upload form yet.
5. UI presents pending/declared labels, read-only or creator/manager authority,
   pagination and visible empty/error/manual-retry states. No download control exists.

## G. Security and privacy

Verified active workspace membership is required for every protected metadata read.
Foreign or missing file/folder IDs return 404. Internal reservation rejects extra
tenant, creator or status fields and derives identity from the authenticated actor.
Destination-folder creation requires creator or current owner/admin authority;
root creation remains available to verified members.

All members currently read shared workspace metadata. can_write records foundation
authority for future file mutations; it grants no client-controlled permission.
Private/viewer/editor ACLs remain Phase 12. Tenant locking serializes reservations
with folder changes and membership management; database constraints back the service.
Existing session-generation protection rejects late responses after workspace changes.

## H. Tests and results

- 131 backend tests passed on SQLite and real PostgreSQL, using disposable
  `cloudvault_phase4_test`; destructive fixtures never used the application database.
- New tests cover pending declarations, root/folder listing, details, pages,
  authentication/verification, no public creation, creator/manager/read-only policy,
  parent authority, foreign and missing folders, identity/status injection,
  invalid names/sizes/MIME, Unicode normalization and concurrent reservations.
- Database tests reject cross-tenant parent links, negative sizes, ready state and
  duplicate root names. Folder moves and creator deletion preserve file identity.
- Seeded SQLite/PostgreSQL migration checks preserve preexisting accounts/password
  hashes and folders across 005-to-006 upgrade and empty downgrade/re-upgrade.
  Populated file downgrade is refused with metadata intact.
- Disposable PostgreSQL full upgrade/check/downgrade-to-base/re-upgrade passes.
- 31 frontend component tests, ESLint, Ruff and TypeScript/Vite build pass.
- 11 Chromium journeys pass with real local SMTP and disposable migrated data,
  including file listing/empty state and existing account/workspace/folder journeys.
- Existing workspace browser tests now wait for loaded current-workspace/roster
  state before branching or asserting member absence. This avoids skipping a switch
  before its button loads or navigating away during session restoration.
- Docker rebuild/start passes; application is at `006_files` with no schema
  differences. Frontend/proxy/authentication gates, Mailpit and real S3 object
  upload/read/delete smoke checks pass.
- Pre-upgrade backup `.local/backups/cloudvault-before-phase4.sql` is ignored.
  Phase 3 is committed as `5c5bccd`; Phase 4 remains uncommitted. No remote CI was run.

## I. Decisions and tradeoffs

ADR-020 records pending-only metadata, declared attributes, organization ownership,
name namespaces and internal reservations. Public creation waits for actual upload
validation so records cannot imply nonexistent stored files. Root uniqueness needs
a partial index because ordinary uniqueness permits multiple null-parent rows.
Per-tenant serialization reuses the established safe hierarchy/management boundary;
later optimization requires measurements. The size bound avoids client precision loss.

## J. Limitations and operation

The running Docker app is migrated at `http://localhost:3000/app/folders`. File lists
are expected to be empty until the upload pipeline creates metadata. No upload,
download, standalone file rename/move, object key, verified size/type or storage
lifecycle exists in this phase. Storage abstraction is Phase 5, uploads Phase 6,
downloads Phase 7; multipart/resume, cleanup, search, sharing, ACLs, trash, versions
and AI follow their roadmap stages. Pending cleanup is not implemented yet.

Lists use pages of 25, API maximum 100; hierarchy still has depth 64. Content persists
after creator departure/deletion. Use `docker compose up --build -d` after source
changes. Direct setups must back up then apply `alembic upgrade head`. A populated
file downgrade is refused; restore a pre-upgrade backup for rollback. Tests need
disposable databases.

Remote CI, production SMTP/provider checks, MFA, independent security review and
deployment hardening remain pending. Local archived MinIO needs a maintained
production storage decision. SMTP acknowledgements can be ambiguous; single-use
account actions prevent repeated state changes, but duplicate emails remain possible.

## K. Interview questions

**Why separate declarations from verified attributes?** Clients can misreport size
and MIME; only object inspection and later processing can establish trusted facts.

**Why a composite folder/tenant FK?** A folder ID alone proves existence, not that
the file and folder belong to the same organization. The database enforces both.

**Why does creator deletion preserve files?** Shared organization content outlives
individual membership; provenance remains a pseudonymous reference and managers
retain stewardship.

**Why no upload form yet?** This phase establishes metadata. Real presigned transfer
and object validation must exist before the product can claim upload success.

**How do concurrent duplicate names behave?** Reservations share the tenant lock;
the second sees the first commit and returns conflict. Unique indexes remain a
second integrity boundary.

Next: Phase 5 — Object Storage, only on explicit instruction.
