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


func TestParseSmartHealthNVMe(t *testing.T) {
	payload := []byte(`{
		"device":{"name":"/dev/nvme0","protocol":"NVMe"},
		"model_name":"Example NVMe",
		"serial_number":"ABC123",
		"temperature":{"current":47},
		"nvme_smart_health_information_log":{
			"critical_warning":0,
			"percentage_used":12,
			"media_errors":3
		}
	}`)
	health, err := parseSmartHealth("/dev/nvme0n1", payload)
	if err != nil {
		t.Fatalf("parseSmartHealth returned error: %v", err)
	}
	if health.Protocol != "NVMe" || health.Model != "Example NVMe" {
		t.Fatalf("unexpected identity: %#v", health)
	}
	if health.TemperatureC == nil || *health.TemperatureC != 47 {
		t.Fatalf("temperature not parsed: %#v", health.TemperatureC)
	}
	if health.PercentageUsed == nil || *health.PercentageUsed != 12 {
		t.Fatalf("percentage used not parsed")
	}
	if health.MediaErrors == nil || *health.MediaErrors != 3 {
		t.Fatalf("media errors not parsed")
	}
	if health.CriticalWarning == nil || *health.CriticalWarning != 0 {
		t.Fatalf("critical warning not parsed")
	}
}

func TestParseSmartHealthATA(t *testing.T) {
	payload := []byte(`{
		"device":{"name":"/dev/sda","protocol":"ATA"},
		"model_name":"Example SSD",
		"smart_status":{"passed":true},
		"temperature":{"current":39}
	}`)
	health, err := parseSmartHealth("/dev/sda", payload)
	if err != nil {
		t.Fatalf("parseSmartHealth returned error: %v", err)
	}
	if health.HealthPassed == nil || !*health.HealthPassed {
		t.Fatalf("SMART status not parsed")
	}
	if health.TemperatureC == nil || *health.TemperatureC != 39 {
		t.Fatalf("temperature not parsed")
	}
}
