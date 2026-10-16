# Phase 15 — Bounded File Preview

Implemented 2026-10-15; **completed and locally verified 2026-10-16**. The user resumed the
previously deferred browser acceptance after Phase 16. All **22 Chromium journeys**, **105
frontend tests**, lint and production build pass. Earlier native/live smokes and the **306-test
PostgreSQL/provider regression** remain recorded below. Changes follow Phase 14B commit
`a933798` and remain uncommitted; production/remote-CI gates retain their later checkpoints.

## A. What was built

Authenticated current/historical UTF-8 text, PNG/JPEG/GIF/WebP and PDF-page previews.
Files, search and history link to previews. Unsupported content offers the existing
authorized versions/download workflow. Original HTML/SVG/PDF/video is never embedded.

## B. Why

L09 requires bounded rendering and actual content detection before scanning arrives.
Declared MIME/extensions are untrusted. Verified upload size/checksum does not establish
malware safety or permit bypassing current tenant, membership or ancestor permissions.

## C. Authority and request flow

`POST /api/v1/files/{id}/preview` accepts optional `version_id` and page 0–99.
PreviewService checks live membership, logical-file/all-ancestor read access and retained
completed version state. Trash/pruned/purged/cleaned/pending content cannot preview.
Provider HEAD must match verified size, ETag, octet-stream and basic/composite checksum.
A bounded conditional read is fully rehashed before parsing. After processing, the initial
transaction ends and live authority/version availability is queried again. Default current
selection also rejects generation changes. Explicit history follows current file authority.

## D. Native rendering and isolation

Strict UTF-8 text rejects binary controls, exposes format/bidi controls literally and uses
escaped React text. Native signatures select supported formats; Pillow/PDFium parse actual
content. Fresh PNG pixels strip image metadata. PDF pages are static pixels with annotation/
form drawing disabled; animations use the first frame. Detection is transient, not scan state.

Compose configures a separate credential-free renderer: network disabled, read-only root,
non-root UID, all capabilities dropped, no-new-privileges, 512 MiB/one CPU/32 PIDs and
a 32 MiB noexec temporary filesystem. Only an IPC volume is shared, read-only in the API.
Each job uses a fresh Python process with minimal environment, CPU 5s/address-space
384 MiB/file-descriptor 32/core-dump zero limits; server/client timeouts are 12/15s.
Actual container restrictions and PNG/PDF round trips pass `scripts/preview_smoke.py`.
The IPC initializer required CHOWN plus FOWNER to chmod its volume after changing owner;
those capabilities exist only in the one-shot initializer. The renderer drops all capabilities.

No native parsing falls back into the API process. Direct Windows APIs can preview text;
native formats require a compatible isolated renderer (use the Compose API), otherwise 503.
The E2E-only `TEST_PREVIEW_FIXTURE_RENDERER=1` option parses owned generated fixtures on
the host; it is not a production setting or evidence of container isolation.

## E. Limits and failure behavior

- Source 10 MiB; oversized records return unsupported without downloading. Processing
  storage reads have an absolute 16 MiB bound; ordinary small reads remain 1 MiB.
- Images: 16 million source pixels, output edge 1600, PNG at most 1 MiB; bounded downscales.
- PDFs: at most 1000 source pages, first 100 browsable, one page per request.
- Text: first 65,536 characters, escaped output ceiling 262,144 characters.
- Two source jobs per API process, one renderer job; busy requests require retry. Preview
  category budget is 100 identity/500 IP requests per configured account window.
- Framed renderer output is size/schema/type/page checked; only bounded PNG is accepted.
  Invalid output, unavailable renderer/provider and changed checksums cannot expose raw
  source as a fallback. Video/unknown types receive an explicit download fallback.

These are development bounds, not a throughput or adversarial security certification.

## F. Browser state

Preview remounts for identity/workspace/file/version changes, aborts obsolete requests,
ignores late responses and revokes PNG blob URLs on page changes/unmount. No preview
bytes enter persistent storage/shared query caches. Text is escaped, images constrained,
PDF paging version-bound and content labelled unscanned. Responses use no-store, nosniff,
no-referrer and sandbox CSP. Already received content cannot be recalled.

## G. Important files

- `backend/app/services/previews.py`, `schemas/previews.py`, `api/files.py`.
- `backend/app/previews/worker.py`, `server.py`, `jobs/render_preview.py`.
- `backend/app/storage/base.py`, `s3.py`, `docker-compose.yml`.
- `frontend/src/features/previews/PreviewPage.tsx`, API/types and file/search/history links.
- `backend/tests/test_preview_renderer.py`, `api/test_previews.py`,
  `test_previews_integration.py`, bounded reads in `test_storage.py`.
