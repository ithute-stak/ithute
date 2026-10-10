import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_public_registry.py"
spec = importlib.util.spec_from_file_location("check_public_registry", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class RegistryCheckTests(unittest.TestCase):
    def test_public_package_exists_without_claiming_ownership(self):
        status, msg = module.classify(200, b'{"name":"ithute-auth","dist-tags":{"latest":"0.1.0"}}')
        self.assertEqual(status, 0)
        self.assertIn("ownership separately", msg)

    def test_missing_package_does_not_prove_ownership(self):
        status, msg = module.classify(404, b"")
        self.assertEqual(status, 2)
        self.assertIn("unverified", msg)

    def test_malformed_or_unavailable_registry_blocks_release(self):
        self.assertEqual(module.classify(200, b"not json")[0], 1)
        self.assertEqual(module.classify(503, b"")[0], 1)
        self.assertEqual(module.classify(200, b'{"name":"other"}')[0], 1)

if __name__ == "__main__":
    unittest.main()
