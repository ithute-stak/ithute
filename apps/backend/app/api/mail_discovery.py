from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from app.services.mail_client_settings import (
    autodiscover_email_address,
    outlook_autodiscover,
    thunderbird_autoconfig,
)

router = APIRouter(tags=["mail-discovery"])
_XML_MEDIA_TYPE = "application/xml; charset=utf-8"


def _xml_response(content: bytes) -> Response:
    return Response(
        content=content,
        media_type=_XML_MEDIA_TYPE,
        headers={"Cache-Control": "public, max-age=300"},
    )


def _thunderbird_response(emailaddress: str) -> Response:
    try:
        return _xml_response(thunderbird_autoconfig(emailaddress))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/mail/config-v1.1.xml", include_in_schema=False)
def thunderbird_mail_config(
    emailaddress: str = Query(..., min_length=3, max_length=254),
):
    return _thunderbird_response(emailaddress)


@router.get("/.well-known/autoconfig/mail/config-v1.1.xml", include_in_schema=False)
def thunderbird_well_known_config(
    emailaddress: str = Query(..., min_length=3, max_length=254),
):
    return _thunderbird_response(emailaddress)


@router.post("/autodiscover/autodiscover.xml", include_in_schema=False)
async def microsoft_autodiscover(request: Request):
    payload = await request.body()
    if len(payload) > 64 * 1024:
        raise HTTPException(status_code=413, detail="Autodiscover request is too large")
    try:
        email = autodiscover_email_address(payload)
        return _xml_response(outlook_autodiscover(email))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
