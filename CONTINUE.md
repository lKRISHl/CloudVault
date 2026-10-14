# CloudVault — Current State

Current Phase:
Phase 10 — File Search

Status:
Implementation and local verification complete on 2026-10-15. Project: D:\CloudVault-Dev\Project\CloudVault. Docker app: http://localhost:3000/app/search. Live schema: 010_file_search with no Alembic drift. Phase 9 and regression notes are committed as 0551f25. Phase 10 remains uncommitted. No push/remote CI was performed.

Completed Work:
- Existing verified accounts, SMTP outbox/dispatcher, revocable workspace sessions, membership/ownership, folders, file metadata, private storage, basic/multipart upload, reload resume, cleanup and authorized attachment download remain implemented.
- GET /api/v1/files/search delegates to FileSearchService with strict query/result models. Current verified membership, unconditional tenant/non-cleaned predicates and folder ancestor validation protect searches.
- Filename terms use NFC, trimming and case-folded name keys with literal substring matching and escaped LIKE punctuation. Accents remain significant; there is no regex/fuzzy/content/AI search.
- Filters: workspace/root/direct-folder scope, pending/uploaded status, basic/multipart method, creator UUID, exact declared MIME and byte range. Pending status includes retained cancelled multipart metadata until cleanup hides it.
- Sort by name/size/created/updated with UUID tie-breaker in the same direction. Offset is bounded at 10000; API default page 25/max100; limit+1 avoids full counts.
- Results contain public metadata and direct folder name, joined by folder plus tenant identity without one query per result. Provider/object/cleanup identities remain hidden. Completed results use the existing checked native download control.
- Dedicated search page/navigation and folder shortcut provide submitted filters, 5/25/50-row pages, pagination reset, folder links, empty/error/manual retry and mobile layout. Cache keys include workspace/user/all submitted filters/page; cancellation/session-generation and context remounting reject stale results.
- Separate persistent search budgets permit 1200 identity/4800 IP per configured rate window (15 minutes default). They are independent of normal upload/account categories.
- 010_file_search adds partial tenant B-tree indexes for name/size/created/updated and status/name plus a PostgreSQL partial pg_trgm GIN index. SQLite omits only that PostgreSQL-specific index in DDL/schema comparison. Downgrade to 009 removes indexes only and retains data/shared extension.
- D-drive development storage and existing frontend style remain. Shared Windows/system temporary files may still use C:.

Important Files:
- backend/app/schemas/search.py, services/search.py and api/files.py.
- backend/app/models/file.py, migrations/versions/010_file_search.py and migrations/env.py.
- backend/tests/api/test_search.py, test_search_migration.py and conftest.py.
- frontend/src/features/search/FileSearchPage.tsx, services/api.ts and types/index.ts.
- frontend/src/components/AppShell.tsx, ui/Icon.tsx, features/folders/FoldersPage.tsx and index.css.
- frontend/src/__tests__/FileSearch.test.tsx and e2e/search.pw.ts.
- scripts/upload_smoke.py, docs/phases/phase10.md and ADR-027.

Verification Passed:
- 214 backend tests pass on SQLite and disposable PostgreSQL cloudvault_phase10_* with actual MinIO enabled. Migration fixtures create independent temporary databases; destructive tests never use app data.
- Coverage includes Unicode/case folding, literal percent/underscore, injection strings, scope/creator/type/size/status/method filters, hidden cleanup/private fields, stable sorting/real ties/pages, foreign tenant/folder, unverified/unauthenticated/revoked access, invalid queries and separate rate limits.
- Search migration preserves accounts/files, checks schema alignment and populated index-only downgrade/re-upgrade. PostgreSQL extension/GIN and SQLite fallback are exercised.
- A 5001-row synthetic PostgreSQL fixture confirms selective GIN and size-order index paths after statistics/pending-list maintenance. A freshly bulk-loaded GIN first used a sequential scan; flushing pending entries changed the selected plan. No forced planner settings or throughput benchmark.
- 60 frontend tests, ESLint, TypeScript/Vite build and Ruff pass. Search tests cover filters, page reset, cache/workspace isolation, scoped folder, read-only downloads, validation/errors/retry, encoding and stale responses.
- All 15 Chromium/SMTP/storage journeys pass. Search journey uses real uploaded/pending records, folder scope, literal percent search, filtering, sorted pages, native downloaded bytes, reset, mobile overflow and switched-workspace isolation. Prior account/workspace/folder/upload/resume/cancel/download journeys remain green.
- Docker rebuild/start, HTTP/private bucket/mc/adapter smoke, real SMTP/upload/resume/download/search/filter/sort/pagination, live Alembic schema check and maintenance tick pass. Head is 010_file_search; no drift. Unique smoke account/workspace/two completed files remain intentionally.
- Testing Library matcher type errors were corrected and final tests/lint/build passed. Browser-owned bucket cleanup completed; .local/e2e-storage.json is absent.
- Ignored evidence: .local/phase10-sqlite.log, phase10-postgres.log, phase10-browser.log, phase10-docker-build.log and phase10-docker-smoke.log. No remote CI/production load/provider/browser certification.

