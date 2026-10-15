# Phase 14 — File Versioning

Implemented and locally verified on 2026-10-15. Live schema: 014_versions, no Alembic drift. Running Docker app: http://localhost:3000/app/folders.
Phase 13 is committed as c3df20f. Phase 14 changes remain uncommitted.

## A. What was built

Immutable application content versions, current-version selection, replacement uploads,
historical downloads, restoration, uploader/content metadata and retained-byte accounting.
The Versions page is available from completed files in browsing and search. Original
basic and multipart objects become version 1 without moving or copying their bytes.

## B. Why

A logical file needs a stable identity, name, location and ACL while its content changes.
Overwriting an object would destroy recovery history and make already-issued downloads
ambiguous. Each content version therefore receives its own UUID object key, and the
logical file exposes the selected version's verified metadata.

## C. Architecture

FileVersion stores tenant/file identity, monotonic per-file number, uploader/request ID,
base generation, declared/verified metadata, exact object identity, original upload
deadline and cleanup markers. File.current_version selects an uploaded snapshot.
File.version_generation increases on every content change, including restoring an older
version; this prevents an upload started before an A→B→A restore from silently replacing A.
FileVersionChange retains upload/restore actor, number, generation and timestamp internally.

File keeps the selected content metadata for existing search/download/share consumers.
Version snapshots stay immutable except for maintenance markers. Upload and restore
mutations use the existing tenant lock, verify effective read/file write and parent write,
and revoke external links in the same transaction. History does not restore names, ACLs,
grants, folders or old external links. Readers can download every completed retained version
of a currently accessible file; editors can publish replacement content and restore history.

Replacement uploads use signed conditional PUT, SHA-256, a fresh object key and the basic
upload cap (default 100 MiB). Request IDs bind file, uploader, generation and declaration;
retries retain the original deadline. Completion requires current authority, matching base
generation and provider HEAD size/checksum/octet-stream/ETag proof. Concurrent candidates
have distinct keys/numbers; only one can activate against a given generation. Losing or
abandoned candidates remain pending for delayed cleanup. There is no multipart replacement
or reload-resume UI for version uploads in this implementation. Existing multipart originals
can be downloaded/restored with their composite checksum and original key.

Historical downloads verify the chosen snapshot and current file access before/after
provider signing. The browser uses native attachment navigation. Bytes never enter
PostgreSQL or pass through the API. Application keys are immutable; provider administrators
can still overwrite/delete objects out of band, so this is not provider object locking.

## D. Lifecycle and accounting

Version 1 is recorded atomically when initial basic/multipart completion commits; migration
014_versions backfills existing completed rows, including retained trash/purge references.
It preserves exact keys, checksums, ETags, deadlines and content provenance.

The upload-cleanup worker now checks retained FileVersion references before deleting bytes
for an old multipart initialization intent. Replacing/restoring the current file can no
longer make the original completed object appear orphaned. Expired pending versions are
checked in batches of 50 under tenant serialization, after original deadline/grace/settle.
References remain after confirmed absence and are revisited for late writes.

Trash not-before includes the latest deadline of every version, including pending ones.
Permanent deletion checks up to 10 version references per selected file (up to 10 files
per batch), rotates attempts and requires all completed snapshots purged and all pending
snapshots cleaned before marking the logical file purged. Provider errors/deadlines cannot
advance completion. References remain after success. Restored trash remains protected.

Retained bytes sum each completed snapshot once, regardless of which is current; restore
does not copy data or double count. Pending declared bytes are reported separately until
confirmed cleanup. These per-file totals prepare Phase 19 quota work; they are not aggregate
quota enforcement, provider billing reconciliation or a claim about unknown/orphan bytes.
All completed versions remain until the entire file is permanently deleted; there is no
automatic version pruning or individually deleting history.

Bucket versioning stays disabled. Enabled/Suspended buckets fail closed in maintenance;
application snapshots do not implement S3 VersionId purge/delete-marker handling. A future
provider-versioning decision must explicitly implement and verify every provider version's
lifecycle before enabling it. Database backups cannot restore reclaimed object bytes.

## E. API

- GET /api/v1/files/{file}/versions?offset=0: 25-item page, current metadata, retained/pending bytes; offset maximum 10000.
- POST /api/v1/files/{file}/versions: request ID, base generation, size/type declaration and canonical SHA-256; returns conditional PUT ticket or completed replay metadata.
- POST /api/v1/files/{file}/versions/{version}/complete: uploader-only proof and optimistic activation; completed replay never reactivates an older version.
- POST /api/v1/files/{file}/versions/{version}/download-url: current-reader authorized historical attachment.
- POST /api/v1/files/{file}/versions/{version}/restore: current writer and base-generation check, provider proof and activation.

Current versions/generation also appear on ordinary FileRead responses. Original transfer
mutation endpoints refuse files after any version transition rather than interpreting old
session IDs/part receipts as the new content. Rename and ACL operations retain logical identity.

