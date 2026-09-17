from app.services import external_webmail_setup as setup
from app.services import mail_provider_detection as detection


def test_mail_exchange_hosts_normalizes_address_and_uses_cached_mx_lookup(monkeypatch):
    seen: list[str] = []

    def fake_mx_hosts(domain: str):
        seen.append(domain)
        return ("mx1.provider.example", "mx2.provider.example")

    monkeypatch.setattr(detection, "_mx_hosts", fake_mx_hosts)

    result = detection.mail_exchange_hosts(" Person@Example.COM ")

    assert result == ("mx1.provider.example", "mx2.provider.example")
    assert seen == ["example.com"]


def test_custom_domain_discovery_tries_apex_and_public_mx_hosts(monkeypatch):
    monkeypatch.setattr(setup, "provider_candidates", lambda _address: ([], []))
    monkeypatch.setattr(
        setup,
        "mail_exchange_hosts",
        lambda _address: ("mx1.provider.example", "mx2.provider.example", "mx3.provider.example"),
    )

    incoming = setup._incoming_candidates(
        "user@example.com",
        "mail.example.com",
        993,
        "ssl",
    )
    outgoing = setup._outgoing_candidates(
        "user@example.com",
        "mail.example.com",
        465,
        "ssl",
    )

    assert incoming[0] == ("mail.example.com", 993, "ssl")
    assert ("example.com", 993, "ssl") in incoming
    assert ("example.com", 143, "starttls") in incoming
    assert ("mx1.provider.example", 993, "ssl") in incoming
    assert ("mx2.provider.example", 993, "ssl") in incoming
    assert ("mx3.provider.example", 993, "ssl") not in incoming

    assert ("example.com", 587, "starttls") in outgoing
    assert ("example.com", 465, "ssl") in outgoing
    assert ("mx1.provider.example", 587, "starttls") in outgoing
    assert ("mx1.provider.example", 465, "ssl") in outgoing
    assert ("mx3.provider.example", 587, "starttls") not in outgoing


def test_setup_uses_detected_provider_candidates_without_weakening_tls(monkeypatch):
    monkeypatch.setattr(
        setup,
        "provider_candidates",
        lambda _address: (
            [("imap.provider.example", 993, "ssl")],
            [("smtp.provider.example", 587, "starttls")],
        ),
    )
    monkeypatch.setattr(setup, "mail_exchange_hosts", lambda _address: ())

    incoming = setup._incoming_candidates(
        "user@example.com",
        "mail.example.com",
        993,
        "ssl",
    )
    outgoing = setup._outgoing_candidates(
        "user@example.com",
        "mail.example.com",
        465,
        "ssl",
    )

    # The explicitly supplied IMAP setting stays first; provider discovery is
    # then tried before generic aliases. The old generated SMTP default is
    # recognized as generated, so the secure provider submission endpoint wins.
    assert incoming[:2] == [
        ("mail.example.com", 993, "ssl"),
        ("imap.provider.example", 993, "ssl"),
    ]
    assert outgoing[0] == ("smtp.provider.example", 587, "starttls")

    assert all(security in {"ssl", "starttls"} for _, _, security in incoming)
    assert all(security in {"ssl", "starttls"} for _, _, security in outgoing)


def test_explicit_non_generated_smtp_setting_remains_first(monkeypatch):
    monkeypatch.setattr(
        setup,
        "provider_candidates",
        lambda _address: ([], [("smtp.provider.example", 587, "starttls")]),
    )
    monkeypatch.setattr(setup, "mail_exchange_hosts", lambda _address: ())

    outgoing = setup._outgoing_candidates(
        "user@example.com",
        "smtp.manual.example",
        465,
        "ssl",
    )

    assert outgoing[0] == ("smtp.manual.example", 465, "ssl")
    assert ("smtp.provider.example", 587, "starttls") in outgoing
