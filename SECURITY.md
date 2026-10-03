# Security Policy

## Supported code

The current `main` branch is the supported production release.

## Reporting a vulnerability

Do not disclose exploitable security issues, credentials, private keys, tokens or customer data in a public issue. Use GitHub private vulnerability reporting when available, or the existing private Ithute support channel.

## Security expectations

Ithute production changes must preserve least privilege, secure cookies, TLS, explicit hostname routing, secret separation, authenticated service-to-service access and durable identity data. Secrets belong in GitHub environment secrets, host secret storage or protected runtime files and must never be committed.

The public edge must route `ithute.co.ls` only to the Ithute web service. Unknown hostnames must not fall through to a different application. Central Auth, Push and Realtime use dedicated upstream names and must never depend on a generic `frontend`, `backend` or `nginx` alias on a shared product network.

Treat suspected credential exposure as compromised immediately: rotate the affected secret, invalidate relevant sessions or service credentials, inspect audit logs and verify production health before restoring normal operation.


## Production security gates

Every production release SHA must pass:

- Ithute Standalone CI
- Production Safety CI
- Security CI

Security CI performs CodeQL extended analysis, Python and npm dependency audits, committed-secret policy checks, critical Trivy vulnerability/misconfiguration scanning, and SPDX SBOM generation.

Release images are immutable SHA-tagged GHCR artifacts. BuildKit emits SBOM/provenance attestations and GitHub records build provenance against each pushed image digest. Production deployment must continue to use an exact tested SHA; mutable `:latest` tags are prohibited.

## Dependency and container maintenance

Dependabot targets the production `main` branch for Python, npm, GitHub Actions, and every Ithute Docker build context. Critical vulnerabilities should be patched or explicitly risk-accepted before the next production release.

## Secret handling

Private keys, runtime `.env` files, cloud credentials, GitHub tokens, payment-provider live keys and unencrypted service secrets must never be committed. Security CI rejects common credential/private-key patterns and tracked runtime secret files.

## Incident preservation

If audit-integrity verification fails, preserve the affected database, audit records, container logs, host logs and immutable backups before attempting repair. Do not edit audit records to clear an integrity warning.
