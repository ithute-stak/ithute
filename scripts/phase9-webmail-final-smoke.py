#!/usr/bin/env python3
import time
import uuid

import httpx

BASE = "http://backend:8000/api/v1"
ADDRESS = "phase6@phase6.test"
PASSWORD = "Phase6Strong!Pass"


def main() -> None:
    token = uuid.uuid4().hex[:10]
    subject = f"Phase 9 final rich {token}"
    with httpx.Client(base_url=BASE, timeout=25.0) as client:
        r = client.post("/webmail/session", json={"address": ADDRESS, "password": PASSWORD})
        r.raise_for_status()

        sig = client.put("/webmail/signature", json={"html": '<p>Regards,<br><strong>Phase 9</strong><script>alert(1)</script></p>'})
        sig.raise_for_status()
        safe = sig.json()["html"]
        assert "<script" not in safe.lower(), safe
        assert "Phase 9" in safe
        read_sig = client.get("/webmail/signature"); read_sig.raise_for_status(); assert read_sig.json()["html"] == safe

        c = client.post("/webmail/contacts", json={"email": f"contact-{token}@example.org", "name": "Phase Nine Contact"})
        c.raise_for_status()
        found = client.get("/webmail/contacts", params={"q": token}); found.raise_for_status()
        assert any(row["email"] == f"contact-{token}@example.org" for row in found.json()["items"])

        counts = client.get("/webmail/folder-counts"); counts.raise_for_status()
        inbox = next((row for row in counts.json()["items"] if row["name"].upper() == "INBOX"), None)
        assert inbox is not None and inbox["messages"] >= 0 and inbox["unseen"] >= 0

        sent = client.post("/webmail/send-rich", json={
            "to": [ADDRESS], "cc": [], "bcc": [], "subject": subject,
            "body_text": "Phase 9 final rich-message acceptance body.",
            "body_html": '<p><strong>Phase 9 final rich-message acceptance body.</strong></p><img src=x onerror=alert(1)>',
            "signature_html": safe,
        })
        sent.raise_for_status(); assert sent.json()["sent"] is True and sent.json()["html"] is True

        found_message = None
        for _ in range(20):
            listing = client.get("/webmail/messages", params={"folder": "INBOX", "q": subject, "limit": 20})
            listing.raise_for_status()
            found_message = next((row for row in listing.json()["items"] if row["subject"] == subject), None)
            if found_message:
                break
            time.sleep(1)
        assert found_message, subject

        uid = found_message["uid"]
        junk = client.post(f"/webmail/messages/{uid}/move", params={"folder": "INBOX"}, json={"destination": "Junk"})
        junk.raise_for_status(); assert junk.json()["moved"] is True

        junk_listing = client.get("/webmail/messages", params={"folder": "Junk", "q": subject, "limit": 20})
        junk_listing.raise_for_status()
        moved = next((row for row in junk_listing.json()["items"] if row["subject"] == subject), None)
        assert moved, "message not visible in Junk"

        restore = client.post(f"/webmail/messages/{moved['uid']}/move", params={"folder": "Junk"}, json={"destination": "INBOX"})
        restore.raise_for_status(); assert restore.json()["moved"] is True

        client.delete("/webmail/session")

    print("Phase 9 FINAL webmail acceptance smoke PASSED.")
    print("Verified sanitized HTML/signatures, contacts, folder counts, rich SMTP/IMAP delivery and Junk/restore lifecycle.")


if __name__ == "__main__":
    main()
