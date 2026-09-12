import json
from typing import Annotated

import redis
from fastapi import APIRouter, Cookie, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from app.api.v1.external_webmail import EXTERNAL_COOKIE
from app.services.external_webmail import (
    ExternalWebmailError,
    _redis,
    _session_key,
    session_config,
)
from app.services.external_webmail_setup import _profile_key
from app.services.webmail import WebmailError, save_display_name
from app.services.webmail_polish import contacts, save_contact, save_signature, signature

router = APIRouter(prefix="/webmail/external", tags=["external-webmail-preferences"])


class ExternalSignature(BaseModel):
    html: str = Field(default="", max_length=20000)


class ExternalIdentity(BaseModel):
    display_name: str = Field(default="", max_length=255)


class ExternalContact(BaseModel):
    email: EmailStr
    name: str = Field(default="", max_length=255)


def _address(token: str | None) -> str:
    try:
        return session_config(token or "").address
    except ExternalWebmailError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _failure(exc: WebmailError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


def _update_external_display_name(token: str, address: str, value: str) -> None:
    """Keep the active session and remembered account profile in sync."""
    try:
        store = _redis()
        session_key = _session_key(token)
        raw_session = store.get(session_key)
        if raw_session:
            session_payload = json.loads(raw_session)
            if isinstance(session_payload, dict):
                session_payload["display_name"] = value
                ttl = store.ttl(session_key)
                if ttl > 0:
                    store.setex(
                        session_key,
                        ttl,
                        json.dumps(session_payload, separators=(",", ":")),
                    )

        profile_key = _profile_key(address)
        raw_profile = store.get(profile_key)
        if raw_profile:
            profile_payload = json.loads(raw_profile)
            if isinstance(profile_payload, dict):
                profile_payload["display_name"] = value
                store.set(
                    profile_key,
                    json.dumps(profile_payload, separators=(",", ":")),
                )
    except (redis.RedisError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise WebmailError("Webmail preferences store is unavailable") from exc


@router.put("/identity")
def put_identity(
    payload: ExternalIdentity,
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    token_value = token or ""
    address = _address(token_value)
    value = " ".join(payload.display_name.split())[:255]
    try:
        result = save_display_name(address, value)
        _update_external_display_name(token_value, address, value)
        return {"address": address, **result}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/signature")
def get_signature(
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    address = _address(token)
    try:
        return {"html": signature(address)}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.put("/signature")
def put_signature(
    payload: ExternalSignature,
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    address = _address(token)
    try:
        return save_signature(address, payload.html)
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.get("/contacts")
def get_contacts(
    q: str = Query(default="", max_length=255),
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    address = _address(token)
    try:
        return {"items": contacts(address, q)}
    except WebmailError as exc:
        raise _failure(exc) from exc


@router.post("/contacts", status_code=201)
def put_contact(
    payload: ExternalContact,
    token: Annotated[str | None, Cookie(alias=EXTERNAL_COOKIE)] = None,
):
    address = _address(token)
    try:
        return save_contact(address, str(payload.email), payload.name)
    except WebmailError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
