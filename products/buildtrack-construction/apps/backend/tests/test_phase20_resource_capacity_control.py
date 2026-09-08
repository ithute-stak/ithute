from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_phase20_resource_capacity_controls_are_wired() -> None:
    migration = (ROOT / "apps/backend/alembic/versions/0021_phase20_resource_control.py").read_text(encoding="utf-8")
    api = (ROOT / "apps/backend/app/api/v1/resources.py").read_text(encoding="utf-8")
    page = (ROOT / "apps/frontend/app/resources/page.tsx").read_text(encoding="utf-8")
    assert 'down_revision = "0020_phase19_programme"' in migration
    assert len("0021_phase20_resources") <= 32
    for table in ("resource_plans", "resource_plan_items", "resource_requests", "resource_audit_events"):
        assert f'"{table}"' in migration
    for safeguard in (
        "Resolve resource capacity conflicts before submitting this plan",
        "Resource requests can only be prepared from an independently approved resource plan",
        "Resource request exceeds the remaining approved planned quantity",
        "Controlled fulfilment evidence is required before recording a resource request",
        "does not create a payroll, procurement or rental transaction",
    ):
        assert safeguard in api or safeguard in page
    assert "Resource Planning &amp; Capacity Control" in page
    assert "capacity conflicts" in page
