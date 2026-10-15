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
concurrency checks, and the updated Docker/storage smoke. Phase 2B is committed as 35d4b58.

Phase 3 adds a real folder browser with creation, rename, destination-based moves,
breadcrumbs/pagination and a shared-workspace permission foundation. Parent edges
and resource access stay tenant-scoped; concurrent writes preserve an acyclic tree.
113 backend tests, 28 frontend tests and 11 Chromium journeys pass, plus migrations
and actual Docker folder operations. Phase 3 is committed as 5c5bccd.

Phase 4 adds tenant-scoped pending file metadata with folder/creator integrity,
declared size/type, normalized names and indexes. Internal reservations check current
membership and parent authority; public listing/details and the folder browser show
metadata without claiming actual uploads. 131 backend tests on SQLite/PostgreSQL,
31 frontend tests, 11 Chromium journeys and Docker at 006_files pass. Phase 5 adds an internal tenant-scoped S3 adapter with UUID-only object keys, private
local bucket provisioning, bounded conditional writes/reads and safe failure handling.
158 backend tests pass on SQLite/PostgreSQL with real MinIO contract checks; the
rebuilt Docker stack passes application-adapter object smoke. Phase 6 adds actual browser-to-private-storage presigned uploads with persistent
reservation identity, checksum/size verification, current permission checks and
retry/reconciliation. 174 backend tests, 39 frontend tests and 12 real Chromium/
SMTP/storage journeys pass; Docker is at 007_uploads with actual upload smoke.
Uploads remain unscanned. Phases 7/8 add downloads and multipart transfers below;
Phases 4–8 and the frontend redesign are committed as 670d2a0.

## Commercial Vision
- **Free Tier**: Basic storage, standard search.
- **Pro Tier**: Increased limits, basic AI summaries.
- **Team/Enterprise**: Advanced RBAC, semantic search, unlimited collaboration, custom domains.


Phase 7 now supports actual member-authorized downloads of completed uploads through private, short-lived attachment URLs. Files remain unscanned; Phase 12 now adds resource ACLs; versioning, scanning and AI remain later phases. Development storage is on D:\CloudVault-Dev.

Phase 8 adds bounded multipart hashing/direct transfer, provider-verified parts,
conditional composite completion and cancellation. Default maximum is 1 GiB with
8 MiB chunks and a one-hour deadline. Schema 008_multipart preserves basic uploads.
Reload-based resume and automated orphan cleanup are Phase 9; production provider,
CI and deployment gates remain pending. Current verification is in CONTINUE.md.

Phase 9 now implements reload-based multipart resume, actual saved progress and only
missing-part transfer. Durable initialization intents and repeated maintenance of hidden
cleanup references reclaim expired/abandoned uploads and names. 206 backend tests,
53 frontend tests, 14 Chromium journeys and Docker checks pass at 009_upload_cleanup.
Current cleanup requires an unversioned bucket; provider lifecycle/production gates
remain. Phase 9 is committed as 0551f25.

Phase 9 and its regression notes are now committed as 0551f25. Phase 10 filename
search is implemented with tenant isolation, metadata filters, stable sorting,
bounded pagination, folder context and PostgreSQL trigram/tenant B-tree indexes.
214 backend tests, 60 frontend tests, 15 browser journeys and Docker checks pass at
010_file_search. Phase 10 is committed as d4aa3e1; Phase 11 Sharing is now implemented. Production
load/provider/remote CI and existing deployment gates remain pending.

## Current Sharing Capability (Phase 11)
Completed files can be shared externally by their creators/workspace managers through expiring secret links with optional passwords, metadata-only access and download-grant limits. Recipients need no account. Revocation and publisher lifecycle checks prevent new grants; issued provider URLs remain usable until expiry. This is file-link sharing, with resource ACLs now implemented in Phase 12; folder share links, previews, recipient identity and AI remain upcoming. See docs/phases/phase11.md.

## Current Resource Access (Phase 12)
File/folder workspace/private visibility and explicit viewer/editor grants now govern signed-in workspace access. Every containing folder must be readable; search/list queries filter before pagination/context. Creators and trusted workspace managers control permissions, moves and external publication. Editors can rename completed files/folders and create content in editable folders; editing does not inherit to others' child resources. Permission changes revoke affected external links and member removal deletes grants. Public recipient identity verification, groups/custom roles, realtime cache synchronization and later trash/version/scanning/AI/deployment work remain pending. See docs/phases/phase12.md.
