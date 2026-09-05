# Phase 12 — Monitoring & Operations

Phase 12 makes Mailbox-DNS observable as an operated mail and DNS platform rather than only a collection of healthy containers.

## Accepted monitoring surface

The backend exposes Prometheus request counters, latency histograms, and PostgreSQL/Redis dependency readiness. Prometheus also scrapes host and container telemetry, synthetic SMTP/IMAP/authoritative-DNS probes, and the operations exporter for Postfix queue and backup status.

Grafana is provisioned with an operations dashboard and an SLO/error-budget dashboard. Alertmanager receives Prometheus alerts. Monitoring endpoints must remain private or be placed behind authenticated operator access in production.

## Platform-owner operations API

The control plane exposes two platform-owner-only endpoints:

- `GET /api/v1/operations/status` — backend, SMTP, IMAP, authoritative DNS, backup and queue summary sourced from Prometheus.
- `GET /api/v1/operations/slo` — seven-day availability objective, error-budget remaining, and one-hour burn-rate telemetry.

The API deliberately returns `503` when Prometheus is unavailable rather than presenting stale telemetry as healthy.

## SLO model

The Phase 12 operational objective is 99.9% control-plane request availability over a seven-day window. Prometheus recording rules calculate seven-day availability, normalized error-budget remaining, and one-hour error-budget burn rate. This is an operational objective and does not constitute a contractual SLA.

The fast-burn alert fires when the one-hour burn rate is above 10x. A seven-day availability warning fires when recorded availability is below 99.9%.

## Alert metadata

Operational alerts carry a component label plus a runbook and operator-action annotation. Alert routing is intentionally generic in the repository; production destinations such as email, webhook, PagerDuty-compatible services, or other incident systems must be configured with deployment secrets outside source control.

## Production boundary

Prometheus, Grafana and Alertmanager should not be exposed directly to the public Internet. Persist Prometheus/Grafana state on reliable storage, protect Grafana credentials, monitor the monitoring stack itself, and retain enough metrics history for the chosen SLO window. Synthetic probes should eventually include external probes from an independent network so internal Docker reachability is not mistaken for public service availability.

## Incident operating sequence

Use `docs/PHASE-12-INCIDENT-OPERATIONS.md` for triage. Prioritize public DNS, SMTP/IMAP reachability, control-plane dependencies, queue pressure, storage capacity and backup freshness. Preserve evidence before destructive queue, database or restore actions.

## Phase 12 acceptance

Phase 12 is accepted only when the Phase 11 verifier remains green and the Phase 12 verifier proves application metrics, validated Prometheus and alert rules, SMTP/IMAP/DNS synthetic probes, queue and backup telemetry, Alertmanager readiness, Grafana provisioning, platform-owner operations routes, SLO/error-budget recording rules, alert runbook metadata and backend unit coverage.
