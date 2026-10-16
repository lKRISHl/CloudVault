# Phase 19 — Storage Quotas

Implemented 2026-10-16–17; local quota acceptance and the combined18+19 checkpoint are
verified to the exact scopes below. Application migration/rebuild is applied; no commit/push.
The user explicitly requested19 ahead of18A;18A remains pending.
Schema021_storage_quotas adds storage policy, accounting bounds and inventory evidence.

## Behavior and architecture

New basic/multipart uploads, replacement versions and queued previews require an atomic
workspace quota admission check under the existing tenant write lock. Default Free capacity
is10GiB and Team100GiB, configurable by STORAGE_FREE_LIMIT_BYTES/STORAGE_TEAM_LIMIT_BYTES.
These are development plan allocations, not paid subscriptions. Only a DB operator can
change a workspace's plan/explicit byte limit. Public users cannot upgrade their own plan.
Billing/entitlement integration remains25A.

The source of truth is retained references, not a mutable counter or file-list total.
An aggregate union groups bucket/file/object identities across File, FileVersion and original
multipart initialization intents. Current file mirrors and their immutable snapshots count
once. History, trash, pending deletion, private files, cancelled/expired uploads and every
scan state—including blocked/oversized—continue to consume allocation until their normal
cleanup proof is recorded. Completion converts reservation to retained usage without adding
another copy. Restore, rename and movement do not create new content allocations.

Multipart intent size is committed before provider creation. Unknown legacy intent sizes
are not guessed as zero: new allocations pause with409 until an operator reconciles them
or normal delayed cleanup proves absence. Known materialized references supersede matching
initialization intents. Same-request retries do not reserve twice. After a plan reduction,
existing reservations can finish and existing downloads/cleanup remain available, while
new allocations fail403 when over quota. There is no automatic eviction or content loss.

Queued previews reserve the full1MiB derivative bound before rendering/provider writes.
Keep this conservative allocation even for small/unsupported/cancelled/failed results:
an earlier attempt may have written bytes with an ambiguous acknowledgement. Only cleanup
after its retained deadline and provider-absence proof releases it. These are allocated
bytes, not a provider invoice or promise of exact physical-byte metering.

## Inventory and safe reclamation

The existing storage rotation now has seven stages, adding quotas after trash. Each quota
turn selects one workspace by oldest check time and persists failure/selection before I/O,
so failed tenants do not monopolize the queue. A tenant lock serializes evidence publication
with admission. One provider page plus at most one page of retained evidence is examined;
page size uses the stage batch default5, bounded to10 for quota inventory. Each exact key
checks object length and a bounded multipart manifest (two simultaneous upload IDs, up to
1024 parts each, at most two part pages per upload). Larger/unknown manifests pause new
admissions rather than silently understating usage.

Object listing uses the workspace prefix. Multipart discovery uses a bounded privileged
bucket listing with persisted markers, then exact tenant filtering: actual local MinIO
testing showed directory Prefix omitted a live upload that the bucket/exact-key listings
exposed. No foreign object identities enter the workspace response. Malformed namespace,
provider errors, versioned/suspended buckets or failed observations retain evidence and
pause new allocations. Namespace changes also require reconciliation.

Observed object bytes and multipart parts may increase an existing bound without counting
the same identity twice. Unreferenced discovered objects/parts are reported separately.
Inventory never deletes data. Missing an item from a listing page does not release it:
retained observations receive exact object/multipart absence checks. Existing upload/version/
trash cleanup retains its grace/late-write/refusal semantics. Initialization cleanup now
records reclamation only after object and multipart absence; all exact references survive.
Provider listing is not an atomic bucket snapshot. External privileged writes/late uploads
can arrive between observations; issued presigned capabilities cannot be recalled (D01/D02).

## API, UI and operation

GET /api/v1/organizations/current/storage-usage requires an active verified owner/admin.
It returns no-store aggregate plan/limit, retained/reserved/derivative/orphan/available bytes,
over-quota and unresolved-accounting state. Ordinary members cannot inspect private workspace
totals. Settings shows this information with safe quota/reconciliation messages and15s polling.
The server, not the browser's displayed remaining space, decides admission.

Operator diagnosis (backend): python -m app.jobs.storage_quota --tenant TENANT_UUID.
Explicit plan change additionally requires --plan free|team --apply --confirm-tenant
TENANT_UUID; optional --limit-bytes sets a nonnegative override. Changing the plan without
an override restores that plan's configured limit. No credentials or payment provider is
invented. Keep API/worker settings synchronized.

Back up before alembic upgrade head. Application upgrade021 is now applied after backup.
Rollback refuses custom plan/limit policy, positive/unknown inventory evidence or an
unmaterialized initialization bound that the old schema cannot reconstruct. Ordinary source
references remain in the older schema; earlier quarantine/version/trash guards still apply.
A coordinated pre-upgrade backup is the recovery path when a rollback is unrepresentable.
Never point destructive tests at the app database/bucket.

## Verification record

Initial local quota tests:10 passed,1 PostgreSQL-only concurrency skip. Targeted realtime,
scanning, background jobs and quota migration:51 passed. Frontend lint/build and125 tests
pass, including quota panel and member privacy. Backend changed-file Ruff passes.

