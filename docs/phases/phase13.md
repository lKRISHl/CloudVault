# Phase 13 — Trash and Restore

Implemented and locally verified on 2026-10-15. Schema: 013_trash. Verification is recorded below.
Phase 12 is committed as cce1f62; Phase 13 remains uncommitted.

## A. What was built

Recoverable trash for completed files and folder subtrees, a paginated Trash page,
original-location restore, name-conflict protection, explicit irreversible purge requests
and retryable storage cleanup after 30-day retention or manual deletion. Existing ACLs,
tenant boundaries and storage identities are preserved. External links revoke on trash.

## B. Why

Accidental deletion needs a recovery window, while permanent deletion must coordinate
database state and object storage safely. Removing metadata first would lose the exact
object reference needed for retries. Restoring after storage deletion starts would revive
unavailable files. Trash therefore separates reversible removal from irreversible cleanup.

## C. Architecture

TrashEntry records a tenant-scoped batch root, kind, actor, trash time, 30-day retention,
earliest cleanup time, purge request, restore and purge completion markers. Files/folders
hold a nullable trash_id. Completed files retain object references and checked/purged
timestamps. These tombstones are internal durable cleanup references, not live content.

TrashService uses the existing tenant write lock and live management/ancestor policy.
Folder trash stamps only currently active descendants; independently trashed batches remain
separate. Live ACL predicates exclude trash before folder traversal, search/list pagination,
direct IDs, grants, uploads and publication. Trash listing uses the same effective read
rules with trash traversal enabled, plus creator/manager control, before union pagination.

Live file/folder sibling-name indexes exclude trash. A name can be reused immediately;
restore clears only its batch in one transaction and rolls back completely on conflict.
Root identities, private/workspace visibility, grants, provenance and object checksums stay
unchanged. Old external links remain revoked after restoration.

Permanent deletion queues irreversible state. Folder purge also queues older independent
trash inside the subtree. The worker commits that state before storage operations, then
reacquires the tenant lock. Restore cannot race provider deletion. File objects are deleted
only after upload expiry plus configured completion grace/settling time; multipart uploads
at the exact key are aborted and their absence rechecked before object deletion/HEAD absence.

TrashCleanupService fails closed on versioned or suspended buckets, changed buckets, missing
references, unsafe deadlines and provider failures. It retains references and fairly rotates
attempts. Completion requires no outstanding unpurged uploaded objects in scope. Successful
tombstones are revisited to reclaim later provider writes. Restored batches are never swept.

The existing Compose upload-cleanup worker invokes trash maintenance. Each tick selects up
to 10 oldest/unattempted batches and processes up to 10 file references per batch. A separate
python -m app.jobs.cleanup_trash --once command is available. Queue/provider latency means
retention expiry is eligibility, not an exact wall-clock reclamation guarantee.

## D. Important files

- backend/app/models/trash.py, models/file.py, models/folder.py and migrations/versions/013_trash.py.
- backend/app/schemas/trash.py, api/trash.py, services/trash.py and services/trash_cleanup.py.
- backend/app/jobs/cleanup_trash.py and jobs/cleanup_uploads.py.
- backend/app/services/permissions.py, folders.py, files.py and app/main.py.
- backend/tests/api/test_trash.py, test_trash_cleanup.py, test_trash_integration.py and test_trash_migration.py.
- frontend/src/features/trash/TrashPage.tsx, TrashButton.tsx, components/AppShell.tsx and app/App.tsx.
- frontend/src/features/folders/FileList.tsx, FoldersPage.tsx, features/search/FileSearchPage.tsx and services/api.ts.
- frontend/src/__tests__/Trash.test.tsx, e2e/trash.pw.ts and scripts/upload_smoke.py.
- CONTINUE.md and ADR-030.

## E. Technical concepts

Soft deletion removes content from live access without destroying its stored bytes.
A batch preserves which descendants were removed together, so restoring a parent cannot
resurrect unrelated older trash. Retaining batch history also makes stale worker jobs safe:
a restored batch is explicitly excluded even if a queue snapshot still contains its ID.

