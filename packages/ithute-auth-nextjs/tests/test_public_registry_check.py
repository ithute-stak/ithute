import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_public_registry.py"
spec = importlib.util.spec_from_file_location("check_public_registry", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_public_package_exists_without_claiming_ownership():
    status, msg=module.classify(200,b'{"name":"ithute-auth","dist-tags":{"latest":"0.1.0"}}')
    assert status == 0
    assert "ownership separately" in msg

def test_missing_package_does_not_prove_ownership():
    status,msg=module.classify(404,b"")
    assert status == 2
    assert "unverified" in msg

def test_malformed_or_unavailable_registry_blocks_release():
    assert module.classify(200,b"not json")[0] == 1
    assert module.classify(503,b"")[0] == 1
    assert module.classify(200,b'{"name":"other"}')[0] == 1
