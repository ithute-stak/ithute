# Phase 11 — Storage, Backup & Disaster Recovery

## Recovery objectives

Mailbox-DNS backups cover the control-plane PostgreSQL database, the PowerDNS PostgreSQL database, and Dovecot Maildir data in one encrypted Restic restore point. The default scheduler runs every six hours. Production operators should choose an RPO/RTO that matches business requirements and may shorten the cadence.

A backup is not considered healthy merely because a job ran. The repository must contain a recent snapshot, `restic check` must succeed during verification, and restore drills must periodically prove that database dumps and mailbox files can be recovered.

## Production repository

Development uses the local `/repository` volume so the acceptance gate is reproducible. Production must use storage independent of the primary application host. Restic supports S3-compatible object storage, SFTP and REST backends among others. Credentials and `RESTIC_PASSWORD` must be injected through the production secret manager or protected environment configuration and must never be committed.

The backup repository must not share the same failure domain as the mail server. Prefer a different provider/account/region where practical. Enable object-lock/immutability at the storage provider when available. Restrict repository credentials to the minimum permissions required by the selected backend.

## Scheduling and monitoring

`backup-scheduler` runs `mailbox-backup` repeatedly using `BACKUP_SCHEDULE_SECONDS` and records its most recent execution result in `/workspace/status/last-run.json`. `mailbox-backup-status --health` checks the newest encrypted restore point and fails when it exceeds `BACKUP_MAX_AGE_SECONDS`. Docker health monitoring therefore exposes stale or missing restore points.

Default values:

- backup cadence: 21,600 seconds (6 hours)
- freshness limit: 93,600 seconds (26 hours)
- retention: 7 daily, 5 weekly and 12 monthly points

Production monitoring should alert when the scheduler container is unhealthy, the repository cannot be reached, the newest point is stale, or repository integrity checks fail.

## Restore-point inspection

Run:

```sh
docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml -f docker-compose.phase11-backup.yml exec backup mailbox-backup-status --json
```

For full repository history:

```sh
docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml -f docker-compose.phase11-backup.yml exec backup restic snapshots --tag mailbox-dns
```

## Disaster recovery sequence

1. Declare the incident and stop writes to the affected production mail/control-plane systems where possible.
2. Provision clean replacement hosts and secure network access.
3. Restore required production secrets independently; do not copy secrets from a suspected compromised host.
4. Configure the same remote `RESTIC_REPOSITORY` and `RESTIC_PASSWORD` on the recovery host.
5. Run `restic check` and identify the required restore point by timestamp and snapshot ID.
6. Restore snapshot data into a staging recovery directory before overwriting any live data.
7. Restore the application PostgreSQL dump and PowerDNS dump into clean database instances.
8. Restore Maildir data to the Dovecot mail volume while preserving ownership and permissions expected by the mail service.
9. Start control-plane, DNS and mail services in dependency order and run health/readiness checks.
10. Verify tenant/domain/mailbox records, authoritative DNS responses, SMTP submission, inbound delivery, IMAP access and webmail.
11. Re-run DKIM synchronization and confirm SPF/DKIM/DMARC/PTR/HELO readiness.
12. Update DNS/IP failover records only after service verification.
13. Record the restored snapshot ID, incident timeline, validation results and any data-loss window.

Never run a destructive production restore before validating the selected point in an isolated target. The repository includes `mailbox-restore-drill` specifically to prove restoration without modifying production databases.

## Restore drills

Run `sh scripts/verify-phase11.sh` after backup-related changes. Production should additionally schedule an operational restore drill at least quarterly, using an isolated environment and a recent off-site restore point. Record the drill date, snapshot ID, elapsed restore time, validation results and remediation work.

## Scope and limitations

Phase 11 establishes backup, retention, encrypted restore points, freshness monitoring, scheduling and tested restore procedures. It does not claim zero data loss, geographic redundancy by itself, or regulatory certification. Those outcomes depend on production repository placement, provider controls, selected cadence, monitoring and operational practice.
