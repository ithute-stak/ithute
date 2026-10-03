from __future__ import annotations

import fcntl
import os
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Domain, MailNode
from app.models.domains import DomainStatus
from app.models.mail import DistributionGroup, MailAlias, Mailbox, MailboxStatus, MailboxStorageType


class MailRoutingSyncError(RuntimeError):
    pass


def _routing_dir() -> Path | None:
    raw = (settings.mail_routing_dir or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        raise MailRoutingSyncError("MAIL_ROUTING_DIR must be an absolute path")
    return path


def _safe_host(value: str) -> str:
    host = value.strip().lower().rstrip(".")
    if not host or any(ch.isspace() for ch in host) or any(ch in host for ch in "[]:/\\"):
        raise MailRoutingSyncError(f"Invalid mail node hostname: {value!r}")
    return host


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _lines(mapping: dict[str, str]) -> str:
    if not mapping:
        return ""
    return "".join(f"{key} {mapping[key]}\n" for key in sorted(mapping))


def build_mail_routing(db: Session) -> dict[str, dict[str, str]]:
    domains = db.scalars(
        select(Domain).where(Domain.status == DomainStatus.verified, Domain.mail_enabled.is_(True))
    ).all()
    domain_names = {domain.id: domain.ascii_name.lower().rstrip(".") for domain in domains}

    nodes = {row.id: row for row in db.scalars(select(MailNode)).all()}
    relay_domains = {name: "OK" for name in domain_names.values()}
    relay_recipients: dict[str, str] = {}
    transport: dict[str, str] = {}
    aliases: dict[str, str] = {}

    for mailbox in db.scalars(select(Mailbox).where(Mailbox.status == MailboxStatus.active)).all():
        if mailbox.domain_id not in domain_names:
            continue
        address = mailbox.address.lower()
        relay_recipients[address] = "OK"
        if mailbox.storage_type == MailboxStorageType.external:
            if mailbox.mail_node_id is None:
                raise MailRoutingSyncError(f"External mailbox {address} has no mail node")
            node = nodes.get(mailbox.mail_node_id)
            if node is None or node.status != "active":
                raise MailRoutingSyncError(f"External mailbox {address} is assigned to an unavailable mail node")
            if node.tenant_id is not None and node.tenant_id != mailbox.tenant_id:
                raise MailRoutingSyncError(f"External mailbox {address} is assigned to another tenant's dedicated mail node")
            transport[address] = f"smtp:[{_safe_host(node.hostname)}]:25"
        else:
            transport[address] = f"smtp:[{_safe_host(settings.mail_gateway_internal_host)}]:25"

    for alias in db.scalars(select(MailAlias).where(MailAlias.active.is_(True))).all():
        if alias.domain_id not in domain_names:
            continue
        source = alias.source_address.lower()
        relay_recipients[source] = "OK"
        aliases[source] = alias.destination_address.lower()

    for group in db.scalars(select(DistributionGroup).where(DistributionGroup.active.is_(True))).all():
        if group.domain_id not in domain_names:
            continue
        source = group.address.lower()
        destinations = sorted({member.destination_address.lower() for member in group.members})
        if not destinations:
            continue
        relay_recipients[source] = "OK"
        aliases[source] = ", ".join(destinations)

    return {
        "relay_domains": relay_domains,
        "relay_recipients": relay_recipients,
        "transport": transport,
        "virtual_aliases": aliases,
    }


def sync_mail_routing(db: Session) -> dict[str, int]:
    root = _routing_dir()
    routes = build_mail_routing(db)
    counts = {key: len(value) for key, value in routes.items()}
    if root is None:
        return counts

    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".routing.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        _atomic_write(root / "relay-domains.cf", _lines(routes["relay_domains"]))
        _atomic_write(root / "relay-recipients.cf", _lines(routes["relay_recipients"]))
        _atomic_write(root / "transport.cf", _lines(routes["transport"]))
        _atomic_write(root / "virtual-aliases.cf", _lines(routes["virtual_aliases"]))
        _atomic_write(root / ".ready", "ready\n")
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return counts
