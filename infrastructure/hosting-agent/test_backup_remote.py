import pathlib
import tempfile
import unittest
from unittest import mock

import backup_remote


class BackupRemoteTests(unittest.TestCase):
    def setUp(self):
        self.original_remote = backup_remote.REMOTE
        self.original_required = backup_remote.REMOTE_REQUIRED

    def tearDown(self):
        backup_remote.REMOTE = self.original_remote
        backup_remote.REMOTE_REQUIRED = self.original_required

    def test_remote_object_rejects_path_escape(self):
        backup_remote.REMOTE = "remote:ithute"
        with self.assertRaises(RuntimeError):
            backup_remote.remote_object("../secret.sql")
        with self.assertRaises(RuntimeError):
            backup_remote.remote_object("/absolute.sql")
        self.assertEqual(
            backup_remote.remote_object("tenant/database/backup.pgdump"),
            "remote:ithute/tenant/database/backup.pgdump",
        )

    def test_required_remote_missing_fails_closed(self):
        backup_remote.REMOTE = ""
        backup_remote.REMOTE_REQUIRED = True
        with self.assertRaises(RuntimeError):
            backup_remote.require_configuration()

    def test_optional_remote_missing_is_noop_for_replication(self):
        backup_remote.REMOTE = ""
        backup_remote.REMOTE_REQUIRED = False
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "backup"
            path.write_bytes(b"test")
            backup_remote.replicate(path, "tenant/db/backup", "0" * 64, 4)
            self.assertFalse(backup_remote.hydrate("tenant/db/backup", path))

    def test_replicate_verifies_remote_size_and_writes_sidecar(self):
        backup_remote.REMOTE = "remote:ithute"
        backup_remote.REMOTE_REQUIRED = True
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "backup.pgdump"
            path.write_bytes(b"database")
            calls = []

            def fake_run(args, timeout=7200):
                calls.append(args)
                class Result:
                    stdout = "8 backup.pgdump\n"
                    stderr = ""
                    returncode = 0
                return Result()

            with mock.patch.object(backup_remote, "_run", side_effect=fake_run):
                backup_remote.replicate(path, "tenant/db/backup.pgdump", "a" * 64, 8)

            self.assertTrue(any("copyto" in call and "--immutable" in call for call in calls))
            self.assertTrue(any(str(item).endswith(".sha256") for call in calls for item in call))

    def test_hydrate_uses_atomic_destination(self):
        backup_remote.REMOTE = "remote:ithute"
        backup_remote.REMOTE_REQUIRED = True
        with tempfile.TemporaryDirectory() as directory:
            destination = pathlib.Path(directory) / "nested" / "backup.sql"

            def fake_run(args, timeout=7200):
                target = pathlib.Path(args[-1])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"remote-copy")
                class Result:
                    stdout = ""
                    stderr = ""
                    returncode = 0
                return Result()

            with mock.patch.object(backup_remote, "_run", side_effect=fake_run):
                self.assertTrue(backup_remote.hydrate("tenant/db/backup.sql", destination))

            self.assertEqual(destination.read_bytes(), b"remote-copy")
            self.assertFalse(destination.with_name(f".{destination.name}.remote-download").exists())


if __name__ == "__main__":
    unittest.main()
