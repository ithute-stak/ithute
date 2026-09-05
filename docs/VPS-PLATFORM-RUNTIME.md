# Ithute VPS Platform Runtime

The production VPS uses `/home/administrator/mailbox-dns` as the mother runtime for Mailbox and Ithute products.

## Target layout

```text
/home/administrator/mailbox-dns/
├── docker-compose.yml
├── docker-compose.prod.yml
├── docker-compose.ithute-platform.yml
├── backups/
├── platform-secrets/
├── infra/
├── infrastructure/
├── scripts/
└── loanhub/
    ├── compose.yaml
    ├── .env.production
    ├── infra/caddy/Caddyfile
    ├── secrets/
    └── backups/
```

`/opt/containerd` is container-runtime infrastructure and is not moved by Ithute application deployments.

## LoanHub first transition from `/opt/loanhub`

The LoanHub production workflow treats `/opt/loanhub` as a legacy runtime source only. On the first deployment to the platform root it:

1. Requires `/home/administrator/mailbox-dns` to already exist.
2. Creates `/home/administrator/mailbox-dns/loanhub`.
3. Copies the existing `.env.production` and, when the new secrets directory is empty, the existing LoanHub secrets from `/opt/loanhub`.
4. Leaves `/opt/loanhub` untouched as a rollback reference.
5. Requires the existing Docker volume `${COMPOSE_PROJECT_NAME:-loanhub}_postgres_data` to exist before starting PostgreSQL.
6. Starts PostgreSQL and verifies `/var/lib/postgresql/data` is mounted from that exact existing volume.
7. Creates a PostgreSQL custom-format dump and SHA-256 checksum in the new LoanHub backup directory.
8. Runs Alembic only after the backup succeeds.
9. Starts the new backend/frontend/maintenance/Caddy containers and performs public health checks.

The workflow deliberately contains no `docker compose down -v` or `docker volume rm` command.

## Data ownership

Moving the runtime directory does not move LoanHub business data into Mailbox. LoanHub PostgreSQL remains the owner of LoanHub companies, borrowers, loans, payments, accounting, HRMS, collections, treasury, documents and reporting data. The Ithute control plane stores only operational metadata such as product registration, health, deployment/backup status, events, licensing and security metadata.

## Stable Compose identity

Production must keep:

```env
COMPOSE_PROJECT_NAME=loanhub
```

Do not change that value on an existing production server without an explicit volume migration plan. It controls the named-volume prefix, including `loanhub_postgres_data`.

## Required GitHub secrets

The LoanHub product deployment uses:

- `VPS_SSH_KEY`
- optional `VPS_SSH_PASSPHRASE`
- `GHCR_TOKEN`

The VPS host, production user, GHCR username and platform root are repository workflow configuration because they are not credentials.
