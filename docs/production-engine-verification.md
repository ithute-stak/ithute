# Verify Ithute production engines

This operator-only check runs **read-only** inside the deployed Python API container. It reports whether Python can load the Rust and C++ native libraries and reach the Go and Java workers through their internal Compose network.

From the Ithute deployment directory, after a normal approved release:

```bash
bash scripts/verify-production-engines.sh
```

By default, the command reads `compose.production.yml` and `.env.production`. Override paths with `ITHUTE_COMPOSE_FILE` and `ITHUTE_ENV_FILE` if your deployment uses different names. Docker Compose and permission to inspect the deployed stack are required.

The command returns a nonzero exit status if any specialist engine is unavailable or Python is no longer authoritative. It does not restart containers, change configuration, print secrets, or deploy images. A green CI run is **not** a substitute for executing this on the production host.

If an engine fails, inspect the worker container health, backend image native library paths, engine routing URLs, and current release image tag before making an approved change. Do not report production verification as successful until the host-side command completes successfully.
