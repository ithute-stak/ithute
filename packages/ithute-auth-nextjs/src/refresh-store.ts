/** Durable server-only refresh-token persistence contract.
 * Implement using a transactional SQL row or atomic Redis script.
 * Never store refresh tokens in browser cookies, localStorage, or logs.
 */
import "server-only";

export type RefreshRecord = {
  /** Opaque random session identifier; browser receives only this identifier. */
  id: string;
  clientId: string;
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
  /** Monotonically increasing compare-and-swap version. */
  version: number;
};

export interface RefreshTokenStore {
  create(record: RefreshRecord): Promise<void>;
  find(id: string): Promise<RefreshRecord | null>;
  /** Exactly one concurrent rotation may succeed. False means replay/race. */
  rotate(id: string, expectedVersion: number, next: Omit<RefreshRecord, "id" | "version">): Promise<boolean>;
  revoke(id: string): Promise<void>;
}

/** Refuse integration with a store without atomic rotation guarantees. */
export function assertRefreshStore(store: RefreshTokenStore): void {
  for (const method of ["create", "find", "rotate", "revoke"] as const) {
    if (typeof store?.[method] !== "function") throw new Error(`RefreshTokenStore.${method} is required`);
  }
}

/** Rotate in central Auth and commit by CAS; on a race fail closed.
 * The caller must verify the returned access JWT and central status before trusting it.
 */
export async function rotateStoredTokens(
  store: RefreshTokenStore,
  record: RefreshRecord,
  issuer: string,
): Promise<RefreshRecord | null> {
  assertRefreshStore(store);
  if (!issuer.startsWith("https://")) throw new Error("HTTPS issuer required");
  let response: Response;
  try {
    response = await fetch(`${issuer.replace(/\/$/, "")}/oauth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "refresh_token",
        client_id: record.clientId,
        refresh_token: record.refreshToken,
      }),
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
  } catch {
    return null;
  }
  if (!response.ok) {
    if (response.status === 400 || response.status === 401) await store.revoke(record.id);
    return null;
  }
  let tokens: {access_token?: string; refresh_token?: string; expires_in?: number};
  try { tokens = await response.json(); } catch { await store.revoke(record.id); return null; }
  if (!tokens.access_token || !tokens.refresh_token || !Number.isFinite(tokens.expires_in)) {
    await store.revoke(record.id);
    return null;
  }
  const expiresAt = Date.now() + Math.min(Math.max(tokens.expires_in!, 1), 3600) * 1000;
  const next = {
    clientId: record.clientId,
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    expiresAt,
  };
  const updated = await store.rotate(record.id, record.version, next);
  if (!updated) {
    // A concurrent use of the previous refresh token means this session must
    // be re-established. Do not overwrite the winner's newer credentials.
    await store.revoke(record.id);
    return null;
  }
  return { id: record.id, version: record.version + 1, ...next };
}
