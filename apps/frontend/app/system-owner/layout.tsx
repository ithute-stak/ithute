import Link from "next/link";
import type { ReactNode } from "react";

const links = [
  ["Command Centre", "/system-owner"],
  ["Operations", "/system-owner/operations"],
  ["Security", "/system-owner/security"],
  ["Backup & Recovery", "/system-owner/recovery"],
] as const;

export default function SystemOwnerLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <nav className="fixed bottom-4 left-1/2 z-[80] flex max-w-[calc(100vw-2rem)] -translate-x-1/2 gap-1 overflow-x-auto rounded-2xl border border-black/10 bg-white/95 p-1.5 shadow-xl backdrop-blur print:hidden">
        {links.map(([label, href]) => (
          <Link key={href} href={href} className="whitespace-nowrap rounded-xl px-3 py-2 text-[10px] font-black text-[#173e3a] transition hover:bg-[#eef5f2]">
            {label}
          </Link>
        ))}
      </nav>
      {children}
    </>
  );
}
