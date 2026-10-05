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


func TestPushBrokerDeliversToActiveReceiver(t *testing.T) {
	broker := newPushBroker()
	endpoint := "device-endpoint-secret-12345"
	waiter := broker.register(endpoint)
	defer broker.unregister(endpoint, waiter)

	response, err := broker.deliver(pushDeliveryRequest{
		Endpoint: endpoint,
		DeliveryID: "delivery-1",
		TTLSeconds: 60,
		Notification: map[string]any{"title": "Hello"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if !response.Queued || response.Engine != "go" || response.MessageID == "" {
		t.Fatalf("unexpected response: %#v", response)
	}
	select {
	case message := <-waiter:
		if message.DeliveryID != "delivery-1" {
			t.Fatalf("unexpected delivery id: %s", message.DeliveryID)
		}
		if message.Notification["title"] != "Hello" {
			t.Fatalf("unexpected notification: %#v", message.Notification)
		}
	default:
		t.Fatal("expected delivered push envelope")
	}
}

func TestPushBrokerRejectsOfflineEndpoint(t *testing.T) {
	broker := newPushBroker()
	_, err := broker.deliver(pushDeliveryRequest{
		Endpoint: "device-endpoint-secret-12345",
		TTLSeconds: 60,
		Notification: map[string]any{"title": "Hello"},
	})
	if err == nil || err.Error() != "endpoint is not actively connected" {
		t.Fatalf("expected offline endpoint error, got %v", err)
	}
}

func TestPushBrokerRejectsInvalidEndpointAndTTL(t *testing.T) {
	broker := newPushBroker()
	if _, err := broker.deliver(pushDeliveryRequest{
		Endpoint: "short",
		TTLSeconds: 60,
		Notification: map[string]any{"title": "Hello"},
	}); err == nil {
		t.Fatal("expected endpoint validation error")
	}
	if _, err := broker.deliver(pushDeliveryRequest{
		Endpoint: "device-endpoint-secret-12345",
		TTLSeconds: 0,
		Notification: map[string]any{"title": "Hello"},
	}); err == nil {
		t.Fatal("expected ttl validation error")
	}
}

func TestConstantTimeTokenMatch(t *testing.T) {
	if !constantTimeTokenMatch("secret-token", "secret-token") {
		t.Fatal("expected token match")
	}
	if constantTimeTokenMatch("secret-token", "wrong-token") {
		t.Fatal("unexpected token match")
	}
	if constantTimeTokenMatch("", "") {
		t.Fatal("empty configured token must never authenticate")
	}
}
