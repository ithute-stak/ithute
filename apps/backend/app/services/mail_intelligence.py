from __future__ import annotations

import re
from collections import Counter
from email.utils import getaddresses
from typing import Any
from urllib.parse import urlparse


URL_RE = re.compile(r"https?://[^\s<>()\[\]\"']+", re.IGNORECASE)
MONEY_RE = re.compile(
    r"(?<!\w)(?:M|LSL|R|ZAR|USD|US\$|\$|EUR|€|GBP|£)\s?\d[\d,]*(?:\.\d{1,2})?",
    re.IGNORECASE,
)
DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b"
)
INVOICE_RE = re.compile(
    r"\b(?:invoice|inv|quotation|quote|po|purchase\s+order|reference|ref)\s*[#:\-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})",
    re.IGNORECASE,
)

URGENCY_TERMS = {
    "urgent": 12,
    "immediately": 12,
    "asap": 12,
    "today": 7,
    "right away": 10,
    "within the hour": 12,
    "final notice": 9,
    "do not delay": 12,
}
CREDENTIAL_TERMS = {
    "password": 10,
    "verify your account": 18,
    "login": 7,
    "sign in": 7,
    "credentials": 15,
    "one-time password": 18,
    "otp": 15,
    "2fa": 12,
}
PAYMENT_TERMS = {
    "bank account": 14,
    "bank details": 15,
    "change account": 18,
    "new account": 12,
    "payment": 8,
    "transfer": 10,
    "wire": 12,
    "beneficiary": 12,
    "invoice": 5,
    "pay": 6,
}
THREAT_TERMS = {
    "account will be suspended": 18,
    "account suspended": 15,
    "legal action": 10,
    "penalty": 8,
    "locked": 8,
}
REQUEST_TERMS = (
    "please",
    "can you",
    "could you",
    "would you",
    "kindly",
    "request",
    "send me",
    "provide",
    "confirm",
    "let me know",
)

RISKY_ATTACHMENT_EXTENSIONS = {
    ".exe", ".scr", ".bat", ".cmd", ".com", ".js", ".jse", ".vbs", ".vbe",
    ".ps1", ".hta", ".msi", ".dll", ".lnk", ".iso", ".img", ".jar",
}

INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "payment": ("payment", "paid", "pay ", "bank details", "transfer", "invoice"),
    "quotation": ("quotation", "quote", "pricing", "price", "estimate", "proposal"),
    "support": ("support", "help", "issue", "problem", "error", "not working", "failed"),
    "meeting": ("meeting", "calendar", "schedule", "appointment", "call", "teams", "zoom"),
    "sales": ("buy", "purchase", "order", "interested", "package", "subscription", "demo"),
    "complaint": ("complaint", "unhappy", "disappointed", "refund", "poor service"),
    "legal": ("legal", "court", "lawyer", "attorney", "notice", "demand", "affidavit"),
    "hr": ("leave", "salary", "employee", "employment", "vacancy", "interview", "cv"),
    "security": ("password", "phishing", "breach", "suspicious", "verify your account", "otp"),
}


def _lower(value: Any) -> str:
    return str(value or "").lower()


def _addresses(value: Any) -> list[str]:
    return [addr.lower() for _, addr in getaddresses([str(value or "")]) if addr]


def _domain(address: str) -> str:
    return address.rsplit("@", 1)[-1].lower() if "@" in address else ""


def _registrable_hint(host: str) -> str:
    host = (host or "").lower().strip(".")
    labels = [label for label in host.split(".") if label]
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def _term_score(text: str, terms: dict[str, int]) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    for term, weight in terms.items():
        if term in text:
            score += weight
            signals.append(term)
    return score, signals


def _extract_entities(message: dict[str, Any]) -> dict[str, list[str]]:
    body = str(message.get("body_text") or "")
    subject = str(message.get("subject") or "")
    combined = f"{subject}\n{body}"
    urls = [match.rstrip(".,;:!?") for match in URL_RE.findall(combined)]
    emails = sorted(set(_addresses(message.get("from")) + _addresses(message.get("to")) + _addresses(message.get("cc")) + _addresses(message.get("reply_to"))))
    money = list(dict.fromkeys(MONEY_RE.findall(combined)))[:20]
    dates = list(dict.fromkeys(DATE_RE.findall(combined)))[:20]
    references = [match.group(1) for match in INVOICE_RE.finditer(combined)]
    deadline_terms = [
        term for term in ("today", "tomorrow", "end of day", "eod", "this week", "before close of business")
        if term in combined.lower()
    ]
    return {
        "emails": emails[:50],
        "urls": urls[:50],
        "money": money,
        "dates": dates,
        "references": list(dict.fromkeys(references))[:20],
        "deadline_terms": deadline_terms,
    }


def _intent(text: str) -> dict[str, Any]:
    scores: Counter[str] = Counter()
    evidence: dict[str, list[str]] = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        found = [keyword for keyword in keywords if keyword in text]
        if found:
            scores[intent] = len(found)
            evidence[intent] = found
    if not scores:
        return {"label": "general", "confidence": 0.45, "alternatives": [], "evidence": []}
    ranked = scores.most_common(3)
    total = sum(scores.values())
    winner, winner_score = ranked[0]
    confidence = min(0.95, 0.55 + 0.08 * winner_score + 0.05 * (winner_score / max(1, total)))
    return {
        "label": winner,
        "confidence": round(confidence, 3),
        "alternatives": [{"label": name, "score": score} for name, score in ranked[1:]],
        "evidence": evidence.get(winner, []),
    }


