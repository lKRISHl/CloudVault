# CloudVault — Limitations and Closure Schedule

2026-10-17 sequencing update: the user explicitly requested19 ahead of18A. Phase19 quota
implementation/local acceptance passes to recorded scopes;18A remains pending and is the
next development step after this checkpoint, before20. L19/L04/L39 accounting acceptance
is being recorded in phase19; new quota/provider/load gates are L41. Earlier18+18A pairing
below is historical and superseded by this instruction.

Historical sequencing note 2026-10-16 (superseded above): Phase17 is locally verified and committed cb85538.
Phase18/L15 implementation and authored tests are present, but verification has not run.
User-requested cadence: execute acceptance after every two consecutive roadmap stages;
the next checkpoint is 18 + 18A before19. This allows 18A implementation while18 checks
remain pending; it does not close L15 or waive acceptance. Phase18 adds L40 below.

2026-10-16 update: the user resumed Phase 15's deferred verification; 22/22 browser journeys,
105 frontend tests, lint/build and cleanup pass. The navigation cache race found during
completion is fixed and covered. Phase 16 local scope also passes decoder/isolation, Redis restart,
prefork kill/real-clock recovery, PostgreSQL/local-provider cleanup and its dedicated browser
journey. The original full regression's four failures were resolved/retested; exact evidence
and the remaining host FFmpeg skip are recorded in docs/phases/phase16.md. 103 frontend tests
and lint/build evidence remain. L20/L25/L37/L38 production extensions keep their later checkpoints.
AWS S3 is selected (ADR-037).
The earlier sequencing exception is closed; all later assigned acceptance remains mandatory.

Reviewed 2026-10-15 against the phase reports currently present (2, 2A, 2B, 3–15),
CONTINUE.md, SECURITY.md and DEVELOPMENT_PLAN.md. Phases 0/1 are represented by the
roadmap/security notes; separate phase0/phase1 reports are not present. Selected current
code includes file moves/bounded previews; avatars are absent, readiness checks only the DB, and
refresh rotation does not yet implement the documented token-family replay response.
This is a documentation/scope reconciliation, not a new security audit or test run.

Historical phase reports describe their original implementation. Their "later" paragraphs
are not the live backlog. Use this register together with current CONTINUE.md instead.
Repeated limitations are consolidated; a feature mentioned by several phases has one owner.

"When" below means implementation order, not a promised date or effort estimate.
Open items stay open until the acceptance check has recorded evidence. Assigning a phase
does not implement or verify anything. Original phase numbers remain unchanged; lettered
follow-ups are additions. Phase 15's container/provider/browser checkpoint is locally complete.

## Execution order

1. Commit the already verified Phase 14 implementation separately from new implementation.
   Keep this planning update reviewable; it does not authorize a push.
2. Phase 14A: locally complete version transfers, resume/cancel and safe version pruning; L04 quota/audit integration remains 19/20. Evidence: [14A](phases/phase14a.md).
3. Phase 14B: close core library movement/trash recovery gaps. Finish before Phase 15.
4. Phases 15–18: safe previews, reliable jobs, scans and realtime synchronization.
5. Phase 18A: collaboration/sharing completion and explicit MVP scope decisions, before 19.
6. Phases 19–22: quota enforcement, audit/metadata retention, content processing/search.
7. Phase 22A: search/navigation and large-list pagination, before Phase 23.
8. Phases 23–25A: permission-aware RAG, API, webhooks and billing/entitlements.
9. Phases 26–33: execute compatibility/failure/security/operational/deployment/load/recovery
   gates. Earlier safety checks are still required when each feature is introduced.

The existing remote-CI gate is immediate, not postponed to Phase 30. It needs separately
authorized push/dispatch. Provider selection starts in Phase 16, before Phase 26 integration
certification. Production SMTP and storage verification must pass before public deployment.

## Earlier limitations already closed

- **R01 — One organization/account and incomplete ownership lifecycle:** Phase 2B adds
  existing-account invitations, workspace switching, ownership transfer, reactivation and
  organization-aware account deletion. Source: [2](phases/phase2.md), [2A](phases/phase2a.md),
  [2B](phases/phase2b.md). Cross-tab synchronization is still L15.
- **R02 — No real email/recovery/email change/session controls/invitation maintenance:**
  Phase 2A implements these locally, including encrypted outbox/dispatcher and technical
  maintenance. Production delivery and stronger recovery remain L26–L28.
- **R03 — Metadata without real transfers or verified size/checksum:** Phases 5–8 provide
  private storage, basic/multipart upload and checked native downloads. Sources: [4](phases/phase4.md),
  [5](phases/phase5.md), [6](phases/phase6.md), [7](phases/phase7.md), [8](phases/phase8.md).
- **R04 — No reload resume/expired or orphan transfer cleanup:** Phase 9 adds part-boundary
  resume and durable exact-key maintenance. This does not close version replacement resume
  (L03), production lifecycle verification (L20) or byte-level resume (D04).
