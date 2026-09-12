"use client";

import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  CloudDownload,
  ExternalLink,
  Inbox,
  Loader2,
  Mail,
  RefreshCw,
  Server,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { API } from "../mail-types";

type Provider = {
  key: string;
  name: string;
  detected_by?: string;
  auth_mode?: string;
  imap_host?: string;
  imap_port?: number;
  imap_security?: string;
  smtp_host?: string;
  smtp_port?: number;
  smtp_security?: string;
  help_text?: string;
};

type Detection = {
  address: string;
  domain: string;
  detected: boolean;
  provider: Provider;
};

type Readiness = {
  ready: boolean;
  issues: string[];
  source: null | { address: string; provider: Provider; imap_host: string };
  destination: null | { address: string; active: boolean; mailbox_id?: string | null };
  behavior: {
    copies_mail: boolean;
    deletes_source: boolean;
    preserves_folders: boolean;
    safe_to_resume: boolean;
  };
};

type MigrationJob = {
  id: string;
  destination: string;
  source_provider: string;
  source_username: string;
  status: "queued" | "running" | "completed" | "failed" | string;
  folders_total: number;
  folders_done: number;
  messages_copied: number;
  bytes_copied: number;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
};

async function external(path: string, init?: RequestInit) {
  return fetch(`${API}/webmail/external${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
}

function prettyBytes(value: number) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size >= 10 || index === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[index]}`;
}

function providerTone(key?: string) {
  if (key === "google") return "G";
  if (key === "microsoft365") return "M";
  if (key === "yahoo") return "Y";
  if (key === "icloud") return "iC";
  if (key === "zoho") return "Z";
  if (key === "fastmail") return "F";
  return "IM";
}

export default function MailMigrationPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [detection, setDetection] = useState<Detection | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [loadingReadiness, setLoadingReadiness] = useState(true);
  const [starting, setStarting] = useState(false);
  const [job, setJob] = useState<MigrationJob | null>(null);
  const [history, setHistory] = useState<MigrationJob[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadReadiness = useCallback(async () => {
    setLoadingReadiness(true);
    try {
      const response = await external("/migration/readiness");
      if (!response.ok) throw new Error("Unable to check migration readiness");
      const data = (await response.json()) as Readiness;
      setReadiness(data);
      if (data.source?.address) setEmail(data.source.address);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to check migration readiness");
    } finally {
      setLoadingReadiness(false);
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const response = await external("/migration/jobs");
      if (!response.ok) return;
      const data = await response.json();
      setHistory((data.items || []) as MigrationJob[]);
      const active = (data.items || []).find((item: MigrationJob) => item.status === "queued" || item.status === "running");
      if (active) setJob(active);
    } catch {
      // History is helpful but must never block the migration wizard.
    }
  }, []);

  useEffect(() => {
    void Promise.all([loadReadiness(), loadHistory()]);
  }, [loadHistory, loadReadiness]);

  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const response = await external(`/migration/jobs/${job.id}`);
        if (!response.ok) return;
        const latest = (await response.json()) as MigrationJob;
        setJob(latest);
        setHistory((current) => [latest, ...current.filter((item) => item.id !== latest.id)].slice(0, 20));
        if (latest.status === "completed") {
          setNotice(`Migration complete: ${latest.messages_copied.toLocaleString()} messages copied.`);
          void loadReadiness();
        } else if (latest.status === "failed") {
          setError(latest.error || "The migration failed. You can safely retry after correcting the connection.");
        }
      } catch {
        // A temporary polling failure should not cancel the server-side job.
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [job, loadReadiness]);

  const detect = useCallback(async (value?: string) => {
    const address = (value ?? email).trim().toLowerCase();
    if (!address || !address.includes("@")) return;
    setDetecting(true);
    setError("");
    try {
      const response = await external(`/provider-detect?address=${encodeURIComponent(address)}`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Unable to detect this mail provider");
      setDetection(data as Detection);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to detect this mail provider");
    } finally {
      setDetecting(false);
    }
  }, [email]);

  async function connectSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const address = email.trim().toLowerCase();
    if (!address) return;
    setConnecting(true);
    setError("");
    setNotice("");
    try {
      if (!detection || detection.address !== address) await detect(address);
      const response = await external("/session", {
        method: "POST",
        body: JSON.stringify({
          address,
          username: address,
          password,
          display_name: "",
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Unable to connect this mailbox");
      setPassword("");
      setNotice(`${data.provider?.name || "External mailbox"} connected securely.`);
      await Promise.all([loadReadiness(), loadHistory()]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to connect this mailbox");
    } finally {
      setConnecting(false);
    }
  }

  async function startMigration() {
    if (!readiness?.ready || !readiness.destination?.address) return;
    setStarting(true);
    setError("");
    setNotice("");
    try {
      const response = await external("/migration/start", {
        method: "POST",
        body: JSON.stringify({ destination_address: readiness.destination.address }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Unable to start migration");
      setJob(data.job as MigrationJob);
      setNotice(data.already_running ? "A migration is already running for this business mailbox." : "Migration queued. You can leave this page while iMail copies the mailbox.");
      await loadHistory();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to start migration");
    } finally {
      setStarting(false);
    }
  }

  const provider = detection?.provider || readiness?.source?.provider || null;
  const google = provider?.key === "google";
  const migrationActive = job && ["queued", "running"].includes(job.status);
  const progress = useMemo(() => {
    if (!job?.folders_total) return 0;
    return Math.min(100, Math.round((job.folders_done / job.folders_total) * 100));
  }, [job]);

  return (
    <main className="min-h-screen bg-[#f7f8fa] text-slate-900">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 sm:px-6">
          <Link href="/webmail" className="grid h-10 w-10 place-items-center rounded-full text-slate-600 hover:bg-slate-100" aria-label="Back to iMail"><ArrowLeft size={19} /></Link>
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-950 text-xs font-black text-amber-300">iM</span>
          <div className="min-w-0"><p className="truncate text-sm font-black">Import & migrate mail</p><p className="truncate text-[11px] font-medium text-slate-500">Gmail, Microsoft and secure IMAP → Ithute business mail</p></div>
          <Link href="/webmail/external" className="ml-auto hidden items-center gap-2 rounded-full border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-600 hover:bg-slate-50 sm:inline-flex"><ExternalLink size={15} /> External mailbox</Link>
        </div>
      </header>

      <div className="mx-auto grid max-w-6xl gap-5 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:py-8">
        <div className="space-y-5">
          <section className="overflow-hidden rounded-[26px] border border-slate-200 bg-white shadow-[0_18px_55px_rgba(15,23,42,.06)]">
            <div className="border-b border-slate-100 bg-[linear-gradient(135deg,#ffffff,#f5f9f7)] p-5 sm:p-7">
              <div className="flex items-start gap-4">
                <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-emerald-950 text-amber-300 shadow-sm"><CloudDownload size={23} /></span>
                <div><p className="text-xs font-black uppercase tracking-[.14em] text-emerald-800">Smart connected accounts</p><h1 className="mt-1 text-2xl font-black tracking-tight sm:text-3xl">Bring your old mail into your business inbox</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">iMail detects the provider, connects securely, preserves folders and copies the messages into the Ithute mailbox you are currently signed in to.</p></div>
              </div>
            </div>

            <div className="p-5 sm:p-7">
              {readiness?.source ? (
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50/70 p-4">
                  <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-white text-sm font-black text-emerald-900 shadow-sm">{providerTone(readiness.source.provider?.key)}</span><div className="min-w-0 flex-1"><p className="truncate text-sm font-black text-emerald-950">{readiness.source.address}</p><p className="truncate text-xs text-emerald-800">{readiness.source.provider?.name || "External mailbox"} • {readiness.source.imap_host}</p></div><CheckCircle2 className="text-emerald-700" size={20} /></div>
                  <div className="mt-3 flex flex-wrap gap-2"><Link href="/webmail/external" className="rounded-full border border-emerald-200 bg-white px-3 py-1.5 text-[11px] font-bold text-emerald-800 hover:bg-emerald-50">Open source mailbox</Link><button type="button" onClick={() => { setReadiness((current) => current ? { ...current, source: null, ready: false } : current); setDetection(null); setEmail(""); }} className="rounded-full px-3 py-1.5 text-[11px] font-bold text-slate-500 hover:bg-white">Connect a different account</button></div>
                </div>
              ) : (
                <form onSubmit={connectSource} className="space-y-4">
                  <div>
                    <label className="text-xs font-black text-slate-700">Email account to import</label>
                    <div className="mt-1.5 flex gap-2"><input type="email" required value={email} onChange={(event) => { setEmail(event.target.value); setDetection(null); }} onBlur={() => void detect()} placeholder="yourname@gmail.com" className="h-12 min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-4 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10" /><button type="button" onClick={() => void detect()} disabled={detecting || !email.includes("@")} className="inline-flex h-12 shrink-0 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3.5 text-xs font-black text-slate-600 hover:bg-slate-100 disabled:opacity-50">{detecting ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />} Detect</button></div>
                  </div>

                  {detection ? <div className={`rounded-2xl border p-4 ${detection.detected ? "border-blue-200 bg-blue-50/60" : "border-slate-200 bg-slate-50"}`}><div className="flex items-start gap-3"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white text-sm font-black text-slate-700 shadow-sm">{providerTone(detection.provider.key)}</span><div className="min-w-0"><p className="text-sm font-black">{detection.provider.name}</p><p className="mt-1 text-xs leading-5 text-slate-600">{detection.provider.help_text}</p>{detection.detected ? <p className="mt-2 text-[10px] font-bold uppercase tracking-[.1em] text-blue-700">Detected from {detection.provider.detected_by === "mx_records" ? "domain MX records" : "email provider"}</p> : null}</div></div></div> : null}

                  <label className="block"><span className="text-xs font-black text-slate-700">{google ? "Google App Password" : "Mailbox password / app password"}</span><input type="password" required value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1.5 h-12 w-full rounded-xl border border-slate-200 bg-white px-4 text-sm outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10" placeholder={google ? "16-character Google App Password" : "Password used by this mail account"} />{google ? <p className="mt-2 text-[11px] leading-5 text-slate-500">iMail automatically uses <strong>imap.gmail.com</strong> and <strong>smtp.gmail.com</strong>. For Google accounts protected by modern sign-in, use an App Password; your normal Google password is not stored as a remembered account credential.</p> : null}</label>

                  <button disabled={connecting} className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-sm font-black text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-60">{connecting ? <Loader2 size={18} className="animate-spin" /> : <Server size={18} />} Detect, verify and connect</button>
                </form>
              )}
            </div>
          </section>

          <section className="rounded-[26px] border border-slate-200 bg-white p-5 shadow-[0_18px_55px_rgba(15,23,42,.05)] sm:p-7">
            <div className="flex items-center gap-3"><span className="grid h-11 w-11 place-items-center rounded-2xl bg-slate-100 text-slate-700"><Inbox size={21} /></span><div><h2 className="text-lg font-black">Destination business mailbox</h2><p className="text-xs text-slate-500">For security, the destination comes only from your hosted iMail session.</p></div></div>
            {loadingReadiness ? <div className="mt-5 flex items-center gap-2 text-sm text-slate-500"><Loader2 size={17} className="animate-spin" /> Checking signed-in mailbox…</div> : readiness?.destination?.active ? <div className="mt-5 flex items-center gap-3 rounded-2xl border border-slate-200 bg-[#fafafa] p-4"><span className="grid h-10 w-10 place-items-center rounded-full bg-emerald-100 text-xs font-black text-emerald-900">IT</span><div className="min-w-0 flex-1"><p className="truncate text-sm font-black">{readiness.destination.address}</p><p className="text-xs text-slate-500">Active Ithute-hosted business mailbox</p></div><ShieldCheck size={20} className="text-emerald-700" /></div> : <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4"><div className="flex items-start gap-3"><TriangleAlert size={19} className="mt-0.5 shrink-0 text-amber-700" /><div><p className="text-sm font-black text-amber-950">Sign in to the destination mailbox</p><p className="mt-1 text-xs leading-5 text-amber-800">Open iMail, sign in to the business address that should receive the imported messages, then return here. Your connected source session will remain separate.</p><Link href="/webmail" className="mt-3 inline-flex items-center gap-2 rounded-full bg-amber-950 px-3.5 py-2 text-xs font-black text-white">Open business iMail <ArrowRight size={14} /></Link></div></div></div>}
          </section>

          <section className="rounded-[26px] border border-slate-200 bg-white p-5 shadow-[0_18px_55px_rgba(15,23,42,.05)] sm:p-7">
            <div className="flex items-center justify-between gap-3"><div><h2 className="text-lg font-black">Migration</h2><p className="mt-1 text-xs text-slate-500">Copies the source mailbox. It never deletes messages from Gmail or the old provider.</p></div><button type="button" onClick={() => void Promise.all([loadReadiness(), loadHistory()])} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100" title="Refresh status"><RefreshCw size={16} /></button></div>

            {job ? <div className={`mt-5 rounded-2xl border p-4 ${job.status === "failed" ? "border-red-200 bg-red-50" : job.status === "completed" ? "border-emerald-200 bg-emerald-50/60" : "border-blue-200 bg-blue-50/60"}`}><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-white shadow-sm">{job.status === "completed" ? <CheckCircle2 size={20} className="text-emerald-700" /> : job.status === "failed" ? <TriangleAlert size={20} className="text-red-600" /> : <Loader2 size={20} className="animate-spin text-blue-600" />}</span><div className="min-w-0 flex-1"><p className="text-sm font-black capitalize">{job.status === "queued" ? "Migration queued" : job.status === "running" ? "Copying mailbox" : `Migration ${job.status}`}</p><p className="truncate text-xs text-slate-600">{job.source_username} → {job.destination}</p></div><span className="text-xs font-black text-slate-500">{progress}%</span></div><div className="mt-4 h-2 overflow-hidden rounded-full bg-white"><div className="h-full rounded-full bg-blue-600 transition-all" style={{ width: `${job.status === "completed" ? 100 : progress}%` }} /></div><div className="mt-4 grid grid-cols-3 gap-2 text-center"><div className="rounded-xl bg-white p-2.5"><p className="text-base font-black">{job.messages_copied.toLocaleString()}</p><p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Messages</p></div><div className="rounded-xl bg-white p-2.5"><p className="text-base font-black">{job.folders_done}/{job.folders_total || "–"}</p><p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Folders</p></div><div className="rounded-xl bg-white p-2.5"><p className="text-base font-black">{prettyBytes(job.bytes_copied)}</p><p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Copied</p></div></div>{job.error ? <p className="mt-3 text-xs font-semibold text-red-700">{job.error}</p> : null}</div> : null}

            {!migrationActive ? <button type="button" disabled={!readiness?.ready || starting} onClick={() => void startMigration()} className="mt-5 inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-emerald-800 px-4 text-sm font-black text-white transition hover:bg-emerald-900 disabled:cursor-not-allowed disabled:bg-slate-300">{starting ? <Loader2 size={18} className="animate-spin" /> : <CloudDownload size={18} />} {job?.status === "completed" ? "Run again to catch newer mail" : "Start mailbox migration"}</button> : null}

            {readiness?.issues?.length ? <div className="mt-4 space-y-1">{readiness.issues.map((issue) => <p key={issue} className="flex items-start gap-2 text-xs text-slate-500"><span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" /> {issue}</p>)}</div> : null}
          </section>

          {history.length ? <section className="rounded-[26px] border border-slate-200 bg-white p-5 sm:p-7"><h2 className="text-lg font-black">Migration history</h2><div className="mt-4 divide-y divide-slate-100">{history.slice(0, 8).map((item) => <button type="button" key={item.id} onClick={() => setJob(item)} className="flex w-full items-center gap-3 py-3 text-left"><span className={`h-2.5 w-2.5 shrink-0 rounded-full ${item.status === "completed" ? "bg-emerald-500" : item.status === "failed" ? "bg-red-500" : "bg-blue-500"}`} /><div className="min-w-0 flex-1"><p className="truncate text-sm font-bold">{item.source_username}</p><p className="text-[11px] text-slate-500">{item.messages_copied.toLocaleString()} copied • {prettyBytes(item.bytes_copied)}</p></div><span className="text-[10px] font-black uppercase tracking-wide text-slate-400">{item.status}</span></button>)}</div></section> : null}
        </div>

        <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          {notice ? <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-semibold leading-6 text-emerald-900">{notice}</div> : null}
          {error ? <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm font-semibold leading-6 text-red-800">{error}</div> : null}

          <div className="rounded-[24px] border border-slate-200 bg-white p-5">
            <p className="text-xs font-black uppercase tracking-[.14em] text-slate-400">What iMail protects</p>
            <div className="mt-4 space-y-4">{[
              ["Source stays intact", "Migration copies mail; it does not remove messages from Gmail or the old provider."],
              ["Safe to resume", "Already imported messages in each folder are detected and skipped on repeat runs."],
              ["Folders preserved", "Inbox and selectable source folders are recreated in the business mailbox."],
              ["Destination locked", "Only the currently signed-in active Ithute mailbox can receive the migration."],
            ].map(([title, copy]) => <div key={title} className="flex gap-3"><CheckCircle2 size={17} className="mt-0.5 shrink-0 text-emerald-700" /><div><p className="text-xs font-black">{title}</p><p className="mt-1 text-[11px] leading-5 text-slate-500">{copy}</p></div></div>)}</div>
          </div>

          <div className="rounded-[24px] border border-blue-200 bg-blue-50/60 p-5">
            <div className="flex items-center gap-2 text-blue-900"><Mail size={17} /><p className="text-xs font-black uppercase tracking-[.12em]">Provider intelligence</p></div><p className="mt-3 text-xs leading-5 text-blue-900/80">Gmail and major providers are detected before connection. Google Workspace domains can also be recognized from their MX records, so users do not need to know IMAP or SMTP hostnames.</p>
          </div>
        </aside>
      </div>
    </main>
  );
}
