export type OidcDiscovery = {
  issuer: string;
  authorization_endpoint: string;
  token_endpoint: string;
  jwks_uri: string;
};

export function authIssuer(): string {
  return (process.env.NBROS_AUTH_ISSUER ?? "https://auth.ithute.co.ls").replace(/\/$/, "");
}

export function clientId(): string {
  return process.env.NBROS_AUTH_CLIENT_ID ?? "nbros";
}

export function redirectUri(): string {
  return process.env.NBROS_OIDC_REDIRECT_URI ?? "https://nbro.ithute.co.ls/api/auth/oidc/callback";
}

export function cookieSecure(): boolean {
  return (process.env.NBROS_COOKIE_SECURE ?? "true").toLowerCase() !== "false";
}

export async function discovery(): Promise<OidcDiscovery> {
  const response = await fetch(`${authIssuer()}/.well-known/openid-configuration`, { cache: "no-store" });
  if (!response.ok) throw new Error("Central Auth discovery failed");
  return response.json() as Promise<OidcDiscovery>;
}
