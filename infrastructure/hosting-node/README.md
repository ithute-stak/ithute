# Ithute Shared Hosting Node

This directory packages the **production runtime host boundary** for Ithute shared hosting. It is separate from the public Ithute control plane and from the isolated build plane.

A hosting node runs customer application containers and, when enabled, dedicated PostgreSQL/MySQL services for hosted customers. It must **not** be a LoanHub, Khanya, Tutor, NBros, Ithute control-plane, or build-plane host.

## Security model

- Customer applications never receive host SSH, the Docker socket, database-admin credentials, or another customer's secrets.
- The production agent entrypoint is `agent_v4.py`.
- Every project receives a dedicated Docker bridge subnet from `ITHUTE_HOSTING_NETWORK_POOL` (default `10.240.0.0/12`, `/28` per project).
- `apply-egress-firewall.sh` protects the entire reserved pool in `DOCKER-USER` **before** customer containers start.
- Private/link-local/metadata destinations and arbitrary outbound ports are denied. DNS, HTTP, HTTPS and the configured local DB gateway are the only default exceptions.
- The firewall script changes only the Ithute custom chain and its one reserved-pool jump. It does not flush the VPS firewall or prune Docker resources.
- `validate-host.sh` fails if database listeners are wildcard/public, if an unrelated Docker network overlaps the reserved pool, if the egress policy is missing, or if known foreign product containers are present.

## PostgreSQL ownership model

PostgreSQL should run as a **dedicated Ithute hosting database service**. The hosting agent uses `ithute_hosting_admin`, which needs `CREATEDB` and `CREATEROLE` but must not be SUPERUSER.

Run `postgresql-bootstrap.sql` once as the cluster administrator and provide a protected `hosting_admin_password` psql variable. The v4 agent then:

1. creates a project-scoped customer login role;
2. creates the database as `ithute_hosting_admin`, so the admin can later drop it without SUPERUSER;
3. revokes PostgreSQL's default `PUBLIC` `CONNECT`/`TEMPORARY` access on the database;
4. grants only the customer role `CONNECT` and `TEMPORARY`;
5. revokes `PUBLIC CREATE` on the `public` schema;
6. grants only the customer role `USAGE, CREATE` on that schema;
7. runs PostgreSQL backup/restore with `--role <customer-role>`, preserving customer ownership of application objects.

The agent refuses to delete or restore a PostgreSQL database whose database owner is not the configured Ithute hosting admin. Legacy test databases created with customer database ownership must be migrated deliberately before using v4 production lifecycle operations.

### PostgreSQL listener / HBA requirements

The admin connection should remain loopback/private, for example `127.0.0.1:5432`. Customer containers connect through the fixed `ithute-db-gateway` host alias. PostgreSQL therefore needs a private listener reachable at the Docker host gateway, **not** `0.0.0.0`.

`pg_hba.conf` should allow only the reserved hosted source pool with password authentication, for example conceptually:

```text
hostssl all all 10.240.0.0/12 scram-sha-256
```

Use the actual configured pool and require TLS if the node's PostgreSQL deployment supports it. Do not expose TCP/5432 on a public interface or security group.

## MySQL ownership model

MySQL must also be a **dedicated Ithute hosting database service**. The current agent creates/deletes databases and customer users dynamically and grants each customer user rights over its database. The administrative account therefore has broad lifecycle/grant capability within that MySQL instance.

Do **not** point `ITHUTE_HOSTING_MYSQL_ADMIN_*` at a MySQL instance that contains LoanHub, Khanya, mail, finance, or unrelated application schemas. Keep the MySQL listener on loopback/private interfaces and expose TCP/3306 only to the reserved hosted network pool through the node firewall.

A narrower MySQL privilege broker can be added later, but the safe current production boundary is a dedicated hosted-customer MySQL instance.

## Installation layout

Recommended host paths:

```text
/etc/ithute-hosting-node/agent.env                 # mode 0600
/opt/ithute-hosting-agent/agent.py
/opt/ithute-hosting-agent/agent_v3.py
/opt/ithute-hosting-agent/agent_v4.py
/opt/ithute-hosting-agent/network_policy.py
/var/lib/ithute-hosting/database-backups/
/etc/systemd/system/ithute-hosting-agent.service
```

Create a dedicated `ithute-hosting-agent` system user, add only that account to the Docker group, and copy `agent.env.example` to the protected environment file. The provided systemd unit runs v4 with a read-only host filesystem except for `/var/lib/ithute-hosting`.

Required host utilities depend on enabled engines:

- Docker Engine / CLI;
- Python 3.12+;
- `iptables` and `ss`;
- PostgreSQL client tools: `psql`, `createdb`, `dropdb`, `pg_dump`, `pg_restore`;
- MySQL client tools: `mysql`, `mysqldump`.

## Bring-up order

1. Prepare a **dedicated hosting node**.
2. Reserve a private Docker CIDR that does not overlap any existing host/VPC/Docker network.
3. Configure private PostgreSQL/MySQL listeners and authentication.
4. Bootstrap the PostgreSQL admin role if PostgreSQL is enabled.
5. Install `agent_v4.py`, its base modules, environment file, and systemd unit.
6. Run `apply-egress-firewall.sh` before starting customer workloads.
7. Run `validate-host.sh`; do not proceed unless it passes.
8. Register/rotate the one-time node token in Ithute and store it only in `agent.env`.
9. Start `ithute-hosting-agent.service`.
10. Deploy a disposable test project and database, verify outbound web access, verify RFC1918/metadata/SMTP blocking, test DB provision/rotate/suspend/resume/delete, then test backup + suspended restore.

## What is still a production validation task

These files make node setup reproducible and fail-closed, but they do not claim a VPS has already been validated. Before PR #219 is merged, a real dedicated hosting node still needs an end-to-end deployment exercise covering:

- firewall persistence across reboot and Docker restart;
- actual Docker/VPC CIDR non-overlap;
- PostgreSQL/MySQL private listeners and authentication;
- registry/image transfer into the runtime node;
- Caddy/public ingress from verified domains to healthy private containers;
- database backup replication off the node and node-loss restore;
- resource pressure and abuse tests.
