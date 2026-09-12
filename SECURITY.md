# Security Policy

## Supported code

The current `main` branch is the supported production release.

## Reporting a vulnerability

Do not disclose exploitable security issues, credentials, private keys, tokens or customer data in a public issue. Use GitHub private vulnerability reporting when available, or the existing private Ithute support channel.

## Security expectations

Ithute production changes must preserve least privilege, secure cookies, TLS, explicit hostname routing, secret separation, authenticated service-to-service access and durable identity data. Secrets belong in GitHub environment secrets, host secret storage or protected runtime files and must never be committed.

The public edge must route `ithute.co.ls` only to the Ithute web service. Unknown hostnames must not fall through to a different application. Central Auth, Push and Realtime use dedicated upstream names and must never depend on a generic `frontend`, `backend` or `nginx` alias on a shared product network.

Treat suspected credential exposure as compromised immediately: rotate the affected secret, invalidate relevant sessions or service credentials, inspect audit logs and verify production health before restoring normal operation.
