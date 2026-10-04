"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { BellRing, Building2, FileText, Mail, MessageCircle, NotebookPen, Pin, Plus, Search, Send, UsersRound } from "lucide-react";

import { API, humanBytes, initials, senderName, shortDate, webmail, type MessageRow } from "./mail-types";

type BusinessContact = {
  email: string;
  name?: string;
  online?: boolean;
  interactions?: number;
  last_seen?: string;
  pinned?: boolean;
  domain?: string;
};

type Workspace = {
  contact: BusinessContact;
  company: { domain: string; people: BusinessContact[] };
  overview: { emails: number; documents: number; status: string; online: boolean; internal_chat: boolean };
  emails: Array<MessageRow & { folder?: string; direction?: "incoming" | "outgoing" }>;
  documents: Array<{ index: number; filename: string; content_type: string; size: number; message_uid: string; folder: string; subject: string; date: string; direction?: string }>;
  notes: Array<{ text: string; created_at: string }>;
  tasks: Array<{ id: string; text: string; due_at?: string; completed?: boolean; created_at: string }>;
  timeline: Array<{ type: string; direction?: string; subject: string; date: string; uid: string; folder?: string; attachments?: number }>;
  shared_contacts: BusinessContact[];
  chat: Array<{ from: string; to: string; text: string; created_at: string }>;
};

type Tab = "overview" | "emails" | "documents" | "people" | "notes" | "activity" | "chat";

