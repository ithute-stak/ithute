import re
from datetime import datetime, timezone

from passlib.hash import sha512_crypt

LOCAL_PART_RE = re.compile(r"^[a-z0-9!#$%&'*+/=?^_`{|}~.-]+$")


def normalize_local_part(value: str) -> str:
    local = value.strip().lower()
    if not local or len(local.encode("utf-8")) > 64:
        raise ValueError("Local part must be between 1 and 64 bytes")
    if not LOCAL_PART_RE.fullmatch(local):
        raise ValueError("Local part contains unsupported characters")
    if local.startswith(".") or local.endswith(".") or ".." in local:
        raise ValueError("Local part has invalid dot placement")
    return local


def mailbox_address(local_part: str, domain: str) -> str:
    local = normalize_local_part(local_part)
    address = f"{local}@{domain.strip().lower().rstrip('.')}"
    if len(address) > 320:
        raise ValueError("Mailbox address is too long")
    return address


def normalize_destination(value: str) -> str:
    address = value.strip().lower()
    if address.count("@") != 1:
        raise ValueError("Destination must be an email address")
    local, domain = address.split("@", 1)
    normalize_local_part(local)
    if not domain or "." not in domain or len(address) > 320:
        raise ValueError("Destination must be a valid email address")
    return f"{local}@{domain.rstrip('.')}"


def validate_mailbox_password(password: str) -> None:
    if len(password) < 12:
        raise ValueError("Mailbox password must be at least 12 characters")
    classes = sum(bool(re.search(pattern, password)) for pattern in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if classes < 3:
        raise ValueError("Mailbox password must use at least three character classes")


def hash_mailbox_password(password: str) -> str:
    validate_mailbox_password(password)
    return "{SHA512-CRYPT}" + sha512_crypt.using(rounds=120000).hash(password)


def mailbox_home(address: str) -> str:
    local, domain = address.split("@", 1)
    return f"/srv/vmail/{domain}/{local}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
