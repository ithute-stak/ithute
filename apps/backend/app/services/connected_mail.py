from __future__ import annotations

import base64
import imaplib
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_secret, encrypt_secret
from app.models import ConnectedMailAccount
from app.services.external_webmail import (
    ExternalWebmailError,
    _assert_public_host,
    _attachment_rows,
    _ensure_folder,
    _fetch_raw,
    _folder_for,
    _list_folder_names,
    _message_json,
    _select,
    _tls_context,
)
from app.services.mail_oauth import MailOAuthError, refresh_access_token, xoauth2_bytes, xoauth2_smtp_value
from app.services.mail_search import filter_attachment_rows, parse_mail_search


class ConnectedMailError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConnectedConfig:
    account_id: str
    address: str
    username: str
    display_name: str
    provider: str
    auth_type: str
    password: str
    access_token: str
    imap_host: str
    imap_port: int
    imap_security: str
    smtp_host: str
    smtp_port: int
    smtp_security: str

    def public_dict(self) -> dict:
        return {
            "id": self.account_id,
            "address": self.address,
            "username": self.username,
            "display_name": self.display_name,
            "provider": self.provider,
            "auth_type": self.auth_type,
            "imap_host": self.imap_host,
            "imap_port": self.imap_port,
            "imap_security": self.imap_security,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "smtp_security": self.smtp_security,
        }


def _decrypt(value: str | None) -> str:
    if not value:
        return ""
    try:
        return decrypt_secret(value)
    except ValueError as exc:
        raise ConnectedMailError("Stored mail credential could not be decrypted") from exc


def _fresh_oauth(account: ConnectedMailAccount, db: Session) -> str:
    access = _decrypt(account.oauth_access_token_encrypted)
    expires = account.oauth_access_token_expires_at
    now = datetime.now(timezone.utc)
    if access and expires and expires > now + timedelta(minutes=3):
        return access

    refresh = _decrypt(account.oauth_refresh_token_encrypted)
    if not refresh:
        account.status = "needs_reauth"
        account.last_error = "OAuth authorization needs to be renewed"
        db.commit()
        raise ConnectedMailError("This connected account needs to be authorized again")
    try:
        token = refresh_access_token(account.provider, refresh)
    except MailOAuthError as exc:
        account.status = "needs_reauth"
        account.last_error = str(exc)[:2000]
        db.commit()
        raise ConnectedMailError(str(exc)) from exc

    access = str(token["access_token"])
    account.oauth_access_token_encrypted = encrypt_secret(access)
    account.oauth_refresh_token_encrypted = encrypt_secret(str(token.get("refresh_token") or refresh))
    account.oauth_access_token_expires_at = token["expires_at"]
    if token.get("scope"):
        account.oauth_scopes_json = list(token["scope"])
    account.status = "active"
    account.last_error = None
    account.last_connected_at = now
    db.commit()
    return access


def config_for_account(account: ConnectedMailAccount, db: Session) -> ConnectedConfig:
    auth_type = (account.auth_type or "password").lower()
    password = ""
    access = ""
    if auth_type == "oauth":
        access = _fresh_oauth(account, db)
    else:
        password = _decrypt(account.credential_encrypted)
        if not password:
            account.status = "needs_reauth"
            db.commit()
            raise ConnectedMailError("This connected account needs its password or app password again")
    return ConnectedConfig(
        account_id=str(account.id),
        address=account.address,
        username=account.address,
        display_name=account.display_name or "",
        provider=account.provider,
        auth_type=auth_type,
        password=password,
        access_token=access,
        imap_host=account.imap_host,
        imap_port=account.imap_port,
        imap_security=account.imap_security,
        smtp_host=account.smtp_host,
        smtp_port=account.smtp_port,
        smtp_security=account.smtp_security,
    )


def _imap(config: ConnectedConfig) -> imaplib.IMAP4:
    _assert_public_host(config.imap_host, config.imap_port)
    client = None
    try:
        if config.imap_security == "ssl":
            client = imaplib.IMAP4_SSL(
                config.imap_host,
                config.imap_port,
                ssl_context=_tls_context(),
                timeout=settings.webmail_transport_timeout_seconds,
            )
        else:
            client = imaplib.IMAP4(
                config.imap_host,
                config.imap_port,
                timeout=settings.webmail_transport_timeout_seconds,
            )
            client.starttls(ssl_context=_tls_context())
        if config.auth_type == "oauth":
            client.authenticate("XOAUTH2", lambda _challenge: xoauth2_bytes(config.username, config.access_token))
        else:
            client.login(config.username, config.password)
        return client
    except (imaplib.IMAP4.error, OSError, ssl.SSLError) as exc:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass
        raise ConnectedMailError("Connected mailbox authentication or IMAP connection failed") from exc