- `frontend/src/__tests__/Previews.test.tsx`, `e2e/previews.pw.ts`, fixture-only E2E harness,
  `scripts/preview_smoke.py` and `scripts/upload_smoke.py`.

## H. Verification

- Full backend SQLite run: **287 pass, 14 skipped**, 288.77s. Later targeted preview/storage
  run: **47 pass, one real-storage case skipped**, 5.19s. Full collection preceded the four
  added protocol/access tests and provider test, and the final text-expansion truncation-label
  correction; these are covered by the targeted rerun.
- Actual Pillow images/PDFium PDF rendering, malformed/bomb/size limits, renderer frames,
  checksum changes, pending/history/foreign/private/trash/prune boundaries, mid-read
  membership removal, generation conflicts and private provider errors pass.
- **99 frontend tests**, ESLint and TypeScript/Vite production build pass. Escaped HTML,
  PNG blob cleanup, history PDF paging, fallback/retry and obsolete responses are tested.
- Docker images build; renderer restrictions and real isolated PNG/PDF round trips pass.
  Live API/provider image preview, two-page replacement PDF navigation and historical PNG
  pass despite misleading declared MIME. UI/API/private bucket/mc/adapter and SMTP/transfers/
  search/sharing/ACL/version/recovery/trash/text-preview smokes pass. Unique demo data remains.
- Earlier Chromium milestone: **21 of 22 journeys passed**, including real text/image/PDF/history/mobile preview.
  The large-version journey hit Node heap exhaustion. Its 8 MiB buffer deep comparison now
  checks length and SHA-256, matching the existing original-multipart test pattern; it needs
  rerun at that milestone. No failed assertion was removed. Final results follow below.
- Final full PostgreSQL/disposable-provider suite: **306 passed**, 350.28s, including real
  native/history/composite preview sources, migrations and earlier API/concurrency/lifecycle
  behavior. This replaces the earlier interrupted backend attempt as current evidence.
- The interrupted database `cloudvault_phase15_20261015205839` and its browser bucket were
  cleaned before that final run. Final test database `cloudvault_phase15_final_20261015211334`
  was dropped by the test command. Confirm catalog absence when Docker is available.
- Earlier blocker: Docker was no longer running when resuming
  browsers; startup failed on the stale Windows socket. Browser web-server startup therefore
  failed before running tests and left a new owned bucket manifest `.local/e2e-storage.json`
  (`cv-browser-upload-ef43f9fc096748f799f71202eb52762c`); cleanup before another run.
  No reset/volume deletion or app-data destructive fixture was used.
- Evidence: `.local/phase15-sqlite.log`, `phase15-targeted-final.log`, `phase15-frontend.log`,
  `phase15-eslint-final.log`, `phase15-build.log`, `phase15-docker-start.log`,
  `phase15-preview-smoke.log`, `phase15-docker-smoke.log`, `phase15-upload-smoke.log`,
  `phase15-browser.log`, `phase15-postgres.log`, `phase15-docker-failure.log` and
  `phase15-test-database-cleanup.log`, `phase15-postgres-final.log`,
  `phase15-final-database-cleanup.log`, `phase15-interrupted-storage-cleanup.log` and
  `phase15-interrupted-database-cleanup.log`. No app DB was used by destructive fixtures.

### Final browser completion, 2026-10-16

The old owned bucket manifest was cleaned; both historical disposable PostgreSQL databases
were confirmed absent. The first resumed Chromium run passed 21/22 and exposed a separate
navigation race: moving a file to trash, then navigating immediately, unmounted TrashButton
before the request finished. Its alive guard skipped shared cache invalidation, leaving
the destination Trash view empty until refresh. TrashButton and TrashPage now invalidate
shared caches after successful moves/restores/purges even after navigation, while local state
updates remain guarded. Two deferred-response/unmount regression tests cover move and restore.
The browser's immediate-navigation assertion was kept; no sleep or retry hid the race.

The fresh full rerun passes **22/22 Chromium journeys in 2.3m**, with no skips. This includes
real SMTP/account/workspace isolation, original/multipart uploads, sharing/ACLs, recovery/trash,
the real text/image/PDF/history/mobile preview journey and the large multipart replacement/
resume/cancel/prune case that previously exhausted Node's heap. The latter retains full-byte
length/SHA-256 verification. The dedicated Phase16 real-queue journey has its own config and
is explicitly excluded from this fixture-stack suite; no Phase15 journey was excluded.

