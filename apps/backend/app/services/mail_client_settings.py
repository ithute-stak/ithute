from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

from app.core.config import settings


@dataclass(frozen=True)
class MailClientSettings:
    email: str
    domain: str
    imap_hostname: str
    imap_port: int = 993
    smtp_hostname: str = ""
    smtp_port: int = 587


def normalize_email_address(value: str) -> tuple[str, str]:
    email = value.strip()
    if not email or email.count("@") != 1:
        raise ValueError("A valid email address is required")
    local, domain = email.rsplit("@", 1)
    domain = domain.strip().rstrip(".").lower()
    if (
        not local
        or not domain
        or "." not in domain
        or len(email) > 254
        or len(local) > 64
        or any(not label or len(label) > 63 for label in domain.split("."))
    ):
        raise ValueError("A valid email address is required")
    return f"{local}@{domain}", domain


def settings_for_email(value: str) -> MailClientSettings:
    email, domain = normalize_email_address(value)
    hostname = settings.mail_hostname.strip().rstrip(".").lower()
    return MailClientSettings(
        email=email,
        domain=domain,
        imap_hostname=hostname,
        smtp_hostname=hostname,
    )


def _xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def thunderbird_autoconfig(value: str) -> bytes:
    client = settings_for_email(value)
    root = ET.Element("clientConfig", {"version": "1.1"})
    provider = ET.SubElement(root, "emailProvider", {"id": client.domain})
    ET.SubElement(provider, "domain").text = client.domain
    ET.SubElement(provider, "displayName").text = "Ithute Mail"
    ET.SubElement(provider, "displayShortName").text = "Ithute"

    incoming = ET.SubElement(provider, "incomingServer", {"type": "imap"})
    ET.SubElement(incoming, "hostname").text = client.imap_hostname
    ET.SubElement(incoming, "port").text = str(client.imap_port)
    ET.SubElement(incoming, "socketType").text = "SSL"
    ET.SubElement(incoming, "authentication").text = "password-cleartext"
    ET.SubElement(incoming, "username").text = "%EMAILADDRESS%"

    outgoing = ET.SubElement(provider, "outgoingServer", {"type": "smtp"})
    ET.SubElement(outgoing, "hostname").text = client.smtp_hostname
    ET.SubElement(outgoing, "port").text = str(client.smtp_port)
    ET.SubElement(outgoing, "socketType").text = "STARTTLS"
    ET.SubElement(outgoing, "authentication").text = "password-cleartext"
    ET.SubElement(outgoing, "username").text = "%EMAILADDRESS%"
    return _xml_bytes(root)


def autodiscover_email_address(payload: bytes) -> str:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError("Malformed Autodiscover XML") from exc
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "EMailAddress" and element.text:
            email, _ = normalize_email_address(element.text)
            return email
    raise ValueError("Autodiscover request is missing EMailAddress")


def outlook_autodiscover(value: str) -> bytes:
    client = settings_for_email(value)
    response_ns = "http://schemas.microsoft.com/exchange/autodiscover/responseschema/2006"
    outlook_ns = "http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a"
    root = ET.Element(f"{{{response_ns}}}Autodiscover")
    response = ET.SubElement(root, f"{{{outlook_ns}}}Response")
    account = ET.SubElement(response, f"{{{outlook_ns}}}Account")
    ET.SubElement(account, f"{{{outlook_ns}}}AccountType").text = "email"
    ET.SubElement(account, f"{{{outlook_ns}}}Action").text = "settings"

    imap = ET.SubElement(account, f"{{{outlook_ns}}}Protocol")
    ET.SubElement(imap, f"{{{outlook_ns}}}Type").text = "IMAP"
    ET.SubElement(imap, f"{{{outlook_ns}}}Server").text = client.imap_hostname
    ET.SubElement(imap, f"{{{outlook_ns}}}Port").text = str(client.imap_port)
    ET.SubElement(imap, f"{{{outlook_ns}}}LoginName").text = client.email
    ET.SubElement(imap, f"{{{outlook_ns}}}SSL").text = "On"
    ET.SubElement(imap, f"{{{outlook_ns}}}AuthRequired").text = "On"

    smtp = ET.SubElement(account, f"{{{outlook_ns}}}Protocol")
    ET.SubElement(smtp, f"{{{outlook_ns}}}Type").text = "SMTP"
    ET.SubElement(smtp, f"{{{outlook_ns}}}Server").text = client.smtp_hostname
    ET.SubElement(smtp, f"{{{outlook_ns}}}Port").text = str(client.smtp_port)
    ET.SubElement(smtp, f"{{{outlook_ns}}}LoginName").text = client.email
    ET.SubElement(smtp, f"{{{outlook_ns}}}Encryption").text = "TLS"
    ET.SubElement(smtp, f"{{{outlook_ns}}}AuthRequired").text = "On"
    return _xml_bytes(root)
