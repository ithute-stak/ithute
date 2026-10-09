# Server-side developer access requests with the Ithute Next.js SDK

The Ithute Auth Next.js wrapper now exposes `authenticatedRequest(path, init)` for making central **account-scoped** API requests from Next.js server routes. It validates the encrypted session cookie, checks the JWT signature and central session state, and attaches the bearer token only to a fixed, same-issuer account URL. **Never call this from browser code.**

## Developer application's server route

```ts
// app/api/developer/requests/route.ts (in a Next.js app with the SDK wired up)
import { auth } from "@/lib/ithute-auth";

export async function GET() {
  try {
    const upstream=await auth.authenticatedRequest("/v1/account/developer/access-requests");
    return new Response(await upstream.text(),{
      status:upstream.status,headers:{"Content-Type":"application/json","Cache-Control":"no-store"},
    });
  } catch {
    return Response.json({message:"Sign in with Ithute Auth"},{status:401});
  }
}

export async function POST(request:Request) {
  if (request.headers.get("origin")!==new URL(request.url).origin)
    return Response.json({message:"Origin rejected"},{status:403});
  const data=await request.json();
  const upstream=await auth.authenticatedRequest("/v1/account/developer/access-requests",{
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({product:data.product,justification:data.justification}),
  });
  return new Response(await upstream.text(),{
    status:upstream.status,headers:{"Content-Type":"application/json","Cache-Control":"no-store"},
  });
}
```

This is an integration example for an app that already has an approved OAuth client and a validated callback URL. The public Ithute developer dashboard is **not yet authenticated** by this commit; deployers must provision a client, integrate the SDK into the frontend and verify login/logout/browser E2E.

`authenticatedRequest` rejects non-account API paths and cross-issuer URLs. Do not log bearer tokens, expose them in JSON, or allow browsers to choose arbitrary upstream destinations. On central Auth outages it fails closed. A verified email address is required before submitting a service-access request, and administrator approval does not automatically provision access.
