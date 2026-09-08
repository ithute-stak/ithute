"use client";

import { CloudDownload } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

export function MailMigrationShortcut() {
  const pathname = usePathname();
  if (pathname.startsWith("/webmail/migrate") || pathname.startsWith("/webmail/settings") || pathname.startsWith("/webmail/compose")) return null;
  if (!(pathname === "/webmail" || pathname.startsWith("/webmail/external"))) return null;

  return (
    <Link
      href="/webmail/migrate"
      className="fixed bottom-20 right-4 z-[45] inline-flex h-11 items-center gap-2 rounded-full border border-slate-200 bg-white px-4 text-xs font-black text-slate-700 shadow-[0_12px_32px_rgba(15,23,42,.14)] transition hover:-translate-y-0.5 hover:border-blue-200 hover:text-blue-700 sm:bottom-6 sm:right-6"
      title="Import Gmail or another mailbox into Ithute Mail"
    >
      <CloudDownload size={16} />
      <span className="hidden sm:inline">Import Gmail / mail</span>
      <span className="sm:hidden">Import</span>
    </Link>
  );
}
