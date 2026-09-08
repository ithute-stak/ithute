import { NextRequest } from "next/server";

const UPSTREAM = (process.env.BUILDTRACK_BACKEND_URL ?? "http://localhost:8004/api/v1").replace(/\/$/, "");

type Context = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, context: Context): Promise<Response> {
  const { path } = await context.params;
  const upstream = new URL(`${UPSTREAM}/${path.map(encodeURIComponent).join("/")}`);
  request.nextUrl.searchParams.forEach((value, key) => upstream.searchParams.append(key, value));

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");
  headers.set("x-forwarded-host", request.nextUrl.host);
  headers.set("x-forwarded-proto", request.nextUrl.protocol.replace(":", ""));

  const method = request.method.toUpperCase();
  const body = method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer();
  const upstreamResponse = await fetch(upstream, {
    method,
    headers,
    body,
    redirect: "manual",
    cache: "no-store",
  });

  const responseHeaders = new Headers(upstreamResponse.headers);
  responseHeaders.delete("content-length");
  responseHeaders.delete("content-encoding");
  responseHeaders.set("cache-control", "no-store");

  return new Response(upstreamResponse.body, {
    status: upstreamResponse.status,
    statusText: upstreamResponse.statusText,
    headers: responseHeaders,
  });
}

export function GET(request: NextRequest, context: Context) { return forward(request, context); }
export function POST(request: NextRequest, context: Context) { return forward(request, context); }
export function PUT(request: NextRequest, context: Context) { return forward(request, context); }
export function PATCH(request: NextRequest, context: Context) { return forward(request, context); }
export function DELETE(request: NextRequest, context: Context) { return forward(request, context); }
export function OPTIONS(request: NextRequest, context: Context) { return forward(request, context); }
