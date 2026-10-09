# Architectural Decision Records

## ADR-001: Modular Monolith Architecture
- **Context**: Starting a new SaaS product with uncertain domain boundaries.
- **Decision**: Adopt a modular monolith architecture.
- **Rationale**: Reduces operational overhead and simplifies deployments while allowing for future microservice extraction if needed.
- **Alternatives considered**: Microservices (rejected due to premature optimization and overhead).

## ADR-002: Async SQLAlchemy with asyncpg
- **Context**: Need high-performance database access for a FastAPI application.
- **Decision**: Use SQLAlchemy with the asyncpg driver.
- **Rationale**: Maximizes concurrency and integrates cleanly with FastAPI's async nature.
- **Alternatives considered**: Synchronous SQLAlchemy, Tortoise ORM.

## ADR-003: Pydantic Settings for Configuration
- **Context**: Managing environment variables and configurations securely.
- **Decision**: Use `pydantic-settings`.
- **Rationale**: Provides strong typing and validation for environment variables out-of-the-box.
- **Alternatives considered**: os.environ, python-decouple.

## ADR-004: S3-Compatible Object Storage
- **Context**: Storing user files and assets securely and scalably.
- **Decision**: Use MinIO for local development and S3/R2 for production.
- **Rationale**: S3 API is the industry standard; MinIO provides an exact local replica.
- **Alternatives considered**: Storing files in DB (rejected due to performance/cost), local filesystem (rejected for scalability).

## ADR-006: JWT Access Tokens + Rotating Refresh Cookies
- **Context**: Phase 1 needs authentication for a browser SPA without placing long-lived secrets in JavaScript storage.
- **Decision**: Issue short-lived JWT access tokens in the JSON body and rotating refresh tokens in HttpOnly `SameSite=lax` cookies. Persist only SHA-256 hashes of refresh tokens.
- **Rationale**: Access tokens stay out of localStorage; refresh tokens can be revoked server-side; rotation invalidates stolen cookies after use.
- **Alternatives considered**: Server sessions in Redis only, JWT in localStorage, opaque access tokens.

## ADR-007: One Tenant Per User at Registration
- **Context**: CloudVault is multi-tenant; registration must create an isolated workspace.
- **Decision**: Registering creates a tenant plus the first user as `owner`. Users currently belong to a single tenant via `users.tenant_id`.
- **Rationale**: Delivers tenant isolation immediately without a membership join table. Invites and multi-workspace membership can be added in the permissions phase.
- **Alternatives considered**: Global users with a memberships table from day one.

## ADR-005: PostgreSQL + pgvector for Vector Search
- **Context**: Needing vector storage for AI semantic search.
- **Decision**: Use PostgreSQL with the pgvector extension.
- **Rationale**: Keeps relational and vector data in the same datastore, simplifying operations and transactions.
- **Alternatives considered**: Pinecone, Milvus, Qdrant (rejected to reduce infrastructure complexity initially).
