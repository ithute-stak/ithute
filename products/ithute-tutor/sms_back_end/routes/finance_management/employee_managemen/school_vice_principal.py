from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.employee_management.schemas.school_vice_principal import VicePrincipalRead, VicePrincipalCreate
from database.multi_tenant_school_management.models import VicePrincipal
from database.session import get_db
from routes.finance_management.employee_managemen.service.school_vice_principal import VicePrincipalService

router = APIRouter(
    prefix="/vice-principals",
    tags=["Vice Principals"],
)


@router.post(
    "/",
    response_model=VicePrincipalRead,
)
def create_vice_principal(
    payload: VicePrincipalCreate,
    db: Session = Depends(get_db),
):
    return VicePrincipalService.create_vice_principal(
        db=db,
        payload=payload,
    )


@router.get(
    "/",
    response_model=list[VicePrincipalRead],
)
def get_all_vice_principals(
    db: Session = Depends(get_db),
):
    return VicePrincipalService.get_all(db)


@router.get(
    "/{vice_principal_id}",
    response_model=VicePrincipalRead,
)
def get_vice_principal(
    vice_principal_id: UUID,
    db: Session = Depends(get_db),
):
    vice_principal = VicePrincipalService.get_one(
        db=db,
        vice_principal_id=vice_principal_id,
    )

    if not vice_principal:
        raise HTTPException(
            status_code=404,
            detail="Vice principal not found",
        )

    return vice_principal


@router.get(
    "/school/{school_id}",
    response_model=list[VicePrincipalRead],
)
def get_vice_principals_by_school(
    school_id: UUID,
    db: Session = Depends(get_db),
):
    return VicePrincipalService.get_by_school(
        db=db,
        school_id=school_id,
    )


@router.delete("/{vice_principal_id}")
def delete_vice_principal(
    vice_principal_id: UUID,
    db: Session = Depends(get_db),
):
    vice_principal = (
        db.query(VicePrincipal)
        .filter(VicePrincipal.id == vice_principal_id)
        .first()
    )

    if not vice_principal:
        raise HTTPException(
            status_code=404,
            detail="Vice principal not found",
        )

    VicePrincipalService.delete(
        db=db,
        vice_principal=vice_principal,
    )

    return {
        "message": "Vice principal deleted successfully"
    }