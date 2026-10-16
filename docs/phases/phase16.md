# Phase 16 — Redis and Background Jobs

Started/completed locally 2026-10-16. **Implemented and locally verified, including live
queue/decoder/PostgreSQL/provider/browser acceptance.** The user explicitly deferred Phase
15's final browser verification during this milestone. It was subsequently resumed and
completed: 22/22 journeys and 105 frontend tests pass. See the Phase15 completion report.

## A. Implemented foundation

Celery Beat schedules separate email, storage and preview queues. Workers reuse the existing encrypted
email outbox and tenant-scoped upload/version/trash maintenance services. Tasks contain no
user content, recipient, token, presigned URL or credentials. PostgreSQL remains the source
of truth; Redis messages are periodic work hints, not authoritative upload/deletion records.

Compose replaces the two polling-worker commands with single-process prefork Celery workers
and adds a dedicated single-concurrency preview worker
and adds one Beat scheduler. The legacy CLI loops remain manual fallback only; do not run
both deployments together. Redis has a persistent AOF volume, localhost-only host binding,
96 MiB no-eviction dataset cap and 256 MiB container cap. Scheduler state is expendable;
its container gets Redis settings only, read-only root and a bounded temporary schedule file.

## B. Leases, retry and checkpoints

`background_jobs` stores one global operator-only row for each maintenance job. Atomic
insert/update claims prevent overlapping duplicate dispatch. UUID ownership fences stale
completion, and a 300-second default lease permits crash recovery. Celery soft/hard timeouts
are 150/180 seconds, with 600-second Redis visibility timeout, late ACK, worker-loss
redelivery and prefetch one. Only JSON is accepted; remote-control commands/results/events
are disabled. Local Redis restart and actual prefork crash recovery pass below; production
provider/load certification remains at its assigned later checkpoints.

Retries have bounded exponential delay/count; periodic discovery finds remaining durable
rows after exhaustion or message loss. Exactly-once effects are not claimed. Existing
per-resource locks, expiry/settle windows, idempotency and confirmed provider absence remain
the storage safety boundaries. SMTP acknowledgement ambiguity still permits duplicates.

Orphan inventory markers persist only after a successful maintenance invocation. A failed
attempt preserves its checkpoint; a replacement lease cannot accept an old owner's result.
Provider endpoint/region/bucket fingerprinting resets a checkpoint when its namespace changes.
Credentials do not enter the checkpoint. Per-task engines use NullPool and are disposed so
asyncpg connections do not cross prefork/event-loop boundaries.

Storage rotates uploads, initialization intents, orphan inventory, version policies, versions
and trash, one stage per invocation. Rotation is committed before provider work, so a failed
or killed stage cannot monopolize every retry. Interrupted attempts are recorded on reclaim;
stale lease owners cannot overwrite the new cursor. `STORAGE_STAGE_BATCH_SIZE` defaults to
5 and allows 1–10 records (or one inventory page of that size). Existing nested cleanup
bounds/timeouts still apply; this is not a latency or throughput guarantee. At the default
60-second schedule, each stage gets a turn approximately every six minutes while jobs are
finishing on schedule. Legacy CLI combined ticks remain manual fallback only.

## C. Monitoring and schema

`python -m app.jobs.check_jobs [--job email|storage|previews]` checks Redis and reports execution,
per-stage freshness/failure/interruption/deferred state and aggregate backlog counts/oldest
ages without exposing cursors, tenant IDs, recipients or exception text. Storage additionally
uses non-destructive bucket HEAD/versioning checks and refuses Enabled/Suspended buckets.
One successful stage cannot hide another failed stage. All six stages must have fresh
successes before storage reports healthy; the threshold accommodates one rotation plus
the lease (at least 600 seconds). Compose allows 720 seconds of startup health grace.

Counts distinguish due email, retrying email (including not-yet-due retries), unconfirmed
expired uploads/versions and due unpurged trash. Outstanding retry failures degrade email
health even when the latest maintenance invocation succeeded.
Retained initialization intents are explicitly a **recheck population**, not orphan bytes.
Deferred work may include grace periods or races, not just provider failures. Orphan abort
failures remain visible until a full clean inventory cycle completes. These are best-effort
snapshots, not byte-reclamation, SMTP deliverability or empty-provider proofs. DB-only API
readiness remains unchanged; API feature gating/production alerts are still L25 in Phase 28.

