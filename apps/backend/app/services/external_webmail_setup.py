import imaplib
import json
import secrets
import smtplib
import socket
import ssl
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import redis

from app.core.config import settings
from app.core.security import encrypt_secret, hash_token
from app.services.external_webmail import (
    ExternalMailboxConfig,
    ExternalWebmailError,
    _assert_public_host,
    _redis,
    _session_key,
    _tls_context,
    normalized_config,
)


@dataclass(frozen=True)
class ExternalConnectionResult:
    token: str
    config: ExternalMailboxConfig
    auto_configured: bool


class ExternalSetupError(ExternalWebmailError):
    def __init__(self, message: str, *, authentication_failed: bool = False):
        super().__init__(message)
        self.authentication_failed = authentication_failed


def _probe_timeout() -> float:
    configured = float(getattr(settings, "webmail_transport_timeout_seconds", 10) or 10)
    return max(3.0, min(configured, 7.0))


def _profile_key(address: str) -> str:
    normalized = (address or "").strip().lower()
    return f"webmail:external-known:{hash_token(normalized)}"


def _persist_verified_session(config: ExternalMailboxConfig) -> str:
    """Create a session and remember only the verified connection profile.

    The password is encrypted in the short-lived session exactly as before, but
    it is never stored in the long-lived known-account profile.
    """
    token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc).isoformat()

    session_payload = asdict(config)
    session_payload["password"] = encrypt_secret(config.password)
    session_payload["created_at"] = now

    profile_payload = config.public_dict()
    profile_payload["verified_at"] = now

    try:
        client = _redis()
        pipeline = client.pipeline()
        pipeline.setex(
            _session_key(token),
            settings.webmail_session_ttl_seconds,
            json.dumps(session_payload, separators=(",", ":")),
        )
        pipeline.set(
            _profile_key(config.address),
            json.dumps(profile_payload, separators=(",", ":")),
        )
        pipeline.execute()
    except redis.RedisError as exc:
        raise ExternalSetupError("External webmail session store is unavailable") from exc
    return token


