# Phase 2B — Multiple Organizations and Membership Lifecycle

Completed and verified locally on 2026-10-14. Phase 3 remains unstarted.

## A. What we built

- Global accounts with multiple organization memberships and independent roles.
- Workspace listing, creation and explicit switching on the home page.
- Verified existing-account invitation acceptance without replacing their identity.
- Owner-authorized reactivation of removed memberships using a fresh invitation.
- Scoped removal that preserves access to other organizations and global account management.
- Password-protected, confirmed ownership transfer to a verified active member.
- Account deletion across all memberships, guarded by ownership in every organization.
- Migration preserving users/passwords/live sessions and revoked access; frontend cache/request isolation.

## B. Why we built it

File and folder schemas must depend on membership-based authorization rather than
the temporary one-organization-per-account model. A user can now own a personal
workspace and be a member or admin of a team without duplicating accounts or passwords.
Removing someone from one team no longer disables their other workspaces.

## C. Architecture

`users` stores global email, profile, credentials, verification, active/deleted state.
`memberships` identifies each `(tenant_id, user_id)` pair and stores role, join time
and revocation. Foreign keys reference the global user and tenant independently.
A partial unique index permits one active owner per tenant; service transactions
prevent removing the final owner. User response tenant/role fields are derived
from the authenticated membership, never stored as global authorization fields.

`login_sessions.tenant_id` binds a session to one workspace. The JWT tenant must
match that session and an active membership; roles are loaded from the database.
An account with no memberships can sign in with an account-only session and use
profile/security/recovery, accept an authorized invitation or create a workspace.
It cannot use organization resources until selecting an active membership.

Login selects the earliest joined active membership, ordered deterministically.
Switching revokes the current session and its refresh tokens, creates a replacement
for the selected membership, and preserves the absolute session deadline. Other
browser sessions keep their selection. Removal revokes sessions for that tenant
only. A revoked session remains revoked even if membership is later restored.

## D. Important files

- `backend/migrations/versions/004_global_identity.py`: identity/session migration and safe downgrade guard.
- `backend/app/models/user.py`, `membership.py`, `account.py`, `invitation.py`: global identity, roles, session tenant and reactivation.
- `backend/app/services/workspaces.py`: scoped listing, creation and session switching.
- `backend/app/services/organizations.py`: invitations, reactivation, roles/removal and ownership transactions.
- `backend/app/services/auth.py`, `accounts.py`, `api/deps.py`: membership/session validation and global deletion.
- `frontend/src/features/organizations/`: workspace controls, existing-account joining and ownership UI.
- `frontend/src/auth/AuthContext.tsx`, `services/api.ts`: query cancellation/cache clearing and stale-request rejection.
- `backend/tests/api/test_workspaces.py`, `tests/test_workspace_migration.py`: lifecycle/concurrency and real migration preservation.
- `frontend/e2e/workspaces.pw.ts`, `src/__tests__/WorkspaceSafety.test.ts`: real browser/email journeys and delayed-request safety.

## E. Technical concepts

**Identity versus authorization:** Email/password identify the person. Membership
identifies their permissions in a particular organization. JWT role claims are
informational; current membership supplies authority.

**Transactions and concurrency:** Organization management locks the tenant before
user rows. Multiple users/tenants are locked in stable order. Conditional membership
updates and a partial uniqueness index add protection against stale role changes.
Owner demotion and target promotion commit together; an intermediate state is not
published as a completed transfer.

**Browser isolation:** Switching cancels queries, clears cached data and changes
the session generation. Late protected responses are rejected. A shared refresh
cookie cannot cause an old workspace mutation to retry against a newly selected
workspace. Public verification/reset/recovery remains usable during session restoration.

## F. Request flows

1. An owner invites an email with an explicit member/admin role. Active membership
   duplicates are rejected; only an owner can re-invite a removed membership.
2. A new person creates an account and separately verifies their mailbox. An
   existing person signs in, verifies their address and explicitly accepts the token.
3. Acceptance checks token expiry/consumption, addressed email, current issuer
   authority and reactivation rules, then commits the membership and consumption.
   It preserves the person's other memberships. The UI explicitly switches afterward.
4. A workspace switch checks current session and target membership under the user
   lock, revokes this session, issues its replacement and clears frontend query state.
5. Removal marks the scoped membership revoked, revokes matching sessions/refresh
   tokens and affected invitations. Sign-in still permits other memberships or
   account-only management. A fresh owner-issued invitation can restore an explicit role.
6. Ownership transfer requires current password and literal TRANSFER, checks the
   verified active target, atomically replaces the owner and invalidates the former
   owner's pending invitations. The previous owner becomes an admin.
