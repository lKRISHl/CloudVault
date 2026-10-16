# CloudVault — Current State

Current phase: Phase 17 — Malware Scanning, implemented and locally verified 2026-10-16.
Next phase: 18 — Realtime, including L15 and its assigned acceptance. Not started.
Project: D:\CloudVault-Dev\Project\CloudVault. Application/source schema: 020_malware_scanning.
Phase15/16 baseline: 6bf868f. Phase17 changes and verification notes are included in this commit.
No push/remote CI. Phase18 has not started.

## Completed Phase 17 scope

- Private ClamAV daemon/signature updater, separate Celery scans queue and one prefork worker.
- Every completed original/replacement/historical version starts quarantined. Migration 020
  backfills all previous content to pending and cancels old preview jobs. No grandfather bypass.
- Conditional bounded S3 streaming, exact size/ETag/basic/composite SHA-256 verification,
  fresh definitions and complete verdict consumption are required before release. No bytes
  enter PostgreSQL or Redis. Tenant/version/namespace/policy/lifecycle/lease rechecks fence I/O.
- Current/history downloads, share creation/anonymous access, transient previews and queued
  preview request/publication/result all enforce the same release policy. Old cached outputs
  cannot survive source release invalidation. Live resource permissions remain mandatory.
- Three attempts/backoff and expiring UUID leases; authorized writers can retry errors from
  version history. Row locking prevents manual retry from overriding a running worker claim.
  Blocked/oversized content has no manual clean override. Policy/provider changes rescan.
- Visible browser scan states, release polling and error retry. Successful scans say no known
  threats detected, never guarantee safety. Supported scan input is at most 100 MiB: larger
  allowed uploads remain quarantined and cannot be downloaded/shared/previewed.
- Operator scan health probes loaded definition freshness and provider access/versioning.
  FreshClam's inherited daemon health check is disabled; active scanner checks verify the
  actual definitions. Independent updater alerts remain Phase28 work. See ADR-041/L39.

## Verification and evidence

- Actual ClamAV 1.5.4/database 28155: clean content accepted, harmless EICAR detected.
  Real owned API/PG/private S3/Redis/prefork round trip proves pre-scan denial, clean exact-byte
  release and detected-content download/preview quarantine. No release/scanner substitution.
- Dedicated real-engine Chromium journey: 1 passed in 5.5s. Full legacy Chromium regression:
  final 22/22 passed in 2.3m. Legacy browser fixtures explicitly substitute only the scanner
  dependency and still stream/verify real provider bytes; they do not certify detection.
- Frontend: 113 tests, lint/build pass. Includes scan-state and authorized retry/cache cases.
- Initial full PG/provider run: 377 passed, five failed, one host-FFmpeg skip, 433.18s.
  Three legacy resource tests needed an explicit successful-scan dependency; two old migration
  tests expected rollback past quarantine. All five were fixed; the guard remains strict.
  Focused PG rerun: 100 passed in 76.07s. Final scan/config PG checks: 22 passed in 12.50s;
  additional cached-preview-release regression: 1 passed on PG. Scan SQLite checkpoint:
  21 passed; final storage/scanner health-only regression passed after dependency-probe work.
  Do not describe the original full backend run as all green.
- Browser initial failures included hard-coded provider routes, Windows resource allocation,
  invitation-click timeout and resumed downloads racing scan release. Routes follow the test
  endpoint; byte assertions now wait for release. Final complete 22-case run passes.
- App backup/020 upgrade preserved all 31 File and 41 FileVersion records before workers ran.
  All 26 original eligible versions were scanned. After unique live smoke demo data, final
  checkpoint: 32 eligible versions clean, zero pending/error/blocked eligible scans.
- Normal UI/API/private-storage smoke and full actual SMTP/basic/multipart/replacement/history
  transfers, sharing/ACLs, retention, movement/recovery/cancel-folder and trash/purge smoke pass.
  The first upload smoke needed replacement scan waits (423); corrected full rerun passes.
  Unique smoke accounts/files remain as documented development demo data.
