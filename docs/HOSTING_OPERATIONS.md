# Ithute Application Hosting Operations

This document is the operator runbook for the release-management layer that sits on top of the Ithute Hosting Rules. The customer-facing rules remain authoritative for what workloads are allowed. This runbook describes how approved workloads move into production without giving customer code control of the shared VPS.

## Trust boundary

Ithute application hosting is managed shared hosting. The web/API control plane must never mount `/var/run/docker.sock`, receive root SSH credentials, create privileged customer containers, publish arbitrary host ports, or run untrusted customer build scripts on the production host.

Customer source is built in an approved isolated CI/builder. The output that crosses into production is an immutable container reference pinned by SHA-256 digest. Mutable tags such as `latest` are not deployment identities.

## Release flow

1. The organization creates a hosted project and accepts the current Hosting Rules version.
2. The project receives fixed storage, RAM, CPU and PID ceilings that fit both its commercial package and the hosting-node capacity ledger.
3. An isolated builder checks out the approved Git commit, builds/tests the application image, scans it according to the platform policy, and publishes it to the approved registry.
4. The builder/operator submits the exact `registry/repository@sha256:<digest>` plus the source commit to the project deployment API.
5. The control plane records an immutable deployment intent. It does not contact Docker directly.
6. The host-side Ithute node agent authenticates with its own node-scoped credential and claims the next queued deployment assigned to that node.
7. The manifest returned to the agent contains the immutable image, project limits, hostname/port/health configuration, decrypted project environment values, and the mandatory runtime security contract.
8. The agent starts the workload inside its project isolation boundary and reports `running` followed by `healthy`, or `failed` with a bounded diagnostic message.
9. Public routing is enabled only after workload health and hostname/TLS checks succeed. DNS management alone must never redirect an existing customer website to Ithute hosting.
10. A rollback creates a new release using an earlier healthy image digest. History is never rewritten in place.

## Runtime contract

Every customer workload must enforce all of the following regardless of runtime language:

- no privileged container mode;
- no Docker socket or host container-engine API;
- no arbitrary public host-port publishing;
- all Linux capabilities dropped unless a future explicitly reviewed platform profile adds a narrowly scoped exception;
- `no-new-privileges` enabled;
- read-only root filesystem where compatible with the runtime;
- the only normal persistent writable mount is the project-scoped data path (`/data` in the manifest contract);
- memory, CPU and PID limits exactly match or are stricter than the project allocation;
- customer traffic enters through Ithute edge/HTTPS routing only;
- one tenant/project must never mount another tenant/project storage or secrets.

## Environment variables and secrets

Project environment values are encrypted at rest by the control plane. After a value is written, browsers can list the key and metadata but cannot retrieve the stored value. Plaintext is only decrypted for the authenticated node agent while preparing a deployment manifest for a project assigned to that agent's node.

Changing an environment value does not mutate a historical deployment record. Operators should queue a new release/restart so the runtime receives the new configuration in a controlled operation.

Do not store Ithute control-plane database passwords, Docker-host credentials, PowerDNS API keys, central-auth service secrets, mail-server administrative credentials, or another customer's credentials inside a hosted project.

## Node-agent credentials

Each hosting node has its own credential. The system owner rotates it from the platform API. The plaintext credential is returned once; only its hash and a non-secret hint are stored centrally.

A node credential may claim and update only deployments assigned to that node. It is not a customer credential and must be stored on the host with operating-system permissions that prevent customer workloads from reading it.

Rotate the credential immediately after suspected disclosure, host rebuild, staff/offboarding event involving the secret, or any unexpected agent activity.

## Health and rollback

A release is not considered live merely because a container process starts. The node agent must report successful workload health. Only a deployment in `healthy` state is eligible as an explicit rollback target.

If a new deployment fails and the project already has an older healthy release, the control-plane project remains logically recoverable/running rather than deleting the previous healthy history. The agent/runtime layer should preserve or restore the last healthy route during production rollout.

## Capacity and overselling

The package is one gate and the node ledger is another. The system owner should register less than the physical machine's total resources as sellable capacity, leaving reserve for the operating system, Ithute control plane, PowerDNS, mail, databases, Caddy, monitoring, backup jobs, filesystem metadata and traffic spikes.

Application storage and professional-email storage are separate entitlements. Backup retention is also operational overhead and must not be counted as permission for a live project to exceed its app-storage allocation.

## Databases

When managed application databases are introduced, each project must receive a project-scoped database and least-privilege database user. Never give a hosted project the Ithute application database owner/superuser credential. Database allocation, backup and restore must eventually be accounted for separately from the application-container lifecycle.

## Incident controls

The platform owner may suspend a project that threatens shared-service availability, violates the Hosting Rules, exceeds its entitlement, or is implicated in abuse. Suspension should stop public execution/routing while preserving customer data unless a separate authorized destructive action is taken.

Audit events should identify deployment requests, rollbacks, environment-key changes, agent-credential rotation, node health and future public-route activation so the operator can reconstruct what changed and when.

## What is still required before fully automated public hosting

The control-plane release API and agent protocol deliberately do not by themselves grant the VPS Docker access. Before automatic customer runtime activation is enabled, the host-side agent implementation must be deployed with the isolation flags above, a private per-project networking strategy, safe image-registry authentication, persistent-storage quota enforcement, Caddy route/TLS reconciliation, log/metrics collection, cleanup semantics and backup/restore integration.

Until those host-side controls are deployed and verified, queued releases are an operational control-plane capability rather than permission to bypass the documented trust boundary.
