"use client";

import { useEffect, useRef, useState } from "react";
import { MailLoading } from "./mail-loading";
import { WebmailEntry } from "./webmail-entry";

export function WebmailShell() {
  const rootRef = useRef<HTMLDivElement>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const sync = () => {
      const text = root.textContent || "";
      setChecking(text.includes("Opening !THUTE Mail"));
    };

    sync();
    const observer = new MutationObserver(sync);
    observer.observe(root, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={rootRef} className="relative min-h-screen">
      <WebmailEntry />
      {checking ? (
        <div className="absolute inset-0 z-[70] bg-white">
          <MailLoading label="Opening iMail" detail="Preparing your secure Ithute mailbox" />
        </div>
      ) : null}
    </div>
  );
}
