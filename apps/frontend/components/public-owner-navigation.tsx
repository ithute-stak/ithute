"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Printer } from "lucide-react";
import { createPortal } from "react-dom";
import { useEffect, useState } from "react";

export function PublicOwnerNavigation() {
  const pathname = usePathname();
  const [homeNavHost, setHomeNavHost] = useState<HTMLElement | null>(null);
  const [founderActionsHost, setFounderActionsHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    setHomeNavHost(null);
    setFounderActionsHost(null);

    if (pathname === "/") {
      const nav = document.querySelector<HTMLElement>("main > section:first-of-type header nav");
      const clientPortal = nav?.querySelector<HTMLElement>('a[href="/login"]');

      if (!nav || !clientPortal) return undefined;

      const host = document.createElement("span");
      host.className = "contents";
      host.dataset.idsOwnerNavigation = "true";
      nav.insertBefore(host, clientPortal);
      setHomeNavHost(host);

      return () => host.remove();
    }

    if (pathname === "/founder") {
      const downloadCv = document.querySelector<HTMLElement>('a[href="/documents/Koetlisi-Theko-CV"]');
      const actions = downloadCv?.parentElement;

      if (!actions || !downloadCv) return undefined;

      const host = document.createElement("span");
      host.className = "contents";
      host.dataset.idsFounderPrintAction = "true";
      actions.insertBefore(host, downloadCv.nextSibling);
      setFounderActionsHost(host);

      return () => host.remove();
    }

    return undefined;
  }, [pathname]);

  return (
    <>
      {homeNavHost
        ? createPortal(
            <Link
              href="/founder"
              className="hidden text-xs font-bold text-white/65 transition hover:text-white md:inline"
            >
              Owner profile
            </Link>,
            homeNavHost,
          )
        : null}

      {founderActionsHost
        ? createPortal(
            <Link
              href="/founder/cv"
              target="_blank"
              className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/[.06] px-5 py-3 text-sm font-black text-white transition hover:bg-white/[.1]"
            >
              <Printer size={16} /> Print CV
            </Link>,
            founderActionsHost,
          )
        : null}
    </>
  );
}
