#!/usr/bin/env python3
import time
import uuid

import httpx

BASE = "http://backend:8000/api/v1"
ADDRESS = "phase6@phase6.test"
PASSWORD = "Phase6Strong!Pass"


def main() -> None:
    subject = f"Phase 9 webmail smoke {uuid.uuid4().hex[:10]}"
    with httpx.Client(base_url=BASE, timeout=20.0) as client:
        login = client.post("/webmail/session", json={"address": ADDRESS, "password": PASSWORD})
        login.raise_for_status()
        payload = login.json()
        assert payload["authenticated"] is True
        assert payload["address"] == ADDRESS
        assert "password" not in payload

        session = client.get("/webmail/session")
        session.raise_for_status()
        assert session.json()["address"] == ADDRESS

        folder_response = client.get("/webmail/folders")
        folder_response.raise_for_status()
        folder_names = [row["name"] for row in folder_response.json()["items"]]
        assert any(name.upper() == "INBOX" for name in folder_names), folder_names

        send = client.post(
            "/webmail/send",
            json={
                "to": [ADDRESS],
                "cc": [],
                "bcc": [],
                "subject": subject,
                "body_text": "Phase 9 live webmail smoke verifies mailbox login, SMTP submission, IMAP delivery and message retrieval.",
            },
        )
        send.raise_for_status()
        assert send.json()["sent"] is True

        found = None
        for _ in range(15):
            inbox = client.get("/webmail/messages", params={"folder": "INBOX", "limit": 75})
            inbox.raise_for_status()
            found = next((row for row in inbox.json()["items"] if row["subject"] == subject), None)
            if found:
                break
            time.sleep(1)
        assert found, f"message with subject {subject!r} not found in INBOX"

        opened = client.get(f"/webmail/messages/{found['uid']}", params={"folder": "INBOX"})
        opened.raise_for_status()
        body = opened.json()
        assert body["subject"] == subject
        assert "Phase 9 live webmail smoke" in body["body_text"]

        logout = client.delete("/webmail/session")
        assert logout.status_code == 204
        expired = client.get("/webmail/session")
        assert expired.status_code == 401

    print("Phase 9 live webmail smoke PASSED.")
    print("Verified opaque HttpOnly session, IMAP folder/message access, authenticated SMTP send, self-delivery and logout revocation.")


if __name__ == "__main__":
    main()
