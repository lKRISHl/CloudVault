# Development Plan

## Roadmap

- **Phase 0: Project Foundation** [COMPLETE] (Complexity: Low)
  Set up repository, basic configuration, Docker Compose, initial docs, CI.

- **Phase 1: Authentication & Tenants** [IN PROGRESS] (Complexity: Medium)
  JWT auth, tenant + user models, register/login, frontend session.

- **Phase 2: File Storage Foundation** (Complexity: Medium)
  S3 integration, file metadata models, presigned URLs for upload/download.

- **Phase 3: Folder Structures & Navigation** (Complexity: Medium)
  Hierarchical folder models, navigation APIs.

- **Phase 4: File Explorer UI** (Complexity: High)
  Drag-and-drop, folder navigation, file previews.

- **Phase 5: Permissions & Sharing** (Complexity: High)
  Granular RBAC, shareable links, access control logic.

- **Phase 6: Background Workers** (Complexity: Medium)
  Celery/Redis integration for asynchronous tasks (e.g., thumbnail generation).

- **Phase 7: AI Pipeline Setup** (Complexity: High)
  Integration with LLMs, document text extraction.

- **Phase 8: Semantic Search (RAG)** (Complexity: High)
  pgvector setup, embeddings generation, search API.

*(Later phases will cover advanced collaboration, enterprise features, billing, and analytics.)*
