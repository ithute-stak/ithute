"use client";

import { MailPlus } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

export function WebmailExternalShortcut() {
  const [mailboxReady, setMailboxReady] = useState(false);

  useEffect(() => {
    const sync = () => {
      const root = document.querySelector(".imail-route-webmail");
      setMailboxReady(Boolean(root?.querySelector("header") && root?.querySelector("main")));
    };

    sync();
    const root = document.querySelector(".imail-route-webmail") || document.body;
    const observer = new MutationObserver(sync);
    observer.observe(root, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  if (!mailboxReady) return null;

  return (
    <Link
      href="/webmail/external"
      className="fixed bottom-4 left-4 z-[75] hidden min-h-11 items-center gap-2 rounded-full border border-[#c9ddd4] bg-white/95 px-4 text-xs font-extrabold text-[#155b47] shadow-[0_10px_28px_rgba(16,72,55,.12)] backdrop-blur transition hover:-translate-y-0.5 hover:border-[#a9cdbf] hover:bg-[#f1f9f5] md:inline-flex"
    >
      <MailPlus size={15} />
      Other email account
    </Link>
  );
}
