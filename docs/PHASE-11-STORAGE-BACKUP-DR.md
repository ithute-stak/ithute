# Phase 11 — Storage, Backup & Disaster Recovery

## Foundation implemented

Phase 11 protects the durable control-plane database, authoritative DNS database and Maildir storage with encrypted Restic snapshots. Application Redis is intentionally excluded because it contains sessions/cache/throttle state, and Rspamd signing Redis is rebuildable from encrypted DKIM material stored in PostgreSQL.

The backup utility creates PostgreSQL custom-format dumps for the application and PowerDNS databases, computes SHA-256 checksums, records a versioned manifest, includes the Maildir tree, writes an encrypted Restic snapshot, applies retention, and runs repository integrity checks.

## Restore drills

`mailbox-restore-drill` restores the newest snapshot into an isolated workspace and verifies checksums before any database restore. It then restores both dumps into a disposable PostgreSQL service and checks that public tables exist. Maildir file counts are compared with the manifest. The restore target uses tmpfs, so the drill cannot overwrite production databases.

## Commands

Use the Phase 11 compose layer together with the normal and mail compose files:

```sh
docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml -f docker-compose.phase11-backup.yml up -d backup restore-postgres
docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml -f docker-compose.phase11-backup.yml exec backup mailbox-backup
docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml -f docker-compose.phase11-backup.yml exec backup mailbox-restore-drill
```

Run the acceptance gate with:

```sh
sh scripts/verify-phase11.sh
```

## Production requirements

The local `/repository` volume is suitable only for development and restore testing. Production must place the Restic repository on infrastructure independent of the primary mail server, for example an S3-compatible object store or SFTP target, and protect `RESTIC_PASSWORD` outside source control. Backup repository credentials should not reuse application, database, DKIM or mail-operation secrets.

A production deployment should keep multiple generations, monitor backup age and failures, periodically run `restic check`, and perform scheduled restore drills. Mailbox-DNS does not claim regulatory certification from these controls; they provide disaster-recovery and compliance-readiness foundations.

## Next increment

The next Phase 11 increment adds scheduled backup execution, off-site repository readiness validation, backup status/restore-point reporting, alertable failure state and a full disaster-recovery runbook with recovery-time and recovery-point objectives.
