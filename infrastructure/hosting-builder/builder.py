#!/usr/bin/env python3
"""Ithute isolated hosting source builder.

This worker is intentionally separate from the production hosting-node agent.
It may fetch customer source and publish immutable images, but it must never
receive production Docker-node credentials or activate customer containers.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any

AGENT_VERSION = "ithute-hosting-builder/1"
STOP = False


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


API_URL = required_env("ITHUTE_API_URL").rstrip("/")
BUILDER_TOKEN = required_env("ITHUTE_HOSTING_BUILDER_TOKEN")
POLL_SECONDS = max(5, int(os.getenv("ITHUTE_HOSTING_BUILDER_POLL_SECONDS", "15")))
WORK_ROOT = pathlib.Path(os.getenv("ITHUTE_HOSTING_BUILDER_WORK_ROOT", "/var/lib/ithute-builder/work"))
KNOWN_HOSTS = pathlib.Path(os.getenv("ITHUTE_HOSTING_BUILDER_KNOWN_HOSTS", "/etc/ithute-builder/known_hosts"))

if not API_URL.startswith("https://") and os.getenv("ITHUTE_HOSTING_ALLOW_HTTP", "false").lower() != "true":
    raise RuntimeError("ITHUTE_API_URL must use HTTPS")
if not BUILDER_TOKEN.startswith("ith_build_"):
    raise RuntimeError("ITHUTE_HOSTING_BUILDER_TOKEN is not a builder credential")


def log(message: str) -> None:
    print(f"[hosting-builder] {message}", flush=True)


def api(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{API_URL}/api/v1{path}",
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Ithute-Builder": BUILDER_TOKEN,
            "User-Agent": AGENT_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"Control-plane HTTP {exc.code}: {detail}") from exc


def run(args: list[str], *, cwd: pathlib.Path | None = None, env: dict[str, str] | None = None, timeout: int = 900) -> str:
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    result = subprocess.run(args, cwd=cwd, env=process_env, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"command failed: {detail}")
    return result.stdout.strip()


def detect_runtime(root: pathlib.Path) -> str:
    markers = [
        ("Dockerfile", "dockerfile"),
        ("package.json", "node"),
        ("pyproject.toml", "python"),
        ("requirements.txt", "python"),
        ("composer.json", "php"),
        ("go.mod", "go"),
        ("Cargo.toml", "rust"),
        ("Gemfile", "ruby"),
        ("pom.xml", "java"),
        ("build.gradle", "java"),
    ]
    for filename, runtime in markers:
        if (root / filename).is_file():
            return runtime
    if list(root.glob("*.csproj")) or list(root.glob("*.sln")):
        return "dotnet"
    if (root / "index.html").is_file():
        return "static"
    raise RuntimeError("Unable to detect a supported runtime from source markers")


def validate_checkout(root: pathlib.Path) -> None:
    total_files = 0
    total_bytes = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            target = path.resolve()
            if root.resolve() not in target.parents and target != root.resolve():
                raise RuntimeError("Source contains a symlink escaping the checkout root")
        if path.is_file():
            total_files += 1
            total_bytes += path.stat().st_size
            if total_files > 100_000:
                raise RuntimeError("Source exceeds the builder file-count limit")
            if total_bytes > 2 * 1024 * 1024 * 1024:
                raise RuntimeError("Source exceeds the 2 GiB unpacked limit")


def checkout_git(source: dict[str, Any], destination: pathlib.Path) -> str:
    url = str(source.get("repository_url") or "")
    branch = str(source.get("branch") or "main")
    credential = source.get("credential")
    env: dict[str, str] = {"GIT_TERMINAL_PROMPT": "0"}
    temp_files: list[pathlib.Path] = []
    try:
        if isinstance(credential, dict) and credential.get("auth_type") == "https_token":
            askpass = destination.parent / "git-askpass.sh"
            askpass.write_text("#!/bin/sh\ncase \"$1\" in *Username*) printf '%s\\n' \"$ITHUTE_GIT_USER\" ;; *) printf '%s\\n' \"$ITHUTE_GIT_SECRET\" ;; esac\n", encoding="utf-8")
            askpass.chmod(0o700)
            temp_files.append(askpass)
            env.update({
                "GIT_ASKPASS": str(askpass),
                "ITHUTE_GIT_USER": str(credential.get("username") or "git"),
                "ITHUTE_GIT_SECRET": str(credential.get("secret") or ""),
            })
        elif isinstance(credential, dict) and credential.get("auth_type") == "ssh_key":
            if not KNOWN_HOSTS.is_file():
                raise RuntimeError("SSH source requires a pinned known_hosts file")
            key = destination.parent / "source-key"
            key.write_text(str(credential.get("secret") or ""), encoding="utf-8")
            key.chmod(0o600)
            temp_files.append(key)
            env["GIT_SSH_COMMAND"] = f"ssh -i {key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile={KNOWN_HOSTS}"
        run(["git", "clone", "--depth", "1", "--single-branch", "--branch", branch, "--", url, str(destination)], env=env, timeout=600)
        validate_checkout(destination)
        commit = run(["git", "rev-parse", "HEAD"], cwd=destination, env=env, timeout=30).lower()
        if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
            raise RuntimeError("Checkout did not produce a valid Git commit id")
        return commit
    finally:
        for path in temp_files:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def process_build(work: dict[str, Any]) -> None:
    build_id = str(work["id"])
    source = work.get("source") or {}
    if source.get("type") != "git":
        raise RuntimeError("ZIP builds remain disabled until the quarantine service supplies verified source bytes")
    with tempfile.TemporaryDirectory(prefix=f"ithute-build-{build_id[:8]}-", dir=WORK_ROOT) as temp:
        root = pathlib.Path(temp) / "source"
        api(f"/hosting/builder/builds/{build_id}/status", {"status": "building", "message": "Source checkout started"})
        commit = checkout_git(source, root)
        detected = detect_runtime(root)
        expected = str(work.get("runtime") or "")
        if expected != "dockerfile" and detected != expected:
            raise RuntimeError(f"Runtime mismatch: project expects {expected}, source looks like {detected}")
        # Image construction is deliberately not performed until the managed
        # runtime templates/BuildKit sandbox are installed. Reporting success
        # without a registry digest is forbidden by the control plane.
        raise RuntimeError(f"Source verified at {commit}; isolated BuildKit runtime template for {expected} is not enabled yet")


def main() -> int:
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    api("/hosting/builder/heartbeat", {"version": AGENT_VERSION})
    log(f"starting {AGENT_VERSION}")
    while True:
        try:
            result = api("/hosting/builder/builds/claim")
            work = result.get("build")
            if isinstance(work, dict):
                try:
                    process_build(work)
                except Exception as exc:
                    message = str(exc)[:1900]
                    log(f"build {work.get('id')} failed: {message}")
                    api(f"/hosting/builder/builds/{work['id']}/status", {"status": "failed", "message": message})
                continue
        except Exception as exc:
            log(f"poll failed: {exc}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
