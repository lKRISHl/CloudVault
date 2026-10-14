# Phase 6 — Basic Upload

Implemented and locally verified on 2026-10-14. Phase 7 has not started.

## A. What we built

- Browser file selection, checksum calculation, direct presigned PUT and completion.
- Pending upload reservations with stable file/object IDs and idempotency request IDs.
- Signed byte length, SHA-256, generic storage content type and overwrite prevention.
- Verified completion metadata, creator/workspace/parent authorization and expiry checks.
- Retry/reconciliation within the upload window, visible errors and workspace-change guards.
- Migration, private bucket CORS, actual S3/API/browser checks and a Docker upload smoke.

## B. Why we built it

File metadata and storage adapters alone cannot establish that a user uploaded an
object. This phase connects them through direct object transfer and an authoritative
completion check. PostgreSQL keeps identity and lifecycle metadata; file bytes travel
from the browser to object storage instead of passing through FastAPI or the database.

## C. Architecture

Migration `007_uploads` adds object ID, bucket, request ID, authorization expiry,
expected checksum, verified size/checksum/storage content type/ETag and completion
timestamp to files. Old metadata remains pending with null upload fields. Constraints
require a complete upload reference and consistent verified attributes for uploaded
state; pending records cannot carry verified completion attributes. Object and
creator-scoped request uniqueness protect identity. Populated upload downgrade is
refused, including pending records with issued object references.

UploadService contains initiation, reticketing and completion logic. The API only
validates requests, derives peer IP and delegates. An injected tenant-scoped adapter
handles signing and checksum-enabled HEAD. Initiation allocates file/object metadata,
generates a grant and commits together; signing failure rolls back the reservation.
The signed URL itself is never persisted and its response uses Cache-Control: no-store.

An internal S3 endpoint serves API inspection; a separate public endpoint serves
browser signing. Compose uses `http://minio:9000` internally and
`http://localhost:9000` publicly. The URL is signed for its final host; rewriting a
signed internal URL would invalidate it. Configured MinIO CORS permits the local app,
Vite development and disposable browser-test origins. Anonymous access remains disabled.

## D. Important files

- `backend/app/services/uploads.py`: authorization, lifecycle, idempotency and verification.
- `backend/app/schemas/uploads.py`, `api/files.py`, `api/storage.py`: typed requests,
  upload endpoints and adapter dependency lifecycle.
- `backend/app/models/file.py`, `schemas/files.py`: persisted reference/verified fields.
- `backend/migrations/versions/007_uploads.py`: additive schema and guarded rollback.
- `backend/app/storage/base.py`, `storage/s3.py`: upload grants and checksum inspection.
- `backend/tests/api/test_uploads.py`, `test_uploads_integration.py`,
  `test_upload_migration.py`: policy, real transfer and migration coverage.
- `frontend/src/features/folders/UploadForm.tsx`, `FileList.tsx`, `FoldersPage.tsx`:
  selection, stages, verified status, pending retry and parent write controls.
- `frontend/src/services/api.ts`, `types/index.ts`: transfer orchestration and typed metadata.
- `frontend/src/__tests__/UploadForm.test.tsx`, `e2e/uploads.pw.ts`: UI and real Chromium tests.
- `scripts/account_e2e_stack.py`, `frontend/e2e/storage-teardown.ts`: disposable
  database/mailbox/bucket and cleanup even after Windows stops the web server.
- `scripts/upload_smoke.py`: real Docker API/SMTP/direct-storage flow.
- `docker-compose.yml`, `.env.example`, `.github/workflows/ci.yml`: configuration/CORS/checks.

## E. Technical concepts

**Presigned capabilities:** A signed URL authorizes one object operation for a limited
period. The browser sends no CloudVault cookies or bearer token to storage. Signing
binds byte count, checksum, Content-Type and If-None-Match; clients cannot substitute
an arbitrary key or silently overwrite the object. An issued URL remains usable until
its expiry even if application membership is later revoked; API completion rechecks
current authority. Treat URLs as temporary secrets.
[AWS presigned URL reference](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html).

**Checksum versus safety:** WebCrypto calculates SHA-256 from the selected bytes.
The provider validates the signed checksum during PUT and supplies it on a
checksum-enabled HEAD. Completion checks actual size/checksum/type against the stored
declaration. This establishes transferred content integrity, not malware safety or
detected MIME. Objects are stored as application/octet-stream; declared MIME stays
untrusted. Uploaded is deliberately distinct from scanned or safe to preview.
[Boto3 HEAD reference](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/head_object.html).

