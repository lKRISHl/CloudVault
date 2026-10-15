# Phase 14A — Version Transfers, Resume/Cancel and Pruning

Implemented and locally verified on 2026-10-15. Phase 14 committed as 14a4485.
Phase 14A implementation and verification are included in this handoff commit. Final verification and live schema are recorded in CONTINUE.md.

## A. What was built

Multipart replacement versions, bounded chunk hashing, reload-resume manifests and server
progress discovery, explicit candidate cancellation, manual history deletion and configurable
per-file retention. Current content stays available while a replacement is pending. Current
versions are protected from pruning, and all bytes remain counted until confirmed cleanup.

## B. Why

The Phase 14 basic-only replacement path was limited to 100 MiB and did not support reload
resume/cancellation or history pruning. Large replacement transfers need the same verified
part receipts and unknown-acknowledgement protection as initial multipart uploads. History
deletion needs durable intent, live authority, download/upload lease safety and retained
cleanup references rather than immediate metadata removal.

## C. Architecture

VersionPart persists each candidate's part number, size, canonical SHA-256 and provider
receipt. VersionMultipartService reuses existing signing/part-proof/reconciliation primitives
with version-scoped ownership, exact logical-file/object identity and generation checks.
The FileVersion candidate and its manifest commit before provider CreateMultipartUpload.
If creation acknowledgement is lost, the initializing candidate/key remains durable; retry
reconciles discoverable exact-key uploads before initialization, while delayed unknown IDs
remain covered by repeated candidate cleanup. No file bytes enter PostgreSQL.

Completion verifies provider ListParts, conditional completion and final size/composite
checksum/octet-stream/ETag proof. Existing-object inspection reconciles lost completion
acknowledgement. Activation still checks the original generation under the tenant lock,
preserves logical name/location/creator/ACL, revokes external links and applies retention.
Stale candidates cannot activate or obtain fresh part grants. Uploaded replay does not
reactivate history. Progress/resume can reconcile already completed provider state.

Cancellation commits cancelled_at (and multipart aborted state) before best-effort provider
abort. Only the uploader with current file/parent write can cancel/retry/complete a pending
candidate. Future grants/completion stop; expired/late writes still have durable cleanup
references. Cancellation is not immediate byte reclamation or an extension of the deadline.

## D. Pruning, retention and accounting

File creator/current workspace managers with writable parents can queue a completed
non-current version for deletion or set version_keep_last (1–1000, or NULL for all).
Editors can upload/restore content but cannot directly prune history/change policy.
Manual deletion requires DELETE; policy changes require PRUNE. Current content is never
selected. The policy keeps the newest N available completed versions plus current if older,
so restoring an older version can retain N+1 snapshots. Pending candidates are not pruned.

Prune intent is irreversible. New download/restore grants stop immediately; already-issued
GET capabilities keep their safe window. The worker waits the later of original upload
expiry plus completion grace, or prune request plus the maximum 900-second GET lifetime,
then adds settling delay. A later prune deadline is respected by trash too. Disabling a
policy changes future selection and does not revive already queued history.

Policy applies on activation/configuration and through the existing cleanup worker:
up to 25 policy files and 100 queue candidates/file per tick; up to 50 expired/prunable
version references are swept. Future prune deadlines are excluded from the due queue so
they cannot monopolize it. Known version refs are excluded from the broad orphan abort
path and handled under tenant serialization. Maintenance fails closed on Enabled/Suspended
bucket versioning, bucket drift and provider errors.

Cleanup confirms known multipart termination, exact-key inventory absence and object HEAD
absence before setting cleaned_at/purged_at. Successful refs remain for late-write rechecks.
Current protection is checked again before uploaded-history cleanup. Retained/pending sums
change only after success; a queued/failed delete still counts. Whole-file trash coordinates
every completed/pending/pruned reference. Aggregate quota enforcement and complete technical/
audit retention remain the assigned Phase 19/20 integration work.

## E. API

- POST /api/v1/files/{file}/versions/multipart: canonical part manifest, composite proof,
  request ID and original generation; durable initialization and missing-part grants.
