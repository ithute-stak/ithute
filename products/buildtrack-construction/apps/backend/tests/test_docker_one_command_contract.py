from pathlib import Path


def test_docker_compose_starts_complete_stack_with_one_command() -> None:
    root = Path(__file__).resolve().parents[3]
    compose = (root / "compose.yaml").read_text(encoding="utf-8")
    backend_dockerfile = (root / "apps" / "backend" / "Dockerfile").read_text(encoding="utf-8")
    frontend_dockerfile = (root / "apps" / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    env_example = (root / ".env.example").read_text(encoding="utf-8")

    for service in ("db:", "redis:", "migrate:", "backend:", "frontend:"):
        assert service in compose

    # Local startup must not require an .env file before Compose can parse.
    assert "${DB_PASSWORD:?" not in compose
    assert "${DB_PASSWORD:-buildtrack-local-dev-only}" in compose

    # Host-facing defaults are reserved for BuildTrack so they do not collide
    # with the user's other local systems. Container-internal ports stay native.
    assert '"8004:8000"' in compose
    assert '"3004:3000"' in compose
    assert "BACKEND_PORT" not in compose
    assert "FRONTEND_PORT" not in compose
    assert "PUBLIC_APP_URL: ${PUBLIC_APP_URL:-http://localhost:3004}" in compose
    assert "CORS_ORIGINS: ${CORS_ORIGINS:-http://localhost:3004}" in compose
    assert "BACKEND_PORT=" not in env_example
    assert "FRONTEND_PORT=" not in env_example

    # Startup order is database -> migration -> backend health -> frontend.
    assert "condition: service_healthy" in compose
    assert "condition: service_completed_successfully" in compose
    assert '["alembic", "upgrade", "head"]' in compose
    assert "/health/ready" in compose
    assert "BUILDTRACK_BACKEND_URL" in compose

    assert 'CMD ["uvicorn", "app.main:app"' in backend_dockerfile
    assert 'CMD ["node", "server.js"]' in frontend_dockerfile
    assert 'output: "standalone"' in (root / "apps" / "frontend" / "next.config.ts").read_text(encoding="utf-8")

    assert "docker compose up --build" in readme
    assert "No `.env` file is required for local development" in readme
    assert "http://localhost:3004" in readme
    assert "http://localhost:8004/docs" in readme