**Idempotency and reconciliation:** A request UUID belongs to one creator in one
tenant and one declaration. Repeating it reuses the pending identity; changed metadata
is rejected. Completion is idempotent and serialized. If the PUT response is lost,
the client tries completion; a subsequent conditional PUT can return 412 because
the first write already succeeded. The API still verifies the actual object.

## F. Request flow

1. A verified active member opens root or a writable folder and selects a file.
2. The UI checks the configured size limit, hashes bytes and submits name, folder,
   declared size/type, checksum and request UUID to POST `/api/v1/files/uploads`.
3. The service applies persistent grant rate limits, locks the tenant, rechecks
   membership/parent authority and reserves pending metadata. A signed PUT ticket
   returns the file, URL, required headers and expiry.
4. The browser transfers the File directly with credentials omitted and no referrer.
   It checks session generation before continuing and aborts transfer on unmount.
5. POST `/api/v1/files/{id}/complete` rechecks creator, tenant and current parent
   authority, validates the completion window and inspects the stored object. Missing,
   mismatched or unavailable objects do not become uploaded.
6. Success persists verified storage facts and completion time, then refreshes the
   scoped file listing. UI shows Uploaded, verified size and Unscanned.
7. A creator can choose the original file and POST `/{id}/upload-url` with its
   checksum to retry within the original window. No expiry extension or byte-level
   resume exists yet. Already completed records reconcile only with matching content.

## G. Security and privacy

Initiation requires verified active workspace membership, creator/manager authority
on a selected parent, and server-derived tenant/creator identity. Root uploads are
allowed for verified members. Completion/reticketing belongs to the original creator;
organization managers cannot complete another person's pending upload. Every UUID
lookup includes the selected tenant; foreign file/folder IDs return 404. Parent
authority and revoked membership are checked again during completion.

Tenant locks serialize reservations/completion with hierarchy and organization writes.
Database checks/unique indexes back the service. Hashes are canonical base64 SHA-256;
extra identity, object, bucket and status fields are rejected. The client cannot
declare itself uploaded or supply verified attributes. Provider errors fail safely.

Grant and completion categories reuse persistent AccountService counters: by default
10 requests per identity/category and 100 per peer IP/category per 15 minutes. Initial
and retry grants share their category. Deployment proxy handling and later abuse/quotas
remain separate work. Uploads are capped at 100 MiB; operators can lower the cap.

Signing responses are not cached; URLs stay in memory. Workspace/session generation
guards prevent continuation under another tenant, including direct transfer callbacks.
The existing shared-workspace read policy applies to metadata, not a public bucket.
No download/preview endpoint is introduced here.

## H. Verification

- 174 backend tests pass on SQLite and PostgreSQL with real MinIO enabled.
  PostgreSQL uses disposable `cloudvault_phase6_test`, never application data.
- Upload policy tests cover pending persistence, hidden storage refs, idempotency,
  changed-request conflicts, creator/parent/tenant authority, revoked/demoted membership,
  malformed/forged input, max size, expired grants/completion, missing/mismatched objects,
  provider failures, signing rollback, rate limits, concurrent start/completion and
  database rejection of forged uploaded facts or null verified content type.
- Two real API/storage integration tests transfer actual bytes through signed URLs,
  verify completion/readback and reject replay, changed byte length, wrong checksum,
  changed content type and provider metadata that does not match declarations.
- Seeded SQLite/PostgreSQL migration tests preserve accounts/password hashes,
  folders and legacy pending metadata across downgrade/re-upgrade. Upload refs block
  destructive downgrade and remain intact. Full disposable PostgreSQL upgrade/check/
  downgrade-to-base/re-upgrade passes; no schema differences are detected.
- 39 frontend tests pass, including hashing, direct credential-free transfer,
  oversized selection, lost acknowledgement, conditional replay reconciliation,
  pending retry, wrong selected content, settings recovery and workspace change.
- 12 Chromium/SMTP journeys pass with actual MinIO: real file selection, browser
  CORS/direct PUT, verified listing, reload persistence and workspace isolation.
  The browser database/mailbox and uniquely owned bucket are disposable.
- The upload journey waits for the destination breadcrumb before selecting a file;
  selecting the previous root picker during navigation would lose the selection.
  Explicit parent-process storage teardown handles Windows force-stopped servers.
  Earlier failed-run empty buckets were identified and removed without touching app data.
- Ruff, ESLint, TypeScript/Vite build and whitespace checks pass. Node type definitions
  support the real WebCrypto unit-test import; npm installation/audit reports zero known
  vulnerabilities at this verification point, not a guarantee against unknown issues.
