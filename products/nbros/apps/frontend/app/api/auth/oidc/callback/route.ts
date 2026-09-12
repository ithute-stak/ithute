import { cookies } from "next/headers";
import { createRemoteJWKSet, jwtVerify } from "jose";
import { NextRequest, NextResponse } from "next/server";

import { authIssuer, clientId, cookieSecure, discovery, publicUrl, redirectUri } from "@/lib/oidc";

type TokenResponse = {
  access_token: string;
  refresh_token: string;
  id_token?: string;
  expires_in: number;
};

function authError(code: string) {
  return NextResponse.redirect(new URL(`/?auth_error=${encodeURIComponent(code)}`, publicUrl()));
}

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const returnedState = request.nextUrl.searchParams.get("state");
  const store = await cookies();
  const verifier = store.get("nbros_oidc_verifier")?.value;
  const expectedState = store.get("nbros_oidc_state")?.value;
  const expectedNonce = store.get("nbros_oidc_nonce")?.value;

  if (!code || !returnedState || !verifier || !expectedState || !expectedNonce || returnedState !== expectedState) {
    return authError("invalid_callback");
  }

  const oidc = await discovery();
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: clientId(),
    code,
    redirect_uri: redirectUri(),
    code_verifier: verifier,
  });
  const tokenResponse = await fetch(oidc.token_endpoint, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
    cache: "no-store",
  });
  if (!tokenResponse.ok) {
    return authError("token_exchange_failed");
  }

  const tokens = (await tokenResponse.json()) as TokenResponse;
  if (!tokens.id_token) {
    return authError("id_token_missing");
  }

  const jwks = createRemoteJWKSet(new URL(oidc.jwks_uri));
  const verified = await jwtVerify(tokens.id_token, jwks, {
    issuer: authIssuer(),
    audience: clientId(),
    algorithms: ["RS256"],
  });
  if (verified.payload.nonce !== expectedNonce || !verified.payload.sub) {
    return authError("id_token_invalid");
  }

  const response = NextResponse.redirect(new URL("/", publicUrl()));
  const secure = cookieSecure();
  response.cookies.set("nbros_access", tokens.access_token, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: Math.max(60, Number(tokens.expires_in) || 600),
  });
  response.cookies.set("nbros_refresh", tokens.refresh_token, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: 30 * 24 * 60 * 60,
  });
  response.cookies.delete("nbros_oidc_verifier");
  response.cookies.delete("nbros_oidc_state");
  response.cookies.delete("nbros_oidc_nonce");
  return response;
}