- Owned test DBs/buckets/queue bindings removed; browser storage manifest absent. Destructive
  pytest fixtures never targeted application data. No unrelated apps closed or WSL cap changed.
- Detailed logs and exact scopes: docs/phases/phase17.md. Reports for completed Phase15/16
  retain their earlier full acceptance evidence; the old Phase15 browser deferral is closed.

## Operation

Normal app is restored at http://localhost:3000/app/folders. Refresh the browser for the new UI.
After source changes: docker compose up --build -d.
Operator scanner check: docker compose exec -T scan-worker python -m app.jobs.check_jobs --job scans --scanner.
API readiness remains DB-only. Scan-worker health also checks definitions/provider.
Other jobs: docker compose exec -T backend python -m app.jobs.check_jobs.
All storage stages have refreshed after restart; the last trash pass reported one deferred
reference while due_trash was zero at observation. Retained cleanup still honors original
capability/late-write deadlines. Health is not a byte-purge or SMTP-delivery guarantee.

Ignored pre-020 DB backup: .local/backups/cloudvault-before-phase17-20261016.sql (176448 bytes).
Earlier pre-upgrade backups remain. Back up before future migrations. Downgrade cannot remove
quarantine from uploaded content or active scan ownership: restore a suitable coordinated
backup instead. Object backup/restore is separate. Never commit dumps/secrets/manifests.

Direct installs need a privately reachable ClamD/updater plus Celery scans worker and Beat.
Synchronize DB/signing/S3 endpoint/region/bucket and scan settings across API/workers; provider
identity is part of scan proofs. There is no always-clean or API-native-scanner fallback.

Docker socket recovery previously required the user's ordinary PowerShell rename of the
stale docker-secrets-engine folder. Do not reset Docker, unregister WSL, prune app volumes
or rewrite ACLs. WSL cap remains 4 GB; heavy suites run sequentially. Windows memory pressure
recurred during browsers while Firefox used substantial RAM. Pause unused development
services first; never close unrelated apps without authorization. Services are restored now.

## Limitations requiring explicit work

- L09 local preview/quarantine/scanning scope is complete. L39 automatically assigns retained
  quarantine quota accounting to 19; pinned/maintained scanner and AWS deployment/paired
  recovery to 26/31; scan-size/format/retroactive rescan/threat-response review to 27;
  freshness/oldest pending/failed/updater alerts to 28; measured memory/latency/fairness/size
  limits to 32. A point-in-time clean scan cannot guarantee safety or recall received bytes.
- L15 realtime cross-tab/progress/cache/roster/ACL/reconnect work is Phase18. L10/L11/L13/P02
  collaboration completion and explicit MVP scope decisions are 18A before quota Phase19.
- L19 reservations, all retained versions/derivatives/quarantine and ambiguous writes are 19.
  L21/L36 audit/job/ref metadata retention is 20. Navigation/rich search is 22A.
- L20/L25/L37/L38 Phase16 local scope passes. Actual AWS/provider replay/lifecycle/decoder
  deployment and long failure windows keep 26/31, security/abuse 27 and load 32.
- L22/L23/P04: AWS selected; unversioned local/refusal policy implemented. Actual AWS IAM,
  encryption/public access/CORS/lifecycle/paired restore and maintained deployment remain.
- L01 remote CI needs separately authorized push/dispatch tied to the tested commit. SMTP,
  MFA, broader security, monitoring, paired restore and L24–L35 retain assigned checkpoints.
  Community MinIO is local development only. No production benchmark/certification is claimed.
- D01–D08 retain capability/SMTP ambiguity, transfer/hierarchy, serialization, cleanup-delay,
  guarded rollback/metadata and platform constraints. See docs/LIMITATIONS_BACKLOG.md.

Standing user instruction: ordinary continue automatically includes all due limitations,
implementation and acceptance. Each phase report records inherited/new IDs, evidence and
future checkpoints synchronized with roadmap/register/CONTINUE. Do not advance past open
acceptance. No automatic commit/push, external spending or destructive app-data authorization.
