# Phase 2 — Users and Organizations

Implementation and local verification completed on 2026-10-13. Docker/PostgreSQL runtime verification remains pending CI. Phase 3 has not started.

## A. What we built

Users can read their profile and change their full name. Every authenticated user can view their organization and its paginated roster. Owners and admins can rename the organization, create private invitations for new accounts, list pending invitations, and revoke invitations. Owners can assign admin/member roles. Owners can remove non-owner members; admins can remove ordinary members only.

Invited people follow a private link, choose their own name/password, and join the inviting organization. The application does not send email. Removing a member disables their account and invalidates its membership and refresh tokens.

## B. Why we built it

Authentication identifies a person; organization membership determines the workspace they may use and which management actions they may perform. This phase turns an isolated owner account into a usable team workspace while keeping another organization's users and membership IDs inaccessible.

Invitations provide a real membership onboarding path. Managers do not choose another person's password or silently move an existing account into their organization.

## C. Architecture

```text
React settings / invitation screens
        |
Typed API client + in-memory access token
        |
FastAPI routes + authenticated-user dependency
        |
OrganizationService / AuthService
        |
SQLAlchemy session and transaction
        |
PostgreSQL: tenants, users, memberships, invitations, refresh_tokens
```

The existing `Tenant` is the organization. We keep one workspace identity rather than introducing an overlapping organization table. Routes validate requests and call services. Services enforce roles and tenant scope before changing database state.

## D. Important files and responsibilities

- `backend/app/models/membership.py`: membership role, joined timestamp, one-organization-per-user constraint, and composite tenant consistency foreign key.
- `backend/app/models/invitation.py`: bound email/role, hashed invitation secret, issuer, expiry, and consumption timestamp; issuer must belong to the same tenant.
- `backend/migrations/versions/002_organizations_memberships.py`: create the new tables and backfill existing active users without replacing their accounts.
- `backend/app/schemas/common.py` and `schemas/organizations.py`: trimmed, bounded names and narrowly allowed role/update payloads.
- `backend/app/services/organizations.py`: profile edits, organization changes, roster queries, role rules, removal, invitations, and acceptance transactions.
- `backend/app/services/auth.py`: atomic registration with owner membership and membership-aware authentication/session issuance.
- `backend/app/api/users.py` and `api/organizations.py`: profile and organization REST endpoints.
- `frontend/src/features/organizations/SettingsPage.tsx`: profile editing, organization settings, member management, invitations, pagination, and visible errors.
- `frontend/src/features/organizations/JoinPage.tsx`: invitation onboarding and URL-secret removal after acceptance.
- `frontend/src/services/api.ts` and `auth/AuthContext.tsx`: typed requests, session updates, query-cache clearing, and sign-out when protected access and refresh are rejected.
- `backend/tests/api/test_organizations.py`, `backend/tests/test_migrations.py`, and `frontend/src/__tests__/OrganizationFlows.test.tsx`: API/security, migration preservation, and browser component-flow tests.

## E. Technical concepts

**Dependency injection:** FastAPI supplies the authenticated user and database session to each route. The caller cannot select a different tenant by putting a tenant ID into an update payload.

**Membership and RBAC:** Membership connects the user to an organization and records a basic role. A member can edit their own profile and read the roster. An admin also manages organization details and ordinary members. The owner alone can grant admin privileges. File-level permissions are a later phase.

**Composite foreign keys:** A normal user foreign key proves that a user exists. The membership's `(user_id, tenant_id)` foreign key also proves that the user belongs to that exact tenant. This catches inconsistent links even if application code were to make a mistake.

**Transactions:** `flush()` sends inserts to the database without making the transaction permanent. `commit()` makes all its changes permanent together. Registration commits the tenant, user, membership, and session together. Invitation acceptance commits consumption, user, membership, and session together. If session creation fails, closing/rolling back the session leaves no partial membership and keeps the invitation unconsumed.

**Conditional updates:** Two requests may read the same invitation before either finishes. The database updates it only if it is still unconsumed and unexpired. Only one request receives a returned ID and proceeds.

**Row locks:** PostgreSQL management transactions lock the organization row before checking current manager privileges and changing roles, removing members, or accepting invitations. This serializes changes within an organization. SQLite ignores `FOR UPDATE`; local tests exercise conditional updates, while PostgreSQL lock behavior requires CI verification. Serialization is intentionally simple for the current phase and can reduce throughput in a very busy organization; no performance measurement has been made.

**Query caching:** TanStack Query keys include organization and user IDs. Mutations invalidate affected lists and refresh the current user. Authentication changes clear cached data so a different account does not reuse the previous account's results.

## F. How requests work

1. **Registration:** Validate input, create a tenant and owner, flush their IDs, insert an owner membership, issue a session, and commit once.
2. **Protected request:** Verify JWT signature/expiry/type, load an active user matching the token's tenant, and require a matching membership. Manager operations read the current membership role from the database.
3. **Invitation creation:** Lock the organization, check manager privileges, reject existing-account email addresses, invalidate earlier pending invitations for that organization/email, generate a random token, and persist its hash. Return the raw secret once for secure manual sharing.
4. **Acceptance:** Find the token hash, lock the organization, atomically consume the unexpired invitation, create the bound-email account with the invite's role, add its membership, and issue a session. The browser replaces `/join#token=...` with `/app`.
5. **Role change:** The owner changes a non-owner membership and the compatibility `User.role` field in one transaction. Invitations issued by that user are invalidated. Older JWT role claims do not retain privileges.
6. **Removal:** Delete the membership, disable the account, revoke its refresh tokens and issued invitations, and commit. Subsequent protected requests fail. If refresh also fails, the browser clears its session/cache and returns to sign in.

