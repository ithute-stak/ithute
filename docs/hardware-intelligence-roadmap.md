# Ithute Hardware Intelligence implementation roadmap

Branch foundation: feature/hardware-intelligence-foundation

## Goal

Detect infrastructure degradation early, then progress from deterministic warnings to evidence-based predictive alerts without giving low-level agents authority over Ithute business state.

## Architecture

C hardware probe + eBPF kernel signals -> Rust validation/hardening -> Go long-running monitoring agent -> Python/FastAPI control plane (PostgreSQL history + Redis/realtime) -> Python anomaly/prediction engine -> Java alert/escalation workflows -> Ithute dashboard + iMail/Push notifications.

## Delivery phases

### Phase 1 - Foundation
- [x] Add C hardware probe.
- [x] Add initial read-only eBPF counters.
- [x] Define telemetry v1 JSON contract.
- [x] Add Go sampling agent command.
- [ ] Add CI compilation and contract tests.
- [ ] Add capability detection so eBPF is never assumed to be available.

### Phase 2 - Core agent
- [ ] Add SMART/NVMe collection through bounded helpers.
- [ ] Add hwmon/IPMI/EDAC/ECC adapters where the host exposes them.
- [ ] Add eBPF loader with least-privilege capability checks.
- [ ] Add local buffering, jitter, backoff and batch compression.
- [ ] Sign agent identity and bind reports to an Ithute infrastructure-server record.
- [ ] Add Rust telemetry normalisation/validation boundary.

### Phase 3 - Backend integration
- [ ] Persist immutable telemetry samples with retention/downsampling policy.
- [ ] Add agent-ingest endpoint with service authentication and replay protection.
- [ ] Publish current health through Ithute Realtime.
- [ ] Add deterministic warning/critical policies.
- [ ] Add System Owner hardware-health API and dashboard.

### Phase 4 - Predictive analytics
- [ ] Baseline each server instead of using one global normal range.
- [ ] Add trend/anomaly features for temperature, memory pressure, disk latency/errors, CPU steal/iowait and network errors.
- [ ] Train and validate failure-risk scoring against historical incidents.
- [ ] Require confidence plus evidence before presenting a predictive warning.
- [ ] Track model version, false positives and operator acknowledgement.

### Phase 5 - Enterprise response
- [ ] Java policy workflow for escalation, maintenance tasks and notification routing.
- [ ] Integrate iMail, Ithute Push and approved SMS/WhatsApp channels.
- [ ] Role-based acknowledgement, maintenance windows and suppression.
- [ ] Multi-tenant and multi-server fleet health views.

### Phase 6 - Production rollout
- [ ] Pilot on selected Ithute-managed servers.
- [ ] Tune thresholds and permissions.
- [ ] Roll out by infrastructure pool.
- [ ] Measure agent overhead, alert precision and incident lead time.
- [ ] Document operations, runbooks and recovery procedures.

## Safety rules

1. Monitoring is read-only by default.
2. eBPF is optional and capability-gated.
3. No automatic reboot, disk repair, filesystem mutation or service termination in the prediction path.
4. A hardware alert must state the evidence used to produce it.
5. Cloud VPS hosts may hide physical sensors; Ithute must label unavailable signals rather than infer them.
6. Python remains the authority for tenancy, identity, health policy and persistence.