# Phase 9 — Resumable Uploads

Implemented and locally verified on 2026-10-15. Schema: 009_upload_cleanup.
Earlier phases were committed as 670d2a0; Phase 9 changes remain uncommitted.

## A. What was built

Pending multipart files expose **Resume upload** after browser reload/interruption.
CloudVault discovers actual stored progress, checks the reselected original file and
sends only missing chunks. An automatic maintenance worker reclaims expired/abandoned
uploads and names, while retaining references for retries and late provider writes.

## B. Why

An in-memory request ID and browser file handle disappear on reload. Persisted upload
identity and independently verified parts let a fresh browser discover progress safely.
Provider and database transactions cannot commit atomically; cleanup must retain enough
identity to recover a lost initialization acknowledgement and retry failed deletions.

## C. Architecture

MultipartService owns creator/workspace/parent-authorized progress and resume. File and
UploadPart remain the session/manifest/receipt store. Progress reconciles ListParts and
clears receipts for missing parts; it returns confirmed bytes, declarations, deadline and
can_resume without signing URLs. Resume compares every original digest before reconciling
parts and signing missing chunks. No public caller can supply verified receipts or keys.

UploadIntent commits server-generated tenant/file/object identity, payload fingerprint,
request identity and fixed expiry before provider creation. It deliberately has no FK
that could erase its cleanup identity when a file transaction fails or an account is
deleted. A failed initialization may leave no visible file but retains its exact key.
Retry keeps those identities/deadline and rejects changed metadata.

upload-cleanup checks up to 50 eligible File records and 50 initialization intents each
tick, rotating by last attempt. It requires an unversioned configured bucket, takes the
tenant/file lock for known records, waits beyond expiry/grace/settling, aborts pending
provider IDs, deletes abandoned objects and verifies absence before reclaiming names.
Hidden File tombstones and intents remain for repeated provider maintenance.

## D. Important files

- backend/app/services/multipart.py and schemas/multipart.py: progress and resume contracts.
- backend/app/api/multipart.py: service delegation and no-store responses.
- backend/app/models/upload_intent.py and file.py: durable intent and cleanup metadata.
- backend/migrations/versions/009_upload_cleanup.py: state/index preservation and rollback guards.
- backend/app/services/upload_cleanup.py and jobs/cleanup_uploads.py: maintenance and worker loop.
- backend/app/storage/s3.py: exact-key pending-upload inventory.
- frontend/src/services/api.ts, features/folders/UploadForm.tsx and FileList.tsx.
- backend/tests/api/test_multipart.py, test_upload_cleanup.py, test_multipart_integration.py,
  test_multipart_migration.py and test_storage.py.
- frontend/src/__tests__/Multipart.test.ts, UploadForm.test.tsx and e2e/multipart.pw.ts.
- docker-compose.yml, .env.example, scripts/upload_smoke.py and ADR-026.

## E. Technical concepts

Resume is at part boundaries: a failed partial chunk is sent again, while complete
provider-confirmed chunks are skipped. The original chunk layout is required because
SHA-256 composite integrity depends on part digests/count. Reselecting a different
file fails before missing bytes are sent. There is no persistent browser capability,
file-byte cache or attempt to access local files without a new user selection.

Conditional database/provider operations are not a distributed transaction. Durable
intent establishes an exact recovery key before provider creation. Tombstones preserve
identity after name reclamation, allowing later sweeps to catch writes that finish after
an abort/delete observation. Neither mechanism establishes immediate physical erasure.

## F. Request flows

1. Click Resume upload on a creator-owned pending multipart file.
2. POST /api/v1/files/{id}/multipart/progress rechecks authority, reconciles actual parts
   and returns saved confirmed bytes/declarations/deadline without transfer URLs.
3. Select the original file. The browser uses the server's original part size and hashes
   bounded slices. POST /multipart/resume compares the original manifest and issues
   only missing-part grants; the deadline does not change.
4. Transfer/confirm missing chunks with existing bounded retries, then verify completion.
   If a completed provider object already exists, progress can reconcile Uploaded state.
5. When every part arrived within completion grace, Verify completed upload can finish
   without sending bytes. An expired grant window cannot be extended by resume.
6. Maintenance waits until expiry plus completion grace and settling delay, then aborts
   unfinished uploads/deletes abandoned objects. Only verified absence releases names.

## G. Security

Current verified membership, tenant scope, original creator and parent authority govern
progress/resume. Removal/demotion and stale browser responses fail closed. Resume checks
all original part digests; uploaded status is still established by provider verification.
No bytes enter PostgreSQL/FastAPI. Failed cleanup retains names/references for retry.
Completed files and unexpired sessions are excluded from maintenance.

The worker is privileged, requires reviewed inventory/abort/delete/versioning permissions
and an exclusive CloudVault namespace. Supplemental unknown-orphan inventory accepts only
canonical server UUID keys, waits beyond maximum session/grace and skips known sessions.
Versioned/suspended buckets fail closed; delete markers cannot prove byte reclamation.
Cleanup identity retention is not an account-erasure or legal-compliance claim.

