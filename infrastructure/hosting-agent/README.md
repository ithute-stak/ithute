# Ithute Hosting Node Agent

The hosting node agent is the privileged runtime boundary for managed customer applications. It runs on an Ithute hosting node and is deliberately separate from the public web/API containers.

## What the API can do

The Ithute control plane can validate a project, store encrypted environment values, queue an immutable release and issue a constrained runtime manifest. It **must not** receive the Docker socket, host SSH credentials, privileged-container access or customer-facing public ports.

## What the node agent can do

The agent authenticates with the one-time node credential issued from **Hosting Nodes**, claims only work assigned to that node and activates only an image that:

- is pinned by `@sha256:<digest>`;
- is inside the approved `ghcr.io/ithute-stak/hosted-` namespace (or an explicitly configured replacement);
- is already present on the node from the isolated builder/transfer stage;
- declares a non-root image `USER`.

The agent never clones a customer repository, runs a customer build, logs in to a customer source provider or pulls an arbitrary image on the production VPS.

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

Environment values are passed to the Docker client through the child process environment rather than being embedded as values in the command line. They are still visible to trusted host/Docker administrators by design; customers never receive host or Docker access.

A candidate is checked over its private project network. The previous container is kept as a stopped backup until the control plane acknowledges the healthy release. If activation or acknowledgement fails, the candidate is removed and the previous container is restored.

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
```

5. Run `agent.py` as a dedicated systemd service account permitted to manage only the Ithute hosted-workload Docker boundary.

Never commit the node token or put it into customer project settings.

## Still separate

The builder/image-transfer pipeline and verified-hostname Caddy activation remain separate trust boundaries. A healthy container does not by itself obtain public ingress, and production nodes do not build customer source code.
