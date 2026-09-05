#!/usr/bin/env python3
import base64
import time
import uuid

import httpx

BASE = "http://backend:8000/api/v1"
ADDRESS = "phase6@phase6.test"
PASSWORD = "Phase6Strong!Pass"


def find(client: httpx.Client, folder: str, query: str):
    for _ in range(15):
        response = client.get("/webmail/messages", params={"folder": folder, "limit": 75, "q": query})
        response.raise_for_status()
        rows = response.json()["items"]
        if rows:
            return rows[0]
        time.sleep(1)
    return None


def main() -> None:
    marker = uuid.uuid4().hex[:10]
    subject = f"Phase 9 actions {marker}"
    draft_subject = f"Phase 9 draft {marker}"
    attachment_bytes = f"Mailbox DNS attachment {marker}\n".encode()

    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        login = client.post("/webmail/session", json={"address": ADDRESS, "password": PASSWORD})
        login.raise_for_status()

        draft = client.post(
            "/webmail/drafts",
            json={"to": [ADDRESS], "cc": [], "subject": draft_subject, "body_text": "Saved by the Phase 9 draft smoke."},
        )
        draft.raise_for_status()
        assert draft.json()["saved"] is True
        draft_row = find(client, "Drafts", draft_subject)
        assert draft_row, "saved draft was not searchable in Drafts"

        sent = client.post(
            "/webmail/send",
            json={
                "to": [ADDRESS],
                "cc": [],
                "bcc": [],
                "subject": subject,
                "body_text": f"Searchable body marker {marker}",
                "attachments": [
                    {
                        "filename": "phase9-smoke.txt",
                        "content_type": "text/plain",
                        "content_b64": base64.b64encode(attachment_bytes).decode(),
                    }
                ],
                "in_reply_to": "",
                "references": "",
            },
        )
        sent.raise_for_status()
        assert sent.json()["sent"] is True
        assert sent.json()["attachments"] == 1

        row = find(client, "INBOX", marker)
        assert row, "server-side IMAP TEXT search did not find delivered message"
        uid = row["uid"]

        opened = client.get(f"/webmail/messages/{uid}", params={"folder": "INBOX"})
        opened.raise_for_status()
        full = opened.json()
        assert full["subject"] == subject
        assert full["attachments"][0]["filename"] == "phase9-smoke.txt"

        download = client.get(f"/webmail/messages/{uid}/attachments/0", params={"folder": "INBOX"})
        download.raise_for_status()
        assert download.content == attachment_bytes

        flag = client.patch(f"/webmail/messages/{uid}/flags", params={"folder": "INBOX"}, json={"flagged": True})
        flag.raise_for_status()
        assert flag.json()["flagged"] is True

        unread = client.patch(f"/webmail/messages/{uid}/flags", params={"folder": "INBOX"}, json={"seen": False})
        unread.raise_for_status()
        assert unread.json()["seen"] is False

        moved = client.post(f"/webmail/messages/{uid}/move", params={"folder": "INBOX"}, json={"destination": "Archive"})
        moved.raise_for_status()
        archived = find(client, "Archive", marker)
        assert archived, "moved message was not found in Archive"

        removed = client.delete(f"/webmail/messages/{archived['uid']}", params={"folder": "Archive"})
        removed.raise_for_status()
        trashed = find(client, "Trash", marker)
        assert trashed, "deleted message was not moved to Trash"
        purged = client.delete(f"/webmail/messages/{trashed['uid']}", params={"folder": "Trash"})
        purged.raise_for_status()
        assert purged.json()["deleted"] is True

        logout = client.delete("/webmail/session")
        assert logout.status_code == 204

    print("Phase 9 webmail actions smoke PASSED.")
    print("Verified draft append, server-side search, attachments, flag changes, archive move, Trash lifecycle and permanent delete.")


if __name__ == "__main__":
    main()
