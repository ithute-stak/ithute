package main

import (
	"encoding/json"
	"fmt"
	"os"
	"time"
)

type EBPFSnapshot struct {
	Available              bool   `json:"available"`
	Reason                 string `json:"reason,omitempty"`
	SampledAtUnix          int64  `json:"sampled_at_unix,omitempty"`
	BlockRequestsIssued    uint64 `json:"block_requests_issued,omitempty"`
	BlockRequestsCompleted uint64 `json:"block_requests_completed,omitempty"`
	ProcessExits           uint64 `json:"process_exits,omitempty"`
	OOMVictims             uint64 `json:"oom_victims,omitempty"`
	BlockLatencyCount      uint64 `json:"block_latency_count,omitempty"`
	BlockLatencyAvgMS      *float64 `json:"block_latency_avg_ms,omitempty"`
	BlockLatencyMaxMS      *float64 `json:"block_latency_max_ms,omitempty"`
	BlockLatencyP50MS      *float64 `json:"block_latency_p50_ms,omitempty"`
	BlockLatencyP95MS      *float64 `json:"block_latency_p95_ms,omitempty"`
	BlockLatencyP99MS      *float64 `json:"block_latency_p99_ms,omitempty"`
	BlockLatencyHistogram  []uint64 `json:"block_latency_histogram,omitempty"`
}

func readEBPFSnapshot(path string, maxAge time.Duration) (EBPFSnapshot, error) {
	var snapshot EBPFSnapshot
	if path == "" {
		return snapshot, nil
	}
	info, err := os.Stat(path)
	if err != nil {
		if os.IsNotExist(err) {
			return snapshot, nil
		}
		return snapshot, fmt.Errorf("stat eBPF snapshot: %w", err)
	}
	if info.Mode().Perm()&0o022 != 0 {
		return snapshot, fmt.Errorf("eBPF snapshot must not be group/world writable")
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return snapshot, fmt.Errorf("read eBPF snapshot: %w", err)
	}
	if len(raw) > 64*1024 {
		return snapshot, fmt.Errorf("eBPF snapshot exceeds 64KiB safety limit")
	}
	if err := json.Unmarshal(raw, &snapshot); err != nil {
		return snapshot, fmt.Errorf("invalid eBPF snapshot JSON: %w", err)
	}
	if snapshot.Available {
		if snapshot.SampledAtUnix <= 0 {
			return EBPFSnapshot{}, fmt.Errorf("available eBPF snapshot is missing sampled_at_unix")
		}
		age := time.Since(time.Unix(snapshot.SampledAtUnix, 0))
		if age < -30*time.Second || age > maxAge {
			return EBPFSnapshot{}, fmt.Errorf("eBPF snapshot is stale")
		}
	}
	return snapshot, nil
}
