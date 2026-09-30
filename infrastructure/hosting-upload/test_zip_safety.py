from __future__ import annotations

import pathlib
import stat
import tempfile
import unittest
import zipfile

from zip_safety import UnsafeZip, inspect_zip, safe_object_path


class ZipSafetyTests(unittest.TestCase):
    def make_zip(self, members: dict[str, bytes], *, symlink: str | None = None) -> pathlib.Path:
        handle = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        handle.close()
        path = pathlib.Path(handle.name)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in members.items():
                archive.writestr(name, data)
            if symlink:
                info = zipfile.ZipInfo(symlink)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, "../../outside")
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_accepts_normal_source_zip(self):
        path = self.make_zip({"app/index.html": b"hello", "app/main.js": b"console.log(1)"})
        result = inspect_zip(path, max_files=100, max_unpacked_bytes=1024 * 1024)
        self.assertEqual(result.file_count, 2)
        self.assertGreater(result.unpacked_size_bytes, 0)

    def test_rejects_parent_traversal(self):
        path = self.make_zip({"../escape.txt": b"bad"})
        with self.assertRaises(UnsafeZip):
            inspect_zip(path, max_files=100, max_unpacked_bytes=1024 * 1024)

    def test_rejects_backslash_paths(self):
        path = self.make_zip({"..\\escape.txt": b"bad"})
        with self.assertRaises(UnsafeZip):
            inspect_zip(path, max_files=100, max_unpacked_bytes=1024 * 1024)

    def test_rejects_symlinks(self):
        path = self.make_zip({"app.txt": b"ok"}, symlink="link")
        with self.assertRaises(UnsafeZip):
            inspect_zip(path, max_files=100, max_unpacked_bytes=1024 * 1024)

    def test_rejects_file_count_limit(self):
        path = self.make_zip({f"f{i}.txt": b"x" for i in range(3)})
        with self.assertRaises(UnsafeZip):
            inspect_zip(path, max_files=2, max_unpacked_bytes=1024 * 1024)

    def test_rejects_unpacked_size_limit(self):
        path = self.make_zip({"large.bin": b"x" * 4096})
        with self.assertRaises(UnsafeZip):
            inspect_zip(path, max_files=10, max_unpacked_bytes=1024)

    def test_object_key_cannot_escape_verified_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            target = safe_object_path(root, "hosting/tenant/source.zip")
            self.assertTrue(str(target).startswith(str(root.resolve())))
            with self.assertRaises(UnsafeZip):
                safe_object_path(root, "../escape.zip")


if __name__ == "__main__":
    unittest.main()
