"use client";

import Link from "next/link";
import { ChevronDown, CloudDownload, Inbox, ListFilter, Mail, Settings2, UsersRound, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const ITEMS = [
  { href: "/webmail/unified", label: "Unified Inbox", detail: "All hosted and connected accounts", icon: Inbox },
  { href: "/webmail/accounts", label: "Mail accounts", detail: "Google, Microsoft and IMAP accounts", icon: UsersRound },
  { href: "/webmail/productivity", label: "Rules & scheduled mail", detail: "Filters, automations and send later", icon: ListFilter },
  { href: "/webmail/migrate", label: "Migration Center", detail: "Move Gmail or external mail into iMail", icon: CloudDownload },
  { href: "/webmail/settings", label: "Mail settings", detail: "Appearance and mailbox preferences", icon: Settings2 },
] as const;

export function WebmailNextNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  if (pathname === "/webmail/login") return null;

  return (
    <div ref={root} className="fixed bottom-20 right-4 z-[58] sm:bottom-6 sm:right-6">
      {open ? (
        <div className="mb-3 w-[min(360px,calc(100vw-32px))] overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-[0_22px_70px_rgba(15,23,42,.22)] dark:border-white/10 dark:bg-[#111820]">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3 dark:border-white/10">
            <div className="flex items-center gap-2"><span className="grid h-8 w-8 place-items-center rounded-xl bg-[#0c6f55] text-[11px] font-black text-white">iM</span><div><p className="text-sm font-black text-slate-900 dark:text-white">iMail Hub</p><p className="text-[10px] text-slate-500">One workspace for every mailbox</p></div></div>
            <button type="button" onClick={() => setOpen(false)} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" aria-label="Close iMail Hub"><X size={15} /></button>
          </div>
          <div className="p-2">
            <Link href="/webmail" className={`flex items-center gap-3 rounded-2xl px-3 py-2.5 transition ${pathname === "/webmail" ? "bg-blue-50 text-blue-800 dark:bg-blue-500/10 dark:text-blue-200" : "hover:bg-slate-50 dark:hover:bg-white/5"}`}><span className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"><Mail size={17} /></span><span><span className="block text-sm font-bold">Hosted iMail</span><span className="block text-[11px] text-slate-500">Your Ithute business mailbox</span></span></Link>
            {ITEMS.map(({ href, label, detail, icon: Icon }) => (
              <Link key={href} href={href} className={`mt-1 flex items-center gap-3 rounded-2xl px-3 py-2.5 transition ${pathname.startsWith(href) ? "bg-blue-50 text-blue-800 dark:bg-blue-500/10 dark:text-blue-200" : "hover:bg-slate-50 dark:hover:bg-white/5"}`}><span className="grid h-9 w-9 place-items-center rounded-xl bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300"><Icon size={17} /></span><span className="min-w-0"><span className="block truncate text-sm font-bold">{label}</span><span className="block truncate text-[11px] text-slate-500">{detail}</span></span></Link>
            ))}
          </div>
        </div>
      ) : null}
      <button type="button" onClick={() => setOpen((value) => !value)} className="inline-flex h-12 items-center gap-2 rounded-full border border-slate-200 bg-white px-4 text-xs font-black text-slate-700 shadow-[0_14px_38px_rgba(15,23,42,.18)] transition hover:-translate-y-0.5 hover:border-blue-200 hover:text-blue-700 dark:border-white/10 dark:bg-[#141b20] dark:text-slate-200" aria-expanded={open} aria-label="Open iMail Hub"><span className="grid h-7 w-7 place-items-center rounded-full bg-[#0c6f55] text-[9px] font-black text-white">iM</span><span className="hidden sm:inline">iMail Hub</span><ChevronDown size={14} className={open ? "rotate-180 transition" : "transition"} /></button>
    </div>
  );
}
