# Phase 8 — Chunked/Multipart Uploads

Implemented and tested locally on 2026-10-14. Database migration: 008_multipart.

## A. What was built

Verified upload creators can transfer files in checksummed chunks, retry failed parts,
verify completion and cancel unfinished transfers. The folder browser supports an
explicit multipart option and uses it automatically above the basic upload cap.
Completed multipart files use the existing authorized download flow.

## B. Why

Basic uploads hash the whole file in browser memory and cap at 100 MiB. Multipart
hashing processes bounded slices and transfers them directly to private storage.
Independent part verification prevents a client receipt from becoming proof of stored
bytes, and retrying a failed part avoids resending already confirmed parts.

## C. Architecture

Routes delegate to MultipartService. It applies persistent rate limits, locks the
workspace, checks current verified membership and parent write authority, and scopes
the file lookup to the selected tenant. Control is restricted to the original creator.
Files hold private provider upload identity/deadline and multipart state. upload_parts
holds declarations and provider-confirmed ETag/time, with a composite file/number key.
Parts are reached through the authorized file. PostgreSQL stores metadata only.

The S3 adapter creates SHA-256 COMPOSITE uploads, signs UploadPart length/checksum,
inspects/paginates ListParts, completes conditionally and aborts. Blocking SDK calls
use executor threads and existing bounded timeouts/retries. Public signing and internal
inspection endpoints remain separate, with UUID-only tenant/file/object keys.

## D. Important files

- backend/app/services/multipart.py, schemas/multipart.py and api/multipart.py.
- backend/app/models/file.py, upload_part.py and migrations/versions/008_multipart.py.
- backend/app/storage/base.py and s3.py; services/downloads.py reconstructs composite checksums.
- frontend/src/services/api.ts, features/folders/UploadForm.tsx and FileList.tsx.
- backend/tests/api/test_multipart.py, test_multipart_integration.py, test_multipart_migration.py and test_storage.py.
- frontend/src/__tests__/Multipart.test.ts and e2e/multipart.pw.ts.
- scripts/upload_smoke.py; .env.example, docker-compose.yml and CI definitions.

## E. Technical concepts

AWS SHA-256 multipart checksums are composite. Each part has its own SHA-256; the final
digest is SHA-256 over the concatenated binary part digests. The provider encodes the
digest in base64 and appends -N. CloudVault stores the base64 digest, explicit
sha256-composite kind and part count, and reconstructs the provider representation for
download verification. This is distinct from SHA-256 over the complete file bytes.
See [AWS checksum documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html).

The browser keeps a bounded part buffer and a small digest manifest rather than a
whole-file buffer. It sends Blob slices with credentials omitted/no referrer. ETags are
provider receipts, not cryptographic hashes. Clients cannot choose provider upload IDs,
object keys or verified completion metadata.

## F. Request flows

1. Hash bounded slices and POST /api/v1/files/multipart/uploads with metadata, request ID,
   fixed chunk size and part checksums. Matching request replay returns the same transfer.
2. PUT each unconfirmed slice to its signed URL; POST the file's
   /multipart/parts/{number}/confirm endpoint. CloudVault checks actual size/hash/receipt.
3. Reconcile a lost transfer acknowledgement through confirmation. If the part is still
   absent, obtain /multipart/parts/{number}/url and retry, up to three browser attempts.
4. POST /multipart/complete. Inspect all stored parts, compare all declarations, perform
   conditional assembly, inspect final size/composite hash/type and commit Uploaded.
5. POST /multipart/abort to request provider cancellation and persist aborted state.
   Completed files cannot be cancelled. Aborted metadata/name remains reserved.

## G. Security

Tenant/creator/parent checks apply to all control operations. Workspace serialization
protects them against concurrent membership/hierarchy changes. Foreign/nonexistent
resources fail closed; demotion and removal cannot use old roles to finish a transfer.
Provider errors hide internal details, tickets are no-store and internal identities are
absent from public file metadata. The basic upload completion API rejects multipart files.

Parts are size/checksum bound and completion checks actual provider state independently.
All current verified workspace members can download completed files under existing read
policy. Files remain unscanned. Signed capabilities can survive app revocation until
expiry; completion still requires current authority. Abort cannot prove immediate byte
cleanup while a provider part write is in flight.

## H. Verification

