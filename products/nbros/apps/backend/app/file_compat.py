import uuid

from fastapi import APIRouter, Depends

from .auth import current_claims
from .fleet import read_file

router = APIRouter(tags=["fleet-files"])


@router.get("/api/fleet/files/{branch_id}/{filename}", include_in_schema=False)
def read_legacy_fleet_file(
    branch_id: uuid.UUID,
    filename: str,
    claims: dict = Depends(current_claims),
):
    """Serve document URLs created by the original Fleet upload contract."""
    return read_file(branch_id=branch_id, filename=filename, claims=claims)
