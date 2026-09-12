from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_dkim_secret
from app.models.deliverability import DkimKey
from app.models.domains import Domain, DomainStatus


def sync_active_dkim_keys(db: Session) -> int:
    """Synchronize active DKIM signing material into Rspamd's isolated Redis.

    Private keys are decrypted only in-process and written exclusively to the
    dedicated Rspamd signing Redis data plane. They are never stored alongside
    control-plane sessions, throttles, or application cache data.
    """
    redis = Redis.from_url(settings.rspamd_redis_url, decode_responses=True)
    rows = db.execute(
        select(DkimKey, Domain)
        .join(Domain, Domain.id == DkimKey.domain_id)
        .where(
            DkimKey.active.is_(True),
            Domain.status == DomainStatus.verified,
            Domain.mail_enabled.is_(True),
        )
    ).all()

    desired_domains: set[str] = set()
    desired_key_fields: set[str] = set()
    pipe = redis.pipeline(transaction=True)

    for key, domain in rows:
        domain_name = domain.ascii_name.lower().rstrip(".")
        selector = key.selector.lower()
        key_field = f"{selector}.{domain_name}"
        desired_domains.add(domain_name)
        desired_key_fields.add(key_field)
        pipe.hset("dkim_selectors", domain_name, selector)
        pipe.hset("dkim_keys", key_field, decrypt_dkim_secret(key.private_key_encrypted))

    existing_domains = set(redis.hkeys("dkim_selectors"))
    existing_keys = set(redis.hkeys("dkim_keys"))
    stale_domains = existing_domains - desired_domains
    stale_keys = existing_keys - desired_key_fields
    if stale_domains:
        pipe.hdel("dkim_selectors", *stale_domains)
    if stale_keys:
        pipe.hdel("dkim_keys", *stale_keys)
    pipe.execute()
    return len(desired_domains)
