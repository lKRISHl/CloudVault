# CloudVault — Current State

Current Phase:
Phase 14A — Version Transfers, Resume/Cancel and Pruning (locally complete)

Status:
Implemented and locally verified 2026-10-15. Phase 14 and limitation planning committed as 14a4485; Phase 14A implementation and verification are included in this handoff commit. Live Docker app is migrated to 015_version_transfers at http://localhost:3000. No push/remote CI. Project remains D:\CloudVault-Dev\Project\CloudVault.

Completed Work:
- Earlier account/email/session, workspace/membership, hierarchy/files, private storage, transfers/resume/cleanup, search, external sharing, ACLs, trash and immutable version history remain implemented. Historical reports: docs/phases/phase2.md through phase14.md.
- Phase 14A closes L02/L03 and L04 core lifecycle: multipart replacements with bounded chunk hashing, durable candidate/VersionPart declarations before provider creation, missing-part receipts and composite proof, lost-create/complete acknowledgement reconciliation. Current content stays available until verified activation.
- Logical name/location/creator/ACL remain current; monotonically increasing generation rejects stale/ABA activation. Completion/restore revoke external links. Live file/ancestor and parent-write authority, uploader identity, tenant and original deadlines govern every candidate operation.
- Reload resume uses scoped secret-free session manifests or server pending-history discovery. Reselect/validate the original file; upload only missing parts. Pause preserves progress; Cancel commits irreversible server state before best-effort abort. Expired/late writes retain exact cleanup references. Storage PUTs omit account credentials.
- Creator/workspace managers can confirm non-current history deletion (DELETE) or configure keep-last 1–1000/all (PRUNE). Policy keeps newest N available completed snapshots plus current if older. Queued deletion is irreversible; disabling policy never revives it. New grants/restore stop immediately.
- Prune cleanup waits original upload expiry/grace, maximum prior GET window and settling delay, checks current protection again, confirms multipart/object absence and only then reduces retained/pending bytes. Trash respects later prune deadlines. Worker applies bounded policies and sweeps; refs/receipts/events persist for retry and late writes.
- Migration 015 adds nullable policy/cancel/prune markers and VersionPart receipts. Existing content/snapshots preserved; downgrade refuses multipart receipts, cancellation/prune history or active policy.

Important Files:
- docs/LIMITATIONS_BACKLOG.md, DEVELOPMENT_PLAN.md, docs/phases/phase14a.md and ADR-033 in DECISIONS.md.
- backend/app/models/file_version.py, models/file.py, migrations/versions/015_version_transfers.py.
- backend/app/services/version_multipart.py, versions.py, version_policy.py, version_cleanup.py, trash_cleanup.py and jobs/cleanup_uploads.py.
- backend/app/api/versions.py, schemas/versions.py; tests/api/test_version_transfers.py, test_version_transfers_integration.py and test_version_transfers_migration.py.
- frontend/src/features/versions/VersionsPage.tsx, versionTransfers.ts, services/api.ts, types/index.ts; __tests__/VersionTransfers.test.ts, Versions.test.tsx, e2e/versions.pw.ts.
- scripts/upload_smoke.py; README.md, ARCHITECTURE.md, SECURITY.md and PROJECT_CONTEXT.md updated.

Verification Passed:
- Full backend: 267 SQLite tests (325.00s) and 267 PostgreSQL tests (311.81s), using disposable databases and actual disposable MinIO buckets.
- Added explicit multipart private-authority revocation, concurrent cancel/complete and actual zero-byte replacement tests after the full runs. All 10 version-transfer API/provider cases pass again on SQLite (7.07s) and PostgreSQL (9.38s), including the expanded retention-on-activation test. Current 270 backend cases are covered by full-plus-targeted runs on each database; no claim that the expanded collection ran as one full suite.
- Fault/race checks cover durable lost initialization, lost completion ACK, superseded grants, cleanup retries/provider failures, restore/prune, cancellation, current protection and retained accounting. Actual bytes verify multipart missing-part resume, old-current download, restore, prune/cancel cleanup and empty basic replacement/download.
- Migration preservation/empty rollback/re-upgrade/schema alignment/guard checks pass on SQLite/PostgreSQL through the full suites and targeted integration runs. Earlier guarded migration tests restore head before model reads.
- 88 frontend tests pass; ESLint, TypeScript/Vite, Ruff and whitespace checks pass. Bounded hash/grace reconciliation/secret-free manifest/stale-session/original-file checks and UI delete/policy/cancel controls covered.
- All 20 Chromium/SMTP/storage journeys pass (1.2m), including multipart reload/wrong file/missing-part-only resume, cancellation, history pruning, retention persistence and mobile layout. Earlier workspace timeout did not recur in the final complete run. A later startup attempt found Docker paused; services were unpaused and its interrupted disposable bucket cleaned before rerun. No product workaround was required.
- Docker rebuild/start, HTTP/private-bucket/mc/adapter smoke and live SMTP/transfers/search/sharing/ACL/version/basic/multipart/resume/cancel/prune/policy/trash smoke pass. Fixed smoke-only checksum variable reuse before successful execution. Live 015_version_transfers has no migration drift. Upload/version/trash maintenance succeeds; eight long-running services running/healthy.
- Ignored pre-upgrade backup .local/backups/cloudvault-before-phase14a.sql (116913 bytes); earlier backups preserved. Owned cloudvault_phase14a_* test database dropped; browser-owned storage teardown completed. No destructive fixture used app data. Unique smoke accounts/content remain development data.
- Ignored evidence: .local/phase14a-sqlite.log, phase14a-postgres.log, phase14a-extra-sqlite.log, phase14a-extra-postgres.log, phase14a-frontend-final.log, phase14a-browser-final.log, phase14a-docker-build.log, phase14a-docker-smoke.log, phase14a-upload-smoke.log, phase14a-live-schema.log, phase14a-maintenance.log and phase14a-services.log. Expiry/cleanup tests inject time; no full retention-duration wait, remote CI or production/load/security certification.

