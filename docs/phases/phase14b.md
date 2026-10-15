# Phase 14B — Core Library Movement and Recovery

Implemented and locally verified 2026-10-15. Phase 14A committed as 98a4a70.
Phase 14B implementation and verification are included in this handoff commit. Final evidence and live schema are recorded in CONTINUE.md.

## A. What was built

Completed-file movement, restore to an explicitly chosen writable destination/name,
confirmed cancellation of pending original uploads followed by folder trash, and authorized
discard of legacy metadata without an upload session. Existing logical file/version/object
identities and resource-local ACLs survive movement and recovery.

## B. Why

L05–L08 were explicit gaps in earlier phases: only folders could move, trash recovery failed
when the original parent/name was unavailable, pending uploads blocked folder trash, and
legacy pending metadata could neither complete nor be removed safely. These workflows need
current authority, atomic namespace changes and durable cleanup rather than copied bytes or
forced database deletion.

## C. Architecture and authority

FileService.move serializes tenant writes, requires creator/manager authority and writable
source/destination parents, checks the caller's source_folder_id and rejects stale location
changes. Name conflicts fail atomically. Actual location changes revoke external links;
file/version IDs, generation, upload/object keys, content and grants remain unchanged.
Resource read/ancestor boundaries and pending-version completion authority remain live.

TrashService.restore accepts the original location by default or an explicit destination
(including root) and optional normalized name. The selected destination must be active,
readable and writable. Creators/managers must still read the original resource/ancestors
including trash; the old parent need not be active for explicit recovery. Folder restore
requires subtree ownership or manager authority and checks the full height, including older
independent trash, against depth 64. A subtree cannot become its own ancestor. Names/FKs
and clearing the batch commit together; conflicts roll back everything. Only the selected
batch is restored; older independent trash remains trash and queued purge cannot restore.

## D. Cancellation and legacy state

The normal folder trash operation still refuses pending uploads. The separate confirmation
path requires literal CANCEL UPLOADS, checks all creator/manager/source-parent boundaries,
and commits pending upload_cancelled_at markers and the trash batch atomically. At most
100 live pending records are cancelled per folder operation; larger folders must be handled
through smaller subfolders first. Mixed creators require a workspace manager. Multipart
pending state becomes aborted; new grants/progress/confirmation/completion fail. Restoring
the folder cannot resume those uploads. Existing issued PUT/part URLs may still write.

There are no provider calls in that transaction. The existing original-upload and extended
trash cleanup workers retain exact refs and original expiry/grace/settle windows, abort
multipart remnants, delete objects and confirm absence. Pending refs prevent successful
trash-purge accounting until cleaned; confirmed refs remain for retries/late writes. Name
reuse follows the existing trash namespace rules; cancellation does not claim immediate
byte reclamation or removal of an already issued capability.

Legacy discard requires literal DISCARD, resource creator/manager and writable parent.
Only pending rows without an object, FileVersion or UploadIntent may be discarded. The
row receives cancelled/cleanup tombstones, retains internal metadata and releases its name
through existing live-name indexes. No bytes or upload session are invented. Contradictory
retained intents fail closed for operator reconciliation and are never silently dropped.

## E. Schema and API

016_library_recovery adds nullable File.upload_cancelled_at, a pending-only check and a
cleanup constraint allowing proven no-reference legacy tombstones. Existing rows, snapshots
and object keys are unchanged. Downgrade refuses any original cancellation/discard history.

- POST /files/{id}/move: folder_id and expected source_folder_id, returns FileRead.
- POST /files/{id}/discard-metadata: DISCARD confirmation, 204.
- POST /folders/{id}/cancel-uploads-and-trash: CANCEL UPLOADS confirmation, 201 TrashRead.
- POST /trash/{id}/restore: optional use_original, destination_id and name; 204. Old callers
  without a body retain original-location recovery.
- FileRead adds upload_cancelled_at and derived legacy_metadata; refs/provider secrets stay private.

File move/discard use ordinary account mutation budgets; restore/cancel-trash use existing
100 identity/500 IP trash budgets per configured window. Response no-store/no-referrer and
tenant/session protections remain in effect.

## F. Frontend

Managed completed files expose Move with a paginated writable-destination picker and stale
source/conflict errors. Legacy records expose DISCARD confirmation instead of unusable retry.
Trash offers original restore and Restore elsewhere with destination/name selection. Folder
trash has a separate CANCEL UPLOADS confirmation explaining scope, outstanding authorizations
and cancelled state after restore. Cancelled basic files cannot offer retry; cancelled multipart
state hides resume controls. Scoped caches refresh file/search/folder/trash/share/permission state.

## G. Important files

- backend/app/services/files.py, trash.py, trash_cleanup.py, uploads.py, multipart.py.
- backend/app/models/file.py, schemas/files.py, schemas/trash.py, api/files.py, api/trash.py.
- backend/migrations/versions/016_library_recovery.py.
- backend/tests/api/test_library_recovery.py, test_library_recovery_integration.py and test_library_recovery_migration.py.
- frontend/src/features/folders/DestinationPicker.tsx, FileRecoveryActions.tsx, FileList.tsx.
- frontend/src/features/trash/TrashPage.tsx, TrashButton.tsx, services/api.ts, types/index.ts.
- frontend/src/__tests__/LibraryRecovery.test.tsx, e2e/library-recovery.pw.ts and scripts/upload_smoke.py.

## H. Verification

286 full backend tests pass on SQLite (429.13s) and PostgreSQL (437.45s), including real
disposable storage and migration/data-preservation/rollback guards. A final fail-closed
legacy-snapshot guard was then added and all 15 recovery API/provider cases pass again on
SQLite (13.55s) and PostgreSQL (16.50s). The full collection was not rerun after that guard.
93 frontend tests pass with final ESLint/TypeScript/Vite, Ruff and whitespace checks.

