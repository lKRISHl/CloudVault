# CloudVault Project Context

## Product Vision
CloudVault is an AI-native multi-tenant cloud file storage SaaS. It bridges the gap between simple object storage and intelligent document management, providing teams with powerful search, summarization, and collaboration capabilities out-of-the-box.

## Target Users
- **Individuals**: Personal file organization and smart search.
- **Teams**: Collaborative spaces, granular permissions, and shared knowledge bases.
- **Enterprises**: Scalable document management with robust access controls and auditing.

## Core Capabilities
- **File Management**: Upload, organize, and retrieve files securely.
- **Collaboration & Sharing**: Shareable links, granular permissions, and real-time updates.
- **AI Features**: Automatic document summarization, semantic search (RAG), and content categorization.
- **Multi-Tenancy**: Complete isolation of data and configuration across tenants.

## Technology Stack Summary
- **Frontend**: React, TypeScript, Vite, Tailwind CSS
- **Backend**: Python, FastAPI, SQLAlchemy (async)
- **Infrastructure**: PostgreSQL, Redis, S3/MinIO
- **Deployment**: Docker, GitHub Actions

## Multi-Tenancy Model
The system enforces strict multi-tenancy. Every resource (file, folder, permission) belongs to a specific tenant. Queries and data access are rigidly scoped to the authenticated tenant context.

## Security Philosophy
- **Defense in Depth**: Multiple layers of security from CORS, input validation, to strict RBAC.
- **Secret Management**: Development defaults are explicitly non-production; production JWT signing keys must be supplied through secure configuration.
- **Zero Trust**: Every request must be fully authenticated and authorized.

## Deployment Strategy
Containerized modular monolith with separate infrastructure services. Extract application services only when actual scaling or operational needs justify it.

## Current Organization Scope

Phase 2B builds on Phase 2 organizations: global identities can hold independent owner/admin/member roles in multiple tenants. Users can create/list/switch workspaces and accept invitations with verified existing identities. Owners transfer ownership with password/confirmation; removal/reactivation is scoped to one membership, and global deletion checks all owned organizations first.

Phase 2A adds SMTP email delivery, verified-email access to organization features,
recovery/email-change workflows, immediate session revocation, and protected profile
deletion. Development delivery is tested against a real local SMTP inbox. Production
provider verification and remote CI remain pending. Phase 2B passes 92 backend tests,
24 frontend component tests, 9 real Chromium/SMTP journeys, PostgreSQL migrations and
concurrency checks, and the updated Docker/storage smoke. Phase 3 is next and unstarted.

## Commercial Vision
- **Free Tier**: Basic storage, standard search.
- **Pro Tier**: Increased limits, basic AI summaries.
- **Team/Enterprise**: Advanced RBAC, semantic search, unlimited collaboration, custom domains.