Limitations requiring explicit work:
- L02/L03 closed locally; L04 core pruning/retention closed. L04 aggregate usage/quota integration remains 19; complete audit/metadata retention remains 20. Per-file sums/minimal change events do not close those acceptance checks.
- Next due: L05–L08 in Phase 14B — completed-file moves, explicit restore destination/name and conflicts, cancel-transfers-then-trash and legacy metadata remediation. L09 safe previews/scanning follows in 15/17. Read exact acceptance criteria in docs/LIMITATIONS_BACKLOG.md before implementation.
- L15 cross-tab/realtime progress/cache coordination remains 18. Tab manifests contain metadata only; original-file reselection, part boundaries, fixed deadline/grace and uploader-only control are deliberate D04 bounds. No browser file cache or automatic whole-file background recovery.
- L20/L21/L25/L33: retained refs/part receipts/history and bounded rotating policies require scheduled production lifecycle/fairness/real-clock verification, metadata compaction, alerts and representative worker/tenant-lock/history load at 16/20/26/28/32. Provider latency delays reclamation; policy may need multiple ticks. No benchmark.
- L22–L24: application UUID versions require an unversioned bucket. Enabled/Suspended cleanup fails closed; provider VersionId/delete-marker byte purge is unsupported. Maintained provider/IAM/encryption/CORS/lifecycle verification remains 16/26/27/31. SQL backups cannot restore reclaimed object bytes.
- L01 stays immediate/open: remote CI needs separately authorized push/dispatch and evidence tied to the tested commit. Local tests do not close it. Production SMTP, MFA, broader abuse/security/cross-browser/provider/load review, monitoring, paired DB/object restore and deployment gates retain their assigned checkpoints.
- Earlier search, sharing, ACL/group/resource-ownership and trash recovery gaps remain scheduled in the shared register, not implicitly closed here. Queued deletion is irreversible; issued capabilities/received bytes cannot be recalled. Cleanup retains internal metadata and cannot promise immediate/legal erasure. No new unassigned gap identified in this handoff.
- Multipart defaults remain 1 GiB/8 MiB/1024 parts/one hour; configured ceiling 5 GiB/5–32 MiB/two hours. New grants do not extend deadlines; completion grace five minutes. Basic cap default 100 MiB. Normal mutation/part budgets apply; aggregate abuse/quotas/scans remain later work.
- Docker WSL cap 4 GB: separate image builds from full DB/browser workloads. Project/Codex/Docker data use D; shared Windows/system temp may still use C.

Operation:
- Back up before alembic upgrade head (015_version_transfers); Docker startup migrates. Run docker compose up --build -d after source changes. Keep email dispatcher/upload-cleanup running; it includes policy/version/trash maintenance.
- Open Versions on a completed file to upload/resume/cancel, download/restore retained content, or manage retention with creator/manager authority. Queued deletion stops new grants but bytes remain counted until confirmed cleanup.
- Run python scripts/docker_smoke.py and python scripts/upload_smoke.py. Destructive fixtures must use owned disposable DBs/buckets; never point TEST_DATABASE_URL at app data. Real S3 tests need test-only bucket credentials.
- Restore a pre-upgrade DB backup for unrepresentable rollback; object backups are separate. Never commit dumps, credentials or E2E manifests. Recover failed browser teardown with matching TEST_S3 settings and scripts/account_e2e_stack.py --cleanup-storage.

Next Exact Phase:
Phase 14B — Core Library Movement and Recovery (L05–L08), before Phase 15. Do not skip its assigned limitation acceptance checks.

Every phase handoff must include "Limitations requiring explicit work" with inherited/new IDs, missing behavior/impact, concrete tasks, checkpoint and acceptance evidence. Synchronize the backlog/roadmap/continuation notes; see docs/phases/README.md. State when no new gaps are identified while reviewing inherited open items.

Standing user instruction: "continue" includes all fixes/acceptance checks assigned to the scheduled step, without individual requests. Implement/test/document due work automatically; do not advance with unresolved assigned checks. Keep genuine external dependencies explicitly open while completing independent work. No background execution, push/deploy/spending/destructive-data authorization is implied.

Commit Reference:
Phase 14A — version transfers, resume/cancel and pruning (this handoff; use git log -1 for its hash). Previous: 14a4485 — Complete Phase 14 file versioning and track limitation closure.