All 21 Chromium/SMTP/storage journeys pass in the final full run (1.2 minutes). The new
journey verifies real moved/recovered download bytes, destination/name selection, explicit
folder cancellation, restored cancelled state, absent retry controls and mobile layout.
Browser test helpers now wait for navigation, activate the intended identity page, allow
15 seconds for workspace email delivery, select large version fixtures from files on D and
remove the simulated part outage before checking successful cancellation. Earlier attempts
had navigation/file-input/transport/timeouts; final assertions remain intact and all pass.

Real provider tests cover basic and multipart pending records, an already-issued basic PUT
arriving after cancellation, safe deadline waiting, confirmed exact-key multipart/object
removal and preservation of moved version bytes/identity. API tests cover foreign/private/
read-only boundaries, source races, conflicts/rollback, older independent trash, full subtree
depth, mixed creators, cancel/complete and restore/purge races, 100-pending bound and legacy
reference refusal/name reuse. Old-schema seeded legacy rows survive upgrade, empty downgrade/
re-upgrade and alignment; cancellation/discard history prevents downgrade.

Rebuilt Docker HTTP/private-bucket/mc/adapter and SMTP/transfers/search/sharing/ACL/version/movement/renamed-recovery/cancel-folder/trash smoke pass. Live 016_library_recovery has no schema drift. Maintenance succeeds (four trash batches checked); all eight services were running/healthy before intentional shutdown to save RAM. Pre-upgrade backup: .local/backups/cloudvault-before-phase14b.sql (140348 bytes). Owned PostgreSQL test DB and browser bucket were removed. Evidence: .local/phase14b-{sqlite,postgres,final-recovery-sqlite,final-recovery-postgres,migration,frontend,browser-final,docker-build,docker-smoke,upload-smoke,live-schema,maintenance,services,shutdown}.log.
Tests use disposable DBs/buckets and injected expiry time; no real-time retention wait or
remote CI, production provider, representative load or independent security claim.

## I. Operation and rollback

Back up before alembic upgrade head (016_library_recovery). Docker startup migrates;
docker compose up --build -d, python scripts/docker_smoke.py and python scripts/upload_smoke.py
exercise the local app with unique development data. Keep cleanup workers running. If not
developing, docker compose stop and quitting Docker Desktop release resources; start again
before using the app. Tests must never point destructive fixtures at application data.

Any cancellation/discard marker prevents downgrade, even after cleanup. Restore a pre-upgrade
backup for unrepresentable rollback; SQL backups cannot recover removed object bytes. Keep
provider bucket versioning disabled and verify paired DB/object recovery before production.

## J. Limitations requiring explicit work

- **L05–L08:** closed locally for the documented tracked-record scope with §H's evidence. Source expectations,
  namespace/depth bounds, subtree ownership and explicit irreversible cancellation are deliberate
  controls. Ordinary no-session legacy discard is covered; contradictory references remain L37.
- **L37 (new):** legacy metadata with a retained intent/version reference fails closed. Phase 16
  must add an operator diagnostic/reconciliation path that preserves every known key/deadline,
  proves cleanup/adoption and safely retires the record; test provider failure/lost ACK/late writes
  and no silent reference deletion. Verify against the chosen provider before public deployment.
  Unmaterialized initialization intents remain in existing exact-key maintenance, outside the
  tracked File cancellation list. Add folder-scoped discovery/cancellation and stale-init retry
  invalidation after trash/recovery in 16; active trashed parents already reject allocation.
- **L09:** Phase 15 safe bounded preview/detected-type handling, then Phase 17 quarantine/scans.
  Moving/restoring bytes does not establish MIME safety or scanning.
- **L04/L19/L21/L36:** Phase 19 aggregate quota/retained-pending/trash usage reconciliation and
  Phase 20 complete movement/recovery/cancellation audit/metadata retention remain open. Tombstones
  are retained; this phase adds no full audit UI or erasure certification.
- **L15/L17/L18:** realtime cross-tab/cache invalidation remains 18; richer navigation and scalable
  pagination remain 22A. Destination pages stay at 25; changing content can shift pages.
- **L20/L22–L25/L33:** provider lifecycle/fairness/real-clock and maintained-provider/IAM/backup/
  monitoring/worker/tenant-lock/load checks remain 16/26/27/28/31/32. The 100-pending cancellation
  cap and existing subtree enumeration must be included in representative scale validation.
- **L01/L26–L35:** remote CI remains immediate pending separate push/dispatch authorization;
  SMTP/MFA/security/abuse/cross-browser/deployment/recovery gates remain assigned and open.
- **D01/D02/D06/D07:** issued capabilities/received bytes cannot be recalled, committed cancellation
  cannot resume, queued purge is irreversible, and retained metadata/refs preserve cleanup safety.
  L37 is the newly recorded follow-up; no additional unassigned gap identified. Inherited checks
  remain in the shared register and are included automatically at their assigned checkpoints.

See ../LIMITATIONS_BACKLOG.md for sources, exact checkpoints and acceptance criteria. An ordinary
"continue" includes due limitation work automatically; do not advance with unfinished due checks.

## K. Interview discussion

Explain logical identity versus location, expected-source concurrency, live source/destination
authority, atomic recovery batches versus older independent trash, height/namespace constraints,
durable cancellation before provider effects and why late-write cleanup must retain original
deadlines. Distinguish safe legacy discard from deleting evidence of a known provider object.
See ADR-034.
