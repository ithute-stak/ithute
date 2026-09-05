import pytest

from app.services.powerdns import validate_record


def test_cname_target_is_canonicalized_for_powerdns():
    name, rtype, values = validate_record(
        "lelefadebtcollectors.co.ls",
        "www",
        "CNAME",
        ["lelefadebtcollectors.co.ls"],
    )

    assert name == "www.lelefadebtcollectors.co.ls"
    assert rtype == "CNAME"
    assert values == ["lelefadebtcollectors.co.ls."]


def test_relative_cname_target_is_made_absolute_inside_zone():
    _, _, values = validate_record("example.co.ls", "www", "CNAME", ["app"])
    assert values == ["app.example.co.ls."]


def test_mx_target_is_canonicalized():
    _, _, values = validate_record("example.co.ls", "@", "MX", ["10 mail.example.co.ls"])
    assert values == ["10 mail.example.co.ls."]


def test_null_mx_root_target_is_preserved():
    _, _, values = validate_record("example.co.ls", "@", "MX", ["0 ."])
    assert values == ["0 ."]


def test_srv_target_is_canonicalized():
    _, _, values = validate_record(
        "example.co.ls",
        "_submission._tcp",
        "SRV",
        ["0 5 587 mail.example.co.ls"],
    )
    assert values == ["0 5 587 mail.example.co.ls."]


def test_txt_is_quoted_for_powerdns_but_existing_quotes_are_preserved():
    _, _, unquoted = validate_record("example.co.ls", "@", "TXT", ["v=spf1 mx -all"])
    _, _, quoted = validate_record("example.co.ls", "_dmarc", "TXT", ['"v=DMARC1; p=reject"'])

    assert unquoted == ['"v=spf1 mx -all"']
    assert quoted == ['"v=DMARC1; p=reject"']


def test_cname_is_still_rejected_at_zone_apex():
    with pytest.raises(ValueError, match="cannot be used at the zone apex"):
        validate_record("example.co.ls", "@", "CNAME", ["target.example.co.ls"])
