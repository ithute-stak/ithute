# Phase 10 — Security & Compliance

Phase 10 hardens the control plane and webmail without changing the accepted Phase 9 mail protocol architecture.

## Implemented controls

- Dedicated versioned DKIM encryption envelope. New DKIM private keys use `DKIM_ENCRYPTION_KEY`; Phase 8 legacy ciphertext remains readable for migration. Production requires the DKIM key to be present, non-placeholder and distinct from `SECRET_KEY`.
- Rspamd signing material is isolated in `RSPAMD_REDIS_URL`. Application sessions, cache and brute-force counters remain in `REDIS_URL`. Production refuses both URLs being the same.
- Webmail login throttling uses Redis counters keyed by a SHA-256 digest of mailbox address plus direct peer IP. Lockouts return `429` and `Retry-After`; successful authentication clears the failure state.
- Browser state-changing API requests reject mismatched `Origin` values and `Sec-Fetch-Site: cross-site`. CLI/server-to-server requests without browser origin headers remain supported.
- Backend responses set `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, API/health CSP, request correlation IDs, and production HSTS.
- Webmail rich HTML is allowlist-sanitized with Bleach. Scripts, SVG/images, event attributes, style attributes and unsafe URL schemes are not allowed.
- Downloaded attachments are forced to `application/octet-stream` with `Content-Disposition: attachment`, filename normalization, `nosniff`, `Cache-Control: private, no-store`, and a sandbox CSP.
- Webmail authentication security events are appended to the existing SQL audit ledger. Existing mailbox targets resolve to internal mailbox/tenant IDs; unknown targets use a short SHA-256 digest. Passwords, session tokens, message bodies and attachment contents are not accepted by the audit helper.
- `scripts/rewrap-dkim-secrets.py` re-encrypts readable stored DKIM material with the currently configured Phase 10 DKIM key without printing private material.

## Operational rules

Keep application Redis and Rspamd signing Redis private and independently backed up according to their data sensitivity. Never expose Redis ports publicly. Production secrets must be injected by the deployment environment rather than committed to the repository.

Before changing `DKIM_ENCRYPTION_KEY`, ensure the currently stored ciphertext is readable by the running release, schedule a maintenance window, configure the intended key, run the rewrap utility, synchronize active DKIM keys to Rspamd, and verify live signing before retiring old secret material.

The API audit ledger is append-oriented: application APIs expose reads, not edit/delete operations. Retention and immutable off-site audit export can be added with the backup/operations phases without putting message content into the audit stream.

## Acceptance gate

Run:

```bash
git checkout development
git pull origin development
sh scripts/verify-phase10.sh
```

The final verifier runs the complete Phase 9 regression gate and then checks DKIM key separation/migration compatibility, isolated signing Redis, brute-force lockout, cross-origin mutation rejection, security headers, audit redaction, HTML sanitizer behavior, attachment boundary handling and the DKIM rewrap deployment artifact.

Phase 10 provides security/compliance readiness controls; it does not claim a third-party compliance certification or legal certification for any jurisdiction.