Full frontend regression passes **105 tests in 56.71s**, including both navigation fixes;
ESLint and TypeScript/Vite build pass. No backend behavior/migration changed during this
completion, so the already recorded backend regression was not repeated. The temporary
SQLite database and unique real-provider bucket were separate from application data. Bucket
cleanup/manifest removal succeeded; all test listeners exited. The final Windows temporary
directory retained only its owned accounts.db; that file and empty directory were explicitly
removed after the listeners exited. The earlier run's temporary directory was already gone.

Evidence: `.local/phase15-browser-completion.log` preserves the initial navigation failure;
`phase15-browser-final-complete.log`, `phase15-completion-frontend.log`,
`phase15-completion-eslint.log`, `phase15-completion-build.log` and
`phase15-prior-browser-cleanup.log` record final verification. The Docker frontend is rebuilt
with the fix and normal CloudVault services restored; completion runtime checks are recorded
in `phase15-completion-docker-build.log`, `phase15-completion-app-restore.log` and
`phase15-completion-app-smoke.log`. Application database/storage volumes are preserved.
Email/previews report healthy after restoration; storage is running and refreshing stale
stage observations over its normal six-minute rotation (`phase15-completion-job-health.log`).
The actual queue recovery/all-stage acceptance already passed separately in Phase16.

## I. Operation and schema

Phase 15 introduced no migration (then-head `016_library_recovery`), persistent derivative/
cache/object reference or readiness state. Phase 16 subsequently added queued derivatives
and migrations through current source/application head `019_preview_jobs`. This completion
introduced no further migration. Earlier backups/guarded rollback requirements remain.
Once Docker starts, run `docker compose up --build -d`, `python scripts/docker_smoke.py`,
`python scripts/preview_smoke.py` and `python scripts/upload_smoke.py`. Use explicit
disposable `TEST_S3_*` settings for real tests and add `TEST_PREVIEW_FIXTURE_RENDERER=1`
for the owned-fixture browser journey. Never use app data in destructive fixtures. Stop
the stack/quit Docker when the app is not in use to save RAM, preserving its volumes.

## J. Limitations requiring explicit work

- **L09, Phase15 local checkpoint complete:** container/native/live API, disposable provider/
  PostgreSQL and all 22 browser checks pass. Run suites sequentially to reduce RAM.
  Phase 17 must implement quarantine/scanning/release policy. The only current preview
  scan label is `unscanned`; content detection does not certify safety.
- **L38 (introduced here; Phase16 local scope now complete):** Phase 15 initially omitted
  bounded video/poster support and durable queues. Phase 16 adds isolated jobs/retries and version-aware publication/invalidation;
  verify malformed/large inputs, ACL/prune/trash races, cancellation and resource bounds.
  Phase 26 verifies chosen-provider/browser failures; 27 reviews decoder isolation.
- **L25/L29/L31/L33:** job/backlog health (16/28), abuse/isolation review (27), actual
  platform/browser compatibility (26/27) and representative decode/concurrency/memory
  workloads (32) remain open. Direct Windows native parsing needs isolated deployment.
- **L37:** Phase16 local reconciliation/cancellation verification now passes, retaining
  original refs/deadlines. Chosen-provider verification remains 26/31.
- **L04/L19, L21/L36, L15, L17/L18:** quota (19), audit/metadata/telemetry (20), realtime
  (18) and rich search/navigation/paging (22A) retain their acceptance gates.
- **L01, L20/L22–L24, L26–L35:** remote CI, maintained provider/IAM/encryption/lifecycle,
  SMTP/MFA, security/load/monitoring/deployment and paired restore remain assigned/open.
  Remote push/CI needs separate authorization. Phase numbers do not close release gates.
- **D01–D08:** issued capabilities/received bytes, SMTP ambiguity, transfer/hierarchy bounds,
  cleanup delays, retained metadata and platform behavior remain explicit constraints.
  No additional unassigned gap is silently deferred.

## K. Interview questions

- Why rehash before parsing? Retained digest plus conditional reads binds the preview to
  verified immutable content even if provider bytes were altered after upload completion.
- Why rasterize PDF? Pixels avoid original active document embedding; the native decoder
  itself still requires strict process/container resource and isolation boundaries.
- Why recheck authority? Membership/parent visibility/trash/pruning can change during work.
- Why transient previews first? Reliable durable derivative lifecycle is assigned to the
  background-job stage instead of introducing stale persistent references prematurely.
