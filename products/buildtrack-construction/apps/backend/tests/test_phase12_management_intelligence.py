from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_phase12_is_wired_to_controlled_source_modules() -> None:
    api = (ROOT / "apps/backend/app/api/v1/intelligence.py").read_text(encoding="utf-8")
    router = (ROOT / "apps/backend/app/api/v1/router.py").read_text(encoding="utf-8")
    page = (ROOT / "apps/frontend/app/intelligence/page.tsx").read_text(encoding="utf-8")
    for token in ("project_health", "tender_pipeline", "fleet_performance", "materials", "exceptions", "cost_actual_total", "portfolio.csv"):
        assert token in api
    assert "intelligence_router" in router
    assert "Management Intelligence" in page


def test_phase12_bootstrap_and_empty_director_dashboard() -> None:
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    def override_db():
        db = Session()
        try: yield db
        finally: db.close()
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        assert client.post("/api/v1/foundation/bootstrap", json={"name": "Nthane Brothers", "code": "NTHANE", "head_office_name": "Head Office", "head_office_code": "HO", "head_office_district": "Maseru"}).status_code == 201
        assert client.post("/api/v1/access/bootstrap-admin", json={"username": "phase12admin", "email": "phase12admin@nthane.example", "full_name": "Phase 12 Administrator", "password": "Nthane!Secure2026X"}).status_code == 201
        assert client.post("/api/v1/intelligence/bootstrap").status_code == 200
        response = client.get("/api/v1/intelligence/director-dashboard")
        assert response.status_code == 200, response.text
        assert response.json()["projects"] == 0
        assert response.json()["currency"] == "LSL"
    finally:
        client.close(); app.dependency_overrides.clear(); Base.metadata.drop_all(engine)
