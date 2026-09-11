from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from .auth import current_claims
from .config import settings
from .db import SessionLocal
from .fleet import _profile, _require_branch, _vehicle
from .fleet_engine import evaluate_vehicle
from .fleet_inventory import vehicle_service_kit_stock
from .fleet_reports import build_branch_summary, vehicle_history_rows
from .models import Vehicle

router = APIRouter(prefix="/api/v1/fleet", tags=["fleet-advisor"])


class AdvisorRequest(BaseModel):
    branch_id: uuid.UUID
    vehicle_id: uuid.UUID | None = None
    question: str = Field(default="What should Fleet management prioritize now?", min_length=1, max_length=1200)


def _deterministic_actions(evidence: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    summary = evidence["branch_summary"]
    readiness = summary["fleet"]["readiness"]
    if readiness["red"]:
        actions.append(f"Prioritize the {readiness['red']} vehicle(s) currently blocked by deterministic Fleet rules.")
    if summary["alerts"]["red"]:
        actions.append(f"Resolve {summary['alerts']['red']} active RED alert(s) before assigning affected vehicles.")
    stock = summary["service_kit_stock"]
    if stock["stock_required"]:
        actions.append(f"Replenish service-kit stock for {stock['stock_required']} vehicle(s) before their next required service.")
    if summary["operations"]["open_maintenance"]:
        actions.append(f"Review expected release dates for {summary['operations']['open_maintenance']} open maintenance job(s).")
    vehicle = evidence.get("vehicle")
    if vehicle:
        snapshot = vehicle["snapshot"]
        for component in ("documents", "service", "mechanical", "inspection", "availability"):
            item = snapshot.get(component)
            if component == "documents": item = item.get("overall") if isinstance(item, dict) else None
            if isinstance(item, dict) and item.get("level") in {"orange", "red"}:
                actions.append(f"{component.title()}: {item.get('label')} — {item.get('detail')}")
        stock_item = vehicle.get("service_kit_stock")
        if isinstance(stock_item, dict) and stock_item.get("level") in {"orange", "red"}:
            actions.append(f"Service kit: {stock_item.get('label')} — {stock_item.get('detail')}")
    if not actions:
        actions.append("No deterministic RED/ORANGE exception currently requires intervention.")
    return actions[:12]


def _provider_payload(evidence: dict[str, Any], question: str) -> dict[str, Any]:
    system = (
        "You are NBros Fleet Advisor. You provide decision support only. The deterministic Fleet engine is authoritative: "
        "never change, soften, or override its GREEN/ORANGE/RED statuses, blockers, compliance results, availability decisions, "
        "or licence rules. Use only the supplied evidence. Do not invent maintenance, legal, safety, inventory, driver, or vehicle facts. "
        "State uncertainties explicitly. Give concise priorities, reasons, operational alternatives, and what record should be updated to resolve each issue."
    )
    return {"model": settings.ai_model, "temperature": 0.2, "messages": [{"role": "system", "content": system}, {"role": "user", "content": f"Question: {question}\n\nAuthoritative Fleet evidence follows as JSON:\n{json.dumps(evidence, ensure_ascii=False, default=str)}"}]}


def _call_provider(evidence: dict[str, Any], question: str) -> str:
    if not (settings.ai_enabled and settings.ai_base_url.strip() and settings.ai_api_key.strip() and settings.ai_model.strip()):
        raise RuntimeError("AI provider is not configured")
    request = urllib.request.Request(
        f"{settings.ai_base_url.rstrip('/')}/chat/completions",
        data=json.dumps(_provider_payload(evidence, question)).encode("utf-8"),
        headers={"Authorization": f"Bearer {settings.ai_api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.ai_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"AI provider request failed: {exc}") from exc
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("AI provider returned an unexpected response") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("AI provider returned an empty advisory")
    return content.strip()


def build_evidence(db, branch_id: uuid.UUID, vehicle_id: uuid.UUID | None) -> dict[str, Any]:
    evidence: dict[str, Any] = {"branch_id": str(branch_id), "branch_summary": build_branch_summary(db, branch_id), "authority": {"deterministic_engine": True, "ai_may_override_rules": False}}
    if vehicle_id is None:
        vehicles = list(db.scalars(select(Vehicle).where(Vehicle.branch_id == branch_id, Vehicle.is_active.is_(True))))
        risks: list[dict[str, Any]] = []
        for vehicle in vehicles:
            snapshot = evaluate_vehicle(db, vehicle)
            if snapshot["readiness"] != "green":
                risks.append({"vehicle_id": str(vehicle.id), "registration_plate": vehicle.registration_plate, "readiness": snapshot["readiness"], "documents": snapshot["documents"]["overall"], "service": snapshot["service"], "mechanical": snapshot["mechanical"], "inspection": snapshot["inspection"], "availability": snapshot["availability"], "service_kit_stock": vehicle_service_kit_stock(db, vehicle, service_snapshot=snapshot.get("service"))})
        evidence["highest_risk_vehicles"] = risks[:20]
        return evidence
    vehicle = _vehicle(db, branch_id, vehicle_id)
    snapshot = evaluate_vehicle(db, vehicle)
    evidence["vehicle"] = {"id": str(vehicle.id), "registration_plate": vehicle.registration_plate, "make": vehicle.make, "model": vehicle.model, "vehicle_type": vehicle.vehicle_type, "current_mileage": vehicle.current_mileage, "snapshot": snapshot, "service_kit_stock": vehicle_service_kit_stock(db, vehicle, service_snapshot=snapshot.get("service")), "recent_history": vehicle_history_rows(db, branch_id, vehicle.id)[:40]}
    return evidence


@router.post("/advisor")
def fleet_advisor(payload: AdvisorRequest, claims: dict = Depends(current_claims)) -> dict[str, Any]:
    with SessionLocal() as db:
        profile = _profile(db, claims); _require_branch(db, profile, payload.branch_id)
        if payload.vehicle_id: _vehicle(db, payload.branch_id, payload.vehicle_id)
        evidence = build_evidence(db, payload.branch_id, payload.vehicle_id)
        deterministic_actions = _deterministic_actions(evidence)
    ai_advice: str | None = None
    ai_error: str | None = None
    mode = "deterministic"
    if settings.ai_enabled:
        try:
            ai_advice = _call_provider(evidence, payload.question); mode = "ai"
        except RuntimeError as exc:
            ai_error = str(exc)
    return {"mode": mode, "question": payload.question, "deterministic_actions": deterministic_actions, "ai_advice": ai_advice, "ai_error": ai_error, "provider_configured": bool(settings.ai_enabled and settings.ai_base_url.strip() and settings.ai_api_key.strip() and settings.ai_model.strip()), "guardrail": "AI advice is advisory only; deterministic Fleet rules remain authoritative.", "evidence": evidence}
