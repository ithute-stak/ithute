# Ithute

Ithute is a **standalone platform repository**. It is no longer a monorepo of application products.

The repository has one clear responsibility: operate the Ithute website and the shared Ithute platform services that belong to Ithute itself.

## Active architecture

- `apps/frontend` — the public `ithute.co.ls` website. It is a small standalone Next.js application with no embedded product routes.
- `platform/ithute-auth` — central identity and authentication.
- `platform/ithute-push` — central push-notification infrastructure.
- `platform/ithute-realtime` — central realtime infrastructure.
- `infrastructure/ithute-edge` — deterministic routing only for Ithute-owned hostnames.
- `docker-compose.ithute-edge.yml` — production edge and public website deployment.

Application systems belong in their own repositories, with their own frontend, backend, database, CI/CD and deployment lifecycle. They may authenticate against Ithute Auth, but their application code is not nested here.

## Public routing contract

| Hostname | Owner in this repository | Upstream |
| --- | --- | --- |
| `ithute.co.ls` | Ithute web | `ithute-web:3000` |
| `www.ithute.co.ls` | Redirect | `https://ithute.co.ls` |
| `auth.ithute.co.ls` | Ithute Auth | `ithute-auth:8080` |
| `push.ithute.co.ls` | Ithute Push | `ithute-push:8080` |
| `realtime.ithute.co.ls` | Ithute Realtime | `ithute-realtime:8080` |

Unknown HTTPS hostnames return `404`; they cannot fall through to another application.

## Local website

```bash
cd apps/frontend
npm ci
npm run dev
```

Open `http://localhost:3000`.

Before committing frontend changes:

```bash
npm run check
npm run build
```

## Production safety

The production workflow builds an immutable `ghcr.io/ithute-stak/ithute-web:<commit>` image and deploys only the Ithute edge project. It does **not** recreate application databases or application containers.

The deploy verification rejects a release when:

- `ithute.co.ls` renders content from another system;
- the Ithute routing marker header is missing;
- the generated Next.js stylesheet cannot be fetched as `text/css`; or
- the homepage does not contain the expected Ithute identity marker.

Existing TLS volumes and the existing central-platform Docker network are reused during the routing transition so certificate and identity data are not destroyed.
