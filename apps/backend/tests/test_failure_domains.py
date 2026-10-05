from app.models import InfrastructureServer
from app.services.failure_domains import (
    failure_domain_overlap,
    failure_domain_sort_key,
)


def _server(*, provider, region, datacenter, physical_host, network_segment):
    return InfrastructureServer(
        name="test",
        hostname="test.example",
        provider=provider,
        region=region,
        datacenter=datacenter,
        physical_host=physical_host,
        network_segment=network_segment,
        roles_json='["application"]',
        status="active",
        created_by_user_id=None,
    )


def test_failure_domain_overlap_detects_critical_collisions():
    source = _server(
        provider="p1",
        region="r1",
        datacenter="dc1",
        physical_host="host-a",
        network_segment="seg-a",
    )
    target = _server(
        provider="p1",
        region="r1",
        datacenter="dc1",
        physical_host="host-a",
        network_segment="seg-b",
    )

    overlap = failure_domain_overlap(source, target)

    assert "physical_host" in overlap["shared"]
    assert overlap["highest_risk"] == "physical_host"
    assert overlap["penalty"] > 0


def test_failure_domain_sort_prefers_smaller_blast_radius_before_placement_score():
    source = _server(
        provider="p1",
        region="r1",
        datacenter="dc1",
        physical_host="host-a",
        network_segment="seg-a",
    )
    same_host = _server(
        provider="p1",
        region="r1",
        datacenter="dc1",
        physical_host="host-a",
        network_segment="seg-z",
    )
    other_region = _server(
        provider="p2",
        region="r2",
        datacenter="dc9",
        physical_host="host-z",
        network_segment="seg-z",
    )

    bad_overlap = failure_domain_overlap(source, same_host)
    good_overlap = failure_domain_overlap(source, other_region)

    bad_key = failure_domain_sort_key(
        bad_overlap,
        placement_score=1.0,
        name="fast-but-collocated",
        node_id="a",
    )
    good_key = failure_domain_sort_key(
        good_overlap,
        placement_score=50.0,
        name="safer",
        node_id="b",
    )

    assert good_key < bad_key


def test_failure_domain_overlap_penalties_are_progressive():
    source = _server(
        provider="p1",
        region="r1",
        datacenter="dc1",
        physical_host="host-a",
        network_segment="seg-a",
    )
    same_provider = _server(
        provider="p1",
        region="r9",
        datacenter="dc9",
        physical_host="host-z",
        network_segment="seg-z",
    )
    same_datacenter = _server(
        provider="p1",
        region="r1",
        datacenter="dc1",
        physical_host="host-z",
        network_segment="seg-z",
    )

    provider_overlap = failure_domain_overlap(source, same_provider)
    dc_overlap = failure_domain_overlap(source, same_datacenter)

    assert provider_overlap["penalty"] < dc_overlap["penalty"]
    assert provider_overlap["highest_risk"] == "provider"
    assert dc_overlap["highest_risk"] == "datacenter"
