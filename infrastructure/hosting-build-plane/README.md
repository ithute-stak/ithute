# Ithute Hosting Build Plane

This Compose project packages the untrusted-source side of Ithute shared hosting. It is intentionally separate from the normal Ithute production Compose project and from every hosting-node runtime.

## Required topology

Run this project on a **dedicated build host**. The builder has access to that host's Docker daemon so it can execute isolated BuildKit builds. For that reason, this host must not run Ithute web/auth/mail databases, LoanHub, Khanya, customer production containers, or other application workloads.

The project contains:

- `edge`: public HTTPS ingress for ZIP upload only;
- `upload`: validates one-time upload tickets and quarantines ZIP files before atomic promotion into verified storage;
- `builder`: polls the control plane, materializes verified Git/ZIP source, builds managed runtime images and pushes immutable images to the approved registry namespace.

`upload` never receives the Docker socket. `builder` receives verified ZIP storage read-only. Neither service joins Ithute application, database, mail, Auth, Push or Realtime networks.

## Filesystem boundary

The host bootstrap prepares:

```text
/srv/ithute-hosting-build-plane/
  quarantine/    # upload service only; untrusted archives
  verified/      # upload service writes; builder reads only
  builder-work/  # temporary builder workspaces
```

The verified archive tree is never writable from the builder container.

## First installation

From this directory on the dedicated build host:

```sh
sudo ./bootstrap-host.sh
cp .env.example .env
```

Populate `.env` with protected runtime values. Do not commit `.env`.

The platform owner must create:

- an `ith_upload_...` upload-service credential;
- an `ith_build_...` builder credential.

Populate the pinned Git `known_hosts` file and authenticate the host-managed Docker config to the approved `ghcr.io/ithute-stak/hosted-*` registry namespace.

Validate before starting:

```sh
docker compose --env-file .env -f compose.yml config
docker compose --env-file .env -f compose.yml build --pull
docker compose --env-file .env -f compose.yml up -d
```

## DNS and TLS

Point the dedicated upload hostname, normally `upload.ithute.co.ls`, at this build host. Caddy obtains and renews TLS automatically. Only `/healthz` and `/v1/uploads/*` are routed to the upload service.

The browser still talks to the normal Ithute control plane for source registration. The returned one-time ZIP credential is then used directly against the upload hostname; the main API never receives the archive bytes.

## Firewall policy

Ingress should permit only TCP 80/443 for Caddy and administrative access from trusted operator networks. Do not expose port `8096` publicly.

Outbound policy should be allow-listed where practical for:

- `ithute.co.ls` control-plane HTTPS;
- approved Git providers/source hosts;
- package registries required by managed runtimes;
- `ghcr.io` and its required registry endpoints;
- DNS/NTP needed by the host.

There must be no route from this host to production database administration endpoints, hosting-node Docker sockets, mail administration interfaces, or private customer workload networks.

## Registry and Docker boundary

The builder container gets `/var/run/docker.sock` only because this is a dedicated build host. The Docker daemon on this host must never run customer production workloads. Build results are pushed to the registry; production hosting nodes consume only immutable digest-pinned images through the separate hosting-agent workflow.

Custom customer Dockerfiles remain disabled by default. Enabling them is a separate operational decision and should be accompanied by a stronger BuildKit sandbox policy.

## Recovery

`quarantine/` and `builder-work/` are disposable. `verified/` is retained according to the hosting source-retention policy and should be backed up only if the product retention policy requires preserving uploaded source archives. Registry images and control-plane records remain separate from this host.
