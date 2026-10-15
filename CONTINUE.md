# CloudVault — Current State

Current Phase:
Phase 13 — Trash and Restore

Status:
Implementation and local verification complete on 2026-10-15. Docker app: http://localhost:3000/app/trash. Live schema: 013_trash with no Alembic drift. Project: D:\CloudVault-Dev\Project\CloudVault. Phase 12 is committed as cce1f62; Phase 13 remains uncommitted. No push/remote CI was performed.

Completed Work:
- Prior account/email/session, workspace/membership, folders/files, private storage, basic/multipart transfers, reload resume/cleanup, search, external sharing and resource-local viewer/editor/private ACLs remain implemented.
- TrashEntry records tenant/root/kind/actor, trash time, fixed 30-day retention, earliest cleanup time, irreversible purge request, restore/completion and fair-attempt markers. File/Folder trash_id groups removals; File retains exact object refs and purge/check timestamps. Existing data migrates live with trash_id NULL.
- Completed managed files and folder subtrees can move to trash. Current verified membership, effective ancestor read and creator/manager authority are required; trash/restore also require a writable original parent. Nonmanagers cannot remove mixed-creator subtrees. Pending uploads must finish or clean first.
- Folder trash marks currently active descendants only, preserving older independent batches. Existing external links revoke. Live ACL predicates now exclude trash before browsing/search pagination/context, direct IDs, upload/download grants and external publishing. Private ancestor gates remain effective for trash pages.
- Live-name partial unique indexes exclude trash for files/folders. Names can be reused immediately; restore atomically returns only its batch to the original location and rolls back on active conflicts. Original ACLs, grants, provenance, object identities/checksums remain. Older independent trash and revoked links do not reactivate.
- GET /api/v1/trash unions file/folder roots after current read/management predicates, then orders/pages of 25(offset <= 10000) with has_more. POST /{files|folders}/{id}/trash creates a batch; POST /trash/{id}/restore restores before retention/purge begins. Foreign/inaccessible entries return not found.
- POST /trash/{id}/purge requires literal DELETE confirmation and returns 202 queued, immediately disabling restore. Permanent folder deletion includes nested independent trash. At retention expiry the worker queues the same irreversible state automatically.
- Tenant serialization orders trash/restore/purge/ACL/move/upload writes. A worker commits irreversible intent before storage effects, then reacquires the lock; restore and purge race to one valid result. Restored batches are never reclaimed by stale queue snapshots.
- TrashCleanupService waits for batch/nested deadlines and original upload expiry plus grace/settle, aborts exact-key multipart remnants, confirms no remaining uploads, deletes bytes and checks HEAD absence. Current configured unversioned bucket is required. Drift, Enabled/Suspended versioning and provider errors fail closed. Exact references remain and rotate fairly after errors/success for retry/late writes.
- Existing Compose upload-cleanup invokes trash maintenance: up to 10 batches and 10 file references each per tick. Standalone python -m app.jobs.cleanup_trash --once is available. Purged entries disappear from Trash; internal metadata/history/names/grants/revoked links/cleanup references remain retained. No complete-erasure or exact-time claim.
- Trash navigation/page provides deadline/state, original-location restore, errors/refresh/paging/mobile layout and an irreversible confirmation panel. Managed completed files/folders expose Move to trash in browsing/search. Scoped caches/remounts use workspace/user; resource/trash successes/errors use no-store/no-referrer.
- Trash mutations use persistent 100 identity/500 IP per configured window(default 15 minutes). Earlier transfer/search/share limits remain. Purge requests cannot be cancelled and already issued GET URLs/received bytes cannot be recalled.
- 013_trash adds retained batches/references and live-name indexes without discarding existing content. Any history/purge reference refuses downgrade, including restored batches. Earlier guarded migration tests restore head before current-ORM reads.

Important Files:
- backend/app/models/trash.py, models/file.py, models/folder.py and migrations/versions/013_trash.py.
- backend/app/services/trash.py, trash_cleanup.py, permissions.py, files.py and folders.py.
- backend/app/api/trash.py, router.py, app/main.py, jobs/cleanup_trash.py and cleanup_uploads.py.
- backend/tests/api/test_trash.py, test_trash_cleanup.py, test_trash_integration.py and test_trash_migration.py.
- frontend/src/features/trash/TrashPage.tsx, TrashButton.tsx, components/AppShell.tsx, ui/Icon.tsx and app/App.tsx.
- frontend/src/features/folders/FileList.tsx, FoldersPage.tsx, features/search/FileSearchPage.tsx and services/api.ts.
- frontend/src/__tests__/Trash.test.tsx, e2e/trash.pw.ts, e2e/permissions.pw.ts and scripts/upload_smoke.py.
- docs/phases/phase13.md and ADR-030.

