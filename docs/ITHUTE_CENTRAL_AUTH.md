# Mailbox DNS -> !thute Auth migration

Mailbox DNS keeps its own PostgreSQL database and all product authorization. The central identity service proves who the user is; Mailbox DNS still decides which tenants, mailboxes, DNS zones, hosting resources and administration actions that user may access.

## Runtime configuration

Central authentication is disabled by default. Enable it only after `auth.ithute.co.ls` is deployed and existing accounts can be deliberately linked.

```env
ITHUTE_AUTH_ENABLED=false
ITHUTE_AUTH_ISSUER=https://auth.ithute.co.ls
ITHUTE_AUTH_AUDIENCE=mailbox-dns
ITHUTE_AUTH_JWKS_URL=https://auth.ithute.co.ls/.well-known/jwks.json
```

`ITHUTE_AUTH_JWKS_URL` may be omitted because the backend derives it from the issuer.

## Security boundary

- The product database stores only `users.auth_user_id`, the immutable central `sub` UUID.
- There is no foreign key, shared table, or database connection to `ithute_auth`.
- Existing Mailbox DNS HS256 sessions remain valid during migration and retain local `session_version` revocation.
- Central tokens must be RS256, issued by `https://auth.ithute.co.ls`, have `aud=mailbox-dns`, `token_use=access`, and valid `sub`, `sid`, `iat`, `nbf`, and `exp` claims.
- Central tokens do not grant tenant roles, mailbox access, DNS permissions or platform-owner status. Those remain local.
- Linking requires a current Mailbox DNS session, the current Mailbox DNS password, and a valid central token.
- Unlinking requires the current Mailbox DNS session and password.

## Migration order

1. Deploy the schema addition with central auth disabled.
2. Deploy `auth.ithute.co.ls` and its JWKS endpoint.
3. Enable central verification in a controlled environment.
4. Link existing users after they prove control of both accounts.
5. Observe login/audit behavior before considering retirement of product-local credentials.

Do not bulk-link accounts solely by matching unverified email addresses or phone numbers.