- 197 backend tests pass on SQLite and disposable PostgreSQL cloudvault_phase8_test,
  including actual MinIO transfers. Tests never clear the application database/bucket.
- Tests cover request replay/declaration conflicts, bounds, foreign tenants, creator
  ownership, demotion/removal, expiry, missing/corrupt parts, safe provider errors,
  initialization rollback/abort, persisted receipts and lost completion acknowledgement.
- Real S3 checks reject wrong part length/hash, verify assembled bytes/downloads and
  provider composite metadata, and reject a part URL after cancellation.
- Adapter checks cover scope, signed headers, pagination/progress and safe NoSuchUpload.
- Migration tests preserve accounts/folders/basic data, check schema alignment, permit
  basic-only rollback/re-upgrade and refuse loss of populated multipart state.
- 49 frontend tests, ESLint and TypeScript/Vite build pass. Multipart tests cover bounded
  hashing, credential-free transfer, acknowledgement reconciliation, retry budgets,
  skipped receipts, invalid plans, abort and stale workspace responses.
- All 14 Chromium/SMTP/storage journeys pass, including multipart downloaded-byte hashes,
  reload persistence and cancellation after a simulated provider outage.
- Earlier test assertions were corrected for an empty referrer and host/browser number
  locale difference. A test-server memory interruption was resolved by bounded test
  payload/hash comparison. Docker stopped during one backend run; four provider tests
  failed to connect, then complete SQLite/PostgreSQL suites passed after restart.
- Browser-owned bucket cleanup completed; the ignored storage manifest is absent.
  Remote CI and production provider/browser certification remain unrun.
- Full Docker rebuild/start, HTTP/private bucket/mc/adapter smoke and actual Docker
  SMTP/basic/multipart upload/download checks pass. The live database is at
  008_multipart; Alembic check reports no schema drift. One unique development
  account/workspace and two smoke files remain intentionally.

## I. Decisions and tradeoffs

ADR-025 records composite integrity, metadata persistence, bounds and failure semantics.
Provider/database commits cannot be atomic. Known initialization failures attempt abort;
unknown acknowledgements can leave provider orphans. Completion retries inspect an
already assembled object to reconcile a lost response or database commit.

## J. Operations and limitations

Default maximum 1 GiB, part size 8 MiB, maximum 1024 parts and upload deadline one hour.
Configuration permits maximum 5 GiB, parts 5–32 MiB and deadline up to two hours; the
part-count bound still applies. Part URLs last at most the basic URL duration (15 minutes
default) or remaining deadline. New grants never extend the deadline. Confirmation and
completion permit the existing five-minute grace. Empty files use basic upload.

Start/completion/abort use normal account category limits (10 identity/100 IP by default).
Part grants/confirmations use 4096 identity/16384 IP per configured window (15 minutes
default). There is no aggregate quota/scan claim. These limits require production abuse
review. Tenant writes serialize; throughput has not been benchmarked.

Back up before alembic upgrade head. Docker backend startup migrates automatically.
An ignored pre-upgrade backup is .local/backups/cloudvault-before-phase8.sql. Downgrade
refuses any multipart record; restore a pre-upgrade backup for unrepresentable rollback.
Run docker compose up --build -d, python scripts/docker_smoke.py and
python scripts/upload_smoke.py. The latter keeps unique development demo data.

Confirmed receipts support retry in the current form with the same selected file/request
ID. Browser-reload resume, progress discovery, automatic abandoned/expired upload and
unknown-orphan cleanup are Phase 9. Cancelled names remain reserved. Concurrent abort
may require repeated provider cleanup/lifecycle work; no automatic production lifecycle
rule is configured. Versioned byte purge, ACLs, scanning, quotas, AI, production SMTP,
MFA, maintained storage, monitoring, backups/restore and deployment gates remain later.

## K. Interview discussion

- Why keep transfer bytes outside FastAPI/PostgreSQL? It separates authorization and
  metadata transactions from bandwidth and avoids whole-file server buffering.
- Why inspect provider receipts? Client acknowledgements do not prove stored integrity.
- How does composite SHA-256 differ? It hashes part digests, so it depends on chunk layout
  and must not be compared directly with a whole-file SHA-256.
- What happens after a lost completion response? Reinspect the deterministic object and
  commit only if its declared integrity matches; retry is idempotent.
- What remains for resume? Discover authorized persisted progress, match the reselected
  file and reclaim expired/abandoned resources safely across database/provider failures.