Verification Passed:
- 250 backend tests on SQLite (291.71s) and disposable PostgreSQL cloudvault_phase13_* (291.26s), with actual MinIO integration enabled. Independent test databases/buckets are owned/disposable; destructive fixtures never use application data.
- Trash/live-path exclusion, private ancestor filtering before pagination, viewer/editor management denial, mixed-creator subtree protection, name reuse, atomic restore conflicts, independent batches, parent-first restore, retention expiry, DELETE confirmation, nested purge and concurrent restore-versus-purge pass.
- Cleanup tests verify deadline waiting, provider failures without premature completion, retained references/retry, late writes, Enabled/Suspended refusal and restored-batch protection. Actual S3 upload/restore/download bytes and actual object deletion/absence/recreated-object recheck pass on disposable buckets. Deadlines use injected test time; the full real-time retention period is not waited out.
- Final nested-deadline cleanup/actual-storage rechecks pass on both SQLite and PostgreSQL (5 cases each).
- New migration checks preserve existing accounts/names/ACL defaults, exercise empty downgrade/re-upgrade and refuse retained trash/history rollback, including after restore. Earlier schema/data/concurrency/search/index/provider regressions remain green.
- 77 frontend tests, ESLint, TypeScript/Vite build, Ruff and whitespace checks pass. Trash tests cover scoped cache identity, restore/error/paging, permanent confirmation/queued state, expired/queued restore denial and move errors.
- All 18 Chromium/SMTP/storage journeys pass (1.4 minutes). Trash journey demonstrates real upload, live hiding, restored native download exact bytes, irreversible DELETE panel, queued restore denial, folder-name reuse/conflict and mobile layout. Prior journeys remain green.
- Initial tests caught a folder name precheck counting trash; corrected it. A prior permission browser journey now waits for target-folder breadcrumbs before selecting a file; final browser run passed separately from database workloads. Browser-owned storage teardown completed; no E2E manifest remains.
- Docker rebuild/start, HTTP/private bucket/mc/adapter and real SMTP/basic/multipart transfer/search/sharing/ACL/file-folder trash/restore/purge-queue checks pass. Restored native/HTTP bytes remain exact; purge queue disables restore without bypassing deadlines. Live head is 013_trash with no drift. Composite upload/trash maintenance and standalone trash tick succeed: zero eligible upload records, one queued smoke trash batch checked and retained pending its deadline. All eight long-running services are healthy/running. Unique smoke accounts/content and queued purge demo remain.
- Ignored logs: .local/phase13-sqlite.log, phase13-postgres.log, phase13-browser.log, phase13-trash-integration.log phase13-docker-build.log and phase13-docker-smoke.log. No remote CI/production provider/load/browser certification.

Remaining Limits:
- Search is literal filename/metadata only, accent-sensitive and direct-folder scoped. It has no recursive/fuzzy/tag/content/AI search or global count. Offset pages can shift under concurrent inserts/cleanup; they are not a consistent snapshot. Deep paging is bounded, not indefinitely scalable.
- Short/common terms and broad filters may scan extensively; GIN does not guarantee each query plan. Production needs real workload/query-plan/index maintenance, database timeout/abuse review and monitoring. Synthetic index evidence is not a benchmark.
- Search GET values may appear in operational access logs; review query logging/redaction/retention. Current resource ACLs are applied before search/list pagination and folder context; no production ACL workload benchmark is claimed.
- Declared type/size remain untrusted for pending uploads. Uploaded files remain unscanned. External sharing, resource ACLs and trash are implemented; versions 14, scans 17, quotas 19 and AI 21 onward remain upcoming.
- Resume remains part-boundary based, requiring the original reselected file within its original deadline. There is no persistent browser capability/file cache or live cross-tab progress. Expired transfers require a new session after cleanup.
- Cleanup waits for original expiry/grace/settling delay, retains hidden references/intents and retries late writes. Queue/provider latency can delay reclamation. It refuses versioned/suspended buckets; Phase 13/14 must coordinate retention/version-aware deletion. SQL backups cannot recover reclaimed object bytes.
- MinIO broad inventory/cache has limitations; current durable exact-key intents cover lost initialization acknowledgement. Historical unknown keys can require local stale-upload cleanup. The full configured 24-hour expiry/hourly scan timing is not measured; supplemental cursor restarts with worker process.
- Multipart defaults remain 1 GiB/8 MiB/1024 parts/one hour, configurable up to 5 GiB/5–32 MiB/two hours; basic cap is 100 MiB/full-buffer hashing. URLs never extend session deadlines; completion grace is five minutes. No aggregate quota/scan claim.
- Issued storage capabilities survive app revocation until expiry; new grants/completion recheck authority. Downloads remain reusable and not immediately revocable/version-pinned or delivery telemetry; out-of-band replacement after HEAD remains a provider/version limitation.
- Normal readiness is database-only; storage smoke is separate. Community MinIO is archived/local-only. Maintained provider, production S3/R2/IAM/CORS/encryption/lifecycle/backups/monitoring, SMTP, MFA, security/abuse review, remote CI and deployment hardening remain gates.
- SMTP ambiguous acknowledgement can duplicate mail; account links remain single-use. Key rotation/retained cleanup identity and content are not complete-erasure/legal-compliance claims.
- Docker WSL cap is 4 GB; keep full tests/browser workloads separate from image builds. Shared Windows/system temporary files may use C:.

