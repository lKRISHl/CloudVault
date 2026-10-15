# CloudVault — Current State

Current Phase:
Phase 12 — Permissions / RBAC

Status:
Implementation and local verification complete on 2026-10-15. Docker app: http://localhost:3000/app/folders. Live schema: 012_permissions with no Alembic drift. Project: D:\CloudVault-Dev\Project\CloudVault. Phase 11 is committed as fa6a27e; Phase 12 remains uncommitted. No push/remote CI was performed.

Completed Work:
- Prior verified accounts/email/session lifecycle, workspaces/membership/ownership, folders, metadata, private storage, basic/multipart uploads, reload resume/cleanup, verified downloads, literal filename search and external file sharing remain implemented.
- File/Folder visibility is workspace or private, defaulting existing/new data to workspace. ResourceGrant binds one file/folder to a tenant membership and viewer/editor role, with role/resource checks and partial unique indexes.
- PermissionService centralizes local visibility, mandatory ancestor read gates, write/management decisions, scoped mutation and link invalidation. Current active verified membership is required. Workspace owners/admins are trusted managers; resource creators retain management subject to readable ancestors.
- Viewer means read/download. Editor adds completed-file rename, folder rename and creation within an editable folder. Grants are resource-local with no inherited editing. Editors cannot manage ACLs, move folders or publish external links. A direct file grant never bypasses a private ancestor. Separately private descendants require their own authorization.
- Recursive SQL visibility starts at readable root folders and traverses readable children to depth 64. File/folder/search queries filter before sorting/offset/limit and folder context; inaccessible rows do not consume pages or affect has_more. Direct IDs/breadcrumbs are protected. Editor flags load in a bulk grant query per page.
- GET /api/v1/{files|folders}/{id}/permissions lists current visibility and active grants in pages of 25 with offset <= 10000. PATCH changes visibility; PUT /permissions/{user_id} sets viewer/editor or removes an explicit grant with role:null. Target must be a current verified active member. Tenant IDs/owner/admin grants/unknown fields are not accepted.
- Permission writes serialize under the tenant lock (SQLite writer lock), recheck management and revoke external links for the affected file/folder subtree in the same transaction. Grant updates are unique under concurrency. Visibility no-ops preserve links; grant updates/removals conservatively revoke affected links.
- Member removal deletes that member's workspace grants; account deletion cascades grants through memberships. Rejoining cannot resurrect removed grants. Existing Phase 11 publisher link revocation on lifecycle changes remains.
- Upload retry/completion/multipart controls preserve creator-only upload-session authority and check current effective file access plus writable parents. Revoking parent editor/read access blocks new grants/completion; previously issued storage URLs retain their lifetime.
- Checked authenticated downloads recheck effective ACLs and membership during provider inspection/signing. External publishing requires creator/manager control. Public shares derive the publisher's tenant context from the capability and recheck effective file access without changing any signed-in user's workspace identity.
- PATCH /api/v1/files/{id} permits authorized completed-file rename with normalized names, uniqueness checks and unchanged storage identities/bytes/checksums. Pending uploads cannot be renamed. Editors can rename without gaining publication/ACL authority.
- Folder moves remain creator/manager-only, require a writable destination, validate hierarchy and revoke subtree share links. Moving changes ancestor restrictions; the UI states the effect before action. Existing folders/files and creator provenance remain intact.
- Permission controls from browsing/search provide visibility actions, paged member candidates/grants, viewer/editor selection/removal, error/retry/loading and mobile layout. UI separates can_write from can_manage; management caches/remounts include workspace/user/resource. Completed files expose editor rename.
- Resource API success/error responses use no-store/no-referrer. Permission mutation budget 100 identity/500 IP per configured window(default 15 minutes); rename uses ordinary category limits. Prior external-link/transfer limits remain unchanged.
- 012_permissions adds default-preserving visibility and checked membership-bound grants. Downgrade refuses private policy or any grant rather than widening access/discarding ACLs. Historical migration tests now seed historical rows directly instead of invoking current-schema services and restore head after guarded chain downgrades.

Important Files:
- backend/app/models/permission.py, models/file.py, models/folder.py, schemas/permissions.py and migrations/versions/012_permissions.py.
- backend/app/services/permissions.py, folders.py, files.py, search.py, downloads.py, uploads.py, multipart.py, shares.py and organizations.py.
- backend/app/api/permissions.py, files.py, router.py and app/main.py.
- backend/tests/api/test_permissions.py, test_permissions_migration.py and migration_seed.py; earlier migration fixtures updated for historical schemas.
- frontend/src/features/permissions/PermissionsPage.tsx, features/folders/RenameFile.tsx, FoldersPage.tsx, FileList.tsx and features/search/FileSearchPage.tsx.
- frontend/src/services/api.ts, types/index.ts, app/App.tsx, __tests__/Permissions.test.tsx and e2e/permissions.pw.ts.
- scripts/upload_smoke.py, docs/phases/phase12.md and ADR-029.

