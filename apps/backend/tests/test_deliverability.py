from app.services.deliverability import generate_dkim_material, normalize_selector, recommended_records


def test_dkim_material_is_2048_rsa_and_private_key_is_protected():
    encrypted, public = generate_dkim_material()
    assert encrypted
    assert "PRIVATE KEY" not in encrypted
    assert len(public) > 300


def test_selector_normalization():
    assert normalize_selector(" S1 ") == "s1"
    try:
        normalize_selector("bad.selector")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid DKIM selector should fail")


def test_recommended_mail_authentication_records():
    records = recommended_records("example.com", "mail.example.com", "s1", "PUBLICKEY")
    by_purpose = {row["purpose"]: row for row in records}
    assert by_purpose["mail-routing"]["value"] == "10 mail.example.com."
    assert by_purpose["spf"]["value"] == "v=spf1 mx -all"
    assert by_purpose["dkim"]["name"] == "s1._domainkey.example.com"
    assert "p=PUBLICKEY" in by_purpose["dkim"]["value"]
    assert by_purpose["dmarc"]["name"] == "_dmarc.example.com"
    assert "p=quarantine" in by_purpose["dmarc"]["value"]
