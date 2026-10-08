from unittest.mock import MagicMock, patch
from fastapi import HTTPException
import pytest
from app.api.v1.webmail_productivity import read_receipt_evidence


def test_history_requires_authenticated_mailbox():
    with patch('app.api.v1.webmail_productivity._owner', side_effect=HTTPException(status_code=401)):
        with pytest.raises(HTTPException) as exc:
            read_receipt_evidence('<msg@example.com>', token=None, db=MagicMock())
    assert exc.value.status_code == 401
