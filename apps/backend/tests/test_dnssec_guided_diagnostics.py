from app.services.dnssec_readiness import activation_readiness


def _readiness(**kwargs):
    args = dict(signing=True, delegation={"ready": True, "parent_ds": [], "parent_ds_error": None},
                registrar_configured=False, recommended_ds=None, parent_contains_recommended=False,
                available_ds=True, registrar_algorithms=[8])
    args.update(kwargs)
    return activation_readiness(**args)


def test_incompatible_existing_ds_is_explained():
    result = _readiness()
    step = next(s for s in result["steps"] if s["key"] == "ds")
    assert step["state"] == "pending"
    assert "not supported by OpenSRS" in step["detail"]
    assert result["registrar_supported_algorithms"] == [8]


def test_parent_resolver_timeout_is_not_reported_as_absent():
    result = _readiness(delegation={"ready": True, "parent_ds": [], "parent_ds_error": "Timeout"})
    assert result["parent_lookup_state"] == "error"
    assert next(s for s in result["steps"] if s["key"] == "parent")["state"] == "blocked"


def test_noanswer_is_nonfatal_but_not_verified():
    result = _readiness(delegation={"ready": True, "parent_ds": [], "parent_ds_error": "NoAnswer"})
    assert result["parent_lookup_state"] == "not_observed"
    assert next(s for s in result["steps"] if s["key"] == "parent")["state"] == "pending"
    assert result["ready"] is False
