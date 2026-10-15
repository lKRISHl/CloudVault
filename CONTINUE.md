# CloudVault — Current State

Current Phase:
Phase 11 — Sharing

Status:
Implementation and local verification complete on 2026-10-15. Docker app: http://localhost:3000/app/folders. Live schema: 011_sharing with no Alembic drift. Project: D:\CloudVault-Dev\Project\CloudVault. Phase 10 is committed as d4aa3e1; Phase 11 remains uncommitted. No push/remote CI was performed.

Completed Work:
- Prior verified accounts, SMTP dispatcher, revocable multi-workspace sessions, organizations/membership/ownership, folders, file metadata, private storage, basic/multipart upload, reload resume, cleanup, checked downloads and literal filename/filter/sort/pagination search remain implemented.
- File creators/current workspace managers manage external share links from folder browsing/search. Only completed non-cleaned tenant-scoped files are eligible; folder hierarchy/current verified membership are checked. Read-only members cannot manage another creator's links.
- ShareLink stores tenant/file/publisher, SHA-256 hash of a random 256-bit capability, optional Argon2 password hash, expiry, revocation, download permission, optional grant cap and committed grant count. Raw secrets/passwords are never persisted or returned from listing.
- Expiry 1–720 hours/default 24; optional password 8–128 characters; max grants 1–10000. Metadata-only links reveal filename/verified size/expiry/download availability after proof, without preview or bytes. No recipient account is required.
- Management API: POST/GET /api/v1/files/{file_id}/shares and DELETE /api/v1/files/{file_id}/shares/{link_id}. Listing pages of 25, offset <= 10000, has_more; create returns the raw fragment URL once. Idempotent revoke prevents new access/grants.
- Public POST /api/v1/shares/access and /shares/download-url receive token/password in request bodies. No caller tenant/key/bucket is accepted. They resolve capability scope and recheck active verified publisher authority. Unknown/expired/revoked/wrong-password/publisher-unavailable share responses are generic.
- Persistent public limits 100/IP and 100/capability per configured window(default 15 minutes), before password work; create/revoke use ordinary category limits(default 10 identity/100 IP). Malformed validation errors occur before service limits.
- Tenant write locks serialize grants/revocation/membership changes through provider work and grant commit; SQLite public handling takes its writer lock. Counts measure issued URLs, including lost acknowledgement, rather than completed downloads. Provider failures do not consume a grant.
- Public storage uses a late tenant-scoped factory after successful capability/password/restriction checks. Common DownloadService object HEAD size/checksum/ETag/type and bucket checks cover basic/multipart shares, with safe provider errors and native attachment GET.
- Download URLs are bounded by normal download duration(default 5 minutes) and remaining share deadline, recalculated after inspection. Provider clock/signing resolution remains a timing boundary. Issued URLs remain reusable until expiry and downloaded bytes cannot be recalled.
- Member removal, role updates, ownership transfer and account deletion revoke affected published links in their existing transactions. Reactivation cannot restore explicitly revoked links. Logout alone does not revoke independent share capabilities.
- Public page clears fragment/address history, omits account cookies/Authorization, does not refresh/sign out another account, cancels obsolete requests and adopts another share in the same tab while clearing password/results. Reload requires reopening the original full link. Management caches/remounting include workspace/user/file.
- Sharing errors/successes use no-store/no-referrer; frontend referrer policy is configured. Current filenames are visible in management; generated URL is shown only in component memory and cleared on revoke/context change.
- 011_sharing adds metadata only, preserves existing data and matches SQLAlchemy schema. Empty downgrade to 010 is supported; any retained link refuses downgrade and requires pre-upgrade backup rollback.

