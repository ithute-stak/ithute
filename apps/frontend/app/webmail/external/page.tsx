"use client";

import Link from "next/link";
import {
  ArrowLeft,
  ChevronDown,
  Download,
  Eye,
  EyeOff,
  Inbox,
  Loader2,
  LogOut,
  Mail,
  Menu,
  Paperclip,
  PenLine,
  RefreshCw,
  Reply,
  Search,
  Send,
  Server,
  ShieldCheck,
  Star,
  Trash2,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";
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
type ComposeState = {
  to: string;
  cc: string;
  bcc: string;
  subject: string;
  body_text: string;
  in_reply_to: string;
  references: string;
  attachments: { filename: string; content_type: string; content_b64: string }[];
};

const emptyCompose: ComposeState = {
  to: "",
  cc: "",
  bcc: "",
  subject: "",
  body_text: "",
  in_reply_to: "",
  references: "",
  attachments: [],
};

async function external(path: string, init?: RequestInit) {
  return fetch(`${API}/webmail/external${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
}

function splitAddresses(value: string) {
  return value.split(/[;,]/).map((item) => item.trim()).filter(Boolean);
}

function addressOnly(value: string) {
  const match = value.match(/<([^>]+)>/);
  return (match?.[1] || value).trim();
}

function senderName(value: string) {
  const text = value.replace(/<.*?>/g, "").replace(/^"|"$/g, "").trim();
  return text || addressOnly(value) || "Unknown sender";
}

function initials(value: string) {
  return senderName(value)
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((item) => item[0]?.toUpperCase())
    .join("") || "M";
}

function shortDate(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const now = new Date();
  if (parsed.toDateString() === now.toDateString()) {
    return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  if (parsed.getFullYear() === now.getFullYear()) {
    return parsed.toLocaleDateString([], { day: "2-digit", month: "short" });
  }
  return parsed.toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" });
}

function folderIcon(name: string) {
  const lower = name.toLowerCase();
  if (lower === "inbox") return <Inbox size={17} />;
  if (lower.includes("sent")) return <Send size={17} />;
  if (lower.includes("trash") || lower.includes("deleted") || lower === "bin") return <Trash2 size={17} />;
  return <Mail size={17} />;
}

export default function ExternalWebmailPage() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [checking, setChecking] = useState(true);
  const [loading, setLoading] = useState(false);
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

  const countFor = useCallback((name: string) => {
    const row = counts.find((item) => item.name.toLowerCase() === name.toLowerCase());
    if (!row) return 0;
    return name.toLowerCase() === "inbox" ? row.unseen : row.messages;
  }, [counts]);

  const loadFolders = useCallback(async () => {
    const [foldersResponse, countsResponse] = await Promise.all([
      external("/folders"),
      external("/folder-counts"),
    ]);
    if (foldersResponse.status === 401 || countsResponse.status === 401) {
      setSession(null);
      return;
    }
    if (foldersResponse.ok) setFolders((await foldersResponse.json()).items || []);
    if (countsResponse.ok) setCounts((await countsResponse.json()).items || []);
  }, []);

  const loadMessages = useCallback(async (target: string, search = "") => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ folder: target, limit: String(PAGE_SIZE), offset: "0" });
      if (search.trim()) params.set("q", search.trim());
      const response = await external(`/messages?${params}`);
      if (response.status === 401) {
        setSession(null);
        return;
      }
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to load messages");
      const data = await response.json();
      setMessages(data.items || []);
      setSelected(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load messages");
    } finally {
      setLoading(false);
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
        if (!response.ok) {
          setSession(null);
          return;
        }
        const data = await response.json();
        setSession(data);
        await Promise.all([loadFolders(), loadMessages("INBOX")]);
      } catch {
        if (active) setSession(null);
      } finally {
        if (active) setChecking(false);
      }
    })();
    return () => { active = false; };
  }, [loadFolders, loadMessages]);

  useEffect(() => {
    if (!session) return;
    const timer = window.setInterval(() => {
      void loadFolders();
    }, 20000);
    return () => window.clearInterval(timer);
  }, [loadFolders, session]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const inferredDomain = useMemo(() => email.trim().toLowerCase().split("@")[1] || "", [email]);

  function useDomainDefaults() {
    if (!inferredDomain) {
      setError("Enter the email address first so iMail can determine the domain.");
      return;
    }
    const host = `mail.${inferredDomain}`;
    setUsername(email.trim().toLowerCase());
    setImapHost(host);
    setImapPort("993");
    setImapSecurity("ssl");
    setSmtpHost(host);
    setSmtpPort("465");
    setSmtpSecurity("ssl");
    setAdvanced(true);
    setError("");
  }

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const address = email.trim().toLowerCase();
      const domain = address.split("@")[1] || "";
      const defaultHost = domain ? `mail.${domain}` : "";
      const response = await external("/session", {
        method: "POST",
        body: JSON.stringify({
          address,
          password,
          display_name: displayName.trim(),
          username: username.trim() || address,
          imap_host: imapHost.trim() || defaultHost,
          imap_port: Number(imapPort || 993),
          imap_security: imapSecurity,
          smtp_host: smtpHost.trim() || defaultHost,
          smtp_port: Number(smtpPort || 465),
          smtp_security: smtpSecurity,
        }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Could not connect to this external mailbox.");
      }
      const data = await response.json();
      setSession(data);
      setFolder("INBOX");
      setPassword("");
      await Promise.all([loadFolders(), loadMessages("INBOX")]);
      setNotice("External mailbox connected securely");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to connect external mailbox");
    } finally {
      setLoading(false);
    }
  }

  async function logout() {
    await external("/session", { method: "DELETE" });
    setSession(null);
    setMessages([]);
    setFolders([]);
    setCounts([]);
    setSelected(null);
    setNotice("External mailbox disconnected");
  }

  async function openMessage(row: MessageRow) {
    setSelected(row);
    const response = await external(`/messages/${row.uid}?folder=${encodeURIComponent(folder)}`);
    if (response.ok) {
      const full = await response.json();
      setSelected(full);
      setMessages((current) => current.map((item) => item.uid === row.uid ? { ...item, seen: true } : item));
      void loadFolders();
    }
  }

  async function toggleStar(row: MessageRow) {
    const response = await external(`/messages/${row.uid}/flags?folder=${encodeURIComponent(folder)}`, {
      method: "PATCH",
      body: JSON.stringify({ flagged: !row.flagged }),
    });
    if (response.ok) {
      const updated = await response.json();
      setMessages((current) => current.map((item) => item.uid === row.uid ? updated : item));
      if (selected?.uid === row.uid) setSelected(updated);
    }
  }

  async function remove(row: MessageRow) {
    const response = await external(`/messages/${row.uid}?folder=${encodeURIComponent(folder)}`, { method: "DELETE" });
    if (!response.ok) {
      setError((await response.json().catch(() => ({}))).detail || "Unable to delete message");
      return;
    }
    setSelected(null);
    await refresh();
    setNotice("Message moved to Trash");
  }

  function startReply(row: MessageRow) {
    const target = addressOnly(row.reply_to || row.from);
    const subject = /^re:/i.test(row.subject) ? row.subject : `Re: ${row.subject}`;
    const refs = [row.references, row.message_id].filter(Boolean).join(" ");
    setCompose({
      ...emptyCompose,
      to: target,
      subject,
      in_reply_to: row.message_id,
      references: refs,
      body_text: `\n\nOn ${row.date}, ${row.from} wrote:\n${(row.body_text || row.snippet || "").split("\n").map((line) => `> ${line}`).join("\n")}`,
    });
    setComposeOpen(true);
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

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await external("/send", {
        method: "POST",
        body: JSON.stringify({
          to: splitAddresses(compose.to),
          cc: splitAddresses(compose.cc),
          bcc: splitAddresses(compose.bcc),
          subject: compose.subject,
          body_text: compose.body_text,
          attachments: compose.attachments,
          in_reply_to: compose.in_reply_to,
          references: compose.references,
        }),
      });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to send message");
      setCompose(emptyCompose);
      setComposeOpen(false);
      await loadFolders();
      setNotice("Message sent through external SMTP server");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to send message");
    } finally {
      setLoading(false);
    }
  }

  async function saveDraft() {
    setLoading(true);
    try {
      const response = await external("/drafts", {
        method: "POST",
        body: JSON.stringify({
          to: splitAddresses(compose.to),
          cc: splitAddresses(compose.cc),
          subject: compose.subject,
          body_text: compose.body_text,
        }),
      });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to save draft");
      setCompose(emptyCompose);
      setComposeOpen(false);
      await loadFolders();
      setNotice("Draft saved on the external mail server");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save draft");
    } finally {
      setLoading(false);
    }
  }

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center bg-[#f3f7f5] text-[#315b50]">
        <div className="flex items-center gap-3 rounded-2xl border border-[#dce7e2] bg-white px-5 py-4 text-sm font-semibold shadow-sm">
          <Loader2 size={18} className="animate-spin" /> Checking external mailbox session
        </div>
      </div>
    );
  }

  if (!session) {
    return (
      <main className="min-h-screen bg-[#f2f7f5] px-4 py-6 text-[#1d302a] sm:px-6">
        <div className="mx-auto max-w-3xl">
          <Link href="/webmail" className="inline-flex items-center gap-2 rounded-full px-3 py-2 text-sm font-semibold text-[#426158] hover:bg-white"><ArrowLeft size={17} /> Back to !THUTE Mail</Link>
          <div className="mt-5 overflow-hidden rounded-[28px] border border-[#dae6e0] bg-white shadow-[0_26px_70px_rgba(24,72,59,.11)]">
            <div className="bg-[linear-gradient(135deg,#e8f3ee,#ffffff_72%)] p-6 sm:p-8">
              <div className="flex items-center gap-3">
                <div className="grid h-12 w-12 place-items-center rounded-2xl bg-[#123a38] text-[#f0d96f]"><Server size={23} /></div>
                <div><p className="text-xs font-black uppercase tracking-[.14em] text-[#8c7930]">External mail account</p><h1 className="text-2xl font-black tracking-tight text-[#193d35]">Connect another mail server</h1></div>
              </div>
              <p className="mt-4 max-w-2xl text-sm leading-6 text-[#64766f]">Use !THUTE Webmail with any standard IMAP/SMTP mail server. The connection is secured for incoming and outgoing mail without promoting or depending on a third-party brand.</p>
            </div>

            <form onSubmit={connect} className="space-y-5 p-6 sm:p-8">
              {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div> : null}
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block"><span className="text-xs font-bold text-[#465b54]">Email address</span><input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@company.co.ls" className="mt-1.5 min-h-12 w-full rounded-xl border border-[#d7e2dd] px-4 text-sm outline-none focus:border-[#276c58] focus:ring-4 focus:ring-[#276c58]/10" /></label>
                <label className="block"><span className="text-xs font-bold text-[#465b54]">Display name <span className="font-normal text-[#83908b]">optional</span></span><input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Your name" className="mt-1.5 min-h-12 w-full rounded-xl border border-[#d7e2dd] px-4 text-sm outline-none focus:border-[#276c58] focus:ring-4 focus:ring-[#276c58]/10" /></label>
              </div>
              <label className="block"><span className="text-xs font-bold text-[#465b54]">Mailbox password</span><div className="relative mt-1.5"><input type={showPassword ? "text" : "password"} required value={password} onChange={(event) => setPassword(event.target.value)} className="min-h-12 w-full rounded-xl border border-[#d7e2dd] px-4 pr-12 text-sm outline-none focus:border-[#276c58] focus:ring-4 focus:ring-[#276c58]/10" /><button type="button" onClick={() => setShowPassword((value) => !value)} className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-2 text-[#71817a] hover:bg-[#edf4f1]">{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></div></label>

              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={useDomainDefaults} className="rounded-xl border border-[#cadbd3] bg-[#f5faf8] px-4 py-2.5 text-xs font-bold text-[#275f50] hover:bg-[#eaf4ef]">Use standard domain defaults</button>
                <button type="button" onClick={() => setAdvanced((value) => !value)} className="inline-flex items-center gap-1 rounded-xl px-4 py-2.5 text-xs font-bold text-[#5e7169] hover:bg-[#f3f6f5]">{advanced ? "Hide" : "Show"} server settings <ChevronDown size={15} className={advanced ? "rotate-180" : ""} /></button>
              </div>

              {advanced ? (
                <div className="grid gap-5 rounded-2xl border border-[#e1e8e5] bg-[#f9fbfa] p-4 sm:grid-cols-2">
                  <div className="space-y-3"><p className="text-xs font-black uppercase tracking-[.11em] text-[#5f756d]">Incoming IMAP</p><input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Username (usually full email)" className="min-h-11 w-full rounded-xl border border-[#d7e2dd] bg-white px-3 text-sm" /><input value={imapHost} onChange={(event) => setImapHost(event.target.value)} placeholder="mail.example.com" className="min-h-11 w-full rounded-xl border border-[#d7e2dd] bg-white px-3 text-sm" /><div className="grid grid-cols-[100px_1fr] gap-2"><input inputMode="numeric" value={imapPort} onChange={(event) => setImapPort(event.target.value)} className="min-h-11 rounded-xl border border-[#d7e2dd] bg-white px-3 text-sm" /><select value={imapSecurity} onChange={(event) => setImapSecurity(event.target.value)} className="min-h-11 rounded-xl border border-[#d7e2dd] bg-white px-3 text-sm"><option value="ssl">SSL/TLS</option><option value="starttls">STARTTLS</option></select></div></div>
                  <div className="space-y-3"><p className="text-xs font-black uppercase tracking-[.11em] text-[#5f756d]">Outgoing SMTP</p><div className="h-11 rounded-xl border border-dashed border-[#d7e2dd] bg-white px-3 text-xs leading-[42px] text-[#7a8883]">Uses the same username and password</div><input value={smtpHost} onChange={(event) => setSmtpHost(event.target.value)} placeholder="mail.example.com" className="min-h-11 w-full rounded-xl border border-[#d7e2dd] bg-white px-3 text-sm" /><div className="grid grid-cols-[100px_1fr] gap-2"><input inputMode="numeric" value={smtpPort} onChange={(event) => setSmtpPort(event.target.value)} className="min-h-11 rounded-xl border border-[#d7e2dd] bg-white px-3 text-sm" /><select value={smtpSecurity} onChange={(event) => setSmtpSecurity(event.target.value)} className="min-h-11 rounded-xl border border-[#d7e2dd] bg-white px-3 text-sm"><option value="ssl">SSL/TLS</option><option value="starttls">STARTTLS</option></select></div></div>
                </div>
              ) : null}

              <div className="flex items-start gap-2 rounded-xl bg-[#f4f8f6] px-4 py-3 text-xs leading-5 text-[#63736d]"><ShieldCheck size={17} className="mt-0.5 shrink-0 text-[#2d715d]" /> Credentials are encrypted in the server-side session. !THUTE Mail only allows public mail-server addresses and verified TLS connections.</div>
              <button disabled={loading} className="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-[#14543f] px-4 text-sm font-black text-white transition hover:bg-[#0f4635] disabled:opacity-60">{loading ? <Loader2 size={18} className="animate-spin" /> : <Server size={18} />} Test and connect mailbox</button>
            </form>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#f3f6f5] text-[#1f2d29]">
      <header className="sticky top-0 z-40 flex h-16 items-center gap-3 border-b border-[#dde5e1] bg-white/95 px-3 backdrop-blur sm:px-5">
        <button className="grid h-10 w-10 place-items-center rounded-full text-[#50625b] hover:bg-[#eef3f1] lg:hidden" onClick={() => setMobileFolders(true)}><Menu size={20} /></button>
        <Link href="/webmail" className="grid h-10 w-10 place-items-center rounded-full text-[#50625b] hover:bg-[#eef3f1]" aria-label="Back to Ithute Mail"><ArrowLeft size={20} /></Link>
        <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#123a38] text-xs font-black text-[#f0d96f]">!T</div>
        <div className="min-w-0"><p className="truncate text-sm font-black text-[#183c34]">{session.display_name || session.address}</p><p className="truncate text-[10px] font-semibold text-[#71817a]">External • {session.imap_host}</p></div>
        <div className="ml-auto flex items-center gap-1"><button onClick={() => void refresh()} className="grid h-10 w-10 place-items-center rounded-full text-[#50625b] hover:bg-[#eef3f1]" title="Refresh"><RefreshCw size={18} /></button><button onClick={() => void logout()} className="grid h-10 w-10 place-items-center rounded-full text-[#50625b] hover:bg-[#eef3f1]" title="Disconnect external mailbox"><LogOut size={18} /></button></div>
      </header>

      {notice ? <div className="fixed right-4 top-20 z-[90] rounded-xl bg-[#183f35] px-4 py-3 text-xs font-bold text-white shadow-xl">{notice}</div> : null}
      {error ? <div className="mx-auto mt-3 max-w-5xl rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div> : null}

      <div className="mx-auto grid max-w-[1450px] lg:grid-cols-[250px_1fr]">
        <aside className="hidden min-h-[calc(100vh-4rem)] border-r border-[#e0e7e4] bg-white p-3 lg:block">
          <button onClick={() => { setCompose(emptyCompose); setComposeOpen(true); }} className="mb-4 flex min-h-12 w-full items-center justify-center gap-2 rounded-2xl bg-[#dcefe6] text-sm font-black text-[#164d3d] hover:bg-[#cee7dc]"><PenLine size={18} /> Compose</button>
          <div className="space-y-1">{folders.map((item) => <button key={item.name} onClick={() => { setFolder(item.name); setQuery(""); void loadMessages(item.name); }} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm ${folder === item.name ? "bg-[#e7f0ec] font-black text-[#174f40]" : "font-semibold text-[#52635d] hover:bg-[#f3f6f5]"}`}>{folderIcon(item.name)}<span className="min-w-0 flex-1 truncate">{item.name}</span><span className="text-xs">{countFor(item.name) || ""}</span></button>)}</div>
          <div className="mt-5 rounded-xl border border-[#e1e8e5] bg-[#fafcfb] p-3 text-[10px] leading-5 text-[#718079]"><Server size={15} className="mb-2 text-[#2f705e]" />Incoming: {session.imap_host}:{session.imap_port}<br />Outgoing: {session.smtp_host}:{session.smtp_port}</div>
        </aside>

        <section className="min-w-0 p-3 sm:p-5">
          <div className="mb-4 flex items-center gap-3">
            <form onSubmit={(event) => { event.preventDefault(); void loadMessages(folder, query); }} className="relative flex-1"><Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-[#82908a]" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search in external mail" className="min-h-12 w-full rounded-full border border-[#dde5e1] bg-white pl-11 pr-12 text-sm outline-none focus:border-[#397762]" />{query ? <button type="button" onClick={() => { setQuery(""); void loadMessages(folder, ""); }} className="absolute right-3 top-1/2 -translate-y-1/2 p-2 text-[#75857f]"><X size={16} /></button> : null}</form>
            <button onClick={() => { setCompose(emptyCompose); setComposeOpen(true); }} className="grid h-12 w-12 place-items-center rounded-full bg-[#14543f] text-white shadow-sm lg:hidden"><PenLine size={19} /></button>
          </div>

          <div className="overflow-hidden rounded-2xl border border-[#dfe6e3] bg-white shadow-sm">
            <div className="flex items-center border-b border-[#e6ece9] px-4 py-3"><div><p className="text-sm font-black text-[#2d4039]">{folder}</p><p className="text-[10px] text-[#798983]">{messages.length} loaded messages</p></div>{loading ? <Loader2 size={17} className="ml-auto animate-spin text-[#2c725e]" /> : null}</div>
            <div className="divide-y divide-[#edf1ef]">
              {messages.length === 0 && !loading ? <div className="p-10 text-center text-sm text-[#7a8983]">No messages in this folder.</div> : null}
              {messages.map((row) => <div key={row.uid} className={`flex cursor-pointer items-center gap-3 px-3 py-3 transition hover:bg-[#f6f9f8] sm:px-4 ${row.seen ? "bg-white" : "bg-[#f4f8f6]"}`} onClick={() => void openMessage(row)}><div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[#dfeee7] text-xs font-black text-[#245c4d]">{initials(row.from)}</div><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><p className={`truncate text-sm ${row.seen ? "font-semibold" : "font-black"}`}>{senderName(row.from)}</p><span className="ml-auto shrink-0 text-[10px] text-[#73827c]">{shortDate(row.date)}</span></div><p className={`truncate text-xs ${row.seen ? "text-[#566861]" : "font-bold text-[#2e443c]"}`}>{row.subject}</p><p className="truncate text-[11px] text-[#84918c]">{row.snippet}</p></div><button onClick={(event) => { event.stopPropagation(); void toggleStar(row); }} className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-[#71817a] hover:bg-[#edf3f0]" title="Star"><Star size={18} fill={row.flagged ? "#d6b84a" : "none"} className={row.flagged ? "text-[#b4972d]" : ""} /></button></div>)}
            </div>
          </div>
        </section>
      </div>

      {mobileFolders ? <div className="fixed inset-0 z-[80] bg-black/35 lg:hidden" onClick={() => setMobileFolders(false)}><aside className="h-full w-[82%] max-w-[320px] bg-white p-4" onClick={(event) => event.stopPropagation()}><div className="mb-5 flex items-center justify-between"><p className="font-black text-[#1b453a]">External folders</p><button onClick={() => setMobileFolders(false)}><X size={20} /></button></div>{folders.map((item) => <button key={item.name} onClick={() => { setMobileFolders(false); setFolder(item.name); void loadMessages(item.name); }} className={`mb-1 flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm ${folder === item.name ? "bg-[#e7f0ec] font-black" : "font-semibold"}`}>{folderIcon(item.name)}<span className="flex-1 truncate text-left">{item.name}</span><span>{countFor(item.name) || ""}</span></button>)}</aside></div> : null}

      {selected ? <div className="fixed inset-0 z-[70] overflow-y-auto bg-white"><header className="sticky top-0 flex h-16 items-center gap-2 border-b border-[#e4eae7] bg-white px-3 sm:px-5"><button onClick={() => setSelected(null)} className="grid h-10 w-10 place-items-center rounded-full hover:bg-[#f0f4f2]"><ArrowLeft size={21} /></button><div className="ml-auto flex gap-1"><button onClick={() => void toggleStar(selected)} className="grid h-10 w-10 place-items-center rounded-full hover:bg-[#f0f4f2]"><Star size={20} fill={selected.flagged ? "#d6b84a" : "none"} /></button><button onClick={() => void remove(selected)} className="grid h-10 w-10 place-items-center rounded-full hover:bg-[#f0f4f2]"><Trash2 size={20} /></button></div></header><article className="mx-auto max-w-4xl px-5 py-7 sm:px-8"><h1 className="text-2xl font-semibold tracking-tight text-[#202824]">{selected.subject}</h1><div className="mt-7 flex items-start gap-3"><div className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#dfeee7] text-sm font-black text-[#245c4d]">{initials(selected.from)}</div><div className="min-w-0"><p className="font-bold text-[#273833]">{senderName(selected.from)} <span className="font-normal text-[#75837e]">&lt;{addressOnly(selected.from)}&gt;</span></p><p className="text-xs text-[#788781]">to {selected.to || "me"} • {shortDate(selected.date)}</p></div><button onClick={() => startReply(selected)} className="ml-auto grid h-10 w-10 place-items-center rounded-full hover:bg-[#f0f4f2]"><Reply size={20} /></button></div><div className="mt-9 whitespace-pre-wrap text-[15px] leading-7 text-[#252e2b]">{selected.body_text || selected.snippet}</div>{selected.attachments?.length ? <div className="mt-8 border-t border-[#e5eae8] pt-5"><p className="mb-3 text-xs font-black uppercase tracking-wide text-[#60716a]">Attachments</p><div className="flex flex-wrap gap-2">{selected.attachments.map((item) => <a key={item.index} href={`${API}/webmail/external/messages/${selected.uid}/attachments/${item.index}?folder=${encodeURIComponent(folder)}`} className="inline-flex items-center gap-2 rounded-xl border border-[#dce4e0] bg-[#f8faf9] px-3 py-2 text-xs font-semibold text-[#40554d]"><Paperclip size={15} />{item.filename}<Download size={14} /></a>)}</div></div> : null}<div className="mt-10 flex gap-2"><button onClick={() => startReply(selected)} className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-[#d7dfdc] px-5 text-sm font-bold hover:bg-[#f3f6f5]"><Reply size={17} /> Reply</button></div></article></div> : null}

      {composeOpen ? <div className="fixed inset-0 z-[90] flex items-end justify-center bg-black/25 p-0 sm:items-center sm:p-5"><form onSubmit={sendMessage} className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-[24px] bg-white shadow-2xl sm:rounded-[24px]"><div className="flex items-center border-b border-[#e5ebe8] px-4 py-3"><p className="text-sm font-black text-[#274139]">New message</p><button type="button" onClick={() => { setComposeOpen(false); setCompose(emptyCompose); }} className="ml-auto grid h-9 w-9 place-items-center rounded-full hover:bg-[#f1f4f3]"><X size={18} /></button></div><div className="space-y-0 overflow-y-auto"><input required value={compose.to} onChange={(event) => setCompose((current) => ({ ...current, to: event.target.value }))} placeholder="To" className="min-h-12 w-full border-b border-[#e8edeb] px-4 text-sm outline-none" /><div className="grid grid-cols-2"><input value={compose.cc} onChange={(event) => setCompose((current) => ({ ...current, cc: event.target.value }))} placeholder="Cc" className="min-h-11 border-b border-r border-[#e8edeb] px-4 text-sm outline-none" /><input value={compose.bcc} onChange={(event) => setCompose((current) => ({ ...current, bcc: event.target.value }))} placeholder="Bcc" className="min-h-11 border-b border-[#e8edeb] px-4 text-sm outline-none" /></div><input value={compose.subject} onChange={(event) => setCompose((current) => ({ ...current, subject: event.target.value }))} placeholder="Subject" className="min-h-12 w-full border-b border-[#e8edeb] px-4 text-sm outline-none" /><textarea autoFocus value={compose.body_text} onChange={(event) => setCompose((current) => ({ ...current, body_text: event.target.value }))} placeholder="Write a message" className="min-h-[260px] w-full resize-none px-4 py-4 text-sm leading-6 outline-none" /></div>{compose.attachments.length ? <div className="flex flex-wrap gap-2 border-t border-[#e8edeb] px-4 py-3">{compose.attachments.map((item, index) => <span key={`${item.filename}-${index}`} className="rounded-lg bg-[#f0f4f2] px-2 py-1 text-[10px] font-semibold">{item.filename}</span>)}</div> : null}<div className="flex items-center gap-2 border-t border-[#e5ebe8] px-4 py-3"><button disabled={loading} className="inline-flex min-h-10 items-center gap-2 rounded-full bg-[#14543f] px-5 text-sm font-black text-white disabled:opacity-60">{loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />} Send</button><label className="grid h-10 w-10 cursor-pointer place-items-center rounded-full text-[#53665e] hover:bg-[#f0f4f2]" title="Attach files"><Paperclip size={18} /><input type="file" multiple className="hidden" onChange={(event) => void attachFiles(event.target.files)} /></label><button type="button" onClick={() => void saveDraft()} className="ml-auto rounded-full px-4 py-2 text-xs font-bold text-[#65766f] hover:bg-[#f0f4f2]">Save draft</button></div></form></div> : null}
    </main>
  );
}