The broader initial SQLite run had385 passed,15 failed,20 skipped. Most failures exposed
old migration fixtures coupled to the evolving Tenant ORM. Storage policy now lives in its
own StorageQuota model/table, preserving the authentication schema. A known-size legacy
recovery fixture now declares its reservation rather than creating an unknown allocation.
These fixes and remaining historical cases were verified below; do not label the initial
full run green.

Initial focused PG/Redis/provider run:62 passed,2 failed. Redis was not published on the
application port; a separate128MiB localhost-only disposable Redis now serves acceptance.
Its actual ticket GETDEL/global lease test passes. Real provider pagination/parts/reclamation
now passes after the MinIO directory-prefix fix. The PG quota concurrency case passed.

Initial account/workspace/folder browser run:9 passed,2 failed. One worker hit native memory
exhaustion while backend checks were active; the other exposed ownership confirmation lost
during a role-change page reset. The UI keeps a scoped secret-free navigation receipt while
still remounting protected state. Subsequent reruns and acceptance are recorded below.
Project scanner/workers were temporarily paused for memory and restored with the rebuilt
stack. Application data/volumes were not reset; the backed-up schema upgrade is applied.

### Final checkpoint evidence (2026-10-17)

- Focused PostgreSQL/Redis/private-provider checkpoint:66 passed in44.91s. Includes real
  concurrent quota admission and actual orphan object/part pagination/absence accounting.
  Final quota-only rerun after operator/1024-part-bound cases:16 passed in8.64s. The separately
  rerun15 historical migration/recovery failures pass on PostgreSQL in171.63s. This resolves
  the observed initial failures; it is not a newly rerun all-green full backend suite.
- Frontend125 tests, lint and build pass. Full browser checkpoint:23 passed/1 invitation-click
  timeout; isolated workspace rerun passes both cases in15.9s, including role-transfer
  confirmation. Dedicated zero-quota browser journey passes in8.9s, proving denial before
  File creation/provider transfer and a zero-allocation usage panel. No timeout is hidden.
- CI startup helper's three deadline/retry tests pass; full backend/script Ruff checks pass.
  Actual fresh-scanner/broker/storage/worker readiness gate passes in the rebuilt app.
- Pre021 ignored backup: .local/backups/cloudvault-before-phase19-20261017.sql (208310bytes).
  Migration preserves36 File,49 FileVersion,24 Tenant,31 User,14 UploadIntent and0 PreviewJob
  rows and creates24 policy rows. Before/after observations are under.local; no dump committed.
- Rebuilt UI/API/private-bucket/mc/application-adapter smoke passes. Actual nginx WebSocket
  upgrade, opaque own confirmed multipart receipt progress, retained cancelled reservation
  and server-side logout closure4401 pass (scripts/realtime_smoke.py). Actual container quota
  inventory checks two references successfully. Real SMTP/basic/multipart/search/sharing/ACL,
  replacement/history/retention, movement/recovery/cancel-folder and trash/purge smoke passes.
  Unique development demo metadata remains; aborted reservations retain normal deadlines.
- Remote CI still needs authorized push/dispatch; no GitHub rerun or production claim.
  Source schema021 and app settings UI are live. Scanner/worker services are restored.
  Readiness remains DB-only. Real worker hints completed the new quota turn; all seven
  stages are fresh. Overall storage health retains one deferred trash item while due_trash=0;
  retained capability/late-write deadlines remain enforced rather than clearing its evidence.
  CI now declares test Redis, real quota provider coverage, nginx receipt smoke and the
  dedicated zero-quota browser check; workflow YAML parses, but remote execution is pending.

## Limitations requiring explicit work

- L19/L04/L39 local quota scope is implemented and verified above. AI is
  not enabled: implement enforceable job/input/daily cost budgets before enabling21; billing
  entitlement/metering work remains25A.
- **L41 (new):** reference aggregates and paged inventory are conservative allocations and
  eventually observed provider evidence. A new external write can precede discovery; long
  bucket-wide multipart inventories, two-upload/1024-part bounds and old namespace evidence
  need production capacity/operating policy.26 verifies AWS pagination/parts/versioning/
  failure/late-write and known-reference reconciliation;27 reviews capability/abuse policy;
 28 adds stale/failed inventory, unresolved sizes and quota-reservation alerts with real
  failures/recovery;32 measures aggregate query/tenant-lock cost, page-cycle latency and
  fairness, implementing required indexing/admission/manifest extensions.20/L36 must compact
  safe zero-usage evidence without losing retained refs.25A must distinguish
  conservative allocation from invoice-grade physical usage and implement its metering.
- L15/Phase18 acceptance remains part of18+19; collaboration L10–L14/P01–P03 stays18A.
  L21/L36 audit/retention remains20; L39 scan policy/recovery/freshness/limits remains26/27/
 28/31/32; L40 realtime production/notification gates remain assigned. L01 remote CI needs
  separately authorized push/dispatch. D01–D08 are still intentional documented boundaries.

## Design discussion

Why sum references instead of maintaining a counter? Retained snapshots/intents are already
the cleanup source of truth. Recomputing under the tenant lock avoids counter drift across
worker crashes, idempotent retries, restore and failed provider calls; load must be measured.
Why charge history/trash/quarantine? Those bytes still exist and have costs despite being
hidden or unreleased. Why retain a cancelled reservation? A signed transfer may still finish;
cancellation alone cannot prove safe byte reclamation. Why separate policy from Tenant?
Storage plans belong to storage accounting and should not alter authentication identity or
couple old migration fixtures to new storage fields. See ADR-044.