export function BusinessContactWorkspace({
  email,
  mailboxAddress,
  onClose,
  onCompose,
  onOpenMessage,
  onChanged,
}: {
  email: string;
  mailboxAddress: string;
  onClose: () => void;
  onCompose: (email: string) => void;
  onOpenMessage: (row: MessageRow & { folder?: string }) => void;
  onChanged?: () => void;
}) {
  const [data, setData] = useState<Workspace | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [task, setTask] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [chatText, setChatText] = useState("");
  const [search, setSearch] = useState("");

  async function load(silent = false) {
    if (!silent) setLoading(true);
    try {
      const response = await webmail(`/business-workspace?email=${encodeURIComponent(email)}`);
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Unable to load relationship workspace");
      setData(await response.json());
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load relationship workspace");
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [email]);

  useEffect(() => {
    if (!data?.overview.internal_chat) return;
    const timer = window.setInterval(() => void load(true), 15000);
    return () => window.clearInterval(timer);
  }, [data?.overview.internal_chat, email]);

  const title = data?.contact.name || senderName(email);
  const normalizedSearch = search.trim().toLowerCase();
  const matches = (value: unknown) => !normalizedSearch || String(value || "").toLowerCase().includes(normalizedSearch);
  const filteredEmails = (data?.emails || []).filter((row) =>
    [row.from, row.to, row.cc, row.subject, row.snippet, row.date, row.direction].some(matches),
  );
  const filteredDocuments = (data?.documents || []).filter((item) =>
    [item.filename, item.content_type, item.subject, item.date, item.direction].some(matches),
  );
  const filteredPeople = (data?.company.people || []).filter((person) =>
    [person.name, person.email, person.domain].some(matches),
  );
  const filteredTimeline = (data?.timeline || []).filter((item) =>
    [item.subject, item.date, item.direction, item.folder].some(matches),
  );
  const tabs = useMemo<Tab[]>(() => {
    const base: Tab[] = ["overview", "emails", "documents", "people", "notes", "activity"];
    if (data?.overview.internal_chat) base.push("chat");
    return base;
  }, [data?.overview.internal_chat]);

  async function togglePin() {
    if (!data) return;
    const response = await webmail("/business-contacts/pin", {
      method: "PUT",
      body: JSON.stringify({ email, pinned: !data.contact.pinned }),
    });
    if (response.ok) {
      await load(true);
      onChanged?.();
    }
  }

  async function addNote(event: FormEvent) {
    event.preventDefault();
    if (!note.trim()) return;
    const response = await webmail("/business-notes", { method: "POST", body: JSON.stringify({ email, text: note }) });
    if (response.ok) {
      setNote("");
      await load(true);
    }
  }

  async function addTask(event: FormEvent) {
    event.preventDefault();
    if (!task.trim()) return;
    const response = await webmail("/business-tasks", { method: "POST", body: JSON.stringify({ email, text: task, due_at: dueAt }) });
    if (response.ok) {
      setTask("");
      setDueAt("");
      await load(true);
    }
  }

  async function sendChat(event: FormEvent) {
    event.preventDefault();
    if (!chatText.trim()) return;
    const response = await webmail("/business-chat", { method: "POST", body: JSON.stringify({ email, text: chatText }) });
    if (response.ok) {
      setChatText("");
      await load(true);
    }
  }

  function downloadDocument(item: Workspace["documents"][number]) {
    window.open(`${API}/webmail/messages/${item.message_uid}/attachments/${item.index}?folder=${encodeURIComponent(item.folder || "INBOX")}`, "_blank", "noopener,noreferrer");
  }

  if (loading) return <section className="grid min-h-0 flex-1 place-items-center bg-white p-8 text-sm font-semibold text-slate-500 dark:bg-slate-900">Loading business relationship…</section>;

  return (
    <section className="flex min-h-0 flex-1 flex-col bg-white dark:bg-slate-900">
      <div className="border-b border-slate-200 px-4 py-4 dark:border-white/10 sm:px-6">
        <div className="flex items-start gap-3">
          <button type="button" onClick={onClose} className="mt-1 rounded-full px-2 py-1 text-sm font-black text-slate-500 hover:bg-slate-100">←</button>
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-[#eaf1fb] text-sm font-black text-[#174ea6] dark:bg-blue-400/10 dark:text-blue-200">{initials(title)}</span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2"><h2 className="truncate text-lg font-black text-slate-900 dark:text-white">{title}</h2>{data?.overview.online ? <span className="rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-black text-emerald-700">Online now</span> : null}</div>
            <p className="truncate text-xs text-slate-500">{email}</p>
            <p className="mt-1 text-[11px] font-bold text-[#174ea6]">{data?.overview.status}</p>
          </div>
          <button type="button" onClick={() => void togglePin()} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100" title={data?.contact.pinned ? "Unpin contact" : "Pin contact"}><Pin size={17} fill={data?.contact.pinned ? "currentColor" : "none"} /></button>
          <button type="button" onClick={() => onCompose(email)} className="inline-flex h-9 items-center gap-2 rounded-xl bg-[#0b57d0] px-3 text-xs font-black text-white"><Mail size={15}/> Email</button>
        </div>
        <div className="mt-4 flex items-center gap-2 rounded-xl border border-slate-200 px-3 dark:border-white/10">
          <Search size={15} className="shrink-0 text-slate-400"/>
          <input value={search} onChange={(event) => setSearch(event.target.value)} className="h-10 min-w-0 flex-1 bg-transparent text-xs outline-none" placeholder="Search this relationship: sender, subject, document, date, domain…"/>
        </div>
        <div className="mt-3 flex gap-1 overflow-x-auto">
          {tabs.map((item) => <button key={item} type="button" onClick={() => setTab(item)} className={`whitespace-nowrap rounded-lg px-3 py-2 text-xs font-black capitalize ${tab === item ? "bg-[#eaf1fb] text-[#174ea6]" : "text-slate-500 hover:bg-slate-100 dark:hover:bg-white/5"}`}>{item}</button>)}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
        {error ? <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}
        {tab === "overview" && data ? <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[["Emails", data.overview.emails, Mail], ["Documents", data.overview.documents, FileText], ["People", data.company.people.length, UsersRound], ["Tasks", data.tasks.filter((item) => !item.completed).length, BellRing]].map(([label, value, Icon]) => {
              const Comp = Icon as typeof Mail;
              return <div key={String(label)} className="rounded-2xl border border-slate-200 p-4 dark:border-white/10"><Comp size={18} className="text-[#174ea6]"/><p className="mt-3 text-2xl font-black text-slate-900 dark:text-white">{String(value)}</p><p className="text-xs font-bold text-slate-500">{String(label)}</p></div>;
            })}
          </div>
          <div className="rounded-2xl border border-slate-200 p-4 dark:border-white/10"><p className="flex items-center gap-2 text-xs font-black uppercase tracking-[.12em] text-slate-500"><Building2 size={14}/> Company</p><p className="mt-2 text-lg font-black text-slate-900 dark:text-white">{data.company.domain || "Unknown domain"}</p><p className="mt-1 text-xs text-slate-500">{data.company.people.length} known contact{data.company.people.length === 1 ? "" : "s"} from this company.</p></div>
          <div className="grid gap-4 xl:grid-cols-2">
            <form onSubmit={addNote} className="rounded-2xl border border-slate-200 p-4 dark:border-white/10"><p className="flex items-center gap-2 text-xs font-black uppercase tracking-[.12em] text-slate-500"><NotebookPen size={14}/> Private note</p><textarea value={note} onChange={(e) => setNote(e.target.value)} className="mt-3 min-h-24 w-full rounded-xl border border-slate-200 bg-transparent p-3 text-sm outline-none focus:border-blue-400 dark:border-white/10" placeholder="Add a relationship note…"/><button className="mt-2 rounded-lg bg-slate-900 px-3 py-2 text-xs font-black text-white">Save note</button></form>
            <form onSubmit={addTask} className="rounded-2xl border border-slate-200 p-4 dark:border-white/10"><p className="flex items-center gap-2 text-xs font-black uppercase tracking-[.12em] text-slate-500"><BellRing size={14}/> Follow-up task</p><input value={task} onChange={(e) => setTask(e.target.value)} className="mt-3 h-10 w-full rounded-xl border border-slate-200 bg-transparent px-3 text-sm outline-none focus:border-blue-400 dark:border-white/10" placeholder="What needs to happen next?"/><input type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} className="mt-2 h-10 w-full rounded-xl border border-slate-200 bg-transparent px-3 text-xs dark:border-white/10"/><button className="mt-2 rounded-lg bg-slate-900 px-3 py-2 text-xs font-black text-white">Add task</button></form>
          </div>
        </div> : null}

        {tab === "emails" && data ? <div className="space-y-2">{filteredEmails.map((row) => <button key={`${row.folder}-${row.uid}`} type="button" onClick={() => onOpenMessage(row)} className="flex w-full items-center gap-3 rounded-xl border border-slate-200 p-3 text-left hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5"><span className="grid h-9 w-9 place-items-center rounded-full bg-slate-100 text-slate-500 dark:bg-white/10">{row.direction === "outgoing" ? <Send size={15}/> : <Mail size={15}/>}</span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-black text-slate-800 dark:text-white">{row.subject || "(no subject)"}</span><span className="block truncate text-xs text-slate-500">{row.snippet}</span></span><time className="text-[10px] font-bold text-slate-400">{shortDate(row.date)}</time></button>)}</div> : null}

        {tab === "documents" && data ? <div className="grid gap-3 md:grid-cols-2">{filteredDocuments.map((item, index) => <button key={`${item.message_uid}-${item.index}-${index}`} type="button" onClick={() => downloadDocument(item)} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3 text-left hover:bg-slate-50 dark:border-white/10 dark:hover:bg-white/5"><FileText size={18} className="text-[#174ea6]"/><span className="min-w-0 flex-1"><span className="block truncate text-sm font-black text-slate-800 dark:text-white">{item.filename}</span><span className="block truncate text-[10px] text-slate-500">{item.subject || "(no subject)"} · {humanBytes(item.size || 0)}</span></span></button>)}</div> : null}

        {tab === "people" && data ? <div className="space-y-4"><div><p className="mb-2 text-xs font-black uppercase tracking-[.12em] text-slate-500">People at {data.company.domain}</p><div className="grid gap-2 md:grid-cols-2">{filteredPeople.map((person) => <button key={person.email} type="button" onClick={() => onCompose(person.email)} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3 text-left dark:border-white/10"><span className="grid h-9 w-9 place-items-center rounded-full bg-[#eaf1fb] text-xs font-black text-[#174ea6]">{initials(person.name || person.email)}</span><span className="min-w-0"><span className="block truncate text-sm font-black">{person.name || senderName(person.email)}</span><span className="block truncate text-xs text-slate-500">{person.email}</span></span></button>)}</div></div><div><p className="mb-2 text-xs font-black uppercase tracking-[.12em] text-slate-500">Shared company contacts</p><p className="text-xs text-slate-500">{data.shared_contacts.length} contact{data.shared_contacts.length === 1 ? "" : "s"} available to mailboxes on your company domain.</p></div></div> : null}

        {tab === "notes" && data ? <div className="space-y-4"><form onSubmit={addNote} className="flex gap-2"><input value={note} onChange={(e) => setNote(e.target.value)} className="h-10 min-w-0 flex-1 rounded-xl border border-slate-200 bg-transparent px-3 text-sm dark:border-white/10" placeholder="Add a note…"/><button className="rounded-xl bg-[#0b57d0] px-3 text-xs font-black text-white"><Plus size={15}/></button></form>{data.notes.map((item, index) => <div key={`${item.created_at}-${index}`} className="rounded-xl border border-slate-200 p-3 dark:border-white/10"><p className="text-sm font-medium text-slate-800 dark:text-slate-100">{item.text}</p><p className="mt-2 text-[10px] font-bold text-slate-400">{shortDate(item.created_at)}</p></div>)}</div> : null}

        {tab === "activity" && data ? <div className="space-y-2">{data.tasks.map((item) => <div key={item.id} className="rounded-xl border border-slate-200 p-3 dark:border-white/10"><p className="text-sm font-black text-slate-800 dark:text-white">{item.text}</p><p className="mt-1 text-[10px] text-slate-500">{item.due_at ? `Due ${item.due_at}` : "No due date"}</p></div>)}{filteredTimeline.map((item) => <div key={`${item.folder}-${item.uid}`} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3 dark:border-white/10"><Mail size={15} className="text-slate-400"/><span className="min-w-0 flex-1 truncate text-xs font-bold text-slate-700 dark:text-slate-200">{item.direction === "outgoing" ? "Sent" : "Received"} · {item.subject}</span><span className="text-[10px] text-slate-400">{shortDate(item.date)}</span></div>)}</div> : null}

        {tab === "chat" && data?.overview.internal_chat ? <div className="flex min-h-[420px] flex-col"><div className="mb-3 flex items-center gap-2 rounded-xl bg-emerald-50 p-3 text-xs font-bold text-emerald-800"><MessageCircle size={15}/> Internal iMail chat is available because both addresses use {data.company.domain}.</div><div className="min-h-0 flex-1 space-y-2 overflow-y-auto rounded-2xl border border-slate-200 p-3 dark:border-white/10">{data.chat.map((item, index) => <div key={`${item.created_at}-${index}`} className={`flex ${item.from.toLowerCase() === mailboxAddress.toLowerCase() ? "justify-end" : "justify-start"}`}><div className={`max-w-[78%] rounded-2xl px-3 py-2 text-sm ${item.from.toLowerCase() === mailboxAddress.toLowerCase() ? "bg-[#0b57d0] text-white" : "bg-slate-100 text-slate-800 dark:bg-white/10 dark:text-white"}`}><p>{item.text}</p><p className="mt-1 text-[9px] opacity-70">{shortDate(item.created_at)}</p></div></div>)}</div><form onSubmit={sendChat} className="mt-3 flex gap-2"><input value={chatText} onChange={(e) => setChatText(e.target.value)} className="h-11 min-w-0 flex-1 rounded-xl border border-slate-200 bg-transparent px-3 text-sm dark:border-white/10" placeholder="Message this colleague…"/><button className="grid h-11 w-11 place-items-center rounded-xl bg-[#0b57d0] text-white"><Send size={16}/></button></form></div> : null}
      </div>
    </section>
  );
}
