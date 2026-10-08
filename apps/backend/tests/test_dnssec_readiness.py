from app.services.dnssec_readiness import activation_readiness


def test_readiness_requires_parent_ds_match():
    result = activation_readiness(
        signing=True,
        delegation={"ready": True, "parent_ds": [], "parent_ds_error": "NoAnswer"},
        registrar_configured=False,
        recommended_ds="12345 8 2 AABB",
        parent_contains_recommended=False,
    )
    assert result["ready"] is False
    assert result["state"] == "blocked"
    assert next(s for s in result["steps"] if s["key"] == "parent")["state"] == "blocked"


def test_readiness_accepts_manually_published_ds_without_registrar_credentials():
    result = activation_readiness(
        signing=True,
        delegation={"ready": True, "parent_ds": ["12345 8 2 AABB"], "parent_ds_error": None},
        registrar_configured=False,
        recommended_ds="12345 8 2 AABB",
        parent_contains_recommended=True,
    )
    assert result["ready"] is True
    assert result["state"] == "verified"
    assert next(s for s in result["steps"] if s["key"] == "registrar")["state"] == "pending"


def test_readiness_detects_missing_delegation():
    result = activation_readiness(
        signing=True,
        delegation={"ready": False, "delegation_error": "Timeout", "parent_ds": [], "parent_ds_error": None},
        registrar_configured=True,
        recommended_ds="12345 8 2 AABB",
        parent_contains_recommended=False,
    )
    assert result["ready"] is False
    assert next(s for s in result["steps"] if s["key"] == "delegation")["state"] == "blocked"


def test_readiness_reports_provider_failure_without_credential_leak():
    result = activation_readiness(
        signing=True,
        delegation={"ready": True, "parent_ds": [], "parent_ds_error": None},
        registrar_configured=True,
        recommended_ds=None,
        parent_contains_recommended=False,
        registrar_error="Registrar unreachable",
    )
    assert result["ready"] is False
    assert next(s for s in result["steps"] if s["key"] == "registrar")["state"] == "blocked"
    assert result["read_only"] is True
