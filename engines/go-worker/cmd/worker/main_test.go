package main

import (
	"context"
	"net"
	"testing"
	"time"
)

func TestRunProbesFindsReachableLocalTCPService(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	port := listener.Addr().(*net.TCPAddr).Port

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	response, err := runProbes(ctx, networkProbeRequest{
		Targets: []networkTarget{{ID: "local", Host: "127.0.0.1", Port: port, Timeout: 500}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if response.Engine != "go" || response.Checked != 1 {
		t.Fatalf("unexpected response: %#v", response)
	}
	if !response.Results[0].Reachable {
		t.Fatalf("expected reachable result: %#v", response.Results[0])
	}
}

func TestRunProbesRejectsUnsafeBounds(t *testing.T) {
	_, err := runProbes(context.Background(), networkProbeRequest{
		Targets: []networkTarget{{ID: "bad", Host: "localhost", Port: 0}},
	})
	if err == nil {
		t.Fatal("expected validation error")
	}
}

func TestPublicTargetIPRejectsPrivateAndReserved(t *testing.T) {
	for _, value := range []string{
		"127.0.0.1",
		"10.0.0.1",
		"169.254.169.254",
		"192.168.1.10",
		"100.64.0.1",
		"192.0.2.10",
		"198.51.100.8",
		"203.0.113.9",
		"::1",
		"fc00::1",
		"2001:db8::1",
	} {
		if _, ok := publicTargetIP(value); ok {
			t.Fatalf("expected %s to be rejected", value)
		}
	}
	if addr, ok := publicTargetIP("1.1.1.1"); !ok || addr.String() != "1.1.1.1" {
		t.Fatalf("expected public address to be accepted")
	}
}

func TestValidateDNSQuery(t *testing.T) {
	if err := validateDNSQuery(dnsQuery{ID: "a", Name: "example.com", Type: "A"}); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if err := validateDNSQuery(dnsQuery{ID: "bad", Name: "example.com", Type: "SRV"}); err == nil {
		t.Fatal("unsupported DNS type should be rejected")
	}
}

func TestOriginProbeRejectsPrivateTargetBeforeDial(t *testing.T) {
	_, err := runOriginProbe(context.Background(), originProbeRequest{
		Scheme:         "https",
		Hostname:       "example.com",
		TargetIP:       "127.0.0.1",
		Port:           443,
		Path:           "/health",
		ExpectedStatus: 200,
		TimeoutMS:      1000,
	})
	if err == nil {
		t.Fatal("private target should be rejected")
	}
}


func FuzzPublicTargetIPNeverPanics(f *testing.F) {
	for _, seed := range []string{
		"127.0.0.1",
		"169.254.169.254",
		"1.1.1.1",
		"::1",
		"2001:4860:4860::8888",
		"not-an-ip",
		"",
	} {
		f.Add(seed)
	}
	f.Fuzz(func(t *testing.T, value string) {
		_, _ = publicTargetIP(value)
	})
}


func TestRunTopologyProbeBuildsSourceRow(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	port := listener.Addr().(*net.TCPAddr).Port

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	response, err := runTopologyProbe(ctx, topologyProbeRequest{
		SourceID: "node-a",
		Targets: []networkTarget{
			{ID: "node-b", Host: "127.0.0.1", Port: port, Timeout: 500},
		},
		Samples: 3,
		Concurrency: 1,
	})
	if err != nil {
		t.Fatal(err)
	}
	if response.Engine != "go" || response.SourceID != "node-a" || response.Samples != 3 {
		t.Fatalf("unexpected response: %#v", response)
	}
	if len(response.Results) != 1 {
		t.Fatalf("unexpected result count: %#v", response.Results)
	}
	result := response.Results[0]
	if !result.Reachable || result.Attempts != 3 || result.Successes != 3 {
		t.Fatalf("unexpected topology result: %#v", result)
	}
	if result.ConnectLossPercent != 0 {
		t.Fatalf("expected zero connect loss: %#v", result)
	}
	if result.LatencyAverageMS < result.LatencyMinMS || result.LatencyAverageMS > result.LatencyMaxMS {
		t.Fatalf("invalid latency summary: %#v", result)
	}
}

func TestRunTopologyProbeRejectsSourceTargetCollision(t *testing.T) {
	_, err := runTopologyProbe(context.Background(), topologyProbeRequest{
		SourceID: "node-a",
		Targets: []networkTarget{
			{ID: "node-a", Host: "127.0.0.1", Port: 443, Timeout: 500},
		},
		Samples: 2,
	})
	if err == nil {
		t.Fatal("expected source/target collision to be rejected")
	}
}

func TestRunTopologyProbeRejectsExcessiveSamples(t *testing.T) {
	_, err := runTopologyProbe(context.Background(), topologyProbeRequest{
		SourceID: "node-a",
		Targets: []networkTarget{
			{ID: "node-b", Host: "127.0.0.1", Port: 443, Timeout: 500},
		},
		Samples: 11,
	})
	if err == nil {
		t.Fatal("expected excessive samples to be rejected")
	}
}
