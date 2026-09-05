import time

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import AuditLog
from app.models.domains import Domain, DomainDnsMode, DomainStatus
from app.services.domains import add_domain_event
from app.services.mail_dns_reconcile import MailDNSReconcileError, reconcile_mail_dns
from app.services.system_mailboxes_smoke import main as system_mailboxes_smoke


def main() -> None:
    failures = 0
    reconciled = 0
    with SessionLocal() as db:
        domains = db.scalars(
            select(Domain)
            .where(
                Domain.status == DomainStatus.verified,
                Domain.dns_mode == DomainDnsMode.platform,
                Domain.mail_enabled.is_(True),
            )
            .order_by(Domain.ascii_name.asc())
        ).all()

        for domain in domains:
            actor_user_id = domain.created_by_user_id
            try:
                result = reconcile_mail_dns(db, domain, actor_user_id)
            except MailDNSReconcileError as exc:
                failures += 1
                add_domain_event(
                    db,
                    domain,
                    actor_user_id,
                    "mail.dns_reconcile_failed",
                    {"detail": str(exc), "source": "production-backfill"},
                )
                db.add(
                    AuditLog(
                        tenant_id=domain.tenant_id,
                        actor_user_id=actor_user_id,
                        action="deliverability.mail_dns.reconcile_failed",
                        resource_type="deliverability",
                        resource_id=str(domain.id),
                        metadata_json='{"source":"production-backfill"}',
                    )
                )
                db.commit()
                print(f"ERROR {domain.ascii_name}: {exc}")
                continue

            reconciled += 1
            add_domain_event(
                db,
                domain,
                actor_user_id,
                "mail.dns_reconciled",
                {
                    "selector": result.selector,
                    "dkim_created": result.dkim_created,
                    "record_count": len(result.records),
                    "source": "production-backfill",
                },
            )
            db.add(
                AuditLog(
                    tenant_id=domain.tenant_id,
                    actor_user_id=actor_user_id,
                    action="deliverability.mail_dns.reconcile",
                    resource_type="deliverability",
                    resource_id=str(domain.id),
                    metadata_json=(
                        '{"source":"production-backfill","selector":"'
                        + result.selector
                        + '"}'
                    ),
                )
            )
            db.commit()
            print(
                f"OK {domain.ascii_name}: selector={result.selector} "
                f"records={len(result.records)} dkim_created={result.dkim_created}"
            )

    print(f"Mail DNS reconciliation summary: reconciled={reconciled} failures={failures}")
    if failures:
        raise SystemExit(1)

    # The built-in !thute mailboxes are provisioned during backend bootstrap.
    # Once DNS/DKIM identities have been reconciled, prove that authenticated
    # SMTP submission is functional.  Postfix may still be finishing startup,
    # so retry briefly instead of making deployment timing brittle.  The smoke
    # itself is idempotent and sends only once after its first successful run.
    last_error: BaseException | None = None
    for attempt in range(1, 13):
        try:
            system_mailboxes_smoke()
            last_error = None
            break
        except (Exception, SystemExit) as exc:
            last_error = exc
            if attempt < 12:
                print(f"System mailbox SMTP smoke not ready (attempt {attempt}/12): {exc}")
                time.sleep(5)
    if last_error is not None:
        raise SystemExit(f"System mailbox SMTP smoke failed: {last_error}")


if __name__ == "__main__":
    main()
