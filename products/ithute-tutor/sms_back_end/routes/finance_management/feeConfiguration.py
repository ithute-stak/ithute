from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.finace_management.schemas.school_fee_configuration import (
    SchoolFeeConfigurationCreate,
    SchoolFeeConfigurationResponse,
    SchoolFeeConfigurationUpdate,
)
from database.session import get_db
from routes.finance_management.service.feeConfiguration import (
    create_school_fee_configuration,
    delete_school_fee_configuration,
    get_school_fee_configuration,
    get_school_fee_configurations,
    update_school_fee_configuration,
)
from utils.school_context import SchoolContext, get_school_context, require_school_roles

router = APIRouter(prefix="/school-fee-configurations", tags=["School Fee Configuration"])


@router.post("/", response_model=SchoolFeeConfigurationResponse)
def create_configuration(
    payload: SchoolFeeConfigurationCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "bursar", "accountant", "principal")),
):
    return create_school_fee_configuration(db, payload, context.school_id)


@router.get("/", response_model=list[SchoolFeeConfigurationResponse])
def get_configurations(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    return get_school_fee_configurations(db, context.school_id)


@router.get("/{config_id}", response_model=SchoolFeeConfigurationResponse)
def get_configuration(
    config_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    config = get_school_fee_configuration(db, config_id, context.school_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found in this school")
    return config


@router.put("/{config_id}", response_model=SchoolFeeConfigurationResponse)
def update_configuration(
    config_id: UUID,
    payload: SchoolFeeConfigurationUpdate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "bursar", "accountant", "principal")),
):
    config = update_school_fee_configuration(db, config_id, payload, context.school_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found in this school")
    return config


@router.delete("/{config_id}")
def delete_configuration(
    config_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "bursar", "principal")),
):
    config = delete_school_fee_configuration(db, config_id, context.school_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found in this school")
    return {"message": "Configuration deleted"}
