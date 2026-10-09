# Security and production readiness

## Required deployment settings

- `ITHUTE_AUTH_INTERNAL_URL`: trusted internal base URL for developer identity registration.
- `ITHUTE_DEVELOPER_TURNSTILE_SECRET`: server-only anti-bot verification secret.
- `NEXT_PUBLIC_ITHUTE_DEVELOPER_TURNSTILE_SITE_KEY`: public challenge site key.
- For each Next.js integration, configure issuer, client ID, exact HTTPS callback and unique strong server-only session secret.

## Safety checklist

1. Verify database migration, deployment version and service availability before enabling registration.
2. Require HTTPS externally, enforce same-origin registration requests, and check anti-bot token hostname.
3. Add distributed rate limits and detection of registration/verification abuse; deployment should not rely on the challenge alone.
4. Verify email ownership before allowing sensitive API access or paid-service activation.
5. Restrict developer application creation, callback modification and activation by ownership and permission checks.
6. Enforce exact callback allowlists, PKCE, signed token validation, central session status and logout revocation.
7. Store refresh tokens only in durable server-controlled storage with atomic rotation and replay handling.
8. Record administrative changes without secrets, and alert on unusual registrations, token failures, and mailbox requests.
9. Test sign-up, legitimate login, rejected callback, revoked session, cross-origin POST, throttling and outage handling.
10. Check final CI on `main`, deployed migrations and production smoke tests, with a rollback plan.

## Status

The public portal is under development and should not be considered a validated public production release until its PR is merged, mandatory configuration and rate limiting are in place, and end-to-end testing is completed.