Migration `017_background_jobs` adds only job metadata. No file bytes or cleanup refs move.
Downgrade refuses active leases; stop workers/scheduler and wait for leases first. Removing
the table restarts inventory at its first page and discards operational history, while user
records and exact cleanup refs remain. Disposable SQLite and PostgreSQL migration checks
pass, including preservation/alignment and guarded rollback. Source head is `019_preview_jobs`.
Migration `018_intent_cancellation` adds retained intent folder/scope/cancellation.
Its downgrade refuses recorded scope or cancellation; use a pre-upgrade backup for lossy rollback.

### Durable private previews and static video posters (L38)

The browser now creates a durable preview request, polls its private result and can cancel
the wait. Each request binds the requester, workspace, immutable completed version and PDF
page. Current-version requests also bind generation; explicit historical requests survive
unrelated current changes. Request IDs deduplicate retries. At most 20 queued/running jobs
per workspace are allowed. Creation/cancellation use 100 identity/500 IP category limits;
polling uses 1500/7500 per configured rate window. These bounds are not aggregate quotas.

Migration `019_preview_jobs` retains job state, lease tokens, source identity and an allocated
derivative object UUID before any provider write. No source/derivative/text bytes enter
PostgreSQL or Redis. Five-second argument-free hints alternate rendering and cleanup, with
rotation committed before provider work so hard failures cannot starve either turn. UUID leases,
three maximum attempts and fixed 15-minute expiry bound retries. Worker-loss recovery fences
old publication. Existing source HEAD/conditional read/full checksum and live authority
checks run before rendering, then again under the tenant write lock before publication.
The dedicated preview heartbeat and backlog CLI expose failures/deferred cleanup safely.

Private S3 holds raw sanitized PNG or UTF-8 derivatives up to 1 MiB. Immutable writes and
SHA-256 reconcile ambiguous write acknowledgements; conflicting bytes fail closed. The API
serves no public derivative URL. Every result read checks requester ownership, live tenant/
membership/ancestor/file access, source prune/trash and generation before and after provider
I/O, and validates the derivative digest. Explicit cancellation fences publication; leaving
the browser aborts polling and best-effort cancels a known job. Lost creation responses still
expire automatically. Content already received cannot be recalled.

Cleanup starts after the fixed job expiry plus the lease and upload settle window (25 minutes
from creation at defaults). Cancellation is immediate in metadata, not a byte-purge promise.
One exact derivative is deleted/absence-checked per hint, with versioned providers refused.
References remain for repeated late-write cleanup. Changed provider namespaces are retained
and reported as blocked cleanup rather than deleted from another bucket. Derivative bytes
and retained/ambiguous writes must be included in Phase 19 accounting (L19); retained job/
cleanup metadata policy remains Phase 20 (L21). No aggregate quota or legal erasure is claimed.

Video detection routes supported MP4/WebM signatures to the isolated renderer. FFprobe and
FFmpeg allow H.264/VP8/VP9, at most 120 seconds, 4096 per dimension and 8,294,400 pixels.
They produce one static first-frame PNG, with no audio or original video embed. Other codecs,
malformed/oversized/unknown-duration inputs use unsupported/download fallback. Existing 10 MiB
source, 1600-edge/1 MiB PNG, CPU/memory/process/socket deadlines remain; probe/decode subprocesses
have additional 4/5-second deadlines. Files are temporary in the renderer's bounded tmpfs.
Network isolation, protocol whitelist and disabled MOV external references apply. Process-group
cleanup kills decoder descendants when the Python worker ends. FFmpeg is installed only in
the dedicated renderer Docker target; API/queue workers use IPC with no native host fallback.
This is static poster preview, not moving playback, scanning or a safety certificate.

