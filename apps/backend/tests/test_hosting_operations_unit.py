import pytest
from fastapi import HTTPException

from app.api.v1.hosting_operations import _validate_image_ref, _validate_source_commit


def test_deployment_requires_immutable_sha256_image_reference():
    image, digest = _validate_image_ref(
        "ghcr.io/ithute-stak/hosted-customer-app@sha256:" + "a" * 64
    )
    assert image.endswith("@" + digest)
    assert digest == "sha256:" + "a" * 64

    with pytest.raises(HTTPException) as exc:
        _validate_image_ref("ghcr.io/ithute-stak/hosted-customer-app:latest")
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        _validate_image_ref("ghcr.io/example/customer-app@sha256:" + "b" * 64)
    assert exc.value.status_code == 422


def test_source_commit_accepts_git_hex_and_rejects_untrusted_text():
    assert _validate_source_commit("ABCDEF0123456789") == "abcdef0123456789"
    assert _validate_source_commit(None) is None

    with pytest.raises(HTTPException) as exc:
        _validate_source_commit("main; rm -rf /")
    assert exc.value.status_code == 422
