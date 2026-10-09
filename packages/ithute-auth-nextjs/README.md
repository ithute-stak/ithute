# @ithute/auth-nextjs (initial integration)

Server-only Next.js App Router OAuth 2.0 authorization-code + PKCE wrapper for the existing Ithute Auth service.

## Integration

Install the package from the repository/workspace (publishing to npm is **not** included), along with `jose`. Set server-only variables `ITHUTE_AUTH_ISSUER`, `ITHUTE_AUTH_CLIENT_ID`, `ITHUTE_AUTH_CALLBACK_URL`, and `ITHUTE_AUTH_SESSION_SECRET` (at least 32 bytes; keep secret private).

```ts
// lib/ithute-auth.ts - server only
import { createIthuteAuth } from "@ithute/auth-nextjs";
export const auth = createIthuteAuth({
  issuer: process.env.ITHUTE_AUTH_ISSUER!,
  clientId: process.env.ITHUTE_AUTH_CLIENT_ID!,
  callbackUrl: process.env.ITHUTE_AUTH_CALLBACK_URL!,
  secret: process.env.ITHUTE_AUTH_SESSION_SECRET!,
});
```

```ts
// app/api/auth/ithute/[action]/route.ts
import { NextRequest } from "next/server";
import { auth } from "@/lib/ithute-auth";
export async function GET(request: NextRequest, context: { params: Promise<{ action: string }> }) {
  const { action } = await context.params;
  if (action === "login") return auth.login(request);
  if (action === "callback") return auth.callback(request);
  return new Response("Not found", { status: 404 });
}
export async function POST(request: NextRequest, context: { params: Promise<{ action: string }> }) {
  const { action } = await context.params;
  if (action === "logout") return auth.logout(request);
  return new Response("Not found", { status: 404 });
}
```

Logout must be a same-origin POST (not a GET link), and needs the browser Origin header. The SDK does not store refresh tokens in cookies.\n\nRead sessions with `await auth.getSession()` from server components/routes. Treat authorization/roles as separate policy checks on the server. The wrapper stores encrypted, HttpOnly, Secure cookies; it does not expose tokens to client JavaScript.

**Important limitations:** This initial version does not support refresh-token rotation, remote session revocation, dashboard client registration, custom login branding or package publishing. Sessions expire at access-token expiry and require login again. Logout clears the local app session, not other Ithute Auth sessions; cross-app revocation needs a separate upstream integration. Register the OAuth client and exact redirect URI in Ithute Auth before using this example; never use a wildcard callback. Authorization-server support for PKCE, ID token nonce and issuer/audience claims must be verified in integration tests. No automatic production enablement.
