from __future__ import annotations

import hashlib
import pathlib
import tempfile
import unittest
import zipfile

from verified_zip import InvalidVerifiedZip, materialize_verified_zip


class VerifiedZipTests(unittest.TestCase):
    def make_archive(self, root: pathlib.Path, object_key: str, members: dict[str, bytes]) -> tuple[pathlib.Path, dict]:
        archive = root / object_key
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
            for name, data in members.items():
                handle.writestr(name, data)
        payload = archive.read_bytes()
        return archive, {
            "object_key": object_key,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }

    def test_materializes_verified_archive(self):
        with tempfile.TemporaryDirectory() as verified, tempfile.TemporaryDirectory() as work:
            root = pathlib.Path(verified)
            _, source = self.make_archive(root, "hosting/a/source.zip", {"app/index.html": b"hello"})
            destination = pathlib.Path(work) / "source"
            effective = materialize_verified_zip(source, destination, root)
            self.assertEqual((effective / "index.html").read_bytes(), b"hello")

    def test_rejects_checksum_change_after_quarantine(self):
        with tempfile.TemporaryDirectory() as verified, tempfile.TemporaryDirectory() as work:
            root = pathlib.Path(verified)
            archive, source = self.make_archive(root, "hosting/a/source.zip", {"index.html": b"hello"})
            source["sha256"] = "a" * 64
            with self.assertRaises(InvalidVerifiedZip):
                materialize_verified_zip(source, pathlib.Path(work) / "source", root)
            self.assertTrue(archive.exists())

    def test_rejects_traversal_even_if_verified_store_is_compromised(self):
        with tempfile.TemporaryDirectory() as verified, tempfile.TemporaryDirectory() as work:
            root = pathlib.Path(verified)
            _, source = self.make_archive(root, "hosting/a/source.zip", {"../outside.txt": b"bad"})
            with self.assertRaises(InvalidVerifiedZip):
                materialize_verified_zip(source, pathlib.Path(work) / "source", root)

    def test_rejects_object_key_escape(self):
        with tempfile.TemporaryDirectory() as verified, tempfile.TemporaryDirectory() as work:
            source = {"object_key": "../escape.zip", "sha256": "a" * 64, "size_bytes": 1}
            with self.assertRaises(InvalidVerifiedZip):
                materialize_verified_zip(source, pathlib.Path(work) / "source", pathlib.Path(verified))


if __name__ == "__main__":
    unittest.main()