7. Global deletion requires verified email, password and DELETE, rejects ownership
   anywhere, then removes all memberships and revokes/redacts global account data.

## G. Security and privacy

An unrelated identity cannot list or switch to someone else's workspace. Changing
a token tenant while retaining another session ID is rejected even if the user
belongs to both organizations. Stale JWT roles cannot restore owner privileges.
Invite possession alone does not verify an existing identity, and public new-user
acceptance cannot replace an existing account/password. Membership revocation
persists as a tombstone so an old invitation cannot silently re-enable access.

Deletion retains a pseudonymous identity reference for integrity and clears personal
profile/recovery/access data according to the earlier retention policy. Already
delivered external mail cannot be recalled; no legal-compliance claim is made.

## H. Tests and results

- 92 backend tests passed on SQLite and PostgreSQL. PostgreSQL used the separate
  `cloudvault_phase2b_test` database; application data was never used for tests.
- Coverage includes different roles in two workspaces, switch/refresh revocation
  and absolute expiry, unrelated membership/session-tenant forgery, identity-bound
  acceptance, scoped removal, owner-only reactivation, stale sessions, ownership
  password/confirmation and global deletion ownership checks.
- Concurrent transfer versus transfer/removal/demotion preserves exactly one active
  owner; ordinary removal/demotion cannot remove the final owner.
- Seeded migration tests preserve password hashes, verified state and valid sessions,
  maintain revoked access for removed members and keep intact suspensions disabled.
  Unsafe downgrade refuses additional memberships and preserves their data.
- PostgreSQL Alembic upgrade/check/downgrade/re-upgrade passed; SQLite migration
  checks passed. Safe empty/single-workspace downgrade remains supported.
- 24 frontend component tests, ESLint, TypeScript/Vite build and Ruff passed.
- 9 Chromium journeys passed using migrated disposable SQLite and real local SMTP,
  including existing identity acceptance, switching, scoped removal/reactivation,
  revoked browser sessions staying revoked, creation, ownership transfer and deletion.
- Full Docker rebuild/start, real application migration to `004_workspaces`, schema
  alignment, HTTP checks and actual storage upload/read/delete passed. Actual Docker
  registration/SMTP verification and two-workspace create/list/switch with old-session
  revocation passed through the frontend proxy. Dispatcher runs; a uniquely named
  smoke account/workspaces remain as development test data.
- A pre-upgrade local development backup is ignored under `.local/backups/`.
  No push or remote CI dispatch was performed; Phase 2B remains uncommitted.

## I. Decisions and tradeoffs

ADR-017 documents global identities, membership tombstones and explicit workspace
sessions. ADR-018 documents atomic ownership and global deletion. Response compatibility
properties limit unrelated API churn while storing all actual roles on membership.
Switching replaces this session rather than changing the meaning of existing JWTs.
Migration preserves valid existing sessions instead of requiring every account to
sign in again. A lossy downgrade is refused rather than silently discard memberships.

## J. Limitations and operation

Run `docker compose up --build -d` and open `http://localhost:3000`. The currently
running development app is migrated. For direct setup, back up the database and run
`alembic upgrade head`. Restore a pre-upgrade backup if a downgrade cannot represent
the multi-workspace data safely. Do not point destructive test fixtures at app data.

Members/ownership candidates are paginated; use member pages to select a target.
Another tab's switch may require reloading/signing in to adopt the shared cookie;
full tab synchronization and real-time roster changes remain later work.
File/folder permissions, uploads/sharing and AI are upcoming phases.
Production SMTP provider verification, remote CI, MFA, broader abuse/security
review and deployment hardening remain pending. Community MinIO is archived;
production requires a maintained S3 provider/deployment decision. SMTP duplicates
remain possible after ambiguous acknowledgement, with account links single-use.

## K. Interview questions

**Why global users?** One identity can join multiple teams with different permissions
without duplicating credentials or disabling unrelated workspaces during removal.

**Why bind tenant to sessions?** An old token cannot acquire the meaning of a new
workspace. Current membership and session state are checked on every protected request.

**How do you avoid ownerless teams?** Tenant serialization, conditional updates,
one-owner uniqueness, authenticated confirmation and a single ownership transaction.

**Why retain revoked membership?** It records that access was explicitly removed;
only a fresh owner-authorized, identity-verified invitation can restore it.

**How do you prove migration safety?** Real seeded PostgreSQL/SQLite migrations,
password/session assertions and a guard that refuses incompatible downgrades.

Next phase: Phase 3 — Folder System, only on explicit instruction.
