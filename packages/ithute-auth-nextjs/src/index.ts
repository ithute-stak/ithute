/** Server-only OAuth 2.0 Authorization Code + PKCE integration for Next.js. */
import "server-only";
import { createCipheriv, createDecipheriv, createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { createRemoteJWKSet, jwtVerify } from "jose";

type Options = { issuer: string; clientId: string; callbackUrl: string; secret: string; scopes?: string };
type Session = { accessToken: string; expiresAt: number };
const TEMP = "ithute_oauth_pending";
const SESSION = "ithute_auth_session";
const b64 = (b: Buffer) => b.toString("base64url");
const key = (secret: string) => createHash("sha256").update(secret).digest();
function seal(value: unknown, secret: string): string {
  const iv = randomBytes(12); const cipher = createCipheriv("aes-256-gcm", key(secret), iv);
  const ciphertext = Buffer.concat([cipher.update(JSON.stringify(value), "utf8"), cipher.final()]);
  return b64(Buffer.concat([iv, cipher.getAuthTag(), ciphertext]));
}
function open<T>(value: string | undefined, secret: string): T | null {
  if (!value) return null;
  try {
    const raw = Buffer.from(value, "base64url");
    if (raw.length < 29) return null;
    const decipher = createDecipheriv("aes-256-gcm", key(secret), raw.subarray(0, 12));
    decipher.setAuthTag(raw.subarray(12, 28));
    return JSON.parse(Buffer.concat([decipher.update(raw.subarray(28)), decipher.final()]).toString("utf8")) as T;
  } catch { return null; }
}
function safeReturnTo(value: string | null): string {
  return value && value.startsWith("/") && !value.startsWith("//") && !value.includes("\\") ? value : "/";
}
function assertConfig(o: Options) {
  if (new URL(o.issuer).protocol !== "https:" || new URL(o.callbackUrl).protocol !== "https:")
    throw new Error("Ithute Auth requires HTTPS issuer and callback URLs");
  if (!o.clientId || Buffer.byteLength(o.secret) < 32)
    throw new Error("Configure clientId and a strong ITHUTE_AUTH_SESSION_SECRET (at least 32 bytes)");
}
export function createIthuteAuth(options: Options) {
  assertConfig(options);
  const issuer = options.issuer.replace(/\/$/, "");
  const callback = options.callbackUrl;
  const shared = { httpOnly: true as const, secure: true, sameSite: "lax" as const, path: "/" };
  const jwks = createRemoteJWKSet(new URL(`${issuer}/.well-known/jwks.json`));
  async function login(request: NextRequest) {
    const state = b64(randomBytes(32)); const nonce = b64(randomBytes(32));
    const verifier = b64(randomBytes(48));
    const challenge = b64(createHash("sha256").update(verifier).digest());
    const returnTo = safeReturnTo(request.nextUrl.searchParams.get("returnTo"));
    const params = new URLSearchParams({ response_type:"code", client_id:options.clientId, redirect_uri:callback,
      code_challenge:challenge, code_challenge_method:"S256", state, nonce, scope:options.scopes ?? "openid profile email" });
    const response = NextResponse.redirect(`${issuer}/oauth/authorize?${params}`);
    response.cookies.set(TEMP, seal({state, nonce, verifier, returnTo, expiresAt:Date.now()+600_000}, options.secret),
      {...shared, maxAge:600});
    return response;
  }
  async function callbackHandler(request: NextRequest) {
    const pending = open<{state:string;nonce:string;verifier:string;returnTo:string;expiresAt:number}>(
      request.cookies.get(TEMP)?.value, options.secret);
    const code = request.nextUrl.searchParams.get("code");
    const returnedState = request.nextUrl.searchParams.get("state");
    if (!pending || Date.now()>pending.expiresAt || !code || !returnedState ||
        Buffer.byteLength(returnedState)!==Buffer.byteLength(pending.state) ||
        !timingSafeEqual(Buffer.from(returnedState), Buffer.from(pending.state))) {
      const response=NextResponse.json({error:"Invalid or expired authentication state"},{status:400});
      response.cookies.delete(TEMP); return response;
    }
    let tokens: {access_token:string;id_token?:string;refresh_token?:string;expires_in?:number};
    try {
      const responseFromIssuer = await fetch(`${issuer}/oauth/token`, {method:"POST",
        headers:{"Content-Type":"application/x-www-form-urlencoded"},
        body:new URLSearchParams({grant_type:"authorization_code",client_id:options.clientId,redirect_uri:callback,
          code,code_verifier:pending.verifier}), cache:"no-store",signal:AbortSignal.timeout(10000)});
      if (!responseFromIssuer.ok) throw new Error("token_exchange_rejected");
      tokens=await responseFromIssuer.json() as typeof tokens;
      if (!tokens.access_token || typeof tokens.access_token !== "string") throw new Error("missing_access_token");
      if (tokens.id_token) {
        const verified=await jwtVerify(tokens.id_token,jwks,{issuer,audience:options.clientId,algorithms:["RS256"]});
        if (verified.payload.nonce!==pending.nonce) throw new Error("invalid_id_token_nonce");
      }
    } catch {
      const failed=NextResponse.json({error:"Authentication exchange failed"},{status:401});
      failed.cookies.delete(TEMP);
      return failed;
    }
    // Do not store unnecessary refresh or identity tokens in browser cookies.
    // Session expiration is bounded by the verified access-token expiry.
    let verifiedAccess;
    try {
      verifiedAccess = await jwtVerify(tokens.access_token,jwks,{issuer,audience:options.clientId,algorithms:["RS256"]});
    } catch {
      const failed=NextResponse.json({error:"Invalid access token"},{status:401});
      failed.cookies.delete(TEMP);return failed;
    }
    const accessExpiresAt = (verifiedAccess.payload.exp ?? 0) * 1000;
    const expiresAt = Math.min(Date.now() + Math.min(Math.max(tokens.expires_in ?? 600, 1), 3600) * 1000, accessExpiresAt);
    if (expiresAt <= Date.now()) {
      const failed=NextResponse.json({error:"Expired access token"},{status:401});
      failed.cookies.delete(TEMP);return failed;
    }
    // Reject revoked sessions and disabled OAuth clients before issuing a local cookie.
    try {
      const statusResponse=await fetch(`${issuer}/v1/account/session-status`,{
        headers:{Authorization:`Bearer ${tokens.access_token}`},
        cache:"no-store",signal:AbortSignal.timeout(5000),
      });
      if (!statusResponse.ok || (await statusResponse.json() as {active?:boolean}).active!==true)
        throw new Error("inactive_central_session");
    } catch {
      const failed=NextResponse.json({error:"Authentication session unavailable"},{status:401});
      failed.cookies.delete(TEMP);return failed;
    }
    const session:Session={accessToken:tokens.access_token,expiresAt};
    const destination=new URL(pending.returnTo,request.nextUrl.origin);
    const response=NextResponse.redirect(destination);
    response.cookies.set(SESSION,seal(session,options.secret),{...shared,maxAge:Math.max(1,Math.floor((expiresAt-Date.now())/1000))});
    response.cookies.delete(TEMP); return response;
  }
  async function getSession() {
    const store=await cookies();
    const session=open<Session>(store.get(SESSION)?.value,options.secret);
    if (!session || Date.now()>=session.expiresAt) return null;
    try {
      const verified=await jwtVerify(session.accessToken,jwks,{issuer,audience:options.clientId,algorithms:["RS256"]});
      // Signatures alone cannot detect revoked sessions or disabled clients.
      // Check online on each protected server request; fail closed on outages.
      const active = await fetch(`${issuer}/v1/account/session-status`, {
        headers: { Authorization: `Bearer ${session.accessToken}` },
        cache: "no-store",
        signal: AbortSignal.timeout(5000),
      });
      if (!active.ok) return null;
      const status = await active.json() as { active?: boolean };
      if (status.active !== true) return null;
      return {user:verified.payload,expiresAt:session.expiresAt};
    } catch { return null; }
  }
  /** Make a central Auth API request entirely on the server using a validated session. */
  async function authenticatedRequest(path: string, init: RequestInit = {}): Promise<Response> {
    // Only account endpoints may be called; never proxy arbitrary URLs.
    if (!path.startsWith("/v1/account/") || path.startsWith("//") ||
        path.includes("?") || path.includes("#") || path.includes("%") || path.includes("\\") ||
        path.split("/").includes(".."))
      throw new Error("ITHUTE_AUTH_INVALID_ACCOUNT_PATH");
    const store=await cookies();
    const session=open<Session>(store.get(SESSION)?.value,options.secret);
    if (!session || Date.now()>=session.expiresAt)
      throw new Error("ITHUTE_AUTH_UNAUTHENTICATED");
    try {
      await jwtVerify(session.accessToken,jwks,{issuer,audience:options.clientId,algorithms:["RS256"]});
      const status=await fetch(`${issuer}/v1/account/session-status`,{
        headers:{Authorization:`Bearer ${session.accessToken}`},
        cache:"no-store",signal:AbortSignal.timeout(5000),
      });
      if (!status.ok || (await status.json() as {active?:boolean}).active!==true)
        throw new Error("ITHUTE_AUTH_UNAUTHENTICATED");
    } catch { throw new Error("ITHUTE_AUTH_UNAUTHENTICATED"); }
    const headers=new Headers(init.headers);
    headers.delete("authorization");
    headers.set("Authorization",`Bearer ${session.accessToken}`);
    return fetch(`${issuer}${path}`,{
      ...init,headers,cache:"no-store",redirect:"error",
      signal:init.signal ?? AbortSignal.timeout(10000),
    });
  }
  async function logout(request: NextRequest) {
    // Logouts mutate authentication state: disallow GET and cross-origin POST.
    if (request.method !== "POST") return NextResponse.json({error:"POST required"},{status:405});
    const origin=request.headers.get("origin");
    if (!origin || origin!==request.nextUrl.origin) return NextResponse.json({error:"Cross-origin logout rejected"},{status:403});
    // Revoke the central session before confirming logout. Clearing the browser
    // cookie alone would leave the bearer token valid in other applications.
    const session=open<Session>(request.cookies.get(SESSION)?.value,options.secret);
    let revoked = !session;
    if (session) {
      try {
        const result=await fetch(`${issuer}/v1/account/sessions/revoke-current`,{
          method:"POST",headers:{Authorization:`Bearer ${session.accessToken}`},
          cache:"no-store",signal:AbortSignal.timeout(5000),
        });
        // An already-expired or revoked session is effectively logged out.
        revoked=result.ok || result.status===401;
      } catch { revoked=false; }
    }
    const response=revoked
      ? NextResponse.redirect(new URL("/",request.nextUrl.origin),303)
      : NextResponse.json({error:"Central logout could not be verified"},{status:503});
    response.cookies.delete(SESSION);response.cookies.delete(TEMP);
    return response;
  }
  async function requireSession() {
    const session = await getSession();
    if (!session) throw new Error("ITHUTE_AUTH_UNAUTHENTICATED");
    return session;
  }
  return {login,callback:callbackHandler,getSession,requireSession,authenticatedRequest,logout};
}