- GET /files/{file}/versions/{version}/progress: scoped provider reconciliation/progress.
- POST /files/{file}/versions/{version}/resume: original part hashes, unchanged deadline.
- POST /files/{file}/versions/{version}/parts/{number}/{url|confirm}: shared bounded proof.
- POST /files/{file}/versions/{version}/upload-url: original-content basic retry ticket.
- POST /files/{file}/versions/{version}/complete: basic/multipart verified activation.
- POST /files/{file}/versions/{version}/cancel: 202 durable cancellation/cleanup pending.
- POST /files/{file}/versions/{version}/prune: DELETE-confirmed history deletion, 202 queued.
- PUT /files/{file}/version-policy: keep_last plus PRUNE confirmation, returns current metadata.

History includes method/part size/state, cancellation/prune/deadline markers. FileRead exposes
the current nullable keep-last setting. Provider IDs, object refs and signed URLs are not
stored in browser resume records. API/resource responses retain no-store/no-referrer policy.

## F. Browser workflow

Large replacements automatically use multipart above the smaller of basic cap/part size;
smaller and empty files use basic. Hash memory is bounded to a chunk for multipart plus
at most 1024 small digests. Defaults remain 1 GiB/8 MiB/1024 parts/one hour; configured
multipart ceilings and original URL/deadline/completion-grace rules still apply.

User/workspace/file-scoped sessionStorage manifests survive tab reload and contain only
IDs, declarations, filename and hashes. No storage/account token, presigned URL or file bytes
are saved. Server history offers pending-candidate resume/cancel even without a local record;
storage-disabled browsers can still transfer and discover candidates on the server. The
original file must be reselected and its full manifest verified before missing-part grants.
Completed receipts can reconcile completion without fresh grants during the grace window.

Pause stops the client and preserves resume state. Cancel records the server transition and
clears the matching local state after success. Forget local record affects browser metadata
only and explicitly says server cancellation/cleanup is separate. Session/workspace changes
abort/reject stale operations. Storage PUTs receive no account cookies or bearer credentials.

History shows queued deletion/cancelled cleanup states, prevents current-version pruning,
and requires confirmation for destructive history/policy actions. Native downloads retain
the current logical filename. Restored current content and retention settings survive reload.

## G. Important files

- backend/app/models/file_version.py (VersionPart/markers), models/file.py, 015_version_transfers.
- backend/app/services/version_multipart.py, versions.py, version_policy.py, version_cleanup.py.
- backend/app/jobs/cleanup_uploads.py, services/trash_cleanup.py, api/versions.py, schemas/versions.py.
- backend/tests/api/test_version_transfers.py, test_version_transfers_integration.py and test_version_transfers_migration.py.
- frontend/src/features/versions/versionTransfers.ts, VersionsPage.tsx, services/api.ts, types/index.ts.
- frontend/src/__tests__/VersionTransfers.test.ts, Versions.test.tsx, e2e/versions.pw.ts, scripts/upload_smoke.py.

## H. Verification

267 full backend tests pass on SQLite (325.00s) and PostgreSQL (311.81s), with actual
disposable MinIO storage. Three additional acceptance cases were then added; all 10 version
transfer API/provider cases pass again on SQLite (7.07s) and PostgreSQL (9.38s), covering
270 current backend cases across full-plus-targeted runs on each database. The expanded
collection was not rerun as one full suite. 88 frontend tests, ESLint, TypeScript/Vite,
Ruff and whitespace checks pass. Real targeted integration
verifies exact multipart replacement bytes, missing-part resume, old-current availability,
restoration, historical deletion and cancelled multipart cleanup without affecting current
content. Fault tests cover lost create/complete acknowledgement, durable manifests,
superseded grants, cancellation and restore/prune races. Migration tests preserve existing
snapshots, exercise empty rollback/re-upgrade/alignment and refuse multipart-history loss.
Explicit added cases verify private-authority revocation for every multipart operation,
foreign/uploader boundaries, concurrent cancel/complete with one durable outcome and actual
zero-byte basic replacement/download. Both databases pass the expanded policy activation test.

