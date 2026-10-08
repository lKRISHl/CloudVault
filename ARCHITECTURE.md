# Phase 0 Architecture

## Overview
CloudVault adopts a modular monolith approach for Phase 0. 

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
