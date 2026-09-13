# Ithute Hosting Node Agent

The hosting node agent is the privileged runtime boundary for managed customer applications. It is deliberately separate from the Ithute web/API containers.

## Security boundary

The application API **must not** receive the Docker socket, host SSH credentials, or privileged-container access. It only writes deployment requests to the database. A node-local agent authenticates with a one-time provisioned node token, claims work assigned to that node, and performs the runtime activation.

The agent accepts only:

- OCI image references pinned by `@sha256:<digest>`;
- images in the approved `ghcr.io/ithute-stak/hosted-` namespace;
- images that are already loaded on the node by a separate isolated builder/transfer stage;
- images that declare a non-root `USER`.

The agent does **not** clone repositories, run customer Dockerfiles/build scripts, log in to GHCR, or pull arbitrary images on the production VPS.

## Runtime isolation

For every project the agent creates a dedicated Docker bridge network and persistent data volume. The workload is started with:

- no public host port;
- `--read-only` root filesystem;
- `/tmp` as a bounded tmpfs;
- `/data` as the project persistent volume;
- `no-new-privileges`;
- all Linux capabilities dropped;
- package CPU, RAM, and PID limits;
- a non-root image user.

A candidate deployment is health-checked on its private container address before promotion. If a candidate fails, it is deleted and the previous application container is restarted. Persistent application data is intentionally not rolled back with an image rollback.

## Provisioning

1. Register the hosting node in **Packages & Capacity**.
2. As System Owner, request/rotate the node agent token using `POST /api/v1/platform/hosting/nodes/{node_id}/agent-token`.
3. Store the returned token only on the target node. Ithute stores only its SHA-256 hash.
4. Configure the agent environment:

```text
ITHUTE_API_URL=https://ithute.co.ls
ITHUTE_HOSTING_NODE_ID=<hosting-node-uuid>
ITHUTE_HOSTING_AGENT_TOKEN=<one-time-token>
ITHUTE_HOSTING_POLL_SECONDS=15
```

5. Run `agent.py` as a restricted systemd service account that is allowed to invoke Docker for hosted workloads.

Do not put the node token in the repository, Compose files, public environment output, or customer project settings.

## Still separate by design

This agent is the **runtime activator**, not the builder. The next builder stage must check out customer source in an isolated GitHub/ephemeral runner, produce an immutable image, scan it, transfer/load the exact digest onto the assigned node, and only then enqueue deployment. Public Caddy hostname activation is also kept separate so a healthy container cannot claim an unverified hostname.
