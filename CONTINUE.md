# CloudVault - Current State

Current work: Phase18A source implementation prepared2026-10-17, including groups explicitly
selected by the user. Acceptance is PENDING at the combined18A+20 checkpoint. Source022 is
unapplied; the running Docker app remains021_storage_quotas. No tests/lint/build, Docker rebuild,
application migration, push or remote CI were run for18A; only source formatting.
The user subsequently requested a local checkpoint commit of18/19/18A. This commit
does not complete the pending18A+20 acceptance or apply022 to the running application.

Source: folder read links/current ancestry and publisher ACL/scan checks; named-recipient
verified email/live-session proof; client-secret/request-ID creation replay; separate resource
ownership preserving immutable upload/version attribution; authorized member search/readable
grant identities; manager-controlled groups with local viewer/editor grants. Ancestors always
apply. Workspace departure clears group memberships. Group/ACL/ownership/trash mutations revoke
affected external links; already issued storage URLs retain expiry. Bounds100 groups/workspace,
1000 members/group,100 grants/group,25/page,offset10000. No custom role definitions.

Read docs/phases/phase18a.md, ADR-045 and L42. L10-L14 remain acceptance candidates, not closed.
Authored API/PG race/migration/React/desktop/mobile coverage has not run. Keep heavy checks
sequential; use owned disposable DB/Redis/buckets, never destructive fixtures on app data.
Back up before022. Rollback guards retained ownership/groups/folder/recipient/retry link state.

Next implementation: Phase20 audit/metadata plus due L21/L36/L41, then paired18A+20 acceptance.
P01-P03 scope decisions are resolved2026-10-17: groups in18A; bounded scanned avatars
in22A; controlled external uploads/editing in dedicated24A after24 and before25. These are
automatically required checkpoint work, not current supported features. Preserve
the18/19/18A checkpoint work. Do not start20 without the user's continuation.

## Prior18+19 checkpoint and preservation record

Previous phase:19 — Storage Quotas, implemented and locally verified2026-10-17.
Phase18 realtime core also completed its combined18+19 local checkpoint. The later18A source/pre-acceptance status is recorded above.
Project: D:\CloudVault-Dev\Project\CloudVault. Source/running application schema021_storage_quotas.
Prior commits: Phase17 cb85538; Docker CI startup correction c3cf0ee.
The subsequent user-requested checkpoint includes18/19/18A; see git log for its identity.
No push, external CI dispatch or production deployment has been performed.

## Scope now available

Quota admission runs under the tenant write lock for new basic/multipart originals,
replacement versions and queued previews. Deduplicated bucket/file/object references count
current/history/private/trash/quarantine, pending/cancelled/expired reservations and retained
preview allocations. Completion does not add a second copy. No premature release on cancel/
expiry or cleanup failure. Unknown legacy sizes/failed inventory pause new allocations.
Existing reservations can complete after a plan reduction; reads/cleanup remain available.

StorageQuota is separate from authentication Tenant. Default Free10GiB/Team100GiB plans are
operator allocations, not billing. Confirmed backend DB-operator CLI changes plan/byte limit;
customers cannot self-upgrade. Verified managers see no-store aggregate usage in Settings.
No file names, private object refs or grant credentials enter usage responses.

The seventh storage maintenance stage discovers scoped objects and multipart orphans,
persists bounded inventory cursors/evidence and exact-rechecks absence. Observed bytes can
increase an existing bound; unknown/excessive manifests fail closed. Actual MinIO omits live
multipart uploads from directory Prefix listings, so discovery uses bounded bucket pages
followed by tenant filtering. No inventory deletion or atomic provider snapshot claim.
Preview jobs keep a conservative1MiB bound through ambiguous acknowledgements until cleanup.
See docs/phases/phase19.md, ADR-044, L19/L04/L39 and newL41.

Phase18: verified session-bound WebSockets, one-use first-frame Redis tickets, strict Origin,
fresh authority, own receipt progress, opaque current-view invalidations, reconnect/REST
fallback and cross-tab Web Locks/secret-free signals. Epoch/generation fences stop stale
scope. Role refresh remounts protected state; ownership confirmation survives via a scoped
secret-free navigation receipt. No durable notification history/replay. See phase18/ADR-042.

## Combined checkpoint — exact evidence

- Final focused PG/Redis/private-provider run:66 passed in44.91s. Final quota-only run after
  operator/1024-part-bound cases:16 passed in8.64s. Earlier targeted local backend51 passed.
- Initial broad SQLite run:385 passed,15 failed,20 skipped. All15 observed migration/recovery
  failures pass in the PostgreSQL rerun (171.63s) after storage policy isolation and a known-
  size legacy fixture correction. Do not call the original full backend run all green.
- Frontend125 tests, lint/build pass; backend and smoke/helper Ruff checks pass. Three
  scanner-readiness retry/deadline unit tests pass. The old workspace virtualenv lacked
  cryptography; tests used the already-installed working Python runtime without package changes.
