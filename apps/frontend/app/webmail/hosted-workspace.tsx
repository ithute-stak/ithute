"use client";

import Link from "next/link";
import {
  Archive,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  FolderClosed,
  Forward,
  Inbox,
  LogOut,
  Mail,
  Menu,
  MoreVertical,
  Paperclip,
  PenLine,
  RefreshCw,
  Reply,
  ReplyAll,
  Search,
  Send,
  Settings2,
  Star,
  Trash2,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { MailCompose } from "./mail-compose";
import { MailPrivacyNote } from "./mail-content";
import { MailLoading } from "./mail-loading";
import { MailSettingsPanel, resolvedTheme, useMailPreferences } from "./mail-preferences";
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
  type Folder,
  type FolderCount,
  type InboxView,
  type MessageRow,
} from "./mail-types";

type SessionInfo = {
  authenticated?: boolean;
  address: string;
};

type ComposeKind = "new" | "reply" | "reply-all" | "forward";

function folderIcon(name: string) {
  const kind = folderKind(name);
  if (kind === "inbox") return <Inbox size={17} />;
  if (kind === "sent") return <Send size={17} />;
  if (kind === "drafts") return <FileText size={17} />;
  if (kind === "trash") return <Trash2 size={17} />;
  if (kind === "archive") return <Archive size={17} />;
  return <FolderClosed size={17} />;
}

function folderDestination(folders: Folder[], kind: "archive" | "trash") {
  const names = folders.map((item) => item.name);
  const preferred = kind === "archive" ? ["Archive", "All Mail"] : ["Trash", "Deleted Items", "Deleted"];
  return preferred.find((name) => names.some((candidate) => candidate.toLowerCase() === name.toLowerCase())) || preferred[0];
}

function hasComposeContent(compose: ComposeState) {
  return Boolean(
    compose.to.trim() || compose.cc.trim() || compose.bcc.trim() || compose.subject.trim() ||
    compose.bodyText.trim() || compose.bodyHtml.trim() || compose.attachments.length,
  );
}

function normalizedRecipients(value: string) {
  return splitAddresses(value).map(addressOnly).filter(Boolean);
}