Important Files:
- backend/app/models/share.py, schemas/shares.py, services/shares.py and api/shares.py.
- backend/app/storage/provider.py, api/storage.py and services/downloads.py.
- backend/app/services/organizations.py and accounts.py; app/main.py sharing response headers.
- backend/migrations/versions/011_sharing.py, tests/api/test_shares.py and test_sharing_migration.py.
- frontend/src/features/sharing/SharingPages.tsx, services/api.ts, types/index.ts and app/App.tsx.
- frontend/src/features/folders/FileList.tsx and features/search/FileSearchPage.tsx.
- frontend/src/__tests__/Sharing.test.tsx, e2e/sharing.pw.ts, scripts/upload_smoke.py.
- docs/phases/phase11.md and ADR-028; prior implementation details remain in phase 2–10 reports.

Verification Passed:
- 225 backend tests on SQLite and disposable PostgreSQL cloudvault_phase11_* with real MinIO integration cases enabled. Independent migration databases are created/dropped; application data is never used by destructive fixtures.
- Sharing tests exercise optional passwords/no-password metadata, hashed secrets/minimal output, completed/pending eligibility, creator/member/tenant isolation, expiry/revocation, unknown/malformed input, rate limits, provider failures/no counter consumption, deadline expiry during inspection, single-grant concurrency, paged listing/file binding and publisher removal/reactivation/role/account deletion.
- Sharing migration tests exercise schema alignment, empty downgrade/re-upgrade and populated refusal while preserving file/account/link rows. Existing migrations/search/index-plan/storage/session/concurrency tests remain green.
- Final PostgreSQL sharing/migration recheck: 11 passed, including final list filename response. Full suites: SQLite 225 in 183.88s; PostgreSQL 225 in 195.16s. No synthetic results substituted for actual PostgreSQL.
- 66 frontend tests, ESLint, TypeScript/Vite build and Ruff pass. Sharing tests cover restrictions/create/revoke/one-time link, management denial, metadata-only access, wrong password, native grant navigation, credential omission, no account refresh, cancellation and same-tab link replacement.
- All 16 Chromium/SMTP/storage browser journeys pass (55.2s). Sharing uses real uploaded bytes, signed-out recipient, password denial/success, exact attachment content, one-grant cap, revocation, metadata-only link, same-tab replacement and mobile layout. Prior journeys remain green.
- Browser testing exposed and corrected a login-dependent public storage adapter and stale same-tab capability state. Browser-owned storage teardown completed.
- Docker rebuild/start, HTTP/private-bucket/mc/adapter smoke and real SMTP/basic/multipart upload/resume/download/search/sharing smoke pass. Anonymous protected multipart bytes, grant cap, revocation and metadata-only basic link are verified. Live Alembic head is 011_sharing with no drift. Maintenance tick succeeds with zero eligible records; all eight long-running services are healthy/running. Unique smoke account/workspace/two completed files and revoked link metadata remain as development data.
- Ignored evidence: .local/phase11-sqlite.log, phase11-postgres.log, phase11-browser.log phase11-docker-build.log and phase11-docker-smoke.log. No remote CI/production load/provider/browser certification.