def analyze_mail_message(message: dict[str, Any], *, mailbox_address: str = "") -> dict[str, Any]:
    subject = str(message.get("subject") or "")
    body = str(message.get("body_text") or "")
    text = f"{subject}\n{body}".lower()
    sender_addresses = _addresses(message.get("from"))
    sender = sender_addresses[0] if sender_addresses else ""
    sender_domain = _domain(sender)
    reply_addresses = _addresses(message.get("reply_to"))
    reply_domain = _domain(reply_addresses[0]) if reply_addresses else sender_domain

    risk_score = 0
    bec_score = 0
    risk_signals: list[dict[str, Any]] = []

    urgency_score, urgency_hits = _term_score(text, URGENCY_TERMS)
    credential_score, credential_hits = _term_score(text, CREDENTIAL_TERMS)
    payment_score, payment_hits = _term_score(text, PAYMENT_TERMS)
    threat_score, threat_hits = _term_score(text, THREAT_TERMS)

    risk_score += urgency_score + credential_score + threat_score
    bec_score += urgency_score // 2 + payment_score

    if urgency_hits:
        risk_signals.append({"signal": "urgency_language", "weight": urgency_score, "evidence": urgency_hits})
    if credential_hits:
        risk_signals.append({"signal": "credential_request", "weight": credential_score, "evidence": credential_hits})
    if payment_hits:
        risk_signals.append({"signal": "payment_language", "weight": payment_score, "evidence": payment_hits})
    if threat_hits:
        risk_signals.append({"signal": "threat_or_pressure", "weight": threat_score, "evidence": threat_hits})

    if reply_domain and sender_domain and _registrable_hint(reply_domain) != _registrable_hint(sender_domain):
        risk_score += 22
        bec_score += 24
        risk_signals.append({
            "signal": "reply_to_domain_mismatch",
            "weight": 22,
            "evidence": [f"from={sender_domain}", f"reply_to={reply_domain}"],
        })

    urls = URL_RE.findall(body)
    sender_root = _registrable_hint(sender_domain)
    external_link_hosts = []
    for raw_url in urls[:50]:
        try:
            host = (urlparse(raw_url).hostname or "").lower()
        except ValueError:
            host = ""
        if host and sender_root and _registrable_hint(host) != sender_root:
            external_link_hosts.append(host)
    if external_link_hosts:
        link_weight = min(18, 6 + len(set(external_link_hosts)) * 3)
        risk_score += link_weight
        risk_signals.append({
            "signal": "external_link_domain",
            "weight": link_weight,
            "evidence": sorted(set(external_link_hosts))[:8],
        })

    risky_attachments = []
    attachments = message.get("attachments") if isinstance(message.get("attachments"), list) else []
    for attachment in attachments:
        filename = _lower(attachment.get("filename"))
        for extension in RISKY_ATTACHMENT_EXTENSIONS:
            if filename.endswith(extension):
                risky_attachments.append(filename)
                break
    if risky_attachments:
        weight = min(30, 18 + len(risky_attachments) * 4)
        risk_score += weight
        risk_signals.append({
            "signal": "risky_attachment_type",
            "weight": weight,
            "evidence": risky_attachments[:8],
        })

    mailbox_domain = _domain(mailbox_address.lower())
    if mailbox_domain and sender_domain == mailbox_domain:
        # Internal mail is not automatically trusted, but same-domain identity
        # reduces only the generic phishing prior, never explicit risky signals.
        risk_score = max(0, risk_score - 5)

    phishing_probability = min(0.99, max(0.01, risk_score / 100.0))
    bec_probability = min(0.99, max(0.01, bec_score / 100.0))

    intent = _intent(text)
    entities = _extract_entities(message)

    question_signal = "?" in body
    request_hits = [term for term in REQUEST_TERMS if term in text]
    reply_needed = bool(question_signal or request_hits or intent["label"] in {"quotation", "support", "sales", "payment", "meeting", "complaint"})
    priority_score = min(
        100,
        int(round(
            phishing_probability * 45
            + bec_probability * 25
            + (18 if entities["deadline_terms"] or entities["dates"] else 0)
            + (12 if reply_needed else 0)
        )),
    )
    if priority_score >= 75:
        priority = "critical"
    elif priority_score >= 50:
        priority = "high"
    elif priority_score >= 25:
        priority = "normal"
    else:
        priority = "low"

    security_action = "allow"
    if phishing_probability >= 0.8 or bec_probability >= 0.8:
        security_action = "warn_and_verify"
    elif phishing_probability >= 0.55 or bec_probability >= 0.55:
        security_action = "review"

    summary_bits = []
    if intent["label"] != "general":
        summary_bits.append(f"Likely {intent['label']} message")
    if entities["money"]:
        summary_bits.append(f"mentions {entities['money'][0]}")
    if entities["deadline_terms"]:
        summary_bits.append(f"deadline signal: {entities['deadline_terms'][0]}")
    if reply_needed:
        summary_bits.append("likely needs a reply")

    return {
        "model": "ithute-mail-intelligence-v1",
        "security": {
            "phishing_probability": round(phishing_probability, 3),
            "bec_probability": round(bec_probability, 3),
            "recommended_action": security_action,
            "signals": sorted(risk_signals, key=lambda item: int(item["weight"]), reverse=True),
        },
        "business": {
            "intent": intent,
            "priority": priority,
            "priority_score": priority_score,
            "reply_needed": reply_needed,
            "reply_evidence": {
                "question_mark": question_signal,
                "request_terms": request_hits[:10],
            },
            "entities": entities,
            "summary": ". ".join(summary_bits) + ("." if summary_bits else "General email message."),
        },
        "governance": {
            "automatic_blocking": False,
            "training_use": False,
            "explainable": True,
        },
    }
