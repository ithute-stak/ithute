import { cookies } from "next/headers";

const backendBase = process.env.NBROS_BACKEND_INTERNAL_URL ?? "http://backend:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function nbrosApi<T>(path: string, init?: RequestInit): Promise<T> {
  const store = await cookies();
  const token = store.get("nbros_access")?.value;
  if (!token) throw new ApiError(401, "Not signed in");

  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${backendBase}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    let message = `NBros API request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {
      // Keep the status-based message when the response is not JSON.
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