019 also admits the preview heartbeat name. Downgrade refuses any retained preview job/ref or
an active preview worker lease. Source/application head is 019. Build the renderer/API/three
workers/scheduler together after backing up. Actual native-video decoding, resource/isolation
and local broker/provider/restart proofs pass below. Ordinary host FFmpeg remains absent;
the real decode passed in the container. Phase 15's browser suite was not rerun.

## D. Production storage decision

The user selected **AWS S3** on 2026-10-16. Local MinIO remains a development provider.
Target private unversioned S3 with existing immutable application keys and conditional,
checksummed transfers. Keep refusing Enabled/Suspended buckets. AWS credentials, region,
actual service compatibility, IAM/encryption/CORS/lifecycle and paired recovery evidence
remain required before deployment. No AWS resource or billable operation was created.
Object Lock/VersionId cleanup and strict immediate revocation are not inferred from selecting
AWS; P04's delivery/security review remains assigned to Phase 27.

### Initialization cancellation and operator reconciliation (L37)

Migration `018_intent_cancellation` records a retained folder location, scope-known flag and
cancellation time independently of hierarchy/account deletion. New multipart reservations
authorize membership and parent writes under the tenant lock before committing their exact
provider intent. Folder trash discovers active unmaterialized intents in the subtree as
well as pending files; explicit cancellation commits with trash. Mixed-creator operations
remain manager-only and the combined cancellation cap remains 100. Deadlines/object IDs
never change. Retried initialization rechecks cancellation under the tenant lock before
provider creation, including the gap after the initial intent commit. Restore cannot revive it.

Historical intents have unknown scope; the migration does not invent a folder. Unmaterialized
unknown-scope retries refuse with an instruction to start a fresh request, preventing stale
activation after a trash/restore cycle. Existing materialized transfers remain governed by
their file row and cancellation policy. Retained unknown intents still receive exact-key
cleanup and can be inspected/cancelled by the operator command.

From the backend, `python -m app.jobs.reconcile_upload --tenant <UUID> --file <UUID>` is
read-only and performs no provider operations. It enumerates intent/version keys, buckets,
original deadlines and completion status. Versions use pages of 25 with
`--version-offset <next_version_offset>`; pages do not imply a mutation is authorized.
Run only as a trusted DB operator; inventories contain private object identities and must
not be published or exposed as an HTTP endpoint.

The explicit `--apply --confirm-file <same UUID>` path cancels legacy pending/initialization
retries first and commits that cancellation before provider work. It waits for every original
deadline plus grace/settle, refuses bucket changes/versioned providers/completed references,
then aborts exact multipart uploads, deletes and confirms absence before retiring metadata.
Lost acknowledgements retain references and cancellation. Repeated sweeps still remove late
writes. Nothing is hard-deleted from PostgreSQL; future maintenance keeps the exact keys.

To recover a completed retained snapshot, add `--adopt-version <UUID> --operator-user <UUID>`
to the explicit apply command. Adoption requires an active verified owner/admin in the
selected workspace, live folder authority and a completed non-pruned/non-purged version.
Provider size/checksum/ETag/type must match its verified snapshot. Existing activation writes
change history, invalidates shares and increments generation; it assigns an adoption request
identity and cancels any stale initialization retry without inventing content. Cancelled or
already-retired metadata cannot be revived by this path. It uses existing provider metadata
verification, not an independent full-byte rescan or malware certificate.

Retirement handles large histories in bounded passes, using `STORAGE_STAGE_BATCH_SIZE`
version objects plus the intent per pass. Global checks cover all retained version buckets,
completion states, tenants and deadlines, including references beyond the diagnostic page.
`cleanup_in_progress` requires another explicit pass; `waiting_for_original_deadlines`
requires waiting. Metadata retires only after all version cleanup confirmations exist.
Provider failures leave the batch unconfirmed and references remain available for retries.
Real PostgreSQL/local-provider lost-ACK and late-write checks pass below; AWS certification
remains 26/31. No operator action was
applied to application data during development.

## E. Files

- `backend/app/jobs/celery_app.py`, `tasks.py`, `check_jobs.py`.
- `backend/app/services/background_jobs.py`, `job_backlog.py`, `models/background_job.py`.
- `backend/migrations/versions/017_background_jobs.py`, `018_intent_cancellation.py`,
  requirements/config and Compose; intent/multipart/trash services and operator reconciliation.
