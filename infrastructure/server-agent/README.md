# Ithute Server Agent v1

Read-only physical-server telemetry agent for the central Infrastructure → Servers inventory.

It reports CPU, memory, local disks, uptime, OS/kernel, Docker state and detected capabilities for PostgreSQL, MySQL/MariaDB, MongoDB, Redis and mail services.

The agent does **not** execute customer deployments or mailbox changes. Those privileged operations remain owned by the existing scoped Hosting Node and Mail Node agents.

## Install

Create/rotate the server-agent token from Infrastructure → Servers. Copy this directory to the target server, run `sudo ./install.sh`, set the token in `/etc/ithute/server-agent.env`, then restart the service.

The token is server-scoped and should never be placed in customer containers.
