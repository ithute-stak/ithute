from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

def test_mobile_capture_contract_is_safe_and_revision_is_ordered() -> None:
    migration=(ROOT/"apps/backend/alembic/versions/0015_phase14_mobile.py").read_text(encoding="utf-8")
    api=(ROOT/"apps/backend/app/api/v1/mobile.py").read_text(encoding="utf-8")
    page=(ROOT/"apps/frontend/app/mobile/page.tsx").read_text(encoding="utf-8")
    assert 'down_revision="0014_phase13_assurance"' in migration
    assert len("0015_phase14_mobile") <= 32
    for token in ("client_submission_id", "idempotent", "cannot complete the independent review", "never auto-posts transactions"):
        assert token in api
    assert "localStorage" in page and "Sync now" in page

def test_mobile_bootstrap_and_empty_queue() -> None:
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app import models  # noqa
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);Session=sessionmaker(bind=engine)
    def override():
        db=Session()
        try: yield db
        finally: db.close()
    app.dependency_overrides[get_db]=override;client=TestClient(app)
    try:
        assert client.post("/api/v1/foundation/bootstrap",json={"name":"Nthane Brothers","code":"NTHANE","head_office_name":"Head Office","head_office_code":"HO","head_office_district":"Maseru"}).status_code==201
        assert client.post("/api/v1/access/bootstrap-admin",json={"username":"phase14admin","email":"phase14admin@nthane.example","full_name":"Phase 14 Administrator","password":"Nthane!Secure2026X"}).status_code==201
        assert client.post("/api/v1/mobile/bootstrap").status_code==200
        queue=client.get("/api/v1/mobile/dashboard")
        assert queue.status_code==200 and queue.json()["pending_review"]==0
    finally:
        client.close();app.dependency_overrides.clear();Base.metadata.drop_all(engine)