def _smtp(config: ConnectedConfig):
    _assert_public_host(config.smtp_host, config.smtp_port)
    client = None
    try:
        if config.smtp_security == "ssl":
            client = smtplib.SMTP_SSL(
                config.smtp_host,
                config.smtp_port,
                timeout=settings.webmail_transport_timeout_seconds,
                context=_tls_context(),
            )
            client.ehlo()
        else:
            client = smtplib.SMTP(
                config.smtp_host,
                config.smtp_port,
                timeout=settings.webmail_transport_timeout_seconds,
            )
            client.ehlo()
            client.starttls(context=_tls_context())
            client.ehlo()
        if config.auth_type == "oauth":
            code, response = client.docmd("AUTH", "XOAUTH2 " + xoauth2_smtp_value(config.username, config.access_token))
            if code != 235:
                raise smtplib.SMTPAuthenticationError(code, response)
        else:
            client.login(config.username, config.password)
        return client
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        raise ConnectedMailError("Connected mailbox authentication or SMTP connection failed") from exc


def test_account(config: ConnectedConfig) -> None:
    imap = _imap(config)
    try:
        imap.noop()
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    smtp = _smtp(config)
    try:
        smtp.noop()
    finally:
        try:
            smtp.quit()
        except Exception:
            try:
                smtp.close()
            except Exception:
                pass


def folders(config: ConnectedConfig) -> list[dict]:
    client = _imap(config)
    try:
        return [{"name": name, "raw": name} for name in _list_folder_names(client)]
    except ExternalWebmailError as exc:
        raise ConnectedMailError(str(exc)) from exc
    finally:
        try:
            client.logout()
        except Exception:
            pass


def folder_counts(config: ConnectedConfig) -> list[dict]:
    client = _imap(config)
    try:
        rows = []
        for name in _list_folder_names(client):
            status, result = client.status(name, "(MESSAGES UNSEEN)")
            raw = result[0].decode(errors="replace") if status == "OK" and result and result[0] else ""
            import re

            messages_match = re.search(r"MESSAGES\s+(\d+)", raw, re.IGNORECASE)
            unseen_match = re.search(r"UNSEEN\s+(\d+)", raw, re.IGNORECASE)
            rows.append(
                {
                    "name": name,
                    "messages": int(messages_match.group(1)) if messages_match else 0,
                    "unseen": int(unseen_match.group(1)) if unseen_match else 0,
                }
            )
        return rows
    finally:
        try:
            client.logout()
        except Exception:
            pass


def messages(config: ConnectedConfig, folder: str = "INBOX", limit: int = 50, offset: int = 0, query: str = "") -> dict:
    client = _imap(config)
    try:
        _select(client, folder, readonly=True)
        plan = parse_mail_search(query)
        status, data = client.uid("search", None, *plan.criteria)
        if status != "OK":
            raise ConnectedMailError("Unable to search connected mailbox")
        uids = data[0].decode(errors="replace").split() if data and data[0] else []
        uids.reverse()
        # Attachment queries require message MIME inspection. Fetch a wider
        # bounded window, filter it, then apply the requested page offset.
        window = uids[: min(len(uids), max(offset + limit * 4, limit))] if plan.post_filter_required else uids
        rows = []
        for uid in window:
            try:
                raw, meta = _fetch_raw(client, uid, mark_seen=False)
                rows.append(_message_json(uid, raw, meta))
            except ExternalWebmailError:
                continue
        rows = filter_attachment_rows(rows, query)
        page = rows[offset : offset + limit] if plan.post_filter_required else rows[offset : offset + limit]
        return {
            "items": page,
            "total": len(rows) if plan.post_filter_required else len(uids),
            "folder": folder,
            "limit": limit,
            "offset": offset,
            "query": query.strip(),
        }
    finally:
        try:
            client.logout()
        except Exception:
            pass


def message(config: ConnectedConfig, uid: str, folder: str = "INBOX") -> dict:
    client = _imap(config)
    try:
        _select(client, folder, readonly=False)
        raw, meta = _fetch_raw(client, uid, mark_seen=True)
        return _message_json(uid, raw, meta, include_body=True)
    finally:
        try:
            client.logout()
        except Exception:
            pass


def set_flags(config: ConnectedConfig, uid: str, folder: str, *, seen: bool | None = None, flagged: bool | None = None, answered: bool | None = None) -> dict:
    client = _imap(config)
    try:
        _select(client, folder, readonly=False)
        for flag, value in (("\\Seen", seen), ("\\Flagged", flagged), ("\\Answered", answered)):
            if value is None:
                continue
            operation = "+FLAGS.SILENT" if value else "-FLAGS.SILENT"
            status, _ = client.uid("store", uid, operation, f"({flag})")
            if status != "OK":
                raise ConnectedMailError("Unable to update message flags")
        raw, meta = _fetch_raw(client, uid, mark_seen=False)
        return _message_json(uid, raw, meta)
    finally:
        try:
            client.logout()
        except Exception:
            pass


