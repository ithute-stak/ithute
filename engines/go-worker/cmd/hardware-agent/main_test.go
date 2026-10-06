package main

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestRunProbeAcceptsTelemetryV1(t *testing.T) {
	dir := t.TempDir()
	probe := filepath.Join(dir, "probe")
	payload := `{"schema_version":1,"sampled_at_unix":1,"uptime_seconds":12,"load":{"one":0.1,"five":0.2,"fifteen":0.3},"memory":{"total_kb":100,"available_kb":50,"swap_total_kb":10,"swap_free_kb":9},"cpu":{"user":1,"nice":0,"system":2,"idle":3,"iowait":0,"irq":0,"softirq":0,"steal":0},"thermal":{"zones_seen":0,"max_celsius":0},"cpu_native":{"available":true,"vendor":"GenuineIntel","family":6,"model":143,"stepping":8,"invariant_tsc":true,"rdtscp":true,"aes_ni":true,"avx":true,"avx2":true,"cycle_counter":123456}}`
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
	if !sample.CPUNative.Available || sample.CPUNative.Vendor != "GenuineIntel" || sample.CPUNative.CycleCounter != 123456 {
		t.Fatalf("cpu native telemetry not preserved: %#v", sample.CPUNative)
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


func TestSignedEnvelopeVerifiesAndDetectsTamper(t *testing.T) {
	var sample Sample
	sample.SchemaVersion = 1
	sample.SampledAtUnix = 123
	sample.UptimeSeconds = 456
	sample.Memory.TotalKB = 1024
	sample.Memory.AvailableKB = 512

	key := []byte("0123456789abcdef0123456789abcdef")
	envelope, err := signSample("server-01", key, sample)
	if err != nil {
		t.Fatalf("signSample returned error: %v", err)
	}
	if envelope.Algorithm != "HMAC-SHA256" || envelope.Signature == "" || envelope.Nonce == "" {
		t.Fatalf("incomplete envelope: %#v", envelope)
	}
	if !verifyEnvelope(envelope, key) {
		t.Fatal("signed envelope did not verify")
	}
	envelope.Payload.Memory.AvailableKB++
	if verifyEnvelope(envelope, key) {
		t.Fatal("tampered envelope unexpectedly verified")
	}
}

func TestAgentIDValidation(t *testing.T) {
	for _, value := range []string{"server-01", "vps.prod_1", "tenant:host"} {
		if !validAgentID(value) {
			t.Fatalf("expected valid agent id %q", value)
		}
	}
	for _, value := range []string{"", "a", "bad id", "../escape", "x/y"} {
		if validAgentID(value) {
			t.Fatalf("expected invalid agent id %q", value)
		}
	}
}

func TestReadSigningKeyRejectsLoosePermissions(t *testing.T) {
	path := filepath.Join(t.TempDir(), "agent.key")
	if err := os.WriteFile(path, []byte("0123456789abcdef0123456789abcdef"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := readSigningKey(path); err == nil {
		t.Fatal("expected loose key permissions to be rejected")
	}
	if err := os.Chmod(path, 0o600); err != nil {
		t.Fatal(err)
	}
	key, err := readSigningKey(path)
	if err != nil {
		t.Fatalf("expected private key file to load: %v", err)
	}
	if len(key) != 32 {
		t.Fatalf("key length = %d, want 32", len(key))
	}
}

func TestRustValidatorBridge(t *testing.T) {
	path := filepath.Join(t.TempDir(), "validator")
	script := "#!/bin/sh\n[ \"$3\" = \"100\" ] || exit 2\nprintf 'ok\\n'\n"
	if err := os.WriteFile(path, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	var sample Sample
	sample.UptimeSeconds = 10
	sample.Load.One = 0.5
	sample.Memory.TotalKB = 100
	sample.Memory.AvailableKB = 50
	sample.Pressure.CPUAvg10 = -1
	sample.Pressure.MemoryAvg10 = -1
	sample.Pressure.IOAvg10 = -1

	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if err := validateWithRust(ctx, path, sample); err != nil {
		t.Fatalf("validator bridge returned error: %v", err)
	}
}


func TestPostEnvelopeUsesAgentHeader(t *testing.T) {
	key := []byte("ith_srv_0123456789abcdef0123456789abcdef")
	var sample Sample
	sample.SchemaVersion = 1
	envelope, err := signSample("server-01", key, sample)
	if err != nil {
		t.Fatal(err)
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Fatalf("method = %s", r.Method)
		}
		if got := r.Header.Get("X-Ithute-Server-Agent"); got != string(key) {
			t.Fatalf("agent header = %q", got)
		}
		if r.Header.Get("Content-Type") != "application/json" {
			t.Fatalf("unexpected content type")
		}
		w.WriteHeader(http.StatusAccepted)
	}))
	defer server.Close()

	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if err := postEnvelope(ctx, server.URL, key, envelope); err != nil {
		t.Fatalf("postEnvelope returned error: %v", err)
	}
}

func TestPostEnvelopeRequiresHTTPSAwayFromLocalhost(t *testing.T) {
	var sample Sample
	envelope := SignedEnvelope{EnvelopeVersion: 1, Algorithm: "HMAC-SHA256", AgentID: "server-01", Payload: sample}
	err := postEnvelope(context.Background(), "http://example.com/telemetry", []byte("key"), envelope)
	if err == nil {
		t.Fatal("expected insecure remote endpoint rejection")
	}
}


func TestReadEBPFSnapshotAcceptsFreshRootExport(t *testing.T) {
	path := filepath.Join(t.TempDir(), "ebpf.json")
	body := fmt.Sprintf(`{"available":true,"sampled_at_unix":%d,"block_requests_issued":10,"block_requests_completed":9,"process_exits":2,"oom_victims":1}`, time.Now().Unix())
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	snapshot, err := readEBPFSnapshot(path, 90*time.Second)
	if err != nil {
		t.Fatalf("readEBPFSnapshot returned error: %v", err)
	}
	if !snapshot.Available || snapshot.BlockRequestsIssued != 10 || snapshot.OOMVictims != 1 {
		t.Fatalf("unexpected snapshot: %#v", snapshot)
	}
}

func TestReadEBPFSnapshotRejectsWritableOrStaleFiles(t *testing.T) {
	path := filepath.Join(t.TempDir(), "ebpf.json")
	fresh := fmt.Sprintf(`{"available":true,"sampled_at_unix":%d}`, time.Now().Unix())
	if err := os.WriteFile(path, []byte(fresh), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(path, 0o666); err != nil {
		t.Fatal(err)
	}
	if _, err := readEBPFSnapshot(path, 90*time.Second); err == nil {
		t.Fatal("expected writable snapshot to be rejected")
	}
	if err := os.Chmod(path, 0o644); err != nil {
		t.Fatal(err)
	}
	stale := fmt.Sprintf(`{"available":true,"sampled_at_unix":%d}`, time.Now().Add(-10*time.Minute).Unix())
	if err := os.WriteFile(path, []byte(stale), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := readEBPFSnapshot(path, 90*time.Second); err == nil {
		t.Fatal("expected stale snapshot to be rejected")
	}
}


func TestReadEBPFSnapshotCarriesLatencyPercentiles(t *testing.T) {
	path := filepath.Join(t.TempDir(), "ebpf-latency.json")
	body := fmt.Sprintf(`{"available":true,"sampled_at_unix":%d,"block_latency_count":100,"block_latency_avg_ms":1.25,"block_latency_max_ms":42.0,"block_latency_p50_ms":0.5,"block_latency_p95_ms":4.0,"block_latency_p99_ms":16.0,"block_latency_percentiles_capped":false,"block_latency_histogram":[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16]}`, time.Now().Unix())
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	snapshot, err := readEBPFSnapshot(path, 90*time.Second)
	if err != nil {
		t.Fatalf("readEBPFSnapshot returned error: %v", err)
	}
	if snapshot.BlockLatencyCount != 100 || snapshot.BlockLatencyP95MS == nil || *snapshot.BlockLatencyP95MS != 4.0 {
		t.Fatalf("unexpected latency snapshot: %#v", snapshot)
	}
	if len(snapshot.BlockLatencyHistogram) != 16 {
		t.Fatalf("histogram buckets = %d, want 16", len(snapshot.BlockLatencyHistogram))
	}
}
