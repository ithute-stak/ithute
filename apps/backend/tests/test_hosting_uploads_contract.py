import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.hosting_uploads import UploadAuthorize, UploadComplete, _service_auth


def test_upload_authorize_requires_nontrivial_one_time_token():
    assert UploadAuthorize(upload_token="ith_zip_abcdefghijklmnopqrstuvwxyz").upload_token.startswith("ith_zip_")
    with pytest.raises(ValidationError):
        UploadAuthorize(upload_token="short")


def test_upload_completion_requires_hex_sha_and_positive_file_count():
    payload = UploadComplete(
        sha256="a" * 64,
        size_bytes=1024,
        unpacked_size_bytes=2048,
        file_count=2,
    )
    assert payload.file_count == 2
    with pytest.raises(ValidationError):
        UploadComplete(sha256="not-a-sha", size_bytes=1, unpacked_size_bytes=1, file_count=1)
    with pytest.raises(ValidationError):
        UploadComplete(sha256="a" * 64, size_bytes=1, unpacked_size_bytes=1, file_count=0)


def test_upload_service_auth_is_fail_closed(monkeypatch):
    monkeypatch.delenv("ITHUTE_HOSTING_UPLOAD_SERVICE_TOKEN", raising=False)
    with pytest.raises(HTTPException) as missing:
        _service_auth("ith_upload_anything")
    assert missing.value.status_code == 503

    monkeypatch.setenv("ITHUTE_HOSTING_UPLOAD_SERVICE_TOKEN", "ith_upload_ci-secret")
    with pytest.raises(HTTPException) as invalid:
        _service_auth("ith_upload_wrong")
    assert invalid.value.status_code == 401

    _service_auth("ith_upload_ci-secret")
