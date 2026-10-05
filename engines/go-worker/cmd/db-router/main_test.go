package main

import "testing"

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
