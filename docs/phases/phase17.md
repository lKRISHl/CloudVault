# Phase 17 — Malware scanning and quarantine

Status: implemented and locally verified, 2026-10-16. Application migrated to 020.
Phase 15/16 baseline is committed as `6bf868f`.

## Behavior

Completed original and replacement uploads remain quarantined until their exact immutable
version passes scanning. Current/historical download grants, sharing and both preview paths
require release. Migration 020 quarantines all prior versions and cancels old preview jobs;
existing content must be scanned too. Metadata, trash and deletion remain available according
to existing permissions. Antivirus does not guarantee safety.

States: pending, scanning, clean, blocked, error and oversized. Worker failure never grants
access. Three automatic attempts use durable UUID leases and bounded backoff. Authorized
file writers can retry errors from version history. Blocked content must be replaced/deleted;
there is no manual clean override. Changes to scan-size policy/provider namespace trigger
rescanning. Historical clean content can remain downloadable while a replacement is pending.

The worker validates provider metadata, conditionally streams the retained exact object in
64 KiB chunks, verifies its complete basic/composite SHA-256 and checks ClamAV's reply.
Successful publication rechecks tenant/version/lifecycle/lease/policy. No object bytes enter
PostgreSQL or queue messages. Quarantine uses database authority over private immutable keys;
it does not move content into another bucket.

## Operational limits

`SCAN_MAX_BYTES` defaults to and permits at most 104857600 bytes (100 MiB). Larger multipart
uploads can complete integrity verification but stay oversized/quarantined. Upload acceptance
is not a promise of eventual scanner release. The configuration API exposes the scan limit.
`SCAN_TIMEOUT_SECONDS` defaults to 90, maximum 120; definitions must be <=24h old by default,
configuration maximum 48h. Missing definitions/daemon, bad replies and checksum errors block
release. Policy alerts include encrypted/archive-limit/macro/malformed supported content;
format coverage and false negatives remain scanner limitations.

Compose includes a private ClamAV daemon, separate signature updater and dedicated single
prefork scan worker. Daemon has no application credentials, host port or external network.
Updater only has the signature volume. Definitions are loaded without concurrent engine
reload to reduce peak RAM. The development image tag is mutable; production image/digest,
patching, AWS behavior and threat-response certification remain release gates.

Existing issued storage URLs work until expiry; upgrade cannot recall them or received bytes.
Pause new grants and account for the capability window when deploying quarantine. Automatic
rescanning on every signature update is not implemented. Quarantined bytes remain retained
until explicit trash/purge/version cleanup; quota accounting is due in Phase 19.

## Verification

- First focused quarantine/protocol run: 8 passed; expanded targeted run: 71 passed, one
  obsolete three-queue schedule assertion failed and was updated to include scans.
- Real ClamAV 1.5.4 with signature database 28155 accepted clean bytes and detected the
  harmless EICAR fixture. FreshClam downloaded/validated the database update successfully.
- Actual API/PostgreSQL/private S3/Redis/prefork worker/ClamAV round trip passed: both clean
  and EICAR objects were denied before dispatch; clean exact bytes became downloadable,
  detected content stayed denied for download and both preview routes. Independent owned
  database and bucket were used; no release-gate dependency substitution was installed.
- Initial full PostgreSQL/provider run: 377 passed, five failed, one host-FFmpeg skip in
  433.18s. Three original resource tests needed their explicit legacy scan dependency;
  two migration tests expected populated uploaded content to downgrade past quarantine.
  Tests now assert the new refusal and preservation; the production guard was not weakened.
  Focused PostgreSQL rerun passed 100 cases in 76.07s, covering all five failures, storage,
  scan rules, actual provider multipart, migration/model alignment, rollback and job health.
- Final exact-gate tests: 21 passed on SQLite; 22 PostgreSQL checks passed in 12.50s including
  configuration and new scan health. Retry obtains a version row lock against worker claims.
  A final health-only check passed after adding the scan storage-dependency probe.
  One additional PostgreSQL regression proves a ready cached preview becomes inaccessible
  when its source release is invalidated; no cached derivative is returned.
- Frontend: all 113 tests pass; lint/build pass. Seven scan-state cases and authorized
  failed-scan retry/cache invalidation are included. Unknown states display quarantine.
- Real-engine Chromium journey: one passed in 5.5s using actual isolated API/PG/S3/Redis/
  prefork/ClamAV state. Browser displays clean/detected content and 423 download/preview
  failures for quarantined content. No scanner/release substitution in that journey.
- Full legacy browser regression: final 22/22 pass in 2.3m. Initial run was 18/22: two
  hard-coded provider-route expectations, Windows ERR_INSUFFICIENT_RESOURCES and an
  invitation click timeout. Next affected run was 4/6: resumed downloads still raced scans.
  Provider routes now follow the test endpoint; byte-download assertions wait for release.
  Final full run passes original/replacement multipart resumes, full downloaded byte hashes,
  history/restore, permissions, sharing, previews, workspace and account journeys.
  Its explicitly selected generated-fixture scanner still fully streams/rehashes sources;
  this run certifies browser behavior, not ClamAV detection or queue delivery.
