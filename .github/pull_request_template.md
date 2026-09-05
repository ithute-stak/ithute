## Production change checklist

- [ ] Change is based on current `development`.
- [ ] No secrets, private keys, production credentials, customer data, or generated runtime files are committed.
- [ ] Database changes include an Alembic migration and upgrade/downgrade considerations.
- [ ] Authentication, authorization, tenant isolation and billing entitlement impacts were reviewed.
- [ ] Mail/DNS changes preserve inbound availability and do not expose management/replication ports publicly.
- [ ] `sh scripts/verify-commercial-release.sh` passes or the PR explains why it cannot run locally.
- [ ] GitHub Commercial full regression is green before merge to `main`.
- [ ] Production operator documentation is updated when configuration, ports, DNS, TLS, backup or external-provider requirements change.

## Rollback

Describe the safe rollback path, including migration/data considerations when applicable.
