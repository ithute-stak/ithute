"use client";

import Link from "next/link";
import {
  Archive,
  ArrowLeft,
  ChevronDown,
  Download,
  Eye,
  EyeOff,
  FileText,
  FolderClosed,
  Forward,
  Inbox,
  Loader2,
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
  Server,
  Settings2,
  ShieldCheck,
  Star,
  Trash2,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { ExternalMailCompose } from "../external-compose";
import { MailContent, MailPrivacyNote } from "../mail-content";
import { MailLoading } from "../mail-loading";
import { MailSettingsPanel, resolvedTheme, useMailPreferences } from "../mail-preferences";
import {
  API,
  addressOnly,
  emptyCompose,
  humanBytes,
  senderName,
  shortDate,
  splitAddresses,
  stripHtml,
  textToHtml,
  type ComposeState,
  type Contact,
} from "../mail-types";

const PAGE_SIZE = 50;

type Folder = { name: string; raw?: string };
type FolderCount = { name: string; messages: number; unseen: number };
type Attachment = { index: number; filename: string; content_type: string; size: number };
type MessageRow = {
  uid: string;
  message_id: string;
  in_reply_to?: string;
  references?: string;
  from: string;
  to: string;
  cc: string;
  reply_to?: string;
  subject: string;
  date: string;
  seen: boolean;
  flagged: boolean;
  answered: boolean;
  draft?: boolean;
  snippet: string;
  attachments: Attachment[];
  body_text?: string;
};
type SessionInfo = {
  authenticated: boolean;
  address: string;
  username: string;
  display_name: string;
  imap_host: string;
  imap_port: number;
  imap_security: string;
  smtp_host: string;
  smtp_port: number;
  smtp_security: string;
};

type ComposeKind = "new" | "reply" | "reply-all" | "forward";

async function external(path: string, init?: RequestInit) {
  return fetch(`${API}/webmail/external${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
}

function initials(value: string) {
  return senderName(value).split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map((item) => item[0]?.toUpperCase()).join("") || "M";
}

function folderKind(name: string) {
  const lower = name.toLowerCase();
  if (lower === "inbox") return "inbox";
  if (lower.includes("sent")) return "sent";
  if (lower.includes("draft")) return "drafts";
  if (lower.includes("trash") || lower.includes("deleted") || lower === "bin") return "trash";
  if (lower.includes("archive") || lower.includes("all mail")) return "archive";
  return "folder";
}

function folderIcon(name: string) {
  const kind = folderKind(name);
  if (kind === "inbox") return <Inbox size={17} />;
  if (kind === "sent") return <Send size={17} />;
  if (kind === "drafts") return <FileText size={17} />;
  if (kind === "trash") return <Trash2 size={17} />;
  if (kind === "archive") return <Archive size={17} />;
  return <FolderClosed size={17} />;
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

export default function ExternalWebmailPage() {
  const { preferences, setPreferences, resetPreferences, ready: preferencesReady } = useMailPreferences();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [checking, setChecking] = useState(true);
  const [loading, setLoading] = useState(false);
  const [messageLoading, setMessageLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [mobileFolders, setMobileFolders] = useState(false);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [username, setUsername] = useState("");
  const [imapHost, setImapHost] = useState("");
  const [imapPort, setImapPort] = useState("993");
  const [imapSecurity, setImapSecurity] = useState("ssl");
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState("465");
  const [smtpSecurity, setSmtpSecurity] = useState("ssl");

  const [folders, setFolders] = useState<Folder[]>([]);
  const [counts, setCounts] = useState<FolderCount[]>([]);
  const [folder, setFolder] = useState("INBOX");
  const [messages, setMessages] = useState<MessageRow[]>([]);
  const [selected, setSelected] = useState<MessageRow | null>(null);
  const [query, setQuery] = useState("");

  const [composeOpen, setComposeOpen] = useState(false);
  const [compose, setCompose] = useState<ComposeState>(emptyCompose);
  const [composeKind, setComposeKind] = useState<ComposeKind>("new");
  const [composeMinimized, setComposeMinimized] = useState(false);
  const [composeExpanded, setComposeExpanded] = useState(false);
  const [showCcBcc, setShowCcBcc] = useState(false);
  const [signatureHtml, setSignatureHtml] = useState("");
  const [signatureDraft, setSignatureDraft] = useState("");
  const [displayNameDraft, setDisplayNameDraft] = useState("");
  const [savingSettings, setSavingSettings] = useState(false);

  const theme = resolvedTheme(preferences.theme);

  useEffect(() => {
    const root = document.documentElement;
    const wantsDark = theme === "dark";
    root.classList.toggle("dark", wantsDark);
    root.dataset.imailTheme = theme;
  }, [theme]);

  const countFor = useCallback((name: string) => {
    const row = counts.find((item) => item.name.toLowerCase() === name.toLowerCase());
    if (!row) return 0;
    return folderKind(name) === "inbox" ? row.unseen : row.messages;
  }, [counts]);

  const loadFolders = useCallback(async () => {
    const [foldersResponse, countsResponse] = await Promise.all([external("/folders"), external("/folder-counts")]);
    if (foldersResponse.status === 401 || countsResponse.status === 401) { setSession(null); return; }
    if (foldersResponse.ok) setFolders((await foldersResponse.json()).items || []);
    if (countsResponse.ok) setCounts((await countsResponse.json()).items || []);
  }, []);

  const loadMessages = useCallback(async (target: string, search = "") => {
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({ folder: target, limit: String(PAGE_SIZE), offset: "0" });
      if (search.trim()) params.set("q", search.trim());
      const response = await external(`/messages?${params}`);
      if (response.status === 401) { setSession(null); return; }
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to load messages");
      const data = await response.json();
      setMessages(data.items || []);
      setSelected(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load messages");
    } finally { setLoading(false); }
  }, []);

  const loadPreferences = useCallback(async () => {
    const [signatureResponse, identityResponse] = await Promise.all([external("/signature"), external("/identity")]);
    if (signatureResponse.ok) {
      const data = await signatureResponse.json();
      setSignatureHtml(String(data.html || ""));
      setSignatureDraft(String(data.html || ""));
    }
    if (identityResponse.ok) {
      const data = await identityResponse.json();
      const name = String(data.display_name || "");
      setDisplayNameDraft(name);
    }
  }, []);

  const refresh = useCallback(async () => {
    await Promise.all([loadFolders(), loadMessages(folder, query)]);
  }, [folder, loadFolders, loadMessages, query]);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const response = await external("/session");
        if (!active) return;
        if (!response.ok) { setSession(null); return; }
        const data = await response.json();
        setSession(data);
        setDisplayNameDraft(String(data.display_name || ""));
        await Promise.all([loadFolders(), loadMessages("INBOX"), loadPreferences()]);
      } catch { if (active) setSession(null); }
      finally { if (active) setChecking(false); }
    })();
    return () => { active = false; };
  }, [loadFolders, loadMessages, loadPreferences]);

  useEffect(() => {
    if (!session) return;
    const timer = window.setInterval(() => { void loadFolders(); }, 20000);
    return () => window.clearInterval(timer);
  }, [loadFolders, session]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3500);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const inferredDomain = useMemo(() => email.trim().toLowerCase().split("@")[1] || "", [email]);

  function useDomainDefaults() {
    if (!inferredDomain) { setError("Enter the email address first so iMail can determine the domain."); return; }
    const host = `mail.${inferredDomain}`;
    setUsername(email.trim().toLowerCase()); setImapHost(host); setImapPort("993"); setImapSecurity("ssl");
    setSmtpHost(host); setSmtpPort("465"); setSmtpSecurity("ssl"); setAdvanced(true); setError("");
  }

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setError("");
    try {
      const address = email.trim().toLowerCase();
      const domain = address.split("@")[1] || "";
      const defaultHost = domain ? `mail.${domain}` : "";
      const response = await external("/session", { method: "POST", body: JSON.stringify({
        address, password, display_name: displayName.trim(), username: username.trim() || address,
        imap_host: imapHost.trim() || defaultHost, imap_port: Number(imapPort || 993), imap_security: imapSecurity,
        smtp_host: smtpHost.trim() || defaultHost, smtp_port: Number(smtpPort || 465), smtp_security: smtpSecurity,
      }) });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Could not connect to this external mailbox.");
      const data = await response.json();
      setSession(data); setDisplayNameDraft(String(data.display_name || "")); setFolder("INBOX"); setPassword("");
      await Promise.all([loadFolders(), loadMessages("INBOX"), loadPreferences()]);
      setNotice("Mailbox connected securely");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to connect external mailbox"); }
    finally { setLoading(false); }
  }

  async function logout() {
    await external("/session", { method: "DELETE" });
    setSession(null); setMessages([]); setFolders([]); setCounts([]); setSelected(null); setNotice("External mailbox disconnected");
  }

  async function openMessage(row: MessageRow) {
    setSelected(row); setMessageLoading(true);
    try {
      const response = await external(`/messages/${row.uid}?folder=${encodeURIComponent(folder)}`);
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to open message");
      const full = await response.json();
      setSelected(full);
      setMessages((current) => current.map((item) => item.uid === row.uid ? { ...item, seen: true } : item));
      void loadFolders();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to open message"); }
    finally { setMessageLoading(false); }
  }

  async function toggleStar(row: MessageRow) {
    const response = await external(`/messages/${row.uid}/flags?folder=${encodeURIComponent(folder)}`, { method: "PATCH", body: JSON.stringify({ flagged: !row.flagged }) });
    if (response.ok) {
      const updated = await response.json();
      setMessages((current) => current.map((item) => item.uid === row.uid ? { ...item, ...updated } : item));
      if (selected?.uid === row.uid) setSelected((current) => current ? { ...current, ...updated } : current);
    }
  }

  async function toggleSeen(row: MessageRow) {
    const response = await external(`/messages/${row.uid}/flags?folder=${encodeURIComponent(folder)}`, { method: "PATCH", body: JSON.stringify({ seen: !row.seen }) });
    if (response.ok) {
      setMessages((current) => current.map((item) => item.uid === row.uid ? { ...item, seen: !row.seen } : item));
      if (selected?.uid === row.uid) setSelected((current) => current ? { ...current, seen: !row.seen } : current);
      void loadFolders();
    }
  }

  async function remove(row: MessageRow) {
    const response = await external(`/messages/${row.uid}?folder=${encodeURIComponent(folder)}`, { method: "DELETE" });
    if (!response.ok) { setError((await response.json().catch(() => ({}))).detail || "Unable to delete message"); return; }
    setSelected(null); await refresh(); setNotice("Message moved to Trash");
  }

  function openComposer(kind: ComposeKind, next: ComposeState) {
    setComposeKind(kind); setCompose(next); setComposeOpen(true); setComposeMinimized(false);
    setComposeExpanded(preferences.composeFullscreen); setShowCcBcc(Boolean(next.cc || next.bcc));
  }

  function startNew() {
    openComposer("new", emptyCompose);
  }

  function startReply(row: MessageRow) {
    const quote = quoteForReply(row);
    const subject = /^re:/i.test(row.subject) ? row.subject : `Re: ${row.subject}`;
    const refs = [row.references, row.message_id].filter(Boolean).join(" ");
    const signatureText = stripHtml(signatureHtml);
    openComposer("reply", { ...emptyCompose, to: addressOnly(row.reply_to || row.from), subject, in_reply_to: row.message_id, references: refs, bodyText: `${signatureText ? `\n\n${signatureText}` : ""}${quote.text}`, bodyHtml: `${signatureHtml ? `<br><br>${signatureHtml}` : ""}${quote.html}` });
  }

  function startReplyAll(row: MessageRow) {
    if (!session) return;
    const own = session.address.toLowerCase();
    const originalTo = normalizedRecipients(row.to).filter((value) => value.toLowerCase() !== own);
    const originalCc = normalizedRecipients(row.cc).filter((value) => value.toLowerCase() !== own);
    const sender = addressOnly(row.reply_to || row.from);
    const quote = quoteForReply(row);
    const subject = /^re:/i.test(row.subject) ? row.subject : `Re: ${row.subject}`;
    const refs = [row.references, row.message_id].filter(Boolean).join(" ");
    const signatureText = stripHtml(signatureHtml);
    openComposer("reply-all", { ...emptyCompose, to: unique([sender, ...originalTo]).join(", "), cc: unique(originalCc).join(", "), subject, in_reply_to: row.message_id, references: refs, bodyText: `${signatureText ? `\n\n${signatureText}` : ""}${quote.text}`, bodyHtml: `${signatureHtml ? `<br><br>${signatureHtml}` : ""}${quote.html}` });
  }

  async function startForward(row: MessageRow) {
    const quote = quoteForForward(row);
    const subject = /^fwd?:/i.test(row.subject) ? row.subject : `Fwd: ${row.subject}`;
    const signatureText = stripHtml(signatureHtml);
    openComposer("forward", { ...emptyCompose, subject, bodyText: `${signatureText ? `\n\n${signatureText}` : ""}${quote.text}`, bodyHtml: `${signatureHtml ? `<br><br>${signatureHtml}` : ""}${quote.html}` });
    if (!row.attachments?.length) return;
    setNotice("Preparing original attachments for forwarding…");
    const prepared: ComposeState["attachments"] = [];
    for (const item of row.attachments) {
      try {
        const response = await external(`/messages/${row.uid}/attachments/${item.index}?folder=${encodeURIComponent(folder)}`, { headers: {} });
        if (!response.ok) continue;
        const blob = await response.blob();
        if (blob.size > 10 * 1024 * 1024) continue;
        const content_b64 = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1] || ""); reader.onerror = () => reject(reader.error); reader.readAsDataURL(blob);
        });
        prepared.push({ filename: item.filename, content_type: item.content_type || blob.type || "application/octet-stream", content_b64 });
      } catch { /* Keep forwarding even if one original attachment cannot be retrieved. */ }
    }
    if (prepared.length) setCompose((current) => ({ ...current, attachments: prepared }));
  }

  async function attachFiles(files: FileList | null) {
    if (!files) return;
    const rows: ComposeState["attachments"] = [];
    let total = compose.attachments.reduce((sum, item) => sum + Math.floor(item.content_b64.length * 0.75), 0);
    for (const file of Array.from(files)) {
      if (file.size > 10 * 1024 * 1024) { setError(`${file.name} is larger than 10 MB`); continue; }
      total += file.size;
      if (total > 15 * 1024 * 1024) { setError("Total attachment size cannot exceed 15 MB"); break; }
      const content_b64 = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1] || ""); reader.onerror = () => reject(reader.error); reader.readAsDataURL(file); });
      rows.push({ filename: file.name, content_type: file.type || "application/octet-stream", content_b64 });
    }
    setCompose((current) => ({ ...current, attachments: [...current.attachments, ...rows].slice(0, 20) }));
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setError("");
    try {
      const response = await external("/send", { method: "POST", body: JSON.stringify({
        to: normalizedRecipients(compose.to), cc: normalizedRecipients(compose.cc), bcc: normalizedRecipients(compose.bcc), subject: compose.subject,
        body_text: compose.bodyText, body_html: compose.bodyHtml, attachments: compose.attachments, in_reply_to: compose.in_reply_to, references: compose.references,
      }) });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to send message");
      setCompose(emptyCompose); setComposeOpen(false); await loadFolders(); setNotice("Message sent through your external mail server");
      if (selected && (composeKind === "reply" || composeKind === "reply-all")) setSelected((current) => current ? { ...current, answered: true } : current);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to send message"); }
    finally { setLoading(false); }
  }

  async function saveDraft() {
    setLoading(true); setError("");
    try {
      const response = await external("/drafts", { method: "POST", body: JSON.stringify({ to: normalizedRecipients(compose.to), cc: normalizedRecipients(compose.cc), subject: compose.subject, body_text: compose.bodyText, body_html: compose.bodyHtml }) });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to save draft");
      setCompose(emptyCompose); setComposeOpen(false); await loadFolders(); setNotice("Draft saved on your mail server");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to save draft"); }
    finally { setLoading(false); }
  }

  const searchContacts = useCallback(async (term: string): Promise<Contact[]> => {
    const response = await external(`/contacts?q=${encodeURIComponent(term)}`);
    if (!response.ok) return [];
    const data = await response.json();
    return (data.items || []) as Contact[];
  }, []);

  async function saveAccountSettings() {
    setSavingSettings(true); setError("");
    try {
      const [identityResponse, signatureResponse] = await Promise.all([
        external("/identity", { method: "PUT", body: JSON.stringify({ display_name: displayNameDraft.trim() }) }),
        external("/signature", { method: "PUT", body: JSON.stringify({ html: signatureDraft }) }),
      ]);
      if (!identityResponse.ok || !signatureResponse.ok) throw new Error("Unable to save mailbox settings");
      setSession((current) => current ? { ...current, display_name: displayNameDraft.trim() } : current);
      setSignatureHtml(signatureDraft); setNotice("Account settings saved");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to save mailbox settings"); }
    finally { setSavingSettings(false); }
  }

  if (checking || !preferencesReady) return <MailLoading label="Opening iMail" detail="Checking your secure mailbox session" />;

  if (!session) {
    return (
      <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,.10),transparent_34%),linear-gradient(180deg,#f7faf9,#eef4f1)] px-4 py-6 text-slate-800 sm:px-6">
        <div className="mx-auto max-w-4xl">
          <Link href="/webmail" className="inline-flex items-center gap-2 rounded-full px-3 py-2 text-sm font-bold text-emerald-950 transition hover:bg-white"><ArrowLeft size={17} /> Back to iMail</Link>
          <div className="mt-5 overflow-hidden rounded-[30px] border border-emerald-950/10 bg-white shadow-[0_30px_90px_rgba(20,55,45,.12)]">
            <div className="bg-[linear-gradient(135deg,#e5f3ed,#ffffff_70%)] p-6 sm:p-9">
              <div className="flex items-center gap-4"><div className="grid h-14 w-14 place-items-center rounded-[18px] bg-gradient-to-br from-emerald-950 to-emerald-700 text-amber-300 shadow-lg"><Mail size={27} /></div><div><p className="text-xs font-black uppercase tracking-[.17em] text-amber-700">iMail • External account</p><h1 className="text-2xl font-black tracking-tight text-emerald-950 sm:text-3xl">Bring your business mailbox into Ithute Mail</h1></div></div>
              <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-600">Connect any standards-based IMAP/SMTP mailbox. iMail keeps the experience consistent while your mail remains on the provider you already use.</p>
            </div>
            <form onSubmit={connect} className="space-y-5 p-6 sm:p-9">
              {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div> : null}
              <div className="grid gap-4 sm:grid-cols-2">
                <label><span className="text-xs font-bold text-slate-600">Email address</span><input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@company.co.ls" className="mt-1.5 h-12 w-full rounded-xl border border-slate-200 px-4 text-sm outline-none focus:border-emerald-600 focus:ring-4 focus:ring-emerald-500/10" /></label>
                <label><span className="text-xs font-bold text-slate-600">Display name <span className="font-normal text-slate-400">optional</span></span><input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Your name" className="mt-1.5 h-12 w-full rounded-xl border border-slate-200 px-4 text-sm outline-none focus:border-emerald-600 focus:ring-4 focus:ring-emerald-500/10" /></label>
              </div>
              <label className="block"><span className="text-xs font-bold text-slate-600">Mailbox password</span><div className="relative mt-1.5"><input type={showPassword ? "text" : "password"} required value={password} onChange={(event) => setPassword(event.target.value)} className="h-12 w-full rounded-xl border border-slate-200 px-4 pr-12 text-sm outline-none focus:border-emerald-600 focus:ring-4 focus:ring-emerald-500/10" /><button type="button" onClick={() => setShowPassword((value) => !value)} className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-2 text-slate-500 hover:bg-slate-100">{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></div></label>
              <div className="flex flex-wrap gap-2"><button type="button" onClick={useDomainDefaults} className="rounded-xl border border-emerald-900/15 bg-emerald-50 px-4 py-2.5 text-xs font-bold text-emerald-800 hover:bg-emerald-100">Use standard domain defaults</button><button type="button" onClick={() => setAdvanced((value) => !value)} className="inline-flex items-center gap-1 rounded-xl px-4 py-2.5 text-xs font-bold text-slate-600 hover:bg-slate-50">{advanced ? "Hide" : "Show"} server settings <ChevronDown size={15} className={advanced ? "rotate-180" : ""} /></button></div>
              {advanced ? <div className="grid gap-5 rounded-2xl border border-slate-200 bg-slate-50 p-4 sm:grid-cols-2">
                <div className="space-y-3"><p className="text-xs font-black uppercase tracking-[.12em] text-slate-500">Incoming IMAP</p><input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Username (usually full email)" className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm" /><input value={imapHost} onChange={(event) => setImapHost(event.target.value)} placeholder="mail.example.com" className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm" /><div className="grid grid-cols-[100px_1fr] gap-2"><input inputMode="numeric" value={imapPort} onChange={(event) => setImapPort(event.target.value)} className="h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm" /><select value={imapSecurity} onChange={(event) => setImapSecurity(event.target.value)} className="h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm"><option value="ssl">SSL/TLS</option><option value="starttls">STARTTLS</option></select></div></div>
                <div className="space-y-3"><p className="text-xs font-black uppercase tracking-[.12em] text-slate-500">Outgoing SMTP</p><div className="h-11 rounded-xl border border-dashed border-slate-200 bg-white px-3 text-xs leading-[42px] text-slate-500">Uses the same username and password</div><input value={smtpHost} onChange={(event) => setSmtpHost(event.target.value)} placeholder="mail.example.com" className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm" /><div className="grid grid-cols-[100px_1fr] gap-2"><input inputMode="numeric" value={smtpPort} onChange={(event) => setSmtpPort(event.target.value)} className="h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm" /><select value={smtpSecurity} onChange={(event) => setSmtpSecurity(event.target.value)} className="h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm"><option value="ssl">SSL/TLS</option><option value="starttls">STARTTLS</option></select></div></div>
              </div> : null}
              <div className="flex items-start gap-2 rounded-xl bg-emerald-50 px-4 py-3 text-xs leading-5 text-emerald-950"><ShieldCheck size={17} className="mt-0.5 shrink-0" /> Credentials stay in the encrypted server-side session. iMail requires public mail-server addresses and verified TLS connections.</div>
              <button disabled={loading} className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-emerald-800 px-4 text-sm font-black text-white transition hover:bg-emerald-900 disabled:opacity-60">{loading ? <Loader2 size={18} className="animate-spin" /> : <Server size={18} />} Test and connect mailbox</button>
            </form>
          </div>
        </div>
      </main>
    );
  }

  const densityClass = preferences.density === "compact" ? "py-2" : "py-3.5";
  const paneRight = preferences.readingPane === "right";
  const paneBottom = preferences.readingPane === "bottom";
  const noPane = preferences.readingPane === "none";
  const composeTitle = composeKind === "reply" ? "Reply" : composeKind === "reply-all" ? "Reply all" : composeKind === "forward" ? "Forward message" : "New message";

  const reader = selected ? (
    <section className="flex min-h-0 flex-1 flex-col bg-white dark:bg-slate-900">
      <div className="flex h-13 shrink-0 items-center gap-1 border-b border-slate-200 px-3 dark:border-white/10 sm:px-4">
        <button type="button" onClick={() => setSelected(null)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Back to inbox"><ArrowLeft size={18} /></button>
        <button type="button" onClick={() => void toggleStar(selected)} className={`grid h-9 w-9 place-items-center rounded-full hover:bg-slate-100 dark:hover:bg-white/10 ${selected.flagged ? "text-amber-500" : "text-slate-500"}`} title="Star"><Star size={18} fill={selected.flagged ? "currentColor" : "none"} /></button>
        <button type="button" onClick={() => void toggleSeen(selected)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title={selected.seen ? "Mark unread" : "Mark read"}><Mail size={18} /></button>
        <button type="button" onClick={() => void remove(selected)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10" title="Delete"><Trash2 size={18} /></button>
        <span className="mx-1 h-5 w-px bg-slate-200 dark:bg-white/10" />
        <button type="button" onClick={() => startReply(selected)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Reply"><Reply size={18} /></button>
        <button type="button" onClick={() => startReplyAll(selected)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Reply all"><ReplyAll size={18} /></button>
        <button type="button" onClick={() => void startForward(selected)} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Forward"><Forward size={18} /></button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-7 sm:py-7 lg:px-9">
        {messageLoading ? <div className="py-12"><MailLoading compact label="Opening message" detail="Loading the full message securely" /></div> : <div className="mx-auto max-w-4xl">
          <h1 className="pr-4 text-[22px] font-black leading-tight tracking-tight text-slate-900 dark:text-white sm:text-[26px]">{selected.subject || "(no subject)"}</h1>
          <div className="mt-6 flex items-start gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-gradient-to-br from-emerald-100 to-emerald-200 text-sm font-black text-emerald-900 dark:from-emerald-400/15 dark:to-emerald-500/10 dark:text-emerald-200">{initials(selected.from)}</span>
            <div className="min-w-0 flex-1"><div className="flex flex-wrap items-baseline gap-x-2"><span className="font-black text-slate-900 dark:text-white">{senderName(selected.from)}</span><span className="truncate text-xs text-slate-500">&lt;{addressOnly(selected.from)}&gt;</span></div><p className="mt-1 text-xs text-slate-500">to {selected.to || session.address}{selected.cc ? ` • cc ${selected.cc}` : ""}</p></div>
            <time className="shrink-0 text-xs font-medium text-slate-500">{selected.date ? shortDate(selected.date) : ""}</time>
          </div>

          <div className="mt-5"><MailPrivacyNote /></div>
          <div className="mt-6 min-h-[220px]"><MailContent text={selected.body_text || selected.snippet || ""} openLinksNewTab={preferences.openLinksNewTab} fontScale={preferences.fontScale} /></div>

          {selected.attachments?.length ? <div className="mt-8 border-t border-slate-200 pt-5 dark:border-white/10"><p className="mb-3 flex items-center gap-2 text-xs font-black uppercase tracking-[.12em] text-slate-500"><Paperclip size={14} /> {selected.attachments.length} attachment{selected.attachments.length === 1 ? "" : "s"}</p><div className="flex flex-wrap gap-2">{selected.attachments.map((item) => <a key={`${selected.uid}-${item.index}`} href={`${API}/webmail/external/messages/${selected.uid}/attachments/${item.index}?folder=${encodeURIComponent(folder)}`} className="group flex max-w-[300px] items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 transition hover:border-emerald-300 hover:bg-emerald-50 dark:border-white/10 dark:bg-white/[.035] dark:hover:bg-emerald-400/10"><span className="grid h-9 w-9 place-items-center rounded-lg bg-white text-slate-500 shadow-sm dark:bg-white/10"><FileText size={17} /></span><span className="min-w-0 flex-1"><span className="block truncate text-xs font-bold text-slate-800 dark:text-slate-100">{item.filename}</span><span className="block text-[10px] text-slate-500">{humanBytes(item.size || 0)}</span></span><Download size={15} className="text-slate-400 group-hover:text-emerald-700" /></a>)}</div></div> : null}

          <div className="mt-9 flex flex-wrap gap-2 border-t border-slate-200 pt-5 dark:border-white/10"><button type="button" onClick={() => startReply(selected)} className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-4 text-sm font-bold text-slate-700 transition hover:border-emerald-300 hover:bg-emerald-50 dark:border-white/10 dark:text-slate-200 dark:hover:bg-emerald-400/10"><Reply size={16} /> Reply</button><button type="button" onClick={() => startReplyAll(selected)} className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-4 text-sm font-bold text-slate-700 transition hover:border-emerald-300 hover:bg-emerald-50 dark:border-white/10 dark:text-slate-200 dark:hover:bg-emerald-400/10"><ReplyAll size={16} /> Reply all</button><button type="button" onClick={() => void startForward(selected)} className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-4 text-sm font-bold text-slate-700 transition hover:border-emerald-300 hover:bg-emerald-50 dark:border-white/10 dark:text-slate-200 dark:hover:bg-emerald-400/10"><Forward size={16} /> Forward</button></div>
        </div>}
      </div>
    </section>
  ) : (
    <section className="hidden min-h-0 flex-1 place-items-center bg-white dark:bg-slate-900 lg:grid"><div className="max-w-sm text-center"><span className="mx-auto grid h-16 w-16 place-items-center rounded-[22px] bg-emerald-50 text-emerald-800 dark:bg-emerald-400/10 dark:text-emerald-300"><Mail size={28} /></span><h2 className="mt-4 text-lg font-black text-slate-800 dark:text-white">Your message opens here</h2><p className="mt-1 text-sm leading-6 text-slate-500">Choose a message from the inbox, or change the reading pane in Settings.</p></div></section>
  );

  const messageList = (
    <section className="flex min-h-0 flex-1 flex-col bg-[#f6f8f7] dark:bg-[#0e1514]">
      <div className="shrink-0 px-3 pb-2 pt-3 sm:px-4">
        <form onSubmit={(event) => { event.preventDefault(); void loadMessages(folder, query); }} className="mx-auto flex h-12 max-w-4xl items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 shadow-sm transition focus-within:border-emerald-400 focus-within:ring-4 focus-within:ring-emerald-500/10 dark:border-white/10 dark:bg-white/[.05]"><Search size={18} className="shrink-0 text-slate-400" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search mail" className="min-w-0 flex-1 bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400 dark:text-white" />{query ? <button type="button" onClick={() => { setQuery(""); void loadMessages(folder, ""); }} className="grid h-8 w-8 place-items-center rounded-full text-slate-400 hover:bg-slate-100 dark:hover:bg-white/10"><X size={16} /></button> : null}</form>
      </div>
      <div className="flex h-11 shrink-0 items-center gap-2 border-y border-slate-200 bg-white px-3 dark:border-white/10 dark:bg-slate-900 sm:px-4"><div className="min-w-0 flex-1"><p className="truncate text-xs font-black uppercase tracking-[.12em] text-slate-600 dark:text-slate-300">{folder}</p><p className="text-[10px] font-medium text-slate-400">{messages.length} loaded message{messages.length === 1 ? "" : "s"}</p></div><button type="button" onClick={() => void refresh()} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Refresh"><RefreshCw size={16} className={loading ? "animate-spin" : ""} /></button><button type="button" className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="More"><MoreVertical size={16} /></button></div>
      {loading && !messages.length ? <div className="grid flex-1 place-items-center p-6"><MailLoading compact label="Loading mail" detail={`Reading ${folder}`} /></div> : <div className="min-h-0 flex-1 overflow-y-auto">
        {!messages.length ? <div className="grid min-h-[360px] place-items-center p-8 text-center"><div><span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-white text-slate-400 shadow-sm dark:bg-white/5"><Inbox size={24} /></span><p className="mt-4 text-sm font-black text-slate-700 dark:text-slate-200">No messages here</p><p className="mt-1 text-xs text-slate-500">{query ? "Try a different search." : "This folder is currently empty."}</p></div></div> : messages.map((row) => <article key={`${folder}-${row.uid}`} className={`group flex cursor-pointer items-center gap-2 border-b border-slate-200/80 px-2 transition hover:z-[1] hover:bg-white hover:shadow-sm dark:border-white/[.07] dark:hover:bg-white/[.045] ${row.seen ? "bg-[#f7f9f8] dark:bg-[#0e1514]" : "bg-white dark:bg-slate-900"} ${densityClass} ${selected?.uid === row.uid ? "border-l-[3px] border-l-emerald-700 bg-emerald-50/70 dark:bg-emerald-400/[.06]" : "border-l-[3px] border-l-transparent"}`} onClick={() => void openMessage(row)}>
          <button type="button" onClick={(event) => { event.stopPropagation(); void toggleStar(row); }} className={`grid h-8 w-8 shrink-0 place-items-center rounded-full transition hover:bg-slate-100 dark:hover:bg-white/10 ${row.flagged ? "text-amber-500" : "text-slate-300 group-hover:text-slate-500"}`}><Star size={16} fill={row.flagged ? "currentColor" : "none"} /></button>
          <span className="hidden h-8 w-8 shrink-0 place-items-center rounded-full bg-emerald-100 text-[10px] font-black text-emerald-900 sm:grid dark:bg-emerald-400/10 dark:text-emerald-200">{initials(row.from)}</span>
          <div className="min-w-0 flex-1 sm:grid sm:grid-cols-[minmax(120px,170px)_1fr_auto] sm:items-center sm:gap-3"><div className={`truncate text-sm ${row.seen ? "font-medium text-slate-700 dark:text-slate-300" : "font-black text-slate-950 dark:text-white"}`}>{senderName(row.from)}</div><div className="min-w-0"><div className={`truncate text-sm ${row.seen ? "font-medium text-slate-700 dark:text-slate-300" : "font-bold text-slate-950 dark:text-white"}`}>{row.subject || "(no subject)"}</div>{preferences.showPreview ? <p className="mt-0.5 truncate text-[11px] text-slate-500">{row.snippet}</p> : null}</div><div className="mt-1 flex items-center gap-2 sm:mt-0 sm:justify-end">{row.attachments?.length ? <Paperclip size={13} className="text-slate-400" /> : null}<time className={`text-[10px] ${row.seen ? "font-medium text-slate-400" : "font-black text-emerald-800 dark:text-emerald-300"}`}>{shortDate(row.date)}</time></div></div>
          <div className="hidden shrink-0 items-center gap-0.5 opacity-0 transition group-hover:opacity-100 xl:flex"><button type="button" onClick={(event) => { event.stopPropagation(); void toggleSeen(row); }} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title={row.seen ? "Mark unread" : "Mark read"}><Mail size={15} /></button><button type="button" onClick={(event) => { event.stopPropagation(); void remove(row); }} className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10" title="Delete"><Trash2 size={15} /></button></div>
        </article>)}
      </div>}
    </section>
  );

  return (
    <main className={`min-h-screen ${theme === "dark" ? "bg-[#0b1110] text-slate-100" : theme === "ithute" ? "bg-[#eef4f1] text-slate-900" : "bg-[#f4f6f8] text-slate-900"}`}>
      <header className="sticky top-0 z-40 flex h-16 items-center gap-2 border-b border-slate-200 bg-white/95 px-2 backdrop-blur dark:border-white/10 dark:bg-slate-950/95 sm:px-4">
        <button className="grid h-10 w-10 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10 lg:hidden" onClick={() => setMobileFolders(true)} aria-label="Open folders"><Menu size={20} /></button>
        <Link href="/webmail" className="grid h-10 w-10 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" aria-label="Back to Ithute Mail"><ArrowLeft size={20} /></Link>
        <div className="grid h-10 w-10 place-items-center rounded-[14px] bg-gradient-to-br from-emerald-950 to-emerald-700 text-xs font-black text-amber-300 shadow-sm">iM</div>
        <div className="min-w-0"><p className="truncate text-sm font-black text-emerald-950 dark:text-white">{session.display_name || session.address}</p><p className="truncate text-[10px] font-semibold text-slate-500">External • {session.imap_host}</p></div>
        <span className="ml-2 hidden rounded-full border border-emerald-900/10 bg-emerald-50 px-2.5 py-1 text-[10px] font-black uppercase tracking-[.1em] text-emerald-800 md:inline">iMail</span>
        <div className="ml-auto flex items-center gap-0.5"><button onClick={() => void refresh()} className="grid h-10 w-10 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Refresh"><RefreshCw size={18} /></button><button onClick={() => setSettingsOpen(true)} className="grid h-10 w-10 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Settings"><Settings2 size={18} /></button><button onClick={() => void logout()} className="grid h-10 w-10 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10" title="Disconnect external mailbox"><LogOut size={18} /></button></div>
      </header>

      {notice ? <div className="fixed right-4 top-20 z-[120] rounded-xl bg-emerald-950 px-4 py-3 text-xs font-bold text-white shadow-2xl">{notice}</div> : null}
      {error ? <div className="fixed left-1/2 top-20 z-[120] w-[min(92vw,620px)] -translate-x-1/2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700 shadow-xl"><div className="flex items-start gap-3"><span className="min-w-0 flex-1">{error}</span><button onClick={() => setError("")} className="grid h-6 w-6 place-items-center rounded-full hover:bg-red-100"><X size={14} /></button></div></div> : null}

      <div className="flex h-[calc(100vh-64px)] min-h-0">
        <aside className={`${mobileFolders ? "fixed inset-y-16 left-0 z-50 flex w-[280px] shadow-2xl" : "hidden"} shrink-0 flex-col border-r border-slate-200 bg-[#fbfcfc] p-3 dark:border-white/10 dark:bg-[#101817] lg:flex lg:w-[244px] lg:shadow-none`}>
          {mobileFolders ? <button type="button" onClick={() => setMobileFolders(false)} className="absolute right-2 top-2 grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10"><X size={16} /></button> : null}
          <button onClick={startNew} className="flex h-13 items-center gap-3 rounded-2xl bg-emerald-100 px-4 text-sm font-black text-emerald-950 shadow-sm transition hover:bg-emerald-200 dark:bg-emerald-400/15 dark:text-emerald-100 dark:hover:bg-emerald-400/20"><PenLine size={18} /> Compose</button>
          <nav className="mt-4 min-h-0 flex-1 overflow-y-auto pr-1">{folders.map((item) => {
            const active = item.name.toLowerCase() === folder.toLowerCase(); const count = countFor(item.name);
            return <button key={item.name} onClick={() => { setFolder(item.name); setMobileFolders(false); void loadMessages(item.name, ""); }} className={`mb-1 flex h-10 w-full items-center gap-3 rounded-xl px-3 text-left text-sm transition ${active ? "bg-emerald-100 font-black text-emerald-950 dark:bg-emerald-400/15 dark:text-emerald-100" : "font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5"}`}><span className="shrink-0">{folderIcon(item.name)}</span><span className="min-w-0 flex-1 truncate">{item.name}</span>{count ? <span className="text-[10px] font-black">{count}</span> : null}</button>;
          })}</nav>
          <div className="mt-3 rounded-2xl border border-slate-200 bg-white p-3 text-[10px] leading-5 text-slate-500 dark:border-white/10 dark:bg-white/[.035]"><div className="flex items-center gap-2 font-black text-slate-700 dark:text-slate-200"><Server size={14} /> Connected securely</div><p className="mt-1 truncate">IMAP {session.imap_host}:{session.imap_port}</p><p className="truncate">SMTP {session.smtp_host}:{session.smtp_port}</p></div>
        </aside>

        <div className="min-w-0 flex flex-1 flex-col">
          {noPane && selected ? reader : paneRight ? <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(390px,46%)_1fr]"><div className="min-h-0 border-r border-slate-200 dark:border-white/10">{messageList}</div>{reader}</div> : paneBottom ? <div className="grid min-h-0 flex-1 grid-rows-[minmax(300px,48%)_1fr]"><div className="min-h-0 border-b border-slate-200 dark:border-white/10">{messageList}</div>{reader}</div> : messageList}
        </div>
      </div>

      <MailSettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} preferences={preferences} setPreferences={setPreferences} onReset={resetPreferences} displayName={displayNameDraft} signatureHtml={signatureDraft} onDisplayNameChange={setDisplayNameDraft} onSignatureChange={setSignatureDraft} onSaveAccount={saveAccountSettings} savingAccount={savingSettings} />

      {composeOpen ? <ExternalMailCompose address={session.address} compose={compose} setCompose={setCompose} loading={loading} minimized={composeMinimized} expanded={composeExpanded} showCcBcc={showCcBcc} title={composeTitle} signatureHtml={composeKind === "new" ? signatureHtml : ""} onMinimized={setComposeMinimized} onExpanded={setComposeExpanded} onShowCcBcc={setShowCcBcc} onClose={() => { void saveDraft(); }} onDiscard={() => { setCompose(emptyCompose); setComposeOpen(false); }} onSaveDraft={() => void saveDraft()} onSend={sendMessage} onAttach={attachFiles} searchContacts={searchContacts} /> : null}
    </main>
  );
}
