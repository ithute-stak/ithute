import pytest
from pydantic import ValidationError

from app.api.v1.domain_orders import DomainOrderCreate, _normalize_domain


def test_domain_order_normalizes_domain_names():
    assert _normalize_domain("Example.CO.LS.") == "example.co.ls"


@pytest.mark.parametrize("value", ["https://example.co.ls", "user@example.co.ls", "example", "bad domain.co.ls"])
def test_domain_order_rejects_non_domain_input(value: str):
    with pytest.raises(ValueError):
        _normalize_domain(value)


def test_domain_order_accepts_supported_operations():
    for operation in ("register", "renew", "transfer_in"):
        row = DomainOrderCreate(domain_name="example.co.ls", operation=operation, years=1)
        assert row.operation == operation


def test_domain_order_rejects_unknown_operation():
    with pytest.raises(ValidationError):
        DomainOrderCreate(domain_name="example.co.ls", operation="delete", years=1)