Remaining Limits:
- Search is literal filename/metadata only, accent-sensitive and direct-folder scoped. It has no recursive/fuzzy/tag/content/AI search or global count. Offset pages can shift under concurrent inserts/cleanup; they are not a consistent snapshot. Deep paging is bounded, not indefinitely scalable.
- Short/common terms and broad filters may scan extensively; GIN does not guarantee each query plan. Production needs real workload/query-plan/index maintenance, database timeout/abuse review and monitoring. Synthetic index evidence is not a benchmark.
- Search GET values may appear in operational access logs; review query logging/redaction/retention. Current verified members share workspace reads; Phase 12 must apply private ACLs before search pagination and folder/count context.
- Declared type/size remain untrusted for pending uploads. Uploaded files remain unscanned. External sharing is implemented; private ACLs 12, trash 13, versions 14, scans 17, quotas 19 and AI 21 onward remain upcoming.
- Resume remains part-boundary based, requiring the original reselected file within its original deadline. There is no persistent browser capability/file cache or live cross-tab progress. Expired transfers require a new session after cleanup.
- Cleanup waits for original expiry/grace/settling delay, retains hidden references/intents and retries late writes. Queue/provider latency can delay reclamation. It refuses versioned/suspended buckets; Phase 13/14 must coordinate retention/version-aware deletion. SQL backups cannot recover reclaimed object bytes.
- MinIO broad inventory/cache has limitations; current durable exact-key intents cover lost initialization acknowledgement. Historical unknown keys can require local stale-upload cleanup. The full configured 24-hour expiry/hourly scan timing is not measured; supplemental cursor restarts with worker process.
- Multipart defaults remain 1 GiB/8 MiB/1024 parts/one hour, configurable up to 5 GiB/5–32 MiB/two hours; basic cap is 100 MiB/full-buffer hashing. URLs never extend session deadlines; completion grace is five minutes. No aggregate quota/scan claim.
- Issued storage capabilities survive app revocation until expiry; new grants/completion recheck authority. Downloads remain reusable and not immediately revocable/version-pinned or delivery telemetry; out-of-band replacement after HEAD remains a provider/version limitation.
- Normal readiness is database-only; storage smoke is separate. Community MinIO is archived/local-only. Maintained provider, production S3/R2/IAM/CORS/encryption/lifecycle/backups/monitoring, SMTP, MFA, security/abuse review, remote CI and deployment hardening remain gates.
- SMTP ambiguous acknowledgement can duplicate mail; account links remain single-use. Key rotation/retained cleanup identity and content are not complete-erasure/legal-compliance claims.
- Docker WSL cap is 4 GB; keep full tests/browser workloads separate from image builds. Shared Windows/system temporary files may use C:.

- Sharing is file-only; no folder subtree, private recipient ACL, editing, upload, preview or recipient identity verification. Links/passwords can be forwarded. Metadata-only reveals filename/size; files remain unscanned.
- Grant counters are not download telemetry. A signed URL can be reused; a lost response after commit consumes a grant. Link creation is not idempotent; revoke uncertain entries and recreate. Raw secrets cannot be recovered; link metadata remains retained indefinitely.
- Per-capability/IP budgets can limit legitimate groups. Password work and provider operations hold tenant serialization; production requires distributed/CPU abuse, proxy/IP trust, timeouts, representative workload and throughput review. Malformed requests precede service budgets. Production HTTPS/body-log redaction/retention review remains required.

Operation:
- Docker: docker compose up --build -d; python scripts/docker_smoke.py; python scripts/upload_smoke.py. Cleanup and SMTP dispatcher are included; Mailpit localhost:8025/SMTP1025.
- Share a completed writable file from /app/folders or /app/search. Save the generated link immediately; send any password separately. Recipients reopen the original full link after reload. FRONTEND_URL must match the intended recipient origin.
- Direct: install requirements, back up, apply alembic upgrade head (011_sharing), configure matching S3/public endpoint/SMTP/signing settings and run API/dispatcher/upload-cleanup. PostgreSQL needs pg_trgm permissions from Phase 10; SQLite uses B-tree fallback.
- Ignored pre-upgrade backup: .local/backups/cloudvault-before-phase11.sql; earlier backups preserved. Sharing rollback refuses any retained record; restore backup for unrepresentable state. Database backups do not restore provider bytes. Tests use owned disposable databases/buckets.
- Recover failed browser bucket teardown using matching TEST_S3 settings and python scripts/account_e2e_stack.py --cleanup-storage. Never commit credentials/backups. Keep image builds separate from full test/browser workloads under 4 GB WSL cap.

Next Exact Phase:
Phase 12 — Permissions/RBAC, only after explicit instruction. Centralize viewer/editor/resource authorization and apply read ACLs before search/list pagination and folder context. Recheck publish/ongoing share authority consistently. Remote CI requires separately authorized push/dispatch.

Last Commit:
d4aa3e1 — Complete Phase 10 file search and verification. Phase 11 remains uncommitted.

Read docs/phases/phase11.md for architecture, operation, security, limitations and interview discussion.
