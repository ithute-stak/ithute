from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime


_TOKEN_RE = re.compile(r'''(?:[^\s"]|"[^"]*")+''')
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class MailSearchPlan:
    criteria: list[str] = field(default_factory=list)
    free_text: list[str] = field(default_factory=list)
    require_attachment: bool = False
    exclude_attachment: bool = False

    @property
    def post_filter_required(self) -> bool:
        return self.require_attachment or self.exclude_attachment


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def _quoted(value: str) -> str:
    safe = value.replace("\\", "\\\\").replace('"', '\\"')[:500]
    return f'"{safe}"'


def _imap_date(value: str) -> str | None:
    if not _DATE_RE.fullmatch(value):
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None
    return parsed.strftime("%d-%b-%Y")


def parse_mail_search(query: str) -> MailSearchPlan:
    plan = MailSearchPlan()
    for raw in _TOKEN_RE.findall((query or "").strip()[:1000]):
        token = raw.strip()
        if not token:
            continue
        lower = token.lower()

        def value(prefix: str) -> str:
            return _unquote(token[len(prefix):]).strip()

        if lower.startswith("from:") and value("from:"):
            plan.criteria.extend(["FROM", _quoted(value("from:"))])
        elif lower.startswith("to:") and value("to:"):
            plan.criteria.extend(["TO", _quoted(value("to:"))])
        elif lower.startswith("cc:") and value("cc:"):
            plan.criteria.extend(["CC", _quoted(value("cc:"))])
        elif lower.startswith("subject:") and value("subject:"):
            plan.criteria.extend(["SUBJECT", _quoted(value("subject:"))])
        elif lower == "is:unread":
            plan.criteria.append("UNSEEN")
        elif lower == "is:read":
            plan.criteria.append("SEEN")
        elif lower in {"is:starred", "is:flagged"}:
            plan.criteria.append("FLAGGED")
        elif lower in {"-is:starred", "-is:flagged"}:
            plan.criteria.append("UNFLAGGED")
        elif lower == "has:attachment":
            plan.require_attachment = True
        elif lower == "-has:attachment":
            plan.exclude_attachment = True
        elif lower.startswith("after:"):
            date = _imap_date(value("after:"))
            if date:
                plan.criteria.extend(["SINCE", date])
            else:
                plan.free_text.append(token)
        elif lower.startswith("before:"):
            date = _imap_date(value("before:"))
            if date:
                plan.criteria.extend(["BEFORE", date])
            else:
                plan.free_text.append(token)
        else:
            clean = _unquote(token)
            if clean:
                plan.free_text.append(clean)

    for text in plan.free_text:
        plan.criteria.extend(["TEXT", _quoted(text)])
    if not plan.criteria:
        plan.criteria.append("ALL")
    return plan


def search_args(query: str) -> tuple[str, ...]:
    return tuple(parse_mail_search(query).criteria)


def filter_attachment_rows(rows: list[dict], query: str) -> list[dict]:
    plan = parse_mail_search(query)
    if not plan.post_filter_required:
        return rows
    result = []
    for row in rows:
        has_attachment = bool(row.get("attachments"))
        if plan.require_attachment and not has_attachment:
            continue
        if plan.exclude_attachment and has_attachment:
            continue
        result.append(row)
    return result


def message_timestamp(value: str) -> float:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.astimezone()
        return dt.timestamp()
    except Exception:
        return 0.0