Database and storage cannot participate in one atomic transaction. Durable purge intent
precedes provider deletion; provider confirmation precedes completion markers. A lost
acknowledgement or crash can retry the same exact object key without deleting a replacement
that reused the old display name, because object IDs remain unique and immutable.

Old upload capabilities can become writable again after an object is removed. Cleanup waits
past the original upload deadline, grace and settling interval and retains tombstones for
rechecks. Versioned deletes may create markers while historical bytes remain; this phase
refuses such buckets rather than claiming version-aware erasure.

## F. Request flow

1. Choose Move to trash on a completed managed file or a managed folder. The original parent
   must be readable/writable. Viewers/editors cannot trash someone else's content.
2. A nonmanager may trash a folder only when all remaining resources in its subtree belong
   to them. Other creators' content requires a workspace manager, without naming hidden items.
   Pending uploads block trash: finish them or allow cancelled/expired cleanup first.
3. The server stamps a batch, revokes affected external links and releases active display
   names. Ordinary browsing, search, downloads and sharing no longer expose the resources.
4. Open Trash. Rows show root name/type, trash time, retention deadline and queued state.
   Only current authorized creators/managers can see/manage rows; pages contain 25 entries.
5. Restore before retention expires and before purge is queued. Restore the original parent
   first, retain its write authority, and resolve active name conflicts. Restore returns to
   the original location only; independently trashed descendants stay in trash.
6. To delete permanently, open the confirmation panel and type DELETE. The API returns 202
   for queued cleanup and immediately disables restore. Folder purge includes nested trash.
7. At retention expiry the worker queues purge automatically. It removes bytes when safe,
   confirms absence and hides completed entries from Trash. Provider failures leave a queued
   entry for retry; metadata/reference retention remains explicit.

## G. Security

Current verified tenant membership, effective ancestor readability and resource management
are checked for trash/list/restore/purge. Trash and restore also require a writable original
parent. Foreign IDs and inaccessible trash return not found. Private ancestors and management
predicates apply before global union ordering/pagination/has_more. Client tenant, object key,
provider bucket, retention deadline and cleanup timestamps are never accepted as authority.

Tenant serialization orders trash, restore, purge, moves, ACL changes and upload writes.
Concurrent restore/purge has one result: restored before purge, or irreversibly queued before
restore. Permission grants survive restore only if membership lifecycle has not removed them.
External links never reactivate automatically. Previously delivered bytes and issued storage
GET URLs cannot be recalled immediately; new grants stop at trash time.

Trash mutations use persistent 100 identity/500 IP requests per configured window (default
15 minutes). Resource/trash API responses, including denials, use no-store/no-referrer.
Frontend cache/remount keys include workspace/user; requests use existing stale-session guards.
Purge confirmation is enforced by the backend as well as the UI. Worker logs avoid raw SDK
exceptions and retain exact scoped references on failure.

## H. Verification

- All 250 backend tests pass on SQLite (291.71 seconds) and disposable PostgreSQL
  (291.26 seconds), with actual MinIO enabled. Final cleanup/integration rechecks pass
  all five cases on each database after respecting every nested batch's recorded deadline.
- Trash/live-path hiding, ancestor/management filtering, mixed-creator protection, active
  name reuse, atomic file/folder conflicts, independent batches, parent-first restore,
  expiry, explicit confirmation, nested purge and concurrent restore-versus-purge pass.
- Cleanup covers deadline waiting, retry without early completion, retained late-write
  references, restored-content protection and Enabled/Suspended bucket refusal. Actual
  presigned upload/restore/download bytes and real deletion/HEAD absence/recreated-object
  recheck use disposable buckets. Test clocks advance eligibility; full real-time 30-day
  retention and provider lifecycle waiting periods are not measured.
- Migration tests preserve existing content/accounts/visibility, verify empty rollback/
  re-upgrade and refuse history loss, including restored batches. Existing migrations,
  ACL/concurrency/transfer/search/index checks remain green.
- All 77 frontend tests, ESLint, TypeScript/Vite build, Ruff and whitespace checks pass.
  Trash scope/cache, restore/conflicts/paging, queued/expired state, explicit DELETE
  confirmation and move errors are covered.
