# CloudVault — Current State

Current Phase: Phase 16 — Redis/Background Jobs, implemented and locally verified 2026-10-16.
Phase 15's previously deferred work is also completed and locally verified 2026-10-16:
22/22 Chromium journeys, 105 frontend tests, lint/build and disposable cleanup pass.
A navigation race in shared Trash/file cache invalidation was fixed and regression-tested.
No Phase 17 work yet. Both phase reports are current; no browser deferral remains.
Project: D:\CloudVault-Dev\Project\CloudVault. Source/application schema: 019_preview_jobs.
Last commit: a933798 (Phase 14B); Phase 15/16 changes remain uncommitted. No push/remote CI.

## Completed Phase 16 scope

- Celery Beat and separate JSON-only email/storage/preview queues; persistent capped Redis.
- PostgreSQL UUID leases/fencing, durable six-stage storage rotation committed before I/O,
  provider-bound orphan cursors and safe operator execution/stage/backlog health.
- L37 retained intent folder/scope/cancellation, subtree cancellation/stale-retry invalidation,
  paged DB-operator diagnostics, explicit bounded retirement and verified snapshot adoption.
  Original deadlines/exact references survive errors and remain available for late writes.
- L38 requester/tenant/version/generation-bound queued previews, private S3 derivatives,
  cancellation/publication fencing, bounded retries and retained-reference cleanup.
- Actual credential-free, network-disabled, read-only constrained FFmpeg renderer for bounded
  static MP4/WebM posters. No moving playback, native host fallback or scan certification.
- AWS S3 selected (ADR-037); unversioned immutable-key release policy retained. Actual AWS
  resources/credentials/spending were not provisioned. Production verification stays 26/31.

## Verification and evidence

- Affected backend milestone: 127 passed, one host-FFmpeg skip. 103 frontend tests, lint/build
  passed at that milestone. Latest Phase15 completion adds two frontend regression cases:
  all 105 tests pass. Successful Trash mutations now invalidate shared caches after unmount.
- Full new PostgreSQL/local-provider suite: 357 passed, four failed, one host-FFmpeg skip,
  698.55s. Two obsolete migration expectations were fixed (legacy unknown-scope fixture and
  current-head assertion). Two were Windows MemoryError/Argon2 allocation failures. A leaked
  test transaction caused by failed session.close was terminated only in its disposable DB
  to release teardown. Never describe this original full run as all green.
- Focused rerun of all four failures, neighboring upload case and two new actual-provider
  cleanup cases: seven passed in 66.67s after stopping unused test services. Final provider
  rerun: two passed in 4.60s, including real Enabled/Suspended bucket refusal.
- Real PostgreSQL 016–019 upgrade, legacy intent preservation, model alignment, downgrade and
  re-upgrade pass in a separate owned DB. Initial suite DBs were confirmed removed.
- Actual renderer isolation/generated PNG/PDF/MP4, queued API/S3 current PDF/historical PNG/
  static poster and real queued SMTP/Mailpit round trips pass. Host FFmpeg skip remains;
  actual video decoding was proved inside the constrained container.
- Final live Redis AOF restart, actual prefork-child SIGKILL during provider I/O, committed
  cursor/lease retention and actual 240-second lease expiry/recovery pass. All six stages
  progress; bounded passes remove objects for 12 seeded expired refs across two tenants,
  retaining exact refs. Final all-job/all-stage health is healthy. This is no load benchmark.
- Phase16-only Chromium journey: one passed in 18.7s, using actual queues/provider/renderer:
  verify, upload, stop preview worker, cancel known queued job (DELETE 200), restart worker,
  refresh to static poster, inert/mobile display. No fixture dispatcher/mocked responses.
- Ruff, Compose static validation and final frontend ESLint pass.
- Evidence: .local/phase16-live-preview.log, phase16-postgres-migrations.log,
  phase16-postgres-full.log, phase16-postgres-rerun.log, phase16-provider-final.log,
  phase16-live-queue.log, phase16-live-health.log, phase16-browser.log,
  phase16-acceptance-eslint.log, phase16-test-cleanup.log, phase16-app-restore.log.
- Earlier observer/container interruptions are not successful recovery evidence. The final
  scenario independently passed. All acceptance DBs/buckets/volumes were separate from app
  data. The owned acceptance project/volumes were removed with its validated manifest.

## Operation