- Real app upgrade preserved 31 File and 41 FileVersion records. Backup before 020:
  `.local/backups/cloudvault-before-phase17-20261016.sql`, 176448 bytes. All 26 original
  eligible retained versions were scanned. Final checkpoint after live smoke: 32 eligible
  versions clean, zero pending/error/blocked eligible scans. Normal app/scan worker restored.
- Live normal-app smoke passes UI/API/private S3 round trips and actual SMTP/basic/multipart/
  historical/replacement downloads, sharing/ACLs, retention, movement/recovery and trash.
  The first upload smoke found a missing replacement scan wait in the smoke itself (423);
  both replacement grant paths now wait for release, and the entire smoke rerun passed.
  Unique smoke accounts/files remain documented development demo data.
- Scanner health actively checks loaded definition age plus provider access/versioning.
  Updater's inherited clamd health check is explicitly disabled: it runs FreshClam, not a
  daemon. Actual updater logs show 28155/63/339 up to date; scanner health probes freshness.
  Independent updater-process alerts remain the Phase28 operational gate.
- Owned acceptance DBs/buckets and queue bindings were removed; browser storage manifest is
  absent. No application DB was used by destructive pytest fixtures. App volumes persist;
  no WSL cap change or unrelated user-app closure. CPU/memory/throughput are not benchmarked.
- Evidence: `.local/phase17-scan-tests.log`, `phase17-focused.log`, `phase17-real-clamd.log`,
  `phase17-real-queue.log`, `phase17-postgres-full.log`, `phase17-postgres-rerun.log`,
  `phase17-scan-postgres-final.log`, `phase17-health-final.log`, `phase17-frontend-tests.log`,
  `phase17-frontend-lint-final.log`, `phase17-frontend-build.log`, `phase17-browser.log`,
  `phase17-browser-final.log`, `phase17-app-backup.log`, `phase17-app-restore.log`,
  `phase17-app-smoke.log`, `phase17-app-upload-smoke-final.log`,
  `phase17-app-scan-health-final.log`, `phase17-updater-health-fix.log`, `phase17-ruff.log`.
  Cached preview regression: `phase17-cached-preview-gate.log`.

Original resource unit tests explicitly substitute a successful scan dependency only in a
frozen list of legacy modules; they verify their original contracts. New test modules and
`scan_enforcement` cases keep the real gate. Actual acceptance uses the real engine and queue.
These different scopes must remain explicit in test reports.

## Operation and remaining release gates

Run `docker compose up --build -d` after source changes. The UI is at
http://localhost:3000/app/folders. From the private worker, use
`docker compose exec -T scan-worker python -m app.jobs.check_jobs --job scans --scanner`.
Readiness remains DB-only; operator scan health is separate. Storage maintenance stages can
warm through their normal six-minute rotation after restart.
At the last checkpoint all six storage stages had refreshed; trash's last pass reported
one deferred reference while the current due-trash count was zero. Existing cleanup deadlines
still apply; this is not an assertion of immediate byte purge. Scan health is healthy.

Direct installs require a reachable privately deployed ClamD and signature updater, plus a
Celery scans worker/Beat. Keep DB/signing/S3 endpoint/region/bucket and scan settings identical
between API/workers; provider identity is part of the verdict. There is no API host-parser
or always-clean fallback. Production AWS/security/load certification remains pending.

## Limitations requiring explicit work

L09 local scanning/quarantine checkpoint is complete. L39 carries explicit size/coverage/retention/rescan/deployment
work to 19/26/27/28/31/32 and is automatically part of those checkpoints.
Acceptance at those checkpoints must prove quota inclusion, actual AWS/pinned private scanner
deployment/recovery, the selected retroactive rescan/threat-response policy, actual freshness/
updater/backlog alerts and measured production size/resource/fairness limits. The 100 MiB
local bound and point-in-time verdict remain until that work is explicitly implemented.

Inherited open work remains: L15 realtime in 18; L10/L11/L13/P02 collaboration/MVP decisions
in 18A; L19 quotas in 19; L21/L36 audit/metadata in 20; L20/L22/L23/L37/L38 actual provider/
deployment/decoder extensions in 26/31 and independent security in 27; L24 MFA/security in 27;
L25/L26 feature-aware operational alerts in 28 and L29/L33 representative abuse/load in 32.
L01 remote CI requires separately authorized push/dispatch. Existing SMTP ambiguity, signed
capabilities, guarded rollback and cleanup-delay boundaries D01–D08 remain as recorded in
the limitations register. No additional untracked phase limitation was identified.