- `backend/tests/test_background_jobs.py`, `test_background_jobs_migration.py`, `test_job_health.py`
  and extended upload cleanup tests.
- `models/preview_job.py`, `services/preview_jobs.py`, `jobs/preview_queue.py`,
  `previews/video.py`, migration `019_preview_jobs.py`, queue API/UI and lifecycle/video tests.

## F. Verification performed for this new work

The earlier stage milestone passed 43 targeted local tests in 34.94s. The expanded
reconciliation/job/migration/cleanup/version/trash regression set passes 87 tests in 78.68s, including:
duplicate
exclusion, expired-lease reclaim/stale-owner fencing, persisted rotation before work,
failure/interruption recovery, marker continuity between stage rotations/provider reset,
per-stage failure/staleness/deferred health, bounded real cleanup selection/backlog reduction,
email eligibility/ages, non-destructive provider refusal/error redaction, secret-free retries,
real empty-outbox tasks across event loops and migration preservation/alignment/active-lease
refusal/rollback/re-upgrade. Existing version-transfer and trash cleanup regressions pass.
New cases cover durable subtree initialization cancellation after lost creation ACK,
mixed-creator authority, the intent-commit/provider-start gap, historical unknown-scope
retry refusal, read-only reference inventory, wrong tenant/confirmation/bucket/versioning
refusal, provider lost ACK/late-write retry, active manager/provider/trash checks for adoption,
101-version diagnostic pagination/bounded multi-pass retirement/global deadlines, and
018 preservation/alignment/lossy rollback guards. Database fixtures are disposable SQLite.
Ruff and Compose static validation pass. Evidence: `.local/phase16-reconciliation-tests.log`;
earlier milestones: `.local/phase16-stage-tests.log`, `.local/phase16-jobs-final.log`.

Queued-preview milestone: **127 passed, one explicitly skipped in 116.57s** across the affected
backend regression set, including final rate/authority and persisted-turn interruption checks.
An earlier direct guard rerun passed 13 tests in 10.13s. Covers
source/result integrity, private ownership/idempotency, duplicate/reclaimed/exhausted leases,
lost-write ACK, cancellation during render, generation/history, live revocation/prune/trash,
versioning/late-write cleanup, registered worker heartbeat, video protocol/resource contract
and migration 019 alignment/preservation/lease/ref downgrade guards. Video boundary tests
mock the tools; the real owned-video fixture explicitly skips without FFmpeg/FFprobe.
**103 frontend tests**, ESLint and TypeScript/Vite production build pass, including queue
polling/cancellation and static video posters. Logs: `.local/phase16-preview-final.log`,
`phase16-preview-final-guards.log`, `phase16-frontend-tests.log`, `phase16-frontend-lint.log`,
`phase16-frontend-build.log`. Ruff/Compose static checks and test-harness syntax pass.

The above source-only milestones preceded live acceptance below. Phase 15's earlier 306
backend and 99 frontend results describe its earlier baseline. Its later completion adds
the successful 22-journey rerun and 105-test frontend regression in the Phase15 report.

### Live acceptance follow-up, 2026-10-16

The owned disposable Compose project has separate PostgreSQL/Redis/S3 volumes, database
and loopback ports (UI 43916, PostgreSQL 45916, S3 49916, Mailpit 48916). Destructive test
fixtures never target application data. `scripts/phase16_stack.py` records and validates its
unique project manifest before running or removing resources. `suite` creates/drops a new
database per invocation and uses installed backend test requirements; application images
intentionally exclude pytest. `down` removes only that manifest's project and test volumes.

Passed: real isolated renderer restrictions, generated PNG/PDF/MP4 decoding, queued API/S3
current PDF, historical PNG and static video-poster results; verification mail arrived through
the real email queue and Mailpit. All six storage stages and three job health reports reached
healthy state. Real PostgreSQL upgrade from 016 through 019, legacy intent preservation,
model alignment, downgrade and re-upgrade pass in a separate disposable database.

