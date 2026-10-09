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
    const responseFromIssuer = await fetch(`${issuer}/oauth/token`, {method:"POST",
      headers:{"Content-Type":"application/x-www-form-urlencoded"},
      body:new URLSearchParams({grant_type:"authorization_code",client_id:options.clientId,redirect_uri:callback,
        code,code_verifier:pending.verifier}), cache:"no-store"});
    if (!responseFromIssuer.ok) {
      const response=NextResponse.json({error:"Authentication exchange failed"},{status:401});
      response.cookies.delete(TEMP); return response;
    }
    const tokens=await responseFromIssuer.json() as {access_token:string;id_token?:string;refresh_token?:string;expires_in?:number};
    if (!tokens.access_token) return NextResponse.json({error:"No access token returned"},{status:502});
    await jwtVerify(tokens.access_token,jwks,{issuer,audience:options.clientId,algorithms:["RS256"]});
    if (tokens.id_token) {
      const verified=await jwtVerify(tokens.id_token,jwks,{issuer,audience:options.clientId,algorithms:["RS256"]});
      if (verified.payload.nonce!==pending.nonce) return NextResponse.json({error:"Invalid ID token nonce"},{status:401});
    }
    // Do not store unnecessary refresh or identity tokens in browser cookies.
    // Session expiration is bounded by the verified access-token expiry.
    const verifiedAccess = await jwtVerify(tokens.access_token,jwks,{issuer,audience:options.clientId,algorithms:["RS256"]});
    const accessExpiresAt = (verifiedAccess.payload.exp ?? 0) * 1000;
    const expiresAt = Math.min(Date.now() + Math.min(Math.max(tokens.expires_in ?? 600, 1), 3600) * 1000, accessExpiresAt);
    if (expiresAt <= Date.now()) return NextResponse.json({error:"Expired access token"},{status:401});
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
      return {user:verified.payload,expiresAt:session.expiresAt};
    } catch { return null; }
  }
  async function logout(request: NextRequest) {
    // Logouts mutate authentication state: disallow GET and cross-origin POST.
    if (request.method !== "POST") return NextResponse.json({error:"POST required"},{status:405});
    const origin=request.headers.get("origin");
    if (!origin || origin!==request.nextUrl.origin) return NextResponse.json({error:"Cross-origin logout rejected"},{status:403});
    const response=NextResponse.redirect(new URL("/",request.nextUrl.origin),303);
    response.cookies.delete(SESSION);response.cookies.delete(TEMP);
    return response;
  }
  async function requireSession() {
    const session = await getSession();
    if (!session) throw new Error("ITHUTE_AUTH_UNAUTHENTICATED");
    return session;
  }
  return {login,callback:callbackHandler,getSession,requireSession,logout};
}
