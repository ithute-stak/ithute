from __future__ import annotations

import email
import imaplib
import smtplib
import ssl
import time
import uuid
from email.message import EmailMessage

USER = "phase6@phase6.test"
PASSWORD = "Phase6Strong!Pass"
SMTP_HOST = "postfix"
DOVECOT_HOST = "dovecot"


def send_with_retry(message: EmailMessage, tls: ssl.SSLContext) -> None:
    deadline = time.time() + 30
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            with smtplib.SMTP(SMTP_HOST, 587, timeout=15) as smtp:
                smtp.ehlo()
                assert smtp.has_extn("starttls"), "submission service does not advertise STARTTLS"
                smtp.starttls(context=tls)
                smtp.ehlo()
                smtp.login(USER, PASSWORD)
                refused = smtp.send_message(message)
                assert not refused, f"SMTP refused recipients: {refused}"
                return
        except smtplib.SMTPResponseException as exc:
            last_error = exc
            # A freshly-started Postfix can briefly return 454/451 while the
            # Rspamd milter worker/Docker DNS becomes reachable. Treat only
            # transient 4xx responses as retryable; permanent failures still
            # fail the smoke immediately.
            if not 400 <= exc.smtp_code < 500:
                raise
        except (ConnectionError, OSError, smtplib.SMTPServerDisconnected) as exc:
            last_error = exc
        time.sleep(1)

    raise RuntimeError(f"SMTP submission was not ready before timeout: {last_error}")


def main() -> None:
    marker = f"phase6-{uuid.uuid4()}"
    message = EmailMessage()
    message["From"] = USER
    message["To"] = USER
    message["Subject"] = marker
    message.set_content(f"Mailbox DNS Phase 6 integration message {marker}\n")

    tls = ssl.create_default_context()
    tls.check_hostname = False
    tls.verify_mode = ssl.CERT_NONE

    send_with_retry(message, tls)

    deadline = time.time() + 30
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with imaplib.IMAP4_SSL(DOVECOT_HOST, 993, ssl_context=tls, timeout=10) as client:
                typ, _ = client.login(USER, PASSWORD)
                assert typ == "OK"
                typ, _ = client.select("INBOX")
                assert typ == "OK"
                typ, data = client.search(None, "SUBJECT", f'"{marker}"')
                assert typ == "OK"
                ids = data[0].split() if data and data[0] else []
                if ids:
                    typ, fetched = client.fetch(ids[-1], "(RFC822)")
                    assert typ == "OK"
                    raw = next(item[1] for item in fetched if isinstance(item, tuple))
                    parsed = email.message_from_bytes(raw)
                    assert parsed.get("Subject") == marker
                    print("Phase 6 authenticated SMTP -> Rspamd -> LMTP -> IMAP smoke PASSED.")
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(1)

    raise RuntimeError(f"message was not visible in IMAP before timeout: {last_error}")


if __name__ == "__main__":
    main()
