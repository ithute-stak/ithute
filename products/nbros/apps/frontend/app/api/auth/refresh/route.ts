import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { clientId, cookieSecure, discovery, publicUrl } from "@/lib/oidc";

type RefreshTokenResponse = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};

function safeReturnPath(request: NextRequest): string {
  const candidate = request.nextUrl.searchParams.get("return");
  if (!candidate || !candidate.startsWith("/") || candidate.startsWith("//")) return "/fleet";
  return candidate;
}

async function rotateSession(): Promise<
  | { ok: true; tokens: RefreshTokenResponse }
  | { ok: false; status: number; detail: string }
> {
  const store = await cookies();
  const refreshToken = store.get("nbros_refresh")?.value;
  if (!refreshToken) {
    return { ok: false, status: 401, detail: "refresh token unavailable" };
  }

  let oidc;
  try {
    oidc = await discovery();
  } catch {
    return { ok: false, status: 503, detail: "central auth discovery unavailable" };
  }

  const tokenResponse = await fetch(oidc.token_endpoint, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: clientId(),
      refresh_token: refreshToken,
    }),
    cache: "no-store",
  });

  if (!tokenResponse.ok) {
    return { ok: false, status: 401, detail: "central auth refresh rejected" };
  }

  const tokens = (await tokenResponse.json()) as RefreshTokenResponse;
  if (!tokens.access_token || !tokens.refresh_token) {
    return { ok: false, status: 502, detail: "central auth refresh response invalid" };
  }
  return { ok: true, tokens };
}

function setSessionCookies(response: NextResponse, tokens: RefreshTokenResponse) {
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
  response.headers.set("Cache-Control", "no-store");
}

function clearSessionCookies(response: NextResponse) {
  response.cookies.delete("nbros_access");
  response.cookies.delete("nbros_refresh");
  response.headers.set("Cache-Control", "no-store");
}

export async function POST() {
  const result = await rotateSession();
  if (!result.ok) {
    const response = NextResponse.json({ detail: result.detail }, { status: result.status });
    if (result.status === 401) clearSessionCookies(response);
    return response;
  }

  const response = NextResponse.json({
    status: "refreshed",
    expires_in: result.tokens.expires_in,
  });
  setSessionCookies(response, result.tokens);
  return response;
}

export async function GET(request: NextRequest) {
  const result = await rotateSession();
  if (!result.ok) {
    const response = NextResponse.redirect(new URL("/api/auth/login", publicUrl()));
    clearSessionCookies(response);
    return response;
  }

  const response = NextResponse.redirect(new URL(safeReturnPath(request), publicUrl()));
  setSessionCookies(response, result.tokens);
  return response;
}