Remaining Limits:
- Search is literal filename/metadata only, accent-sensitive and direct-folder scoped. It has no recursive/fuzzy/tag/content/AI search or global count. Offset pages can shift under concurrent inserts/cleanup; they are not a consistent snapshot. Deep paging is bounded, not indefinitely scalable.
- Short/common terms and broad filters may scan extensively; GIN does not guarantee each query plan. Production needs real workload/query-plan/index maintenance, database timeout/abuse review and monitoring. Synthetic index evidence is not a benchmark.
- Search GET values may appear in operational access logs; review query logging/redaction/retention. Current verified members share workspace reads; Phase 12 must apply private ACLs before search pagination and folder/count context.
- Declared type/size remain untrusted for pending uploads. Uploaded files remain unscanned. Sharing 11, private ACLs 12, trash 13, versions 14, scans 17, quotas 19 and AI 21 onward remain upcoming.
- Resume remains part-boundary based, requiring the original reselected file within its original deadline. There is no persistent browser capability/file cache or live cross-tab progress. Expired transfers require a new session after cleanup.
- Cleanup waits for original expiry/grace/settling delay, retains hidden references/intents and retries late writes. Queue/provider latency can delay reclamation. It refuses versioned/suspended buckets; Phase 13/14 must coordinate retention/version-aware deletion. SQL backups cannot recover reclaimed object bytes.
- MinIO broad inventory/cache has limitations; current durable exact-key intents cover lost initialization acknowledgement. Historical unknown keys can require local stale-upload cleanup. The full configured 24-hour expiry/hourly scan timing is not measured; supplemental cursor restarts with worker process.
- Multipart defaults remain 1 GiB/8 MiB/1024 parts/one hour, configurable up to 5 GiB/5–32 MiB/two hours; basic cap is 100 MiB/full-buffer hashing. URLs never extend session deadlines; completion grace is five minutes. No aggregate quota/scan claim.
- Issued storage capabilities survive app revocation until expiry; new grants/completion recheck authority. Downloads remain reusable and not immediately revocable/version-pinned or delivery telemetry; out-of-band replacement after HEAD remains a provider/version limitation.
- Normal readiness is database-only; storage smoke is separate. Community MinIO is archived/local-only. Maintained provider, production S3/R2/IAM/CORS/encryption/lifecycle/backups/monitoring, SMTP, MFA, security/abuse review, remote CI and deployment hardening remain gates.
- SMTP ambiguous acknowledgement can duplicate mail; account links remain single-use. Key rotation/retained cleanup identity and content are not complete-erasure/legal-compliance claims.
- Docker WSL cap is 4 GB; keep full tests/browser workloads separate from image builds. Shared Windows/system temporary files may use C:.

Operation:
- Docker: docker compose up --build -d; python scripts/docker_smoke.py; python scripts/upload_smoke.py. Cleanup and SMTP dispatcher are included; Mailpit localhost:8025/SMTP1025.
- Search files from navigation or Search this folder from browsing. Submit filters/order/page size; opening folders and completed downloads use normal flows.
- Direct: install requirements, back up, apply alembic upgrade head (010_file_search), configure matching S3/public endpoint/SMTP/signing settings and run API/dispatcher/upload-cleanup. PostgreSQL needs pg_trgm installation permission or prior operator provisioning. SQLite uses the B-tree fallback.
- Ignored pre-upgrade backup: .local/backups/cloudvault-before-phase10.sql; earlier backups are preserved. Index rollback to 009 is data-preserving; older downgrades retain upload/tombstone/intent guards. Plan blocking index DDL separately on large production databases. Provider object backup is separate.
- Tests use owned disposable databases/buckets. Recover a failed browser bucket teardown with matching TEST_S3 settings and python scripts/account_e2e_stack.py --cleanup-storage. Never commit credentials/backups.

Next Exact Phase:
Phase 11 — Sharing, only after explicit instruction. Remote CI requires separately authorized push/dispatch.

Last Commit:
0551f25 — Phase 9 and regression notes. Phase 10 remains uncommitted.

Read docs/phases/phase10.md for architecture, operations, security, limits and interview discussion.
