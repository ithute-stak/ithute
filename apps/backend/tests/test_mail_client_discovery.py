from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.mail_client_settings import (
    autodiscover_email_address,
    outlook_autodiscover,
    thunderbird_autoconfig,
)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def test_thunderbird_autoconfig_uses_secure_imap_and_submission(monkeypatch):
    monkeypatch.setattr(settings, "mail_hostname", "mail.ithute.co.ls")

    root = ET.fromstring(thunderbird_autoconfig("person@example.co.ls"))
    servers = list(root.iter("incomingServer")) + list(root.iter("outgoingServer"))

    incoming = next(server for server in servers if server.attrib["type"] == "imap")
    outgoing = next(server for server in servers if server.attrib["type"] == "smtp")
    assert incoming.findtext("hostname") == "mail.ithute.co.ls"
    assert incoming.findtext("port") == "993"
    assert incoming.findtext("socketType") == "SSL"
    assert incoming.findtext("username") == "%EMAILADDRESS%"
    assert outgoing.findtext("hostname") == "mail.ithute.co.ls"
    assert outgoing.findtext("port") == "587"
    assert outgoing.findtext("socketType") == "STARTTLS"
    assert outgoing.findtext("username") == "%EMAILADDRESS%"


def test_autodiscover_parser_and_response(monkeypatch):
    monkeypatch.setattr(settings, "mail_hostname", "mail.ithute.co.ls")
    request = b"""<?xml version='1.0'?>
    <Autodiscover xmlns='http://schemas.microsoft.com/exchange/autodiscover/outlook/requestschema/2006'>
      <Request><EMailAddress>person@example.co.ls</EMailAddress></Request>
    </Autodiscover>"""

    email = autodiscover_email_address(request)
    root = ET.fromstring(outlook_autodiscover(email))
    values = {(_local_name(node.tag), node.text) for node in root.iter() if node.text}

    assert email == "person@example.co.ls"
    assert ("Type", "IMAP") in values
    assert ("Type", "SMTP") in values
    assert ("Server", "mail.ithute.co.ls") in values
    assert ("Port", "993") in values
    assert ("Port", "587") in values
    assert ("LoginName", "person@example.co.ls") in values


def test_autodiscover_rejects_malformed_xml():
    with pytest.raises(ValueError, match="Malformed"):
        autodiscover_email_address(b"<Autodiscover>")


def test_public_discovery_routes(monkeypatch):
    monkeypatch.setattr(settings, "mail_hostname", "mail.ithute.co.ls")
    client = TestClient(app)

    thunderbird = client.get("/mail/config-v1.1.xml", params={"emailaddress": "person@example.co.ls"})
    assert thunderbird.status_code == 200
    assert "application/xml" in thunderbird.headers["content-type"]
    assert "mail.ithute.co.ls" in thunderbird.text

    request = """<?xml version='1.0'?>
    <Autodiscover xmlns='http://schemas.microsoft.com/exchange/autodiscover/outlook/requestschema/2006'>
      <Request><EMailAddress>person@example.co.ls</EMailAddress></Request>
    </Autodiscover>"""
    outlook = client.post(
        "/autodiscover/autodiscover.xml",
        content=request,
        headers={"content-type": "application/xml"},
    )
    assert outlook.status_code == 200
    assert "mail.ithute.co.ls" in outlook.text
    assert ">993<" in outlook.text
    assert ">587<" in outlook.text
