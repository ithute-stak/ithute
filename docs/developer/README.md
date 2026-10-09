# Ithute Developer Platform

Developer entry point: `https://ithute.co.ls/developer` (available after the developer-portal release is deployed).

## Contents

| Area | Documentation | Availability |
| --- | --- | --- |
| Identity and OAuth 2.0 | [Authentication](./authentication.md) | Central Ithute Auth service; client registration restricted to elevated platform administrators |
| Next.js applications | [Next.js integration](./nextjs.md) | Repository SDK; not yet published on npm |
| Developer registration | [Accounts and email](./accounts-and-mail.md) | Existing-email identity registration, with anti-bot configuration required |
| API reference | [API reference](./api-reference.md) | Documented Auth endpoints; other endpoints require product authorization |
| Security and deployment | [Security and operations](./security.md) | Mandatory production controls and checklist |

## What is available today

The source repository implements central Ithute Auth user registration, OAuth 2.0 authorization-code + PKCE, JWT discovery/JWKS, managed application registration and exact redirect URLs, online session status and session revocation. The Next.js SDK uses secure server-side authentication logic and is intended for App Router applications.

Professional email, DNS, Push and infrastructure management are **managed/restricted services** rather than unrestricted public APIs. Listing them on the portal does not grant access or imply documented general-purpose public credentials.

## Access model

1. Register an Ithute identity using an existing email address.
2. Verify account ownership and complete any requested account security checks.
3. Request access to an integration/product.
4. An authorized platform administrator registers or activates OAuth clients and permissions.
5. Configure your application, test in a non-production environment, then request production enablement.

**An Ithute identity is not automatically a mailbox, platform administrator, tenant member, or API client.**

## Documentation guarantees

- Examples use placeholders rather than live credentials.
- Server secrets must never use `NEXT_PUBLIC_`.
- All callback URLs must be exact and HTTPS in production.
- Any feature marked planned/experimental must not be presented as already provisioned.
- Developer signup must not be enabled without `ITHUTE_AUTH_INTERNAL_URL` and the configured Turnstile public/site secret pair.

For SDK implementation-level details, see `packages/ithute-auth-nextjs/README.md`.
