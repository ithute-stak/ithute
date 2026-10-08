from app.services.dnssec_monitor_state import MonitorState, transition


WARNING = {"severity": "warning", "code": "DNS_RESOLVER_SERVFAIL"}
HEALTHY = {"severity": "healthy", "code": "DNSSEC_VALIDATED"}
UNKNOWN = {"severity": "unknown", "code": "DNSSEC_RESOLVER_UNAVAILABLE"}


def test_three_consecutive_failures_open_once():
    state = MonitorState()
    events = []
    for _ in range(5):
        state, changes = transition(state, WARNING)
        events.extend(changes)
    assert state.status == "open"
    assert events == ["opened"]


def test_unknown_does_not_clear_open_incident():
    state = MonitorState("DNS_RESOLVER_SERVFAIL", 3, "open")
    updated, events = transition(state, UNKNOWN)
    assert updated == state
    assert events == []


def test_healthy_recovers_once():
    state = MonitorState("DNS_RESOLVER_SERVFAIL", 5, "open")
    updated, events = transition(state, HEALTHY)
    assert updated.status == "healthy"
    assert events == ["recovered"]
    _, events = transition(updated, HEALTHY)
    assert events == []


def test_changed_failure_requires_new_confirmation():
    state = MonitorState("DNS_RESOLVER_SERVFAIL", 4, "open")
    updated, events = transition(state, {"severity": "warning", "code": "DNSSEC_PARENT_DS_UNVERIFIED"})
    assert updated.status == "pending"
    assert updated.failures == 1
    assert events == []
