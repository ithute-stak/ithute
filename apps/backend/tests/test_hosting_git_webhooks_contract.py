import json

import pytest
from fastapi import HTTPException

from app.api.v1.hosting_git_webhooks import (
    _branch_and_commit,
    _delivery_id,
    _hmac_signature,
    _safe_commit,
    _verify_signature,
)


class Headers(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


def test_github_signature_and_selected_branch():
    secret = "ith_hook_test_secret"
    body = json.dumps({"ref": "refs/heads/main", "after": "a" * 40}).encode()
    headers = Headers({
        "x-hub-signature-256": _hmac_signature(secret, body),
        "x-github-event": "push",
        "x-github-delivery": "delivery-1",
    })
    event = _verify_signature("github", secret, body, headers)
    matched, commit = _branch_and_commit("github", event, json.loads(body), "main")
    assert matched is True
    assert commit == "a" * 40
    assert _delivery_id("github", event, body, headers) == "delivery-1"


def test_github_wrong_branch_does_not_trigger():
    payload = {"ref": "refs/heads/develop", "after": "b" * 40}
    assert _branch_and_commit("github", "push", payload, "main") == (False, None)


def test_gitlab_token_and_push_hook():
    secret = "ith_hook_gitlab"
    body = json.dumps({"ref": "refs/heads/main", "checkout_sha": "c" * 40}).encode()
    headers = Headers({"x-gitlab-token": secret, "x-gitlab-event": "Push Hook"})
    event = _verify_signature("gitlab", secret, body, headers)
    assert _branch_and_commit("gitlab", event, json.loads(body), "main") == (True, "c" * 40)


def test_bitbucket_hmac_and_branch_change():
    secret = "ith_hook_bitbucket"
    payload = {
        "push": {
            "changes": [
                {"new": {"type": "branch", "name": "main", "target": {"hash": "d" * 40}}}
            ]
        }
    }
    body = json.dumps(payload).encode()
    headers = Headers({"x-hub-signature": _hmac_signature(secret, body), "x-event-key": "repo:push"})
    event = _verify_signature("bitbucket", secret, body, headers)
    assert _branch_and_commit("bitbucket", event, payload, "main") == (True, "d" * 40)


def test_generic_webhook_uses_hmac():
    secret = "ith_hook_generic"
    payload = {"ref": "main", "commit": "e" * 40}
    body = json.dumps(payload).encode()
    headers = Headers({"x-ithute-signature": _hmac_signature(secret, body), "x-ithute-event": "push"})
    event = _verify_signature("generic", secret, body, headers)
    assert _branch_and_commit("generic", event, payload, "main") == (True, "e" * 40)


def test_invalid_hmac_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _verify_signature("github", "secret", b"{}", Headers({"x-hub-signature-256": "sha256=bad"}))
    assert exc.value.status_code == 401


def test_fallback_delivery_id_is_deterministic():
    body = b'{"ref":"main"}'
    first = _delivery_id("generic", "push", body, Headers())
    second = _delivery_id("generic", "push", body, Headers())
    assert first == second
    assert len(first) == 64


@pytest.mark.parametrize("value", ["a" * 7, "b" * 40, "c" * 64])
def test_safe_commit_accepts_hex(value: str):
    assert _safe_commit(value) == value


@pytest.mark.parametrize("value", ["", "xyz", "g" * 40, "a" * 65])
def test_safe_commit_drops_invalid_values(value: str):
    assert _safe_commit(value) is None
