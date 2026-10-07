from app.services.registrar_dnssec import DSRecord, OpenSRSRegistrar, preferred_ds


def test_preferred_ds_uses_sha256_when_available():
    record = preferred_ds([
        "41805 13 1 BC8AE6B1AFB4296AB2B6209493A7D3630D4F393A",
        "41805 13 4 C2D01EF92D23193BB09A224D8D03435FDC4E19B3C9E09154917CFC8452BB97A0F2B7D988837D283C4277D4441C154EA2",
        "41805 13 2 426D93D1248D7C64E88794E3EDD986D08D9AC9FDD42061A92A3FE9F3AE74920C",
    ])
    assert record is not None
    assert record.key_tag == 41805
    assert record.algorithm == 13
    assert record.digest_type == 2


def test_ds_record_rejects_non_hex_digest():
    try:
        DSRecord.parse("41805 13 2 NOT-HEX")
        assert False, "expected invalid DS digest to fail"
    except ValueError:
        pass


def test_publish_preserves_existing_registrar_ds(monkeypatch):
    registrar = OpenSRSRegistrar()
    existing = DSRecord.parse("11111 13 2 AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    selected = DSRecord.parse("41805 13 2 426D93D1248D7C64E88794E3EDD986D08D9AC9FDD42061A92A3FE9F3AE74920C")
    written = []

    monkeypatch.setattr(registrar, "get_dnssec", lambda domain: [existing])
    monkeypatch.setattr(registrar, "set_dnssec", lambda domain, records: written.append((domain, records)))

    result = registrar.publish("example.com", selected)
    assert result == [existing, selected]
    assert written == [("example.com", [existing, selected])]


def test_remove_managed_preserves_unrelated_ds(monkeypatch):
    registrar = OpenSRSRegistrar()
    managed = DSRecord.parse("41805 13 2 426D93D1248D7C64E88794E3EDD986D08D9AC9FDD42061A92A3FE9F3AE74920C")
    unrelated = DSRecord.parse("22222 13 2 BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB")
    written = []

    monkeypatch.setattr(registrar, "get_dnssec", lambda domain: [managed, unrelated])
    monkeypatch.setattr(registrar, "set_dnssec", lambda domain, records: written.append((domain, records)))

    remaining = registrar.remove_managed("example.com", [managed])
    assert remaining == [unrelated]
    assert written == [("example.com", [unrelated])]


def test_opensrs_rejects_unsupported_algorithm_before_network(monkeypatch):
    registrar = OpenSRSRegistrar()
    record = DSRecord.parse("41805 13 2 426D93D1248D7C64E88794E3EDD986D08D9AC9FDD42061A92A3FE9F3AE74920C")
    called = []
    monkeypatch.setattr(registrar, "_request", lambda *args, **kwargs: called.append((args, kwargs)))
    try:
        registrar.set_dnssec("example.com", [record])
        assert False, "expected unsupported OpenSRS algorithm to fail"
    except Exception as exc:
        assert "algorithm 13" in str(exc)
    assert called == []


def test_preferred_ds_can_filter_to_registrar_algorithms():
    values = [
        "41805 13 2 426D93D1248D7C64E88794E3EDD986D08D9AC9FDD42061A92A3FE9F3AE74920C",
        "51000 8 2 AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    ]
    selected = preferred_ds(values, allowed_algorithms={8})
    assert selected is not None
    assert selected.algorithm == 8
    assert selected.key_tag == 51000
