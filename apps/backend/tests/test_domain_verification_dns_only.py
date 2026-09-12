import uuid
from types import SimpleNamespace

from app.models.domains import DomainStatus
from app.schemas.domains import DomainVerifyRequest
from app.services.domains import token_hash, verification_value, verify_domain


def fake_db():
    added = []
    return SimpleNamespace(add=added.append), added


def pending_domain(token: str):
    return SimpleNamespace(
        id=uuid.uuid4(),
        verification_record_name="_mailbox-dns-verification.example.com",
        verification_token_hash=token_hash(token),
        verification_token_hint=token[-8:],
        status=DomainStatus.pending_verification,
        ownership_verified_at=None,
    )


def test_verify_request_allows_server_side_dns_verification():
    assert DomainVerifyRequest.model_validate({}).token is None


def test_verify_domain_accepts_matching_public_dns_token_without_browser_token():
    token = "dns-only-verification-token-1234567890abcdef"
    domain = pending_domain(token)
    db, attempts = fake_db()

    success, observed, error = verify_domain(
        domain,
        None,
        uuid.uuid4(),
        db,
        resolver=lambda _: [verification_value(token)],
    )

    assert success is True
    assert observed == [verification_value(token)]
    assert error is None
    assert domain.status == DomainStatus.verified
    assert domain.ownership_verified_at is not None
    assert domain.verification_token_hint == "verified"
    assert len(attempts) == 1
    assert attempts[0].success is True


def test_verify_domain_rejects_unrelated_public_txt_values():
    token = "dns-only-verification-token-1234567890abcdef"
    domain = pending_domain(token)
    db, attempts = fake_db()

    success, observed, error = verify_domain(
        domain,
        None,
        uuid.uuid4(),
        db,
        resolver=lambda _: ["google-site-verification=other", verification_value("wrong-token-12345678901234567890")],
    )

    assert success is False
    assert error is None
    assert domain.status == DomainStatus.pending_verification
    assert len(attempts) == 1
    assert attempts[0].success is False
