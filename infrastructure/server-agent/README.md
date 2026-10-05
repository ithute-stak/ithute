# Ithute Server Agent v2

Physical-server telemetry, container-inventory and guarded operations agent for Infrastructure → Servers.

It reports CPU, memory, local disks, uptime, OS/kernel, Docker state, managed-container inventory and detected capabilities for PostgreSQL, MySQL/MariaDB, MongoDB, Redis and mail services.

The agent can also claim a deliberately small allowlist of structured commands from Ithute:

- `agent.ping`
- `service.start`, `service.stop`, `service.restart`
- `container.start`, `container.stop`, `container.restart`

There is **no arbitrary shell command** capability. Connectivity-critical services such as SSH, networking and firewall services are rejected by the Ithute API before a command can be queued.

Container inventory includes the `ithute.project_id` label when present. The control plane compares those labels with projects assigned to the server's Hosting Node and records missing or unexpected managed containers as infrastructure drift.

The agent does **not** execute customer deployment build logic or mailbox changes. Those privileged workflows remain owned by the scoped Hosting Node and Mail Node agents.

## Install

Create/rotate the server-agent token from Infrastructure → Servers. Copy this directory to the target server, run `sudo ./install.sh`, set the token in `/etc/ithute/server-agent.env`, then restart the service.

The token is server-scoped and should never be placed in customer containers.

The systemd unit runs as root because infrastructure telemetry and guarded Docker/systemd actions require host visibility, but it is constrained with `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `RestrictSUIDSGID` and read-only filesystem policy outside the Ithute log path.