def move_message(config: ConnectedConfig, uid: str, folder: str, destination: str) -> dict:
    if folder.lower() == destination.lower():
        raise ConnectedMailError("Source and destination folders are the same")
    client = _imap(config)
    try:
        _select(client, folder, readonly=False)
        _ensure_folder(client, destination)
        status, _ = client.uid("copy", uid, destination)
        if status != "OK":
            raise ConnectedMailError("Unable to copy message")
        status, _ = client.uid("store", uid, "+FLAGS.SILENT", "(\\Deleted)")
        if status != "OK":
            raise ConnectedMailError("Unable to remove source message")
        client.expunge()
        return {"moved": True, "uid": uid, "from": folder, "to": destination}
    finally:
        try:
            client.logout()
        except Exception:
            pass


def delete_message(config: ConnectedConfig, uid: str, folder: str) -> dict:
    client = _imap(config)
    try:
        names = _list_folder_names(client)
        trash = _folder_for(names, "trash") or "Trash"
    finally:
        try:
            client.logout()
        except Exception:
            pass
    if folder.lower() != trash.lower():
        return move_message(config, uid, folder, trash)
    client = _imap(config)
    try:
        _select(client, folder, readonly=False)
        status, _ = client.uid("store", uid, "+FLAGS.SILENT", "(\\Deleted)")
        if status != "OK":
            raise ConnectedMailError("Unable to delete message")
        client.expunge()
        return {"deleted": True, "uid": uid, "folder": folder}
    finally:
        try:
            client.logout()
        except Exception:
            pass


def attachment(config: ConnectedConfig, uid: str, folder: str, index: int) -> tuple[str, str, bytes]:
    from email import policy
    from email.parser import BytesParser

    client = _imap(config)
    try:
        _select(client, folder, readonly=True)
        raw, _ = _fetch_raw(client, uid, mark_seen=False)
        parsed = BytesParser(policy=policy.default).parsebytes(raw)
        candidates = [part for part in parsed.walk() if part.get_filename() or part.get_content_disposition() == "attachment"]
        if index < 0 or index >= len(candidates):
            raise ConnectedMailError("Attachment was not found")
        part = candidates[index]
        return (
            part.get_filename() or f"attachment-{index + 1}",
            part.get_content_type(),
            part.get_payload(decode=True) or b"",
        )
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _sender(config: ConnectedConfig) -> str:
    return formataddr((config.display_name, config.address)) if config.display_name else config.address


def send_message(
    config: ConnectedConfig,
    *,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    subject: str,
    body_text: str,
    body_html: str = "",
    attachments: list[dict] | None = None,
    in_reply_to: str = "",
    references: str = "",
) -> dict:
    msg = EmailMessage()
    msg["From"] = _sender(config)
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = make_msgid(domain=config.address.split("@", 1)[-1])
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to[:998]
    if references:
        msg["References"] = references[:4000]
    msg.set_content(body_text or "")
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    for payload, maintype, subtype, filename in _attachment_rows(attachments):
        msg.add_attachment(payload, maintype=maintype, subtype=subtype, filename=filename)

    smtp = _smtp(config)
    try:
        smtp.send_message(msg, from_addr=config.address, to_addrs=[*to, *cc, *bcc])
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        raise ConnectedMailError("Unable to send connected-account message") from exc
    finally:
        try:
            smtp.quit()
        except Exception:
            try:
                smtp.close()
            except Exception:
                pass

    try:
        client = _imap(config)
        try:
            names = _list_folder_names(client)
            sent = _folder_for(names, "sent") or "Sent"
            _ensure_folder(client, sent)
            client.append(sent, "\\Seen", imaplib.Time2Internaldate(datetime.now().timestamp()), msg.as_bytes())
        finally:
            client.logout()
    except Exception:
        pass
    return {"sent": True, "message_id": msg["Message-ID"]}


def save_draft(config: ConnectedConfig, *, to: list[str], cc: list[str], subject: str, body_text: str) -> dict:
    msg = EmailMessage()
    msg["From"] = _sender(config)
    if to:
        msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = make_msgid(domain=config.address.split("@", 1)[-1])
    msg.set_content(body_text)
    client = _imap(config)
    try:
        names = _list_folder_names(client)
        drafts = _folder_for(names, "drafts") or "Drafts"
        _ensure_folder(client, drafts)
        status, _ = client.append(drafts, "\\Draft", imaplib.Time2Internaldate(datetime.now().timestamp()), msg.as_bytes())
        if status != "OK":
            raise ConnectedMailError("Unable to save connected-account draft")
        return {"saved": True, "message_id": msg["Message-ID"], "folder": drafts}
    finally:
        try:
            client.logout()
        except Exception:
            pass
