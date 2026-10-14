# CloudVault — Current State

Current Phase:
Phase 9 — Resumable Uploads

Status:
Implementation and local verification complete on 2026-10-15. Project: D:\CloudVault-Dev\Project\CloudVault. Docker app: http://localhost:3000/app/folders. Live schema: 009_upload_cleanup, with no Alembic schema drift. Phases 4–8/frontend redesign were committed as 670d2a0. Phase 9 remains uncommitted. No push or remote CI was performed.

Completed Work:
- Verified global accounts, encrypted SMTP outbox/dispatcher, revocable workspace sessions, membership/ownership, folders, metadata, private storage, basic/multipart upload and authorized attachment downloads remain.
- Progress/resume recheck current creator, verified membership and parent authority under tenant serialization. Provider ListParts determines actual receipts; missing parts lose confirmed state. Progress returns confirmed bytes/declarations/deadline without URLs.
- Reload recovery selects a pending file, shows saved progress and requires reselecting the original content. Browser hashing uses the original chunk size; resume checks every original digest and signs only missing chunks. Existing bounded retry/completion integrity remain. Deadlines never extend.
- Uploaded-object reconciliation updates the UI after lost completion acknowledgement. If every part arrived within grace, Verify completed upload can finish without transfer. Expired grant windows fail closed and require a fresh session after cleanup.
- UploadIntent commits exact UUID key, immutable payload fingerprint and fixed expiry before provider create. It survives file-transaction rollback/account deletion, so lost initialization acknowledgement does not lose the cleanup key. Retry reuses identity/deadline and rejects changed declarations.
- upload-cleanup in Compose/direct setups checks expired pending File records and initialization intents, after completion grace plus settling delay. It aborts provider uploads, deletes abandoned objects and checks absence before names are reclaimed. Errors retain references/names for retry and rotate attempts.
- Hidden File tombstones release names through partial unique indexes while retaining cleanup references for repeated late-write/provider sweeps. Completed/unexpired files are excluded. Initialization intents retain exact keys for orphan cleanup even without visible files.
- MinIO broad-prefix inventory proved incomplete in real tests. Current intent cleanup uses persistent exact-key inventory. A supplemental canonical-UUID-key scan handles provider-reported old unknown uploads. Local MinIO stale-upload expiry is explicitly 24 hours with hourly scanning.
- Migration 009_upload_cleanup preserves prior data, adds intent/cleanup metadata and indexes, and refuses downgrade that discards tombstones/intents. Ignored pre-upgrade database backup is preserved. No file bytes enter PostgreSQL or FastAPI.
- Project/Codex/Docker development storage remains on D: with compatibility junctions. Shared Windows/system files may still use C:.

Important Files:
- backend/app/services/multipart.py, schemas/multipart.py and api/multipart.py.
- backend/app/models/upload_intent.py, file.py and migrations/versions/009_upload_cleanup.py.
- backend/app/services/upload_cleanup.py, jobs/cleanup_uploads.py and storage/s3.py.
- frontend/src/services/api.ts, features/folders/UploadForm.tsx and FileList.tsx.
- backend/tests/api/test_multipart.py, test_upload_cleanup.py, test_multipart_integration.py, test_multipart_migration.py and test_storage.py.
- frontend/src/__tests__/Multipart.test.ts, UploadForm.test.tsx and e2e/multipart.pw.ts.
- docker-compose.yml, .env.example, scripts/upload_smoke.py and docs/phases/phase9.md/ADR-026.

Verification Passed:
- 206 backend tests pass on SQLite and disposable PostgreSQL cloudvault_phase9_test, with actual MinIO enabled. Migration fixtures use separate temporary databases. Destructive tests never point at app data.
- Progress/resume coverage: actual/missing receipts, unchanged windows, original manifests, foreign tenants/creators, expiry, safe errors and lost initialization acknowledgements.
- Cleanup coverage: safety delays, completed/foreign files, retained names on provider failure, hidden references, name reclamation/repeated sweeps, versioned-bucket refusal, canonical-key filtering and exact-key inventory.
- Real integration checks reclaim an expired basic-upload name, clean a simulated late write, abort an unknown provider upload and recover an initialization with lost acknowledgement through its durable intent. Private completed-file upload/download integrity remains green.
- Migration checks preserve accounts/folders/basic/multipart data, compare schema/model, permit representable rollback and reject loss of tombstones/intents.
- 53 frontend tests, ESLint, TypeScript/Vite build and Ruff pass. Tests cover original chunk layout, missing-part resume, stale workspace responses, changed file selection, expired controls and already-completed progress reconciliation.
- All 14 Chromium/SMTP/storage journeys pass. Resume journey reloads after failed part, shows saved progress, rejects wrong content with no transfer, sends exactly one missing chunk and verifies native downloaded-byte hashes. Account/workspace/folder/basic upload/download/cancellation/mobile journeys remain green.
- Full Docker rebuild/start, HTTP/private bucket/mc/adapter smoke and actual Docker SMTP/basic/multipart upload/progress/resume/download pass. Live schema is 009_upload_cleanup with no schema drift.
- Maintenance worker logs successful ticks and one-shot execution succeeds. The live tick had zero eligible records; actual reclamation is established by disposable real-provider integration tests. The unique smoke account/workspace and two completed files remain as development data.
- Browser-owned bucket teardown completed; .local/e2e-storage.json is absent. CI definitions include multipart provider/browser/maintenance checks; remote CI remains unrun.
- Fresh Phases 0–9 regression rerun on 2026-10-15: 206 tests pass on SQLite (107.30 seconds) and PostgreSQL (118.44 seconds), 53 frontend tests and all 14 Chromium journeys (41.6 seconds). Ruff, ESLint, production build, Docker private storage/SMTP/upload/progress/resume/download, live schema alignment and maintenance checks pass with no failures. This tests the current uncommitted Phase 9 working tree over 670d2a0, not a remote CI run.
- Rerun evidence is ignored under .local/regression-{sqlite,postgres,frontend,browser,docker}.log. The fresh disposable PostgreSQL database and owned browser/provider buckets were used; application tables were never cleared. Docker smoke adds one unique demonstration workspace/account and two completed files intentionally.