- External links remain file-only with no folder subtree, external recipient identity verification, editing/upload or preview. Signed-in workspace viewer/editor ACLs are now separate resource controls. Links/passwords can be forwarded. Metadata-only reveals filename/size; files remain unscanned.
- Grant counters are not download telemetry. A signed URL can be reused; a lost response after commit consumes a grant. Link creation is not idempotent; revoke uncertain entries and recreate. Raw secrets cannot be recovered; link metadata remains retained indefinitely.
- Per-capability/IP budgets can limit legitimate groups. Password work and provider operations hold tenant serialization; production requires distributed/CPU abuse, proxy/IP trust, timeouts, representative workload and throughput review. Malformed requests precede service budgets. Production HTTPS/body-log redaction/retention review remains required.

- Private ancestor access must be granted separately. Resource editor roles do not inherit, and removing an explicit grant does not deny workspace visibility or implicit creator/manager rights. Trusted owners/admins can access private resources. Groups/custom roles, external named-recipient verification and per-resource ownership transfer are not implemented.
- Recursive visibility and repeated bounded ancestor checks have workload-dependent costs; prior synthetic trigram/order plans do not establish ACL-query throughput. Production needs representative hierarchies/grants, statement timeouts, index/query monitoring and tenant-lock/abuse review.
- Previously authorized metadata may remain in browser caches until refresh; no live cache erasure/ACL event synchronization is claimed. Downloaded bytes and already-issued provider capabilities cannot be recalled. Private sibling names can cause generic namespace conflicts during attempted creation/rename.
- Resource grant metadata has no dedicated audit/history/retention worker yet. Trash now enforces ACLs; versions, previews, realtime and AI must preserve those boundaries.

- Trash retains completed content for 30 days. Pending transfers block containing-folder trash until completed/cleaned. Restore only supports the active original parent and conflict-free original names; it cannot relocate/rename conflicts automatically. Nonmanagers need ownership of all remaining subtree resources; mixed-creator content requires a manager.
- Permanent folder deletion queues older independent nested trash too. Queueing is irreversible. Reclamation waits at least for recorded deadlines and original upload expiry/grace/settle, and can take longer under provider failure/load. Metadata/history/cleanup refs remain internal indefinitely; this is not immediate erasure or compliance certification.
- Trash cleanup refuses Enabled/Suspended bucket versioning. Phase 14 must coordinate all retained application/provider versions with trash purge and quotas before enabling versioned storage. SQL backups cannot restore purged bytes. Tombstone growth, tenant locks and query/cleanup workload require production review/monitoring.

Operation:
- Docker: docker compose up --build -d; python scripts/docker_smoke.py; python scripts/upload_smoke.py. Existing cleanup worker includes trash; SMTP dispatcher/Mailpit remain included(localhost:8025/SMTP1025).
- Use Move to trash from completed managed file/folder rows; open /app/trash for restore/deletion. Retention 30 days; restore the parent first and resolve active name conflicts. Permanent deletion requires typing DELETE and disables restore immediately.
- Direct: install requirements, back up, alembic upgrade head (013_trash), configure matching storage/SMTP/signing settings and run API/dispatcher/cleanup_uploads. Standalone cleanup_trash --once is optional for operator ticks. Phase 10 pg_trgm requirements remain.
- Ignored pre-upgrade backup: .local/backups/cloudvault-before-phase13.sql; earlier backups preserved. Any retained trash history prevents downgrade, even if restored; restore backup for an unrepresentable rollback. Provider object backups are separate.
- Tests use disposable DBs/buckets. Recover failed browser bucket teardown with matching TEST_S3 settings and python scripts/account_e2e_stack.py --cleanup-storage. Never commit credentials/backups. Separate Docker builds from full test/browser workloads under 4 GB WSL cap.

Next Exact Phase:
Phase 14 — File Versioning, only after explicit instruction. Include all retained versions in reference/retention/purge/quota handling and keep ACLs effective. Do not enable provider versioning with existing unversioned cleanup. Remote CI requires separately authorized push/dispatch.

Last Commit:
cce1f62 — Complete Phase 12 resource permissions and verification. Phase 13 remains uncommitted.

Read docs/phases/phase13.md for exact semantics, architecture, operations, limits and interview discussion.
