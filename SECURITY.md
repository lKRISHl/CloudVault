# Security Considerations

## Phase 0 Baseline

- **CORS Configuration**: Restrict origins in production. Local development allows specific localhost ports.
- **Input Validation**: All incoming API requests must be validated using Pydantic models.
- **Secrets Management**: No secrets are hardcoded. Everything is managed via `.env` files locally and secure environment variables in production.

## Future Security Roadmap
- **Authentication**: JWT-based auth with short-lived tokens and secure HttpOnly refresh tokens.
- **RBAC (Role-Based Access Control)**: Granular permissions for files and folders.
- **Tenant Isolation**: Mandatory filtering by `tenant_id` on all database queries.

## Responsible Disclosure Policy
*(Placeholder: Details on how to report vulnerabilities will be added prior to production release.)*