def _known_config(address: str, password: str, display_name: str) -> ExternalMailboxConfig | None:
    """Load a previously verified external account without storing its password."""
    try:
        raw = _redis().get(_profile_key(address))
    except redis.RedisError as exc:
        raise ExternalSetupError("External webmail account registry is unavailable") from exc

    if not raw:
        return None

    try:
        payload = json.loads(raw)
        return normalized_config(
            address=address,
            username=str(payload["username"]),
            password=password,
            display_name=(display_name or str(payload.get("display_name") or "")),
            imap_host=str(payload["imap_host"]),
            imap_port=int(payload["imap_port"]),
            imap_security=str(payload["imap_security"]),
            smtp_host=str(payload["smtp_host"]),
            smtp_port=int(payload["smtp_port"]),
            smtp_security=str(payload["smtp_security"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, ExternalWebmailError):
        # A stale or malformed remembered profile must never block recovery.
        # The normal secure discovery path below can verify fresh settings.
        return None


def connect_known_external_account(
    *,
    address: str,
    password: str,
    display_name: str = "",
) -> ExternalConnectionResult | None:
    """Fast sign-in for an external mailbox that has already been verified."""
    mailbox = (address or "").strip().lower()
    if "@" not in mailbox or mailbox.startswith("@") or mailbox.endswith("@"):
        raise ExternalSetupError("Enter a valid mailbox address")
    if not password:
        raise ExternalSetupError("Mailbox password is required", authentication_failed=True)

    known = _known_config(mailbox, password, display_name)
    if known is None:
        return None

    outcome = _probe_imap(
        known.imap_host,
        known.imap_port,
        known.imap_security,
        known.username,
        password,
    )
    if outcome == "ok":
        token = _persist_verified_session(known)
        return ExternalConnectionResult(token=token, config=known, auto_configured=True)
    if outcome == "auth":
        raise ExternalSetupError(
            "The mailbox password was not accepted. Check the email address and password and try again.",
            authentication_failed=True,
        )
    raise ExternalSetupError(
        "This known mailbox could not reach its saved mail server securely. "
        "Use external mailbox setup once to refresh its server settings."
    )


def _unique(rows):
    result = []
    seen = set()
    for row in rows:
        key = tuple(row)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _incoming_candidates(address: str, host: str, port: int, security: str):
    domain = address.rsplit("@", 1)[1]
    supplied = []
    if host:
        supplied.append((host.strip().lower(), int(port or 993), (security or "ssl").strip().lower()))
    return _unique(
        supplied
        + [
            (f"mail.{domain}", 993, "ssl"),
            (f"imap.{domain}", 993, "ssl"),
            (f"mail.{domain}", 143, "starttls"),
            (f"imap.{domain}", 143, "starttls"),
        ]
    )


def _outgoing_candidates(address: str, host: str, port: int, security: str):
    domain = address.rsplit("@", 1)[1]
    host_value = (host or "").strip().lower()
    port_value = int(port or 587)
    security_value = (security or "starttls").strip().lower()

    standard = [
        (f"mail.{domain}", 587, "starttls"),
        (f"smtp.{domain}", 587, "starttls"),
        (f"mail.{domain}", 465, "ssl"),
        (f"smtp.{domain}", 465, "ssl"),
        (f"mail.{domain}", 2525, "starttls"),
        (f"smtp.{domain}", 2525, "starttls"),
    ]

    # The old web UI generated mail.<domain>:465/SSL as its default. Prefer
    # the modern submission port first for that generated value, while still
    # keeping explicitly-entered settings as the first candidate otherwise.
    looks_like_old_default = (
        host_value == f"mail.{domain}" and port_value == 465 and security_value == "ssl"
    )
    supplied = [(host_value, port_value, security_value)] if host_value else []
    return _unique((standard + supplied) if looks_like_old_default else (supplied + standard))


def _probe_imap(host: str, port: int, security: str, username: str, password: str) -> str:
    _assert_public_host(host, port)
    client = None
    try:
        if security == "ssl":
            client = imaplib.IMAP4_SSL(
                host,
                port,
                ssl_context=_tls_context(),
                timeout=_probe_timeout(),
            )
        elif security == "starttls":
            client = imaplib.IMAP4(host, port, timeout=_probe_timeout())
            client.starttls(ssl_context=_tls_context())
        else:
            return "settings"
        client.login(username, password)
        client.noop()
        return "ok"
    except imaplib.IMAP4.error:
        return "auth"
    except (socket.timeout, TimeoutError):
        return "timeout"
    except (OSError, ssl.SSLError):
        return "network"
    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass


def _probe_smtp(host: str, port: int, security: str, username: str, password: str) -> str:
    _assert_public_host(host, port)
    client = None
    try:
        if security == "ssl":
            client = smtplib.SMTP_SSL(
                host,
                port,
                timeout=_probe_timeout(),
                context=_tls_context(),
            )
            client.ehlo()
        elif security == "starttls":
            client = smtplib.SMTP(host, port, timeout=_probe_timeout())
            client.ehlo()
            client.starttls(context=_tls_context())
            client.ehlo()
        else:
            return "settings"
        client.login(username, password)
        client.noop()
        return "ok"
    except smtplib.SMTPAuthenticationError:
        return "auth"
    except (socket.timeout, TimeoutError):
        return "timeout"
    except (smtplib.SMTPException, OSError, ssl.SSLError):
        return "network"
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:
                try:
                    client.close()
                except Exception:
                    pass


def connect_external_account(
    *,
    address: str,
    username: str,
    password: str,
    display_name: str,
    imap_host: str = "",
    imap_port: int = 993,
    imap_security: str = "ssl",
    smtp_host: str = "",
    smtp_port: int = 587,
    smtp_security: str = "starttls",
) -> ExternalConnectionResult:
    mailbox = (address or "").strip().lower()
    if "@" not in mailbox or mailbox.startswith("@") or mailbox.endswith("@"):
        raise ExternalSetupError("Enter a valid external mailbox address")
    login = (username or mailbox).strip()
    if not login:
        login = mailbox
    if not password:
        raise ExternalSetupError("Mailbox password is required", authentication_failed=True)

    # Fast path: once an external mailbox has successfully completed the full
    # secure setup, treat it as a known iMail mailbox on future sign-ins.
    try:
        known_result = connect_known_external_account(
            address=mailbox,
            password=password,
            display_name=display_name,
        )
    except ExternalSetupError as exc:
        if exc.authentication_failed:
            raise
        # A provider can change hosts or TLS policy. Setup-mode login is
        # allowed to fall through to discovery so the remembered account can
        # repair itself automatically.
        known_result = None
    if known_result is not None:
        return known_result

    incoming_match = None
    incoming_auth_rejected = False
    incoming_attempted = False
    for host, port, security in _incoming_candidates(mailbox, imap_host, imap_port, imap_security):
        try:
            # normalized_config applies the same host, port, TLS and SSRF policy
            # as normal external-webmail sessions before any probe is made.
            normalized_config(
                address=mailbox,
                username=login,
                password=password,
                display_name=display_name,
                imap_host=host,
                imap_port=port,
                imap_security=security,
                smtp_host=smtp_host or f"mail.{mailbox.rsplit('@', 1)[1]}",
                smtp_port=smtp_port or 587,
                smtp_security=smtp_security or "starttls",
            )
            incoming_attempted = True
            outcome = _probe_imap(host, port, security, login, password)
        except ExternalWebmailError:
            continue
        if outcome == "ok":
            incoming_match = (host, port, security)
            break
        if outcome == "auth":
            incoming_auth_rejected = True

    if incoming_match is None:
        if incoming_auth_rejected:
            raise ExternalSetupError(
                "The incoming mail server was reached but did not accept the sign-in. "
                "Check the mailbox username and password, or review the IMAP server and security settings.",
                authentication_failed=True,
            )
        detail = "No secure incoming mail server could be verified."
        if incoming_attempted:
            detail = "The incoming mail server could not be reached securely."
        raise ExternalSetupError(
            f"{detail} Review the IMAP host, port and SSL/TLS settings and try again."
        )

    outgoing_match = None
    outgoing_auth_rejected = False
    for host, port, security in _outgoing_candidates(mailbox, smtp_host, smtp_port, smtp_security):
        try:
            normalized_config(
                address=mailbox,
                username=login,
                password=password,
                display_name=display_name,
                imap_host=incoming_match[0],
                imap_port=incoming_match[1],
                imap_security=incoming_match[2],
                smtp_host=host,
                smtp_port=port,
                smtp_security=security,
            )
            outcome = _probe_smtp(host, port, security, login, password)
        except ExternalWebmailError:
            continue
        if outcome == "ok":
            outgoing_match = (host, port, security)
            break
        if outcome == "auth":
            outgoing_auth_rejected = True

    if outgoing_match is None:
        if outgoing_auth_rejected:
            raise ExternalSetupError(
                "Incoming mail connected successfully, but the outgoing mail server did not accept the SMTP sign-in. "
                "Your mailbox password may still be correct. Check the SMTP username, port, SSL/TLS mode, or the server's outgoing-mail authentication policy."
            )
        raise ExternalSetupError(
            "Incoming mail connected successfully, but no secure outgoing mail server could be verified. "
            "Check the SMTP host, port and SSL/TLS settings."
        )

    config = normalized_config(
        address=mailbox,
        username=login,
        password=password,
        display_name=display_name,
        imap_host=incoming_match[0],
        imap_port=incoming_match[1],
        imap_security=incoming_match[2],
        smtp_host=outgoing_match[0],
        smtp_port=outgoing_match[1],
        smtp_security=outgoing_match[2],
    )

    # The probes above have already authenticated both IMAP and SMTP. Do not
    # repeat those network round trips just to create the session. Persist the
    # session and remember the verified profile for future fast sign-ins.
    token = _persist_verified_session(config)

    supplied_matches = (
        (imap_host or "").strip().lower() == incoming_match[0]
        and int(imap_port or 993) == incoming_match[1]
        and (imap_security or "ssl").strip().lower() == incoming_match[2]
        and (smtp_host or "").strip().lower() == outgoing_match[0]
        and int(smtp_port or 587) == outgoing_match[1]
        and (smtp_security or "starttls").strip().lower() == outgoing_match[2]
    )
    return ExternalConnectionResult(token=token, config=config, auto_configured=not supplied_matches)
