"use client";

import Link from "next/link";
import {
  ArrowLeft,
  ChevronDown,
  Clock3,
  Inbox,
  Loader2,
  Mail,
  Paperclip,
  RefreshCw,
  Search,
  Settings2,
  Star,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { MailContent, MailPrivacyNote } from "../mail-content";
import { API, initials, senderName, shortDate, type Attachment } from "../mail-types";

type UnifiedMessage = {
  uid: string;
  message_id: string;
  in_reply_to?: string;
  references?: string;
  from: string;
  to: string;
  cc: string;
  subject: string;
  date: string;
  seen: boolean;
  flagged: boolean;
  answered: boolean;
  snippet: string;
  attachments: Attachment[];
  body_text?: string;
  thread_key: string;
  source_key: string;
  source_type: "hosted" | "connected";
  account_id: string | null;
  account_address: string;
  account_label: string;
  provider: string;
  folder: string;
};

type UnifiedPayload = {
  items: UnifiedMessage[];
  errors: { source_key: string; address: string; error: string }[];
  sources: number;
  query: string;
};

type ThreadRow = {
  key: string;
  messages: UnifiedMessage[];
  latest: UnifiedMessage;
  unread: boolean;
};

async function mailApi(path: string, init?: RequestInit) {
  return fetch(`${API}/webmail${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
}

function groupThreads(items: UnifiedMessage[]): ThreadRow[] {
  const groups = new Map<string, UnifiedMessage[]>();
  for (const row of items) {
    const key = row.thread_key || `${row.source_key}:${row.uid}`;
    const current = groups.get(key) || [];
    current.push(row);
    groups.set(key, current);
  }
  return [...groups.entries()].map(([key, messages]) => {
    messages.sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
    const latest = messages[messages.length - 1];
    return { key, messages, latest, unread: messages.some((item) => !item.seen) };
  }).sort((a, b) => new Date(b.latest.date).getTime() - new Date(a.latest.date).getTime());
}

function providerBadge(provider: string) {
  if (provider === "ithute") return "iMail";
  if (provider === "google") return "Gmail";
  if (provider === "microsoft") return "Outlook";
  return provider ? provider[0].toUpperCase() + provider.slice(1) : "Mail";
}

function snoozeAt(kind: "later" | "tomorrow" | "week"): Date {
  const now = new Date();
  if (kind === "later") return new Date(now.getTime() + 3 * 60 * 60 * 1000);
  if (kind === "tomorrow") {
    const next = new Date(now);
    next.setDate(next.getDate() + 1);
    next.setHours(8, 0, 0, 0);
    return next;
  }
  const next = new Date(now);
  next.setDate(next.getDate() + 7);
  next.setHours(8, 0, 0, 0);
  return next;
}

export default function UnifiedInboxPage() {
  const [payload, setPayload] = useState<UnifiedPayload>({ items: [], errors: [], sources: 0, query: "" });
  const [query, setQuery] = useState("");
  const [accountFilter, setAccountFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [messageLoading, setMessageLoading] = useState(false);
  const [selectedThread, setSelectedThread] = useState<string>("");
  const [opened, setOpened] = useState<Record<string, UnifiedMessage>>({});
  const [error, setError] = useState("");
  const [snoozeOpen, setSnoozeOpen] = useState(false);

  const load = useCallback(async (search = query) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ limit: "120" });
      if (search.trim()) params.set("q", search.trim());
      const response = await mailApi(`/unified/inbox?${params}`);
      if (response.status === 401) {
        window.location.assign("/webmail");
        return;
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Unable to load Unified Inbox");
      setPayload(data);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load Unified Inbox");
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const account = params.get("account");
    if (account) setAccountFilter(account);
    void load("");
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const accounts = useMemo(() => {
    const map = new Map<string, { key: string; label: string; address: string; provider: string }>();
    for (const item of payload.items) {
      if (!map.has(item.source_key)) {
        map.set(item.source_key, { key: item.source_key, label: item.account_label, address: item.account_address, provider: item.provider });
      }
    }
    return [...map.values()];
  }, [payload.items]);

  const visibleItems = useMemo(
    () => accountFilter === "all" ? payload.items : payload.items.filter((item) => item.source_key === accountFilter),
    [accountFilter, payload.items],
  );
  const threads = useMemo(() => groupThreads(visibleItems), [visibleItems]);
  const selected = threads.find((thread) => thread.key === selectedThread) || null;

  async function openMessage(row: UnifiedMessage) {
    const cacheKey = `${row.source_key}:${row.folder}:${row.uid}`;
    if (opened[cacheKey]?.body_text !== undefined) return;
    setMessageLoading(true);
    try {
      const endpoint = row.source_type === "hosted"
        ? `/messages/${encodeURIComponent(row.uid)}?folder=${encodeURIComponent(row.folder)}`
        : `/connected-accounts/${encodeURIComponent(String(row.account_id))}/messages/${encodeURIComponent(row.uid)}?folder=${encodeURIComponent(row.folder)}`;
      const response = await mailApi(endpoint);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Unable to open message");
      setOpened((current) => ({ ...current, [cacheKey]: { ...row, ...data } }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to open message");
    } finally {
      setMessageLoading(false);
    }
  }

  function selectThread(thread: ThreadRow) {
    setSelectedThread(thread.key);
    setSnoozeOpen(false);
    const latest = thread.messages[thread.messages.length - 1];
    void openMessage(latest);
  }

  async function snoozeThread(kind: "later" | "tomorrow" | "week") {
    if (!selected) return;
    const wakeAt = snoozeAt(kind).toISOString();
    try {
      await Promise.all(selected.messages.map((row) => mailApi("/snoozes", {
        method: "POST",
        body: JSON.stringify({
          source_key: row.source_key,
          connected_account_id: row.account_id,
          folder: row.folder,
          message_uid: row.uid,
          message_id: row.message_id || "",
          wake_at: wakeAt,
        }),
      })));
      setSelectedThread("");
      setSnoozeOpen(false);
      await load(query);
    } catch {
      setError("Unable to snooze this conversation");
    }
  }

  const selectedMessages = selected?.messages || [];

  return (
    <main className="h-screen overflow-hidden bg-white text-[#202124] dark:bg-[#0f1418] dark:text-slate-100">
      <header className="flex h-16 items-center gap-3 border-b border-[#e2e6ea] bg-white px-3 dark:border-white/10 dark:bg-[#111820] sm:px-4">
        <Link href="/webmail" className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-[#5f6368] hover:bg-[#f1f3f4] dark:text-slate-300 dark:hover:bg-white/10" aria-label="Back"><ArrowLeft size={19} /></Link>
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[#0c6f55] text-xs font-bold text-white">iM</span>
        <div className="hidden min-w-0 sm:block"><p className="truncate text-sm font-semibold">Unified Inbox</p><p className="truncate text-[11px] text-[#6b7280] dark:text-slate-400">All your mail accounts in one place</p></div>
        <form onSubmit={(event) => { event.preventDefault(); void load(query); }} className="ml-0 flex min-w-0 flex-1 items-center gap-2 rounded-2xl border border-[#dfe3e8] bg-[#f6f8fc] px-3 focus-within:border-[#9bb6dc] focus-within:bg-white dark:border-white/10 dark:bg-white/5 dark:focus-within:bg-white/10 sm:ml-4 sm:max-w-2xl">
          <Search size={17} className="shrink-0 text-[#6b7280]" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} className="h-10 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-[#8a939f]" placeholder="Search all mail · from:amy has:attachment after:2026-09-01" />
        </form>
        <button onClick={() => void load(query)} className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-[#5f6368] hover:bg-[#f1f3f4] dark:text-slate-300 dark:hover:bg-white/10" title="Refresh"><RefreshCw size={17} /></button>
        <Link href="/webmail/accounts" className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-[#5f6368] hover:bg-[#f1f3f4] dark:text-slate-300 dark:hover:bg-white/10" title="Mail accounts"><Settings2 size={17} /></Link>
      </header>

      <div className="grid h-[calc(100vh-64px)] min-h-0 grid-cols-1 md:grid-cols-[250px_minmax(330px,430px)_minmax(0,1fr)]">
        <aside className="hidden min-h-0 border-r border-[#e4e7eb] bg-[#fafbfc] p-3 dark:border-white/10 dark:bg-[#111820] md:block">
          <Link href="/webmail" className="mb-4 flex items-center gap-2 rounded-xl bg-[#eaf1fb] px-3 py-3 text-sm font-semibold text-[#174ea6] hover:bg-[#dce8fb] dark:bg-blue-950/40 dark:text-blue-200"><Mail size={17} /> Compose in iMail</Link>
          <button onClick={() => setAccountFilter("all")} className={`mb-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm ${accountFilter === "all" ? "bg-[#e8f0fe] font-semibold text-[#174ea6] dark:bg-blue-950/40 dark:text-blue-200" : "text-[#4b5563] hover:bg-[#eef1f4] dark:text-slate-300 dark:hover:bg-white/5"}`}><Inbox size={17} /><span className="min-w-0 flex-1 truncate">All inboxes</span><span className="text-xs text-[#6b7280] dark:text-slate-400">{payload.items.filter((row) => !row.seen).length}</span></button>
          <div className="my-3 border-t border-[#e3e7eb] dark:border-white/10" />
          <p className="px-3 pb-2 text-[10px] font-bold uppercase tracking-[.16em] text-[#8a94a0]">Accounts</p>
          <div className="space-y-1">
            {accounts.map((item) => <button key={item.key} onClick={() => setAccountFilter(item.key)} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left ${accountFilter === item.key ? "bg-[#eef4ff] text-[#174ea6] dark:bg-blue-950/40 dark:text-blue-200" : "text-[#4b5563] hover:bg-[#eef1f4] dark:text-slate-300 dark:hover:bg-white/5"}`}><span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-white text-[10px] font-bold shadow-sm dark:bg-white/10">{item.provider === "ithute" ? "iM" : providerBadge(item.provider).slice(0, 2)}</span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{item.label}</span><span className="block truncate text-[10px] text-[#8a94a0]">{item.address}</span></span></button>)}
          </div>
          <div className="absolute bottom-3 left-3 right-3 hidden md:block"><Link href="/webmail/accounts" className="flex items-center justify-center rounded-xl border border-[#dce2e9] bg-white px-3 py-2 text-xs font-semibold hover:bg-[#f8fafc] dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10">Manage accounts</Link></div>
        </aside>

        <section className={`${selected ? "hidden md:flex" : "flex"} min-h-0 min-w-0 flex-col border-r border-[#e4e7eb] bg-white dark:border-white/10 dark:bg-[#10171c]`}>
          <div className="flex h-11 shrink-0 items-center justify-between border-b border-[#e4e7eb] px-3 dark:border-white/10"><div className="min-w-0"><p className="truncate text-[11px] font-bold uppercase tracking-[.12em] text-[#586579] dark:text-slate-400">{accountFilter === "all" ? "All inboxes" : accounts.find((item) => item.key === accountFilter)?.label || "Inbox"}</p><p className="text-[10px] text-[#8a94a0]">{threads.length} conversations · {payload.sources} sources</p></div>{loading ? <Loader2 size={15} className="animate-spin text-[#0b57d0]" /> : null}</div>
          {error ? <div className="m-3 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900/50 dark:bg-red-950/20 dark:text-red-200"><TriangleAlert size={14} className="mt-0.5 shrink-0" />{error}</div> : null}
          {payload.errors.length ? <div className="mx-3 mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-200">{payload.errors.length} account source{payload.errors.length === 1 ? "" : "s"} could not refresh. Your other inboxes are still available.</div> : null}
          <div className="min-h-0 flex-1 overflow-y-auto">
            {!loading && !threads.length ? <div className="grid min-h-64 place-items-center px-6 text-center"><div><Inbox className="mx-auto mb-3 text-[#9aa3ad]" size={30} /><p className="font-semibold">No messages here</p><p className="mt-1 text-sm text-[#6b7280] dark:text-slate-400">Try another account or change your search.</p></div></div> : null}
            {threads.map((thread) => {
              const row = thread.latest;
              const active = selectedThread === thread.key;
              return <button key={thread.key} onClick={() => selectThread(thread)} className={`group flex w-full items-start gap-3 border-b border-[#edf0f2] px-3 py-3 text-left transition dark:border-white/[.06] ${active ? "border-l-[3px] border-l-[#0b57d0] bg-[#eef4ff] dark:bg-blue-950/30" : thread.unread ? "bg-white hover:bg-[#f7f9fc] dark:bg-[#111920] dark:hover:bg-white/[.045]" : "bg-[#fafbfc] hover:bg-[#f4f6f8] dark:bg-[#0f161b] dark:hover:bg-white/[.04]"}`}><span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#eaf1fb] text-[10px] font-bold text-[#315b91] dark:bg-white/10 dark:text-slate-200">{initials(row.from)}</span><span className="min-w-0 flex-1"><span className="flex items-center gap-2"><span className={`min-w-0 flex-1 truncate text-sm ${thread.unread ? "font-bold" : "font-medium"}`}>{senderName(row.from)}</span><span className="shrink-0 text-[10px] text-[#7b8794]">{shortDate(row.date)}</span></span><span className={`mt-0.5 flex items-center gap-1.5 truncate text-[12px] ${thread.unread ? "font-semibold text-[#28394f] dark:text-slate-200" : "text-[#5f6b78] dark:text-slate-400"}`}><span className="truncate">{row.subject || "(no subject)"}</span>{thread.messages.length > 1 ? <span className="shrink-0 rounded-full bg-[#e6ebf1] px-1.5 text-[9px] text-[#586579] dark:bg-white/10 dark:text-slate-300">{thread.messages.length}</span> : null}{row.attachments?.length ? <Paperclip size={11} className="shrink-0" /> : null}</span><span className="mt-1 block truncate text-[11px] text-[#88929e]">{row.snippet}</span><span className="mt-1.5 inline-flex rounded-full bg-[#f0f3f7] px-2 py-0.5 text-[9px] font-semibold text-[#667381] dark:bg-white/[.07] dark:text-slate-400">{providerBadge(row.provider)} · {row.account_address}</span></span>{row.flagged ? <Star size={14} className="mt-0.5 shrink-0 fill-amber-400 text-amber-500" /> : null}</button>;
            })}
          </div>
        </section>

        <section className={`${selected ? "flex" : "hidden md:flex"} min-h-0 min-w-0 flex-col bg-white dark:bg-[#111820]`}>
          {!selected ? <div className="grid min-h-0 flex-1 place-items-center px-8 text-center"><div><Mail className="mx-auto mb-3 text-[#a0a9b3]" size={34} /><p className="font-semibold">Choose a conversation</p><p className="mt-1 max-w-sm text-sm text-[#6b7280] dark:text-slate-400">Messages from Ithute Mail, Gmail, Outlook and connected accounts stay together here.</p></div></div> : <>
            <div className="flex h-11 shrink-0 items-center gap-1 border-b border-[#e4e7eb] px-2 dark:border-white/10"><button onClick={() => setSelectedThread("")} className="grid h-8 w-8 place-items-center rounded-full text-[#5f6368] hover:bg-[#f1f3f4] dark:text-slate-300 dark:hover:bg-white/10 md:hidden"><ArrowLeft size={17} /></button><button onClick={() => setSnoozeOpen((value) => !value)} className="relative inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-xs font-semibold text-[#5f6368] hover:bg-[#f1f3f4] dark:text-slate-300 dark:hover:bg-white/10"><Clock3 size={15} /> Snooze <ChevronDown size={13} />{snoozeOpen ? <span className="absolute left-0 top-full z-30 mt-1 w-44 overflow-hidden rounded-xl border border-[#d9dee5] bg-white py-1 text-left shadow-xl dark:border-white/10 dark:bg-[#182027]"><span onClick={() => void snoozeThread("later")} className="block cursor-pointer px-3 py-2 hover:bg-[#f3f6f9] dark:hover:bg-white/5">Later today</span><span onClick={() => void snoozeThread("tomorrow")} className="block cursor-pointer px-3 py-2 hover:bg-[#f3f6f9] dark:hover:bg-white/5">Tomorrow morning</span><span onClick={() => void snoozeThread("week")} className="block cursor-pointer px-3 py-2 hover:bg-[#f3f6f9] dark:hover:bg-white/5">Next week</span></span> : null}</button><div className="ml-auto flex items-center gap-2 text-[10px] text-[#7b8794]"><span>{selected.messages.length} message{selected.messages.length === 1 ? "" : "s"}</span>{messageLoading ? <Loader2 size={14} className="animate-spin text-[#0b57d0]" /> : null}</div></div>
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6 lg:px-8">
              <h1 className="mb-5 text-xl font-semibold leading-tight text-[#1f2937] dark:text-slate-100 sm:text-2xl">{selected.latest.subject || "(no subject)"}</h1>
              <div className="space-y-4">
                {selectedMessages.map((row, index) => {
                  const key = `${row.source_key}:${row.folder}:${row.uid}`;
                  const full = opened[key] || row;
                  const latest = index === selectedMessages.length - 1;
                  return <article key={key} className="rounded-2xl border border-[#e1e6eb] bg-white p-4 shadow-sm dark:border-white/10 dark:bg-white/[.025] sm:p-5" onClick={() => void openMessage(row)}><div className="mb-3 flex items-start gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#eaf1fb] text-[10px] font-bold text-[#315b91] dark:bg-white/10 dark:text-slate-200">{initials(row.from)}</span><div className="min-w-0 flex-1"><div className="flex gap-2"><p className="min-w-0 flex-1 truncate text-sm font-semibold">{senderName(row.from)}</p><time className="shrink-0 text-[10px] text-[#7b8794]">{shortDate(row.date)}</time></div><p className="truncate text-[11px] text-[#7b8794]">to {row.to || row.account_address} · via {providerBadge(row.provider)}</p></div></div>{latest ? <MailPrivacyNote mode={row.source_type === "hosted" ? "hosted" : "external"} /> : null}<div className="mt-4"><MailContent text={full.body_text !== undefined ? full.body_text : row.snippet} /></div>{row.attachments?.length ? <div className="mt-4 flex flex-wrap gap-2">{row.attachments.map((attachment) => <span key={`${key}:${attachment.index}`} className="inline-flex items-center gap-1.5 rounded-xl border border-[#dce2e9] bg-[#fafbfc] px-3 py-2 text-xs dark:border-white/10 dark:bg-white/5"><Paperclip size={13} />{attachment.filename}</span>)}</div> : null}<div className="mt-4 flex items-center justify-between gap-3 border-t border-[#edf0f2] pt-3 dark:border-white/10"><span className="text-[10px] text-[#8a94a0]">{row.account_address}</span><Link href={row.source_type === "hosted" ? `/webmail?folder=${encodeURIComponent(row.folder)}&message=${encodeURIComponent(row.uid)}` : `/webmail/unified?account=${encodeURIComponent(row.source_key)}`} className="text-xs font-semibold text-[#0b57d0] hover:underline">Open in mailbox</Link></div></article>;
                })}
              </div>
            </div>
          </>}
        </section>
      </div>
    </main>
  );
}
