# CloudVault — Current State

Current Phase:
Phase 8 — Chunked/Multipart Uploads

Status:
Implementation and local verification complete on 2026-10-14. Project is D:\CloudVault-Dev\Project\CloudVault. Docker app: http://localhost:3000/app/folders. Live schema: 008_multipart, with no Alembic schema drift. Phases 4–8 and the frontend redesign remain uncommitted. No push or remote CI was performed.

Completed Work:
- Verified global accounts, encrypted SMTP outbox/dispatcher, revocable workspace sessions, memberships/ownership, hierarchical folders, file metadata and private storage remain implemented.
- Basic uploads remain capped at 100 MiB, with signed conditional size/SHA-256 PUT and provider-verified completion. Current verified members can download completed files through checked, short-lived attachment URLs.
- MultipartService adds creator/tenant/parent-authorized initiation, part grants/confirmation, conditional completion and explicit cancellation. Tenant write serialization protects control operations against concurrent permission/hierarchy changes.
- Files persist private provider upload identity, request identity, fixed part size/count, deadline and transfer state; upload_parts persists declarations and independently inspected receipts. Public metadata hides provider IDs, bucket and object identity. PostgreSQL stores no file bytes.
- The browser hashes bounded slices sequentially, sends Blob parts directly without application credentials/referrer, reconciles acknowledgements and retries each part at most three times. Retry with the same selected file/request ID can skip confirmed parts in the current form. UI supports cancellation in the form or pending file row.
- Provider ListParts must match every declared part. Completion uses If-None-Match and final HEAD size/composite SHA-256/type verification before Uploaded. Existing-object inspection reconciles lost completion acknowledgement. Basic completion rejects multipart records.
- Composite SHA-256 is stored with explicit sha256-composite kind and part count; it is not a whole-file hash. Download verification reconstructs the provider digest-count representation.
- Migration 008_multipart preserves basic uploads/accounts/folders, adds coherent transfer state and receipts, and refuses downgrade while any multipart record exists. An ignored pre-upgrade database backup is preserved.
- Shared frontend shell/auth styling and responsive navigation remain. Project, Codex and Docker development storage physically reside on D: with C: compatibility junctions; shared Windows/system files may still use C:.

Important Files:
- backend/app/services/multipart.py, schemas/multipart.py, api/multipart.py.
- backend/app/models/file.py, upload_part.py, migrations/versions/008_multipart.py.
- backend/app/storage/base.py, s3.py, services/downloads.py, uploads.py and accounts.py.
- frontend/src/services/api.ts, features/folders/UploadForm.tsx and FileList.tsx.
- backend/tests/api/test_multipart.py, test_multipart_integration.py, test_multipart_migration.py and test_storage.py.
- frontend/src/__tests__/Multipart.test.ts and e2e/multipart.pw.ts.
- scripts/upload_smoke.py, account_e2e_stack.py; docs/phases/phase8.md and ADR-025.

Verification Passed:
- 197 backend tests pass on SQLite and disposable PostgreSQL cloudvault_phase8_test, with actual MinIO enabled. Migration tests create separate temporary databases; destructive fixtures never use application data.
- Coverage includes tenant/creator isolation, changed parent authority, expiry, request replay/conflicts, corrupt/missing parts, safe provider errors, initialization rollback/abort, receipts, separate rate budgets and lost completion acknowledgement.
- Actual signed transfers reject wrong length/checksum, assemble/download exact bytes and verify composite metadata. Cancelled provider uploads reject old part URLs. Adapter scope/signature/pagination/missing-upload checks pass.
- Migration checks preserve basic files/accounts/folders, compare ORM/schema, permit basic-only downgrade/re-upgrade and refuse populated multipart rollback.
- 49 frontend tests, ESLint, TypeScript/Vite build and Ruff pass. Tests cover bounded hashing, credential-free transfer, retries/reconciliation, confirmed-part skipping, invalid plans, abort and stale workspace responses.
- All 14 Chromium/SMTP/storage journeys pass. Multipart journey checks uploaded size, native downloaded-byte hash/filename, reload persistence and cancellation after a simulated failed part. Prior account/workspace/folder/basic upload/download and responsive navigation journeys remain green.
- Full Docker rebuild/start, private bucket/mc/adapter smoke and actual Docker SMTP/basic/multipart upload/download checks pass. Live schema is 008_multipart; Alembic check finds no upgrade operations. One unique smoke account/workspace and two files remain as development data.
- Earlier browser assertions needed empty-referrer/locale corrections. Test-server memory failure was resolved by bounded test payload/hash comparison. Docker stopped during one backend run: four provider checks failed to connect, then full SQLite/PostgreSQL suites passed after restart. No failed check is counted as passing.
- Disposable browser bucket cleanup completed; .local/e2e-storage.json is absent. CI definitions include multipart provider/browser checks; remote CI remains unrun.