## H. Verification

- 206 backend tests pass on SQLite and disposable PostgreSQL cloudvault_phase9_test,
  with actual MinIO enabled. Application data is never a destructive test fixture.
- Coverage includes provider-reconciled progress, lost receipts, missing parts, unchanged
  deadlines, wrong manifests, foreign tenants/creators, expired grants and safe errors.
- Cleanup tests check expiry safety, completed/foreign files, retained names on errors,
  hidden tombstones, reclaimed names, repeated sweeps and versioned-bucket refusal.
- Actual provider tests reclaim an expired basic-upload name, remove a deliberately
  simulated late write, abort an unknown upload and clean a lost initialization
  acknowledgement through its durable exact-key intent.
- Migration tests preserve accounts/folders/basic/multipart data, compare schema/model,
  permit safe empty/basic rollback and reject loss of cleanup tombstones/intents.
- 53 frontend tests, ESLint, TypeScript/Vite build, Ruff and whitespace checks pass.
- All 14 Chromium/SMTP/storage journeys pass. The multipart journey reloads after a
  failed part, shows confirmed progress, rejects changed content without transfer,
  sends only the missing part and checks downloaded-byte hashes. Cancellation remains.
- Docker rebuild/start, HTTP/private bucket/mc/adapter smoke, real SMTP/basic/multipart
  upload/progress/resume/download and Alembic schema check pass at 009_upload_cleanup.
- The running maintenance worker and a one-shot tick complete successfully. The live
  tick had zero eligible records; actual reclamation was verified with disposable
  storage/database integration tests. One unique development smoke workspace/account
  and two completed files remain intentionally.
- Browser-owned bucket teardown completed; the ignored storage manifest is absent.
  Remote CI and production S3/R2/browser/lifecycle certification remain unrun.

## I. Decisions and tradeoffs

ADR-026 records resume, durable intent and cleanup retention. An actual provider test
exposed a MinIO inventory mismatch: a broad prefix returned no uploads. Empty-prefix
listing relies on an in-memory cache, while exact-key lookup uses provider metadata.
Durable intents therefore retain the recovery key even when database/file commit fails.
See the [pinned MinIO source](https://github.com/minio/minio/blob/7aac2a2c5b7c882e68c1ce017d8256be2feea27f/cmd/erasure-server-pool.go).

The supplementary scan has a worker-memory cursor; restart begins a new scan. Historical
untracked keys absent from provider inventory may still require provider lifecycle
cleanup. Local MinIO explicitly uses 24-hour stale-upload expiry and hourly scanning;
the full-day waiting interval has not been measured. Production needs a maintained
provider, reviewed IAM, lifecycle and compatibility verification.

## J. Operations and limitations

Docker includes upload-cleanup. Direct setups run python -m app.jobs.cleanup_uploads
with the same database/S3 settings; --once runs a single tick. Default tick interval is
60 seconds and settling delay 300 seconds, in addition to existing completion grace.
Cancelled transfers retain their original expiry; names are reclaimed after the original
deadline and safety delays. Queue size/provider latency can delay cleanup beyond one tick.
Versioning or provider errors stop unsafe reclamation and preserve retry metadata.

Back up before alembic upgrade head. Local ignored backup:
.local/backups/cloudvault-before-phase9.sql. 009_upload_cleanup refuses downgrade that
loses tombstones or initialization intents. Restore a pre-upgrade backup for rollback
that cannot represent them. Database backups cannot recover reclaimed provider bytes;
storage backup/restore requires a separate deployment plan.

Resume requires reselecting the original file within the original deadline; it does not
extend sessions or preserve partial bytes inside one part. Progress is refreshed through
API checks, not live cross-tab synchronization. Hidden maintenance metadata is retained
and periodically rechecked; compaction/retention policy and monitoring need deployment
planning. Worker running state alone is not proof of successful reclamation.

Files remain unscanned; private ACLs, trash, versions, quotas and AI remain later phases.
Phase 13 must coordinate trash retention with cleanup references; Phase 14 must extend
cleanup before enabling provider versioning. No benchmark, remote CI, production SMTP,
MFA, maintained-storage, security-audit or production-readiness claim is made.

## K. Interview discussion

- How do you resume without trusting browser state? Authorize the file and inspect
  actual provider parts, then compare the reselected file's original digest manifest.
- Why retain an initialization intent? A provider can create an upload before its
  response is lost; the database must already know the exact key for later cleanup.
- Why keep cleanup tombstones? A late write can arrive after deletion; retaining the
  reference permits another sweep while freeing the user-facing name safely.
- Why wait after cancellation? Previously issued provider capabilities and in-flight
  requests can outlive the application request; early name reuse must not reuse object keys.
- Why refuse versioned buckets? Ordinary delete can leave all historical bytes intact;
  explicit version-aware reclamation needs its own tested lifecycle policy.
