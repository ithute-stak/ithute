# NBros Production Readiness

NBros is designed as an isolated product using Ithute Central Auth and Ithute Central Realtime while retaining its own PostgreSQL database, Redis instance, uploads volume and branch-scoped authorization.

## Release gate

A production release is acceptable only when the `NBros Main Release Gate` workflow is fully green on the exact commit being released. The same gate runs on `nbros`, on the pull request to `main`, and again on the exact `main` revision after merge. It verifies Python compilation, all Alembic migrations, zero model/schema drift, Fleet and enterprise API contracts, backend regressions, Next.js type checking and production build, standalone and production-overlay Compose validation, deployment script syntax, shared-edge cutover rendering/security headers, and a PostgreSQL backup/restore round-trip.

The retired BuildTrack CI and BuildTrack production workflows have been removed. `nbro.ithute.co.ls` is now owned by NBros; the deployment renderer replaces the legacy BuildTrack edge aliases with the isolated `nbros-backend` and `nbros-frontend` aliases only after NBros is healthy.

## Runtime secrets

Do not commit database passwords, Central Auth service credentials, AI credentials or other runtime secrets. Keep them in the production environment or secret manager. The repository only contains placeholders/default non-secret configuration. On first production deployment, the NBros deployment script creates strong product-local database/realtime secrets on the VPS and preserves those runtime-owned values on later releases.

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

1. Confirm the exact `nbros` head and its pull-request checks are completely green.
2. Merge the reviewed NBros pull request to `main`.
3. Require `NBros Main Release Gate` to pass again on the exact merged `main` revision.
4. Allow the established shared-platform sequence (`Commercial Release Regression` → `Build and Deploy Production`) to complete successfully first.
5. `Deploy NBros Production` then builds the exact merged revision, stages the isolated NBros product and preserves existing runtime data/secrets.
6. Take/verify the pre-change NBros PostgreSQL backup and back up uploads when an existing uploads volume is present.
7. Start the product-owned PostgreSQL and Redis, apply Alembic through backend startup, and require backend readiness before proceeding.
8. Start the Fleet monitor and frontend, then verify local health.
9. Provision the runtime-only NBros service credential into Central Auth without replacing sibling service-client registrations.
10. Verify Central Auth and Central Realtime are healthy, validate the existing TLS certificate contains `nbro.ithute.co.ls`, render/test the shared Nginx cutover, and only then route public NBros traffic to `nbros-backend`/`nbros-frontend`.
11. Verify public `/healthz`, `/readyz`, the frontend, Central Auth login redirection, Central Auth health, Central Realtime health and TLS SAN from the GitHub runner.

## Security controls

NBros responses receive request IDs, MIME-sniffing protection, clickjacking protection, referrer policy, permissions policy and cross-origin opener protection. The HTTPS edge additionally supplies HSTS and matching browser security headers. Company branch access is managed through the Governance API and important changes are written to the audit trail.

The internal `/metrics` endpoint is intentionally omitted from OpenAPI and is not routed by the public edge configuration. It is intended for host/internal-network observability only.

## Recovery

If a deployment fails after a migration or application change, preserve the current database volume first. Do not delete or recreate the production PostgreSQL volume as a rollback mechanism. Restore into a clean recovery database or host from the latest verified backup, validate the recovered schema/data, then deliberately switch service traffic after verification.

Uploads live in the `nbros_uploads` persistent volume and must be backed up separately from PostgreSQL. Redis is treated as reconstructable operational state and must never be the sole source of business records.
