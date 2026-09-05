"use client";

import Link from "next/link";
import {
  Archive,
  ArchiveRestore,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Download,
  Inbox,
  Loader2,
  LogOut,
  Mail,
  MailOpen,
  Menu,
  MoreVertical,
  Paperclip,
  PenLine,
  RefreshCw,
  Reply,
  Search,
  Send,
  Settings,
  SlidersHorizontal,
  Star,
  Trash2,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MailCompose } from "./mail-compose";
import {
  API,
  PAGE_SIZE,
  addressOnly,
  draftStorageKey,
  emptyCompose,
  folderKind,
  humanBytes,
  initials,
  isEditableTarget,
  senderName,
  shortDate,
  splitAddresses,
  stripHtml,
  textToHtml,
  webmail,
  type ComposeState,
  type Density,
  type Folder,
  type FolderCount,
  type InboxView,
  type MessageRow,
} from "./mail-types";

function folderIcon(name: string) {
  const kind = folderKind(name);
  if (kind === "inbox") return <Inbox size={17} />;
  if (kind === "trash") return <Trash2 size={17} />;
  if (kind === "sent") return <Send size={17} />;
  if (kind === "drafts") return <MailOpen size={17} />;
  return <Archive size={17} />;
}

function folderDestination(folders: Folder[], kind: "archive" | "trash") {
  const names = folders.map((folder) => folder.name);
  const preferred = kind === "archive" ? ["Archive", "All Mail"] : ["Trash", "Deleted Items", "Deleted"];
  return preferred.find((name) => names.some((candidate) => candidate.toLowerCase() === name.toLowerCase())) || preferred[0];
}

function hasComposeContent(compose: ComposeState) {
  return Boolean(compose.to.trim() || compose.cc.trim() || compose.bcc.trim() || compose.subject.trim() || compose.bodyText.trim() || compose.bodyHtml.trim() || compose.attachments.length);
}

