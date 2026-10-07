from datetime import datetime, timezone

import app.services.domain_intelligence_enrichment as enrichment


def test_private_or_local_addresses_are_never_probe_targets(monkeypatch):
    monkeypatch.setattr(
        enrichment.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (2, 1, 6, "", ("127.0.0.1", 0)),
            (2, 1, 6, "", ("10.0.0.5", 0)),
            (2, 1, 6, "", ("8.8.8.8", 0)),
        ],
    )

    assert enrichment._public_addresses("example.com") == ["8.8.8.8"]


def test_automatic_enrichment_collects_bounded_evidence(monkeypatch):
    monkeypatch.setattr(enrichment, "_public_addresses", lambda _domain: ["8.8.8.8"])
    monkeypatch.setattr(
        enrichment,
        "_dns_values",
        lambda domain, record_type: (
            ["10 mail.example.com"] if record_type == "MX"
            else ["ns1.example.com", "ns2.example.com"] if record_type == "NS"
            else ["v=spf1 -all"] if record_type == "TXT" and not domain.startswith("_dmarc.")
            else ["v=DMARC1; p=reject"] if record_type == "TXT"
            else []
        ),
    )
    monkeypatch.setattr(
        enrichment,
        "_rdap_created_at",
        lambda _domain, _timeout: (
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            {"endpoint": "rdap.org", "status": "available"},
        ),
    )
    monkeypatch.setattr(
        enrichment,
        "_tls_http_probe",
        lambda _domain, addresses, _timeout: {
            "tls_present": True,
            "tls_version": "TLSv1.3",
            "certificate_matches_hostname": True,
            "https_status": 200,
            "public_address_count": len(addresses),
        },
    )

    evidence = enrichment.collect_domain_evidence("Example.COM", timeout_seconds=2)

    assert evidence["domain"] == "example.com"
    assert evidence["domain_age_days"] > 1000
    assert evidence["dns"]["spf_present"] is True
    assert evidence["dns"]["dmarc_present"] is True
    assert evidence["web"]["tls_present"] is True
    assert evidence["privacy"]["raw_page_content_stored"] is False


def test_invalid_domain_is_rejected_before_network_access():
    try:
        enrichment.collect_domain_evidence("http://127.0.0.1")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid domain should be rejected")
