"""Database-backed client registration operations (not routed until migration is deployed)."""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Application, ApplicationRedirectURI
from .redirect_uri_policy import validate_redirect_uris

_CLIENT_ID = re.compile(r"^[a-z][a-z0-9-]{2,59}$")


def register_application(db: Session, *, client_id: str, name: str, redirect_uris: list[str]) -> Application:
    """Create an inactive-by-default OAuth client; caller owns transaction."""
    if not _CLIENT_ID.fullmatch(client_id):
        raise ValueError("Client ID must use 3-60 lowercase letters, digits or hyphens")
    name = name.strip()
    if not name or len(name) > 160:
        raise ValueError("Invalid application name")
    urls = validate_redirect_uris(redirect_uris)
    if db.scalar(select(Application.id).where(Application.client_id == client_id)) is not None:
        raise ValueError("Application client ID already exists")
    app = Application(client_id=client_id, name=name, is_active=False)
    db.add(app)
    db.flush()
    for uri in urls:
        db.add(ApplicationRedirectURI(application_id=app.id, redirect_uri=uri))
    return app


def replace_redirect_uris(db: Session, *, application: Application, redirect_uris: list[str]) -> None:
    """Replace callbacks transactionally. A disabled app cannot be activated without callbacks."""
    urls = validate_redirect_uris(redirect_uris)
    previous = db.scalars(select(ApplicationRedirectURI).where(
        ApplicationRedirectURI.application_id == application.id
    )).all()
    for row in previous:
        db.delete(row)
    db.flush()
    for uri in urls:
        db.add(ApplicationRedirectURI(application_id=application.id, redirect_uri=uri))
