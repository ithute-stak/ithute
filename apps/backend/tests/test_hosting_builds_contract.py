import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.hosting_builds import BuilderStatus, BuilderTokenCreate, _validate_build_image


def test_builder_name_contract():
    assert BuilderTokenCreate(name="builder-maseru-1").name == "builder-maseru-1"
    with pytest.raises(ValidationError):
        BuilderTokenCreate(name="bad/name")


def test_builder_status_requires_known_state():
    assert BuilderStatus(status="building").status == "building"
    with pytest.raises(ValidationError):
        BuilderStatus(status="deployed")


def test_build_image_requires_approved_digest_pinned_namespace():
    digest = "sha256:" + "a" * 64
    ref = "ghcr.io/ithute-stak/hosted-abc@" + digest
    assert _validate_build_image(ref, digest) == (ref, digest)


@pytest.mark.parametrize(
    ("ref", "digest"),
    [
        ("docker.io/customer/app@sha256:" + "a" * 64, "sha256:" + "a" * 64),
        ("ghcr.io/ithute-stak/hosted-app:latest", "sha256:" + "a" * 64),
        ("ghcr.io/ithute-stak/hosted-app@sha256:" + "a" * 64, "sha256:" + "b" * 64),
        ("ghcr.io/ithute-stak/hosted-app@sha256:nothex", "sha256:nothex"),
    ],
)
def test_build_image_rejects_untrusted_or_mutable_results(ref: str, digest: str):
    with pytest.raises(HTTPException):
        _validate_build_image(ref, digest)
