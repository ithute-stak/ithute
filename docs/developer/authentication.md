# Authentication and OAuth

Ithute Auth is a central identity service. A developer account alone does **not** grant permission to create or activate OAuth applications.

## Available endpoints

- `GET /.well-known/openid-configuration`: discovery metadata.
- `GET /.well-known/jwks.json`: public signing keys.
- `GET /oauth/authorize`: authorization-code + PKCE authorization.
- `POST /oauth/token`: code exchange and refresh-token grant.
- `GET /v1/account/session-status`: authenticated, online session verification.
- `POST /v1/account/sessions/revoke-current`: revoke the bearer token's current central session.

The endpoint paths are relative to the configured central Ithute Auth issuer, **not necessarily** `https://ithute.co.ls`. Use the issuer shown in your approved integration settings.

## Register an OAuth application

Ask an authorized Ithute platform administrator to create a disabled application under Ithute Auth & Push, register exact HTTPS redirect URLs, review permissions and enable it. Use a unique client ID. Do not use wildcards, query-string tricks or local development callbacks in production.

## Authorization-code flow

Generate cryptographically random `state`, a PKCE code verifier/challenge (S256), and a nonce where applicable. Redirect to the issuer authorization endpoint using the approved client ID and exact redirect URI. On callback, validate state and exchange the code server-side. Validate the JWT signature, issuer, audience and expiry using the issuer JWKS. Enforce roles and tenant permissions in your own server application.

## Revocation and availability

The Next.js SDK checks central session status. Revocation or application disablement invalidates that central session on subsequent online checks. Ithute Auth unavailability fails closed; account for this in user experience and monitoring.

Refresh-token rotation is supported by central Auth; safe automatic renewal in the Next.js SDK is separately under development. Never expose refresh tokens to browser JavaScript.
