from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.core.config import settings
from app.core.security import hash_token
from app.services.webmail import WebmailError, _redis, session_credentials


router = APIRouter(prefix="/webmail", tags=["webmail-compose-tools"])
HOSTED_COOKIE = settings.webmail_session_cookie_name


class ComposeTemplateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    subject: str = Field(default="", max_length=998)
    body_text: str = Field(default="", max_length=2_000_000)
    body_html: str = Field(default="", max_length=2_000_000)


class ComposeSignatureIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    html: str = Field(default="", max_length=20_000)
    is_default: bool = False


class FollowUpIn(BaseModel):
    recipient: EmailStr
    subject: str = Field(default="", max_length=998)
    remind_at: datetime
    source_key: str = Field(default="hosted", min_length=1, max_length=80)
    scheduled_mail_id: str = Field(default="", max_length=80)


def _mailbox_key(token: str | None) -> str:
    try:
        address, _ = session_credentials(token or "")
    except WebmailError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return hash_token(address.lower())


def _hash_key(owner: str, collection: str) -> str:
    return f"webmail:compose:{owner}:{collection}"


def _decode_rows(raw: dict) -> list[dict]:
    rows: list[dict] = []
    for key, value in raw.items():
        row_id = key.decode() if isinstance(key, bytes) else str(key)
        text = value.decode() if isinstance(value, bytes) else str(value)
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            continue
        payload["id"] = row_id
        rows.append(payload)
    return rows


def _put(owner: str, collection: str, row_id: str, payload: dict) -> dict:
    _redis().hset(_hash_key(owner, collection), row_id, json.dumps(payload, separators=(",", ":")))
    return {"id": row_id, **payload}


def _remove(owner: str, collection: str, row_id: str) -> None:
    deleted = int(_redis().hdel(_hash_key(owner, collection), row_id) or 0)
    if not deleted:
        raise HTTPException(status_code=404, detail="Item not found")


@router.get("/compose-templates")
def list_templates(token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None):
    owner = _mailbox_key(token)
    rows = _decode_rows(_redis().hgetall(_hash_key(owner, "templates")))
    rows.sort(key=lambda row: str(row.get("name") or "").lower())
    return {"items": rows}


@router.post("/compose-templates", status_code=201)
def create_template(payload: ComposeTemplateIn, token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None):
    owner = _mailbox_key(token)
    row_id = str(uuid4())
    row = payload.model_dump()
    row["name"] = " ".join(payload.name.split())
    row["created_at"] = datetime.now(timezone.utc).isoformat()
    return _put(owner, "templates", row_id, row)


@router.put("/compose-templates/{template_id}")
def update_template(template_id: str, payload: ComposeTemplateIn, token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None):
    owner = _mailbox_key(token)
    if not _redis().hexists(_hash_key(owner, "templates"), template_id):
        raise HTTPException(status_code=404, detail="Template not found")
    row = payload.model_dump()
    row["name"] = " ".join(payload.name.split())
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    return _put(owner, "templates", template_id, row)


@router.delete("/compose-templates/{template_id}", status_code=204)
def delete_template(template_id: str, token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None):
    _remove(_mailbox_key(token), "templates", template_id)


@router.get("/compose-signatures")
def list_signatures(token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None):
    owner = _mailbox_key(token)
    rows = _decode_rows(_redis().hgetall(_hash_key(owner, "signatures")))
    rows.sort(key=lambda row: (not bool(row.get("is_default")), str(row.get("name") or "").lower()))
    return {"items": rows}


@router.post("/compose-signatures", status_code=201)
def create_signature(payload: ComposeSignatureIn, token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None):
    owner = _mailbox_key(token)
    store = _redis()
    key = _hash_key(owner, "signatures")
    if payload.is_default:
        for item in _decode_rows(store.hgetall(key)):
            item["is_default"] = False
            row_id = str(item.pop("id"))
            store.hset(key, row_id, json.dumps(item, separators=(",", ":")))
    row_id = str(uuid4())
    row = payload.model_dump()
    row["name"] = " ".join(payload.name.split())
    row["created_at"] = datetime.now(timezone.utc).isoformat()
    return _put(owner, "signatures", row_id, row)


@router.put("/compose-signatures/{signature_id}")
def update_signature(signature_id: str, payload: ComposeSignatureIn, token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None):
    owner = _mailbox_key(token)
    store = _redis()
    key = _hash_key(owner, "signatures")
    if not store.hexists(key, signature_id):
        raise HTTPException(status_code=404, detail="Signature not found")
    if payload.is_default:
        for item in _decode_rows(store.hgetall(key)):
            if item["id"] == signature_id:
                continue
            item["is_default"] = False
            row_id = str(item.pop("id"))
            store.hset(key, row_id, json.dumps(item, separators=(",", ":")))
    row = payload.model_dump()
    row["name"] = " ".join(payload.name.split())
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    return _put(owner, "signatures", signature_id, row)


@router.delete("/compose-signatures/{signature_id}", status_code=204)
def delete_signature(signature_id: str, token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None):
    _remove(_mailbox_key(token), "signatures", signature_id)


@router.get("/follow-ups")
def list_follow_ups(token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None):
    owner = _mailbox_key(token)
    rows = _decode_rows(_redis().hgetall(_hash_key(owner, "follow-ups")))
    rows.sort(key=lambda row: str(row.get("remind_at") or ""))
    now = datetime.now(timezone.utc)
    for row in rows:
        try:
            parsed = datetime.fromisoformat(str(row.get("remind_at") or ""))
            row["due"] = parsed <= now
        except ValueError:
            row["due"] = False
    return {"items": rows}


@router.post("/follow-ups", status_code=201)
def create_follow_up(payload: FollowUpIn, token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None):
    owner = _mailbox_key(token)
    remind_at = payload.remind_at
    if remind_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="remind_at must include a timezone")
    if remind_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Follow-up reminder must be in the future")
    row_id = str(uuid4())
    row = payload.model_dump(mode="json")
    row["recipient"] = str(payload.recipient)
    row["status"] = "pending"
    row["created_at"] = datetime.now(timezone.utc).isoformat()
    return _put(owner, "follow-ups", row_id, row)


@router.post("/follow-ups/{follow_up_id}/complete")
def complete_follow_up(follow_up_id: str, token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None):
    owner = _mailbox_key(token)
    store = _redis()
    key = _hash_key(owner, "follow-ups")
    value = store.hget(key, follow_up_id)
    if value is None:
        raise HTTPException(status_code=404, detail="Follow-up reminder not found")
    text = value.decode() if isinstance(value, bytes) else str(value)
    row = json.loads(text)
    row["status"] = "complete"
    row["completed_at"] = datetime.now(timezone.utc).isoformat()
    return _put(owner, "follow-ups", follow_up_id, row)


@router.delete("/follow-ups/{follow_up_id}", status_code=204)
def delete_follow_up(follow_up_id: str, token: Annotated[str | None, Cookie(alias=HOSTED_COOKIE)] = None):
    _remove(_mailbox_key(token), "follow-ups", follow_up_id)
