# NBros Production Readiness

NBros is designed as an isolated product using Ithute Central Auth and Ithute Central Realtime while retaining its own PostgreSQL database, Redis instance, uploads volume and branch-scoped authorization.

## Release gate

A production release is acceptable only when the `NBros Fleet CI` workflow is fully green on the exact commit being deployed. The gate verifies Python compilation, all Alembic migrations, zero model/schema drift, Fleet and enterprise API contracts, backend regressions, Next.js type checking and production build, Compose validation, Caddy routing/security headers, and a PostgreSQL backup/restore round-trip.

## Runtime secrets

Do not commit database passwords, Central Auth service credentials, AI credentials or other runtime secrets. Keep them in the production environment or secret manager. The repository only contains placeholders/default non-secret configuration.

## Database backup

From `products/nbros` with the production `.env` loaded:

```bash
./scripts/backup.sh
```

Backups are written to `backups/` by default with mode restricted by `umask 077`. The directory and `*.dump` archives are ignored by Git.

Verify an archive before relying on it:

```bash
./scripts/verify-backup.sh backups/nbros-YYYYMMDDTHHMMSSZ.dump
```

Store production backups outside the application host as well. A backup is not considered proven merely because `pg_dump` returned successfully; CI performs an independent restore into a second PostgreSQL database and verifies the restored schema.

## Deployment sequence

1. Confirm the exact `nbros` commit has a completely successful CI run.
2. Take a fresh PostgreSQL backup and verify it.
3. Confirm persistent volume names for PostgreSQL, Redis and uploads have not changed unexpectedly.
4. Pull/build the exact release commit.
5. Run `alembic upgrade head` through the backend startup process.
6. Start PostgreSQL/Redis, backend, Fleet monitor and frontend.
7. Confirm `/healthz` and `/readyz` are healthy on the backend.
8. Verify Central Auth sign-in and logout.
9. Verify branch access, one Fleet readiness calculation, one vehicle request/match, one Workshop job, one procurement workflow and one report/export.
10. Verify realtime Fleet alert delivery and confirm no active notification delivery error in Fleet monitor status.

## Security controls

NBros responses receive request IDs, MIME-sniffing protection, clickjacking protection, referrer policy, permissions policy and cross-origin opener protection. Caddy additionally supplies HSTS and matching browser security headers at the edge. Company branch access is managed through the Governance API and important changes are written to the audit trail.

The internal `/metrics` endpoint is intentionally omitted from OpenAPI and is not routed by the public Caddy configuration. It is intended for host/internal-network observability only.

## Recovery

If a deployment fails after a migration or application change, preserve the current database volume first. Do not delete or recreate the production PostgreSQL volume as a rollback mechanism. Restore into a clean recovery database or host from the latest verified backup, validate the recovered schema/data, then deliberately switch service traffic after verification.

Uploads live in the `nbros_uploads` persistent volume and must be backed up separately from PostgreSQL. Redis is treated as reconstructable operational state and must never be the sole source of business records.
