# Development Plan

## Roadmap

- **Phase 0: Project Foundation** [IN PROGRESS] (Complexity: Low)
  Set up repository, basic configuration, Docker Compose, initial docs, CI.

- **Phase 1: Backend Scaffolding** (Complexity: Low)
  Basic FastAPI setup, DB connections, initial models.

- **Phase 2: User Authentication & Tenants** (Complexity: Medium)
  JWT auth, multi-tenant data structures, basic user management.

- **Phase 3: File Storage Foundation** (Complexity: Medium)
  S3 integration, file metadata models, presigned URLs for upload/download.

- **Phase 4: Folder Structures & Navigation** (Complexity: Medium)
  Hierarchical folder models, navigation APIs.

- **Phase 5: Frontend Scaffolding** (Complexity: Low)
  React setup, routing, authentication context, basic layout.

- **Phase 6: File Explorer UI** (Complexity: High)
  Drag-and-drop, folder navigation, file previews.

- **Phase 7: Permissions & Sharing** (Complexity: High)
  Granular RBAC, shareable links, access control logic.

- **Phase 8: Background Workers** (Complexity: Medium)
  Celery/Redis integration for asynchronous tasks (e.g., thumbnail generation).

- **Phase 9: AI Pipeline Setup** (Complexity: High)
  Integration with LLMs, document text extraction.

- **Phase 10: Semantic Search (RAG)** (Complexity: High)
  pgvector setup, embeddings generation, search API.

*(Phases 11-33 to be detailed as the project evolves, covering advanced collaboration, enterprise features, billing, analytics, etc.)*
