from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import DomainIntelligenceProfile
from app.services.domain_intelligence_enrichment import apply_automatic_enrichment

logger = logging.getLogger("ithute.domain_intelligence")


def enrich_due_profiles() -> int:
    if not settings.domain_intelligence_enrichment_enabled:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=settings.domain_intelligence_enrichment_stale_seconds
    )
    with SessionLocal() as db:
        rows = db.scalars(
            select(DomainIntelligenceProfile)
            .where(
                or_(
                    DomainIntelligenceProfile.enrichment_checked_at.is_(None),
                    DomainIntelligenceProfile.enrichment_checked_at < cutoff,
                )
            )
            .order_by(
                DomainIntelligenceProfile.enrichment_checked_at.asc().nullsfirst(),
                DomainIntelligenceProfile.last_seen_at.desc(),
            )
            .limit(settings.domain_intelligence_enrichment_batch_size)
        ).all()

        processed = 0
        for profile in rows:
            try:
                apply_automatic_enrichment(
                    db,
                    profile,
                    timeout_seconds=settings.domain_intelligence_enrichment_timeout_seconds,
                )
                db.commit()
                processed += 1
            except Exception as exc:
                db.rollback()
                logger.warning(
                    "domain intelligence enrichment failed domain=%s error=%s",
                    profile.domain,
                    exc.__class__.__name__,
                )
        return processed


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("domain intelligence enrichment worker started")
    while True:
        try:
            processed = enrich_due_profiles()
            if processed:
                logger.info("domain intelligence enrichment processed=%d", processed)
        except Exception:
            logger.exception("domain intelligence enrichment cycle failed")
        time.sleep(settings.domain_intelligence_enrichment_poll_seconds)


if __name__ == "__main__":
    main()