The full PostgreSQL/provider regression initially finished **357 passed, four failed, one
explicit host-FFmpeg skip** in 698.55s. Two failures were obsolete migration fixtures:
the original intent rollback guard now uses an explicitly unknown-scope legacy row, and the
sharing migration checks the actual migration head. Two failures were Windows MemoryError /
Argon2 allocation errors; memory exhaustion also prevented closing a test transaction and
blocked teardown. Only that disposable database's idle transaction was terminated to allow
the failure report to finish. After stopping unused test services, a focused rerun of all four
failed cases, the neighboring upload integration case and two new provider cases passed
**seven tests in 66.67s**. No application behavior was weakened to make tests pass.

The actual MP4 decode passed through FFmpeg in the constrained container; the ordinary host
suite's tool-unavailable skip remains explicit. Real-provider cleanup tests inject a lost
acknowledgement *after* an actual delete, then verify retained metadata, retry and removal of
late actual writes. Expired records are seeded for these tests; this is not a claim of waiting
through full original upload/preview deadlines. Final provider rerun passes **two tests in
4.60s**, including actual Enabled/Suspended bucket refusal without changing the app bucket.

The final live queue scenario passes end to end: Redis AOF retained two queued hints through
broker restart; an actual prefork child was SIGKILLed while the owned provider was paused;
the committed lease/stage cursor survived. After the **actual 240-second lease expired**,
periodic discovery recovered without clock/database timestamp changes. All six stages made
fresh progress; bounded passes processed 12 seeded expired initialization references across
two tenants and HEAD proved their objects absent. Retained references remain a recheck
population, not a claim of zero metadata or a production throughput/fairness benchmark.
Final operator health reports email/previews/storage and every stage healthy.

The dedicated Phase 16 Chromium journey passes **one test in 18.7s** against real Redis,
Celery, Mailpit, PostgreSQL and S3: register/verify, browser upload, stop the actual preview
worker, cancel a known queued job (HTTP DELETE 200), restart the worker, refresh to a static
video poster and verify inert/mobile display. An earlier response-interception harness
failed after aborting its own route; the final test uses no mocked responses. Phase 15's
browser suite was deferred during this milestone and subsequently passed separately. Existing 103 frontend tests/build evidence remains valid;
the final new browser source also passes ESLint. Backend Ruff passes.

Evidence under ignored `.local/`: `phase16-live-preview.log`, `phase16-postgres-migrations.log`,
`phase16-postgres-full.log` (initial failures retained), `phase16-postgres-rerun.log`,
`phase16-provider-final.log`, `phase16-live-queue.log`, `phase16-live-health.log`,
`phase16-browser.log`, `phase16-acceptance-eslint.log` and `phase16-test-cleanup.log`.
Interrupted Docker/container/observer attempts are not counted as successful recovery proof;
the final queue scenario independently passes. No test touched application tables or volumes.

The owned acceptance containers/network/volumes were removed. Normal app volumes remain;
CloudVault is restored at localhost:3000 with source/application schema 019. A fresh existing-019
database backup was saved to `.local/backups/cloudvault-before-phase16-app-restore-20261016.sql`
(174758 bytes); it is not a pre-017 rollback backup. Restored UI/API, private-bucket denial,
mc object round trip and application-adapter round trip pass (`phase16-app-smoke.log`).
Normal maintenance uses the unmodified 60-second schedule and refreshes all six stages over
approximately six minutes after downtime; `.local/phase16-app-health.log` records its status.
The final restored-app health assertion passes for email, previews and storage, with every
storage stage fresh. All normal application volumes remain intact.

## G. Operation when deployment/testing resumes

Back up before applying `alembic upgrade head` (source head 019). Compose startup migrates;
rebuild backend/worker/scheduler images together. Run one Beat scheduler and separate email/
storage/preview workers using the commands in Compose. Native Windows prefork deployment is not
the intended runtime; use Linux containers. Run `check_jobs` in each corresponding worker
after startup. Keep signing/SMTP/storage settings synchronized between API and workers.
Do not delete Redis/PostgreSQL/S3 volumes to diagnose a health failure.
When live Phase 16 testing resumes, `python scripts/preview_smoke.py --queued --video` uses
owned generated fixtures to check isolation, actual decoder and queued API/provider results.
It passes for this milestone. The older disposable browser harness has a fixture-only preview
dispatcher; it is not Redis/prefork evidence. Phase 15 browser verification later passed separately.

