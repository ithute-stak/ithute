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

## Privilege-separated eBPF loader

The normal Go hardware agent remains unprivileged. eBPF loading and map reads are isolated behind root-owned systemd units:

- `ithute-ebpf.service` loads only the Ithute BPF object and pins it below `/sys/fs/bpf/ithute_hardware`.
- `ithute-ebpf-snapshot.timer` refreshes a small JSON snapshot every 15 seconds.
- The snapshot is written atomically to `/run/ithute-hardware/ebpf.json` as root-owned, mode 0644.
- The Go agent reads that file only if it is not group/world writable and is no older than 90 seconds.

The loader never enumerates, detaches or deletes BPF programs outside the Ithute pin tree.

The current eBPF signal set contains cumulative block request issue/complete counts, process exits and OOM victims. These are useful for backlog and fault-growth detection. True request latency percentiles are still a separate roadmap item and must not be inferred from the current counters.


## Block request latency

The eBPF observer now correlates block request issue and completion events by kernel request identity and records the measured duration using `bpf_ktime_get_ns()`.

Latency is accumulated into 16 bounded histogram buckets from <=100 microseconds through an open-ended >2 second bucket. The privileged exporter calculates approximate p50, p95 and p99 values from those measured request durations and also exports average/max latency.

Because histogram buckets are cumulative from loader start, the backend derives interval percentiles from differences between consecutive signed samples before feeding them into per-server prediction. If a percentile lands in the open-ended final bucket, Ithute marks it as capped/lower-bound rather than pretending the exact latency is known.
