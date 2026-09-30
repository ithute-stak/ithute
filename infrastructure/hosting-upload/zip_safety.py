from __future__ import annotations

import os
import pathlib
import stat
import zipfile
from dataclasses import dataclass


@dataclass(frozen=True)
class ZipInspection:
    file_count: int
    unpacked_size_bytes: int
    compressed_payload_bytes: int


class UnsafeZip(ValueError):
    pass


def _safe_member_name(name: str) -> pathlib.PurePosixPath:
    if not name or "\x00" in name or "\\" in name:
        raise UnsafeZip("ZIP contains an invalid member name")
    if len(name) > 1024:
        raise UnsafeZip("ZIP contains an excessively long member path")
    path = pathlib.PurePosixPath(name)
    if path.is_absolute() or name.startswith(("/", "~")):
        raise UnsafeZip("ZIP contains an absolute member path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafeZip("ZIP contains a traversal or ambiguous member path")
    if path.parts and len(path.parts[0]) >= 2 and path.parts[0][1:2] == ":":
        raise UnsafeZip("ZIP contains a drive-qualified member path")
    return path


def inspect_zip(
    archive_path: pathlib.Path,
    *,
    max_files: int,
    max_unpacked_bytes: int,
    max_ratio: int = 250,
    max_single_file_bytes: int = 512 * 1024 * 1024,
) -> ZipInspection:
    file_count = 0
    unpacked = 0
    compressed = 0
    seen: set[str] = set()
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            if not infos:
                raise UnsafeZip("ZIP archive is empty")
            for info in infos:
                path = _safe_member_name(info.filename)
                normalized = path.as_posix().rstrip("/")
                if normalized in seen:
                    raise UnsafeZip("ZIP contains duplicate member paths")
                seen.add(normalized)
                if info.flag_bits & 0x1:
                    raise UnsafeZip("Encrypted ZIP members are not supported")

                mode = (info.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(mode) if mode else 0
                if stat.S_ISLNK(mode):
                    raise UnsafeZip("ZIP symlinks are not allowed")
                if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise UnsafeZip("ZIP contains a special filesystem entry")
                if info.is_dir():
                    continue

                file_count += 1
                if file_count > max_files:
                    raise UnsafeZip("ZIP exceeds the file-count limit")
                if info.file_size < 0 or info.file_size > max_single_file_bytes:
                    raise UnsafeZip("ZIP contains a file exceeding the per-file limit")
                unpacked += info.file_size
                compressed += info.compress_size
                if unpacked > max_unpacked_bytes:
                    raise UnsafeZip("ZIP exceeds the unpacked-size limit")
                if info.file_size and info.compress_size == 0:
                    raise UnsafeZip("ZIP contains an invalid zero-byte compressed payload")
                if info.compress_size and info.file_size / info.compress_size > max_ratio:
                    raise UnsafeZip("ZIP member compression ratio is too high")

            if file_count < 1:
                raise UnsafeZip("ZIP archive contains no files")
            if compressed and unpacked / compressed > max_ratio:
                raise UnsafeZip("ZIP aggregate compression ratio is too high")
    except zipfile.BadZipFile as exc:
        raise UnsafeZip("Uploaded file is not a valid ZIP archive") from exc

    return ZipInspection(file_count=file_count, unpacked_size_bytes=unpacked, compressed_payload_bytes=compressed)


def safe_object_path(root: pathlib.Path, object_key: str) -> pathlib.Path:
    if not object_key or "\\" in object_key or "\x00" in object_key:
        raise UnsafeZip("Invalid quarantine object key")
    relative = pathlib.PurePosixPath(object_key)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise UnsafeZip("Invalid quarantine object key")
    target = (root / pathlib.Path(*relative.parts)).resolve()
    resolved_root = root.resolve()
    if resolved_root != target and resolved_root not in target.parents:
        raise UnsafeZip("Quarantine object key escapes verified storage")
    return target
