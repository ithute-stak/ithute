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
