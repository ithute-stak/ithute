# Product integration contract

All Ithute Solutions products authenticate against `https://auth.ithute.co.ls` and keep their business data in their own databases.

## Identity link

Each product should add an immutable nullable column during migration:

```text
auth_user_id UUID
```

After an account is linked, `auth_user_id` contains the OIDC/JWT `sub` from !thute Auth. Do not reuse email or phone as the cross-product primary identity because those values can change.

Current first-party client IDs include:

```text
loanhub
rsl-pos
mailbox-dns
ithute-account
ithute-tutor
ithute-pay
```

Each product validates only tokens whose `aud` is its own client ID.

## Browser/mobile SSO

First-party clients use OpenID Connect Authorization Code + PKCE with `S256`.

1. Generate a cryptographically random `code_verifier` between 43 and 128 unreserved ASCII characters.
2. Compute `code_challenge = BASE64URL(SHA256(code_verifier))` without `=` padding.
3. Generate independent unpredictable `state` and `nonce` values and store both in the initiating product session.
4. Redirect the browser to the `authorization_endpoint` from `/.well-known/openid-configuration` with:
   - `response_type=code`
   - the product `client_id`
   - the exact registered `redirect_uri`
   - `code_challenge`
   - `code_challenge_method=S256`
   - `scope=openid profile email phone`
   - `state`
   - `nonce`
5. On the callback, reject the response unless returned `state` exactly matches the initiating session.
6. POST the returned `code`, original `code_verifier`, same `client_id`, same `redirect_uri`, and `grant_type=authorization_code` to the discovered `token_endpoint`.
7. Validate the returned ID token using JWKS: RS256 signature, exact issuer, product audience, expiry, immutable `sub`, and exact `nonce` match with the initiating session.
8. Store refresh tokens only in an HttpOnly server-side/browser-session boundary appropriate to the product. Do not expose refresh tokens to page JavaScript when a backend-for-frontend pattern is available.

Authorization codes are one-time, short-lived, stored only as SHA-256 hashes, and row-locked during exchange to prevent concurrent replay. Redirect URIs are exact-match allowlisted by Auth. Wildcards are not supported. Production callbacks use HTTPS; plain HTTP is limited to actual localhost/127.0.0.1/::1 development hosts.

The signed `ithute_sso` browser cookie belongs only to `auth.ithute.co.ls`. Product applications must not read or recreate that cookie. Password or MFA changes can invalidate that central cookie by increasing the user's Auth security version.

## Passkeys

`!thute Auth` also supports WebAuthn/passkeys. Products do not store credential public keys or WebAuthn sign counters themselves; those belong to the central identity service.

For a native or product-managed passkey login:

1. Request authentication options from `POST /v1/auth/passkey/options?client_id=<product-client-id>`.
2. Pass the returned public-key options to the platform WebAuthn API (`navigator.credentials.get()` on the web or the equivalent native API).
3. POST the returned credential plus `challenge_id` and the same product `client_id` to `/v1/auth/passkey/verify`.
4. Auth verifies the one-time challenge, `auth.ithute.co.ls` relying-party ID, exact origin, user verification, credential public key and signature counter.
5. On success, Auth returns the same product-audience access/refresh-token contract used by password-based login.

Browser products may continue to prefer OIDC + PKCE and let the central Auth site decide whether the user signs in with password/MFA or a passkey. A product must never collect or store biometric data; WebAuthn user verification happens inside the authenticator/device.

## Access-token validation

A product API must:

1. Read the issuer from `/.well-known/openid-configuration`.
2. Resolve signing keys from `/.well-known/jwks.json`.
3. Verify the RS256 signature using the JWT `kid`; accept retained public keys published during an announced signing-key rollover until their tokens expire.
4. Require `iss=https://auth.ithute.co.ls`.
5. Require its own exact `aud` (`loanhub`, `rsl-pos`, `mailbox-dns`, `ithute-tutor`, `ithute-pay`, etc.).
6. Require a non-expired `exp`.
7. Require `token_use=access`.
8. Use `sub` only as the centralized identity key.

Products must not receive the Auth database password, JWT private key, MFA encryption key, service-client secrets or passkey credential private material. Products must not query the Auth database directly.

## Authorization boundary

!thute Auth answers **who the user is**.

Each product remains responsible for **what that user may do**. Roles, company memberships, schools, branches, permissions, product subscriptions and business policies remain in the product database.

For example, `ithute-tutor` stores Tutor-specific learner, teacher, school, course, subscription and authorization records in the Tutor database while linking the local profile to the central `sub` through `auth_user_id`. `ithute-pay` similarly keeps merchant, payment, provider, ledger, settlement and financial authorization data in the Ithute Pay database.

## Migration safety

During product migration:

- keep the existing local login available behind a temporary migration flag where a legacy login already exists;
- add `auth_user_id` without deleting old user rows;
- link an existing local account only after proving control of both identities through the product's audited link flow;
- protect link initiation as a state-changing action (for browser products, require the product's CSRF boundary before redirecting to Auth);
- switch product API authentication to central JWT verification;
- add Authorization Code + PKCE callbacks before making SSO the default login path;
- only after successful rollout, retire local password/session creation.

Never merge user accounts solely because display names, email addresses or phone numbers look similar.

## Push boundary

!thute Auth owns user and service identity. The separate `!thute Push` service owns FCM/APNs/Web-Push provider tokens, message queues, retry state and delivery receipts.

Product backends request a central service token with:

```text
iss=https://auth.ithute.co.ls
aud=ithute-push
token_use=service
azp=<product client id>
scope=push.send
```

Products publish notification requests to Push rather than calling FCM/APNs directly. Push never reads a product's business database.