- Docker is rebuilt and migrated at `007_uploads`; HTTP/private-storage/adapter smoke
  passes. Actual Docker registration and SMTP verification, public-host signing,
  direct transfer, checksum completion and list persistence pass through the frontend proxy.
- Ignored pre-upgrade backup: `.local/backups/cloudvault-before-phase6.sql`.
  Unique Docker smoke identity/workspace/file remains as intentional development data.
  Phases 4–6 are uncommitted. CI definitions are updated; no remote CI was dispatched.

## I. Decisions and tradeoffs

ADR-022 records conditional checksummed PUT, private bucket/CORS, separate signing
endpoint, pending-to-uploaded verification, finite grants and creator-scoped retry.
One basic single-object attempt is stored on the file; later resumability/versioning
needs richer session/attempt lifecycle. Browser hashing buffers the file, bounded
by the 100 MiB cap; large-file multipart/streaming hashing is later work.
Completion holds the tenant lock during provider inspection for consistent authority;
later optimization needs measured latency/concurrency evidence.

## J. Operation and limitations

Open `http://localhost:3000/app/folders`, verify your account, select a writable
location and upload. The running Docker app is migrated. After source changes run
`docker compose up --build -d`, then `python scripts/docker_smoke.py`. The optional
`python scripts/upload_smoke.py` creates a unique development account/workspace/file
and verifies the actual SMTP-to-upload flow; its demo data remains.

Direct setups must back up, install backend requirements and apply `alembic upgrade head`.
Set an API-reachable S3_ENDPOINT and browser-reachable S3_PUBLIC_ENDPOINT for the same
provider/bucket. Configure production CORS for exact application origins and signed
PUT headers. Public-endpoint HTTPS is required in production. A local bucket's CORS
origin allowlist is configured by Compose; CORS does not replace signing/private IAM.

Default maximum is 100 MiB, URL lifetime 15 minutes and completion grace 5 minutes.
Rate limits, depth 64 and pages of 25 (API max 100) also apply. Uploaded files are
unscanned; download is Phase 7, multipart Phase 8, resume/abandoned cleanup Phase 9,
resource ACLs Phase 12, trash Phase 13, versions Phase 14 and scanning Phase 17.
Expired pending records still reserve their names, and abandoned objects/records
are retained until the later cleanup lifecycle. Legacy metadata without an upload
reference cannot be completed/reticketed. No aggregate quota enforcement exists yet.

Already-issued storage capabilities cannot be immediately revoked by application
logout/removal, but completion requires current membership and parent authority.
Lost acknowledgements/aborts can leave an object to reconcile or clean up. URL expiry
can be shortened by provider credential expiry; correct clocks/provider compatibility
are deployment prerequisites. Object HEAD/checksum support and conditional writes
must be verified on the selected production provider; local MinIO alone does not
verify S3/R2 deployment. Public transfers are PUT only; bucket access remains private.

Populated upload downgrade is refused; restore a pre-upgrade backup for rollback.
Tests use disposable databases and unique buckets. With TEST_S3_ENDPOINT,
TEST_S3_ACCESS_KEY and TEST_S3_SECRET_KEY set, run backend tests or frontend
`npm run test:e2e` for real upload checks. Without those variables, real provider
tests and the upload browser journey explicitly skip. The browser harness writes an
ignored `.local/e2e-storage.json` manifest for owned-bucket cleanup; a failed teardown
can be retried with the same TEST_S3 variables and
`python scripts/account_e2e_stack.py --cleanup-storage`. It validates bucket prefix
and provider origin and never clears the application bucket.

Normal readiness still checks the database; operator smoke checks storage. Production
IAM/encryption/provider/public-access controls, maintained storage, quotas, backups,
monitoring, independent security review, MFA, production SMTP and remote CI remain
pending. Account deletion preserves organizational metadata/objects and pseudonymous
creator references. This is local phase completion, not production certification.

## K. Interview questions

**Why inspect storage after upload?** A browser response is not proof that the declared
object exists or has the right bytes. The server checks actual provider facts.

**How is overwrite prevented?** Signed If-None-Match binds conditional creation;
replay cannot replace an existing object. Completion verifies bytes even after a 412.

**Why two endpoints?** Containers reach MinIO by service name; browsers need a public
host. Signature V4 includes the final host, so sign correctly instead of rewriting URLs.

**What does uploaded prove?** Stored size/checksum/type match the reservation. It does
not prove malware safety, MIME detection, long-term durability or production readiness.

**What happens after revocation during transfer?** An issued capability can finish
until expiry, but the application refuses completion without current authority.
Later cleanup handles abandoned objects; no immediate-capability-revocation claim.

Next: Phase 7 — Basic Download, only on explicit instruction.