Verification Passed:
- 235 backend tests on SQLite (240.64s) and disposable PostgreSQL cloudvault_phase12_* (241.51s), with actual MinIO integration cases enabled. Test databases/buckets are owned and disposable; application data is never used by destructive fixtures.
- Private-file hiding, ancestor boundaries, visible pagination/has_more, viewer/editor/management distinctions, foreign tenant/member rejection, forbidden role escalation, grant removal/lifecycle, concurrent grant uniqueness, subtree/file link revocation and download ACL loss during provider work pass.
- Pending upload creators lose retry/completion authority after parent ACL revocation. Viewer/editor read/write results remain distinct; completed-file rename preserves object references.
- New migration checks preserve existing names/accounts/sizes, default visibility and empty downgrade/re-upgrade; private visibility and grant rollback refuse. Prior account/folder/file/upload/multipart/search/sharing migration tests pass after removing current-ORM assumptions from historical fixtures.
- 72 frontend tests, ESLint, TypeScript/Vite build, Ruff and whitespace checks pass. Permission tests cover private visibility, scoped cache keys, viewer/editor grants, paginated member selection, revoke semantics, denial/retry and file rename conflict/retry.
- All 17 Chromium/SMTP/storage journeys pass (1.2 minutes). A real two-user permission journey checks private files hidden from search, viewer native download exact bytes, no editor/management controls for viewers, editor rename, private-ancestor boundary, explicit ancestor access, revocation and mobile layout. Earlier journeys remain green.
- The initial full run exposed historical fixture schema assumptions; historical seed helpers/restore-head steps fixed them, and final suites pass. A React rename test was corrected to wait for its form to render; final frontend tests pass. Browser-owned storage teardown completed; no E2E manifest remains.
- Docker rebuild/start, HTTP/private bucket/mc/adapter smoke and real SMTP/basic/multipart transfer/resume/search/sharing/ACL smoke pass. A second verified member demonstrates private hiding, actual viewer download bytes, editor rename, management denial and access removal. Live Alembic head is 012_permissions with no drift. Maintenance tick succeeds with zero eligible records; all eight long-running services are healthy/running. Unique smoke accounts/workspace/two completed files and revoked link metadata remain as development data.
- Ignored evidence: .local/phase12-sqlite.log, phase12-postgres.log, phase12-browser.log, phase12-migrations.log phase12-docker-build.log and phase12-docker-smoke.log. No remote CI/production provider/load/browser certification.

Remaining Limits:
- Search is literal filename/metadata only, accent-sensitive and direct-folder scoped. It has no recursive/fuzzy/tag/content/AI search or global count. Offset pages can shift under concurrent inserts/cleanup; they are not a consistent snapshot. Deep paging is bounded, not indefinitely scalable.
- Short/common terms and broad filters may scan extensively; GIN does not guarantee each query plan. Production needs real workload/query-plan/index maintenance, database timeout/abuse review and monitoring. Synthetic index evidence is not a benchmark.
- Search GET values may appear in operational access logs; review query logging/redaction/retention. Current resource ACLs are applied before search/list pagination and folder context; no production ACL workload benchmark is claimed.
- Declared type/size remain untrusted for pending uploads. Uploaded files remain unscanned. External sharing and resource ACLs are implemented; trash 13, versions 14, scans 17, quotas 19 and AI 21 onward remain upcoming.
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
- Resource grant metadata has no dedicated audit/history/retention worker yet. ACLs must remain enforced in upcoming trash, versions, previews, realtime and AI features.

Operation:
- Docker: docker compose up --build -d; python scripts/docker_smoke.py; python scripts/upload_smoke.py. Cleanup and SMTP dispatcher are included; Mailpit localhost:8025/SMTP1025.
- Use Permissions from /app/folders or /app/search. Existing content is workspace-visible; choose Private and grant the required resource/ancestor access. Save external links immediately; permission changes revoke affected published links.
- Direct: install requirements, back up, apply alembic upgrade head (012_permissions), configure matching storage/SMTP/signing settings and run API/dispatcher/upload-cleanup. Phase 10 pg_trgm/operator requirements remain.
- Ignored pre-upgrade backup: .local/backups/cloudvault-before-phase12.sql; earlier backups preserved. Downgrade refuses private visibility/grants; restore pre-upgrade backup for unrepresentable rollback. SQL backups do not restore provider bytes.
- Tests use disposable databases/buckets. Recover failed browser bucket teardown with matching TEST_S3 settings and python scripts/account_e2e_stack.py --cleanup-storage. Never commit credentials/backups. Separate Docker builds from full test/browser workloads under 4 GB WSL cap.

Next Exact Phase:
Phase 13 — Trash + Restore, only after explicit instruction. Preserve effective ACLs on trash/list/restore/permanent deletion and coordinate object retention with upload cleanup/version handling. Remote CI requires separately authorized push/dispatch.

Last Commit:
fa6a27e — Complete Phase 11 external file sharing and verification. Phase 12 remains uncommitted.

Read docs/phases/phase12.md for exact policy, architecture, operations, limits and interview discussion.
