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

## ADR-005: PostgreSQL + pgvector for Vector Search
- **Context**: Needing vector storage for AI semantic search.
- **Decision**: Use PostgreSQL with the pgvector extension.
- **Rationale**: Keeps relational and vector data in the same datastore, simplifying operations and transactions.
- **Alternatives considered**: Pinecone, Milvus, Qdrant (rejected to reduce infrastructure complexity initially).