All 20 Chromium/SMTP/storage journeys pass (1.2 minutes), including reload, wrong-file
rejection, missing-part-only resume, native bytes, cancel, pruning/policy persistence and
mobile layout. An earlier older-workspace timeout did not reproduce in the final full run;
a subsequent startup attempt was blocked by paused Docker services. Services were unpaused,
interrupted owned storage cleaned and the complete final suite passed without a product fix.

Live Docker build/start, HTTP/private-bucket/mc/adapter smoke, real SMTP/transfers/search/
sharing/ACL and basic/multipart version/resume/cancel/prune/policy/trash smoke pass. The smoke
script's reused checksum variable was corrected before the successful run. Live schema is
015_version_transfers with no migration drift; maintenance succeeds and all eight services
are running/healthy. Ignored pre-upgrade backup cloudvault-before-phase14a.sql is 116913 bytes.
Owned PostgreSQL test DB and browser-owned bucket are removed after testing. Evidence:
.local/phase14a-{sqlite,postgres,extra-sqlite,extra-postgres,frontend-final,browser-final,
docker-build,docker-smoke,upload-smoke,live-schema,maintenance,services}.log.
Deletion uses injected test time; no real-time retention wait or remote CI claim.

## I. Operation and rollback

Back up before alembic upgrade head (015_version_transfers). Docker startup migrates;
docker compose up --build -d, python scripts/docker_smoke.py and python scripts/upload_smoke.py
verify the local app with unique development data. Existing upload-cleanup includes policy,
pending version and prune/trash maintenance. Keep it running; failed references are retained.

Migration 015 preserves existing snapshots and adds nullable policy/markers plus receipts.
Any VersionPart, cancellation/prune history or active retention policy refuses downgrade.
Restore a pre-upgrade backup for unrepresentable rollback; object backups are separate.
Keep provider bucket versioning disabled. Tests must use disposable DBs/buckets, never app data.

## J. Limitations requiring explicit work

- **L02/L03:** closed locally with the verification in §H. Original-file reselection, fixed deadlines, chunk
  boundaries, pending-candidate caps and issuer-only controls remain deliberate D04 bounds.
- **L04:** core manual/configurable version pruning is implemented; aggregate quota reconciliation
  remains Phase 19 and complete audit/metadata retention remains 20. Do not mark those later
  acceptance checks complete from this phase's per-file sums or minimal change events.
- **L15:** cross-tab/live progress/cache coordination remains Phase 18. Manifests are tab
  session metadata, not a persistent file cache; current server authority always applies.
- **L20/L21/L25/L33:** repeated refs/part receipts/policy state persist. Metadata compaction,
  production lifecycle/fairness/real-clock behavior, alerts and representative worker/tenant-
  lock/history scale need the scheduled 16/20/26/28/32 work. Provider queue latency can delay
  cleanup and policies may require multiple bounded ticks.
- **L22–L24:** maintained production provider/IAM/encryption/lifecycle verification and any
  explicit provider VersionId decision remain 16/26/27/31. Application versions still do
  not support enabling bucket versioning; maintenance refuses Enabled/Suspended buckets.
- **L01/L26–L35:** remote CI, production SMTP, MFA/security/abuse, cross-browser/provider/load,
  monitoring, deployment and paired backup/restore gates remain open at assigned checkpoints.
- **D01/D02/D06/D07:** bytes/issued capabilities cannot be recalled, pruning/cancellation
  do not instantly free bytes or quota slots, queued deletion is irreversible, and cleanup
  refs/organization content remain protected. This is not complete metadata erasure or legal
  compliance. No additional unassigned implementation gap was identified in this handoff.

See ../LIMITATIONS_BACKLOG.md for the exact sources, tasks, checkpoints and acceptance checks.

## K. Interview discussion

Explain durable intent before provider effects, logical identity versus candidate object,
composite part proof, generation versus version number, actual missing-part reconciliation,
safe download/upload lease expiry before pruning, and accounting only after confirmed
absence. Discuss cancellation/complete and restore/prune races, lost acknowledgements,
bounded policy sweeps, retained late-write refs and why phase completion is not production
or independent security certification. See ADR-033.
