# Phase Reports

## Current implementation

- [Phase18A - Collaboration and groups](phase18a.md): source prepared; paired18A+20 acceptance pending. Running app remains021;022 unapplied.

## Latest completed phase

- [Phase19 — Storage Quotas](phase19.md) and [Phase18 — Realtime](phase18.md): combined
  local checkpoint passes to recorded scopes; source/app schema021. Full browser run had
  one invitation timeout with a passing isolated rerun; exact evidence and future gates remain explicit.

- [Phase 17 — Malware Scanning](phase17.md): locally verified exact-version quarantine,
  actual ClamAV/queue/provider/browser acceptance and application migration; commit cb85538.

- [Phase 16 — Redis and Background Jobs](phase16.md): maintenance queues, bounded stage
  rotation, operator backlog health and reference reconciliation/cancellation implemented;
  queued previews/static video posters, actual decoder/container/broker restart/prefork kill/
  real-clock recovery, PostgreSQL/local provider cleanup and Phase16-only browser checks pass.

- [Phase 15 — Bounded File Preview](phase15.md): unit/SQLite/frontend and container/native/live
  API/provider smokes pass; PostgreSQL/provider baseline passes 306 tests. Deferred browser
  acceptance is now complete: 22/22 Chromium journeys and 105 frontend tests pass after a
  shared-cache navigation fix. Lint/build and test-data cleanup pass.

Keep completed phase explanations in this folder, named `phase<N>.md`, such as
`phase2.md` and `phase3.md`. Added stages use lowercase suffixes, such as `phase2a.md`,
`phase2b.md`, and `phase25a.md`. Create a report for implemented work; do not create empty
placeholder reports. User-requested cadence (2026-10-16): author tests with each feature,
execute verification every two consecutive roadmap stages, including lettered stages.
An interim report must say implemented/verification pending, list unexecuted checks and
name its checkpoint. Neither phase is locally complete until assigned acceptance passes.

Current implementations: [Phase18 — Realtime](phase18.md) and [Phase19 — Storage Quotas](phase19.md).
The user explicitly requested19 ahead of18A; combined18+19 local verification is recorded.
Phase18A remains pending and must be revisited. Running app upgrade status is in CONTINUE.md.

Each report should explain what was built, why, architecture, important files,
technical concepts, request flows, security, test results, decisions, limitations,
and interview questions. Record verification gaps explicitly.

## Required limitation handoff for every phase

Every phase, including lettered follow-ups, must include a "Limitations requiring explicit
work" section. Link existing L/P/D IDs instead of duplicating their tasks. For each new gap,
record a stable ID, the missing behavior and impact, the exact implementation/verification
work, an assigned phase or release checkpoint, acceptance checks and current status/evidence.
Add new entries to [the shared backlog](../LIMITATIONS_BACKLOG.md), assign the work in
DEVELOPMENT_PLAN.md and carry the next action into CONTINUE.md in the same handoff.

Review inherited items too: close them only with evidence, keep future work visibly open,
and distinguish product decisions and intentional boundaries from fixable gaps. If no new
implementation gaps were identified, say so explicitly and list inherited open IDs. Never
use only "future phases will handle it" or treat a scheduled item as implemented.

Assigned limitation work is automatically included when development continues; the user
does not need to request each fix again. Unfinished assigned checks prevent phase completion.

## Completed Implementations

- [Phase 2 — Users and Organizations](phase2.md)
- [Phase 2A — Account Lifecycle and Email Delivery](phase2a.md)
- [Phase 2B — Multiple Organizations and Membership Lifecycle](phase2b.md)
- [Phase 3 — Folder System](phase3.md)

- [Phase 4 — File Metadata](phase4.md)
- [Phase 5 — Object Storage](phase5.md)
- [Phase 6 — Basic Upload](phase6.md)
- [Phase 7 — Basic Download](phase7.md)
- [Phase 8 — Chunked/Multipart Uploads](phase8.md)
- [Phase 9 — Resumable Uploads](phase9.md)
- [Phase 10 — File Search](phase10.md)

- [Phase 11 — Sharing](phase11.md)

- [Phase 12 — Permissions / RBAC](phase12.md)

- [Phase 13 — Trash and Restore](phase13.md)

- [Phase 14 — File Versioning](phase14.md)

- [Phase 14A — Version Transfers, Resume/Cancel and Pruning](phase14a.md)

- [Phase 14B — Core Library Movement and Recovery](phase14b.md)

Current cross-phase status and follow-up schedule: [Limitations backlog](../LIMITATIONS_BACKLOG.md). Older phase reports retain their historical implementation scope.

- [Phase18A � Collaboration and groups (source prepared; paired acceptance pending)](phase18a.md)
