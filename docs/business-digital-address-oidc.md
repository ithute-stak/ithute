# Business Digital Address OIDC registration

Business Digital Address is a first-party Ithute Auth interactive client.

- Client ID: `business-digital-address`
- Name: `Business Digital Address`
- Production callback: `https://business.ls/api/auth/callback`
- Local development callback: `http://localhost:3000/api/auth/callback`

Redirect matching remains exact. Remote HTTP callbacks are not permitted by Ithute Auth; localhost HTTP is allowed only for local development.

The registration is also added through repository-owned defaults in `Settings.client_map` and `Settings.redirect_uris` so an older production environment override cannot accidentally omit this first-party product.
