from fastapi import Request

from app.main import _request_origin, _strip_untrusted_proxy_headers
from app.services.auth_security import request_client_ip, request_is_https


def _request(*, peer: str, headers: list[tuple[bytes, bytes]], scheme: str = "http") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": scheme,
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": headers,
            "client": (peer, 43210),
            "server": ("backend", 8000),
        }
    )


def test_direct_client_cannot_spoof_proxy_identity_or_https():
    request = _request(
        peer="203.0.113.20",
        headers=[
            (b"host", b"direct.example"),
            (b"x-real-ip", b"198.51.100.9"),
            (b"x-forwarded-for", b"198.51.100.9"),
            (b"x-forwarded-host", b"panel.ithute.co.ls"),
            (b"x-forwarded-proto", b"https"),
        ],
    )

    assert request_client_ip(request) == "203.0.113.20"
    assert request_is_https(request) is False

    _strip_untrusted_proxy_headers(request)
    assert request.headers.get("x-real-ip") is None
    assert request.headers.get("x-forwarded-for") is None
    assert request.headers.get("x-forwarded-host") is None
    assert request.headers.get("x-forwarded-proto") is None
    assert _request_origin(request) == "http://direct.example"


def test_trusted_docker_proxy_can_supply_original_request_context():
    request = _request(
        peer="172.20.0.5",
        headers=[
            (b"host", b"backend:8000"),
            (b"x-real-ip", b"203.0.113.44"),
            (b"x-forwarded-host", b"panel.ithute.co.ls"),
            (b"x-forwarded-proto", b"https"),
        ],
    )

    _strip_untrusted_proxy_headers(request)
    assert request_client_ip(request) == "203.0.113.44"
    assert request_is_https(request) is True
    assert request.headers.get("x-forwarded-proto") == "https"
    assert _request_origin(request) == "https://panel.ithute.co.ls"


def test_invalid_forwarded_ip_is_not_used_for_rate_limit_identity():
    request = _request(
        peer="172.20.0.5",
        headers=[
            (b"host", b"backend:8000"),
            (b"x-real-ip", b"not-an-ip-address"),
            (b"x-forwarded-proto", b"https"),
        ],
    )

    assert request_client_ip(request) == "172.20.0.5"
    assert request_is_https(request) is True
