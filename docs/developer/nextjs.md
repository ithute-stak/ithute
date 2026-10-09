# Integrating Next.js App Router

The source package is `packages/ithute-auth-nextjs`. It is **not published to npm**. Integrate from the checked-out Ithute repository or approved workspace; do not assume `npm install @ithute/auth-nextjs` works publicly.

## Required environment variables

```dotenv
ITHUTE_AUTH_ISSUER=https://YOUR-APPROVED-ISSUER
ITHUTE_AUTH_CLIENT_ID=your-registered-client-id
ITHUTE_AUTH_CALLBACK_URL=https://your-app.example/api/auth/ithute/callback
ITHUTE_AUTH_SESSION_SECRET=GENERATE-A-UNIQUE-SECRET-OF-AT-LEAST-32-BYTES
```

Do **not** use `NEXT_PUBLIC_` for any of these values.

## Server-only wrapper

```ts
// lib/ithute-auth.ts
import { createIthuteAuth } from "@ithute/auth-nextjs";

export const auth = createIthuteAuth({
  issuer: process.env.ITHUTE_AUTH_ISSUER!,
  clientId: process.env.ITHUTE_AUTH_CLIENT_ID!,
  callbackUrl: process.env.ITHUTE_AUTH_CALLBACK_URL!,
  secret: process.env.ITHUTE_AUTH_SESSION_SECRET!,
});
```

## Route handlers

```ts
// app/api/auth/ithute/[action]/route.ts
import { NextRequest } from "next/server";
import { auth } from "@/lib/ithute-auth";

type Ctx = { params: Promise<{ action: string }> };
export async function GET(req: NextRequest, ctx: Ctx) {
  const { action } = await ctx.params;
  if (action === "login") return auth.login(req);
  if (action === "callback") return auth.callback(req);
  return new Response("Not found", { status: 404 });
}
export async function POST(req: NextRequest, ctx: Ctx) {
  const { action } = await ctx.params;
  if (action === "logout") return auth.logout(req);
  return new Response("Not found", { status: 404 });
}
```

Use `await auth.requireSession()` for protected server routes and `await auth.getSession()` to read the current session. Enforce application roles and tenancy separately. Logout requires a same-origin POST request with an Origin header; if central revocation is unavailable the handler returns an error and clears local cookies.

See the SDK's `README.md` and tests for implementation details. Browser integration testing using a newly created client must be completed before production enablement.
