import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const backendBase = process.env.NBROS_BACKEND_INTERNAL_URL ?? "http://backend:8000";

export async function GET(
  _request: Request,
  context: { params: Promise<{ branch: string; filename: string }> },
) {
  const { branch, filename } = await context.params;
  const store = await cookies();
  const token = store.get("nbros_access")?.value;
  if (!token) return NextResponse.json({ detail: "not signed in" }, { status: 401 });

  const response = await fetch(
    `${backendBase}/api/v1/fleet/files/${encodeURIComponent(branch)}/${encodeURIComponent(filename)}`,
    { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" },
  );

  if (!response.ok) {
    return NextResponse.json({ detail: "file unavailable" }, { status: response.status });
  }

  const headers = new Headers();
  const contentType = response.headers.get("content-type");
  const disposition = response.headers.get("content-disposition");
  if (contentType) headers.set("content-type", contentType);
  if (disposition) headers.set("content-disposition", disposition);
  headers.set("cache-control", "private, no-store");

  return new Response(response.body, { status: 200, headers });
}
