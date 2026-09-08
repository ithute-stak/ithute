"use client";

import { FileText, Inbox, MoreHorizontal, Paperclip, PenLine, Send, SlidersHorizontal, Star } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

type MobileView = "inbox" | "starred" | "attachments" | "drafts" | "sent";

function buttonsInMail() {
  return Array.from(document.querySelectorAll<HTMLButtonElement>(".imail-route-webmail button"));
}

function clickButton(predicate: (button: HTMLButtonElement) => boolean) {
  const button = buttonsInMail().find(predicate);
  if (!button) return false;
  button.click();
  return true;
}

function folderButton(kind: string) {
  const normalized = kind.toLowerCase();
  return buttonsInMail().find((button) => {
    const title = button.title.trim().toLowerCase();
    if (normalized === "drafts") return title === "drafts" || title.includes("draft");
    if (normalized === "sent") return title === "sent" || title.includes("sent mail");
    return title === normalized;
  });
}

function openFolder(kind: MobileView) {
  if (kind === "starred") return clickButton((button) => button.title.trim().toLowerCase() === "starred");
  if (kind === "attachments") {
    return clickButton((button) => {
      const text = button.textContent?.trim().toLowerCase() || "";
      return text.startsWith("attachments");
    });
  }
  const button = folderButton(kind);
  if (!button) return false;
  button.click();
  return true;
}

function openCompose() {
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "c", bubbles: true }));
}

function openFilters() {
  clickButton((button) => button.title.trim().toLowerCase() === "more");
}

function profileInitials(value: string) {
  const local = value.includes("@") ? value.split("@")[0] : value;
  const parts = local.split(/[\s._-]+/).map((item) => item.trim()).filter(Boolean);
  if (!parts.length) return "IT";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || "I"}${parts[parts.length - 1][0] || "T"}`.toUpperCase();
}

function parseCount(button: HTMLButtonElement | undefined) {
  if (!button) return 0;
  const spans = Array.from(button.querySelectorAll("span"));
  for (const span of spans.reverse()) {
    const value = (span.textContent || "").trim().replace(/,/g, "");
    if (/^\d+$/.test(value)) return Number(value);
  }
  const match = (button.textContent || "").match(/(\d[\d,]*)\s*$/);
  return match ? Number(match[1].replace(/,/g, "")) : 0;
}

export function WebmailMobileActions() {
  const pathname = usePathname();
  const [mailboxReady, setMailboxReady] = useState(false);
  const [messageOpen, setMessageOpen] = useState(false);
  const [activeView, setActiveView] = useState<MobileView>("inbox");
  const [inboxCount, setInboxCount] = useState(0);
  const [accountLabel, setAccountLabel] = useState("Ithute");

  useEffect(() => {
    if (pathname !== "/webmail") {
      setMailboxReady(false);
      setMessageOpen(false);
      return;
    }

    const sync = () => {
      const root = document.querySelector(".imail-route-webmail");
      const shell = root?.querySelector(".imail-hosted-workspace");
      setMailboxReady(Boolean(shell?.querySelector("header") && shell?.querySelector("section")));
      setMessageOpen(Boolean(shell?.querySelector("article.imail-message-reader")));

      const inbox = folderButton("inbox");
      setInboxCount(parseCount(inbox));

      const label = shell?.querySelector("header > div:nth-of-type(2) p:first-child")?.textContent?.trim();
      if (label) setAccountLabel(label);

      const starred = folderButton("starred");
      const attachments = buttonsInMail().find((button) => (button.textContent?.trim().toLowerCase() || "").startsWith("attachments"));
      const drafts = folderButton("drafts");
      const sent = folderButton("sent");
      const isActive = (button?: HTMLButtonElement) => Boolean(button?.className.includes("bg-[#eaf1fb]") || button?.className.includes("font-black text-[#174ea6]"));
      if (isActive(starred)) setActiveView("starred");
      else if (isActive(attachments)) setActiveView("attachments");
      else if (isActive(drafts)) setActiveView("drafts");
      else if (isActive(sent)) setActiveView("sent");
      else if (isActive(inbox)) setActiveView("inbox");
    };

    sync();
    const root = document.querySelector(".imail-route-webmail") || document.body;
    const observer = new MutationObserver(sync);
    observer.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, [pathname]);

  const initials = useMemo(() => profileInitials(accountLabel), [accountLabel]);

  if (pathname !== "/webmail" || !mailboxReady) return null;

  const navigate = (view: MobileView) => {
    if (openFolder(view)) setActiveView(view);
  };

  return (
    <>
      <button type="button" className="imail-mobile-profile" onClick={() => { if (!clickButton((button) => button.title.trim().toLowerCase() === "settings")) window.location.assign("/webmail/settings"); }} aria-label="Open mailbox settings">
        {initials}
      </button>

      {!messageOpen ? (
        <>
          <button type="button" className="imail-mobile-search-filter" onClick={openFilters} aria-label="Filter mail">
            <SlidersHorizontal size={19} />
          </button>

          <div className="imail-mobile-home-actions" aria-label="Mailbox shortcuts">
            <div className="imail-mobile-quick-folders">
              <button type="button" data-active={activeView === "inbox"} onClick={() => navigate("inbox")}>
                <Inbox size={19} />
                <span>Inbox</span>
                {inboxCount > 0 ? <strong>{inboxCount > 999 ? "999+" : inboxCount}</strong> : null}
              </button>
              <button type="button" data-active={activeView === "starred"} onClick={() => navigate("starred")}>
                <Star size={19} />
                <span>Starred</span>
              </button>
              <button type="button" data-active={activeView === "drafts"} onClick={() => navigate("drafts")}>
                <FileText size={18} />
                <span>Drafts</span>
              </button>
              <button type="button" data-active={activeView === "sent"} onClick={() => navigate("sent")}>
                <Send size={18} />
                <span>Sent</span>
              </button>
            </div>
            <button type="button" className="imail-mobile-primary-compose" onClick={openCompose}>
              <PenLine size={20} />
              <span>Compose</span>
            </button>
          </div>

          <nav className="imail-mobile-nav" aria-label="Mobile mailbox navigation">
            <button type="button" data-active={activeView === "inbox"} onClick={() => navigate("inbox")}>
              <span className="imail-mobile-nav-icon"><Inbox size={20} />{inboxCount > 0 ? <strong className="imail-mobile-badge">{inboxCount > 999 ? "999+" : inboxCount}</strong> : null}</span>
              <span>Inbox</span>
            </button>
            <button type="button" data-active={activeView === "starred"} onClick={() => navigate("starred")}>
              <span className="imail-mobile-nav-icon"><Star size={20} /></span>
              <span>Starred</span>
            </button>
            <button type="button" data-active={activeView === "attachments"} onClick={() => navigate("attachments")}>
              <span className="imail-mobile-nav-icon"><Paperclip size={20} /></span>
              <span>Attachments</span>
            </button>
            <Link href="/webmail/settings">
              <span className="imail-mobile-nav-icon"><MoreHorizontal size={22} /></span>
              <span>More</span>
            </Link>
          </nav>
        </>
      ) : null}
    </>
  );
}
