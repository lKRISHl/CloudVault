# CloudVault — Current State

Current Phase:
Phase 14B — Core Library Movement and Recovery (locally complete)

Status:
Implemented and locally verified 2026-10-15. Phase 14A committed as 98a4a70; Phase 14B implementation and verification are included in this handoff commit. Development DB/image verified at 016_library_recovery. Docker/WSL intentionally stopped after verification to save RAM; localhost:3000 is offline until restarted. No push/remote CI. Project remains D:\CloudVault-Dev\Project\CloudVault.

Completed Work:
- Earlier account/email/session, workspaces/membership, hierarchy/files, storage, transfers/resume/cleanup, search, sharing, ACLs, trash, immutable versions and version multipart/resume/cancel/pruning remain implemented. Historical reports: docs/phases/phase2.md through phase14a.md.
- L05: completed-file moves require creator/manager authority, writable source/destination parents and matching expected source_folder_id under tenant serialization. Location changes revoke links; immutable object/version identity, current generation, bytes and resource-local grants stay unchanged. Foreign/private/read-only/stale/name-conflict paths fail safely.
- L06: restore to the original parent or an explicitly selected active writable destination/name. Original readable trash authority remains mandatory. Root move/name and clearing only that batch commit atomically; older independent trash remains trash. Full subtree height, cycles, mixed creators, conflicts and irreversible purge protect recovery.
- L07: normal trash still blocks pending original uploads. A separate CANCEL UPLOADS confirmation cancels up to 100 tracked live pending File records with folder trash atomically; mixed creators require managers. upload_cancelled_at/aborted state denies later grants/completion even after restore. Existing capabilities retain their deadline; refs remain for safe original/trash cleanup. Pending refs block completed purge until absence is confirmed; retries catch late bytes.
- L08: no-session legacy metadata offers DISCARD with creator/manager/writable-parent authority. Only pending rows without object/version/intent refs can be tombstoned; the row stays retained and its live name becomes reusable. Contradictory references fail closed, tracked as L37.
- Migration 016 adds nullable pending-only File.upload_cancelled_at and permits no-reference legacy cleanup tombstones. Existing rows/snapshots preserved. Any cancellation/discard marker guards downgrade, even after cleanup; use a pre-upgrade backup for unrepresentable rollback.
- Browser destination picker uses 25-record pages; moves carry expected source, restore supports new destination/name, cancellation/discard require explicit confirmations and cancelled records hide retry/resume. Scoped caches refresh affected views. Browser helper stability fixes preserve all assertions: navigation/page activation, bounded email wait, large fixtures from D and outage teardown before successful cancellation.

Important Files:
- docs/phases/phase14b.md, docs/LIMITATIONS_BACKLOG.md, DEVELOPMENT_PLAN.md and ADR-034 in DECISIONS.md.
- backend/app/services/files.py, trash.py, trash_cleanup.py, uploads.py, multipart.py; models/file.py, schemas/files.py, schemas/trash.py, api/files.py and api/trash.py.
- backend/migrations/versions/016_library_recovery.py; tests/api/test_library_recovery.py, test_library_recovery_integration.py and test_library_recovery_migration.py.
- frontend/src/features/folders/DestinationPicker.tsx, FileRecoveryActions.tsx, FileList.tsx; features/trash/TrashPage.tsx, TrashButton.tsx; services/api.ts and types/index.ts.
- frontend/src/__tests__/LibraryRecovery.test.tsx, e2e/library-recovery.pw.ts, multipart.pw.ts, versions.pw.ts and workspaces.pw.ts; scripts/upload_smoke.py.

Verification Passed:
- Full backend: 286 SQLite tests (429.13s) and 286 PostgreSQL tests (437.45s), including disposable real MinIO and migration cases. A final legacy-snapshot fail-closed guard was then added; all 15 recovery API/provider cases pass again on SQLite (13.55s) and PostgreSQL (16.50s). The full collection was not rerun after that guard.
- Actual provider tests preserve moved/recovered native bytes, filename/version/object identity; cover basic and multipart pending cancellation, an issued basic PUT arriving after cancellation, safe deadline waiting and confirmed exact-key abort/delete absence without affecting completed content.
- API checks cover creator/manager/editor/foreign/private/read-only boundaries, concurrent moves, stale source, conflicts/rollback, original-parent absence, older independent trash, depth 64, mixed creators, cancel/complete and restore/purge races, 100-pending bound, legacy intent/snapshot refusal, tombstones and name reuse.
- Migration tests seed old-schema legacy rows, preserve data through upgrade/empty downgrade/re-upgrade, verify schema alignment and refuse cancellation/discard history loss. Earlier version/history migration checks remain green.
- 93 frontend tests pass. Final ESLint, TypeScript/Vite, Ruff and whitespace pass. Controls cover expected-source conflict, DISCARD/CANCEL confirmations, destination paging/read-only selection and renamed explicit restore.
- All 21 Chromium/SMTP/storage journeys pass in the final full run (1.2m). New journey verifies moved/recovered bytes, cancellation and restored cancelled-state controls/mobile. Earlier attempts had intermittent navigation/input/transport failures; helpers now activate identity pages, wait for navigation/email, use large version files on D and end simulated storage outages before cancellation. Assertions remain intact.
- Docker rebuild/start, private bucket/mc/adapter/HTTP and SMTP/transfers/search/sharing/ACL/version/movement/renamed-recovery/cancel-folder/trash smoke pass. Verified 016_library_recovery has no schema drift; maintenance checked four trash batches. Eight services were running/healthy before intentional shutdown to save RAM.
- Ignored pre-upgrade backup .local/backups/cloudvault-before-phase14b.sql (140348 bytes); earlier backups preserved. Owned cloudvault_phase14b_* PostgreSQL test database dropped, browser bucket removed and no .local/e2e-storage.json remains. No destructive fixture used application data. Unique smoke data remains in development storage.
- Evidence: .local/phase14b-sqlite.log, phase14b-postgres.log, phase14b-final-recovery-sqlite.log, phase14b-final-recovery-postgres.log, phase14b-migration.log, phase14b-frontend.log, phase14b-browser-final.log, phase14b-eslint-final.log, phase14b-build-final.log, phase14b-ruff-final.log, phase14b-docker-build.log, phase14b-docker-smoke.log, phase14b-upload-smoke.log, phase14b-live-schema.log, phase14b-maintenance.log, phase14b-services.log and phase14b-shutdown.log. Expiry tests inject time; no real-duration retention, remote CI or production/load/security certification.

