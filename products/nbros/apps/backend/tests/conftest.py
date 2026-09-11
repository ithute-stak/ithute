import os
from datetime import date, datetime, timezone

os.environ.setdefault("NBROS_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("NBROS_REDIS_URL", "redis://127.0.0.1:6379/15")
os.environ.setdefault("NBROS_REALTIME_PUBLISH_ENABLED", "false")
os.environ.setdefault("NBROS_AI_ENABLED", "false")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app import models as _models  # noqa: F401
from app import fleet_alerts as _fleet_alerts  # noqa: F401
from app import fleet_inventory as _fleet_inventory  # noqa: F401
from app import enterprise_models as _enterprise_models  # noqa: F401
from app.models import Branch, BranchModule, FleetSetting, Inspection, ServiceRecord, Vehicle

TODAY = date(2026, 9, 11)
NOW = datetime(2026, 9, 11, 8, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionFactory() as session:
        yield session
    engine.dispose()


@pytest.fixture()
def branch(db: Session) -> Branch:
    row = Branch(code="HQ", name="Head Office", location="Maseru")
    db.add(row); db.flush(); db.add(BranchModule(branch_id=row.id, module_key="fleet", is_enabled=True)); db.add(FleetSetting(branch_id=row.id, document_warning_days=30, document_critical_days=7, service_warning_days=30, service_mileage_warning=1000)); db.commit(); return row


@pytest.fixture()
def healthy_vehicle(db: Session, branch: Branch) -> Vehicle:
    vehicle = Vehicle(branch_id=branch.id, registration_plate="A100", make="Toyota", model="Hilux", vehicle_type="Light vehicle", current_mileage=10_000, mechanical_condition="operational")
    db.add(vehicle); db.flush(); db.add(ServiceRecord(branch_id=branch.id, vehicle_id=vehicle.id, service_date=TODAY, mileage=10_000, service_type="Minor", service_kit="Hilux Minor Kit", next_service_date=date(2026, 12, 1), next_service_mileage=15_000)); db.add(Inspection(branch_id=branch.id, vehicle_id=vehicle.id, inspection_date=TODAY, status="passed", inspector="Fleet Test", next_inspection_date=date(2027, 1, 1))); db.commit(); return vehicle
