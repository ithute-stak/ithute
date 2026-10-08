from app.services.dnssec_monitor_runner import build_dnssec_monitor_readiness
from app.services.dnssec_incidents import classify_dnssec_observation

DS = "41805 8 2 " + "A" * 64


def state(readiness, key):
    return next(step["state"] for step in readiness["steps"] if step["key"] == key)


def test_matching_parent_ds_and_signed_zone_can_be_healthy():
    data = build_dnssec_monitor_readiness(
        {"dnssec": True}, [{"ds": [DS]}],
        {"ready": True, "parent_ds": [DS], "parent_ds_error": None},
    )
    assert state(data, "parent") == "complete"
    assert classify_dnssec_observation(data, {"state": "validated"})["severity"] == "healthy"


def test_parent_lookup_timeout_is_not_mistaken_for_missing_ds():
    data = build_dnssec_monitor_readiness(
        {"dnssec": True}, [{"ds": [DS]}],
        {"ready": True, "parent_ds": [], "parent_ds_error": "Timeout"},
    )
    assert state(data, "parent") == "blocked"
    assert classify_dnssec_observation(data, {"state": "validated"})["severity"] != "healthy"


def test_unsigned_zone_and_unmatched_parent_cannot_be_healthy():
    data = build_dnssec_monitor_readiness(
        {"dnssec": False}, [{"ds": [DS]}],
        {"ready": True, "parent_ds": [], "parent_ds_error": "NoAnswer"},
    )
    assert state(data, "signing") == "pending"
    assert state(data, "parent") == "pending"
    assert classify_dnssec_observation(data, {"state": "validated"})["severity"] != "healthy"



def test_multiple_zone_ds_records_accept_matching_secondary_key():
    secondary = "51000 8 2 " + "B" * 64
    data = build_dnssec_monitor_readiness(
        {"dnssec": True}, [{"ds": [DS, secondary]}],
        {"ready": True, "parent_ds": [secondary], "parent_ds_error": None},
    )
    assert state(data, "parent") == "complete"
