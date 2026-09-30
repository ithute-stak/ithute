#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
failures: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


# The frontend has historical page-local development fallbacks. Production
# safety is enforced centrally in next.config.ts so every build gets /api/v1
# unless an explicit public API URL is supplied at build time.
next_config = (ROOT / "apps/frontend/next.config.ts").read_text(encoding="utf-8")
require(
    'NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "/api/v1"' in next_config,
    "Frontend must centrally default NEXT_PUBLIC_API_URL to /api/v1",
)

# Finance pages were actively hardened and should not carry the historical
# localhost fallback at all.
finance_root = ROOT / "apps/frontend/app/finance"
for path in finance_root.rglob("*.tsx"):
    text = path.read_text(encoding="utf-8")
    require(
        "http://localhost:8006/api/v1" not in text,
        f"{path.relative_to(ROOT)} uses a localhost API fallback; use /api/v1",
    )

finance_pages = [
    "apps/frontend/app/finance/page.tsx",
    "apps/frontend/app/finance/clients/page.tsx",
    "apps/frontend/app/finance/collections/page.tsx",
    "apps/frontend/app/finance/documents/page.tsx",
    "apps/frontend/app/finance/reports/page.tsx",
    "apps/frontend/app/finance/accounting/page.tsx",
    "apps/frontend/app/finance/control/page.tsx",
    "apps/frontend/app/finance/governance/page.tsx",
    "apps/frontend/app/finance/sender/page.tsx",
    "apps/frontend/app/finance/invoices/[id]/page.tsx",
]
for relative in finance_pages:
    path = ROOT / relative
    require(path.exists(), f"Missing Finance workspace page: {relative}")
    if path.exists():
        text = path.read_text(encoding="utf-8")
        require("useFinanceAccess" in text, f"{relative} must use delegated Finance access")
        require("setOwner(Boolean(body.is_platform_owner))" not in text, f"{relative} still gates Finance to platform owner only")

hook = ROOT / "apps/frontend/app/finance/_components/use-finance-access.ts"
require(hook.exists(), "Delegated Finance access hook is missing")

backup_ci = (ROOT / ".github/workflows/backup-assurance-ci.yml").read_text(encoding="utf-8")
for marker in (
    "Run a real backup and isolated restore drill",
    "ithute-restore-drill-db",
    "restore-drills.jsonl",
):
    require(marker in backup_ci, f"Backup assurance must retain restore verification marker: {marker}")

readme = (ROOT / "README.md").read_text(encoding="utf-8")
for image in (
    "ithute-web:<commit-sha>",
    "ithute-app-api:<commit-sha>",
    "ithute-auth:<commit-sha>",
    "ithute-push:<commit-sha>",
    "ithute-realtime:<commit-sha>",
):
    require(image in readme, f"README runtime image documentation is incomplete: {image}")
require("scripts/verify-production-readiness.sh" in readme, "README must point operators to the production readiness verifier")

production_check = ROOT / "scripts/verify-production-readiness.sh"
require(production_check.exists(), "Production readiness verifier is missing")

security_deps = (ROOT / "apps/backend/app/api/deps.py").read_text(encoding="utf-8")
for marker in (
    'return "viewer"',
    'return "clerk"',
    'return "approver"',
    'return "admin"',
    '"/api/v1/finance/sender"',
):
    require(marker in security_deps, f"Finance role boundary is missing marker: {marker}")

if failures:
    raise SystemExit("Repository readiness verification failed:\n- " + "\n- ".join(failures))

print("Repository readiness checks passed.")
