#!/usr/bin/env python3
"""Verify the Ithute authoritative DNS server directly over UDP and TCP."""

from __future__ import annotations

import argparse
import ipaddress
import os
import random
import socket
import struct
from dataclasses import dataclass

A = 1
NS = 2
IN = 1


@dataclass(frozen=True)
class Record:
    name: str
    rtype: int
    value: str


def encode_name(name: str) -> bytes:
    name = name.rstrip(".")
    if not name:
        return b"\x00"
    encoded = bytearray()
    for label in name.split("."):
        part = label.encode("ascii")
        if not part or len(part) > 63:
            raise ValueError(f"invalid DNS label: {label!r}")
        encoded.append(len(part))
        encoded.extend(part)
    encoded.append(0)
    return bytes(encoded)


def read_name(message: bytes, offset: int) -> tuple[str, int]:
    labels: list[str] = []
    end_offset: int | None = None
    seen: set[int] = set()

    while True:
        if offset >= len(message):
            raise ValueError("DNS name exceeds message length")
        if offset in seen:
            raise ValueError("DNS compression pointer loop")
        seen.add(offset)

        length = message[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(message):
                raise ValueError("truncated DNS compression pointer")
            pointer = ((length & 0x3F) << 8) | message[offset + 1]
            if end_offset is None:
                end_offset = offset + 2
            offset = pointer
            continue

        if length == 0:
            if end_offset is None:
                end_offset = offset + 1
            return ".".join(labels) + ".", end_offset

        if length & 0xC0:
            raise ValueError("unsupported DNS label encoding")
        offset += 1
        if offset + length > len(message):
            raise ValueError("truncated DNS label")
        labels.append(message[offset : offset + length].decode("ascii"))
        offset += length


def recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise ConnectionError("DNS TCP connection closed early")
        chunks.extend(chunk)
    return bytes(chunks)


def exchange(server: str, packet: bytes, protocol: str, timeout: float) -> bytes:
    address = (server, 53)
    if protocol == "udp":
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(packet, address)
            response, peer = sock.recvfrom(65535)
            if peer[0] != server:
                raise RuntimeError(f"unexpected DNS responder: {peer[0]}")
            return response

    with socket.create_connection(address, timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(struct.pack("!H", len(packet)) + packet)
        length = struct.unpack("!H", recv_exact(sock, 2))[0]
        return recv_exact(sock, length)


def query(server: str, name: str, rtype: int, protocol: str, timeout: float) -> list[Record]:
    query_id = random.SystemRandom().randrange(0, 65536)
    # RD=0: this must be an authoritative answer, not recursion.
    packet = struct.pack("!HHHHHH", query_id, 0, 1, 0, 0, 0)
    packet += encode_name(name) + struct.pack("!HH", rtype, IN)
    message = exchange(server, packet, protocol, timeout)

    if len(message) < 12:
        raise ValueError("truncated DNS response")
    response_id, flags, qdcount, ancount, _nscount, _arcount = struct.unpack("!HHHHHH", message[:12])
    if response_id != query_id:
        raise ValueError("DNS transaction ID mismatch")
    if not flags & 0x8000:
        raise ValueError("response is not marked as a DNS response")
    if not flags & 0x0400:
        raise ValueError(f"{name} response is not authoritative")
    rcode = flags & 0x000F
    if rcode != 0:
        raise ValueError(f"{name} returned DNS rcode {rcode}")

    offset = 12
    for _ in range(qdcount):
        _qname, offset = read_name(message, offset)
        offset += 4
        if offset > len(message):
            raise ValueError("truncated DNS question")

    records: list[Record] = []
    for _ in range(ancount):
        owner, offset = read_name(message, offset)
        if offset + 10 > len(message):
            raise ValueError("truncated DNS resource record")
        rrtype, rrclass, _ttl, rdlength = struct.unpack("!HHIH", message[offset : offset + 10])
        offset += 10
        rdata_offset = offset
        offset += rdlength
        if offset > len(message):
            raise ValueError("truncated DNS rdata")
        if rrclass != IN:
            continue
        if rrtype == A and rdlength == 4:
            value = socket.inet_ntoa(message[rdata_offset : rdata_offset + 4])
            records.append(Record(owner, rrtype, value))
        elif rrtype == NS:
            value, _ = read_name(message, rdata_offset)
            records.append(Record(owner, rrtype, value.lower()))

    return records


def require_a(server: str, hostname: str, expected_ip: str, protocol: str, timeout: float) -> None:
    values = {record.value for record in query(server, hostname, A, protocol, timeout) if record.rtype == A}
    if expected_ip not in values:
        raise SystemExit(
            f"{protocol.upper()} authoritative A check failed for {hostname}: "
            f"expected {expected_ip}, got {sorted(values)}"
        )


def require_ns(server: str, protocol: str, timeout: float) -> None:
    values = {record.value for record in query(server, "ithute.co.ls", NS, protocol, timeout) if record.rtype == NS}
    expected = {"ns1.ithute.co.ls.", "ns2.ithute.co.ls."}
    if values != expected:
        raise SystemExit(
            f"{protocol.upper()} authoritative NS check failed: expected {sorted(expected)}, got {sorted(values)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default=os.environ.get("ITHUTE_PUBLIC_IPV4", "204.12.205.224"))
    parser.add_argument("--expected-ip", default=os.environ.get("ITHUTE_PUBLIC_IPV4", "204.12.205.224"))
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    # This verifier intentionally targets IPv4 because the current authoritative
    # service and registrar glue are anchored to the production VPS IPv4.
    ipaddress.IPv4Address(args.server)
    ipaddress.IPv4Address(args.expected_ip)

    hosts = (
        "ithute.co.ls",
        "ns1.ithute.co.ls",
        "ns2.ithute.co.ls",
        "www.ithute.co.ls",
        "auth.ithute.co.ls",
        "push.ithute.co.ls",
        "realtime.ithute.co.ls",
        "mail.ithute.co.ls",
    )

    for protocol in ("udp", "tcp"):
        for hostname in hosts:
            require_a(args.server, hostname, args.expected_ip, protocol, args.timeout)
        require_ns(args.server, protocol, args.timeout)

    print(
        f"Authoritative DNS is reachable on UDP/TCP 53 at {args.server}; "
        "ns1.ithute.co.ls and ns2.ithute.co.ls serve the Ithute zone."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
