import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  const accessToken = request.cookies.get("nbros_access")?.value;
  if (accessToken) return NextResponse.next();

  const refreshToken = request.cookies.get("nbros_refresh")?.value;
  const target = `${request.nextUrl.pathname}${request.nextUrl.search}`;

  const destination = request.nextUrl.clone();
  destination.search = "";

  if (refreshToken) {
    destination.pathname = "/api/auth/refresh";
    destination.searchParams.set("return", target);
    return NextResponse.redirect(destination);
  }

  destination.pathname = "/api/auth/login";
  return NextResponse.redirect(destination);
}

export const config = {
  matcher: ["/fleet/:path*"],
};
