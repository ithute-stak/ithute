# Ithute Hosting Node Agent

The hosting node agent is the privileged runtime boundary for managed customer applications and shared customer databases. It runs on an Ithute hosting node and is deliberately separate from the public web/API containers.

## What the API can do

The Ithute control plane can validate a project, store encrypted environment values, queue an immutable release, issue a constrained runtime manifest, and queue project-scoped PostgreSQL/MySQL lifecycle jobs. It **must not** receive the Docker socket, host SSH credentials, privileged-container access, database-admin credentials, or customer-facing public ports.

## What the node agent can do

The agent authenticates with the one-time node credential issued from **Hosting Nodes**, claims only work assigned to that node, and activates only an image that:

- is pinned by `@sha256:<digest>`;
- is inside the approved `ghcr.io/ithute-stak/hosted-` namespace (or an explicitly configured replacement);
- is already present on the node from the isolated builder/transfer stage;
- declares a non-root image `USER`.

The same agent can provision project-scoped PostgreSQL or MySQL databases using node-local admin credentials. Those admin credentials stay on the node. The control plane sends only the generated customer database name, user and password for the specific operation.

The agent never clones a customer repository, runs a customer build, logs in to a customer source provider, pulls an arbitrary image on the production VPS, or returns database-admin credentials to the API.

## Runtime enforcement

Each project receives a dedicated Docker bridge network and persistent data volume. The agent enforces the server-issued manifest with:

- no host/public port publishing;
- a read-only root filesystem;
- bounded `/tmp` tmpfs;
- `/data` as the only project persistent mount;
- `no-new-privileges`;
- every Linux capability dropped;
- package CPU, RAM and PID ceilings;
- a non-root image user.

Hosted containers receive a fixed `ithute-db-gateway` host alias for access to node-local shared database services. Database services must be bound only to the hosting node's private/host interface and protected by host firewall rules; they must never be exposed as public Internet services.

Environment values are passed to the Docker client through the child process environment rather than being embedded as values in the command line. PostgreSQL/MySQL admin passwords are also passed through child-process environment variables (`PGPASSWORD` / `MYSQL_PWD`) rather than command-line arguments. They are still visible to trusted host administrators by design; customers never receive host, Docker or database-admin access.

A candidate application is checked over its private project network. The previous container is kept as a stopped backup until the control plane acknowledges the healthy release. If activation or acknowledgement fails, the candidate is removed and the previous container is restored.

## Provisioning

1. Register sellable node capacity in **Packages & Capacity**.
2. In **Hosting Nodes**, create/rotate the node credential.
3. Store the returned credential only on the target host.
4. Configure the service environment:

```text
ITHUTE_API_URL=https://ithute.co.ls
ITHUTE_HOSTING_AGENT_TOKEN=ith_host_<one-time-value>
ITHUTE_HOSTING_POLL_SECONDS=15
ITHUTE_HOSTING_HEARTBEAT_SECONDS=60
ITHUTE_HOSTING_IMAGE_PREFIX=ghcr.io/ithute-stak/hosted-

# PostgreSQL shared service (optional; required to sell PostgreSQL)
ITHUTE_HOSTING_POSTGRES_ADMIN_HOST=127.0.0.1
ITHUTE_HOSTING_POSTGRES_ADMIN_PORT=5432
ITHUTE_HOSTING_POSTGRES_ADMIN_USER=ithute_hosting_admin
ITHUTE_HOSTING_POSTGRES_ADMIN_PASSWORD=<node-secret>
ITHUTE_HOSTING_POSTGRES_ADMIN_DATABASE=postgres
ITHUTE_HOSTING_POSTGRES_HOST=ithute-db-gateway
ITHUTE_HOSTING_POSTGRES_PORT=5432

# MySQL shared service (optional; required to sell MySQL)
ITHUTE_HOSTING_MYSQL_ADMIN_HOST=127.0.0.1
ITHUTE_HOSTING_MYSQL_ADMIN_PORT=3306
ITHUTE_HOSTING_MYSQL_ADMIN_USER=ithute_hosting_admin
ITHUTE_HOSTING_MYSQL_ADMIN_PASSWORD=<node-secret>
ITHUTE_HOSTING_MYSQL_HOST=ithute-db-gateway
ITHUTE_HOSTING_MYSQL_PORT=3306
```

5. Install the PostgreSQL client utilities (`psql`, `createdb`, `dropdb`) and/or the MySQL client on nodes that sell those database engines.
6. Run `agent.py` as a dedicated systemd service account permitted to manage only the Ithute hosted-workload Docker boundary and the configured shared database services.

The PostgreSQL/MySQL admin account should have only the rights required to create, alter, lock/unlock and remove customer databases/users. Do not use the database superuser if a narrower administrative role can satisfy those operations.

Never commit the node token or database-admin secrets, and never put them into customer project settings.

## Database lifecycle

The control plane queues database operations and the node agent claims them using the same node credential as deployments. Supported operations are:

- provision database + project-scoped user;
- rotate the generated user password;
- suspend access (`NOLOGIN` / account lock);
- resume access;
- delete the database and its project-scoped user.

Customer passwords are generated by the control plane and shown to the customer only when created or rotated. Ithute stores the customer password encrypted at rest so the node agent can apply lifecycle operations later.

## Still separate

The builder/image-transfer pipeline, verified-hostname Caddy activation, database backup/restore pipeline, storage metering and ZIP quarantine scanner remain separate trust boundaries. A healthy container does not by itself obtain public ingress, and production nodes do not build customer source code.