## G. Security considerations

- Members cannot use manager endpoints. Admins cannot grant admin roles, change roles, remove another admin, or remove the owner.
- The owner cannot be demoted or removed; ownership transfer is not implemented.
- Cross-tenant member and invitation IDs return 404, and list queries include tenant scope.
- JWT roles are descriptive claims, not the source of management authorization. Current database membership governs access.
- Profile and organization update schemas forbid extra fields, including injected role/tenant changes. Names are trimmed and cannot be blank.
- Passwords use the existing Argon2id implementation. Invitation secrets are random and hashed; no raw secret is persisted in the invitation row.
- Invitation links are bearer credentials bound to an email. Possessing the link permits creation of that email's account; mailbox ownership is not independently verified.
- The secret is in the URL fragment, which is excluded from HTTP request URLs. The fragment is cleared after successful acceptance. Secrets/passwords must not be logged or collected by analytics.
- Removed users lose membership and active status; subsequent requests cannot rely on a previously issued access token.

## H. Testing and results

Local results: **59 backend tests passed**, **20 frontend tests passed**, Ruff passed, ESLint passed, and the TypeScript/Vite production build passed. Frontend tests still emit React Router future-version migration warnings.

The tests include normal profile/org edits, owner/admin/member behavior, unauthenticated requests, blank/extra fields, role escalation, forged/stale JWT role claims, genuine cross-tenant IDs, missing membership, removal with old access/refresh credentials, expired/revoked/unknown invitations, replay, replacement invitations, existing-account movement rejection, concurrent acceptance, and simulated session-creation failure with rollback.

SQLite test databases have foreign keys enabled. A database test rejects a cross-tenant membership link. Real Alembic upgrade/check/downgrade/re-upgrade tests pass. A seeded Phase 1 migration test verifies active-user backfill, skipped inactive accounts, retained password hashes, and retained users after downgrade.

Frontend tests drive forms and controls through the rendered app with mocked HTTP responses. They cover profile/org saves, role changes, removal, invitation creation/revocation, member/admin control visibility, roster pagination, joining, expired/incomplete links, failed API mutations, and removed-session redirection. These are component integration tests, not a real-browser full-stack E2E run.

CI already provisions PostgreSQL and a Docker smoke job. Those runtime checks were not run in this work because Docker/PostgreSQL are unavailable on this host and no push was authorized. Local SQLite results do not establish PostgreSQL lock behavior or full container startup.

## I. Important design decisions

ADR-010 reuses tenants as organizations and explicitly retains one organization per account. A separate organization entity would duplicate workspace identity. Multi-workspace support would need a session/tenant-selection redesign and is deferred.

Membership role is the authorization record. `User.role` remains for compatibility with Phase 1 responses and is kept synchronized in the service transaction. Authentication fails closed if the two disagree.

ADR-011 uses manually shared invitation links because no email transport exists. No fake delivery is claimed. The recipient chooses their password. Existing accounts cannot be moved by an invitation. Organization locks and conditional consumption keep management and onboarding changes consistent across backend instances.

## J. Limitations

- Docker/PostgreSQL runtime verification remains pending CI.
- One organization per account; no workspace switching, joining with an existing account, ownership transfer, or removed-account reactivation.
- No email sending or independent email verification. Private links must be shared securely.
- No avatar upload, password reset, or email-change workflow in this phase; the profile edit is full name only.
- No granular file/folder permissions, rate limiting, invitation abuse monitoring, or production-readiness claim.
- Pending invitations are persisted and can be revoked; there is no background cleanup worker yet.

## K. Interview questions and answers

**How do you prevent an old admin token from retaining admin rights?** The API validates the JWT's identity/tenant but reads the current membership role from the database for manager operations. Demoting the membership and compatibility user role takes effect on later requests even if the token still says `admin`.

**How do you prevent cross-tenant IDOR?** Resource queries include the authenticated tenant ID. A foreign tenant's member or invitation ID yields 404. Composite foreign keys also prevent inconsistent membership and invitation-issuer links in stored data.

**Why use a transaction for invitation acceptance?** Token consumption, account creation, membership creation, and session issuance must succeed together. Tests deliberately fail session creation and confirm the invitation is still usable and no extra membership remains.

**Why is reading a valid invitation insufficient?** Two requests can read it concurrently. The conditional update allows only one to consume it. PostgreSQL organization locks additionally serialize related management changes.

**Why hash an invitation token?** A read-only database leak should not expose directly usable invitation links. The user supplies the random secret, and the backend matches its hash.

**Why did you keep a modular monolith?** Profiles, membership rules, and onboarding share transactions and domain data. Separate services would add distributed consistency work without a demonstrated need at this stage.

**What would you change for multiple organizations per user?** Remove the one-membership-per-user constraint and primary-tenant assumption, make users independent of a tenant, derive roles from the selected membership, and design explicit organization selection/session behavior. That is not implemented here.

## Operational handoff

Run `alembic upgrade head` before starting a locally installed backend; Compose applies it automatically. Open **Profile and organization** after sign-in. Create a private invitation and share it with the intended new user through a secure channel.

Phase 3 — Folder System remains unstarted. After Phase 2 completion, the owner approved roadmap extensions: Phase 2A adds email/account/session lifecycle and Phase 2B adds multi-organization membership, ownership transfer, and reactivation before Phase 3. These extensions are planned, not implemented. See [Development Plan](../../DEVELOPMENT_PLAN.md) for their acceptance criteria and the immediate infrastructure verification gate.

Suggested commit for the implemented Phase 2 work: `feat(phase-2): add organization memberships profiles and invitations`. This phase's changes are prepared but uncommitted; no push was performed.
