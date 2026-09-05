# !thute Auth

`!thute Auth` is the centralized identity and single-sign-on service for applications owned by Ithute Solutions.

## Platform rule

- Every Ithute product keeps its own database and migrations.
- Products never read another product database directly.
- `!thute Auth` owns identity only: users, credentials, passkeys, MFA, central sessions, first-party application registrations, recovery and device identity.
- Product roles, permissions, companies, transactions, messages, subscriptions and other business records remain in each product database.
- Products link their local user/profile row to the immutable OIDC `sub` issued by this service.

Issuer:

```text
https://auth.ithute.co.ls
```

First-party audiences:

```text
loanhub
rsl-pos
mailbox-dns
ithute-account
ithute-tutor
```

## Security capabilities

The central identity service provides:

- RS256 access and ID tokens with published JWKS.
- Authorization Code + PKCE (`S256`) for browser/mobile SSO.
- rotating refresh tokens and centrally revocable sessions.
- encrypted TOTP MFA secrets and one-time hashed recovery codes.
- password recovery plus email/phone verification delivery adapters.
- WebAuthn/passkeys with discoverable credentials and required user verification.
- account lockout and IP-based failed-login throttling.
- immutable security audit events for login, recovery, MFA, passkey and administrative activity.
- signing-key rollover with retained public keys until old tokens expire.
- central account and platform-admin web portals.

A password or MFA security change increments the user's security version, revokes applicable product sessions and invalidates older central browser SSO cookies.

## Web portals

- `/account/login` — central password + MFA sign-in.
- `/account/passkey-login` — central passwordless passkey sign-in.
- `/account` — profile/security dashboard, verification, MFA, sessions and audit history.
- `/account/passkeys` — register, inspect and remove passkeys.
- `/admin` — platform-admin user and first-party application controls.

Platform-admin privilege is never granted through a default credential or public endpoint. Bootstrap it explicitly from the Auth server with the checked-in admin bootstrap command.

## API

Migration-compatible first-party endpoints remain available:

- `POST /v1/users/register`
- `POST /v1/auth/login`
- `POST /v1/auth/refresh`
- `POST /v1/auth/logout`
- `POST /v1/auth/service-token`
- `GET /v1/me`
- `POST /v1/devices`
- `DELETE /v1/devices/{device_key}`

Account-security endpoints include password recovery/change, contact verification, TOTP enrollment/recovery, session management and audit history under `/v1/account/*`.

Passkey endpoints:

- `GET /v1/account/passkeys`
- `POST /v1/account/passkeys/registration/options`
- `POST /v1/account/passkeys/registration/verify`
- `POST /v1/account/passkeys/{passkey_id}/remove`
- `POST /v1/auth/passkey/options?client_id=<product>`
- `POST /v1/auth/passkey/verify`

Passkey registration and removal require account re-authentication. When TOTP MFA is enabled, the MFA/recovery-code requirement is also enforced. Passwordless authentication requires WebAuthn user verification and is still issued into the requested first-party product audience.

Standards-based SSO endpoints:

- `GET /oauth/authorize`
- `POST /oauth/authorize`
- `POST /oauth/token`
- `POST /oauth/browser-logout`
- `GET /oauth/userinfo`
- `GET /.well-known/openid-configuration`
- `GET /.well-known/jwks.json`
- `GET /healthz`

Access tokens are short-lived RS256 JWTs. Products verify them using the published JWKS and store the token `sub` as their `auth_user_id`.

## Authorization Code + PKCE

Ithute browser/mobile clients use Authorization Code with PKCE and `S256` only.

1. The product creates a high-entropy `code_verifier` and its `S256` `code_challenge`.
2. The browser is redirected to `/oauth/authorize` with `response_type=code`, `client_id`, exact registered `redirect_uri`, `code_challenge`, `code_challenge_method=S256`, `scope`, `state` and `nonce`.
3. `!thute Auth` authenticates the user and enforces MFA when enabled. A signed HttpOnly central browser cookie lets subsequent first-party products reuse the central login session.
4. Auth creates a short-lived one-time authorization code; only its SHA-256 hash is stored.
5. Auth redirects to the exact registered product callback with `code` and the original `state`.
6. The product posts the code plus the original `code_verifier` to `/oauth/token`.
7. Auth validates the one-time code, client, redirect URI, expiry and PKCE challenge, consumes the code, and returns product-audience tokens.

Authorization codes cannot be replayed. Redirect URIs are exact-match allowlisted through `AUTH_REDIRECT_URIS_JSON`; wildcard callbacks are not supported. Production callbacks use HTTPS. Plain HTTP is accepted only for localhost/127.0.0.1 development.

Example runtime callback configuration:

```text
AUTH_REDIRECT_URIS_JSON={"ithute-tutor":["https://<tutor-host>/auth/callback"],"loanhub":["https://<loanhub-host>/auth/callback"]}
```

Do not commit production secrets, private keys, MFA encryption keys, service client secrets or recovery-provider credentials.

## WebAuthn / passkeys

Production defaults are bound to the central Auth origin:

```text
AUTH_WEBAUTHN_RP_ID=auth.ithute.co.ls
AUTH_WEBAUTHN_ORIGIN=https://auth.ithute.co.ls
```

Changing the public Auth hostname requires changing both values together. WebAuthn registration/authentication validates the server-issued one-time challenge, relying-party ID, browser origin and user-verification flag before trusting a credential.

## Service authentication for Push

Product backends obtain a short-lived service JWT from `/v1/auth/service-token`. Push accepts only the `ithute-push` audience with `token_use=service`, the product `azp`, and `scope=push.send`.

## Backup, monitoring and recovery

The platform deployment includes the Auth PostgreSQL database in encrypted backup snapshots and restore drills when its database credentials are configured. Monitoring probes both `/healthz` and OIDC discovery and raises a critical Auth-unavailable alert if the identity surface remains unreachable.

Operational recovery, key rotation, MFA encryption-key handling and emergency session-revocation procedures are documented in the Auth operations runbook.

## Local development

Generate an RSA signing key pair:

```bash
mkdir -p secrets
openssl genpkey -algorithm RSA -out secrets/jwt-private.pem -pkeyopt rsa_keygen_bits:3072
openssl rsa -pubout -in secrets/jwt-private.pem -out secrets/jwt-public.pem
```

Generate a Fernet key for TOTP-secret encryption:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the environment file, configure local redirect URIs/WebAuthn origin, and start the isolated Auth stack:

```bash
cp .env.example .env
docker compose up --build
```

The service uses its own PostgreSQL database named `ithute_auth`. It does not use the Mailbox-DNS application database or any product database.

## Product integration

See `docs/PRODUCT-INTEGRATION.md`.