Limitations requiring explicit work:
- L05–L08 close locally for the documented tracked/no-reference scope. L37 is new: contradictory legacy intent/version refs require safe operator diagnostics/adoption/cleanup before retirement. Unmaterialized initialization intents stay in existing exact-key maintenance, outside tracked folder File cancellation. Phase 16 adds folder-scoped discovery/cancellation and stale-init retry invalidation after trash/recovery; Phase 26 verifies chosen-provider failures/lost ACK/late writes and no dropped refs. Active trashed parents already reject allocation. This follow-up is automatically included at those checkpoints.
- Next due L09: Phase 15 safe bounded preview/detected-type handling, then Phase 17 quarantine/scanning. Existing bytes/declared MIME/attachment responses do not establish safe content.
- L04/L19 aggregate quota/current/history/trash/pending reconciliation remains 19; L21/L36 and complete movement/recovery/cancellation audit/metadata retention remain 20. Per-file accounting/minimal events/tombstones do not close those checks.
- L15 realtime/cross-tab/cache coordination remains 18; L17/L18 navigation/rich search/pagination remain 22A. Destination pages shift under concurrent changes. Source location checks are optimistic; users refresh conflicts. Resource grants remain attached when containing-folder visibility changes.
- L20/L22–L25/L33 provider lifecycle/fairness/real-clock verification, maintained production storage/IAM/encryption/CORS/lifecycle, job/backlog health, paired backups and representative worker/tenant-lock/deep-tree/100-pending workloads remain 16/26/27/28/31/32. No throughput benchmark. Application versions require unversioned buckets; Enabled/Suspended maintenance fails closed.
- L01 remote CI stays immediate/open pending separately authorized push/dispatch with evidence tied to the tested commit. Production SMTP, MFA, abuse/security/cross-browser/provider/load, deployment/monitoring and paired DB/object restore gates remain assigned/open.
- D constraints remain: issued URLs/received bytes cannot be recalled; cancellation/queued purge cannot be undone; byte reclamation waits safe provider proof; cleanup refs/organization data remain retained. Ordinary original/version multipart limits/deadlines/grace/part boundaries and uploader controls remain. Full metadata erasure/legal compliance is not claimed.
- L37 is the new assigned follow-up; no additional unassigned gap identified. Earlier sharing/ownership/search/product-decision gaps retain their checkpoints in the register. Every phase must review and carry them explicitly.

Operation:
- Docker/WSL are stopped to save RAM. Start Docker Desktop, then docker compose up -d from this folder when using the app/testing. Use docker compose up --build -d after source changes. Open http://localhost:3000/app/folders. Stop the stack/quit Docker when finished; volumes/data are preserved.
- Back up before direct alembic upgrade head (016_library_recovery); Docker startup migrates. Cancellation/discard history guards downgrade. Restore a pre-upgrade backup for unrepresentable rollback; object backups are separate. Never commit credentials/dumps/test manifests.
- Use Move on managed completed files; Restore elsewhere for changed location/name; CANCEL UPLOADS for tracked pending folder transfers; DISCARD only for no-reference legacy metadata. Restore cannot resume cancelled uploads. Keep dispatcher/cleanup running while the app is active; provider lag may delay reclamation.
- Run python scripts/docker_smoke.py and python scripts/upload_smoke.py after starting services. Destructive tests must use disposable databases/buckets, never app data. Failed browser teardown uses matching TEST_S3 settings and scripts/account_e2e_stack.py --cleanup-storage.
- Docker WSL cap is 4 GB; separate image builds from full DB/browser workloads. Project/Codex/Docker data remain on D; shared Windows/system temp may still use C.

Next Exact Phase:
Phase 15 — File Preview, including L09 safe preview/detected-type acceptance. Phase 16 automatically includes L37 and its other due limitation/provider decisions. Do not advance with unfinished assigned checks.

Standing user instruction:
An ordinary "continue" includes the scheduled step's limitation fixes and acceptance checks automatically. Every numbered/lettered phase report must include "Limitations requiring explicit work" with inherited/new IDs, behavior/impact, tasks, checkpoint and evidence, synchronized with the roadmap/register/CONTINUE. Keep genuine external dependencies explicit while completing independent work. No background execution, push/deploy/spending/destructive-data authorization is implied.

Last Commit:
98a4a70 — Complete Phase 14A version transfers and retention lifecycle. Phase 14B implementation and verification are included in this handoff commit.
