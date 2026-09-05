# !thute Auth operations runbook

`!thute Auth` is the central identity boundary for Ithute Solutions products. An Auth outage can prevent new logins across products, so changes must preserve existing sessions where possible and must never expose the Auth database or private signing keys to product applications.

## Service ownership

- Public issuer: `https://auth.ithute.co.ls`
- API/container service: `ithute-auth`
- Database: `ithute-auth-db` / `ithute_auth`
- Signing keys: mounted read-only under `/run/secrets`
- MFA secret encryption: `AUTH_TOTP_ENCRYPTION_KEY`
- Product identity key: immutable JWT/OIDC `sub`

Products verify short-lived access tokens locally with JWKS. Product business data, roles, permissions, organizations, subscriptions and transactions remain in each product database.

## Health checks

The following must return HTTP 200:

```text
/healthz
/.well-known/openid-configuration
/.well-known/jwks.json
```

Prometheus probes the first two through the blackbox exporter. `IthuteAuthUnavailable` is critical after two minutes.

When Auth is unavailable, check in this order:

1. `ithute-auth` container health and logs.
2. `ithute-auth-db` PostgreSQL health.
3. Alembic migration state.
4. Presence/readability of JWT private/public key mounts.
5. `AUTH_TOTP_ENCRYPTION_KEY` presence and format.
6. reverse-proxy/DNS/TLS routing for `auth.ithute.co.ls`.
7. the latest deployment diff.

Do not rotate keys, reset databases or recreate users as a first response to an availability incident.

## Database backup and restore

When `ITHUTE_AUTH_DB_PASSWORD` is configured in the Phase 11 backup stack, every encrypted Restic backup includes `db/ithute-auth.dump` and records its SHA-256 checksum in `manifest.json`.

Restore drills restore the Auth dump into the isolated `mailbox_restore_auth` database and require at least one public table. A failed Auth restore makes the drill fail.

The Auth PostgreSQL data volume is not a substitute for an encrypted logical backup. Keep off-site Restic credentials independent from the Auth database credentials.

## Signing-key rotation

1. Generate a new RSA private/public key pair outside the repository.
2. Record the currently published public JWK from `/.well-known/jwks.json`.
3. Add the retiring public JWK to `AUTH_PREVIOUS_JWKS_JSON`.
4. Change `AUTH_JWT_KEY_ID` to a new unique key ID.
5. Replace the mounted private/public key pair atomically.
6. Deploy Auth.
7. Confirm JWKS publishes the new current key and the retained old public key.
8. Confirm a token signed with the retiring key remains accepted during the overlap period.
9. Keep the retired public JWK longer than the maximum lifetime of every token/cookie signed by that key.
10. Remove the retired JWK only after that overlap period has elapsed.

Never reuse a `kid` for different RSA key material. Never place private key material in `AUTH_PREVIOUS_JWKS_JSON`.

## Suspected signing-key compromise

A compromise is different from routine rotation. Replace the signing key immediately, remove the compromised public key from the accepted rollover set, increment/revoke affected sessions as operationally appropriate, and require reauthentication. Review `audit_events` for suspicious authentication and administrative activity.

## MFA encryption key

TOTP secrets are encrypted at rest with Fernet using `AUTH_TOTP_ENCRYPTION_KEY`.

- Store this value in the production secret store, not Git.
- Back it up independently with restricted access.
- Losing it makes existing encrypted TOTP secrets unreadable.
- If it is compromised, rotate it through a controlled re-encryption procedure; do not simply replace it while encrypted secrets still depend on the old key.

Recovery codes are stored only as hashes and cannot be recovered. Users regenerate a new set after authenticating with TOTP.

## Account lockout

Repeated password or MFA failures temporarily lock an account according to:

- `AUTH_MAX_LOGIN_FAILURES`
- `AUTH_LOGIN_LOCK_MINUTES`

A platform admin may clear the lock through the protected admin API. Never disclose whether an unknown email/phone exists during password-reset requests or failed login responses.

## Password reset and verification delivery

Email delivery uses the `AUTH_SMTP_*` settings. Phone verification/recovery uses the provider-neutral HTTPS SMS webhook configured by `AUTH_SMS_WEBHOOK_URL` and `AUTH_SMS_WEBHOOK_TOKEN`.

Password-reset tokens are random, one-time, expiry-bound and stored only as SHA-256 hashes. Verification codes are user-bound before hashing so the same six-digit code cannot authenticate another account.

If delivery is unavailable, restore the provider configuration rather than exposing reset tokens through logs or API responses.

## Emergency session revocation

Users can revoke their own sessions. Platform admins can revoke sessions for a target user. Disabling an Ithute application revokes its active central sessions.

Password resets revoke all sessions. Password changes and MFA changes revoke other sessions and increment the user's `security_version`, invalidating older central browser SSO cookies.

Because product APIs validate short-lived access tokens offline, an already-issued access token can remain cryptographically valid until its short expiry even after central session revocation. Keep access-token lifetimes short; do not compensate by sharing the Auth database with products.

## Platform administrator bootstrap

There is no default platform-admin password or hidden administrator account.

After creating and verifying a normal central Auth user, run inside the trusted Auth environment:

```bash
python scripts/grant_platform_admin.py user@example.com
```

Revoke the privilege with:

```bash
python scripts/grant_platform_admin.py user@example.com --revoke
```

Platform-admin actions are written to the Auth audit log.

## Product registration

First-party product IDs are explicit. Current intended products include:

- `loanhub`
- `rsl-pos`
- `mailbox-dns`
- `ithute-account`
- `ithute-tutor`

Browser/mobile callbacks must be exact-match entries in `AUTH_REDIRECT_URIS_JSON`. Production callbacks use HTTPS. Wildcards are not accepted.

## Incident evidence

Preserve these before destructive remediation when possible:

- Auth container logs
- reverse-proxy access/error logs
- `audit_events`
- affected user/session IDs
- deployment commit SHA
- PostgreSQL health and migration state
- Prometheus/Alertmanager timeline

Do not log passwords, refresh tokens, reset tokens, TOTP secrets, recovery codes, private signing keys or MFA encryption keys.
