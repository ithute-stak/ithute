# Security Policy

## Supported code

Only the current `main` release and the next candidate on `development` are supported. Historical `agent/*` branches are not production releases.

## Reporting a vulnerability

Do not disclose exploitable security issues, credentials, private keys or customer data in a public issue. If GitHub private vulnerability reporting is enabled for this repository, use **Security → Report a vulnerability**. Otherwise contact the deployment owner through the existing private business/support channel and include the affected component, impact, reproduction steps and a proposed mitigation when available.

## Security expectations

Production changes must preserve tenant isolation, least privilege, secure cookies, verified signup, CAPTCHA, TLS for public/system-mail paths, mail sender ownership, DNS authorization, encrypted backups and secret separation. Secrets belong in deployment secret storage or `.env` on the host and must never be committed.

A suspected credential exposure should be treated as compromised immediately: rotate the affected secret, invalidate sessions/API keys where relevant, review audit logs, and verify mail/DNS/provider access before restoring normal operation.
