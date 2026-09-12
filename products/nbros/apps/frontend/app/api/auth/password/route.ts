import { NextRequest, NextResponse } from "next/server";

import { authIssuer, clientId, cookieSecure, discovery, publicUrl } from "@/lib/oidc";

type TokenResponse = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};

type ErrorPayload = {
  detail?: string;
};

function redirectWithError(code: string): NextResponse {
  const response = NextResponse.redirect(
    new URL(`/?auth_error=${encodeURIComponent(code)}`, publicUrl()),
    303,
  );
  response.headers.set("Cache-Control", "no-store");
  return response;
}

function setSessionCookies(response: NextResponse, tokens: TokenResponse) {
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

async function centralLoginEndpoint(): Promise<string> {
  try {
    const oidc = await discovery();
    if (oidc.password_login_endpoint) return oidc.password_login_endpoint;
  } catch {
    // Direct first-party login remains available even if discovery has a
    // transient failure. The request still goes only to the configured issuer.
  }
  return `${authIssuer()}/v1/auth/login`;
}

export async function POST(request: NextRequest) {
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return redirectWithError("missing_credentials");
  }

  const identifier = String(form.get("identifier") ?? "").trim();
  const password = String(form.get("password") ?? "");
  const mfaCode = String(form.get("mfa_code") ?? "").trim();
  if (!identifier || !password || identifier.length > 320 || password.length > 128) {
    return redirectWithError("missing_credentials");
  }

  let authResponse: Response;
  try {
    authResponse = await fetch(await centralLoginEndpoint(), {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "user-agent": request.headers.get("user-agent") ?? "NBros",
      },
      body: JSON.stringify({
        identifier,
        password,
        client_id: clientId(),
        ...(mfaCode ? { mfa_code: mfaCode } : {}),
      }),
      cache: "no-store",
    });
  } catch {
    return redirectWithError("auth_unavailable");
  }

  if (!authResponse.ok) {
    let detail = "";
    try {
      detail = ((await authResponse.json()) as ErrorPayload).detail ?? "";
    } catch {
      // Keep a generic error if Central Auth did not return JSON.
    }
    if (authResponse.status === 429) return redirectWithError("too_many_attempts");
    if (authResponse.status === 401 && detail.toLowerCase().includes("mfa")) {
      return redirectWithError("mfa_required");
    }
    if (authResponse.status === 401) return redirectWithError("invalid_credentials");
    return redirectWithError("auth_unavailable");
  }

  let tokens: TokenResponse;
  try {
    tokens = (await authResponse.json()) as TokenResponse;
  } catch {
    return redirectWithError("auth_response_invalid");
  }
  if (!tokens.access_token || !tokens.refresh_token) {
    return redirectWithError("auth_response_invalid");
  }

  const response = NextResponse.redirect(new URL("/fleet", publicUrl()), 303);
  setSessionCookies(response, tokens);
  return response;
}
