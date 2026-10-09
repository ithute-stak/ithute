import pytest

from app.redirect_uri_policy import validate_redirect_uris


def test_https_callback_and_exact_localhost_dev_url():
    urls = ["https://customer.example.com/api/auth/ithute/callback", "http://localhost:3000/api/auth/ithute/callback"]
    assert validate_redirect_uris(urls) == tuple(urls)


@pytest.mark.parametrize("uri", [
    "http://example.com/callback",
    "https://*.example.com/callback",
    "https://user:password@example.com/callback",
    "https://example.com/callback#fragment",
    "https://example.com\\@evil.com/",
    "http://192.168.0.5:3000/callback",
    "https://example.com/callback ",
])
def test_unsafe_callback_rejected(uri):
    with pytest.raises(ValueError):
        validate_redirect_uris([uri])


def test_callback_set_is_bounded_and_deduplicated():
    with pytest.raises(ValueError):
        validate_redirect_uris([])
    with pytest.raises(ValueError):
        validate_redirect_uris([f"https://example{i}.com/callback" for i in range(11)])
    assert validate_redirect_uris(["https://app.example.com/cb"] * 2) == ("https://app.example.com/cb",)
