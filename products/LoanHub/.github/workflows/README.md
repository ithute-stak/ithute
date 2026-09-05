# Workflows

GitHub Actions validation and production deployment workflows.

## Release model

Pull requests to `main` run the LoanHub quality gate only. A merge/push to `main` must pass the same gate before production images are published and the VPS is touched.

The production workflow then:

1. Builds `ghcr.io/lelefe-dc/loanhub-backend` and `ghcr.io/lelefe-dc/loanhub-frontend`.
2. Publishes both `latest` and immutable commit-SHA tags.
3. Copies `compose.yaml` and the Caddyfile to the VPS.
4. Pulls the exact commit-SHA images on the VPS.
5. Uses Dockerized PostgreSQL and Redis, creates a pre-migration PostgreSQL backup, runs Alembic, and starts the application with `--no-build`.
6. Verifies backend/frontend container health and the public HTTPS endpoints.

Required repository Actions secrets are `VPS_USER`, `VPS_SSH_KEY`, `VPS_APP_DIR`, `GHCR_USERNAME`, and `GHCR_TOKEN`. `VPS_SSH_PASSPHRASE` is optional for encrypted SSH keys.

## Engineering rules

- Keep tenant and branch access checks on the backend.
- Do not commit secrets, generated caches or runtime uploads.
- Keep user-facing labels readable; database UUIDs are internal identifiers.
- Add or update tests and documentation when behaviour changes.
- Run the project validation workflow before deployment.

## Related documentation

See the repository root `README.md` and `docs/HOSTINGER_GITHUB_DEPLOYMENT.md` for architecture, security, roles and the current Cloudflare/GHCR/VPS deployment procedure.
