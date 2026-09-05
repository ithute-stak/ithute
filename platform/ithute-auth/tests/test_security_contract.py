from app.security import normalize_email, normalize_phone


def test_normalize_email() -> None:
    assert normalize_email("  USER@Example.COM ") == "user@example.com"
    assert normalize_email("") is None


def test_normalize_phone() -> None:
    assert normalize_phone("+266 5800 0000") == "+26658000000"
    assert normalize_phone("5800-0000") == "58000000"
    assert normalize_phone("") is None
