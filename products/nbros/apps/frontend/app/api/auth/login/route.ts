import { createHash, randomBytes } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

import { clientId, cookieSecure, discovery, publicUrl, redirectUri } from "@/lib/oidc";

function randomUrlSafe(bytes = 32): string {
  return randomBytes(bytes).toString("base64url");
}

export async function GET(_request: NextRequest) {
  const codeVerifier = randomUrlSafe(32);
  const codeChallenge = createHash("sha256").update(codeVerifier).digest("base64url");
  const state = randomUrlSafe(32);
  const nonce = randomUrlSafe(32);

  let oidc;
  try {
    oidc = await discovery();
  } catch {
    const response = NextResponse.redirect(new URL("/?auth_error=auth_unavailable", publicUrl()));
    response.headers.set("Cache-Control", "no-store");
    return response;
  }

  const url = new URL(oidc.authorization_endpoint);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", clientId());
  url.searchParams.set("redirect_uri", redirectUri());
  url.searchParams.set("code_challenge", codeChallenge);
  url.searchParams.set("code_challenge_method", "S256");
  url.searchParams.set("scope", "openid profile email phone");
  url.searchParams.set("state", state);
  url.searchParams.set("nonce", nonce);

  const response = NextResponse.redirect(url);
  const cookieOptions = { httpOnly: true, secure: cookieSecure(), sameSite: "lax" as const, path: "/", maxAge: 600 };
  response.cookies.set("nbros_oidc_verifier", codeVerifier, cookieOptions);
  response.cookies.set("nbros_oidc_state", state, cookieOptions);
  response.cookies.set("nbros_oidc_nonce", nonce, cookieOptions);
  response.headers.set("Cache-Control", "no-store");
  return response;
}
