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
