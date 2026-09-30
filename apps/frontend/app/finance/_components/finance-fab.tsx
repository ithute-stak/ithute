"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, ChevronUp, FileText, ReceiptText, Repeat2, Users2, WalletCards } from "lucide-react";

const links = [
  { href: "/finance", label: "Invoices & automation", icon: Repeat2 },
  { href: "/finance/documents", label: "Quotations & pro-formas", icon: FileText },
  { href: "/finance/clients", label: "Clients", icon: Users2 },
  { href: "/finance/collections", label: "Collections & payments", icon: WalletCards },
  { href: "/finance/reports", label: "Reports & statements", icon: BarChart3 },
];

export function FinanceFab() {
  const pathname = usePathname();
  const current = links.find((item) => item.href === pathname) ?? links.find((item) => item.href !== "/finance" && pathname.startsWith(item.href));

  return (
    <details className="group fixed bottom-5 right-5 z-[70]">
      <div className="mb-2 w-[min(320px,calc(100vw-2.5rem))] overflow-hidden rounded-2xl border border-[#b9d5cb] bg-white/98 p-2 shadow-2xl backdrop-blur">
        <div className="px-3 pb-2 pt-1">
          <p className="text-[10px] font-black uppercase tracking-[0.16em] text-[#4f776c]">Finance workspace</p>
          <p className="mt-1 text-xs text-[#6c7c78]">Jump between finance tools without using the main navbar.</p>
        </div>
        <nav className="grid gap-1">
          {links.map(({ href, label, icon: Icon }) => {
            const active = href === "/finance" ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-xs font-extrabold transition ${active ? "bg-[#e7f4ee] text-[#124f3e]" : "text-[#31443f] hover:bg-[#f1f7f4]"}`}
              >
                <span className="grid h-8 w-8 place-items-center rounded-lg border border-[#d8e8e2] bg-white"><Icon size={15} /></span>
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
      <summary className="ml-auto flex w-fit cursor-pointer list-none items-center gap-2 rounded-full border border-[#8db9aa] bg-[#123f35] px-4 py-3 text-xs font-black text-white shadow-xl transition hover:-translate-y-0.5 hover:bg-[#0e342c] [&::-webkit-details-marker]:hidden">
        <ReceiptText size={16} />
        <span>{current?.label || "Finance menu"}</span>
        <ChevronUp size={14} className="transition group-open:rotate-180" />
      </summary>
    </details>
  );
}
