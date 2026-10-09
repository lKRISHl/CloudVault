# Security Considerations

## Phase 0 Baseline

- **CORS Configuration**: Restrict origins in production. Local development allows specific localhost ports.
- **Input Validation**: All incoming API requests must be validated using Pydantic models.
- **Secrets Management**: No secrets are hardcoded. Everything is managed via `.env` files locally and secure environment variables in production.

## Phase 1 Authentication
- **Passwords**: Argon2id hashes; login verifies a dummy hash when the email is unknown to reduce timing leaks.
- **Access tokens**: Short-lived JWTs (`sub`, `tid`, `role`) sent as `Authorization: Bearer`.
- **Refresh tokens**: Random secrets stored as SHA-256 hashes, rotated on refresh, revoked on logout, delivered in HttpOnly cookies.
- **Tenant isolation**: Authenticated lookups require both `user_id` and `tenant_id` from the access token.

## Future Security Roadmap
- **RBAC (Role-Based Access Control)**: Granular permissions for files and folders.
- **Invites / multi-workspace membership**: Users belonging to more than one tenant.

## Responsible Disclosure Policy
*(Placeholder: Details on how to report vulnerabilities will be added prior to production release.)*
