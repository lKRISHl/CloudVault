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
- **Secret Management**: No hardcoded secrets; configuration via environment variables.
- **Zero Trust**: Every request must be fully authenticated and authorized.

## Deployment Strategy
Containerized microservices architecture orchestrated via Docker. Future scalability planned with Kubernetes or managed cloud services.

## Commercial Vision
- **Free Tier**: Basic storage, standard search.
- **Pro Tier**: Increased limits, basic AI summaries.
- **Team/Enterprise**: Advanced RBAC, semantic search, unlimited collaboration, custom domains.