function unique(values: string[]) {
  const seen = new Set<string>();
  return values.filter((value) => {
    const key = value.toLowerCase();
    if (!value || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function quoteForReply(row: MessageRow) {
  const source = row.body_text || row.snippet || "";
  const header = `On ${row.date || "an earlier date"}, ${row.from} wrote:`;
  return {
    text: `\n\n${header}\n${source.split("\n").map((line) => `> ${line}`).join("\n")}`,
    html: `<br><br><div style="color:#64748b;font-size:12px">${textToHtml(header)}</div><blockquote style="margin:8px 0 0 0;border-left:3px solid #cbd5e1;padding-left:12px;color:#64748b">${textToHtml(source)}</blockquote>`,
  };
}

function quoteForForward(row: MessageRow) {
  const source = row.body_text || row.snippet || "";
  const header = `---------- Forwarded message ----------\nFrom: ${row.from}\nDate: ${row.date}\nSubject: ${row.subject}\nTo: ${row.to}${row.cc ? `\nCc: ${row.cc}` : ""}`;
  return {
    text: `\n\n${header}\n\n${source}`,
    html: `<br><br><div style="border-top:1px solid #d7dee8;padding-top:14px;color:#64748b;font-size:12px;line-height:1.65">${textToHtml(header)}</div><div style="margin-top:14px">${textToHtml(source)}</div>`,
  };
}

export function HostedMailWorkspace() {
  const { preferences, setPreferences, resetPreferences, ready: preferencesReady } = useMailPreferences();
  const searchRef = useRef<HTMLInputElement>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [checking, setChecking] = useState(true);
  const [loading, setLoading] = useState(false);
  const [messageLoading, setMessageLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [mobileFolders, setMobileFolders] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [onlyUnread, setOnlyUnread] = useState(false);
  const [onlyAttachments, setOnlyAttachments] = useState(false);

  const [displayName, setDisplayName] = useState("");
  const [displayNameDraft, setDisplayNameDraft] = useState("");
  const [signatureHtml, setSignatureHtml] = useState("");
  const [signatureDraft, setSignatureDraft] = useState("");
  const [savingSettings, setSavingSettings] = useState(false);

  const [folders, setFolders] = useState<Folder[]>([]);
  const [counts, setCounts] = useState<FolderCount[]>([]);
  const [folder, setFolder] = useState("INBOX");
  const [messages, setMessages] = useState<MessageRow[]>([]);
  const [selected, setSelected] = useState<MessageRow | null>(null);
  const [selectedUids, setSelectedUids] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [inboxView, setInboxView] = useState<InboxView>("primary");

  const [composeOpen, setComposeOpen] = useState(false);
  const [composeKind, setComposeKind] = useState<ComposeKind>("new");
  const [compose, setCompose] = useState<ComposeState>(emptyCompose);
  const [composeMinimized, setComposeMinimized] = useState(false);
  const [composeExpanded, setComposeExpanded] = useState(false);
  const [showCcBcc, setShowCcBcc] = useState(false);

  const theme = resolvedTheme(preferences.theme);
  const address = session?.address || "";

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    root.dataset.imailTheme = theme;
  }, [theme]);

  const loadFolders = useCallback(async () => {
    const response = await webmail("/folders");
    if (response.status === 401) { window.location.assign("/webmail"); return; }
    if (response.ok) setFolders((await response.json()).items || []);
  }, []);

  const loadCounts = useCallback(async () => {
    const response = await webmail("/folder-counts");
    if (response.status === 401) { window.location.assign("/webmail"); return; }
    if (response.ok) setCounts((await response.json()).items || []);
  }, []);

  const loadIdentity = useCallback(async () => {
    const response = await webmail("/identity");
    if (!response.ok) return;
    const value = String((await response.json()).display_name || "");
    setDisplayName(value);
    setDisplayNameDraft(value);
  }, []);

  const loadSignature = useCallback(async () => {
    const response = await webmail("/signature");
    if (!response.ok) return;
    const value = String((await response.json()).html || "");
    setSignatureHtml(value);
    setSignatureDraft(value);
  }, []);

  const loadMessages = useCallback(async (target: string, search = "", nextOffset = 0) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ folder: target, limit: String(PAGE_SIZE), offset: String(nextOffset) });
      if (search.trim()) params.set("q", search.trim());
      const response = await webmail(`/messages?${params}`);
      if (response.status === 401) { window.location.assign("/webmail"); return [] as MessageRow[]; }
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to load messages");
      const payload = await response.json();
      const items = (payload.items || []) as MessageRow[];
      setMessages(items);
      setTotal(Number(payload.total || 0));
      setOffset(nextOffset);
      setSelectedUids(new Set());
      return items;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load messages");
      return [] as MessageRow[];
    } finally {
      setLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    await Promise.all([loadFolders(), loadCounts(), loadMessages(folder, query, offset)]);
  }, [folder, loadCounts, loadFolders, loadMessages, offset, query]);

  async function openMessageByUid(uid: string, targetFolder: string, pushHistory: boolean, preview?: MessageRow) {
    if (preview) setSelected(preview);
    setMessageLoading(true);
    setError("");
    if (pushHistory) {
      const url = new URL(window.location.href);
      url.search = "";
      url.searchParams.set("folder", targetFolder);
      url.searchParams.set("message", uid);
      window.history.pushState({ folder: targetFolder, message: uid }, "", `${url.pathname}?${url.searchParams}`);
    }
    try {
      const response = await webmail(`/messages/${uid}?folder=${encodeURIComponent(targetFolder)}`);
      if (response.status === 401) { window.location.assign("/webmail"); return; }
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to open message");
      const full = (await response.json()) as MessageRow;
      setSelected(full);
      setMessages((items) => items.map((item) => item.uid === uid ? { ...item, seen: true } : item));
      void loadCounts();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to open message");
    } finally {
      setMessageLoading(false);
    }
  }

  async function openMessage(row: MessageRow) {
    await openMessageByUid(row.uid, folder, true, row);
  }

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const sessionResponse = await webmail("/session");
        if (!active) return;
        if (!sessionResponse.ok) { window.location.assign("/webmail"); return; }
        const sessionData = (await sessionResponse.json()) as SessionInfo;
        setSession(sessionData);

        const params = new URLSearchParams(window.location.search);
        const initialFolder = params.get("folder") || "INBOX";
        const initialQuery = params.get("q") || "";
        const initialMessage = params.get("message") || "";
        setFolder(initialFolder);
        setQuery(initialQuery);

        await Promise.all([loadFolders(), loadCounts(), loadIdentity(), loadSignature()]);
        const items = await loadMessages(initialFolder, initialQuery, 0);
        if (!active) return;
        if (initialMessage) {
          const preview = items.find((item) => item.uid === initialMessage);
          await openMessageByUid(initialMessage, initialFolder, false, preview);
        }
      } catch {
        if (active) setError("The mailbox could not be opened. Please refresh and try again.");
      } finally {
        if (active) setChecking(false);
      }
    })();
    return () => { active = false; };
  }, [loadCounts, loadFolders, loadIdentity, loadMessages, loadSignature]);

  useEffect(() => {
    const onPopState = () => {
      const params = new URLSearchParams(window.location.search);
      const nextFolder = params.get("folder") || "INBOX";
      const nextMessage = params.get("message") || "";
      const nextQuery = params.get("q") || "";
      if (nextFolder !== folder || nextQuery !== query) {
        setFolder(nextFolder);
        setQuery(nextQuery);
        setInboxView("primary");
        void loadMessages(nextFolder, nextQuery, 0).then((items) => {
          if (nextMessage) void openMessageByUid(nextMessage, nextFolder, false, items.find((item) => item.uid === nextMessage));
          else setSelected(null);
        });
      } else if (nextMessage) {
        void openMessageByUid(nextMessage, nextFolder, false, messages.find((item) => item.uid === nextMessage));
      } else {
        setSelected(null);
      }
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [folder, loadMessages, messages, query]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (!composeOpen || !address) return;
    const timer = window.setTimeout(() => {
      try {
        const key = draftStorageKey(address);
        if (hasComposeContent(compose)) window.localStorage.setItem(key, JSON.stringify(compose));
        else window.localStorage.removeItem(key);
      } catch {
        // Browser storage can be unavailable; the open composer still works.
      }
    }, 550);
    return () => window.clearTimeout(timer);
  }, [address, compose, composeOpen]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || isEditableTarget(event.target)) return;
      const key = event.key.toLowerCase();
      if (key === "/") { event.preventDefault(); searchRef.current?.focus(); }
      else if (key === "c") { event.preventDefault(); startNew(); }
      else if (key === "r" && selected) { event.preventDefault(); startReply(selected); }
      else if (key === "f" && selected) { event.preventDefault(); startForward(selected); }
      else if (event.key === "Escape" && selected) { event.preventDefault(); closeReader(); }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  function countFor(name: string) {
    const row = counts.find((item) => item.name.toLowerCase() === name.toLowerCase());
    if (!row) return 0;
    return folderKind(name) === "inbox" ? row.unseen : row.messages;
  }

  function closeReader() {
    setSelected(null);
    const url = new URL(window.location.href);
    url.searchParams.delete("message");
    window.history.pushState({ folder }, "", `${url.pathname}?${url.searchParams}`);
  }

  function openFolder(name: string, view: InboxView = "primary") {
    setFolder(name);
    setInboxView(view);
    setQuery("");
    setOnlyUnread(false);
    setOnlyAttachments(false);
    setSelected(null);
    setSelectedUids(new Set());
    setMobileFolders(false);
    const url = new URL(window.location.href);
    url.search = "";
    url.searchParams.set("folder", name);
    window.history.pushState({ folder: name }, "", `${url.pathname}?${url.searchParams}`);
    void loadMessages(name, "", 0);
  }

  function openVirtualView(view: InboxView) {
    if (folder !== "INBOX") {
      setFolder("INBOX");
      void loadMessages("INBOX", "", 0);
    }
    setInboxView(view);
    setSelected(null);
    setSelectedUids(new Set());
    setMobileFolders(false);
    const url = new URL(window.location.href);
    url.search = "";
    url.searchParams.set("folder", "INBOX");
    window.history.pushState({ folder: "INBOX", view }, "", `${url.pathname}?${url.searchParams}`);
  }

  async function setRowFlags(row: MessageRow, payload: { seen?: boolean; flagged?: boolean }) {
    const response = await webmail(`/messages/${row.uid}/flags?folder=${encodeURIComponent(folder)}`, { method: "PATCH", body: JSON.stringify(payload) });
    if (!response.ok) return;
    setMessages((items) => items.map((item) => item.uid === row.uid ? { ...item, ...payload } : item));
    if (selected?.uid === row.uid) setSelected((current) => current ? { ...current, ...payload } : current);
    if (payload.seen !== undefined) void loadCounts();
  }

  async function moveRow(row: MessageRow, destination: string) {
    const response = await webmail(`/messages/${row.uid}/move?folder=${encodeURIComponent(folder)}`, { method: "POST", body: JSON.stringify({ destination }) });
    if (!response.ok) { setError((await response.json().catch(() => ({}))).detail || "Unable to move message"); return; }
    setMessages((items) => items.filter((item) => item.uid !== row.uid));
    setSelectedUids((current) => { const next = new Set(current); next.delete(row.uid); return next; });
    if (selected?.uid === row.uid) closeReader();
    setNotice(destination.toLowerCase().includes("archive") ? "Conversation archived" : `Moved to ${destination}`);
    void loadCounts();
  }

  async function deleteRow(row: MessageRow) {
    const response = await webmail(`/messages/${row.uid}?folder=${encodeURIComponent(folder)}`, { method: "DELETE" });
    if (!response.ok) { setError((await response.json().catch(() => ({}))).detail || "Unable to delete message"); return; }
    setMessages((items) => items.filter((item) => item.uid !== row.uid));
    setSelectedUids((current) => { const next = new Set(current); next.delete(row.uid); return next; });
    if (selected?.uid === row.uid) closeReader();
    setNotice(folderKind(folder) === "trash" ? "Message deleted permanently" : "Moved to Trash");
    void loadCounts();
  }

  function toggleSelection(uid: string) {
    setSelectedUids((current) => {
      const next = new Set(current);
      if (next.has(uid)) next.delete(uid); else next.add(uid);
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
    const size = selectedUids.size;
    await Promise.all(Array.from(selectedUids).map((uid) => webmail(`/messages/${uid}/move?folder=${encodeURIComponent(folder)}`, { method: "POST", body: JSON.stringify({ destination }) })));
    setSelectedUids(new Set());
    setNotice(`Moved ${size} message${size === 1 ? "" : "s"}`);
    await Promise.all([loadCounts(), loadMessages(folder, query, offset)]);
  }

  async function bulkDelete() {
    if (!selectedUids.size) return;
    await Promise.all(Array.from(selectedUids).map((uid) => webmail(`/messages/${uid}?folder=${encodeURIComponent(folder)}`, { method: "DELETE" })));
    setSelectedUids(new Set());
    setNotice("Messages moved to Trash");
    await Promise.all([loadCounts(), loadMessages(folder, query, offset)]);
  }

  function openComposer(kind: ComposeKind, next: ComposeState) {
    setComposeKind(kind);
    setCompose(next);
    setShowCcBcc(Boolean(next.cc || next.bcc));
    setComposeMinimized(false);
    setComposeExpanded(preferences.composeFullscreen);
    setComposeOpen(true);
  }

  function startNew() {
    let next = { ...emptyCompose, attachments: [] } as ComposeState;
    if (address) {
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
    openComposer("new", next);
  }

  function startReply(row: MessageRow) {
    const quote = quoteForReply(row);
    const subject = /^re:/i.test(row.subject) ? row.subject : `Re: ${row.subject}`;
    const refs = [row.references, row.message_id].filter(Boolean).join(" ");
    openComposer("reply", { ...emptyCompose, to: addressOnly(row.reply_to || row.from), subject, bodyText: quote.text, bodyHtml: quote.html, in_reply_to: row.message_id, references: refs, attachments: [] });
  }

  function startReplyAll(row: MessageRow) {
    const own = address.toLowerCase();
    const sender = addressOnly(row.reply_to || row.from);
    const originalTo = normalizedRecipients(row.to).filter((value) => value.toLowerCase() !== own);
    const originalCc = normalizedRecipients(row.cc).filter((value) => value.toLowerCase() !== own);
    const quote = quoteForReply(row);
    const subject = /^re:/i.test(row.subject) ? row.subject : `Re: ${row.subject}`;
    const refs = [row.references, row.message_id].filter(Boolean).join(" ");
    openComposer("reply-all", { ...emptyCompose, to: unique([sender, ...originalTo]).join(", "), cc: unique(originalCc).join(", "), subject, bodyText: quote.text, bodyHtml: quote.html, in_reply_to: row.message_id, references: refs, attachments: [] });
  }

  function startForward(row: MessageRow) {
    const quote = quoteForForward(row);
    const subject = /^fwd?:/i.test(row.subject) ? row.subject : `Fwd: ${row.subject}`;
    openComposer("forward", { ...emptyCompose, subject, bodyText: quote.text, bodyHtml: quote.html, attachments: [] });
  }

  async function attachFiles(files: FileList | null) {
    if (!files) return;
    const rows: ComposeState["attachments"] = [];
    let totalBytes = compose.attachments.reduce((sum, item) => sum + Math.floor(item.content_b64.length * 0.75), 0);
    for (const file of Array.from(files)) {
      if (file.size > 10 * 1024 * 1024) { setError(`${file.name} is larger than 10 MB`); continue; }
      totalBytes += file.size;
      if (totalBytes > 15 * 1024 * 1024) { setError("Total attachment size cannot exceed 15 MB"); break; }
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

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await webmail("/send-rich", {
        method: "POST",
        body: JSON.stringify({
          to: splitAddresses(compose.to), cc: splitAddresses(compose.cc), bcc: splitAddresses(compose.bcc), subject: compose.subject,
          body_text: compose.bodyText || stripHtml(compose.bodyHtml), body_html: compose.bodyHtml, signature_html: signatureHtml,
          attachments: compose.attachments, in_reply_to: compose.in_reply_to, references: compose.references,
        }),
      });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to send message");
      if (address) window.localStorage.removeItem(draftStorageKey(address));
      setCompose(emptyCompose);
      setComposeOpen(false);
      setNotice("Message sent");
      await Promise.all([loadFolders(), loadCounts()]);
      if (folderKind(folder) === "sent") await loadMessages(folder, query, offset);
      if (selected && (composeKind === "reply" || composeKind === "reply-all")) setSelected((current) => current ? { ...current, answered: true } : current);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to send message");
    } finally {
      setLoading(false);
    }
  }

  async function saveDraft() {
    setLoading(true);
    try {
      const response = await webmail("/drafts", { method: "POST", body: JSON.stringify({ to: splitAddresses(compose.to), cc: splitAddresses(compose.cc), subject: compose.subject, body_text: compose.bodyText || stripHtml(compose.bodyHtml) }) });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to save draft");
      if (address) window.localStorage.removeItem(draftStorageKey(address));
      setCompose(emptyCompose);
      setComposeOpen(false);
      setNotice("Draft saved");
      await Promise.all([loadFolders(), loadCounts()]);
      if (folderKind(folder) === "drafts") await loadMessages(folder, query, offset);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save draft");
    } finally {
      setLoading(false);
    }
  }

  function discardDraft() {
    if (address) window.localStorage.removeItem(draftStorageKey(address));
    setCompose(emptyCompose);
    setComposeOpen(false);
    setNotice("Draft discarded");
  }

  async function saveAccountSettings() {
    setSavingSettings(true);
    setError("");
    try {
      const [identityResponse, signatureResponse] = await Promise.all([
        webmail("/identity", { method: "PUT", body: JSON.stringify({ display_name: displayNameDraft.trim() }) }),
        webmail("/signature", { method: "PUT", body: JSON.stringify({ html: signatureDraft }) }),
      ]);
      if (!identityResponse.ok || !signatureResponse.ok) throw new Error("Unable to save mailbox settings");
      setDisplayName(displayNameDraft.trim());
      setSignatureHtml(signatureDraft);
      setNotice("Account settings saved");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save mailbox settings");
    } finally {
      setSavingSettings(false);
    }
  }

  async function logout() {
    await webmail("/session", { method: "DELETE" });
    window.location.assign("/webmail");
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
  const densityClass = preferences.density === "compact" ? "py-2" : "py-3.5";
  const paneRight = preferences.readingPane === "right";
  const paneBottom = preferences.readingPane === "bottom";
  const noPane = preferences.readingPane === "none";
  const fontSize = preferences.fontScale === "small" ? "13px" : preferences.fontScale === "large" ? "16px" : "14px";

  function toggleSelectAll() {
    if (allVisibleSelected) setSelectedUids(new Set());
    else setSelectedUids(new Set(visibleMessages.map((row) => row.uid)));
  }

  if (checking || !preferencesReady || !session) {
    return <MailLoading label="Opening iMail" detail="Preparing your hosted business mailbox" />;
  }

  const reader = selected ? (
    <section className="flex min-h-0 flex-1 flex-col bg-white dark:bg-slate-900">
      <div className="flex h-13 shrink-0 items-center gap-1 border-b border-slate-200 px-3 dark:border-white/10 sm:px-4">
        <button type="button" onClick={closeReader} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Back to inbox"><ArrowLeft size={18} /></button>
        <button type="button" onClick={() => void setRowFlags(selected, { flagged: !selected.flagged })} className={`grid h-9 w-9 place-items-center rounded-full hover:bg-slate-100 dark:hover:bg-white/10 ${selected.flagged ? "text-amber-500" : "text-slate-500"}`} title="Star"><Star size={18} fill={selected.flagged ? "currentColor" : "none"} /></button>
        <button type="button" onClick={() => void setRowFlags(selected, { seen: !selected.seen })} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title={selected.seen ? "Mark unread" : "Mark read"}><Mail size={18} /></button>
        <button type="button" onClick={() => void moveRow(selected, archiveFolder)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Archive"><Archive size={18} /></button>
        <button type="button" onClick={() => void deleteRow(selected)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10" title="Delete"><Trash2 size={18} /></button>
        <span className="mx-1 h-5 w-px bg-slate-200 dark:bg-white/10" />
        <button type="button" onClick={() => startReply(selected)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Reply"><Reply size={18} /></button>
        <button type="button" onClick={() => startReplyAll(selected)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Reply all"><ReplyAll size={18} /></button>
        <button type="button" onClick={() => startForward(selected)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Forward"><Forward size={18} /></button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-7 sm:py-7 lg:px-9">
        {messageLoading ? <div className="py-12"><MailLoading compact label="Opening message" detail="Loading the full message securely" /></div> : (
          <article className="imail-message-reader mx-auto max-w-4xl">
            <h1 className="pr-4 text-[22px] font-black leading-tight tracking-tight text-slate-900 dark:text-white sm:text-[26px]">{selected.subject || "(no subject)"}</h1>
            <div className="mt-6 flex items-start gap-3">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#eaf1fb] text-sm font-black text-[#174ea6] dark:bg-blue-400/10 dark:text-blue-200">{initials(selected.from)}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-2"><span className="font-black text-slate-900 dark:text-white">{senderName(selected.from)}</span><span className="truncate text-xs text-slate-500">&lt;{addressOnly(selected.from)}&gt;</span></div>
                <p className="mt-1 text-xs text-slate-500">to {selected.to || address}{selected.cc ? ` • cc ${selected.cc}` : ""}</p>
              </div>
              <time className="shrink-0 text-xs font-medium text-slate-500">{selected.date ? shortDate(selected.date) : ""}</time>
            </div>

            <div className="mt-5"><MailPrivacyNote /></div>
            <div className="mt-6 min-h-[220px]">
              <div className="whitespace-pre-wrap break-words leading-7 text-slate-800 dark:text-slate-100" style={{ fontSize }}>{selected.body_text || selected.snippet || ""}</div>
            </div>

            {selected.attachments?.length ? (
              <div className="mt-8 border-t border-slate-200 pt-5 dark:border-white/10">
                <p className="mb-3 flex items-center gap-2 text-xs font-black uppercase tracking-[.12em] text-slate-500"><Paperclip size={14} /> {selected.attachments.length} attachment{selected.attachments.length === 1 ? "" : "s"}</p>
                <div className="flex flex-wrap gap-2">
                  {selected.attachments.map((item) => (
                    <button key={`${selected.uid}-${item.index}`} type="button" onClick={() => downloadAttachment(item)} className="group flex max-w-[300px] items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-left transition hover:border-blue-300 hover:bg-blue-50 dark:border-white/10 dark:bg-white/[.035] dark:hover:bg-blue-400/10">
                      <span className="grid h-9 w-9 place-items-center rounded-lg bg-white text-slate-500 shadow-sm dark:bg-white/10"><FileText size={17} /></span>
                      <span className="min-w-0 flex-1"><span className="block truncate text-xs font-bold text-slate-800 dark:text-slate-100">{item.filename}</span><span className="block text-[10px] text-slate-500">{humanBytes(item.size || 0)}</span></span>
                      <Download size={15} className="text-slate-400 group-hover:text-[#0b57d0]" />
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="mt-9 flex flex-wrap gap-2 border-t border-slate-200 pt-5 dark:border-white/10">
              <button type="button" onClick={() => startReply(selected)} className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-4 text-sm font-bold text-slate-700 transition hover:border-blue-300 hover:bg-blue-50 dark:border-white/10 dark:text-slate-200 dark:hover:bg-blue-400/10"><Reply size={16} /> Reply</button>
              <button type="button" onClick={() => startReplyAll(selected)} className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-4 text-sm font-bold text-slate-700 transition hover:border-blue-300 hover:bg-blue-50 dark:border-white/10 dark:text-slate-200 dark:hover:bg-blue-400/10"><ReplyAll size={16} /> Reply all</button>
              <button type="button" onClick={() => startForward(selected)} className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-4 text-sm font-bold text-slate-700 transition hover:border-blue-300 hover:bg-blue-50 dark:border-white/10 dark:text-slate-200 dark:hover:bg-blue-400/10"><Forward size={16} /> Forward</button>
            </div>
          </article>
        )}
      </div>
    </section>
  ) : (
    <section className="hidden min-h-0 flex-1 place-items-center bg-white dark:bg-slate-900 lg:grid">
      <div className="max-w-sm text-center"><span className="mx-auto grid h-16 w-16 place-items-center rounded-[22px] bg-[#eaf1fb] text-[#174ea6] dark:bg-blue-400/10 dark:text-blue-200"><Mail size={28} /></span><h2 className="mt-4 text-lg font-black text-slate-800 dark:text-white">Your message opens here</h2><p className="mt-1 text-sm leading-6 text-slate-500">Choose a message from the inbox, or change the reading pane in Settings.</p></div>
    </section>
  );

  const messageList = (
    <section className="flex min-h-0 flex-1 flex-col bg-[#f6f8f7] dark:bg-[#0e1514]">
      <div className="shrink-0 px-3 pb-2 pt-3 sm:px-4">
        <form onSubmit={(event) => { event.preventDefault(); setSelected(null); setInboxView("primary"); void loadMessages(folder, query, 0); const url = new URL(window.location.href); url.searchParams.set("folder", folder); url.searchParams.delete("message"); if (query.trim()) url.searchParams.set("q", query.trim()); else url.searchParams.delete("q"); window.history.pushState({}, "", `${url.pathname}?${url.searchParams}`); }} className="mx-auto flex h-12 max-w-4xl items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 shadow-sm transition focus-within:border-blue-400 focus-within:ring-4 focus-within:ring-blue-500/10 dark:border-white/10 dark:bg-white/[.05]">
          <Search size={18} className="shrink-0 text-slate-400" />
          <input ref={searchRef} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search mail" className="min-w-0 flex-1 bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400 dark:text-white" />
          {query ? <button type="button" onClick={() => { setQuery(""); void loadMessages(folder, "", 0); }} className="grid h-8 w-8 place-items-center rounded-full text-slate-400 hover:bg-slate-100 dark:hover:bg-white/10"><X size={16} /></button> : null}
        </form>
      </div>

      <div className="relative flex h-11 shrink-0 items-center gap-2 border-y border-slate-200 bg-white px-3 dark:border-white/10 dark:bg-slate-900 sm:px-4">
        <label className="grid h-8 w-8 shrink-0 place-items-center rounded-full hover:bg-slate-100 dark:hover:bg-white/10" title="Select all"><input type="checkbox" checked={allVisibleSelected} onChange={toggleSelectAll} className="h-4 w-4 accent-[#0b57d0]" /></label>
        {selectedUids.size ? (
          <div className="flex min-w-0 flex-1 items-center gap-1">
            <button type="button" onClick={() => void bulkMove(archiveFolder)} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100" title="Archive selected"><Archive size={16} /></button>
            <button type="button" onClick={() => void bulkDelete()} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-red-50 hover:text-red-600" title="Delete selected"><Trash2 size={16} /></button>
            <button type="button" onClick={() => void bulkFlags({ seen: false })} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100" title="Mark unread"><Mail size={16} /></button>
            <button type="button" onClick={() => void bulkFlags({ flagged: true })} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100" title="Star selected"><Star size={16} /></button>
            <span className="truncate text-[10px] font-bold text-slate-500">{selectedUids.size} selected</span>
          </div>
        ) : (
          <div className="min-w-0 flex-1"><p className="truncate text-xs font-black uppercase tracking-[.12em] text-slate-600 dark:text-slate-300">{inboxView === "primary" ? folder : inboxView}</p><p className="text-[10px] font-medium text-slate-400">{visibleMessages.length} loaded message{visibleMessages.length === 1 ? "" : "s"}</p></div>
        )}
        <button type="button" onClick={() => void refresh()} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Refresh"><RefreshCw size={16} className={loading ? "animate-spin" : ""} /></button>
        <button type="button" onClick={() => setFilterOpen((value) => !value)} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="More"><MoreVertical size={16} /></button>
        <div className="hidden items-center gap-0.5 text-[10px] text-slate-500 xl:flex"><span className="mr-1">{pageStart}-{pageEnd} of {total}</span><button disabled={offset === 0 || loading} onClick={() => void loadMessages(folder, query, Math.max(0, offset - PAGE_SIZE))} className="grid h-8 w-8 place-items-center rounded-full hover:bg-slate-100 disabled:opacity-30"><ChevronLeft size={15} /></button><button disabled={offset + PAGE_SIZE >= total || loading} onClick={() => void loadMessages(folder, query, offset + PAGE_SIZE)} className="grid h-8 w-8 place-items-center rounded-full hover:bg-slate-100 disabled:opacity-30"><ChevronRight size={15} /></button></div>
        {filterOpen ? <div className="absolute right-3 top-10 z-30 w-56 rounded-xl border border-slate-200 bg-white p-3 text-xs shadow-xl dark:border-white/10 dark:bg-slate-900"><label className="flex items-center justify-between gap-3 py-2"><span className="font-semibold text-slate-700 dark:text-slate-200">Unread only</span><input type="checkbox" checked={onlyUnread} onChange={(event) => setOnlyUnread(event.target.checked)} /></label><label className="flex items-center justify-between gap-3 py-2"><span className="font-semibold text-slate-700 dark:text-slate-200">Has attachment</span><input type="checkbox" checked={onlyAttachments} onChange={(event) => setOnlyAttachments(event.target.checked)} /></label><button type="button" onClick={() => { setOnlyUnread(false); setOnlyAttachments(false); setFilterOpen(false); }} className="mt-2 w-full rounded-lg bg-slate-100 px-3 py-2 font-bold text-slate-600 hover:bg-slate-200 dark:bg-white/10 dark:text-slate-200">Clear filters</button></div> : null}
      </div>

      {loading && !messages.length ? <div className="grid flex-1 place-items-center p-6"><MailLoading compact label="Loading mail" detail={`Reading ${folder}`} /></div> : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          {error ? <div className="m-3 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700"><span className="flex-1">{error}</span><button onClick={() => setError("")}><X size={14} /></button></div> : null}
          {!visibleMessages.length ? <div className="grid min-h-[360px] place-items-center p-8 text-center"><div><span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-white text-slate-400 shadow-sm dark:bg-white/5"><Inbox size={24} /></span><p className="mt-4 text-sm font-black text-slate-700 dark:text-slate-200">No messages here</p><p className="mt-1 text-xs text-slate-500">{query ? "Try a different search." : "This mailbox view is currently empty."}</p></div></div> : visibleMessages.map((row) => {
            const checked = selectedUids.has(row.uid);
            return (
              <div key={`${folder}-${row.uid}`} className={`group flex cursor-pointer items-center gap-2 border-b border-slate-200/80 px-2 transition hover:z-[1] hover:bg-white hover:shadow-sm dark:border-white/[.07] dark:hover:bg-white/[.045] ${row.seen ? "bg-[#f7f9f8] dark:bg-[#0e1514]" : "bg-white dark:bg-slate-900"} ${densityClass} ${selected?.uid === row.uid ? "border-l-[3px] border-l-[#0b57d0] bg-[#eef4ff] dark:bg-blue-400/[.06]" : "border-l-[3px] border-l-transparent"}`} onClick={() => void openMessage(row)}>
                <label onClick={(event) => event.stopPropagation()} className="grid h-8 w-8 shrink-0 place-items-center rounded-full hover:bg-slate-100 dark:hover:bg-white/10" title="Select"><input type="checkbox" checked={checked} onChange={() => toggleSelection(row.uid)} className="h-4 w-4 accent-[#0b57d0]" /></label>
                <button type="button" onClick={(event) => { event.stopPropagation(); void setRowFlags(row, { flagged: !row.flagged }); }} className={`grid h-8 w-8 shrink-0 place-items-center rounded-full transition hover:bg-slate-100 dark:hover:bg-white/10 ${row.flagged ? "text-amber-500" : "text-slate-300 group-hover:text-slate-500"}`}><Star size={16} fill={row.flagged ? "currentColor" : "none"} /></button>
                <span className="hidden h-8 w-8 shrink-0 place-items-center rounded-full bg-[#eaf1fb] text-[10px] font-black text-[#174ea6] sm:grid dark:bg-blue-400/10 dark:text-blue-200">{initials(row.from)}</span>
                <div className="min-w-0 flex-1 sm:grid sm:grid-cols-[minmax(120px,170px)_1fr_auto] sm:items-center sm:gap-3">
                  <div className={`truncate text-sm ${row.seen ? "font-medium text-slate-700 dark:text-slate-300" : "font-black text-slate-950 dark:text-white"}`}>{senderName(row.from)}</div>
                  <div className="min-w-0"><div className={`truncate text-sm ${row.seen ? "font-medium text-slate-700 dark:text-slate-300" : "font-bold text-slate-950 dark:text-white"}`}>{row.subject || "(no subject)"}</div>{preferences.showPreview ? <p className="mt-0.5 truncate text-[11px] text-slate-500">{row.snippet}</p> : null}</div>
                  <div className="mt-1 flex items-center gap-2 sm:mt-0 sm:justify-end">{row.attachments?.length ? <Paperclip size={13} className="text-slate-400" /> : null}<time className={`text-[10px] ${row.seen ? "font-medium text-slate-400" : "font-black text-[#174ea6] dark:text-blue-200"}`}>{shortDate(row.date)}</time></div>
                </div>
                <div className="hidden shrink-0 items-center gap-0.5 opacity-0 transition group-hover:opacity-100 xl:flex"><button type="button" onClick={(event) => { event.stopPropagation(); void moveRow(row, archiveFolder); }} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100" title="Archive"><Archive size={15} /></button><button type="button" onClick={(event) => { event.stopPropagation(); void deleteRow(row); }} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-red-50 hover:text-red-600" title="Delete"><Trash2 size={15} /></button><button type="button" onClick={(event) => { event.stopPropagation(); void setRowFlags(row, { seen: !row.seen }); }} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100" title={row.seen ? "Mark unread" : "Mark read"}><Mail size={15} /></button></div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );

  return (
    <main className={`imail-hosted-workspace min-h-screen ${theme === "dark" ? "bg-[#0b1110] text-slate-100" : theme === "ithute" ? "bg-[#eef4f1] text-slate-900" : "bg-[#f4f6f8] text-slate-900"}`}>
      <header className="sticky top-0 z-40 flex h-16 items-center gap-2 border-b border-slate-200 bg-white/95 px-2 backdrop-blur dark:border-white/10 dark:bg-slate-950/95 sm:px-4">
        <button className="grid h-10 w-10 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10 lg:hidden" onClick={() => setMobileFolders(true)} aria-label="Open folders"><Menu size={20} /></button>
        <div className="grid h-10 w-10 place-items-center rounded-[14px] bg-gradient-to-br from-emerald-950 to-emerald-700 text-xs font-black text-amber-300 shadow-sm">iM</div>
        <div className="min-w-0"><p className="truncate text-sm font-black text-slate-950 dark:text-white">{displayName || address}</p><p className="truncate text-[10px] font-semibold text-slate-500">Ithute hosted mailbox</p></div>
        <span className="ml-2 hidden rounded-full border border-blue-900/10 bg-[#eaf1fb] px-2.5 py-1 text-[10px] font-black uppercase tracking-[.1em] text-[#174ea6] sm:inline-flex">iMail</span>
        <div className="ml-auto flex items-center gap-0.5">
          <button type="button" onClick={() => void refresh()} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Refresh"><RefreshCw size={17} className={loading ? "animate-spin" : ""} /></button>
          <button type="button" onClick={() => setSettingsOpen(true)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Settings"><Settings2 size={17} /></button>
          <button type="button" onClick={() => void logout()} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10" title="Sign out"><LogOut size={17} /></button>
        </div>
      </header>

      <div className="flex h-[calc(100vh-4rem)] min-h-0">
        <aside className={`${mobileFolders ? "fixed inset-0 z-50 flex" : "hidden"} w-full bg-black/30 lg:static lg:flex lg:w-[244px] lg:shrink-0 lg:bg-transparent`}>
          <button aria-label="Close folders" className="absolute inset-0 lg:hidden" onClick={() => setMobileFolders(false)} />
          <div className="relative flex h-full w-[84%] max-w-[286px] flex-col border-r border-slate-200 bg-[#f8fafd] p-2.5 dark:border-white/10 dark:bg-[#0e1514] lg:w-[244px] lg:max-w-none">
            <div className="mb-1 flex items-center justify-between px-2 lg:hidden"><span className="text-sm font-black">Folders</span><button type="button" onClick={() => setMobileFolders(false)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100"><X size={18} /></button></div>
            <button type="button" onClick={() => { startNew(); setMobileFolders(false); }} className="mb-3 flex h-12 w-full items-center gap-3 rounded-2xl bg-[#eaf1fb] px-4 text-sm font-black text-[#174ea6] shadow-sm transition hover:bg-[#dce8fb]" title="Compose"><PenLine size={18} /> Compose</button>
            <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto">
              <button type="button" onClick={() => openVirtualView("starred")} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm ${inboxView === "starred" ? "bg-[#eaf1fb] font-black text-[#174ea6]" : "font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5"}`} title="Starred"><Star size={17} /><span className="min-w-0 flex-1 truncate">Starred</span></button>
              <button type="button" onClick={() => openVirtualView("attachments")} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm ${inboxView === "attachments" ? "bg-[#eaf1fb] font-black text-[#174ea6]" : "font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5"}`} title="Attachments"><Paperclip size={17} /><span className="min-w-0 flex-1 truncate">Attachments</span></button>
              {folders.map((item) => {
                const active = folder === item.name && inboxView === "primary";
                const count = countFor(item.name);
                return <button key={item.name} type="button" onClick={() => openFolder(item.name)} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm ${active ? "bg-[#eaf1fb] font-black text-[#174ea6]" : "font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5"}`} title={item.name}>{folderIcon(item.name)}<span className="min-w-0 flex-1 truncate">{item.name}</span>{count ? <span className={`text-[10px] ${active ? "font-black text-[#174ea6]" : "font-bold text-slate-400"}`}>{count}</span> : null}</button>;
              })}
            </nav>
            <div className="mt-2 rounded-2xl border border-slate-200 bg-white p-3 dark:border-white/10 dark:bg-white/[.035]"><p className="truncate text-xs font-black text-slate-800 dark:text-white">{displayName || address}</p>{displayName ? <p className="mt-0.5 truncate text-[10px] font-medium text-slate-500">{address}</p> : null}<Link href="/webmail/settings" className="mt-2 inline-flex text-[10px] font-black text-[#174ea6] hover:underline">Full mailbox settings</Link></div>
          </div>
        </aside>

        <div className="min-w-0 flex-1 overflow-hidden">
          {noPane ? (
            <div className="flex h-full min-h-0">{selected ? reader : messageList}</div>
          ) : (
            <>
              <div className={`hidden h-full min-h-0 lg:grid ${paneRight ? "grid-cols-[minmax(390px,46%)_1fr]" : paneBottom ? "grid-rows-[minmax(300px,48%)_1fr]" : "grid-cols-[minmax(390px,46%)_1fr]"}`}>{messageList}{reader}</div>
              <div className="flex h-full min-h-0 lg:hidden">{selected ? reader : messageList}</div>
            </>
          )}
        </div>
      </div>

      {composeOpen ? <MailCompose address={address} compose={compose} setCompose={setCompose} loading={loading} minimized={composeMinimized} expanded={composeExpanded} showCcBcc={showCcBcc} signatureHtml={signatureHtml} onMinimized={setComposeMinimized} onExpanded={setComposeExpanded} onShowCcBcc={setShowCcBcc} onClose={() => setComposeOpen(false)} onDiscard={discardDraft} onSaveDraft={() => void saveDraft()} onSend={sendMessage} onAttach={(files) => void attachFiles(files)} /> : null}

      <MailSettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} preferences={preferences} setPreferences={setPreferences} onReset={resetPreferences} displayName={displayNameDraft} signatureHtml={signatureDraft} onDisplayNameChange={setDisplayNameDraft} onSignatureChange={setSignatureDraft} onSaveAccount={() => void saveAccountSettings()} savingAccount={savingSettings} />

      {notice ? <div className="fixed bottom-5 left-1/2 z-[120] -translate-x-1/2 rounded-xl bg-slate-900 px-4 py-3 text-sm font-bold text-white shadow-xl sm:left-5 sm:translate-x-0">{notice}</div> : null}
    </main>
  );
}
