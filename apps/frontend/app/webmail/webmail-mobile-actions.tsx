"use client";

import { Inbox, Paperclip, PenLine, Settings, Star } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

function buttonsInMail() {
  return Array.from(document.querySelectorAll<HTMLButtonElement>(".imail-route-webmail button"));
}

function clickButton(predicate: (button: HTMLButtonElement) => boolean) {
  const button = buttonsInMail().find(predicate);
  button?.click();
}

function openInbox() {
  clickButton((button) => button.title.trim().toLowerCase() === "inbox");
}

function openStarred() {
  clickButton((button) => button.title.trim().toLowerCase() === "starred");
}

function openAttachments() {
  clickButton((button) => {
    const text = button.textContent?.trim().toLowerCase() || "";
    return text.startsWith("attachments");
  });
}

function openCompose() {
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "c", bubbles: true }));
}

export function WebmailMobileActions() {
  const pathname = usePathname();
  const [mailboxReady, setMailboxReady] = useState(false);

  useEffect(() => {
    if (pathname !== "/webmail") {
      setMailboxReady(false);
      return;
    }

    const sync = () => {
      const root = document.querySelector(".imail-route-webmail");
      const authenticatedShell = root?.querySelector("header") && root?.querySelector("main");
      setMailboxReady(Boolean(authenticatedShell));
    };

    sync();
    const root = document.querySelector(".imail-route-webmail") || document.body;
    const observer = new MutationObserver(sync);
    observer.observe(root, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [pathname]);

  if (pathname !== "/webmail" || !mailboxReady) return null;

  return (
    <>
      <button type="button" className="imail-mobile-compose" onClick={openCompose} aria-label="Compose a new email">
        <PenLine size={18} />
        Compose
      </button>
      <nav className="imail-mobile-nav" aria-label="Mobile mailbox navigation">
        <button type="button" data-active="true" onClick={openInbox}>
          <Inbox size={19} />
          Inbox
        </button>
        <button type="button" onClick={openStarred}>
          <Star size={19} />
          Starred
        </button>
        <button type="button" onClick={openAttachments}>
          <Paperclip size={19} />
          Attachments
        </button>
        <Link href="/webmail/settings">
          <Settings size={19} />
          More
        </Link>
      </nav>
    </>
  );
}
