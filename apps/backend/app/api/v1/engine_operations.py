from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import require_platform_owner
from app.models import User
from app.services.engine_router import execute_enterprise_xml, routing_status
from app.services.engine_runtime import engine_status, sample_native_result

router = APIRouter(tags=["engine-operations"])


class EngineSampleRequest(BaseModel):
    text: str = Field(max_length=65536)


class EnterpriseXmlInspectRequest(BaseModel):
    xml: str = Field(min_length=1, max_length=10 * 1024 * 1024)


@router.get("/platform/engines")
def platform_engines(current: User = Depends(require_platform_owner)):
    status = engine_status()
    status["routes"] = routing_status()
    return status


@router.post("/platform/engines/sample")
def platform_engine_sample(
    payload: EngineSampleRequest,
    current: User = Depends(require_platform_owner),
):
    return sample_native_result(payload.text.encode("utf-8"))


@router.post("/platform/engines/xml/inspect")
def platform_engine_xml_inspect(
    payload: EnterpriseXmlInspectRequest,
    current: User = Depends(require_platform_owner),
):
    execution = execute_enterprise_xml(payload.xml.encode("utf-8"))
    return {
        "operation": execution.operation,
        "engine": execution.engine,
        "result": execution.value,
    }
