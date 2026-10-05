from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_health_controller_import_does_not_require_full_application_settings():
    backend_dir = Path(__file__).resolve().parents[1]
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "DKIM_ENCRYPTION_KEY",
            "BILLING_WEBHOOK_SECRET",
            "BOOTSTRAP_ADMIN_PASSWORD",
            "POWERDNS_API_KEY",
            "MAIL_OPS_TOKEN",
            "MAIL_NODE_TOKEN",
            "RECOVERY_OPS_TOKEN",
        }
    }
    env.update(
        {
            "ENVIRONMENT": "production",
            "PLATFORM_MODE": "domain",
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "SECRET_KEY": "controller-import-contract-secret-key-000000000000",
        }
    )

    script = """
import sys
import app.services.hosting_node_health_daemon
assert "app.core.config" not in sys.modules, (
    "health controller import must not load full application Settings; "
    "the controller only needs its narrow worker configuration"
)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
