# CapitalBridge ONE as an Ithute Auth relying party

Client ID: `capitalbridge`; issuer: `https://auth.ithute.co.ls`.

This change registers the *public client ID* only. It does **not** register a callback automatically, enable sign-in, share databases, create user memberships, or deploy the service.

Before activation, an operator must add the exact, verified HTTPS callback for CapitalBridge to the existing `AUTH_REDIRECT_URIS_JSON` configuration under the `capitalbridge` client ID. Do not guess the CapitalBridge public hostname or introduce wildcard redirects. Existing client redirects must be retained when changing the JSON configuration.

CapitalBridge uses Authorization Code + PKCE (S256), validated state and nonce, the Auth issuer's JWKS, and local immutable `(iss, sub)` mapping to its own users. Never trust only an email address for account linking. Company memberships and finance roles remain in CapitalBridge PostgreSQL.

A central account does not automatically grant access to CapitalBridge; the locally registered identity and company membership must be present. Existing OAuth features (including MFA and passkeys) remain owned by Ithute Auth.
