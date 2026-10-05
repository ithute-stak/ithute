const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type CacheEntry = { expiresAt: number; value: unknown };
type JsonOptions = { ttlMs?: number; signal?: AbortSignal; force?: boolean };

const cache = new Map<string, CacheEntry>();
const inflight = new Map<string, Promise<unknown>>();
let sessionRefresh: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  if (sessionRefresh) return sessionRefresh;

  sessionRefresh = (async () => {
    // Central Ithute Auth is the production identity path. Try it first so a
    // rotating central refresh token is consumed exactly once. Development and
    // explicitly enabled legacy installations may fall back to local auth.
    let response = await fetch(`${API}/auth/ithute/refresh`, {
      method: "POST",
      credentials: "include",
      cache: "no-store",
    });
    if (!response.ok) {
      response = await fetch(`${API}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        cache: "no-store",
      });
    }
    return response.ok;
  })();

  try {
    return await sessionRefresh;
  } finally {
    sessionRefresh = null;
  }
}

export class PlatformApiError extends Error {
  status: number;
  detail?: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "PlatformApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const request = () => fetch(`${API}${path}`, { credentials: "include", ...init });
  let response = await request();

  const refreshPath =
    path === "/auth/refresh" ||
    path === "/auth/ithute/refresh" ||
    path === "/auth/login" ||
    path === "/auth/ithute/login";

  if (response.status === 401 && !refreshPath && (await refreshSession())) {
    response = await request();
  }

  return response;
}

export async function apiJson<T>(path: string, options: JsonOptions = {}): Promise<T> {
  const ttlMs = options.ttlMs ?? 15_000;
  const now = Date.now();
  const existing = cache.get(path);
  if (!options.force && existing && existing.expiresAt > now) return existing.value as T;

  if (!options.force) {
    const pending = inflight.get(path);
    if (pending) return pending as Promise<T>;
  }

  const promise = (async () => {
    const response = await apiFetch(path, { signal: options.signal });
    if (!response.ok) {
      const detail = await response.json().catch(() => undefined);
      const message = typeof detail === "object" && detail && "detail" in detail ? String((detail as { detail?: unknown }).detail || response.statusText) : response.statusText;
      throw new PlatformApiError(message || `Request failed (${response.status})`, response.status, detail);
    }
    const value = (await response.json()) as T;
    if (ttlMs > 0) cache.set(path, { value, expiresAt: Date.now() + ttlMs });
    return value;
  })();

  inflight.set(path, promise);
  try {
    return await promise;
  } finally {
    inflight.delete(path);
  }
}

export function peekApiCache<T>(path: string): T | undefined {
  const entry = cache.get(path);
  if (!entry || entry.expiresAt <= Date.now()) return undefined;
  return entry.value as T;
}

export function setApiCache<T>(path: string, value: T, ttlMs = 15_000) {
  cache.set(path, { value, expiresAt: Date.now() + ttlMs });
}

export function updateApiCache<T>(path: string, updater: (current: T | undefined) => T, ttlMs = 15_000) {
  const current = peekApiCache<T>(path);
  const next = updater(current);
  setApiCache(path, next, ttlMs);
  return next;
}

export function invalidateApiCache(prefix?: string) {
  if (!prefix) {
    cache.clear();
    return;
  }
  for (const key of cache.keys()) if (key.startsWith(prefix)) cache.delete(key);
}

export async function apiMutation<T = unknown>(path: string, init: RequestInit, invalidatePrefixes: string[] = []) {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    const detail = await response.json().catch(() => undefined);
    const message = typeof detail === "object" && detail && "detail" in detail ? String((detail as { detail?: unknown }).detail || response.statusText) : response.statusText;
    throw new PlatformApiError(message || `Request failed (${response.status})`, response.status, detail);
  }
  invalidatePrefixes.forEach((prefix) => invalidateApiCache(prefix));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export { API as PLATFORM_API_URL };
