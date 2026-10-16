# Phase18A — Collaboration completion and groups

Status: source implementation prepared2026-10-17; verification pending at18A+20.
The user explicitly chose groups in this phase. No test execution, lint/build, running-app
upgrade or deployment is claimed here. Migration022 has not been applied to the application.

## Implemented behavior

- Folder links expose a paginated current subtree, with current publisher membership,
  ownership/manager authority, every ancestor and local read ACL rechecked. New children may
  appear. Moving a file outside the root denies new downloads; moving folders/ACL changes,
  ownership changes and trash revoke affected links. Restore never unrevokes a link.
  Only current-policy released file entries are listed/downloadable; folder names are metadata.
  Publisher managers can read private content according to the existing explicit trust policy.
- Named recipient is a distinct optional link restriction. A password alone proves no identity.
  The specified email must match a live, active, verified CloudVault account/session; it can be
  an external account without workspace membership. The public UI sends bearer identity only
  after explicit opt-in, never cookies. Sign in in another tab, then reopen access. No email is
  sent, no workspace membership/write/AI access is created, and a link is still required.
- New UI creations send a cryptographically random256-bit token plus UUID request ID and keep
  them in form memory across ambiguous failures. The server stores only token/password hashes
  and an options fingerprint. Matching publisher/resource/options/password/secret retries return
  the same URL/expiry/record, including inactive status; mismatches return409. Revoked/expired
  records never revive. Reloading loses the retry secret; list responses never recover it.
  Legacy clients omitting the retry pair keep legacy non-idempotent creation semantics; new
  integrations must send both. Grant counters count URL issuance, never completed delivery.
- ResourceOwner overrides management authority without rewriting File/Folder.created_by,
  upload request identity, history attribution or provider keys. Transfers serialize with
  tenant mutations, require current verified target membership and ancestor reads, reject
  pending files, preserve explicit/group grants, and revoke resource/subtree links. Transfer
  is local, not recursive. Workspace managers can recover resources after owner departure;
  membership removal does not delete organization content. Former owners may still read via
  workspace visibility or another grant. No permission can bypass an inaccessible ancestor.
- Resource-authorized candidate lookup filters verified active current-tenant members by
  literal name/email substring before pagination. Grant rows include readable name/email even
  when the user is not on the current candidate page. No cross-tenant directory enumeration.
- Workspace managers create/delete groups and add/remove verified current members. Resource
  owners/managers grant a group viewer/editor access. Groups are a workspace-visible directory;
  group rosters/candidate administration require owner/admin. Group and direct grants combine:
  editor wins for local editing; owner/manager retains management; no deny rule, inherited
  editor, custom role, ownership or admin escalation. Group membership is cleared on departure.
  Group membership/grant/delete changes revoke affected links transactionally; future reads
  and WebSocket snapshots resolve current membership. Group directories/rosters poll15seconds.
- UI: folder Share entry, folder navigation/download pagination, named-recipient checkbox,
  retry form, member search/readable grants, local ownership transfer, group grant selector,
  /app/groups administration and Settings entry. Cache keys include user/workspace; group
  queries join protected-cache handling. Existing session coordination remains the authority.

## Authored acceptance, not executed

backend/tests/api/test_collaboration.py covers retry mismatches/revoked replay, named recipient
and wrong/unverified account, current subtree/new children/move-out/foreign paths, trash/restore,
provenance/transfer authority/ancestor/departure/search. It includes PostgreSQL-only concurrent
creation replay and transfer/member-removal checks. backend/tests/api/test_groups.py covers
manager/tenant boundaries, viewer/editor/private ancestors/no edit inheritance, removal/deletion
and permanent workspace-departure cleanup. Explicit fake storage and persisted successful verdict
fixtures isolate those service contracts; they do not certify the scanner/provider deployment.
backend/tests/test_collaboration_migration.py covers empty rollback and populated-state guards.
Updated React tests cover revised contracts; added group administration, retry/identity/folder
and group grant cases. frontend/e2e/collaboration.pw.ts authors desktop1280/mobile390 journeys.

At18A+20: run these and relevant inherited backend/React/browser/PG concurrency checks sequentially;
upgrade an owned disposable database, prove preservation on a fresh app backup, test actual
SMTP+scanner+private storage and nginx/session behavior, then record exact outcomes. Do not use
application data for destructive fixtures. P02/P03 scope is resolved: avatars22A and controlled external uploads/editing24A. Verify the implemented18A scope before final completion.

## Operation and limitations

Do not deploy unverified022 merely to mark the phase complete. After paired checks, back up the
running DB and apply migrations/rebuild.022 rollback refuses retained ownership overrides,
groups, folder/recipient/retry links. Old file links/provenance are preserved by upgrade.
External capabilities still allow already-issued storage URLs until expiry; received data cannot
be recalled. Named recipient proof protects grant issuance, not redistribution of received bytes.
Folder pages are current observations, not snapshots; filtered scan verdicts can produce short
pages. Group changes can revoke links for other publishers in affected subtrees, conservatively.
100 groups/workspace,1000 members/group,100 grants/group and25-entry pages/offset10000 are explicit
initial bounds, not measured production scale. L42 assigns cross-feature hardening26/security27,
alerts28 and representative limits/fairness32; audit events are due20. P01 groups are included,
with existing fixed roles. User resolved P02/P03 on2026-10-17: controlled external uploads/
editing in dedicated24A after24/before25, and bounded scanned avatars in22A. Both are
automatically required implementation/acceptance work at those checkpoints; neither is
implemented or supported now. Scope decisions are complete;18A verification remains pending. Existing D01–D08/L01/provider/security gates remain.
