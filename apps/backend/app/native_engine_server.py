from __future__ import annotations

import hmac
import json
import os
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.services.engine_runtime import push_envelope_scan, route_shard


app = FastAPI(title="Ithute Native Engine", version="1.0.0", redoc_url=None)


def _configured_token() -> str:
    return os.getenv("ITHUTE_NATIVE_ENGINE_TOKEN", "").strip()


def require_internal_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = _configured_token()
    supplied = ""
    if authorization and authorization.startswith("Bearer "):
        supplied = authorization[7:].strip()
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="unauthorized")


class RealtimeAnalyzeRequest(BaseModel):
    route_key: str = Field(min_length=1, max_length=512)
    shard_count: int = Field(default=64, ge=1, le=65536)
    frame: dict[str, Any]


@app.get("/healthz")
def healthz() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "ithute-native-engine",
        "engines": ["rust", "cpp"],
    }


@app.post("/v1/realtime/analyze")
def analyze_realtime(
    payload: RealtimeAnalyzeRequest,
    _: Annotated[None, Depends(require_internal_token)],
) -> dict[str, object]:
    raw = json.dumps(payload.frame, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    scan, scan_engine = push_envelope_scan(raw)
    if not scan.utf8_valid or not scan.json_object_shape or scan.nul_bytes or scan.control_bytes:
        raise HTTPException(status_code=422, detail="realtime envelope failed native safety scan")
    shard, shard_engine = route_shard(payload.route_key.encode("utf-8"), payload.shard_count)
    return {
        "scan": asdict(scan),
        "scan_engine": scan_engine,
        "shard": shard,
        "shard_engine": shard_engine,
    }