export function MailClient() {
  const searchRef = useRef<HTMLInputElement>(null);
  const [address, setAddress] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [signatureHtml, setSignatureHtml] = useState("");
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [folderCounts, setFolderCounts] = useState<FolderCount[]>([]);
  const [folder, setFolder] = useState("INBOX");
  const [messages, setMessages] = useState<MessageRow[]>([]);
  const [selected, setSelected] = useState<MessageRow | null>(null);
  const [selectedUids, setSelectedUids] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [composeOpen, setComposeOpen] = useState(false);
  const [composeMinimized, setComposeMinimized] = useState(false);
  const [composeExpanded, setComposeExpanded] = useState(false);
  const [showCcBcc, setShowCcBcc] = useState(false);
  const [compose, setCompose] = useState<ComposeState>(emptyCompose);
  const [mobileFolders, setMobileFolders] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [showMoreFolders, setShowMoreFolders] = useState(false);
  const [query, setQuery] = useState("");
  const [density, setDensity] = useState<Density>("comfortable");
  const [inboxView, setInboxView] = useState<InboxView>("primary");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [accountOpen, setAccountOpen] = useState(false);
  const [searchOptionsOpen, setSearchOptionsOpen] = useState(false);
  const [onlyUnread, setOnlyUnread] = useState(false);
  const [onlyAttachments, setOnlyAttachments] = useState(false);

  const loadFolders = useCallback(async () => {
    const response = await webmail("/folders");
    if (response.ok) setFolders((await response.json()).items || []);
  }, []);

  const loadCounts = useCallback(async () => {
    const response = await webmail("/folder-counts");
    if (response.ok) setFolderCounts((await response.json()).items || []);
  }, []);

  const loadIdentity = useCallback(async () => {
    const response = await webmail("/identity");
    if (response.ok) setDisplayName((await response.json()).display_name || "");
  }, []);

  const loadSignature = useCallback(async () => {
    const response = await webmail("/signature");
    if (response.ok) setSignatureHtml((await response.json()).html || "");
  }, []);

  const loadMessages = useCallback(async (target: string, search = "", nextOffset = 0) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ folder: target, limit: String(PAGE_SIZE), offset: String(nextOffset) });
      if (search.trim()) params.set("q", search.trim());
      const response = await webmail(`/messages?${params}`);
      if (response.status === 401) {
        setAuthenticated(false);
        return;
      }
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to load messages");
      const payload = await response.json();
      setMessages(payload.items || []);
      setTotal(payload.total || 0);
      setOffset(nextOffset);
      setSelected(null);
      setSelectedUids(new Set());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load messages");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      setDensity((window.localStorage.getItem("ithute-webmail-density") as Density) || "comfortable");
      setSidebarCollapsed(window.localStorage.getItem("ithute-webmail-sidebar") === "collapsed");
    }
    void (async () => {
      try {
        const response = await webmail("/session");
        if (!response.ok) {
          setAuthenticated(false);
          return;
        }
        const data = await response.json();
        setAddress(data.address);
        setAuthenticated(true);
        await Promise.all([loadFolders(), loadCounts(), loadIdentity(), loadSignature(), loadMessages("INBOX", "", 0)]);
      } finally {
        setAuthenticated((value) => (value === null ? false : value));
      }
    })();
  }, [loadCounts, loadFolders, loadIdentity, loadMessages, loadSignature]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (!composeOpen || !address) return;
    const timer = window.setTimeout(() => {
      const key = draftStorageKey(address);
      if (hasComposeContent(compose)) window.localStorage.setItem(key, JSON.stringify(compose));
      else window.localStorage.removeItem(key);
    }, 550);
    return () => window.clearTimeout(timer);
  }, [address, compose, composeOpen]);

  useEffect(() => {
    const onPopState = () => {
      const params = new URLSearchParams(window.location.search);
      const uid = params.get("message");
      if (!uid) setSelected(null);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || isEditableTarget(event.target)) return;
      const key = event.key.toLowerCase();
      if (key === "/") {
        event.preventDefault();
        searchRef.current?.focus();
      } else if (key === "c") {
        event.preventDefault();
        newCompose();
      } else if (key === "r" && selected) {
        event.preventDefault();
        reply();
      } else if (key === "f" && selected) {
        event.preventDefault();
        forward();
      } else if (key === "e" && selected) {
        event.preventDefault();
        void moveCurrent(folderDestination(folders, "archive"));
      } else if (event.key === "Escape") {
        if (composeOpen) setComposeMinimized(true);
        else if (selected) backToList();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setLoading(true);
    setError("");
    const response = await webmail("/session", { method: "POST", body: JSON.stringify({ address: form.get("address"), password: form.get("password") }) });
    setLoading(false);
    if (!response.ok) {
      setError((await response.json().catch(() => ({}))).detail || "Mailbox login failed");
      return;
    }
    const data = await response.json();
    setAddress(data.address);
    setAuthenticated(true);
    await Promise.all([loadFolders(), loadCounts(), loadIdentity(), loadSignature(), loadMessages("INBOX", "", 0)]);
  }

  async function logout() {
    await webmail("/session", { method: "DELETE" });
    setAuthenticated(false);
    setAddress("");
    setDisplayName("");
    setSignatureHtml("");
    setMessages([]);
    setSelected(null);
    setAccountOpen(false);
  }

  async function openMessage(row: MessageRow, pushHistory = true) {
    setSelected(row);
    if (pushHistory) {
      const url = new URL(window.location.href);
      url.searchParams.set("folder", folder);
      url.searchParams.set("message", row.uid);
      window.history.pushState({ folder, message: row.uid }, "", `${url.pathname}?${url.searchParams}`);
    }
    const response = await webmail(`/messages/${row.uid}?folder=${encodeURIComponent(folder)}`);
    if (response.ok) {
      const full = await response.json();
      setSelected(full);
      setMessages((items) => items.map((item) => (item.uid === row.uid ? { ...item, seen: true } : item)));
      void loadCounts();
    }
  }

  function backToList() {
    const params = new URLSearchParams(window.location.search);
    if (params.has("message") && window.history.length > 1) window.history.back();
    else setSelected(null);
  }

  function newCompose(seed: Partial<ComposeState> = {}) {
    let next: ComposeState = { ...emptyCompose, ...seed, attachments: seed.attachments || [] };
    const explicitSeed = Boolean(seed.to || seed.subject || seed.bodyText || seed.bodyHtml || seed.in_reply_to);
    if (!explicitSeed && address) {
      try {
        const stored = window.localStorage.getItem(draftStorageKey(address));
        if (stored) {
          next = { ...next, ...JSON.parse(stored) };
          setNotice("Restored your unfinished draft");
        }
      } catch {
        // Ignore malformed local draft data.
      }
    }
    setCompose(next);
    setShowCcBcc(Boolean(next.cc || next.bcc));
    setComposeMinimized(false);
    setComposeExpanded(false);
    setComposeOpen(true);
  }

  function reply() {
    if (!selected) return;
    const target = addressOnly(selected.reply_to || selected.from);
    const subject = /^re:/i.test(selected.subject) ? selected.subject : `Re: ${selected.subject}`;
    const refs = [selected.references, selected.message_id].filter(Boolean).join(" ");
    const quote = `\n\n--- Original message ---\nFrom: ${selected.from}\nDate: ${selected.date}\nSubject: ${selected.subject}\n\n${selected.body_text || ""}`;
    newCompose({ to: target, subject, bodyText: quote, bodyHtml: textToHtml(quote), in_reply_to: selected.message_id, references: refs });
  }

  function forward() {
    if (!selected) return;
    const subject = /^fwd:/i.test(selected.subject) ? selected.subject : `Fwd: ${selected.subject}`;
    const body = `\n\n--- Forwarded message ---\nFrom: ${selected.from}\nTo: ${selected.to}\nDate: ${selected.date}\nSubject: ${selected.subject}\n\n${selected.body_text || ""}`;
    newCompose({ subject, bodyText: body, bodyHtml: textToHtml(body) });
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    const response = await webmail("/send-rich", {
      method: "POST",
      body: JSON.stringify({
        to: splitAddresses(compose.to),
        cc: splitAddresses(compose.cc),
        bcc: splitAddresses(compose.bcc),
        subject: compose.subject,
        body_text: compose.bodyText || stripHtml(compose.bodyHtml),
        body_html: compose.bodyHtml,
        signature_html: signatureHtml,
        attachments: compose.attachments,
        in_reply_to: compose.in_reply_to,
        references: compose.references,
      }),
    });
    setLoading(false);
    if (!response.ok) {
      setError((await response.json().catch(() => ({}))).detail || "Unable to send message");
      return;
    }
    if (address) window.localStorage.removeItem(draftStorageKey(address));
    setCompose(emptyCompose);
    setComposeOpen(false);
    setNotice("Message sent");
    await loadCounts();
    if (folderKind(folder) === "sent") await loadMessages(folder, query, offset);
  }

  async function saveDraft() {
    const response = await webmail("/drafts", {
      method: "POST",
      body: JSON.stringify({ to: splitAddresses(compose.to), cc: splitAddresses(compose.cc), subject: compose.subject, body_text: compose.bodyText || stripHtml(compose.bodyHtml) }),
    });
    if (!response.ok) {
      setError((await response.json().catch(() => ({}))).detail || "Unable to save draft");
      return;
    }
    if (address) window.localStorage.removeItem(draftStorageKey(address));
    setComposeOpen(false);
    setCompose(emptyCompose);
    setNotice("Draft saved");
    await Promise.all([loadFolders(), loadCounts()]);
    if (folderKind(folder) === "drafts") await loadMessages(folder, query, offset);
  }

  function discardDraft() {
    if (address) window.localStorage.removeItem(draftStorageKey(address));
    setCompose(emptyCompose);
    setComposeOpen(false);
    setNotice("Draft discarded");
  }

  async function attachFiles(files: FileList | null) {
    if (!files) return;
    const rows: ComposeState["attachments"] = [];
    for (const file of Array.from(files)) {
      if (file.size > 10 * 1024 * 1024) {
        setError(`${file.name} is larger than 10 MB`);
        continue;
      }
      const content_b64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
      });
      rows.push({ filename: file.name, content_type: file.type || "application/octet-stream", content_b64 });
    }
    setCompose((current) => ({ ...current, attachments: [...current.attachments, ...rows].slice(0, 20) }));
  }

  function countFor(name: string) {
    return folderCounts.find((item) => item.name === name);
  }

  function openFolder(name: string, pushHistory = true) {
    setFolder(name);
    setInboxView("primary");
    setQuery("");
    setOnlyUnread(false);
    setOnlyAttachments(false);
    setSelected(null);
    setSelectedUids(new Set());
    setMobileFolders(false);
    if (pushHistory) {
      const url = new URL(window.location.href);
      url.search = "";
      url.searchParams.set("folder", name);
      window.history.pushState({ folder: name }, "", `${url.pathname}?${url.searchParams}`);
    }
    void loadMessages(name, "", 0);
  }

  async function setRowFlags(row: MessageRow, payload: { seen?: boolean; flagged?: boolean }) {
    const response = await webmail(`/messages/${row.uid}/flags?folder=${encodeURIComponent(folder)}`, { method: "PATCH", body: JSON.stringify(payload) });
    if (!response.ok) return;
    setMessages((items) => items.map((item) => (item.uid === row.uid ? { ...item, ...payload } : item)));
    if (selected?.uid === row.uid) setSelected((current) => (current ? { ...current, ...payload } : current));
    if (payload.seen !== undefined) void loadCounts();
  }

  async function moveRow(row: MessageRow, destination: string) {
    const response = await webmail(`/messages/${row.uid}/move?folder=${encodeURIComponent(folder)}`, { method: "POST", body: JSON.stringify({ destination }) });
    if (!response.ok) {
      setError((await response.json().catch(() => ({}))).detail || "Unable to move message");
      return;
    }
    setMessages((items) => items.filter((item) => item.uid !== row.uid));
    if (selected?.uid === row.uid) setSelected(null);
    setNotice(destination.toLowerCase().includes("archive") ? "Conversation archived" : `Moved to ${destination}`);
    void loadCounts();
  }

  async function deleteRow(row: MessageRow) {
    const response = await webmail(`/messages/${row.uid}?folder=${encodeURIComponent(folder)}`, { method: "DELETE" });
    if (!response.ok) {
      setError((await response.json().catch(() => ({}))).detail || "Unable to delete message");
      return;
    }
    setMessages((items) => items.filter((item) => item.uid !== row.uid));
    if (selected?.uid === row.uid) setSelected(null);
    setNotice(folderKind(folder) === "trash" ? "Message deleted permanently" : "Moved to Trash");
    void loadCounts();
  }

  async function moveCurrent(destination: string) {
    if (selected) await moveRow(selected, destination);
  }

  function toggleSelection(uid: string) {
    setSelectedUids((current) => {
      const next = new Set(current);
      if (next.has(uid)) next.delete(uid);
      else next.add(uid);
      return next;
    });
  }

  async function bulkFlags(payload: { seen?: boolean; flagged?: boolean }) {
    if (!selectedUids.size) return;
    await Promise.all(Array.from(selectedUids).map((uid) => webmail(`/messages/${uid}/flags?folder=${encodeURIComponent(folder)}`, { method: "PATCH", body: JSON.stringify(payload) })));
    setSelectedUids(new Set());
    await Promise.all([loadCounts(), loadMessages(folder, query, offset)]);
  }

  async function bulkMove(destination: string) {
    if (!selectedUids.size) return;
    await Promise.all(Array.from(selectedUids).map((uid) => webmail(`/messages/${uid}/move?folder=${encodeURIComponent(folder)}`, { method: "POST", body: JSON.stringify({ destination }) })));
    setSelectedUids(new Set());
    setNotice(`Moved ${selectedUids.size} message${selectedUids.size === 1 ? "" : "s"}`);
    await Promise.all([loadFolders(), loadCounts(), loadMessages(folder, query, offset)]);
  }

  async function bulkDelete() {
    if (!selectedUids.size) return;
    await Promise.all(Array.from(selectedUids).map((uid) => webmail(`/messages/${uid}?folder=${encodeURIComponent(folder)}`, { method: "DELETE" })));
    setSelectedUids(new Set());
    setNotice("Messages moved to Trash");
    await Promise.all([loadFolders(), loadCounts(), loadMessages(folder, query, offset)]);
  }

  function downloadAttachment(item: MessageRow["attachments"][number]) {
    if (!selected) return;
    window.open(`${API}/webmail/messages/${selected.uid}/attachments/${item.index}?folder=${encodeURIComponent(folder)}`, "_blank", "noopener,noreferrer");
  }

  const visibleMessages = useMemo(() => {
    let items = messages;
    if (inboxView === "starred") items = items.filter((row) => row.flagged);
    if (inboxView === "attachments") items = items.filter((row) => row.attachments?.length);
    if (onlyUnread) items = items.filter((row) => !row.seen);
    if (onlyAttachments) items = items.filter((row) => row.attachments?.length);
    return items;
  }, [inboxView, messages, onlyAttachments, onlyUnread]);

  const allVisibleSelected = visibleMessages.length > 0 && visibleMessages.every((row) => selectedUids.has(row.uid));
  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + messages.length, total);
  const archiveFolder = folderDestination(folders, "archive");
  const primaryFolders = folders.slice(0, 6);
  const moreFolders = folders.slice(6);
  const inboxUnseen = countFor("INBOX")?.unseen || 0;

  function toggleSelectAll() {
    if (allVisibleSelected) setSelectedUids(new Set());
    else setSelectedUids(new Set(visibleMessages.map((row) => row.uid)));
  }

  if (authenticated === null) {
    return <div className="grid min-h-screen place-items-center bg-[#f6f8fc]"><Loader2 className="animate-spin text-[#0b57d0]" /></div>;
  }

  if (!authenticated) {
    return (
      <div className="min-h-screen bg-[#f6f8fc] px-4 py-8 sm:py-10">
        <div className="mx-auto grid min-h-[80vh] max-w-5xl overflow-hidden rounded-[30px] border border-[#e0e5ea] bg-white shadow-[0_24px_80px_rgba(32,33,36,.10)] lg:grid-cols-[1.08fr_.92fr]">
          <section className="hidden bg-[linear-gradient(145deg,#123a38,#0d2d2b)] p-10 text-white lg:flex lg:flex-col lg:justify-between">
            <div>
              <div className="grid h-12 w-12 place-items-center rounded-2xl bg-[#d8c56a] font-black text-[#153d38]">!T</div>
              <h1 className="mt-8 max-w-md text-4xl font-semibold tracking-tight">Your business inbox, without the learning curve.</h1>
              <p className="mt-4 max-w-lg text-sm leading-7 text-[#c7d7d1]">A familiar Gmail-like workflow backed by your own !thute hosted mailbox, IMAP storage and authenticated SMTP delivery.</p>
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs text-[#bdd0c9]"><span>✓ Familiar compose</span><span>✓ Search & attachments</span><span>✓ Stars & archive</span><span>✓ Mobile ready</span></div>
          </section>
          <section className="flex items-center p-6 sm:p-10">
            <form onSubmit={login} className="mx-auto w-full max-w-sm">
              <div className="grid h-11 w-11 place-items-center rounded-xl bg-[#123a38] font-black text-[#d8c56a]">!T</div>
              <p className="mt-6 text-[11px] font-semibold uppercase tracking-[.16em] text-[#6f777b]">!thute Mail</p>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight">Sign in</h2>
              <p className="mt-2 text-sm leading-6 text-[#6f777b]">Use your full mailbox address and mailbox password.</p>
              {error ? <div className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs font-semibold text-red-700">{error}</div> : null}
              <div className="mt-7 space-y-4">
                <input name="address" type="email" required autoComplete="username" className="w-full rounded-xl border border-[#dadce0] bg-white px-4 py-3 text-sm outline-none focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8]" placeholder="you@company.co.ls" />
                <input name="password" type="password" required autoComplete="current-password" className="w-full rounded-xl border border-[#dadce0] bg-white px-4 py-3 text-sm outline-none focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8]" placeholder="Mailbox password" />
                <button disabled={loading} className="flex w-full items-center justify-center gap-2 rounded-full bg-[#0b57d0] px-4 py-3 text-sm font-semibold text-white hover:bg-[#0842a0]"><Mail size={16} />{loading ? "Signing in…" : "Sign in"}</button>
              </div>
            </form>
          </section>
        </div>
      </div>
    );
  }

  const rowHeight = density === "compact" ? "min-h-[40px]" : "min-h-[50px]";

  return (
    <div className="h-screen overflow-hidden bg-[#f6f8fc] text-[#202124]">
      <header className="flex h-16 items-center gap-2 px-2 sm:px-4">
        <button onClick={() => { if (window.innerWidth >= 1024) { setSidebarCollapsed((value) => { const next = !value; window.localStorage.setItem("ithute-webmail-sidebar", next ? "collapsed" : "expanded"); return next; }); } else setMobileFolders(true); }} className="grid h-10 w-10 shrink-0 place-items-center rounded-full hover:bg-[#e9eef6]" title="Main menu"><Menu size={20} /></button>
        <div className={`flex items-center gap-2 ${sidebarCollapsed ? "lg:min-w-[52px]" : "lg:min-w-[188px]"}`}>
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#123a38] text-xs font-black text-[#d8c56a]">!T</div>
          {!sidebarCollapsed ? <div className="hidden sm:block"><p className="text-[16px] font-semibold">!thute Mail</p><p className="text-[9px] uppercase tracking-[.12em] text-[#6f777b]">Webmail</p></div> : null}
        </div>

        <div className="relative mx-auto w-full max-w-[760px]">
          <form onSubmit={(event) => { event.preventDefault(); setInboxView("primary"); void loadMessages(folder, query, 0); const url = new URL(window.location.href); url.searchParams.set("folder", folder); if (query.trim()) url.searchParams.set("q", query.trim()); else url.searchParams.delete("q"); url.searchParams.delete("message"); window.history.pushState({}, "", `${url.pathname}?${url.searchParams}`); }} className="flex h-12 items-center rounded-full bg-[#eaf1fb] px-4 shadow-[inset_0_0_0_1px_transparent] focus-within:bg-white focus-within:shadow-[0_1px_2px_rgba(60,64,67,.2),0_1px_6px_rgba(60,64,67,.15)] sm:rounded-xl">
            <Search size={18} className="shrink-0 text-[#5f6368]" />
            <input ref={searchRef} value={query} onChange={(event) => setQuery(event.target.value)} className="min-w-0 flex-1 bg-transparent px-3 text-sm outline-none" placeholder="Search mail" />
            {query ? <button type="button" onClick={() => { setQuery(""); void loadMessages(folder, "", 0); }} className="grid h-8 w-8 place-items-center rounded-full hover:bg-black/5" title="Clear search"><X size={16} /></button> : null}
            <button type="button" onClick={() => setSearchOptionsOpen((value) => !value)} className="grid h-8 w-8 place-items-center rounded-full hover:bg-black/5" title="Search options"><SlidersHorizontal size={17} /></button>
          </form>
          {searchOptionsOpen ? (
            <div className="absolute right-0 top-14 z-40 w-[min(92vw,360px)] rounded-2xl border border-[#dadce0] bg-white p-4 shadow-2xl">
              <p className="text-sm font-semibold">Search options</p>
              <label className="mt-4 flex items-center justify-between gap-3 text-sm"><span>Unread only</span><input type="checkbox" checked={onlyUnread} onChange={(event) => setOnlyUnread(event.target.checked)} /></label>
              <label className="mt-3 flex items-center justify-between gap-3 text-sm"><span>Has attachment</span><input type="checkbox" checked={onlyAttachments} onChange={(event) => setOnlyAttachments(event.target.checked)} /></label>
              <div className="mt-4 flex justify-end gap-2"><button type="button" onClick={() => { setOnlyUnread(false); setOnlyAttachments(false); }} className="rounded-full px-3 py-2 text-xs font-semibold text-[#5f6368] hover:bg-[#f1f3f4]">Clear</button><button type="button" onClick={() => setSearchOptionsOpen(false)} className="rounded-full bg-[#0b57d0] px-4 py-2 text-xs font-semibold text-white">Done</button></div>
            </div>
          ) : null}
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-0.5">
          <Link href="/help" className="hidden h-10 w-10 place-items-center rounded-full hover:bg-[#e9eef6] md:grid" title="Help"><CircleHelp size={19} /></Link>
          <Link href="/webmail/settings" className="grid h-10 w-10 place-items-center rounded-full hover:bg-[#e9eef6]" title="Settings"><Settings size={19} /></Link>
          <button onClick={() => void Promise.all([loadMessages(folder, query, offset), loadCounts()])} className="hidden h-10 w-10 place-items-center rounded-full hover:bg-[#e9eef6] sm:grid" title="Refresh"><RefreshCw size={18} className={loading ? "animate-spin" : ""} /></button>
          <div className="relative">
            <button onClick={() => setAccountOpen((value) => !value)} className="ml-1 grid h-9 w-9 place-items-center rounded-full bg-[#123a38] text-[11px] font-semibold text-white" title={displayName || address}>{initials(displayName || address)}</button>
            {accountOpen ? (
              <div className="absolute right-0 top-12 z-50 w-72 rounded-2xl border border-[#dadce0] bg-white p-3 shadow-2xl">
                <div className="rounded-xl bg-[#f6f8fc] p-3"><p className="truncate text-sm font-semibold">{displayName || address}</p>{displayName ? <p className="mt-0.5 truncate text-xs text-[#6f777b]">{address}</p> : null}</div>
                <Link onClick={() => setAccountOpen(false)} href="/webmail/settings" className="mt-2 flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm hover:bg-[#f1f3f4]"><Settings size={16} />Webmail settings</Link>
                <button onClick={() => void logout()} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm hover:bg-[#f1f3f4]"><LogOut size={16} />Sign out</button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <div className="flex h-[calc(100vh-4rem)]">
        <aside className={`${mobileFolders ? "fixed inset-0 z-50 flex" : "hidden"} w-full bg-black/30 lg:static lg:flex lg:w-auto lg:bg-transparent`}>
          <button aria-label="Close sidebar overlay" className="absolute inset-0 lg:hidden" onClick={() => setMobileFolders(false)} />
          <div className={`relative flex h-full w-[84%] max-w-[286px] flex-col bg-[#f6f8fc] pb-3 transition-all lg:w-full ${sidebarCollapsed ? "lg:w-[72px] lg:px-2" : "lg:w-[256px] lg:px-3"}`}>
            <div className="mb-1 flex items-center justify-between px-2 pt-2 lg:hidden"><span className="text-sm font-semibold">!thute Mail</span><button className="grid h-10 w-10 place-items-center rounded-full" onClick={() => setMobileFolders(false)}><X size={18} /></button></div>
            <button onClick={() => { newCompose(); setMobileFolders(false); }} className={`mb-4 mt-2 flex items-center gap-3 rounded-2xl bg-[#c2e7ff] text-sm font-semibold text-[#001d35] shadow-sm transition hover:shadow-md ${sidebarCollapsed ? "h-14 w-14 justify-center p-0" : "w-fit min-w-[142px] px-5 py-4"}`} title="Compose"><PenLine size={18} />{!sidebarCollapsed ? "Compose" : null}</button>

            <div className="space-y-0.5 overflow-y-auto">
              <button onClick={() => { if (folder !== "INBOX") openFolder("INBOX"); setInboxView("starred"); }} className={`flex w-full items-center rounded-r-full py-2 text-left text-sm ${sidebarCollapsed ? "justify-center px-2" : "gap-4 px-4"} ${inboxView === "starred" ? "bg-[#d3e3fd] font-semibold text-[#001d35]" : "text-[#3c4043] hover:bg-[#e8eaed]"}`} title="Starred"><Star size={17} />{!sidebarCollapsed ? <span>Starred</span> : null}</button>
              {primaryFolders.map((item) => {
                const count = countFor(item.name);
                return <button key={item.name} onClick={() => openFolder(item.name)} className={`flex w-full items-center rounded-r-full py-2 text-left text-sm ${sidebarCollapsed ? "justify-center px-2" : "gap-4 px-4"} ${folder === item.name && inboxView === "primary" ? "bg-[#d3e3fd] font-semibold text-[#001d35]" : "text-[#3c4043] hover:bg-[#e8eaed]"}`} title={item.name}>{folderIcon(item.name)}{!sidebarCollapsed ? <><span className="min-w-0 flex-1 truncate">{item.name}</span>{count?.unseen ? <span className="text-xs font-semibold">{count.unseen}</span> : null}</> : null}</button>;
              })}
              {moreFolders.length ? <><button onClick={() => setShowMoreFolders((value) => !value)} className={`flex w-full items-center rounded-r-full py-2 text-sm text-[#3c4043] hover:bg-[#e8eaed] ${sidebarCollapsed ? "justify-center px-2" : "gap-4 px-4"}`}><ChevronDown size={17} className={showMoreFolders ? "rotate-180" : ""} />{!sidebarCollapsed ? "More" : null}</button>{showMoreFolders ? moreFolders.map((item) => <button key={item.name} onClick={() => openFolder(item.name)} className={`flex w-full items-center rounded-r-full py-2 text-left text-sm ${sidebarCollapsed ? "justify-center px-2" : "gap-4 px-4"} ${folder === item.name ? "bg-[#d3e3fd] font-semibold" : "hover:bg-[#e8eaed]"}`}>{folderIcon(item.name)}{!sidebarCollapsed ? <span className="min-w-0 flex-1 truncate">{item.name}</span> : null}</button>) : null}</> : null}
            </div>

            <div className="mt-auto border-t border-[#e0e3e7] pt-3"><Link href="/webmail/settings" className={`flex items-center rounded-r-full py-2 text-sm text-[#3c4043] hover:bg-[#e8eaed] ${sidebarCollapsed ? "justify-center px-2" : "gap-4 px-4"}`}><Settings size={17} />{!sidebarCollapsed ? "Settings" : null}</Link>{!sidebarCollapsed ? <div className="mt-2 px-4"><p className="truncate text-xs font-semibold">{displayName || address}</p>{displayName ? <p className="truncate text-[10px] text-[#6f777b]">{address}</p> : null}</div> : null}</div>
          </div>
        </aside>

        <main className="min-w-0 flex-1 overflow-hidden rounded-tl-2xl bg-white shadow-[0_1px_3px_rgba(60,64,67,.08)]">
          {selected ? (
            <div className="h-full overflow-y-auto">
              <div className="sticky top-0 z-10 flex h-12 items-center gap-1 border-b border-[#edf0f2] bg-white/95 px-3 backdrop-blur">
                <button className="grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f3f4]" onClick={backToList} title="Back"><ChevronLeft size={18} /></button>
                {folderKind(folder) === "archive" ? <button onClick={() => void moveCurrent("INBOX")} className="grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f3f4]" title="Move to Inbox"><ArchiveRestore size={17} /></button> : <button onClick={() => void moveCurrent(archiveFolder)} className="grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f3f4]" title="Archive"><Archive size={17} /></button>}
                <button onClick={() => void deleteRow(selected)} className="grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f3f4]" title="Delete"><Trash2 size={17} /></button>
                <button onClick={() => void setRowFlags(selected, { seen: false })} className="grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f3f4]" title="Mark unread"><Mail size={17} /></button>
                <div className="ml-auto flex items-center gap-1"><button onClick={() => void setRowFlags(selected, { flagged: !selected.flagged })} className={`grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f3f4] ${selected.flagged ? "text-amber-500" : "text-[#5f6368]"}`} title="Star"><Star size={17} className={selected.flagged ? "fill-current" : ""} /></button><button className="grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f3f4]" title="More"><MoreVertical size={18} /></button></div>
              </div>
              <article className="mx-auto max-w-5xl px-4 py-6 sm:px-10 sm:py-8">
                <h1 className="text-[24px] font-normal leading-tight sm:text-[28px]">{selected.subject || "(no subject)"}</h1>
                <div className="mt-7 flex items-start gap-3"><div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[#d3e3fd] text-xs font-bold text-[#0b57d0]">{initials(selected.from)}</div><div className="min-w-0 flex-1"><div className="flex items-start gap-2"><div className="min-w-0"><p className="break-words text-sm font-semibold">{selected.from}</p><p className="mt-0.5 text-xs text-[#6f777b]">to {selected.to || address}{selected.cc ? ` · cc ${selected.cc}` : ""}</p></div><p className="ml-auto hidden whitespace-nowrap text-xs text-[#6f777b] sm:block">{selected.date}</p></div></div></div>
                {selected.attachments?.length ? <div className="mt-6 flex flex-wrap gap-2">{selected.attachments.map((attachment) => <button key={attachment.index} onClick={() => downloadAttachment(attachment)} className="flex items-center gap-2 rounded-xl border border-[#dadce0] bg-white px-3 py-2 text-xs font-medium hover:bg-[#f8f9fa]"><Paperclip size={14} /><span>{attachment.filename}</span><span className="text-[#6f777b]">{humanBytes(attachment.size)}</span><Download size={13} /></button>)}</div> : null}
                <div className="mt-9 whitespace-pre-wrap break-words text-sm leading-7 text-[#202124]">{selected.body_text ?? selected.snippet}</div>
                <div className="mt-12 flex flex-wrap gap-2"><button onClick={reply} className="flex items-center gap-2 rounded-full border border-[#dadce0] bg-white px-5 py-2.5 text-sm font-semibold hover:bg-[#f8f9fa]"><Reply size={16} />Reply</button><button onClick={forward} className="rounded-full border border-[#dadce0] bg-white px-5 py-2.5 text-sm font-semibold hover:bg-[#f8f9fa]">Forward</button></div>
              </article>
            </div>
          ) : (
            <div className="flex h-full flex-col">
              <div className="flex h-12 shrink-0 items-center border-b border-[#edf0f2] px-2 sm:px-3">
                <label className="grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f3f4]" title="Select all"><input type="checkbox" checked={allVisibleSelected} onChange={toggleSelectAll} className="h-4 w-4 accent-[#0b57d0]" /></label>
                {selectedUids.size ? <><button onClick={() => void bulkMove(archiveFolder)} className="grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f3f4]" title="Archive selected"><Archive size={17} /></button><button onClick={() => void bulkDelete()} className="grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f3f4]" title="Delete selected"><Trash2 size={17} /></button><button onClick={() => void bulkFlags({ seen: false })} className="grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f3f4]" title="Mark unread"><Mail size={17} /></button><button onClick={() => void bulkFlags({ flagged: true })} className="grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f3f4]" title="Star"><Star size={17} /></button><span className="ml-2 text-xs text-[#5f6368]">{selectedUids.size} selected</span></> : <><button onClick={() => void Promise.all([loadMessages(folder, query, offset), loadCounts()])} className="grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f3f4]" title="Refresh"><RefreshCw size={17} className={loading ? "animate-spin" : ""} /></button><button className="grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f3f4]" title="More"><MoreVertical size={17} /></button></>}
                <div className="ml-auto flex items-center gap-1 text-xs text-[#5f6368]"><span className="mr-2 hidden sm:inline">{pageStart}-{pageEnd} of {total}</span><button disabled={offset === 0 || loading} onClick={() => void loadMessages(folder, query, Math.max(0, offset - PAGE_SIZE))} className="grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f3f4] disabled:opacity-30"><ChevronLeft size={17} /></button><button disabled={offset + PAGE_SIZE >= total || loading} onClick={() => void loadMessages(folder, query, offset + PAGE_SIZE)} className="grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f3f4] disabled:opacity-30"><ChevronRight size={17} /></button></div>
              </div>

              {folderKind(folder) === "inbox" ? <div className="flex h-14 shrink-0 items-end overflow-x-auto border-b border-[#edf0f2] px-1 sm:px-4">{(["primary", "starred", "attachments"] as InboxView[]).map((view) => <button key={view} onClick={() => setInboxView(view)} className={`relative flex h-full min-w-[118px] items-center justify-center gap-2 px-3 text-sm capitalize sm:min-w-[160px] ${inboxView === view ? "font-semibold text-[#0b57d0]" : "text-[#5f6368] hover:bg-[#f8fafd]"}`}>{view === "primary" ? <Inbox size={17} /> : view === "starred" ? <Star size={17} /> : <Paperclip size={17} />}{view}{view === "primary" && inboxUnseen ? <span className="rounded-full bg-[#d3e3fd] px-1.5 py-0.5 text-[10px]">{inboxUnseen}</span> : null}{inboxView === view ? <span className="absolute inset-x-4 bottom-0 h-[3px] rounded-t bg-[#0b57d0]" /> : null}</button>)}</div> : null}

              <div className="min-h-0 flex-1 overflow-y-auto">
                {error ? <div className="m-3 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700"><span className="flex-1">{error}</span><button onClick={() => setError("")}><X size={14} /></button></div> : null}
                {visibleMessages.map((row) => {
                  const checked = selectedUids.has(row.uid);
                  return (
                    <div key={row.uid} className={`group relative border-b border-[#eef0f2] ${row.seen ? "bg-white" : "bg-[#f7faff]"} hover:z-10 hover:bg-[#f2f6fc] hover:shadow-[0_1px_4px_rgba(60,64,67,.22)]`}>
                      <div className={`hidden items-center px-2 sm:flex sm:px-3 ${rowHeight}`}>
                        <label className="grid h-8 w-8 shrink-0 place-items-center rounded-full hover:bg-[#e5e9ef]" title="Select"><input type="checkbox" checked={checked} onChange={() => toggleSelection(row.uid)} className="h-4 w-4 accent-[#0b57d0]" /></label>
                        <button onClick={() => void setRowFlags(row, { flagged: !row.flagged })} className={`grid h-8 w-8 shrink-0 place-items-center rounded-full hover:bg-[#e5e9ef] ${row.flagged ? "text-amber-500" : "text-[#9aa0a6]"}`} title="Star"><Star size={16} className={row.flagged ? "fill-current" : ""} /></button>
                        <button onClick={() => void openMessage(row)} className="grid min-w-0 flex-1 grid-cols-[minmax(130px,220px)_minmax(0,1fr)_auto] items-center gap-3 py-1 text-left"><span className={`truncate text-sm ${row.seen ? "font-medium" : "font-bold"}`}>{senderName(row.from)}</span><span className="min-w-0 truncate text-sm"><span className={row.seen ? "font-medium" : "font-bold"}>{row.subject || "(no subject)"}</span><span className="text-[#6f777b]"> — {row.snippet}</span>{row.attachments?.length ? <span className="ml-2 inline-flex max-w-[180px] items-center gap-1 rounded-md bg-[#eef1f3] px-2 py-0.5 text-[10px] text-[#5f6368]"><Paperclip size={10} /><span className="truncate">{row.attachments[0]?.filename}</span></span> : null}</span><span className={`row-date whitespace-nowrap text-xs ${row.seen ? "text-[#777]" : "font-semibold text-[#3c4043]"}`}>{shortDate(row.date)}</span></button>
                        <div className="row-actions absolute right-2 hidden items-center rounded-lg bg-[#f2f6fc] pl-2 group-hover:flex"><button onClick={() => void moveRow(row, archiveFolder)} className="grid h-8 w-8 place-items-center rounded-full hover:bg-[#e5e9ef]" title="Archive"><Archive size={15} /></button><button onClick={() => void deleteRow(row)} className="grid h-8 w-8 place-items-center rounded-full hover:bg-[#e5e9ef]" title="Delete"><Trash2 size={15} /></button><button onClick={() => void setRowFlags(row, { seen: row.seen ? false : true })} className="grid h-8 w-8 place-items-center rounded-full hover:bg-[#e5e9ef]" title={row.seen ? "Mark unread" : "Mark read"}>{row.seen ? <Mail size={15} /> : <MailOpen size={15} />}</button></div>
                      </div>

                      <div className="flex min-h-[76px] items-start gap-2 px-2 py-2.5 sm:hidden"><button onClick={() => void openMessage(row)} className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[#d3e3fd] text-xs font-bold text-[#0b57d0]">{initials(row.from)}</button><button onClick={() => void openMessage(row)} className="min-w-0 flex-1 text-left"><div className="flex items-center gap-2"><span className={`min-w-0 flex-1 truncate text-sm ${row.seen ? "font-medium" : "font-bold"}`}>{senderName(row.from)}</span><span className={`text-[11px] ${row.seen ? "text-[#777]" : "font-semibold"}`}>{shortDate(row.date)}</span></div><p className={`mt-0.5 truncate text-sm ${row.seen ? "font-medium" : "font-bold"}`}>{row.subject || "(no subject)"}</p><p className="mt-0.5 truncate text-xs text-[#6f777b]">{row.snippet}</p></button><button onClick={() => void setRowFlags(row, { flagged: !row.flagged })} className={`grid h-8 w-8 shrink-0 place-items-center rounded-full ${row.flagged ? "text-amber-500" : "text-[#9aa0a6]"}`}><Star size={16} className={row.flagged ? "fill-current" : ""} /></button></div>
                    </div>
                  );
                })}
                {!loading && !visibleMessages.length ? <div className="grid h-72 place-items-center text-center"><div><Inbox className="mx-auto text-[#9aa0a6]" /><p className="mt-3 text-sm font-semibold">No messages here</p><p className="mt-1 text-xs text-[#6f777b]">Nothing matches this mailbox view.</p></div></div> : null}
              </div>
            </div>
          )}
        </main>
      </div>

      {composeOpen ? <MailCompose address={address} compose={compose} setCompose={setCompose} loading={loading} minimized={composeMinimized} expanded={composeExpanded} showCcBcc={showCcBcc} signatureHtml={signatureHtml} onMinimized={setComposeMinimized} onExpanded={setComposeExpanded} onShowCcBcc={setShowCcBcc} onClose={() => setComposeOpen(false)} onDiscard={discardDraft} onSaveDraft={() => void saveDraft()} onSend={sendMessage} onAttach={(files) => void attachFiles(files)} /> : null}

      {notice ? <div className="fixed bottom-5 left-1/2 z-[100] -translate-x-1/2 rounded-lg bg-[#323232] px-4 py-3 text-sm font-medium text-white shadow-xl sm:left-5 sm:translate-x-0">{notice}</div> : null}
    </div>
  );
}
