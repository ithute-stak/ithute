from __future__ import annotations

import hashlib
import ipaddress
from collections.abc import Iterable


def parse_pool(value: str, subnet_prefix: int) -> ipaddress.IPv4Network:
    try:
        pool = ipaddress.ip_network(value, strict=True)
    except ValueError as exc:
        raise RuntimeError("ITHUTE_HOSTING_NETWORK_POOL must be a canonical IPv4 CIDR") from exc
    if not isinstance(pool, ipaddress.IPv4Network) or not pool.is_private:
        raise RuntimeError("ITHUTE_HOSTING_NETWORK_POOL must be a private IPv4 network")
    if subnet_prefix < pool.prefixlen or subnet_prefix > 28:
        raise RuntimeError("ITHUTE_HOSTING_NETWORK_PREFIX must be between the pool prefix and /28")
    return pool


def choose_project_subnet(
    pool: ipaddress.IPv4Network,
    subnet_prefix: int,
    project_id: str,
    used: Iterable[ipaddress.IPv4Network],
) -> ipaddress.IPv4Network:
    if not project_id:
        raise RuntimeError("Project id is required for network allocation")

    used_networks = tuple(used)
    total = 1 << (subnet_prefix - pool.prefixlen)
    block_size = 1 << (32 - subnet_prefix)
    start = int.from_bytes(hashlib.sha256(project_id.encode("utf-8")).digest()[:8], "big") % total
    pool_start = int(pool.network_address)

    for offset in range(total):
        index = (start + offset) % total
        candidate = ipaddress.ip_network((pool_start + (index * block_size), subnet_prefix))
        if not any(candidate.overlaps(existing) for existing in used_networks):
            return candidate

    raise RuntimeError("Ithute hosted network pool is exhausted")


def parse_existing_subnets(lines: Iterable[str]) -> list[ipaddress.IPv4Network]:
    result: list[ipaddress.IPv4Network] = []
    for raw in lines:
        value = raw.strip()
        if not value:
            continue
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError:
            continue
        if isinstance(network, ipaddress.IPv4Network):
            result.append(network)
    return result
