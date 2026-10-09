# CapitalBridge ONE OAuth production callback

Registered client ID: `capitalbridge`
Issuer: `https://auth.ithute.co.ls`
Exact redirect URI: `https://capitalbridge.co.ls/api/v1/oidc/complete`

The user confirmed `capitalbridge.co.ls` as the CapitalBridge domain. The Auth configuration now supplies this exact URI as the default allowed redirect for `capitalbridge`. If production sets `AUTH_REDIRECT_URIS_JSON`, the override must explicitly include `capitalbridge: ["https://capitalbridge.co.ls/api/v1/oidc/complete"]`, because `setdefault` will not replace a configured client entry. Keep other product redirects unchanged.

This registration does not establish DNS/TLS ownership, route deployment, or authorization to use CapitalBridge. Do not activate sign-in until HTTPS callback routing, login/session revocation and company-membership checks are verified in a real environment.