Normal CloudVault services are restored at http://localhost:3000. App schema was already
019 before restoration; it was not downgraded or targeted by tests. Fresh ignored backup:
.local/backups/cloudvault-before-phase16-app-restore-20261016.sql (174758 bytes).
This is an existing-019 backup, not a pre-017 backup. Earlier pre-upgrade backups remain.
Phase16 restored-app UI/API/private-storage smoke and email/previews/storage health all passed;
all six normal storage stages refreshed at that checkpoint. Evidence: .local/phase16-app-smoke.log and
.local/phase16-app-health.log.
Storage health can warm up for a six-stage rotation (about six minutes at the normal
60-second schedule). Keep workers/Beat with the app; don't run legacy loops alongside them.
Back up before future upgrades. Guarded lossy downgrade requires a suitable pre-upgrade
backup; object backup/restore is separate. Never commit credentials/dumps/manifests.

Docker socket recovery previously required the user's ordinary Windows PowerShell rename
of the stale docker-secrets-engine folder; Codex got OS access denied. Do not reset Docker,
unregister WSL, prune app volumes or rewrite ACLs. WSL cap remains 4 GB; run heavy suites
sequentially. Windows reported paging-file/allocation errors while Firefox used about 2 GB;
free unused apps before heavy testing. Do not close unrelated apps without authorization.

## Next exact action

Review/commit Phase 15/16 work when requested, then continue Phase 17 with its due limitations.
The user explicitly resumed Phase15 verification. Its fresh complete suite passed 22/22
in 2.3m, including previews and the large-version full-byte length/SHA-256 check. The initial
resumed run exposed a rapid-navigation Trash cache race; it is fixed, with two unit cases.
Full frontend: 105 passed in 56.71s; lint/build pass. No backend change or new migration.
The old bucket manifest and final unique browser bucket were cleaned. Both prior disposable
PG databases are absent; current temp SQLite data was removed after all test listeners exited.
Evidence: .local/phase15-browser-final-complete.log, phase15-completion-frontend.log,
phase15-completion-eslint.log, phase15-completion-build.log, phase15-prior-browser-cleanup.log,
phase15-completion-docker-build.log, phase15-completion-app-restore.log and
phase15-completion-app-smoke.log. The rebuilt frontend includes the fix; app volumes remain.
After Phase15 restoration, UI/API/private storage smoke passes and email/previews are healthy.
Storage is running and refreshing stale stage observations on its normal six-minute rotation;
see .local/phase15-completion-job-health.log. No worker logic changed in this completion.

## Limitations requiring explicit work

- L20/L25/L37/L38 Phase16 local scope passes. Actual AWS/provider outage/replay and long
  lifecycle windows stay 26/31; decoder/security/abuse review 27; representative load 32.
- L22/L23/P04: AWS selection and local unversioned/refusal policy complete; AWS compatibility,
  IAM/encryption/public-access/CORS/lifecycle/paired restore remain deployment gates. Issued
  capabilities/received bytes cannot be recalled; delivery/revocation review stays 27.
- L09 Phase15 local preview checkpoint passes; scanning/quarantine remains Phase17.
- L19 quota/reservations/derivative/ambiguous-write accounting is Phase19. L21/L36 audit and
  retained job/ref metadata policy is Phase20. Realtime is 18; navigation/rich search is 22A.
- L25 API readiness remains DB-only; feature-aware probes/alerts are Phase28. Retained intent
  counts are recheck populations, not orphan-byte or purge proofs. No production benchmark.
- L01 remote CI awaits separately authorized push/dispatch tied to the tested commit. SMTP,
  MFA, maintained storage deployment, security, monitoring, paired restore and other L24–L35
  gates keep their recorded checkpoints. Community MinIO is local development only.
- Bounds remain explicit: preview source 10 MiB, image 16M pixels, PNG 1600 edge/1 MiB,
  PDF 1000 source/100 browseable pages, text 65,536 characters, video 120s/H264/VP8/VP9 and
  bounded 4K pixels. Cancellation/expiry retain refs and delay byte cleanup; no scan guarantee.
- D01–D08 retain capability/SMTP ambiguity, transfer/hierarchy, serialization, cleanup-delay,
  guarded rollback/metadata and platform constraints. See docs/LIMITATIONS_BACKLOG.md.

Standing user instruction: ordinary continue automatically includes all due assigned limitations,
implementation and acceptance. Every phase report must record inherited/new IDs, actual evidence
and future checkpoints, synchronized with roadmap/register/CONTINUE. Don't advance past unfinished
acceptance. The previous Phase15 browser deferral is now closed. No automatic commit/push, external
spending or destructive application-data authorization is implied.
