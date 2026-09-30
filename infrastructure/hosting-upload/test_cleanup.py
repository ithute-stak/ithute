import os
import pathlib
import tempfile
import time
import unittest

os.environ.setdefault("ITHUTE_API_URL", "https://ithute.example.test")
os.environ.setdefault("ITHUTE_HOSTING_UPLOAD_SERVICE_TOKEN", "ith_upload_test_only")

import cleanup


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.temp.name)
        self.quarantine = root / "quarantine"
        self.verified = root / "verified"
        self.quarantine.mkdir()
        self.verified.mkdir()
        cleanup.QUARANTINE_ROOT = self.quarantine
        cleanup.VERIFIED_ROOT = self.verified
        cleanup.QUARANTINE_GRACE_SECONDS = 3600
        cleanup.ORPHAN_VERIFIED_GRACE_SECONDS = 3600

    def tearDown(self):
        self.temp.cleanup()

    def age(self, path: pathlib.Path, seconds: int = 7200):
        stamp = time.time() - seconds
        os.utime(path, (stamp, stamp))

    def test_referenced_verified_archive_is_never_removed(self):
        path = self.verified / "tenant" / "source.zip"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"zip")
        self.age(path)

        count, size = cleanup.clean_verified(time.time(), {"tenant/source.zip"})

        self.assertEqual((count, size), (0, 0))
        self.assertTrue(path.exists())

    def test_old_unreferenced_verified_archive_is_removed(self):
        path = self.verified / "tenant" / "orphan.zip"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"orphan")
        self.age(path)

        count, size = cleanup.clean_verified(time.time(), set())

        self.assertEqual(count, 1)
        self.assertEqual(size, len(b"orphan"))
        self.assertFalse(path.exists())

    def test_fresh_unreferenced_verified_archive_survives_grace(self):
        path = self.verified / "tenant" / "fresh.zip"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"fresh")

        count, _ = cleanup.clean_verified(time.time(), set())

        self.assertEqual(count, 0)
        self.assertTrue(path.exists())

    def test_old_quarantine_temp_is_removed_but_fresh_file_survives(self):
        old = self.quarantine / "upload-old.zip"
        fresh = self.quarantine / "upload-fresh.zip"
        old.write_bytes(b"old")
        fresh.write_bytes(b"fresh")
        self.age(old)

        count, _ = cleanup.clean_quarantine(time.time())

        self.assertEqual(count, 1)
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())

    def test_invalid_inventory_key_aborts_verified_cleanup(self):
        orphan = self.verified / "orphan.zip"
        orphan.write_bytes(b"data")
        self.age(orphan)

        with self.assertRaises(RuntimeError):
            cleanup.clean_verified(time.time(), {"../escape.zip"})

        self.assertTrue(orphan.exists())


if __name__ == "__main__":
    unittest.main()
