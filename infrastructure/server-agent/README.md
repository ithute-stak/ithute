# Ithute Server Agent v3

Physical-server telemetry, container-inventory, host-security posture and guarded operations agent for Infrastructure → Servers.

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


## Host security posture

Version 3 adds read-only security evidence inspired by the consumed VPS control-plane donor:

- effective SSH root-login and password-authentication policy;
- host firewall presence/state;
- Fail2ban state;
- unattended security-update state;
- Docker socket permissions;
- count of running privileged containers;
- public listeners for common database/cache ports;
- availability of restic/rclone backup tooling.

The agent reports evidence only. The Ithute control plane performs the authoritative scoring and recommendations. Security findings are canonicalized and fingerprinted through Ithute's Rust SHA-256 engine, while role-aware network readiness probes use the Go worker. Java and C++ continue to serve their specialist enterprise/XML and benchmarked native workloads through the common engine router.

## Cluster awareness

Every trusted server agent now downloads a sanitized cluster directory from the Ithute control plane and stores it at `/var/lib/ithute/server-agent/cluster-state.json` by default. This lets each VPS know which other Ithute nodes exist, their roles, online/health state, WireGuard private address, workload counts, resource pressure, capabilities, and container/service inventory.

Cluster awareness is intentionally **read-only discovery**, not peer shell access. The directory never contains agent tokens, passwords, environment variables, private keys, customer secrets, or arbitrary command capability. Node-to-node application traffic should continue to use the managed WireGuard network and explicit service authorization.

The cache is replaced atomically on each agent cycle, so local automation can read a consistent snapshot even if the control plane is temporarily unreachable.
