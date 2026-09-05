import socket
from ipaddress import ip_address

import dns.resolver


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
    ptr_ok = False
    fcrdns_ok = False
    ptr_name = None
    try:
        ptr_name = socket.gethostbyaddr(mail_ip)[0].rstrip(".").lower()
        ptr_ok = ptr_name == expected_hostname.rstrip(".").lower()
        if ptr_name:
            addresses = {x[4][0] for x in socket.getaddrinfo(ptr_name, 25, type=socket.SOCK_STREAM)}
            fcrdns_ok = mail_ip in addresses
    except OSError:
        pass

    hits: list[str] = []
    try:
        reversed_ip = reverse_ip(mail_ip)
        resolver = dns.resolver.Resolver(configure=True)
        resolver.lifetime = 3.0
        for zone in DNSBLS:
            try:
                resolver.resolve(f"{reversed_ip}.{zone}", "A")
                hits.append(zone)
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.resolver.LifetimeTimeout):
                continue
    except ValueError:
        pass

    score = 100
    if not ptr_ok:
        score -= 25
    if not fcrdns_ok:
        score -= 20
    score -= min(45, len(hits) * 20)
    return {"ptr_ok": ptr_ok, "fcrdns_ok": fcrdns_ok, "ptr_name": ptr_name, "dnsbl_hits": hits, "score": max(0, score)}
