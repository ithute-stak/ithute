from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.employee_management.schemas.schoo_principal import PrincipalRead, PrincipalCreate
from database.multi_tenant_school_management.models import Principal
from database.session import get_db
from routes.finance_management.employee_managemen.service.school_principal import PrincipalService

router = APIRouter(
    prefix="/principals",
    tags=["Principals"],
)


@router.post(
    "/",
    response_model=PrincipalRead,
)
def create_principal(
    payload: PrincipalCreate,
    db: Session = Depends(get_db),
):
    return PrincipalService.create_principal(
        db=db,
        payload=payload,
    )


@router.get(
    "/",
    response_model=list[PrincipalRead],
)
def get_all_principals(
    db: Session = Depends(get_db),
):
    return PrincipalService.get_all_principals(db)


@router.get(
    "/{principal_id}",
    response_model=PrincipalRead,
)
def get_principal(
    principal_id: UUID,
    db: Session = Depends(get_db),
):
    principal = PrincipalService.get_principal(
        db=db,
        principal_id=principal_id,
    )

    if not principal:
        raise HTTPException(
            status_code=404,
            detail="Principal not found",
        )

    return principal


@router.get(
    "/school/{school_id}",
    response_model=PrincipalRead,
)
def get_principal_by_school(
    school_id: UUID,
    db: Session = Depends(get_db),
):
    principal = PrincipalService.get_principal_by_school(
        db=db,
        school_id=school_id,
    )

    if not principal:
        raise HTTPException(
            status_code=404,
            detail="Principal not found for this school",
        )

    return principal


@router.delete("/{principal_id}")
def delete_principal(
    principal_id: UUID,
    db: Session = Depends(get_db),
):
    principal = (
        db.query(Principal)
        .filter(Principal.id == principal_id)
        .first()
    )

    if not principal:
        raise HTTPException(
            status_code=404,
            detail="Principal not found",
        )

    PrincipalService.delete_principal(
        db=db,
        principal=principal,
    )

    return {
        "message": "Principal deleted successfully"
    }