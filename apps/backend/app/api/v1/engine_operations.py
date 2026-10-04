from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import require_platform_owner
from app.models import User
from app.services.engine_runtime import engine_status, sample_native_result

router = APIRouter(tags=["engine-operations"])


class EngineSampleRequest(BaseModel):
    text: str = Field(max_length=65536)


@router.get("/platform/engines")
def platform_engines(current: User = Depends(require_platform_owner)):
    return engine_status()


@router.post("/platform/engines/sample")
def platform_engine_sample(
    payload: EngineSampleRequest,
    current: User = Depends(require_platform_owner),
):
    return sample_native_result(payload.text.encode("utf-8"))
