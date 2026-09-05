from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.finace_management.schemas.feePlan import FeePlanCreate, FeePlanResponse, FeePlanUpdate
from database.session import get_db
from routes.finance_management.service.feePlan import (
    create_fee_plan,
    delete_fee_plan,
    get_fee_plan,
    get_fee_plans,
    update_fee_plan,
)
from utils.school_context import SchoolContext, get_school_context, require_school_roles

router = APIRouter(prefix="/fee-plans", tags=["Fee Plans"])


@router.post("/", response_model=FeePlanResponse)
def create_plan(
    payload: FeePlanCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "bursar", "accountant", "principal")),
):
    plan = create_fee_plan(db, payload, context.school_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Fee configuration not found in this school")
    return plan


@router.get("/", response_model=list[FeePlanResponse])
def get_plans(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    return get_fee_plans(db, context.school_id)


@router.get("/{plan_id}", response_model=FeePlanResponse)
def get_plan(
    plan_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    plan = get_fee_plan(db, plan_id, context.school_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Fee plan not found in this school")
    return plan


@router.put("/{plan_id}", response_model=FeePlanResponse)
def update_plan(
    plan_id: UUID,
    payload: FeePlanUpdate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "bursar", "accountant", "principal")),
):
    plan = update_fee_plan(db, plan_id, payload, context.school_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Fee plan not found in this school")
    return plan


@router.delete("/{plan_id}")
def delete_plan(
    plan_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "bursar", "principal")),
):
    plan = delete_fee_plan(db, plan_id, context.school_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Fee plan not found in this school")
    return {"message": "Fee plan deleted"}
