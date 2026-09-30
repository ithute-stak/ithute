from __future__ import annotations

import hashlib
import pathlib
import shutil
import stat
import zipfile
from typing import Any

MAX_FILES = 100_000
MAX_UNPACKED = 2 * 1024 * 1024 * 1024
MAX_SINGLE_FILE = 512 * 1024 * 1024
MAX_RATIO = 250


class InvalidVerifiedZip(RuntimeError):
    pass


def _object_path(root: pathlib.Path, object_key: str) -> pathlib.Path:
    if not object_key or "\\" in object_key or "\x00" in object_key:
        raise InvalidVerifiedZip("Invalid verified ZIP object key")
    relative = pathlib.PurePosixPath(object_key)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise InvalidVerifiedZip("Invalid verified ZIP object key")
    target = (root / pathlib.Path(*relative.parts)).resolve()
    resolved_root = root.resolve()
    if resolved_root != target and resolved_root not in target.parents:
        raise InvalidVerifiedZip("Verified ZIP object key escapes storage root")
    return target


def _member_path(destination: pathlib.Path, name: str) -> pathlib.Path:
    if not name or "\x00" in name or "\\" in name or len(name) > 1024:
        raise InvalidVerifiedZip("ZIP contains an invalid member path")
    relative = pathlib.PurePosixPath(name)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise InvalidVerifiedZip("ZIP contains an unsafe member path")
    target = (destination / pathlib.Path(*relative.parts)).resolve()
    resolved = destination.resolve()
    if resolved != target and resolved not in target.parents:
        raise InvalidVerifiedZip("ZIP member escapes build source root")
    return target


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def materialize_verified_zip(source: dict[str, Any], destination: pathlib.Path, verified_root: pathlib.Path) -> pathlib.Path:
    object_key = str(source.get("object_key") or "")
    expected_sha = str(source.get("sha256") or "").lower()
    expected_size = int(source.get("size_bytes") or 0)
    if len(expected_sha) != 64 or any(ch not in "0123456789abcdef" for ch in expected_sha):
        raise InvalidVerifiedZip("Control plane did not provide a verified ZIP checksum")
    if expected_size <= 0:
        raise InvalidVerifiedZip("Control plane did not provide a verified ZIP size")

    archive_path = _object_path(verified_root, object_key)
    if not archive_path.is_file() or archive_path.is_symlink():
        raise InvalidVerifiedZip("Verified ZIP archive is unavailable")
    if archive_path.stat().st_size != expected_size:
        raise InvalidVerifiedZip("Verified ZIP size changed after quarantine")
    if _sha256(archive_path) != expected_sha:
        raise InvalidVerifiedZip("Verified ZIP checksum changed after quarantine")

    destination.mkdir(parents=True, exist_ok=False)
    file_count = 0
    unpacked = 0
    compressed = 0
    seen: set[str] = set()
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            for info in archive.infolist():
                target = _member_path(destination, info.filename)
                normalized = target.relative_to(destination.resolve()).as_posix().rstrip("/")
                if normalized in seen:
                    raise InvalidVerifiedZip("ZIP contains duplicate member paths")
                seen.add(normalized)
                if info.flag_bits & 0x1:
                    raise InvalidVerifiedZip("Encrypted ZIP members are not supported")
                mode = (info.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(mode) if mode else 0
                if stat.S_ISLNK(mode) or file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise InvalidVerifiedZip("ZIP contains a link or special filesystem entry")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                file_count += 1
                if file_count > MAX_FILES:
                    raise InvalidVerifiedZip("ZIP exceeds builder file-count limit")
                if info.file_size < 0 or info.file_size > MAX_SINGLE_FILE:
                    raise InvalidVerifiedZip("ZIP contains a file exceeding builder limits")
                unpacked += info.file_size
                compressed += info.compress_size
                if unpacked > MAX_UNPACKED:
                    raise InvalidVerifiedZip("ZIP exceeds builder unpacked-size limit")
                if info.file_size and info.compress_size == 0:
                    raise InvalidVerifiedZip("ZIP contains an invalid compressed entry")
                if info.compress_size and info.file_size / info.compress_size > MAX_RATIO:
                    raise InvalidVerifiedZip("ZIP compression ratio exceeds builder limit")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source_handle, target.open("wb") as output:
                    shutil.copyfileobj(source_handle, output, length=1024 * 1024)
                target.chmod(0o600)
            if file_count < 1:
                raise InvalidVerifiedZip("ZIP contains no source files")
            if compressed and unpacked / compressed > MAX_RATIO:
                raise InvalidVerifiedZip("ZIP aggregate compression ratio exceeds builder limit")
    except zipfile.BadZipFile as exc:
        raise InvalidVerifiedZip("Verified archive is no longer a valid ZIP") from exc

    entries = [item for item in destination.iterdir()]
    if len(entries) == 1 and entries[0].is_dir() and not entries[0].is_symlink():
        return entries[0]
    return destination