- **R05 — No filename search:** Phase 10 adds scoped metadata search/indexes. Rich search
  and scalable navigation remain L16/L17/L18.
- **R06 — No password-protected external sharing:** Phase 11 adds expiring file links,
  passwords and grant limits. Folder/recipient/idempotency gaps remain L10–L12.
- **R07 — No private file/folder viewer/editor controls:** Phase 12 implements local grants,
  ancestor boundaries and filtered queries. Groups/resource ownership remain L13/L14.
- **R08 — No deletion/recovery/version history:** Phases 13/14 implement trash/restore,
  delayed confirmed purge and basic version history/restore. This does not close the
  explicit transfer/pruning/recovery additions below.

## Implementation and verification register

Each ID includes its source, assigned checkpoint and the evidence required for closure.

### Before Phase 15: core file/version completion

- **L01 — Remote CI has not executed.** Sources: roadmap immediate gate, every recent
  phase report. **When: immediate after separately authorized push/dispatch; do not wait
  for 30.** Close with a successful run tied to the tested commit, PostgreSQL migrations/
  concurrency, real disposable storage and Docker smoke. If authorization/credentials are
  absent, keep this explicitly open; local results do not replace remote evidence.
- **L02 — Large replacement versions are basic-only/full-buffer hashing.** Sources:
  [14 §J](phases/phase14.md#j-remaining-limits), [6 §J](phases/phase6.md#j-operation-and-limitations).
  **When: 14A.** Add bounded multipart replacement hashing/receipts/composite verification,
  select the appropriate transfer mode, preserve old current bytes and reject stale
  activation. Verify actual large/empty-file paths, lost acknowledgements and ACL races.
  **Closed locally in 14A:** actual multipart/empty replacement bytes, bounded hashing,
  missing receipts, lost create/complete ACKs, stale generation, revoked private authority
  and cancel/complete races pass. SQLite/PostgreSQL/provider/browser evidence: [14A §H](phases/phase14a.md#h-verification).
- **L03 — Version reload resume, progress discovery and explicit cancellation absent.**
  Source: 14 §J. **When: 14A.** Persist a secret-free manifest; reselect/validate original
  content, resume missing parts within the original deadline, and reconcile aborts/cleanup.
  Verify reload, changed file, workspace switch, revoked authority and abort/complete races.
  **Closed locally in 14A:** secret-free manifests/server discovery, original-file rejection,
  reload with missing-part-only transfers, stale-session guards, revoked authority and
  durable cancel/complete outcome verified; fixed deadlines and grace reconciliation pass.
  See [14A §H](phases/phase14a.md#h-verification). Cross-tab synchronization remains L15.
- **L04 — No version pruning/individual history deletion or bounded history policy.**
  Sources: 14 §D/J. **When: 14A core lifecycle; 19 usage reconciliation; 20 audit/metadata
  retention.** Add configurable retained-version rules and explicit deletion authority;
  never prune current content or unresolved authorizations. Commit intent before provider
  effects; retain exact retry refs, confirm absence, and verify restore/prune/trash races.
  Do not decrement retained usage just because a delete was requested.
  **Core lifecycle closed locally in 14A:** confirmed manual/policy pruning, current/older-
  restored-current protection, upload/download lease windows, restore/prune races, provider
  failure and retained-byte reclamation verified. **Still open:** Phase 19 aggregate quota/
  provider usage reconciliation and Phase 20 complete audit/metadata retention; per-file
  totals/minimal change events do not close those checks. See [14A](phases/phase14a.md).
- **L05 — Completed files cannot move between folders.** Sources: [4 §J](phases/phase4.md#j-limitations-and-operation),
  current files API (rename exists, move does not). **When: 14B.** Add file moves with
  source/destination/ancestor authority, conflict handling, share revocation and unchanged
  content/version keys. Verify cross-tenant, private-parent and concurrent move cases.
  **Closed locally in 14B:** immutable refs/share revocation, source/destination authority, expected-source concurrency and conflict rollback pass. Evidence: [14B §H](phases/phase14b.md#h-verification).
- **L06 — Trash restore only supports the original active parent/conflict-free name.**
  Source: [13 §J](phases/phase13.md#j-operations-and-limitations). **When: 14B.** Add explicit
  writable destination/name selection and safe conflict recovery, preserving batch boundaries,
  ACLs and versions. Verify name collisions, private destination, missing parent and rollback.
  **Closed locally in 14B:** chosen destination/name, active-parent/authority/depth/ownership checks, batch boundaries, collisions, rollback and restore/purge races pass. Evidence: [14B](phases/phase14b.md).
- **L07 — Pending original transfers block containing-folder trash.** Sources: 13 §J,
  9 §J. **When: 14B.** Add an explicit cancel-transfers-then-trash workflow with durable
  cleanup references and race checks. Do not bypass deadlines, silently abandon objects or
  claim immediate name/byte reclamation. Preserve the existing safe block until implemented.
  **Closed locally in 14B for tracked original File records:** confirmed atomic cancellation/trash, no activation after restore, creator/cap/race checks, actual late basic PUT and multipart cleanup pass. Original refs/deadlines remain; unmaterialized initialization-intent reconciliation is explicitly L37 in 16. Evidence: [14B](phases/phase14b.md).
- **L08 — Legacy metadata lacking an upload reference cannot be completed/reticketed.**
  Source: 6 §J. **When: 14B.** Provide an authorized remediation/discard path that never
  invents stored bytes or drops cleanup refs. Verify old-schema seeded rows and name reuse.
  **Closed locally in 14B for ordinary no-reference legacy rows:** authorized DISCARD, retained tombstone, old-schema preservation/guarded rollback and safe name reuse pass. Contradictory retained intent/version refs fail closed and are tracked separately as L37. Evidence: [14B](phases/phase14b.md).

### Previews, jobs, collaboration and security boundaries

- **L09 — Unscanned bytes, untrusted declared MIME, no safe inline preview.** Sources:
  6/7/14 §J. **When: 15 safe bounded preview/detected-type handling; 17 quarantine/scanning.**
  Verify hostile/oversized inputs, restricted rendering, ACL checks for derived artifacts,
  fail-closed scan/release states and no inference that attachment/octet-stream means safe.
  **Phase 15 local checkpoint complete:** verified-source transient text/static-PNG previews, bounded native
  renderer configuration, live authority/version rechecks and unit/SQLite/frontend checks
  exist. Actual container restrictions/native PNG/PDF and live API/provider current/history
  smokes pass. PostgreSQL/provider baseline passes all 306 tests. Final browser rerun passes
  22/22, with 105 frontend tests/lint/build and disposable cleanup complete. A navigation cache
  race found during the resumed run was fixed with two late-response regression tests.
  **Phase 17 local checkpoint complete:** exact-version quarantine, verified streaming hashes,
  real ClamAV/queue detection/release, guarded backfill, browser status/retry and existing app
  rescans pass. See [17](phases/phase17.md). Explicit scan size/coverage/retention/rescan and
  production deployment extensions are L39; video/job expansion remains L38.
- **L10 — Sharing covers files only; no folder links or recipient editing/upload.**
  Source: [11 §J](phases/phase11.md#j-operations-and-limitations). **When: 18A folder-read
  sharing; editing/upload remains decision P02.** Verify subtree/current-ancestor boundaries,
  moves, revocation, new children and indirect disclosure before enabling folder links.
- **L11 — Forwardable capability links do not verify a named recipient.** Source: 11 §J.
  **When: 18A.** Add a distinct named-recipient flow with actual identity proof and current
  permission enforcement. Keep anonymous capability semantics explicit; a password is not
  proof of recipient identity. Test forwarding/wrong account/revocation/recovery.
- **L12 — Share creation is not idempotent; ambiguous replies can create uncertainty.**
  Source: 11 §J. **When: 18A.** Bind creation request IDs to publisher/file/options and return
  a well-defined replay without weakening one-time raw-secret handling. Test lost replies,
  changed options and concurrent retries. Grant counting remains D02.
- **L13 — No per-resource ownership transfer.** Source: 12/current CONTINUE limits.
  **When: 18A.** Define file/folder transfer authority, verified target membership, ancestor
  boundaries, version provenance and link/grant consequences; test departure/transfer races.
- **L14 — Member/grant candidate lookup requires paging; absent names show UUIDs.**
  Sources: [2B §J](phases/phase2b.md#j-limitations-and-operation), [12 §J](phases/phase12.md#j-operations-and-limitations).
  **When: 18A UX; 22A common pagination.** Add tenant-authorized lookup/search and accessible
  selection without enumerating private/foreign identities. Groups/custom roles are P01.
- **L15 — Cross-tab workspace/refresh coordination and realtime roster/ACL/cache acceptance.**
  Sources: 2A/2B/9/12 §J. **When: 18 client/realtime; 27 refresh-security verification.**
  Coordinate shared-cookie changes and refresh ownership, reset scoped caches, reconnect
  safely, and stop stale writes. Verify multiple tabs, logout, removal and rapid switches.
  Previously received bytes/metadata cannot be remotely erased (D01).
  **Source implemented in18; verification pending:** first-frame one-use tickets, fresh
  session/membership/resource checks, bounded current-state observation, reconnect/REST
  fallback, own receipt counts, Web Locks and secret-free shared-cookie change signals.
  Execute real Redis/nginx/PG/browser multi-tab logout/removal/ACL/rapid-switch/worker-change
  and receipt cases at the user-directed combined18+19 checkpoint. Local core passes:
  actual Redis ticket/lease, nginx receipt/logout smoke, cross-tab/offline browser cases
  and PG authority tests. Broader refresh-family security still belongs27.
  Unsupported Web Locks/privacy configurations and production scaling remain L40.
- **L16 — Filename search lacks recursive scope, fuzzy/accent-normalized matching and tags.**
  Source: [10 §J](phases/phase10.md#j-operations-and-limitations). **When: 21 tags; 22A lexical
  search/navigation.** Define search semantics and preserve resource/ancestor predicates
  before page/count/context computation. Test deep private hierarchies and index plans.
- **L17 — No extracted-content/semantic/AI search or RAG.** Sources: 4–14 later-work notes.
  **When: 21 extraction, 22 semantic retrieval, 23 RAG.** Verify current permission checks on
  source/derived chunks/citations, deletion/version invalidation and prompt-injection bounds.
- **L18 — Offset paging is bounded, shifts concurrently and has no global total/snapshot.**
  Sources: 10/12/14 §J; 3 list bounds. **When: 22A common cursor/keyset strategy, scoped counts
  only where useful; 32 workload verification.** Cover files/search/history/large membership
  lists. Define consistency rather than promising an immutable snapshot or unlimited paging.
- **L19 — Aggregate storage reservation/quota acceptance and later cost/entitlement integration.** Sources: 6/8/14 §J.
  **When: 19; billing entitlements 25A.** Count current/history/trashed bytes once, pending
  reservations and unknown/orphan reconciliation separately; enforce concurrent limits and
  safe downgrade/over-quota behavior. Add bounded AI budgets before enabling AI in 21,
  then integrate subscription metering in 25A.
  Source implemented19: locked retained-reference admission, plan/limit policy, own original/
  replacement reservations, history/trash/quarantine, conservative preview bounds and bounded
  provider inventory. Unknown sizes and failed reconciliation pause new allocations. Manager
  usage and explicit DB-operator plan changes pass local acceptance in phase19, including PG
  concurrent admission, real object/part evidence, migration guards and zero-quota browser denial.
  See phase19/ADR-044. AI budgets remain a mandatory pre-enable21 gate; billing25A and L41
  production capacity/provider/operational verification remain open.

### Durable maintenance and production-provider evidence

- **L20 — Provider lifecycle/orphan inventory and real waiting-period behavior unverified.**
  Sources: [9 §J](phases/phase9.md#j-operations-and-limitations), 8/14 lifecycle notes.
  **When: 16 reliable job/provider-lifecycle design; 26 failure and real-clock tests;
  31 deployed provider verification.** Preserve durable exact-key intents, inventory cursors
  and late-write refs; verify provider abort/delete retries and configured stale expiry/scan
  timing. Local injected time does not establish a 24-hour provider lifecycle guarantee.
  **16 local scope complete:** actual broker restart, prefork kill, real four-minute lease
  recovery, six-stage progress, bounded two-tenant cleanup and retained late-write retry pass.
  Long provider lifecycle windows and AWS failure/load evidence remain 26/31.
- **L21 — Hidden tombstones, intents, revoked links, grants and change metadata grow.**
  Sources: 9/11/12/13/14 §J. **When: 20 technical/audit retention implementation;
  27 privacy/security review; 33 operational policy sign-off.** Classify retention purposes,
  compact only when safe, and test that no live authorization, late-write cleanup identity
  or restoration proof is lost. Content pruning is L04; legal erasure is L35.
- **L22 — Community MinIO is local-only/archived; AWS S3 selected, not yet certified.**
  Sources: 2A onward. **When: select in 16, certify in 26/31 before public deployment.**
  Record maintained S3/R2/provider choice and test checksums/composite HEAD, conditional PUT/
  completion, pagination, public signer endpoints, clock/credential expiry and abort/delete.
  Local MinIO results are not evidence for another provider.
  User selected AWS S3 on 2026-10-16 (ADR-037). Provider selection is recorded; actual AWS
  compatibility/configuration and release certification remain open in 26/31.
- **L23 — No provider VersionId purge or protection against out-of-band overwrite/delete.**
  Sources: 5/7/9/13/14 §J. **When: 16 explicit provider/versioning decision; 26/31 enforce
  and verify selected policy.** Default release policy remains unversioned immutable app keys.
  If enabling bucket versioning, implement and test exact VersionId/delete-marker lifecycle
  for every upload/prune/trash/orphan path first. Otherwise detect/refuse Enabled/Suspended
  configuration and document independent object-backup controls; do not promise unused
  provider-versioning support. Administrator-resistant object locking is decision P04.
- **L24 — Production IAM/encryption/public-access/CORS/TLS/lifecycle not verified.**
  Sources: 5/6/9 §J. **When: 27 policy/security review; 29 config; 31 actual provider checks.**
  Use exact origins/private buckets, scoped application versus maintenance permissions,
  credential/clock handling and secret rotation. Close with denied-public-access and real
  transfer/purge tests on the chosen configuration, not configuration snippets alone.
- **L25 — Readiness is DB-only; worker-running state does not prove storage/cleanup health.**
  Sources: 5/6/9 §J; current health API. **When: 16 job health/backlog semantics; 28 dependency
  probes/alerts.** Define feature-aware readiness and bounded non-destructive S3/Redis checks,
  appropriate degraded responses, cleanup age/error alerts and tests for dependency failure.
  Phase 16 now records durable rotation, provider-bound cursors, individual stage failures/
  deferred work, aggregate backlog counts/ages and operator Redis/bucket/versioning checks.
  Initialization intents are labeled recheck populations, not orphan-byte counts. None of
  these establish backlog completion or per-effect success. Live stage fairness/broker-loss/
  restart/PG/local-provider proofs now pass in Phase 16; API feature gating/alerts remain 28;
  see docs/phases/phase16.md. AWS/provider expansion remains 26/31.
- **L26 — Production SMTP transport/domain/TLS/delivery failures not verified.**
  Sources: 2A/2B §J. **When: 28 delivery monitoring, 31 actual provider verification before
  customer mail.** Test configured sender/domain/transport, failure/retry behavior and alerting.
  Keep generic recovery and single-use links. Ambiguous SMTP ACK duplicates remain D03.

### Hardening and release gates

- **L27 — MFA, inaccessible-mailbox recovery and legacy-account support policy absent.**
  Source: [2A §J](phases/phase2a.md#j-limitations-and-operation). **When: 27, before public
  release.** Implement MFA enrollment/challenge/recovery/revocation and safe recovery codes;
  define support proof/audit rules for inaccessible addresses without bypassing verification.
  Test lockout, lost factors, ownership abuse and session invalidation.
- **L28 — Refresh rotation lacks explicit token-family compromise response.** Sources:
  2A §J/SECURITY.md; current auth service. **When: 27, with 18 cross-tab coordination.**
  Detect replay and revoke the appropriate session/family while defining legitimate
  concurrent-tab behavior. Verify replay, logout, password recovery and race cases.
- **L29 — Production rate/abuse/proxy/CPU/timing protections need review.** Sources:
  2A/6/8/11/14 §J. **When: 27; tune with measured 32 workloads; final 33 gate.** Cover trusted
  proxies/IP identity, malformed requests before budgets, recovery timing under load,
  password hashing/public-capability CPU cost, per-link/IP group fairness and per-tenant
  transfer/AI limits. Existing configured limits are not abuse certification.
- **L30 — No independent broader security assessment or deployed threat-model evidence.**
  Sources: completed reports/SECURITY.md. **When: 27; final release check 33.** Review auth,
  IDOR/tenant isolation, SSRF, uploads/previews/AI and secrets; resolve release blockers and
  record residual risks. Arrange independent review where required; self-tests do not count
  as independent assessment.
- **L31 — Safari/Firefox, provider outages and recovery/concurrency matrix not certified.**
  Sources: 7 §J, 14 §H/J. **When: 26; actual deployed configuration recheck 31/33.** Run
  browser/provider-specific transfers, versions/resume/sharing, partitions, lost ACKs,
  retries, partial migrations and rollback/restore drills using disposable data.
- **L32 — Observability, signed/query/body log redaction and retention incomplete.**
  Sources: 10/11/12/14 notes. **When: 20 audit events; 27 redaction policy; 28 logging,
  metrics/traces/alerts.** Verify secrets/URLs/passwords/document content are excluded,
  sensitive search/body fields follow policy and storage/SMTP/job failures trigger alerts.
- **L33 — Tenant writes serialize; search/ACL/deep hierarchy/history performance unmeasured.**
  Sources: 2/3/8/10/12/14 notes. **When: 26 initial profiling/timeouts; 32 representative
  workloads/optimization; 33 accepted targets.** Measure actual lock wait, common/short-term
  search plans, index/migration cost, worker fairness/backlog and large-grant/version sets.
  Optimize from evidence; synthetic index checks are not throughput benchmarks.
  Phase 14B adds the 100-pending cancellation bound and full subtree restore-height/ownership
  traversal to these workloads; destination lists remain pages of 25.
- **L34 — Production images/configuration, complete CI/CD and hosted services absent.**
  Sources: roadmap 29–31 and prior deployment gates. **When: 29 container/resource/config
  hardening; 30 repeatable build/test/security/deployment pipeline; 31 HTTPS/domain/secrets/
  managed services.** Separate local 4 GB WSL constraints from deployed capacity. Remote CI
  evidence remains immediate L01, not deferred behind this pipeline work.
- **L35 — Paired DB/object backup restore, deletion policy and incident runbooks unverified.**
  Sources: 5–14 rollback/retention notes. **When: 26 restore/failure tests; configure in 31;
  full timed drills/policy acceptance in 33.** Restore metadata and matching objects/versions,
  choose recovery targets and measure results; define rollback after irreversible migrations,
  legal/privacy retention, availability/cost/incident procedures. A local SQL dump alone does
  not close this item or establish compliance.
- **L36 — Download grants are not completed-delivery telemetry.** Sources: 7/11 §J.
  **When: 20 explicit grant/audit events; 28 provider-log telemetry evaluation.** Label
  attempted/issued/provider-observed events honestly, reconcile missing/duplicate signals
  where supported and never equate a grant or native browser handoff to completed delivery.

## Product-scope decisions with a fixed review point

These are absent capabilities, not silently promised enterprise features. At the checkpoint,
record an explicit include/exclude decision. If included, add implementation/acceptance work
before claiming support; if excluded, document the boundary for the resume demo/MVP.

- **P01 — Groups/custom resource roles:** decide in **18A**; existing workspace roles plus
  viewer/editor grants remain supported. Include permission precedence, membership lifecycle
  and ancestor semantics in any design. Source: 12/current limits.
- **P02 - Controlled external uploads/editing:** user approved dedicated **24A** on2026-10-17, after24 and before25. Automatically implement scoped verified-recipient guest writes, current ACL/ancestor checks, quotas/scanning/version lifecycle, revocation, idempotency, audit and abuse controls with actual acceptance. Anonymous read links remain read-only; no current guest-write support is claimed. Source:11 and18A.
- **P03 - Profile avatars:** user approved **22A** on2026-10-17. Automatically implement bounded scanned image upload, safe decode/re-encode, account/tenant privacy, quota inclusion and replacement/deletion/orphan cleanup, with malformed-image/security and lifecycle tests. Full-name-only profile remains supported until this work passes acceptance. Source:2 and18A.
- **P04 — Provider object lock/version pinning and strict one-use/immediately revocable
  download access:** decide provider requirements in **16** and delivery architecture in
  **27**, before release. Strict revocation/one-use semantics need a separately designed
  mediation/delivery model and tradeoff review; ordinary presigned URLs cannot acquire them
  through a UI change. Sources: 5/7/11/14.

## Intentional constraints and unavoidable semantics

- **D01 — Received bytes/metadata cannot be recalled.** Phase 18 prevents new stale views/
  requests where possible; it cannot erase another person's saved data. ACLs remain current
  authorization boundaries; trusted managers' private access and required ancestor reads
  are explicit policy, not unfinished bugs.
- **D02 — Presigned URLs are reusable until expiry; link passwords/capabilities can be
  forwarded.** Issued-grant counters may advance on a lost response and are not delivery
  counts. Phase 27 reviews TTL/policies; P04 decides any alternative architecture. Public
  share page intentionally forgets its fragment on reload; reopening the full link is
  currently required rather than persisting a bearer secret in browser storage.
- **D03 — SMTP acknowledgement can be ambiguous.** Single-use account actions avoid repeated
  effects, but exactly-once email arrival cannot be guaranteed. L26 verifies provider
  behavior/monitoring without promising that duplicates become impossible.
- **D04 — Transfer limits/deadlines, original-file reselection and part-boundary resume are
  deliberate bounds.** Default 100 MiB basic, 1 GiB multipart/8 MiB parts/1024 parts/one hour;
  configured ceilings and grace remain documented. No automatic deadline extension or
  within-part byte resume is promised. L02/L03 extend versions; 32 validates/tunes bounds.
- **D05 — Depth 64/page caps and tenant serialization protect current correctness.** L18/L33
  address navigation/scaling from measurements; no unlimited hierarchy/page/throughput claim.
- **D06 — Cleanup waits original expiry/grace/settle and provider confirmation.** Names/bytes
  need not free immediately after cancellation/purge; queued purge is irreversible. L20/L25
  make maintenance reliable/observable, not instantaneous or guaranteed at an exact time.
- **D07 — Guarded downgrade and organization-owned content retention are protective policy.**
  Creator departure/account deletion does not erase shared organization content. Old schemas
  may not represent current memberships/ACLs/trash/version refs. L21/L35 define safe retention
  and paired recovery rather than removing guards or claiming total metadata/legal erasure.
- **D08 — Native download errors/progress belong partly to the browser/provider.** L31 tests
  compatibility and retry; L36 labels telemetry. Shared Windows/system temporary files may
  still use C: despite project/Codex/Docker data living on D:. These are documented platform
  boundaries, not file-storage feature failures.

## Newly tracked in Phase 15

- **L38 — Queued previews/static video posters require live certification.** Source:
  [15 §D/E/J](phases/phase15.md#j-limitations-requiring-explicit-work). Phase 15 preview was
  transient UTF-8/static PNG with a 10 MiB source cap; video/unknown formats use an explicit
  authorized download fallback. **When: 16 bounded isolated video/poster jobs, retries and
  version-aware publication/invalidation; 26 chosen-provider/browser/failure validation;
  27 decoder/isolation security review.** Preserve limits/unsupported states; test malformed,
  oversized, cancellation, stale generation, live ACL/ancestor/prune/trash races and worker
  failures without publishing stale content. Record actual container resource/isolation and
  provider evidence. Production job/backlog monitoring is L25; load is L33. Direct Windows
  APIs require a deliberate isolated native-renderer deployment, never unsafe host fallback.
  This work is automatically included at those checkpoints. The original Phase 15 scope was
  transient; Phase 16 extends it below. Full video playback and scan certification are not claimed.
  **Implemented in source during 16:** durable version/requester/generation-bound jobs,
  private S3-only UTF-8/PNG results, three-attempt leases/recovery, publication/read authority
  rechecks, explicit cancellation and retained late-write cleanup. Static MP4/WebM posters
  use credential-free isolated FFmpeg with protocol/codec/duration/pixel/time bounds;
  no moving playback is claimed. Migration 019 preserves cleanup refs/guards downgrade.
  127 targeted backend checks pass with one real-video skip; 103 frontend tests/lint/build
  pass. Actual isolated FFmpeg decode, Redis/prefork recovery, PG/local-provider cleanup and
  the dedicated Phase 16 browser journey now pass. Ordinary host FFmpeg remains unavailable;
  the actual decoder proof is inside the container. AWS expansion stays 26 and security review 27.
  Derivative/reserved/ambiguous-write accounting is explicitly L19 in 19; retained job/ref
  metadata policy is L21 in 20. See ADR-040 and docs/phases/phase16.md for bounds/evidence.

## Maintenance rule

Standing user instruction: assigned limitation work is mandatory phase scope. When the user
says "continue", automatically read this register, work on all due L items and P decisions
alongside the next scheduled feature, run their acceptance checks and update the evidence.
No separate "fix this limitation" request is needed. Do not mark the phase complete or
advance past unfinished assigned checks. Complete independent authorized work around external
dependencies; keep affected items open and report the actual blocker/next action. Request
only genuinely missing decisions, credentials or separately authorized external/destructive
actions. Existing scope needs no repeat approval. This is active-development guidance, not
background execution or authorization to push/deploy/spend/delete data. D constraints remain
explicit design boundaries, not automatically fixable promises.

Every new phase report must list the relevant L/P/D IDs, evidence for items it closes,
new limitations with an assigned checkpoint, and any explicitly accepted design boundary.
Include a "Limitations requiring explicit work" section for every numbered or lettered
phase. Every new gap needs a stable ID, missing behavior/impact, concrete implementation or
verification task, assigned phase/checkpoint, acceptance checks and status/evidence. Update
this register, DEVELOPMENT_PLAN.md and CONTINUE.md together. If no new gaps are identified,
state that and still review inherited open IDs. The report format is in docs/phases/README.md.
Do not replace this register with "later phases will handle it." At Phase 33, no release-
blocking L item may remain unexplained; P decisions must be recorded. Deferred optional
features are not completed features. Any reproducible security/data-loss defect discovered
while implementing these tasks is fixed before proceeding, regardless of its planned phase.

## Newly tracked in Phase 14B

- **L37 — Contradictory legacy metadata with retained provider intent/version refs requires operator reconciliation.**
  Source: [14B §D/J](phases/phase14b.md#d-cancellation-and-legacy-state). Ordinary pending rows
  with no upload reference can be safely discarded. If a retained intent/snapshot contradicts
  that legacy state, discard/cancel-trash fails closed rather than deleting evidence.
  **When: 16 diagnostic/job reconciliation; 26 chosen-provider verification before public release.**
  Add an authorized operator path that enumerates all retained refs/deadlines, safely adopts or
  proves cleanup, and then retires metadata without inventing bytes or losing retries. Test
  lost acknowledgements, changed bucket/provider errors, late writes and authorization. This
  follow-up is automatically included when continuing those phases; current safe refusal remains.
  Before Phase 16, initialization intents without a materialized File row were outside the
  folder's tracked pending-record cancellation list. Phase 16 adds folder-scoped discovery/
  cancellation and stale initialization-retry invalidation after trash/recovery, preserving
  every original deadline/ref.
  **Implemented in source during 16:** retained folder/scope/cancellation, subtree intent
  cancellation with manager/cap checks, stale-retry invalidation and fail-closed historical
  unknown scope. DB-operator diagnostics page all refs; explicit confirmed multi-pass
  retirement waits all deadlines, aborts/deletes/checks absence and retains exact keys.
  Completed snapshots can be adopted after active owner/admin and verified provider checks,
  using normal version activation/share invalidation/history. Migration 018 preserves old
  unknown scope and guards lossy rollback. See ADR-039/phase16 report for local evidence;
  actual PG/local-provider lost-ACK/late-write checks pass. AWS certification remains 26/31.
## Newly tracked in Phase 17

- **L39 — Bounded antivirus coverage, quarantined retention and operational release gates.**
  Source: [Phase 17](phases/phase17.md), ADR-041. Default/maximum supported scan input is
  100 MiB; larger uploads stay quarantined. Definitions can miss threats and supported
  formats/archives have conservative bounds. Successful scan is a point-in-time result;
  signature updates do not automatically rescan previously released versions. No manual
  override converts blocked/oversized content to clean. Prior signed URLs retain expiry.
  **When: 19** account for every retained quarantined byte/reservation in quotas;
  **26/31** verify chosen AWS provider, pinned maintained scanner images and private network/
  signature-update deployment, backup/restore and outstanding capability rollout;
  **27** review detection/format/size policy, retroactive rescanning/threat response and
  released-content revocation; **28** monitor definition freshness, unavailable scanner,
  oldest pending/failed scan, quarantine counts and signature-updater failures;
  **32** measure memory/CPU, queue delay/fairness and throughput with representative objects,
  then record the supported production scan-size/service limits. These are automatically
  required work when continuing those phases; they are not closed by installing ClamAV.

## Newly tracked in Phase 18

- **L40 — Realtime observation capacity, durable notification policy and deployment matrix.**
  Source: [Phase18](phases/phase18.md), ADR-042. Current bounded DB observations coalesce
  transitions, have no durable replay/inbox and incur reads per socket/subscription.
  Defaults permit eight paged views/socket, four sockets/user, 64/IP/process and three-second
  observation; none is a measured production capacity. Redis leases assume standalone Redis.
  ASGI peer-IP limits require a trusted production proxy topology. Without Web Locks,
  competing refreshes can safely fail closed instead of transparently adopting the session.
  **When20:** decide/record whether durable user notifications are in scope; if included,
  implement tenant-authorized persistence, retention/read state and replay/idempotency tests.
  Audit history alone is not a user notification inbox. Explicit exclusion is a product
  boundary, not an implemented inbox. **26:** prove actual nginx/TLS upgrade, Redis restart,
  multi-process lease caps/expiry, slow clients, offline fallback and supported browser/privacy
  combinations; implement fixes and document any unsupported deployments before release.
  **27:** review Origin/ticket replay/expiry, session changes, proxy spoofing, denial of service
  and strict current authority. **28:** implement secret-safe connection/reconnect/fallback,
  failed lease and observation-latency/error metrics and verify actionable alerts on real
  failures/recovery. **32:** measure many tenants/tabs/pages under representative DB/fanout
  load, report latency/fairness/resource limits and implement required admission, cadence or
  event-fanout changes. No invented performance claim or assumption that a Redis restart is
  durable event delivery. Current status: implementation bounds only; these gates remain open.

## Newly tracked in Phase19

- **L41 — Conservative allocation, eventual provider evidence and production quota capacity.**
  Source: [Phase19](phases/phase19.md), ADR-044. Known references/reservations are enforced
  atomically; external writes and unknown provider overhead are discovered by bounded paged
  inventory, not a simultaneous physical-byte snapshot. Preview allocation retains its1MiB
  worst-case bound until cleanup. Local MinIO needs bucket-wide multipart discovery with
  tenant filtering; long inventories and many tenants can delay reconciliation. Two upload
  IDs/1024 parts per key are supported; excessive/unknown manifests pause new admissions.
  Changed/failed namespaces require explicit reconciliation, not deletion of old evidence.
  **26:** prove actual AWS object/multipart pagination, lost acknowledgements/late writes,
  supported versioning/refusal, namespace changes and known-reference cleanup. **27:** review
  presigned-capability/abuse and operator access policy. **28:** implement stale/failed inventory,
  unresolved-size and reservation/over-quota alerts and test real failures/recovery. **32:**
  measure aggregate SQL/tenant-lock cost, manifest bounds, cycle latency and tenant fairness;
  implement justified indexes, admission or inventory extensions and document measured limits.
  **25A:** implement the chosen billing metering, explicitly distinguishing conservative
  allocation from provider invoice bytes. AI budgets stay a mandatory pre-enable21 condition.
  These tasks are automatically included in their checkpoints. No production scale or exact
  physical-byte billing guarantee is implied by the current local implementation.
  **20/L36:** define/implement safe zero-usage evidence compaction without discarding live
  cleanup or namespace/reconciliation references. Local19 evidence does not close these later gates.


## Phase18A follow-through (2026-10-17)

L10�L14: source implementation candidates now exist; none is closed before paired18A+20
acceptance. See [phase18A](phases/phase18a.md) for exact scope, legacy retry-client semantics,
new authored tests and operation boundaries. P01 groups were explicitly included by the user;
fixed viewer/editor roles are implemented. P02/P03 were explicitly resolved2026-10-17: controlled external uploads/editing24A and
bounded scanned avatars22A. Those checkpoints automatically own implementation/acceptance;
no current external write or avatar support is implied.

- **L42 � Collaboration acceptance and initial group/directory limits.** Source:18A report.
  **When:18A+20 local checkpoint;26 deployment compatibility;27 independent security;
  28 feature-aware alerts;32 measured query/lock/invalidation/fairness limits.** Prove actual
  recipient identity/session, lost-response/concurrent replay, ownership provenance, private
  ancestors, current subtree moves/trash/restore, direct/group precedence and permanent
  departure cleanup. Initial100 groups/workspace,1000 members/group,100 grants/group,
  pages25/offset10000 and15-second group-directory polling are explicit unbenchmarked bounds.
  Keep pending acceptance separate from verified claims. Audit share/group/ownership events
  in20; URLs remain reusable until expiry and received bytes cannot be recalled (D01/D02).
  Legacy share-create clients must adopt request-ID/client-secret pair for retry guarantees;
  form reload intentionally does not recover raw secrets. Consider public API contract24.