- All 18 Chromium/SMTP/storage journeys pass (1.4 minutes). Trash tests prove actual
  restored bytes, live hiding, queued deletion/restore denial, folder name reuse/conflict
  and mobile layout. An earlier permissions test now waits for its target folder before
  file selection; the final browser run passes separately from database workloads.
- Rebuilt Docker HTTP/private bucket/mc/adapter smoke and actual SMTP/transfer/search/
  sharing/ACL/file-folder trash/restore/purge-queue checks pass. Live schema 013_trash
  has no drift. Both composite and standalone trash maintenance run successfully; the
  new smoke purge stays queued before its deadline. All services are healthy/running.
- Browser-owned storage cleanup is complete and the disposable PostgreSQL test database
  is removed. Ignored .local/phase13-*.log evidence and pre-upgrade backup are retained;
  unique development smoke content includes a queued purge demo. No remote CI, public
  provider, production load/security or Safari/Firefox certification is claimed.

## I. Decisions and tradeoffs

ADR-030 records batch soft deletion, original-location restore, preserved ACLs, live-name
reuse, irreversible queued purge and retained cleanup tombstones. Completed files are the
recoverable unit; pending transfers keep their existing bounded lifecycle. Nonmanagers
cannot delete mixed-creator folder subtrees. This favors explicit authority over inheriting
destructive access from an editor role or solely from ownership of a containing folder.

Original-location restore preserves ancestor restrictions; this phase does not relocate to
root, automatically rename collisions or widen visibility to recover content. Permanently
deleting a parent deliberately queues independently trashed descendants too. Tombstone
retention and tenant serialization favor retry safety over immediate metadata erasure or
unmeasured throughput. Search indexes still contain some hidden rows and need production
workload/index maintenance review as retained data grows.

## J. Operations and limitations

Run docker compose up --build -d, python scripts/docker_smoke.py and python scripts/upload_smoke.py.
Trash is at /app/trash. The cleanup service is already included in Compose through the
upload-cleanup worker; direct setups must keep that worker or cleanup_trash running.
Maintenance uses the same interval (60 seconds default) and configured unversioned bucket.

Back up before alembic upgrade head (013_trash). The ignored local backup is
.local/backups/cloudvault-before-phase13.sql. Existing data stays live with trash_id NULL.
Empty migration downgrade is supported. Any retained trash history/purge reference refuses
downgrade, including restored batches; restore the pre-upgrade backup for an unrepresentable
rollback. A SQL backup cannot restore already deleted object bytes; provider backups are separate.

Retention is 30 days. New purge requests cannot be cancelled. Cleanup waits at least until
the recorded not_before deadline and each file's original upload expiry plus grace/settle,
and can take longer under provider failure or queue load. No synchronous erasure, exact
completion time, physical disk wipe or legal-compliance guarantee is made. Internal filenames,
metadata, grants, revoked links and exact object references remain as hidden tombstones/history;
there is no metadata-erasure scheduler yet.

Only completed files are recoverable through trash. Pending files block containing-folder
trash until finished or cleaned. Restore requires an active original parent and conflict-free
names; grants do not bypass private ancestors or restore removed memberships. Managers are
trusted to manage private content. Public download URLs retain their normal short lifetime.

Versioned/suspended buckets are refused. Phase 14 must coordinate object versions/retained
references before enabling provider versioning. Preview, scans, quotas, audit, AI, maintained
production storage, SMTP/MFA, monitoring, remote CI, representative load and backup/restore
verification remain pending. Local MinIO is archived and for development only.

## K. Interview discussion

- Why retain exact object references? Retried cleanup must target the original UUID key,
  never replacement content that reused its display name.
- Why queue deletion before provider operations? Restore must be disabled before any bytes
  can disappear, including a crash after an ambiguous storage acknowledgement.
- Why batch folders? A parent restore should recover its own removal event without reviving
  independently trashed children or changing their original ACLs.
- Why wait for upload capabilities? A previously issued conditional PUT can recreate an
  object after deletion until its original authorization expires.
- Why refuse versioned buckets? Delete markers do not prove historical bytes were removed;
  version-aware retention/purge needs an explicit verified design.
