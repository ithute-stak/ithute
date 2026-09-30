# Ithute Isolated Hosting Builder

The hosting builder is the trust boundary that converts approved customer source into immutable application images. It must run separately from the production hosting-node agent.

## Boundary

The builder may:

- claim queued build jobs from the Ithute control plane;
- clone the Git source for that one job;
- receive the source credential only for that claimed job;
- validate source size, file count, symlink boundaries and runtime markers;
- build managed runtime images with Ithute-generated Dockerfiles;
- push images only to the approved `ghcr.io/ithute-stak/hosted-*` namespace;
- return the resulting immutable registry digest.

The builder must **not**:

- receive `ITHUTE_HOSTING_AGENT_TOKEN`;
- receive production-node SSH credentials;
- activate or restart production customer containers;
- have access to production customer volumes or databases;
- reuse customer Git credentials after the claimed job;
- report a successful build without an immutable registry digest.

The production hosting-node agent remains the only component allowed to activate a digest-pinned image on a hosting node.

## Required environment

```text
ITHUTE_API_URL=https://ithute.co.ls
ITHUTE_HOSTING_BUILDER_TOKEN=ith_build_<one-time-token>
ITHUTE_HOSTING_BUILDER_WORK_ROOT=/var/lib/ithute-builder/work
ITHUTE_HOSTING_BUILDER_KNOWN_HOSTS=/etc/ithute-builder/known_hosts
ITHUTE_HOSTING_BUILDER_POLL_SECONDS=15
ITHUTE_HOSTING_BUILDER_DOCKER=docker
ITHUTE_HOSTING_BUILDER_ALLOW_CUSTOM_DOCKERFILE=false
```

The builder host must also be authenticated to the approved image registry through a host-managed credential. Registry credentials are operational secrets and are never returned by the Ithute customer API.

## Network policy

Run this service on a dedicated builder VM/container host or equivalent sandbox. Its outbound network policy should allow only what a build requires, normally:

- the Ithute API;
- approved Git providers / customer source hosts;
- approved package registries used by managed runtimes;
- the Ithute container registry.

It should have no route to production private database/admin endpoints, Docker APIs on hosting nodes, mail administration, or other customer networks.

## Managed runtimes

Ithute currently supplies managed templates for:

- static HTML/CSS/JavaScript;
- Node.js;
- Python;
- PHP;
- .NET;
- Java;
- Go;
- Ruby;
- Rust.

The project can provide an optional build command and start command. Ithute may infer a simple start command for common layouts, but Java, .NET and non-standard applications should set an explicit start command.

Custom customer Dockerfiles are disabled by default. Enabling `ITHUTE_HOSTING_BUILDER_ALLOW_CUSTOM_DOCKERFILE=true` should be treated as a separately reviewed operational policy because Dockerfiles can execute arbitrary build-time instructions.

## Git credential handling

HTTPS tokens use a temporary `GIT_ASKPASS` helper and are never embedded into repository URLs. SSH keys are written only to a temporary `0600` file and require a pinned `known_hosts` file with strict host-key verification. Temporary credential files are deleted after checkout.

## Source limits

Git checkouts are rejected when they exceed either:

- 100,000 files; or
- 2 GiB unpacked source data.

Symlinks resolving outside the checkout root are rejected.

ZIP source is intentionally not consumed by this worker until Ithute's separate upload/quarantine service verifies checksum, path traversal, compression ratio and unpacked-size limits.

## Image promotion

A managed build uses Docker Buildx to push an image. The builder reads the registry digest from BuildKit metadata and reports only:

```text
ghcr.io/ithute-stak/hosted-<project>@sha256:<64-hex-digest>
```

The control plane validates the namespace and digest before creating a `HostingDeployment`. Production then applies its independent runtime security checks before promotion.

## Operational prerequisites before production enablement

Before running the builder against real customer repositories, Ithute operations must provide all of the following:

1. a dedicated builder host or equally isolated execution environment;
2. Docker Buildx/BuildKit with no production-host Docker context configured;
3. registry credentials restricted to the hosted-image namespace;
4. a pinned `known_hosts` file for approved SSH Git hosts;
5. outbound firewall rules that deny production private/admin networks;
6. disk quotas and scheduled cleanup for the builder work root;
7. registry retention/garbage-collection policy for superseded build tags;
8. monitoring for queue latency, build failures, disk pressure and builder heartbeat age.

Do not place the builder token, registry password or customer source credentials in Git, application environment variables exposed to hosted workloads, or production host-agent configuration.