Remaining Limits:
- Resume occurs at part boundaries and requires reselecting the original file within its original deadline. Partial bytes inside an unfinished part are resent. No persisted browser capabilities/file cache or live cross-tab progress exists.
- Cancelled names are reclaimed only after original expiry, completion grace and settling delay; provider latency/queue size can add delay. Tombstones/intents are retained and rechecked; metadata compaction/retention remains operational work, not a complete-erasure claim.
- Provider/database transactions are not atomic. Repeated references/exact-key intent inventory cover current failed/late operations, but provider abort cannot prove instant physical cleanup of concurrent bytes. Historical untracked keys missing from MinIO inventory may require its stale-upload cleanup. The full 24-hour lifecycle waiting period is not measured.
- Supplemental inventory cursor is in worker memory and restarts from the beginning. Maintenance is privileged and requires an exclusive CloudVault namespace and reviewed IAM. Current job checks at most 50 File records/50 intents per tick. Throughput has not been benchmarked.
- Versioned/suspended buckets fail closed; ordinary delete markers do not prove byte reclamation. Phase 13 must coordinate trash/cleanup references and Phase 14 must implement version-aware cleanup before enabling bucket versioning. SQL backups cannot recover reclaimed object bytes; provider backup/restore needs separate verification.
- Multipart defaults: 1 GiB, 8 MiB parts, 1024-part bound, one-hour deadline. Settings allow up to 5 GiB, 5–32 MiB and two hours; count bound applies. Basic cap remains 100 MiB/full-buffer hashing. No aggregate quota/scan claim.
- Part grants last at most UPLOAD_URL_SECONDS (15 minutes default) or remaining deadline; five-minute completion grace. Part categories allow 4096 identity/16384 IP per window; normal control categories default 10/100. Progress/resume have separate normal control categories.
- Issued storage capabilities survive app revocation until expiry; completion/new grants recheck authority. Downloads are reusable capabilities, not immediately revocable/version-pinned or delivery telemetry. Out-of-band replacement after HEAD remains a provider/versioning limitation.
- Uploaded files remain unscanned. All verified workspace members share read access; sharing Phase 11, private ACLs 12, trash 13, versions 14, scans 17, quotas 19 and AI 21 onward remain upcoming.
- Normal readiness is database-only; operator smoke checks storage. Community MinIO remains archived/local-only. Maintained storage, production S3/R2/browser/lifecycle/IAM/CORS/encryption/public access, monitoring, object/DB backup/restore, production SMTP, MFA, abuse/security review and deployment hardening remain gates. Worker running state is not proof of successful cleanup; inspect results/errors and add production alerting.
- SMTP ambiguous acknowledgement may duplicate mail; action links remain single-use. Key rotation affects queued email. Content/identity retention is not complete legal erasure. Full tab/live synchronization remains later.
- Docker WSL is capped at 4 GB; keep image builds separate from full test/browser workloads. Shared Windows/system temporary files may use C:.

Operation:
- Docker: docker compose up --build -d; python scripts/docker_smoke.py; python scripts/upload_smoke.py. Cleanup worker and SMTP dispatcher are included; Mailpit localhost:8025/SMTP1025.
- Direct: install backend requirements, back up, apply alembic upgrade head (009_upload_cleanup), configure matching S3/public endpoint/SMTP/signing settings, run API/dispatcher and python -m app.jobs.cleanup_uploads in another backend terminal. --once runs one maintenance tick.
- In Files, click Resume upload, reselect original content and upload missing chunks. Progress is provider-confirmed; expired windows require a new session after cleanup.
- Cleanup defaults: interval 60 seconds, settling delay 300 seconds after expiry/grace; settings are in .env.example/Compose. Current automatic cleanup requires an unversioned bucket.
- .local/backups/cloudvault-before-phase9.sql and earlier backups are ignored/preserved. Restore a pre-upgrade backup if rollback cannot represent retained cleanup state; provider object backup is separate. Private D-drive migration scripts/status/backups remain under D:\CloudVault-Dev\Migration. Never commit credentials/backups.
- Tests use unique disposable buckets/databases. Failed browser teardown leaves an ignored validated manifest; recover using the same TEST_S3 settings and python scripts/account_e2e_stack.py --cleanup-storage.

Next Exact Phase:
Phase 10 — File Search, only after explicit instruction. Remote CI needs separately authorized push/dispatch.

Last Commit:
670d2a0 — complete phases 4–8, storage, transfers and frontend redesign. Phase 9 remains uncommitted.

Read docs/phases/phase9.md for architecture, operations, security, limits and interview discussion.
