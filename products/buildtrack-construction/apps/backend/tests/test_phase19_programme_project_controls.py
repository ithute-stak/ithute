from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_phase19_programme_controls_are_wired() -> None:
    migration = (ROOT / "apps/backend/alembic/versions/0020_phase19_programme_control.py").read_text(encoding="utf-8")
    api = (ROOT / "apps/backend/app/api/v1/planning.py").read_text(encoding="utf-8")
    page = (ROOT / "apps/frontend/app/planning/page.tsx").read_text(encoding="utf-8")
    assert 'down_revision = "0019_phase18_finance"' in migration
    assert len("0020_phase19_programme") <= 32
    for table in (
        "programme_baselines", "programme_activities", "programme_activity_updates",
        "programme_lookahead_items", "programme_delay_events", "planning_audit_events",
    ):
        assert f'"{table}"' in migration
    for safeguard in (
        "Programme activity dependencies contain a cycle",
        "Programme activity weights must total",
        "Activity progress can only be recorded against an independently approved baseline",
        "Cumulative activity progress cannot move backwards",
        "BuildTrack does not decide entitlement or send contractual notices",
    ):
        assert safeguard in api or safeguard in page
    assert "Programme &amp; Project Controls" in page
    assert "Six-week lookahead" in page
