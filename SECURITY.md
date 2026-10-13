# Security Considerations

## Phase 0 Baseline

- **CORS Configuration**: Restrict origins in production. Local development allows specific localhost ports.
- **Input Validation**: All incoming API requests must be validated using Pydantic models.
- **Secrets Management**: Development-only defaults exist in settings and Compose. Production startup rejects the default JWT signing secret and secrets shorter than 32 bytes. Supply a randomly generated key through secure environment configuration.

## Phase 1 Authentication
- **Passwords**: Argon2id hashes; login verifies a dummy hash when the email is unknown to reduce timing leaks.
- **Access tokens**: Short-lived JWTs (`sub`, `tid`, `role`) sent as `Authorization: Bearer`.
- **Refresh tokens**: Random secrets stored as SHA-256 hashes, rotated on refresh, revoked on logout, delivered in HttpOnly cookies.
- **Concurrent refresh**: An atomic conditional database update claims an unrevoked, unexpired token. Revocation and replacement are committed together. The frontend shares an in-flight refresh request within a browser tab.
- **JWT validation**: Signature, expiry, token type, required claims, active user status, and tenant ownership are checked.
- **Logout scope**: Logout revokes the presented refresh token. An already-issued access token remains valid until its short expiry; immediate access-token revocation is not implemented.
- **Tenant isolation**: Authenticated lookups require both `user_id` and `tenant_id` from the access token.

## Future Security Roadmap
- **RBAC (Role-Based Access Control)**: Granular permissions for files and folders.
- **Membership**: Organization membership is planned in Phase 2; richer permissions arrive in Phase 12.
- Rate limiting, token-family replay response, cross-tab refresh coordination, and wider security review remain future hardening work.

## Responsible Disclosure Policy
*(Placeholder: Details on how to report vulnerabilities will be added prior to production release.)*
