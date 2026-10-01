"use client";

import Link from "next/link";
import { Boxes, Plus } from "lucide-react";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Membership = { tenant_id: string; tenant_name: string };
type Me = { is_platform_owner?: boolean };

export function AddonLauncher() {
  const [visible, setVisible] = useState(false);
  const [tenantName, setTenantName] = useState("");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const meResponse = await fetch(`${API}/auth/me`, { credentials: "include", cache: "no-store" });
        if (!meResponse.ok) return;
        const me = (await meResponse.json()) as Me;
        if (me.is_platform_owner) return;
        const membershipsResponse = await fetch(`${API}/me/memberships`, { credentials: "include", cache: "no-store" });
        if (!membershipsResponse.ok) return;
        const memberships = (await membershipsResponse.json()) as Membership[];
        if (cancelled || memberships.length === 0) return;
        const selected = window.localStorage.getItem("mailbox_dns_tenant");
        const membership = memberships.find((item) => item.tenant_id === selected) || memberships[0];
        setTenantName(membership?.tenant_name || "your company");
        setVisible(Boolean(membership));
      } catch {
        // Public/unauthenticated pages intentionally render no capacity launcher.
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (!visible) return null;

  return (
    <Link
      href="/addons"
      aria-label="Open add-ons and capacity upgrades"
      className="fixed bottom-5 right-5 z-[85] flex items-center gap-3 rounded-2xl border border-[#d8c56a]/35 bg-[#123a38] px-4 py-3 text-white shadow-[0_18px_50px_rgba(18,58,56,.28)] transition hover:-translate-y-0.5 hover:bg-[#285b55]"
    >
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-white/10 text-[#eadb86]"><Boxes size={17} /></span>
      <span className="hidden sm:block">
        <span className="block max-w-[180px] truncate text-[10px] font-black uppercase tracking-[.09em] text-[#d8c56a]">{tenantName}</span>
        <span className="mt-0.5 flex items-center gap-1.5 text-xs font-black"><Plus size={13} /> Add capacity</span>
      </span>
    </Link>
  );
}
