from app.api.v1.ithute_operating_common import *  # noqa: F401,F403
from app.api.v1.ithute_operating_common import _product_or_404, _serialize_event, _service_claims, _subject_id

@router.post("/ingest/deployment", status_code=202)
def ingest_deployment(
    payload: DeploymentIn,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    claims = _service_claims(authorization, scope="platform.deployments.write", product_id=payload.product_id)
    _product_or_404(db, payload.product_id)
    item = IthuteProductDeployment(
        product_id=payload.product_id,
        version=payload.version,
        source_sha=payload.source_sha,
        environment=payload.environment,
        target=payload.target,
        status=payload.status,
        initiated_by=str(claims.get("azp")),
        backup_id=payload.backup_id,
        metadata_json=payload.metadata,
        error=payload.error,
        finished_at=payload.finished_at,
    )
    db.add(item)
    db.commit()
    return {"accepted": True, "deployment_id": str(item.id)}


@router.post("/ingest/backup", status_code=202)
def ingest_backup(
    payload: BackupIn,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _service_claims(authorization, scope="platform.backups.write", product_id=payload.product_id)
    _product_or_404(db, payload.product_id)
    item = IthuteProductBackup(
        product_id=payload.product_id,
        kind=payload.kind,
        status=payload.status,
        storage_uri=payload.storage_uri,
        checksum=payload.checksum,
        size_bytes=payload.size_bytes,
        restore_verified=payload.restore_verified,
        metadata_json=payload.metadata,
        verified_at=payload.verified_at,
        expires_at=payload.expires_at,
    )
    db.add(item)
    db.commit()
    return {"accepted": True, "backup_id": str(item.id)}


@router.post("/ingest/security", status_code=202)
def ingest_security_event(
    payload: SecurityEventIn,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    product_id = payload.product_id
    claims = _service_claims(authorization, scope="platform.security.write", product_id=product_id)
    if product_id:
        _product_or_404(db, product_id)
    item = IthuteSecurityEvent(
        product_id=product_id,
        severity=payload.severity,
        event_type=payload.event_type,
        actor_ref=payload.actor_ref or str(claims.get("azp") or ""),
        subject_ref=payload.subject_ref,
        source_ip=payload.source_ip,
        details_json=payload.details,
    )
    db.add(item)
    db.commit()
    return {"accepted": True, "security_event_id": str(item.id)}


@router.get("/security")
def security_events(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
) -> list[dict[str, Any]]:
    _ = current
    return [
        {
            "id": str(item.id),
            "product_id": item.product_id,
            "severity": item.severity.value,
            "event_type": item.event_type,
            "actor_ref": item.actor_ref,
            "subject_ref": item.subject_ref,
            "source_ip": item.source_ip,
            "details": item.details_json,
            "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
            "created_at": item.created_at.isoformat(),
        }
        for item in db.scalars(select(IthuteSecurityEvent).order_by(IthuteSecurityEvent.created_at.desc()).limit(limit))
    ]


@router.get("/secrets")
def list_secret_references(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
) -> list[dict[str, Any]]:
    _ = current
    return [
        {
            "id": str(item.id),
            "product_id": item.product_id,
            "name": item.name,
            "provider": item.provider,
            "reference": item.reference,
            "version": item.version,
            "rotation_due_at": item.rotation_due_at.isoformat() if item.rotation_due_at else None,
            "last_rotated_at": item.last_rotated_at.isoformat() if item.last_rotated_at else None,
        }
        for item in db.scalars(select(IthuteSecretReference).order_by(IthuteSecretReference.name))
    ]


@router.post("/secrets", status_code=201)
def create_secret_reference(
    payload: SecretReferenceIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
) -> dict[str, Any]:
    _ = current
    if payload.product_id:
        _product_or_404(db, payload.product_id)
    item = IthuteSecretReference(
        product_id=payload.product_id,
        name=payload.name,
        provider=payload.provider,
        reference=payload.reference,
        version=payload.version,
        rotation_due_at=payload.rotation_due_at,
        metadata_json=payload.metadata,
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Secret reference already exists") from exc
    return {"id": str(item.id), "created": True}


@router.get("/developer/clients")
def developer_clients(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
) -> list[dict[str, Any]]:
    _ = current
    return [
        {
            "id": str(item.id),
            "client_id": item.client_id,
            "name": item.name,
            "owner_ref": item.owner_ref,
            "allowed_products": item.allowed_products_json,
            "scopes": item.scopes_json,
            "is_active": item.is_active,
        }
        for item in db.scalars(select(IthuteDeveloperClient).order_by(IthuteDeveloperClient.name))
    ]


@router.post("/developer/clients", status_code=201)
def create_developer_client(
    payload: DeveloperClientIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
) -> dict[str, Any]:
    _ = current
    item = IthuteDeveloperClient(
        client_id=payload.client_id,
        name=payload.name,
        owner_ref=payload.owner_ref,
        allowed_products_json=payload.allowed_products,
        scopes_json=payload.scopes,
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Developer client already exists") from exc
    return {"id": str(item.id), "client_id": item.client_id}


@router.post("/developer/webhooks", status_code=201)
def create_webhook(
    payload: WebhookIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
) -> dict[str, Any]:
    _ = current
    if db.get(IthuteDeveloperClient, payload.developer_client_id) is None:
        raise HTTPException(status_code=404, detail="Developer client not found")
    if payload.product_id:
        _product_or_404(db, payload.product_id)
    item = IthuteWebhookSubscription(
        developer_client_id=payload.developer_client_id,
        product_id=payload.product_id,
        event_pattern=payload.event_pattern,
        target_url=str(payload.target_url),
        secret_reference_id=payload.secret_reference_id,
    )
    db.add(item)
    db.commit()
    return {"id": str(item.id), "created": True}


@router.get("/support/contexts")
def support_contexts(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    _ = current
    rows = list(db.scalars(select(IthuteSupportContext).order_by(IthuteSupportContext.created_at.desc()).limit(limit)))
    return [
        {
            "id": str(row.id),
            "support_ticket_id": str(row.support_ticket_id),
            "product_id": row.product_id,
            "organization_ref": row.organization_ref,
            "user_ref": row.user_ref,
            "trace_id": row.trace_id,
            "deployment_id": str(row.deployment_id) if row.deployment_id else None,
            "context": row.context_json,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.put("/support/contexts")
def upsert_support_context(
    payload: SupportContextIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    _ = current
    if payload.product_id and db.get(IthuteProduct, payload.product_id) is None:
        raise HTTPException(status_code=404, detail="Unknown Ithute product")
    row = db.scalar(select(IthuteSupportContext).where(IthuteSupportContext.support_ticket_id == payload.support_ticket_id))
    if row is None:
        row = IthuteSupportContext(support_ticket_id=payload.support_ticket_id)
        db.add(row)
    row.product_id = payload.product_id
    row.organization_ref = payload.organization_ref
    row.user_ref = payload.user_ref
    row.trace_id = payload.trace_id
    row.deployment_id = payload.deployment_id
    row.context_json = payload.context
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "support_ticket_id": str(row.support_ticket_id)}
