package main

import (
	"context"
	"io"
	"net"
	"strconv"
	"testing"
	"time"
)

func TestValidateSnapshotRejectsDuplicatePorts(t *testing.T) {
	s := snapshot{Routes: []route{
		{EndpointID: "a", ListenPort: 20001, TargetHost: "db-a.internal", TargetPort: 5432, Generation: 1},
		{EndpointID: "b", ListenPort: 20001, TargetHost: "db-b.internal", TargetPort: 5432, Generation: 1},
	}}
	if err := validateSnapshot(s); err == nil {
		t.Fatal("expected duplicate port rejection")
	}
}

func TestValidateRouteRejectsUnsafeTarget(t *testing.T) {
	r := route{
		EndpointID: "a",
		ListenPort: 20001,
		TargetHost: "bad host",
		TargetPort: 5432,
		Generation: 1,
	}
	if err := validateRoute(r); err == nil {
		t.Fatal("expected unsafe target host rejection")
	}
}

func TestRouteTargetUpdateIsVisibleToNewConnections(t *testing.T) {
	target := &routeTarget{r: route{
		EndpointID: "a",
		ListenPort: 20001,
		TargetHost: "old-primary.internal",
		TargetPort: 5432,
		Generation: 1,
	}}
	target.set(route{
		EndpointID: "a",
		ListenPort: 20001,
		TargetHost: "new-primary.internal",
		TargetPort: 5432,
		Generation: 2,
	})
	got := target.get()
	if got.TargetHost != "new-primary.internal" || got.Generation != 2 {
		t.Fatalf("unexpected route after update: %+v", got)
	}
}

func startBannerServer(t *testing.T, banner string) (string, int, func()) {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	host, portText, err := net.SplitHostPort(ln.Addr().String())
	if err != nil {
		ln.Close()
		t.Fatal(err)
	}
	port, _ := strconv.Atoi(portText)
	done := make(chan struct{})
	go func() {
		defer close(done)
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			_, _ = conn.Write([]byte(banner))
			_ = conn.Close()
		}
	}()
	return host, port, func() {
		_ = ln.Close()
		<-done
	}
}

func reservePort(t *testing.T) int {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	_, portText, err := net.SplitHostPort(ln.Addr().String())
	if err != nil {
		ln.Close()
		t.Fatal(err)
	}
	port, _ := strconv.Atoi(portText)
	_ = ln.Close()
	return port
}

func readBanner(t *testing.T, port int) string {
	t.Helper()
	conn, err := net.DialTimeout("tcp", net.JoinHostPort("127.0.0.1", strconv.Itoa(port)), time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	_ = conn.SetReadDeadline(time.Now().Add(time.Second))
	payload, err := io.ReadAll(conn)
	if err != nil {
		t.Fatal(err)
	}
	return string(payload)
}

func TestChaosPrimaryRouteSwitchSendsNewConnectionsToPromotedTarget(t *testing.T) {
	oldHost, oldPort, closeOld := startBannerServer(t, "old-primary")
	defer closeOld()
	newHost, newPort, closeNew := startBannerServer(t, "new-primary")
	defer closeNew()

	listenPort := reservePort(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	manager := newRouteManager("127.0.0.1", time.Second)
	defer manager.close()

	first := route{
		EndpointID: "cluster-a",
		ListenPort: listenPort,
		TargetHost: oldHost,
		TargetPort: oldPort,
		Generation: 1,
	}
	if _, err := manager.apply(ctx, snapshot{Routes: []route{first}}); err != nil {
		t.Fatal(err)
	}
	if got := readBanner(t, listenPort); got != "old-primary" {
		t.Fatalf("expected old primary before cutover, got %q", got)
	}

	second := first
	second.TargetHost = newHost
	second.TargetPort = newPort
	second.Generation = 2
	if _, err := manager.apply(ctx, snapshot{Routes: []route{second}}); err != nil {
		t.Fatal(err)
	}
	if got := readBanner(t, listenPort); got != "new-primary" {
		t.Fatalf("expected promoted primary after cutover, got %q", got)
	}
}

func TestChaosRouteRemovalStopsAcceptingNewConnections(t *testing.T) {
	host, port, closeBackend := startBannerServer(t, "primary")
	defer closeBackend()
	listenPort := reservePort(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	manager := newRouteManager("127.0.0.1", time.Second)
	defer manager.close()

	r := route{
		EndpointID: "cluster-remove",
		ListenPort: listenPort,
		TargetHost: host,
		TargetPort: port,
		Generation: 1,
	}
	if _, err := manager.apply(ctx, snapshot{Routes: []route{r}}); err != nil {
		t.Fatal(err)
	}
	if got := readBanner(t, listenPort); got != "primary" {
		t.Fatalf("unexpected route banner %q", got)
	}
	if _, err := manager.apply(ctx, snapshot{}); err != nil {
		t.Fatal(err)
	}
	time.Sleep(25 * time.Millisecond)
	if conn, err := net.DialTimeout("tcp", net.JoinHostPort("127.0.0.1", strconv.Itoa(listenPort)), 100*time.Millisecond); err == nil {
		conn.Close()
		t.Fatal("removed route still accepted a new connection")
	}
}
