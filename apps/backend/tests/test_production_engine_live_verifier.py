from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

def test_live_engine_verifier_is_read_only_and_fail_closed():
    script = (ROOT / "scripts/verify-production-engines.sh").read_text()
    assert "set -euo pipefail" in script
    assert 'exec -T ithute-app-api python -' in script
    assert "from app.services.engine_runtime import engine_status" in script
    assert '("rust", "cpp", "go", "java")' in script
    assert 'not all(item["available"] for item in results.values())' in script
    assert "sys.exit(1)" in script
    for unsafe in ("docker compose up", "docker compose down", "docker compose restart", "docker compose pull"):
        assert unsafe not in script
