from __future__ import annotations

import re


_REPLY_PREFIX_RE = re.compile(r"^\s*((re|fw|fwd)\s*:\s*)+", re.IGNORECASE)
_MESSAGE_ID_RE = re.compile(r"<[^>]+>")


def normalized_subject(subject: str) -> str:
    value = _REPLY_PREFIX_RE.sub("", (subject or "").strip()).strip().lower()
    return " ".join(value.split())[:500]


def thread_key(row: dict) -> str:
    references = str(row.get("references") or "")
    ids = _MESSAGE_ID_RE.findall(references)
    if ids:
        return "ref:" + ids[0].lower()
    in_reply_to = str(row.get("in_reply_to") or "").strip()
    match = _MESSAGE_ID_RE.search(in_reply_to)
    if match:
        return "ref:" + match.group(0).lower()
    message_id = str(row.get("message_id") or "").strip()
    subject = normalized_subject(str(row.get("subject") or ""))
    if subject:
        return "subject:" + subject
    if message_id:
        return "id:" + message_id.lower()
    return "uid:" + str(row.get("uid") or "")


def annotate_thread(row: dict) -> dict:
    return {**row, "thread_key": thread_key(row)}
