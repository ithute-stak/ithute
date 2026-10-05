# Ithute Hardware Intelligence

This engine is the low-level Linux observation layer for Ithute Hardware Intelligence.

## Responsibility boundary

- C reads physical/OS telemetry exposed by Linux: /proc, /sys, hwmon, thermal, block-device and memory signals.
- eBPF observes kernel events that are difficult to infer from polling alone.
- Rust will validate and normalise untrusted native telemetry before it reaches the control plane.
- Go owns the long-running agent, batching, backoff and secure transport.
- Python/FastAPI remains authoritative for tenancy, server identity, persistence, health policy and prediction orchestration.
- Java will own alert and escalation workflows once the signal model is stable.

No C/eBPF code is allowed to authorize tenant actions, alter tenant state or perform remediation automatically.

## Phase 1 probe

Run make in this directory, then execute build/ithute-hw-probe.

The probe prints one versioned JSON sample to stdout. It is intentionally read-only and currently gathers:

- load averages
- uptime
- memory totals, available memory and swap
- CPU aggregate counters including iowait and steal
- thermal-zone temperatures when exposed by the host

Optional sensors are reported as unavailable instead of failing the sample.

## eBPF

The bpf/ithute_observer.bpf.c program is the first kernel-observability component. eBPF is opt-in because containerised VPS environments may not expose the required kernel capabilities.

Run make ebpf only on a supported Linux build host with Clang and libbpf headers.

Production loading will be implemented through a privilege-separated agent. Normal Ithute application containers must not receive broad host privileges.

## Telemetry contract

All agent output must conform to contracts/hardware-intelligence/telemetry-v1.schema.json.

The contract is versioned and additive so older agents can continue reporting during rolling upgrades.