"""Guard production engine service wiring against accidental drift."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = (ROOT / "compose.production.yml").read_text()
RUNTIME = (ROOT / "apps/backend/app/services/engine_runtime.py").read_text()

def test_go_and_java_worker_services_are_declared_and_isolated():
    for engine in ("go", "java"):
        name = f"ithute-{engine}-worker"
        assert f"  {name}:\n" in COMPOSE
        section = COMPOSE.split(f"  {name}:\n", 1)[1].split("\n  ithute-", 1)[0]
        assert f"image: {name}:${{ITHUTE_IMAGE_TAG:" in section
        assert "read_only: true" in section
        assert "no-new-privileges:true" in section
        assert "cap_drop:" in section
        assert "/healthz" in section
        assert "networks: [ithute]" in section

def test_api_worker_addresses_match_backend_runtime_defaults():
    for engine in ("GO", "JAVA"):
        name = f"ithute-{engine.lower()}-worker"
        assert f"ITHUTE_{engine}_WORKER_URL: http://{name}:8080" in COMPOSE
        assert f'os.getenv("ITHUTE_{engine}_WORKER_URL", "http://{name}:8080")' in RUNTIME
