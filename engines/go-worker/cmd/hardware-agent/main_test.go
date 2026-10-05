package main

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestRunProbeAcceptsTelemetryV1(t *testing.T) {
	dir := t.TempDir()
	probe := filepath.Join(dir, "probe")
	payload := `{"schema_version":1,"sampled_at_unix":1,"uptime_seconds":12,"load":{"one":0.1,"five":0.2,"fifteen":0.3},"memory":{"total_kb":100,"available_kb":50,"swap_total_kb":10,"swap_free_kb":9},"cpu":{"user":1,"nice":0,"system":2,"idle":3,"iowait":0,"irq":0,"softirq":0,"steal":0},"thermal":{"zones_seen":0,"max_celsius":0}}`
	script := "#!/bin/sh\nprintf '%s\\n' '" + payload + "'\n"
	if err := os.WriteFile(probe, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	sample, err := runProbe(ctx, probe)
	if err != nil {
		t.Fatalf("runProbe returned error: %v", err)
	}
	if sample.SchemaVersion != 1 {
		t.Fatalf("schema version = %d, want 1", sample.SchemaVersion)
	}
	if sample.Memory.TotalKB != 100 {
		t.Fatalf("total memory = %d, want 100", sample.Memory.TotalKB)
	}
}

func TestRunProbeRejectsUnknownSchema(t *testing.T) {
	dir := t.TempDir()
	probe := filepath.Join(dir, "probe")
	script := "#!/bin/sh\nprintf '%s\\n' '{\"schema_version\":99}'\n"
	if err := os.WriteFile(probe, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if _, err := runProbe(ctx, probe); err == nil {
		t.Fatal("expected unsupported schema error")
	}
}
