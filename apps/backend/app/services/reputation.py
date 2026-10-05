from ipaddress import ip_address

from app.services.engine_router import execute_dns


DNSBLS = (
    "zen.spamhaus.org",
    "bl.spamcop.net",
    "b.barracudacentral.org",
)


def reverse_ip(value: str) -> str:
    parsed = ip_address(value)
    if parsed.version != 4:
        raise ValueError("DNSBL checks currently require an IPv4 mail address")
    return ".".join(reversed(value.split(".")))


def reputation_check(mail_ip: str, expected_hostname: str) -> dict:
    expected = expected_hostname.rstrip(".").lower()
    reversed_ip = None
    try:
        reversed_ip = reverse_ip(mail_ip)
    except ValueError:
        pass

    queries = [{"id": "ptr", "name": mail_ip, "type": "PTR", "timeout_ms": 3000}]
    if reversed_ip:
        queries.extend(
            {
                "id": f"dnsbl:{zone}",
                "name": f"{reversed_ip}.{zone}",
                "type": "A",
                "timeout_ms": 3000,
            }
            for zone in DNSBLS
        )
    execution = execute_dns(queries, concurrency=8)
    rows = execution.value.get("results", []) if isinstance(execution.value, dict) else []
    by_id = {
        str(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and row.get("id")
    }

    ptr_values = list((by_id.get("ptr") or {}).get("values") or [])
    ptr_name = str(ptr_values[0]).rstrip(".").lower() if ptr_values else None
    ptr_ok = bool(ptr_name and ptr_name == expected)

    fcrdns_ok = False
    if ptr_name:
        forward = execute_dns(
            [
                {"id": "a", "name": ptr_name, "type": "A", "timeout_ms": 3000},
                {"id": "aaaa", "name": ptr_name, "type": "AAAA", "timeout_ms": 3000},
            ],
            concurrency=2,
        )
        forward_rows = forward.value.get("results", []) if isinstance(forward.value, dict) else []
        addresses = {
            str(value)
            for row in forward_rows
            if isinstance(row, dict)
            for value in (row.get("values") or [])
        }
        fcrdns_ok = mail_ip in addresses

    hits = [
        zone
        for zone in DNSBLS
        if list((by_id.get(f"dnsbl:{zone}") or {}).get("values") or [])
    ]

    score = 100
    if not ptr_ok:
        score -= 25
    if not fcrdns_ok:
        score -= 20
    score -= min(45, len(hits) * 20)
    return {
        "ptr_ok": ptr_ok,
        "fcrdns_ok": fcrdns_ok,
        "ptr_name": ptr_name,
        "dnsbl_hits": hits,
        "score": max(0, score),
    }
