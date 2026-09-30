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
import subprocess
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from typing import Any

from verified_zip import materialize_verified_zip

AGENT_VERSION = "ithute-hosting-builder/3"
IMAGE_NAME_RE = re.compile(r"^ghcr\.io/ithute-stak/hosted-[a-z0-9]+$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


API_URL = required_env("ITHUTE_API_URL").rstrip("/")
BUILDER_TOKEN = required_env("ITHUTE_HOSTING_BUILDER_TOKEN")
POLL_SECONDS = max(5, int(os.getenv("ITHUTE_HOSTING_BUILDER_POLL_SECONDS", "15")))
WORK_ROOT = pathlib.Path(os.getenv("ITHUTE_HOSTING_BUILDER_WORK_ROOT", "/var/lib/ithute-builder/work"))
VERIFIED_ROOT = pathlib.Path(os.getenv("ITHUTE_HOSTING_BUILDER_VERIFIED_ROOT", "/var/lib/ithute-upload/verified"))
KNOWN_HOSTS = pathlib.Path(os.getenv("ITHUTE_HOSTING_BUILDER_KNOWN_HOSTS", "/etc/ithute-builder/known_hosts"))
DOCKER = os.getenv("ITHUTE_HOSTING_BUILDER_DOCKER", "docker")
ALLOW_CUSTOM_DOCKERFILE = os.getenv("ITHUTE_HOSTING_BUILDER_ALLOW_CUSTOM_DOCKERFILE", "false").lower() == "true"

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
    if (root / "Dockerfile").is_file():
        return "dockerfile"
    raise RuntimeError("Unable to detect a supported runtime from source markers")


def validate_checkout(root: pathlib.Path) -> None:
    total_files = 0
    total_bytes = 0
    resolved_root = root.resolve()
    for path in root.rglob("*"):
        if path.is_symlink():
            target = path.resolve()
            if resolved_root not in target.parents and target != resolved_root:
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


def _json_exec(command: str) -> str:
    return json.dumps(["sh", "-lc", command])


def infer_start_command(root: pathlib.Path, runtime: str, port: int) -> str | None:
    if runtime == "node" and (root / "package.json").is_file():
        try:
            package = json.loads((root / "package.json").read_text(encoding="utf-8"))
            if isinstance(package.get("scripts"), dict) and package["scripts"].get("start"):
                return "npm start"
        except (OSError, json.JSONDecodeError):
            pass
        for filename in ("server.js", "index.js", "app.js"):
            if (root / filename).is_file():
                return f"node {filename}"
    if runtime == "python":
        for filename in ("app.py", "main.py"):
            if (root / filename).is_file():
                return f"python {filename}"
    if runtime == "php":
        target = "public" if (root / "public").is_dir() else "."
        return f"php -S 0.0.0.0:{port} -t {target}"
    if runtime == "ruby" and (root / "config.ru").is_file():
        return f"bundle exec rackup -o 0.0.0.0 -p {port}"
    if runtime == "go" and (root / "go.mod").is_file():
        return "/opt/ithute/app"
    if runtime == "rust" and (root / "Cargo.toml").is_file():
        try:
            cargo = tomllib.loads((root / "Cargo.toml").read_text(encoding="utf-8"))
            name = str(cargo.get("package", {}).get("name") or "").strip()
            if re.fullmatch(r"[A-Za-z0-9_-]+", name):
                return f"/opt/ithute/{name}"
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return None


def render_managed_dockerfile(root: pathlib.Path, runtime: str, build_command: str | None, start_command: str | None, port: int) -> str:
    if runtime == "static":
        return "\n".join([
            "FROM nginxinc/nginx-unprivileged:stable-alpine",
            "COPY . /usr/share/nginx/html",
            f"EXPOSE {port}",
            "USER 101:101",
            "",
        ])

    base = {
        "node": "node:22-alpine",
        "python": "python:3.12-slim",
        "php": "composer:2",
        "dotnet": "mcr.microsoft.com/dotnet/sdk:8.0",
        "java": "eclipse-temurin:21-jdk-alpine",
        "go": "golang:1.23-alpine",
        "ruby": "ruby:3.3-alpine",
        "rust": "rust:1.82-alpine",
    }.get(runtime)
    if base is None:
        raise RuntimeError(f"No managed build template exists for runtime {runtime}")

    install = {
        "node": "if [ -f package-lock.json ]; then npm ci; else npm install; fi",
        "python": "if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi",
        "php": "if [ -f composer.json ]; then composer install --no-dev --no-interaction --prefer-dist; fi",
        "dotnet": "dotnet restore",
        "java": "true",
        "go": "go mod download",
        "ruby": "if [ -f Gemfile ]; then bundle install; fi",
        "rust": "cargo fetch",
    }[runtime]

    effective_build = build_command
    if not effective_build and runtime == "go":
        effective_build = "go build -trimpath -ldflags='-s -w' -o /opt/ithute/app ."
    elif not effective_build and runtime == "rust":
        cargo = tomllib.loads((root / "Cargo.toml").read_text(encoding="utf-8"))
        package_name = str(cargo.get("package", {}).get("name") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", package_name):
            raise RuntimeError("Rust package name is invalid; provide an explicit build/start command")
        effective_build = f"cargo build --release && cp target/release/{package_name} /opt/ithute/{package_name}"

    effective_start = start_command or infer_start_command(root, runtime, port)
    if not effective_start:
        raise RuntimeError(f"Runtime {runtime} needs an explicit start command for this project")

    lines = [
        f"FROM {base}",
        "WORKDIR /app",
        "COPY . /app",
        "RUN mkdir -p /opt/ithute && chmod 755 /opt/ithute",
        f"RUN {_json_exec(install)}",
    ]
    if effective_build:
        lines.append(f"RUN {_json_exec(effective_build)}")
    lines.extend([
        "ENV HOME=/tmp",
        f"EXPOSE {port}",
        "USER 10001:10001",
        f"CMD {_json_exec(effective_start)}",
        "",
    ])
    return "\n".join(lines)


def build_and_push(work: dict[str, Any], root: pathlib.Path) -> tuple[str, str]:
    runtime = str(work.get("runtime") or "")
    image_name = str(work.get("image_name") or "").lower()
    if not IMAGE_NAME_RE.fullmatch(image_name):
        raise RuntimeError("Control plane supplied an invalid image namespace")
    port = int(work.get("container_port") or 8080)
    if not 1024 <= port <= 65535:
        raise RuntimeError("Control plane supplied an invalid application port")

    with tempfile.TemporaryDirectory(prefix="ithute-dockerfile-", dir=WORK_ROOT) as temp:
        temp_path = pathlib.Path(temp)
        metadata_path = temp_path / "metadata.json"
        tag = f"{image_name}:build-{str(work['id']).replace('-', '')[:16]}"
        args = [
            DOCKER,
            "buildx",
            "build",
            "--pull",
            "--no-cache",
            "--push",
            "--provenance=false",
            "--metadata-file",
            str(metadata_path),
            "--tag",
            tag,
        ]

        if runtime == "dockerfile":
            if not ALLOW_CUSTOM_DOCKERFILE:
                raise RuntimeError("Custom Dockerfile builds are disabled on this builder")
            dockerfile = root / "Dockerfile"
            if not dockerfile.is_file():
                raise RuntimeError("Custom Dockerfile runtime requires Dockerfile at repository root")
            args.extend(["--file", str(dockerfile), str(root)])
        else:
            dockerfile = temp_path / "Managed.Dockerfile"
            dockerfile.write_text(
                render_managed_dockerfile(
                    root,
                    runtime,
                    str(work.get("build_command") or "").strip() or None,
                    str(work.get("start_command") or "").strip() or None,
                    port,
                ),
                encoding="utf-8",
            )
            args.extend(["--file", str(dockerfile), str(root)])

        run(args, timeout=1800)
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("BuildKit did not produce valid image metadata") from exc
        digest = str(metadata.get("containerimage.digest") or metadata.get("containerimage.descriptor", {}).get("digest") or "").lower()
        if not DIGEST_RE.fullmatch(digest):
            raise RuntimeError("BuildKit did not return an immutable registry digest")
        return f"{image_name}@{digest}", digest


def process_build(work: dict[str, Any]) -> None:
    build_id = str(work["id"])
    source = work.get("source") or {}
    source_type = str(source.get("type") or "")
    with tempfile.TemporaryDirectory(prefix=f"ithute-build-{build_id[:8]}-", dir=WORK_ROOT) as temp:
        root = pathlib.Path(temp) / "source"
        api(f"/hosting/builder/builds/{build_id}/status", {"status": "building", "message": "Source materialization started"})
        commit: str | None = None
        if source_type == "git":
            commit = checkout_git(source, root)
        elif source_type == "zip":
            root = materialize_verified_zip(source, root, VERIFIED_ROOT)
            validate_checkout(root)
        else:
            raise RuntimeError("Unsupported hosting source type")

        detected = detect_runtime(root)
        expected = str(work.get("runtime") or "")
        if expected != "dockerfile" and detected != expected:
            raise RuntimeError(f"Runtime mismatch: project expects {expected}, source looks like {detected}")
        if expected == "dockerfile" and detected != "dockerfile":
            raise RuntimeError("Custom Dockerfile runtime requires a repository-root Dockerfile")
        image_ref, digest = build_and_push(work, root)
        api(
            f"/hosting/builder/builds/{build_id}/status",
            {
                "status": "succeeded",
                "image_ref": image_ref,
                "image_digest": digest,
                "source_commit": commit,
                "message": "Immutable image published by isolated builder",
            },
        )
        log(f"build {build_id} published {image_ref}")


def main() -> int:
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    run([DOCKER, "buildx", "version"], timeout=30)
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
