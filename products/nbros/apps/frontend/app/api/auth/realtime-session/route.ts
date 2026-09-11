import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export async function GET() {
  const store = await cookies();
  const accessToken = store.get("nbros_access")?.value;
  if (!accessToken) {
    return NextResponse.json({ detail: "not authenticated" }, { status: 401 });
  }
  const response = NextResponse.json({
    access_token: accessToken,
    websocket_url: process.env.NBROS_REALTIME_WS_URL ?? "wss://realtime.ithute.co.ls/v1/ws",
  });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
