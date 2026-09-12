"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

function routeClass(pathname: string) {
  if (pathname.startsWith("/webmail/migrate")) return "imail-route-migrate";
  if (pathname.startsWith("/webmail/external")) return "imail-route-external";
  if (pathname.startsWith("/webmail/settings")) return "imail-route-settings";
  if (pathname.startsWith("/webmail/compose")) return "imail-route-compose";
  return "imail-route-webmail";
}

export function WebmailRouteFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return <div className={`imail-approved-ui ${routeClass(pathname)}`}>{children}</div>;
}