## F. Frontend

The page shows current version, content sizes, uploader/time, immutable history, download,
replacement selection, refresh and paging. Restoration has an explicit confirmation panel.
Query identities include workspace/user/file/page; the page remounts on scope changes.
Requests and direct PUTs use abort/session-change protection. Storage gets no account
credentials. A lost PUT acknowledgement reconciles completion; same-selection retry uses
the same request ID. Refresh/reselect after a generation conflict; abandoning navigation
leaves a pending candidate for server cleanup. History download uses the current filename.

## G. Important files

- backend/app/models/file_version.py, models/file.py, migrations/versions/014_versions.py.
- backend/app/services/versions.py, version_records.py, version_cleanup.py, trash_cleanup.py.
- backend/app/api/versions.py, schemas/versions.py, jobs/cleanup_uploads.py.
- backend/tests/api/test_versions.py, test_versions_migration.py, test_versions_integration.py.
- frontend/src/features/versions/VersionsPage.tsx, services/api.ts, types/index.ts.
- frontend/src/__tests__/Versions.test.tsx, frontend/e2e/versions.pw.ts, scripts/upload_smoke.py.

## H. Verification

Full backend suites: 257 SQLite (237.74s) and 258 PostgreSQL (268.01s), with real storage enabled. Final expanded version integration (2 cases) and API history/permission/concurrency/accounting (6 cases) pass on both DBs through full plus targeted runs, covering the current 259 cases; the expanded final collection was not rerun in one full invocation. Frontend: 81 tests, ESLint, TypeScript/Vite and Ruff/whitespace pass. All 19 Chromium journeys pass (1.4 minutes), including actual historical/current bytes, restore/reload and mobile layout. Docker HTTP/private bucket/mc/adapter and real SMTP/transfers/search/share/ACL/versions/trash smoke pass. Live head is 014_versions with no drift; maintenance tick succeeds and eight services are healthy/running. Ignored backup: .local/backups/cloudvault-before-phase14.sql (89259 bytes). Disposable test DB/buckets were cleaned; unique Docker demo data remains. See CONTINUE.md for logs and exact evidence. Tests cover history,
actual basic/multipart bytes, restoration, request replay, stale/concurrent completion,
private/viewer/editor/foreign-tenant boundaries, trash exclusions, expired pending cleanup,
provider failure, original-intent preservation, all-reference purge and migration backfill.
Injected time exercises delayed deletion; the full real-time retention period is not waited.
No remote CI, production storage certification or throughput benchmark is claimed.

## I. Operation and rollback

Back up the application DB before alembic upgrade head. Docker backend startup migrates
automatically; run docker compose up --build -d after source changes. Keep the existing
cleanup worker running. Use python scripts/docker_smoke.py and python scripts/upload_smoke.py
for unique development smoke data; destructive fixtures use disposable databases/buckets.

014_versions permits rollback of untouched initial snapshots. Any later version candidate
(even failed/cleaned) or content-change event refuses downgrade because old schemas cannot
retain its cleanup/history references. Restore a pre-upgrade backup for an unrepresentable
rollback, with a separate object backup strategy. Never enable provider bucket versioning
to work around application restore or deletion behavior.

## J. Remaining limits

Scheduling update 2026-10-15: version transfers/resume/cancel/pruning are assigned to planned Phase 14A before Phase 15. Core library recovery gaps are Phase 14B. See [the current limitations register](../LIMITATIONS_BACKLOG.md) for all closure checkpoints; scheduling does not implement these additions.

Replacement uploads are basic-only and full-buffer browser hashing, capped by UPLOAD_MAX_BYTES.
Up to 10 not-yet-cleaned pending candidates per file; there is no manual cancellation,
multipart replacement or persistent reload-resume manifest. Upload/complete/restore use
normal 10 identity/100 IP category budgets per configured window; malformed requests
precede budgets. History uses bounded offset pages; totals and pages can change concurrently.
No consistent-history snapshot, global version count or unlimited deep paging is promised.

Retained metadata and refs grow until a later retention policy. Cleanup can perform up to
100 reference checks per batch and hold tenant serialization during provider work. Real
tenant/large-history workload, abuse limits, statement timeouts, fair scheduling and
observability need production validation. Aggregate quotas/scans/audit UI remain later.
Issued URLs/received bytes cannot be recalled. Production SMTP/MFA/maintained S3 provider,
IAM/encryption/backups/monitoring/remote CI/security/deployment gates remain open.

## K. Interview discussion

Explain logical identity versus immutable content identity, generation versus selected
version number, verifying storage before activation, preserving refs before cleanup,
counting retained content once, and why application versions do not justify enabling
provider bucket versioning. Discuss stale writers, lost acknowledgements, authority changes,
bounded cleanup and the difference between a reversible trash action and irreversible purge.
