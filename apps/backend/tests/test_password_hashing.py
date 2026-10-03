import bcrypt
import pytest

from app.core.security import hash_password, verify_password


def test_password_hash_round_trip_uses_standard_bcrypt_format():
    encoded = hash_password("Strong-Test-Password-42!")
    assert encoded.startswith(("$2a$", "$2b$", "$2y$"))
    assert verify_password("Strong-Test-Password-42!", encoded) is True
    assert verify_password("wrong-password", encoded) is False


def test_existing_standard_bcrypt_hash_remains_verifiable():
    password = "Existing-Bcrypt-Password!"
    encoded = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    assert verify_password(password, encoded) is True


def test_passwords_over_bcrypt_limit_fail_safely():
    with pytest.raises(ValueError, match="72 UTF-8 bytes"):
        hash_password("x" * 73)

    valid_hash = hash_password("short-password")
    assert verify_password("x" * 73, valid_hash) is False
