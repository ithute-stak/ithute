from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache

import dns.exception
import dns.resolver


@dataclass(frozen=True)
class MailProviderProfile:
    key: str
    name: str
    detected_by: str
    auth_mode: str
    imap_host: str
    imap_port: int
    imap_security: str
    smtp_host: str
    smtp_port: int
    smtp_security: str
    help_text: str

    def public_dict(self) -> dict:
        return asdict(self)


_PROVIDER_PRESETS = {
    "google": {
        "name": "Google Gmail / Workspace",
        "auth_mode": "oauth_preferred",
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "imap_security": "ssl",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "help_text": "Google account detected. Sign in with Google when OAuth is available, or use a Google App Password for IMAP/SMTP.",
    },
    "microsoft365": {
        "name": "Microsoft 365 / Outlook",
        "auth_mode": "oauth_preferred",
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "imap_security": "ssl",
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "help_text": "Microsoft mail detected. OAuth is preferred; manual credentials remain available when the tenant permits IMAP/SMTP authentication.",
    },
    "yahoo": {
        "name": "Yahoo Mail",
        "auth_mode": "app_password",
        "imap_host": "imap.mail.yahoo.com",
        "imap_port": 993,
        "imap_security": "ssl",
        "smtp_host": "smtp.mail.yahoo.com",
        "smtp_port": 465,
        "smtp_security": "ssl",
        "help_text": "Yahoo Mail detected. Use an app password if normal account authentication is blocked.",
    },
    "icloud": {
        "name": "Apple iCloud Mail",
        "auth_mode": "app_password",
        "imap_host": "imap.mail.me.com",
        "imap_port": 993,
        "imap_security": "ssl",
        "smtp_host": "smtp.mail.me.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "help_text": "iCloud Mail detected. Apple typically requires an app-specific password for third-party mail clients.",
    },
    "zoho": {
        "name": "Zoho Mail",
        "auth_mode": "password_or_app_password",
        "imap_host": "imap.zoho.com",
        "imap_port": 993,
        "imap_security": "ssl",
        "smtp_host": "smtp.zoho.com",
        "smtp_port": 465,
        "smtp_security": "ssl",
        "help_text": "Zoho Mail detected. iMail will use Zoho's secure IMAP/SMTP endpoints.",
    },
    "fastmail": {
        "name": "Fastmail",
        "auth_mode": "app_password",
        "imap_host": "imap.fastmail.com",
        "imap_port": 993,
        "imap_security": "ssl",
        "smtp_host": "smtp.fastmail.com",
        "smtp_port": 465,
        "smtp_security": "ssl",
        "help_text": "Fastmail detected. Use an app password generated for iMail.",
    },
}

_DIRECT_DOMAINS = {
    "gmail.com": "google",
    "googlemail.com": "google",
    "outlook.com": "microsoft365",
    "hotmail.com": "microsoft365",
    "live.com": "microsoft365",
    "msn.com": "microsoft365",
    "yahoo.com": "yahoo",
    "ymail.com": "yahoo",
    "rocketmail.com": "yahoo",
    "icloud.com": "icloud",
    "me.com": "icloud",
    "mac.com": "icloud",
    "zoho.com": "zoho",
    "fastmail.com": "fastmail",
    "fastmail.fm": "fastmail",
}


def _normalize_address(address: str) -> tuple[str, str]:
    mailbox = (address or "").strip().lower()
    if mailbox.count("@") != 1:
        raise ValueError("Enter a valid email address")
    local, domain = mailbox.rsplit("@", 1)
    domain = domain.strip().rstrip(".")
    if not local or not domain or "." not in domain:
        raise ValueError("Enter a valid email address")
    return mailbox, domain


def _profile(key: str, detected_by: str) -> MailProviderProfile:
    preset = _PROVIDER_PRESETS[key]
    return MailProviderProfile(key=key, detected_by=detected_by, **preset)


def _provider_from_mx_hosts(hosts: tuple[str, ...]) -> str | None:
    for raw in hosts:
        host = raw.lower().rstrip(".")
        if host.endswith(".google.com") or host.endswith(".googlemail.com"):
            return "google"
        if host.endswith(".mail.protection.outlook.com") or host.endswith(".outlook.com"):
            return "microsoft365"
        if host.endswith(".yahoodns.net") or host.endswith(".yahoo.com"):
            return "yahoo"
        if host.endswith(".icloud.com"):
            return "icloud"
        if host.endswith(".zoho.com") or host.endswith(".zoho.eu") or host.endswith(".zoho.in"):
            return "zoho"
        if host.endswith(".messagingengine.com"):
            return "fastmail"
    return None


@lru_cache(maxsize=512)
def _mx_hosts(domain: str) -> tuple[str, ...]:
    try:
        answer = dns.resolver.resolve(domain, "MX", lifetime=2.5)
        return tuple(sorted(str(row.exchange).lower().rstrip(".") for row in answer))
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout):
        return ()


def detect_mail_provider(address: str) -> MailProviderProfile | None:
    _, domain = _normalize_address(address)
    direct = _DIRECT_DOMAINS.get(domain)
    if direct:
        return _profile(direct, "email_domain")

    hosts = _mx_hosts(domain)
    detected = _provider_from_mx_hosts(hosts)
    if detected:
        return _profile(detected, "mx_records")
    return None


def provider_detection_payload(address: str) -> dict:
    mailbox, domain = _normalize_address(address)
    profile = detect_mail_provider(mailbox)
    if profile:
        return {
            "address": mailbox,
            "domain": domain,
            "detected": True,
            "provider": profile.public_dict(),
        }
    return {
        "address": mailbox,
        "domain": domain,
        "detected": False,
        "provider": {
            "key": "imap",
            "name": "Custom IMAP/SMTP",
            "detected_by": "fallback",
            "auth_mode": "password",
            "imap_host": f"mail.{domain}",
            "imap_port": 993,
            "imap_security": "ssl",
            "smtp_host": f"mail.{domain}",
            "smtp_port": 587,
            "smtp_security": "starttls",
            "help_text": "No major provider was identified. iMail will securely discover standard IMAP/SMTP endpoints and allows manual settings if needed.",
        },
    }


def provider_candidates(address: str) -> tuple[list[tuple[str, int, str]], list[tuple[str, int, str]]]:
    try:
        profile = detect_mail_provider(address)
    except ValueError:
        profile = None
    if not profile:
        return [], []

    incoming = [(profile.imap_host, profile.imap_port, profile.imap_security)]
    outgoing = [(profile.smtp_host, profile.smtp_port, profile.smtp_security)]
    if profile.key == "google":
        outgoing.append(("smtp.gmail.com", 465, "ssl"))
    elif profile.key == "microsoft365":
        outgoing.append(("smtp.office365.com", 587, "starttls"))
    return incoming, outgoing


def migration_provider_key(address: str, imap_host: str = "") -> str:
    try:
        profile = detect_mail_provider(address)
    except ValueError:
        profile = None
    if profile and profile.key == "google":
        return "google"
    if profile and profile.key == "microsoft365":
        return "microsoft365"
    host = (imap_host or "").strip().lower()
    if host == "imap.gmail.com":
        return "google"
    if host == "outlook.office365.com":
        return "microsoft365"
    return "imap"
