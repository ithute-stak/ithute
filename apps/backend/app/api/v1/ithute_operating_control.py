from app.api.v1.ithute_operating_common import *  # noqa: F401,F403
from app.api.v1.ithute_operating_common import _product_or_404, _serialize_event, _service_claims, _subject_id

@router.get("/control-center")
def control_center(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
) -> dict[str, Any]:
    _ = current
    products = ensure_default_products(db)
    cards: list[dict[str, Any]] = []
    for product in products:
        card = product_snapshot(db, product)
        deployment = db.scalar(
            select(IthuteProductDeployment)
            .where(IthuteProductDeployment.product_id == product.id)
            .order_by(IthuteProductDeployment.started_at.desc())
            .limit(1)
        )
        backup = db.scalar(
            select(IthuteProductBackup)
            .where(IthuteProductBackup.product_id == product.id)
            .order_by(IthuteProductBackup.created_at.desc())
            .limit(1)
        )
        card["last_deployment"] = (
            {
                "id": str(deployment.id),
                "version": deployment.version,
                "source_sha": deployment.source_sha,
                "status": deployment.status.value,
                "started_at": deployment.started_at.isoformat(),
                "finished_at": deployment.finished_at.isoformat() if deployment.finished_at else None,
            }
            if deployment else None
        )
        card["last_backup"] = (
            {
                "id": str(backup.id),
                "status": backup.status.value,
                "restore_verified": backup.restore_verified,
                "created_at": backup.created_at.isoformat(),
                "verified_at": backup.verified_at.isoformat() if backup.verified_at else None,
            }
            if backup else None
        )
        card["event_count"] = db.scalar(
            select(func.count()).select_from(IthutePlatformEvent).where(IthutePlatformEvent.product_id == product.id)
        ) or 0
        card["open_security_events"] = db.scalar(
            select(func.count())
            .select_from(IthuteSecurityEvent)
            .where(IthuteSecurityEvent.product_id == product.id, IthuteSecurityEvent.resolved_at.is_(None))
        ) or 0
        cards.append(card)

    return {
        "products": cards,
        "totals": {
            "products": len(cards),
            "online": sum(1 for p in cards if p["status"] == "online"),
            "degraded": sum(1 for p in cards if p["status"] == "degraded"),
            "maintenance": sum(1 for p in cards if p["maintenance_mode"]),
            "unread_security": db.scalar(
                select(func.count()).select_from(IthuteSecurityEvent).where(IthuteSecurityEvent.resolved_at.is_(None))
            ) or 0,
            "event_backlog": db.scalar(
                select(func.count())
                .select_from(IthutePlatformEvent)
                .where(IthutePlatformEvent.status.in_([PlatformEventStatus.accepted, PlatformEventStatus.processing]))
            ) or 0,
        },
    }


@router.get("/products")
def products(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
) -> list[dict[str, Any]]:
    _ = current
    return [product_snapshot(db, item) for item in ensure_default_products(db)]


@router.get("/products/{product_id}")
def product_detail(
    product_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
) -> dict[str, Any]:
    _ = current
    product = _product_or_404(db, product_id)
    result = product_snapshot(db, product)
    result["deployments"] = [
        {
            "id": str(item.id),
            "version": item.version,
            "source_sha": item.source_sha,
            "status": item.status.value,
            "started_at": item.started_at.isoformat(),
            "finished_at": item.finished_at.isoformat() if item.finished_at else None,
            "error": item.error,
        }
        for item in db.scalars(
            select(IthuteProductDeployment)
            .where(IthuteProductDeployment.product_id == product_id)
            .order_by(IthuteProductDeployment.started_at.desc())
            .limit(25)
        )
    ]
    result["backups"] = [
        {
            "id": str(item.id),
            "kind": item.kind,
            "status": item.status.value,
            "restore_verified": item.restore_verified,
            "size_bytes": item.size_bytes,
            "created_at": item.created_at.isoformat(),
            "verified_at": item.verified_at.isoformat() if item.verified_at else None,
        }
        for item in db.scalars(
            select(IthuteProductBackup)
            .where(IthuteProductBackup.product_id == product_id)
            .order_by(IthuteProductBackup.created_at.desc())
            .limit(25)
        )
    ]
    return result


@router.post("/products/{product_id}/commands", status_code=202)
def create_command(
    product_id: str,
    payload: CommandIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
) -> dict[str, Any]:
    product = _product_or_404(db, product_id)
    command = IthuteProductCommand(
        product_id=product.id,
        command_type=payload.command_type,
        payload_json=payload.payload,
        requested_by=str(current.auth_user_id or current.id),
    )
    if payload.command_type == "maintenance.enable":
        product.maintenance_mode = True
        product.operational_status = ProductOperationalStatus.maintenance
    elif payload.command_type == "maintenance.disable":
        product.maintenance_mode = False
        if product.operational_status == ProductOperationalStatus.maintenance:
            product.operational_status = ProductOperationalStatus.unknown
    db.add(command)
    db.commit()
    return {"id": str(command.id), "status": command.status, "command_type": command.command_type}


@router.get("/products/{product_id}/commands/next")
def next_command(
    product_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any] | None:
    _service_claims(authorization, scope="platform.commands.read", product_id=product_id)
    _product_or_404(db, product_id)
    item = db.scalar(
        select(IthuteProductCommand)
        .where(IthuteProductCommand.product_id == product_id, IthuteProductCommand.status == "queued")
        .order_by(IthuteProductCommand.created_at)
        .limit(1)
    )
    if item is None:
        return None
    return {
        "id": str(item.id),
        "command_type": item.command_type,
        "payload": item.payload_json,
        "created_at": item.created_at.isoformat(),
    }


@router.patch("/products/{product_id}/commands/{command_id}")
def update_command(
    product_id: str,
    command_id: uuid.UUID,
    payload: CommandUpdate,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _service_claims(authorization, scope="platform.commands.write", product_id=product_id)
    item = db.get(IthuteProductCommand, command_id)
    if item is None or item.product_id != product_id:
        raise HTTPException(status_code=404, detail="Command not found")
    item.status = payload.status
    item.result_json = payload.result
    item.error = payload.error
    if payload.status == "running" and item.started_at is None:
        item.started_at = utcnow()
    if payload.status in {"succeeded", "failed", "cancelled"}:
        item.completed_at = utcnow()
    db.commit()
    return {"id": str(item.id), "status": item.status}


@router.post("/ingest/heartbeat", status_code=202)
def ingest_heartbeat(
    payload: HeartbeatIn,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _service_claims(authorization, scope="platform.heartbeat.write", product_id=payload.product_id)
    product = _product_or_404(db, payload.product_id)
    heartbeat = IthuteProductHeartbeat(
        product_id=payload.product_id,
        status=payload.status,
        version=payload.version,
        database_status=payload.database_status,
        auth_status=payload.auth_status,
        push_status=payload.push_status,
        realtime_status=payload.realtime_status,
        container_summary_json=payload.containers,
        metrics_json=payload.metrics,
        last_error=payload.last_error,
    )
    product.operational_status = payload.status
    if payload.version:
        product.version = payload.version
    db.add(heartbeat)
    db.commit()
    return {"accepted": True, "heartbeat_id": str(heartbeat.id)}
