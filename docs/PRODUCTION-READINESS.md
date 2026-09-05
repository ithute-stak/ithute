# Production Readiness Gate

Mailbox DNS should be treated as production-ready **only when this checklist and the automated Commercial Release Regression are both satisfied**. Source-code readiness does not replace external infrastructure readiness.

## Repository and release governance

- Use `development` for changes and keep `main` as the release branch.
- Require the **Commercial full regression** status check before merging to `main`.
- Configure a GitHub ruleset for `main`: require pull requests, require the regression check, block force-pushes and branch deletion, require conversation resolution, and restrict bypass to repository owners/emergency maintainers.
- Keep GitHub Actions permissions read-only unless a narrowly scoped maintenance workflow explicitly needs write access.
- Review Dependabot PRs on `development`; do not auto-merge dependency changes without the full regression.

## Secrets and identity

- Generate independent, high-entropy values for application, DKIM, billing, PowerDNS, mail-ops, recovery, mail-node, Restic, Grafana, bootstrap-admin and HA replication secrets.
- Never reuse `SECRET_KEY`, `DKIM_ENCRYPTION_KEY` or `BILLING_WEBHOOK_SECRET`.
- Keep `.env`, private keys, certificates with private material and provider credentials out of Git.
- Enable CAPTCHA for public signup and configure real Cloudflare Turnstile site/secret keys.
- Use secure cookies and verify production email delivery for signup/invitation flows.

## Network and DNS

- Run NS2 on an independent public server/failure domain.
- Restrict PowerDNS API/database, PostgreSQL, Redis, Rspamd Redis, mail operations, recovery and Dovecot replication ports to private networks/firewalls.
- Confirm UDP/TCP 53, SMTP 25, submission 587, IMAPS 993 and HTTPS are reachable only where intended.
- Configure real A/AAAA, MX, NS, SPF, DKIM and DMARC records and verify delegation externally.

## Mail deliverability

- Use a dedicated clean public mail IP and matching PTR/rDNS.
- Use public TLS certificates; production must not use self-signed mail TLS.
- Verify HELO/EHLO, forward-confirmed reverse DNS, SPF, DKIM signing, DMARC alignment and outbound reputation.
- Send real external test messages in both directions before moving customer MX.

## Data protection and recovery

- Store Restic backups off-site in a separate failure domain.
- Encrypt backups with an independent password and protect object-storage credentials.
- Run and document a real restore drill, including database and at least one mailbox recovery.
- Confirm backup-age monitoring and alert routing are operational.

## External providers

- DPO Pay remains disabled until real merchant credentials and HTTPS callback/redirect URLs are configured and verified server-to-server.
- OpenSRS remains disabled until reseller credentials are provisioned and production source IPs are allowlisted as required by the provider.
- Never infer a successful payment or registration from a browser redirect alone.

## Release commands

```bash
sh scripts/verify-commercial-release.sh
sh scripts/prod-preflight.sh
sh scripts/prod-up.sh
```

After deployment, verify API/frontend health, authoritative DNS, SMTP/IMAP, queue processing, groupware, monitoring, backup freshness and public TLS before accepting customer traffic.
