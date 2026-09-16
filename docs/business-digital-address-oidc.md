# Business Digital Address OIDC registration

Business Digital Address is a first-party Ithute Auth interactive client.

- Client ID: `business-digital-address`
- Name: `Business Digital Address`
- Current production callback: `https://business.ithute.co.ls/api/auth/callback`
- Local development callback: `http://localhost:3000/api/auth/callback`

The `business.ithute.co.ls` hostname is an interim deployment hostname until the dedicated Business Digital Address domain is acquired. The product stores its public portal URL and official business-email domain as database-backed runtime configuration so the product itself does not need a code rewrite when the final domain is introduced. Ithute Auth redirect matching remains exact, so the Auth application registration must be updated operationally when that final hostname changes.

Remote HTTP callbacks are not permitted by Ithute Auth; localhost HTTP is allowed only for local development.

The registration is also added through repository-owned defaults in `Settings.client_map` and `Settings.redirect_uris` so an older production environment override cannot accidentally omit this first-party product.
