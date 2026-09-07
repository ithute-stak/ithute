from __future__ import annotations

import os
import subprocess
import sys


def test_central_auth_import_does_not_require_legacy_jwt_keys():
    """Production central Auth must boot without migration-only Tutor key files.

    Run in a fresh interpreter so the Settings singleton and module cache cannot
    hide an eager import of utils.decode_encode_token. This reproduces the
    production failure where importing utils.auth.tokens used to call
    load_keys(settings) before Uvicorn could load the application.
    """
    env = os.environ.copy()
    for key in (
        "JWT_PRIVATE_KEY",
        "JWT_PUBLIC_KEY",
        "JWT_PRIVATE_KEY_PATH",
        "JWT_PUBLIC_KEY_PATH",
    ):
        env.pop(key, None)
    env["LEGACY_AUTH_ENABLED"] = "false"

    code = """
import sys
from utils.auth.tokens import get_current_user
assert callable(get_current_user)
assert 'utils.decode_encode_token' not in sys.modules
print('Tutor central-auth import is independent of legacy JWT keys.')
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=os.getcwd(),
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "independent of legacy JWT keys" in completed.stdout