For isolated acceptance, run `python scripts/phase16_stack.py up`, then `suite`, `migrations`,
`python scripts/preview_smoke.py --queued --video --phase16-stack` and
`python scripts/phase16_queue_smoke.py`. The latter pauses only the owned test provider,
kills only its prefork child and waits the real 240-second test lease; run it without other
provider tests at the same time. Once provider availability is restored, the dedicated
frontend command is `npx playwright test --config playwright.phase16.config.ts`.
This config runs only the Phase 16 journey against real queues, with no fixture dispatcher.
Finish with `python scripts/phase16_stack.py down` and restore the normal app if it was stopped.

## H. Limitations requiring explicit work

- **L20, Phase 16 local scope complete:** real broker restart, prefork kill, four-minute lease
  recovery, six-stage progress and two-tenant bounded cleanup pass. Broader slow/large tenant
  backlogs and actual AWS failure/lifecycle windows remain 26/31;
  per-stage batching does not make a nested provider sweep constant-time. Existing refs/
  checkpoints survive, but production completion/fairness is not certified. Test broker loss, worker kill, duplicate delivery,
  restart/checkpoint recovery, delayed provider ACK and long lifecycle windows on AWS in 26/31.
- **L25:** operator dependency/backlog/oldest-age/per-stage health is implemented locally.
  Real local broker/worker/stage/backlog evidence passes in 16; API feature readiness and
  production alerts remain in 28. A fresh invocation can include deferred records; health never
  establishes an empty provider or reclaimed bytes.
- **L37:** folder-scoped unmaterialized cancellation, stale-retry invalidation and explicit
  paged operator inventory/bounded multi-pass retirement/verified adoption are implemented.
  Actual PG/local-provider failure/late-write paths pass; AWS verification remains 26/31. Every deadline/ref
  stays retained; no production closure is claimed.
- **L38:** queued publication/invalidation/cancellation and static poster source work is
  locally verified through actual FFmpeg/container, Redis/prefork/restart, PostgreSQL/local
  provider and browser checks. AWS/failure expansion stays 26; isolation review stays 27.
- **L22:** provider choice is now AWS S3; actual AWS compatibility/credentials/certification
  remains 26/31. **L23/P04:** unversioned release policy and actual local Enabled/Suspended
  refusal pass; AWS enforcement stays 26/31 and delivery/revocation review stays 27.
- **L01, L04/L19, L21/L36, L24, L26–L35, D01–D08:** remote CI, quota/audit, SMTP/MFA,
  production policy/security/load/monitoring/recovery and established capability/cleanup/
  metadata/platform limits keep their assigned checkpoints. Remote CI needs authorization.
- Phase 15 final browser acceptance was deferred at this milestone and subsequently completed
  at the user's request. Its 22-journey rerun is separate evidence from Phase16's browser test.
  No unassigned limitation is hidden by either local completion.

## I. Next exact work

Phase 16's assigned local implementation and acceptance are complete. Review/commit Phase
15/16 changes when requested, then continue Phase 17 with its due limitations. Phase15's
previous deferral is closed by its own successful full rerun, not by Phase16's test.

## J. Design references

[Celery configuration](https://docs.celeryq.dev/en/stable/userguide/configuration.html),
[Redis broker behavior](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html),
[AWS integrity checks](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html),
[AWS conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html).

## K. Interview questions

- Why keep database records when Redis is persistent? Queue persistence is not an exactly-once
  business transaction; replay/loss must not erase authoritative upload or deletion intent.
- Why a lease token? A worker that resumes after replacement must not overwrite a newer
  owner's checkpoint or health outcome.
- Why distinguish execution and backlog health? A worker can run while individual provider
  operations remain failed; readiness must reflect the actual feature's delivery/removal state.