Remaining Limits:
- Phase 9 must add authorized progress discovery, reload-based resume and automated expired/abandoned/unknown-orphan cleanup. Current-form retry is not reload resume. Pending/aborted names remain reserved.
- Provider/database transactions cannot be atomic. Known failed initialization attempts abort; unknown create acknowledgements may leave untracked provider uploads. Abort cannot prove immediate cleanup of concurrent in-flight parts. Production lifecycle rules require configuration/verification; none is automatically configured here.
- Default multipart cap 1 GiB, chunk size 8 MiB, at most 1024 parts and one-hour deadline. Settings allow up to 5 GiB, 5–32 MiB parts and two hours; part-count bound still applies. Basic upload remains 100 MiB with whole-file buffering. No aggregate quota or benchmark claim exists.
- Part grants last at most UPLOAD_URL_SECONDS (15 minutes default) or remaining session time; they never extend the deadline. Confirmation/completion permit five-minute grace. Separate part categories allow 4096 identity/16384 IP per configured rate window; start/complete/abort retain normal 10/100 defaults.
- Issued storage capabilities remain reusable until expiry and can survive app permission revocation; completion/new grants recheck authority. Native downloads may continue after logout/removal. HEAD does not pin GET to a version; out-of-band replacement remains a provider/versioning limitation.
- Uploaded files remain unscanned, generic attachment downloads with no safe inline preview/MIME detection. All verified workspace members share read access; private ACLs Phase 12, sharing 11, trash 13, versions 14, scans 17, quotas 19 and AI 21 onward remain upcoming.
- Normal readiness checks database only; operator smoke checks storage. Community MinIO is archived and local-only. Production needs maintained storage, S3/R2/browser verification, reviewed IAM/encryption/public access/CORS, lifecycle/version purge, monitoring, backup/restore, production SMTP, MFA, abuse/security review and deployment hardening.
- SMTP ambiguous acknowledgements can duplicate mail; action links remain single-use. Key rotation affects queued email. Content/identity retention is not a complete-erasure/legal-compliance claim. Full tab/live synchronization remains later.
- Docker WSL is capped at 4 GB; keep image builds separate from full test/browser workloads. Shared Windows tools/system temporary files may still use C:.

Operation:
- Docker: docker compose up --build -d; python scripts/docker_smoke.py; python scripts/upload_smoke.py. Mailpit localhost:8025/SMTP1025; dispatcher is in Compose.
- Direct: install backend requirements, back up, apply alembic upgrade head (008_multipart), configure matching S3/public endpoint/SMTP/signing settings and run API/dispatcher. Restore a pre-upgrade backup if downgrade cannot safely represent populated multipart state.
- Multipart defaults are in .env.example and forwarded by Compose. Select Use multipart upload, or choose a file above the basic cap. Empty files use basic upload.
- Provider/browser tests require TEST_S3_ENDPOINT/ACCESS_KEY/SECRET_KEY and unique disposable buckets. A failed teardown leaves an ignored validated manifest; recover with the same test settings and python scripts/account_e2e_stack.py --cleanup-storage.
- .local/backups/cloudvault-before-phase8.sql and earlier backups are ignored and preserved. Private storage-migration scripts/status/backups remain outside Git under D:\CloudVault-Dev\Migration. Never commit credentials/backups.

Next Exact Phase:
Phase 9 — Resumable Uploads, only after explicit instruction. Remote CI requires separately authorized push/dispatch.

Last Commit:
5c5bccd — phase 3 complete. Phases 4–8 and frontend redesign remain uncommitted.

Read docs/phases/phase8.md for architecture, operations, security, limitations and interview discussion.
