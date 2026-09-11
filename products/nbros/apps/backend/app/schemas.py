import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class BranchCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    location: str | None = Field(default=None, max_length=255)


class BranchOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    location: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class FleetSettingUpdate(BaseModel):
    document_warning_days: int = Field(default=30, ge=1, le=365)
    document_critical_days: int = Field(default=7, ge=1, le=90)
    service_warning_days: int = Field(default=30, ge=1, le=365)
    service_mileage_warning: int = Field(default=1000, ge=0, le=50000)


class DocumentRequirementCreate(BaseModel):
    branch_id: uuid.UUID
    document_type: str = Field(min_length=1, max_length=100)
    vehicle_type: str | None = Field(default=None, max_length=100)
    is_required: bool = True
    warning_days: int | None = Field(default=None, ge=1, le=365)
    critical_days: int | None = Field(default=None, ge=1, le=90)


class VehicleCreate(BaseModel):
    branch_id: uuid.UUID
    registration_plate: str = Field(min_length=1, max_length=50)
    make: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    vehicle_type: str = Field(min_length=1, max_length=100)
    year: int | None = Field(default=None, ge=1900, le=2200)
    vin: str | None = Field(default=None, max_length=100)
    engine_number: str | None = Field(default=None, max_length=100)
    fuel_type: str | None = Field(default=None, max_length=40)
    current_mileage: int = Field(default=0, ge=0)
    purchase_date: date | None = None
    purchase_price: Decimal | None = Field(default=None, ge=0)
    purchase_supplier: str | None = Field(default=None, max_length=160)
    notes: str | None = None


class VehicleDocumentCreate(BaseModel):
    branch_id: uuid.UUID
    vehicle_id: uuid.UUID
    document_type: str = Field(min_length=1, max_length=100)
    document_number: str | None = Field(default=None, max_length=160)
    issue_date: date | None = None
    expiry_date: date | None = None
    file_url: str | None = Field(default=None, max_length=1024)
    is_required: bool = True


class ServiceRecordCreate(BaseModel):
    branch_id: uuid.UUID
    vehicle_id: uuid.UUID
    service_date: date
    mileage: int = Field(ge=0)
    service_type: str = Field(min_length=1, max_length=100)
    parts_used: str | None = None
    service_kit: str | None = Field(default=None, max_length=160)
    mechanic: str | None = Field(default=None, max_length=160)
    cost: Decimal | None = Field(default=None, ge=0)
    next_service_date: date | None = None
    next_service_mileage: int | None = Field(default=None, ge=0)


class MechanicalFaultCreate(BaseModel):
    branch_id: uuid.UUID
    vehicle_id: uuid.UUID
    severity: str = Field(default="attention", pattern="^(attention|critical)$")
    description: str = Field(min_length=1)


class InspectionCreate(BaseModel):
    branch_id: uuid.UUID
    vehicle_id: uuid.UUID
    inspection_date: date
    status: str = Field(pattern="^(passed|attention|failed)$")
    inspector: str | None = Field(default=None, max_length=160)
    notes: str | None = None
    next_inspection_date: date | None = None


class DriverCreate(BaseModel):
    branch_id: uuid.UUID
    auth_user_id: uuid.UUID | None = None
    employee_number: str | None = Field(default=None, max_length=80)
    full_name: str = Field(min_length=1, max_length=160)
    license_number: str = Field(min_length=1, max_length=100)
    license_category: str = Field(min_length=1, max_length=80)
    license_expiry: date


class MaintenanceWorkOrderCreate(BaseModel):
    branch_id: uuid.UUID
    vehicle_id: uuid.UUID
    description: str = Field(min_length=1)
    expected_release_at: datetime | None = None


class AssignmentCreate(BaseModel):
    branch_id: uuid.UUID
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID
    purpose: str | None = Field(default=None, max_length=255)
    start_at: datetime
    end_at: datetime | None = None


class TripCreate(BaseModel):
    branch_id: uuid.UUID
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID
    destination: str = Field(min_length=1, max_length=255)
    purpose: str | None = Field(default=None, max_length=255)
    start_at: datetime
    expected_return_at: datetime | None = None


class ReservationCreate(BaseModel):
    branch_id: uuid.UUID
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID | None = None
    purpose: str | None = Field(default=None, max_length=255)
    start_at: datetime
    end_at: datetime


class FuelRecordCreate(BaseModel):
    branch_id: uuid.UUID
    vehicle_id: uuid.UUID
    recorded_at: datetime | None = None
    mileage: int = Field(ge=0)
    litres: Decimal = Field(gt=0)
    cost: Decimal | None = Field(default=None, ge=0)
    station: str | None = Field(default=None, max_length=160)


class AccidentRecordCreate(BaseModel):
    branch_id: uuid.UUID
    vehicle_id: uuid.UUID
    occurred_at: datetime
    location: str | None = Field(default=None, max_length=255)
    description: str = Field(min_length=1)
    driver_id: uuid.UUID | None = None
    reference_number: str | None = Field(default=None, max_length=160)


class VehicleMatchRequest(BaseModel):
    branch_id: uuid.UUID
    vehicle_type: str = Field(min_length=1, max_length=100)
    start_at: datetime
    end_at: datetime
    driver_id: uuid.UUID | None = None


class VehicleTypeLicenseRuleCreate(BaseModel):
    branch_id: uuid.UUID
    vehicle_type: str = Field(min_length=1, max_length=100)
    license_category: str = Field(min_length=1, max_length=80)


class ServiceKitRuleCreate(BaseModel):
    branch_id: uuid.UUID
    make: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    service_type: str = Field(min_length=1, max_length=100)
    kit_name: str = Field(min_length=1, max_length=160)