- Full Chromium run:23 passed,1 invitation-click timeout. Isolated workspace rerun:2 passed
  in15.9s. Earlier browser memory failure was rerun sequentially after pausing project workers;
  no unrelated apps were closed. Dedicated zero-quota browser:1 passed in8.9s; denial creates
  neither a File nor a provider transfer. Actual Redis two-tab refresh/switch/offline cases pass.
  Legacy browser scanning/rendering fixtures are explicit dependencies, not engine certification.
- App schema upgrade preserves36 File,49 FileVersion,24 Tenant,31 User,14 UploadIntent and
  0 PreviewJob rows and creates24 quota policy rows. Before/after counts are under.local.
- Rebuilt UI/API/private S3/mc/application-adapter smoke passes. Actual nginx socket upgrade,
  own confirmed multipart receipts, retained cancelled quota and logout closure4401 pass in
  scripts/realtime_smoke.py. Direct container quota inventory checks2 refs. Real Celery storage
  hints execute the new quota turn successfully; all seven stages have fresh execution.
- Actual scanner freshness/broker/storage/worker readiness gate passes, then full real SMTP/
  basic/multipart/search/share/ACL/version/history/retention/move/recovery/cancel-folder/trash
  smoke passes. Unique development demo accounts/metadata remain; aborted uploads retain deadlines.
- Owned disposable PG database and labelled localhost-only Redis container/anonymous volume
  removed. Test bucket fixtures/teardown completed; .local/e2e-storage.json absent. App DB,
  bucket/volumes and existing data were never targeted by destructive fixtures.

## Operation and preservation

App: http://localhost:3000/app/settings (manager storage panel) and /app/folders.
Rebuild after future source changes: docker compose up --build -d.
Pre021 backup: .local/backups/cloudvault-before-phase19-20261017.sql (208310bytes), ignored.
Earlier backups remain. Back up before future migrations.021 refuses loss of custom policy,
positive/unknown inventory evidence or unmaterialized size bounds; earlier quarantine/version/
trash guards remain. Restore a coordinated backup if rollback cannot represent retained state.
Object backup/recovery remains separate. Never commit dumps, secrets or upload manifests.

Project scanner/workers are restored; WSL cap remains4GB. Run heavy checks sequentially.
Current normal worker health: email/previews/scans healthy, scanner definitions/provider
probed successfully. All7 storage stages fresh including quotas; overall storage reports
one deferred trash reference in its last pass while due_trash=0. Preserve original retained
capability/late-write deadlines; do not clear evidence or call deferred cleanup a byte purge.
API readiness remains DB-only. Operator health: python -m app.jobs.check_jobs; --job scans
--scanner includes private daemon freshness. This is not SMTP deliverability certification.
Docker startup initially failed; user started the engine. No resets, WSL unregister, volume
pruning, ACL rewrites, unrelated app closure or global configuration changes were performed.

## Next work and inherited limitations

- Prior next-stage assignment18A: L10–L14/P01–P03 collaboration/sharing/ownership/candidate lookup and explicit MVP
  decisions. After this user sequencing exception, continue actual development order with
  two-phase verification; next pair18A+20 unless the user directs otherwise. Write tests with
  every feature. Never infer completion from an assigned phase or skip a known safety defect.
- L15 local core passes; broader refresh-family/security remains27 and production/browser/
  proxy/load gates remainL40. Notification persistence decision is20, not an implemented inbox.
- L19/L04/L39 local retained-byte/reservation accounting passes. AI is not enabled: enforce
  real input/job/daily cost budgets before21. Billing/entitlements/metering remain25A.
- L41 automatically assigns evidence compaction/L3620, AWS inventory/namespace/late-write26,
  capability/abuse27, stale/failed/unresolved inventory alerts28, measured query/lock/cycle/
  fairness32 and invoice-grade metering decisions25A. Conservative allocated bytes are not
  a provider bill or instantaneous physical-byte total. Do not silently lift manifest bounds.
- L21/L36 audit/metadata retention20; navigation/search22A. L20/L22/L23/L25/L37/L38 actual AWS/
  lifecycle/decoder/deployment/recovery26/31, security27 and operational/load28/32 remain open.
- L39 retains100MiB/point-in-time scan coverage; pinned private scanner/AWS/recovery26/31,
  retroactive rescan/threat response27, freshness/updater/backlog alerts28 and limits/fairness32.
- L24 MFA/security27. L01 remote CI needs separately authorized push/dispatch. Community MinIO
  is local only; AWS selected but not provisioned/certified. D01–D08 received bytes/capabilities,
  SMTP ambiguity, serialization, delayed cleanup and guarded rollback remain explicit.

Standing instruction: ordinary continue includes every due limitation and acceptance task
without another request. Keep roadmap/register/report/handoff synchronized for new gaps.
No automatic commit/push, external spending or destructive application-data authorization.
