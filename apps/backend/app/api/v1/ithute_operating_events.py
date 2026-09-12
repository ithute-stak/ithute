from app.api.v1.ithute_operating_common import *  # noqa: F401,F403
from app.api.v1.ithute_operating_common import _product_or_404, _serialize_event, _service_claims, _subject_id

@router.post("/events", status_code=202)
def publish_event(
    payload: EventIn,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _service_claims(authorization, scope="platform.events.publish", product_id=payload.product_id)
    _product_or_404(db, payload.product_id)
    event = IthutePlatformEvent(
        product_id=payload.product_id,
        source_event_id=payload.source_event_id,
        event_type=payload.event_type,
        subject=payload.subject,
        tenant_ref=payload.tenant_ref,
        trace_id=payload.trace_id,
        payload_json=payload.payload,
        occurred_at=payload.occurred_at.astimezone(timezone.utc),
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(IthutePlatformEvent).where(
                IthutePlatformEvent.product_id == payload.product_id,
                IthutePlatformEvent.source_event_id == payload.source_event_id,
            )
        )
        if existing is None:
            raise
        return {"accepted": True, "duplicate": True, "event_id": str(existing.id)}

    notification = payload.payload.get("notification")
    if isinstance(notification, dict):
        recipient = str(notification.get("recipient_sub") or "").strip()
        title = str(notification.get("title") or "").strip()
        body = str(notification.get("body") or "").strip()
        if recipient and title and body:
            db.add(
                IthutePlatformNotification(
                    recipient_sub=recipient[:255],
                    product_id=payload.product_id,
                    event_id=event.id,
                    title=title[:240],
                    body=body[:8000],
                    category=str(notification.get("category") or "general")[:100],
                    action_url=(str(notification.get("action_url"))[:1024] if notification.get("action_url") else None),
                    metadata_json=notification.get("metadata") if isinstance(notification.get("metadata"), dict) else {},
                )
            )
    db.commit()
    return {"accepted": True, "duplicate": False, "event_id": str(event.id)}


@router.get("/events")
def list_events(
    product_id: str | None = Query(default=None, max_length=80),
    event_type: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=50, ge=1, le=250),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
) -> list[dict[str, Any]]:
    _ = current
    query = select(IthutePlatformEvent)
    if product_id:
        query = query.where(IthutePlatformEvent.product_id == product_id)
    if event_type:
        query = query.where(IthutePlatformEvent.event_type == event_type)
    query = query.order_by(IthutePlatformEvent.created_at.desc()).limit(limit)
    return [_serialize_event(item) for item in db.scalars(query)]


@router.post("/notifications", status_code=202)
def create_notification(
    payload: NotificationIn,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _service_claims(authorization, scope="platform.notifications.write", product_id=payload.product_id)
    _product_or_404(db, payload.product_id)
    item = IthutePlatformNotification(
        recipient_sub=payload.recipient_sub,
        product_id=payload.product_id,
        title=payload.title,
        body=payload.body,
        category=payload.category,
        action_url=payload.action_url,
        metadata_json=payload.metadata,
    )
    db.add(item)
    db.commit()
    return {"id": str(item.id), "accepted": True}


@router.get("/me/apps")
def my_apps(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    products = ensure_default_products(db)
    if current.is_platform_owner:
        return [product_snapshot(db, item) for item in products]

    subject = _subject_id(current)
    grants = list(
        db.scalars(
            select(IthuteSubscriptionGrant).where(
                IthuteSubscriptionGrant.subject_type == "user",
                IthuteSubscriptionGrant.subject_id == subject,
                IthuteSubscriptionGrant.status.in_([SubscriptionGrantStatus.demo, SubscriptionGrantStatus.active]),
            )
        )
    )
    allowed = {grant.product_id: grant for grant in grants}
    allowed.setdefault("mailbox-dns", None)
    result = []
    for product in products:
        if product.id not in allowed:
            continue
        card = product_snapshot(db, product)
        grant = allowed[product.id]
        card["license"] = (
            {"plan": grant.plan, "status": grant.status.value, "features": grant.features_json}
            if grant is not None else {"plan": "legacy", "status": "active", "features": {}}
        )
        result.append(card)
    return result


@router.get("/me/notifications")
def my_notifications(
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    subject = _subject_id(current)
    query = select(IthutePlatformNotification).where(IthutePlatformNotification.recipient_sub == subject)
    if unread_only:
        query = query.where(IthutePlatformNotification.read_at.is_(None))
    query = query.order_by(IthutePlatformNotification.created_at.desc()).limit(limit)
    return [
        {
            "id": str(item.id),
            "product_id": item.product_id,
            "title": item.title,
            "body": item.body,
            "category": item.category,
            "action_url": item.action_url,
            "metadata": item.metadata_json,
            "read_at": item.read_at.isoformat() if item.read_at else None,
            "created_at": item.created_at.isoformat(),
        }
        for item in db.scalars(query)
    ]


@router.post("/me/notifications/{notification_id}/read", status_code=204)
def read_notification(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> None:
    item = db.get(IthutePlatformNotification, notification_id)
    if item is None or item.recipient_sub != _subject_id(current):
        raise HTTPException(status_code=404, detail="Notification not found")
    item.read_at = utcnow()
    db.commit()


@router.put("/subscriptions/grant")
def upsert_subscription(
    payload: SubscriptionGrantIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
) -> dict[str, Any]:
    _ = current
    _product_or_404(db, payload.product_id)
    item = db.scalar(
        select(IthuteSubscriptionGrant).where(
            IthuteSubscriptionGrant.subject_type == payload.subject_type,
            IthuteSubscriptionGrant.subject_id == payload.subject_id,
            IthuteSubscriptionGrant.product_id == payload.product_id,
        )
    )
    if item is None:
        item = IthuteSubscriptionGrant(
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            product_id=payload.product_id,
        )
        db.add(item)
    item.plan = payload.plan
    item.status = payload.status
    item.features_json = payload.features
    item.starts_at = payload.starts_at
    item.ends_at = payload.ends_at
    db.commit()
    return {
        "id": str(item.id),
        "product_id": item.product_id,
        "plan": item.plan,
        "status": item.status.value,
    }
