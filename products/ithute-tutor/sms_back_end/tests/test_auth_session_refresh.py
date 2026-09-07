from __future__ import annotations

import httpx
from starlette.requests import Request

from routes import auth


def make_request(*, refresh_token: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if refresh_token is not None:
        cookie = f"{auth.settings.AUTH_REFRESH_COOKIE_NAME}={refresh_token}".encode("latin-1")
        headers.append((b"cookie", cookie))

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/auth/refresh",
            "raw_path": b"/auth/refresh",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443),
        }
    )


class FakeResponse:
    def __init__(self, status_code: int, payload: object):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def set_cookie_headers(response) -> list[str]:
    return [value.decode("latin-1") for key, value in response.raw_headers if key.lower() == b"set-cookie"]


def test_refresh_without_cookie_ends_and_clears_stale_session():
    response = auth.refresh(make_request())

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    cookies = "\n".join(set_cookie_headers(response))
    assert auth.settings.AUTH_ACCESS_COOKIE_NAME in cookies
    assert auth.settings.AUTH_REFRESH_COOKIE_NAME in cookies
    assert "Max-Age=0" in cookies


def test_central_invalid_refresh_ends_and_clears_session(monkeypatch):
    monkeypatch.setattr(auth.httpx, "post", lambda *args, **kwargs: FakeResponse(401, {"detail": "expired"}))

    response = auth.refresh(make_request(refresh_token="expired-refresh"))

    assert response.status_code == 401
    cookies = "\n".join(set_cookie_headers(response))
    assert auth.settings.AUTH_REFRESH_COOKIE_NAME in cookies
    assert "Max-Age=0" in cookies


def test_central_outage_preserves_local_session_for_retry(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ConnectError("central Auth unavailable")

    monkeypatch.setattr(auth.httpx, "post", fail)

    response = auth.refresh(make_request(refresh_token="still-valid-refresh"))

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    cookies = "\n".join(set_cookie_headers(response))
    assert auth.settings.AUTH_REFRESH_COOKIE_NAME not in cookies
    assert auth.settings.AUTH_ACCESS_COOKIE_NAME not in cookies


def test_central_server_error_preserves_local_session(monkeypatch):
    monkeypatch.setattr(auth.httpx, "post", lambda *args, **kwargs: FakeResponse(503, {"detail": "down"}))

    response = auth.refresh(make_request(refresh_token="still-valid-refresh"))

    assert response.status_code == 503
    assert set_cookie_headers(response) == []


def test_successful_refresh_rotates_both_session_cookies(monkeypatch):
    monkeypatch.setattr(
        auth.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(
            200,
            {"access_token": "new-access", "refresh_token": "new-refresh"},
        ),
    )
    monkeypatch.setattr(auth, "validate_central_access_token", lambda token: {"sub": "test"})

    response = auth.refresh(make_request(refresh_token="old-refresh"))

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    cookies = "\n".join(set_cookie_headers(response))
    assert auth.settings.AUTH_ACCESS_COOKIE_NAME in cookies
    assert auth.settings.AUTH_REFRESH_COOKIE_NAME in cookies
    assert "new-access" in cookies
    assert "new-refresh" in cookies


def test_malformed_success_response_does_not_clear_session(monkeypatch):
    monkeypatch.setattr(auth.httpx, "post", lambda *args, **kwargs: FakeResponse(200, ValueError("bad json")))

    response = auth.refresh(make_request(refresh_token="valid-refresh"))

    assert response.status_code == 502
    assert set_cookie_headers(response) == []
