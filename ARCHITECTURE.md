# CloudVault Architecture

## Overview
CloudVault uses a modular monolith. Phase 2 adds organization and membership services to the existing backend.

```text
[Frontend Client (React/Vite)] 
       | (REST API via HTTP)
       v
[Backend API (FastAPI)] 
  |--> [PostgreSQL (Relational Data)]
  |--> [Redis (Caching/Queues)]
  |--> [MinIO (Object Storage)]
```

## Component Descriptions
- **Frontend**: A React Single Page Application built with Vite and Tailwind CSS. It communicates with the backend via REST.
- **Backend**: A Python FastAPI application providing core business logic and API endpoints. 
- **Database**: PostgreSQL handles relational data, configured with async SQLAlchemy and Alembic for migrations.
- **Cache/Queue**: Redis is provisioned for future caching and asynchronous task queues.
- **Storage**: MinIO provides an S3-compatible local object storage environment for file blobs.

## Authentication (Phase 1)
- Register creates a tenant and an `owner` user.
- Login returns a short-lived JWT access token and sets an HttpOnly refresh cookie.
- Protected routes require matching user and tenant IDs, active user status, and an explicit membership with a matching stored role. JWT role claims are not used to grant management privileges.

## Organizations and Membership (Phase 2)

- The existing `Tenant` is the organization/workspace; there is no duplicate organization table.
- Registration creates a tenant, owner user, membership, and session in one transaction.
- `memberships` records organization membership and its role. A unique user constraint preserves the current one-organization-per-user model. A composite foreign key binds membership to the user's actual tenant.
- `invitations` contains a hashed, seven-day bearer token, bound email and role, issuing user, organization, expiry, and consumption timestamp. Its issuer is constrained to the same tenant.
- Only owners can assign admin roles. Admins can rename organizations, invite members, and remove members; members can edit their own profile and read their organization's roster.
- Owner membership cannot be removed or demoted. Removing a member deletes their membership, disables their account, revokes refresh tokens, and invalidates invitations they issued.
- PostgreSQL organization-row locks serialize management operations. Invitation acceptance uses an additional conditional update and commits token consumption, account, membership, and session together.
- `User.role` remains for Phase 1 response compatibility and is updated with `Membership.role` in the same transaction. Authentication fails closed if these disagree.
- Frontend routes `/app/settings` and `/join` provide management and invitation onboarding. Query caches are scoped to tenant/user and cleared when authentication changes. Invitation secrets are placed in the URL fragment and cleared after acceptance.
- File/folder permissions and multi-workspace membership are not implemented in this phase.

## Account Lifecycle (Phase 2A)

- JWT access tokens now contain `sid`, referencing a stable `login_sessions` row. Refresh rotation preserves the session ID and seven-day absolute session deadline. Protected requests check membership plus active session state; revocation takes effect on subsequent requests.
- `users.email_verified` defaults to false, including migrated accounts. Organization features require verified email. `account_tokens` stores hashed purpose-bound verification/reset/email-change challenges.
- Registration and invitation acceptance queue a separate verification challenge in their database transaction. Resets and email changes revoke sessions and invalidate account links; confirmation requires new-address verification and current-account reauthentication.
- `email_outbox` stores encrypted mail payloads, attempts, delivery deadlines, leases, and status. A small dedicated SMTP dispatcher processes it separately from requests; general Redis/Celery processing remains Phase 16 work.
- Compose adds a local Mailpit inbox and an email dispatcher. Shared database rate counters protect account endpoints across backend processes without relying on local memory.
- Migration `003_accounts` preserves identities/passwords, marks addresses unverified, and revokes legacy refresh cookies. Legacy access tokens lack the required session claim and are rejected; existing users must sign in and verify their address.
- `/account/recover`, `/account/action`, and `/app/security` provide recovery, verification/email confirmation, delivery status, and session management. Action secrets use URL fragments; successful actions clear those fragments.
- Verified non-owner deletion redacts profile identifiers, removes memberships/recovery tokens, and revokes access while retaining reference-safe tombstones. Full multi-organization deletion/ownership transfer remains Phase 2B work.

## Configuration Management
Configuration is managed using `pydantic-settings` on the backend, reading from environment variables. The `.env` file serves as the source of truth for the local development environment.

## Database Setup
- **ORM**: Async SQLAlchemy for performant database interactions.
- **Migrations**: Alembic is configured to manage schema evolutions.

## Future Architecture Vision
As the application scales, the modular monolith may be split into specific microservices (e.g., separating AI processing pipelines). We will introduce Celery for background workers and pgvector for semantic search.

## Core Principles
- **Stateless Backend**: API servers maintain no local state.
- **Modular Monolith**: Code is organized into cohesive modules before premature extraction.
- **Separation of Concerns**: Clear boundaries between routing, business logic (services), and data access.
