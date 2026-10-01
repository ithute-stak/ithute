"use client";

import Link from "next/link";
import { ArrowLeft, CheckCircle2, CloudDownload, Loader2, Mail, RefreshCw, ShieldCheck, TriangleAlert } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { API } from "../mail-types";

type Phase = "initial" | "delta" | "final";
type Provider = { key: string; name: string; imap_host?: string; help_text?: string; detected_by?: string };
type Detection = { address: string; detected: boolean; provider: Provider };
type Readiness = {
  ready: boolean;
  issues: string[];
  source: null | { address: string; provider: Provider; imap_host: string };
  destination: null | { address: string; active: boolean; mailbox_id?: string | null };
  behavior: {
    copies_mail: boolean;
    deletes_source: boolean;
    preserves_folders: boolean;
    preserves_message_dates?: boolean;
    safe_to_resume: boolean;
    deduplicates_repeat_syncs?: boolean;
    contacts_and_calendars_included?: boolean;
  };
  cutover?: { initial_done: boolean; final_clean: boolean; steps: Phase[] };
};
type MigrationJob = {
  id: string;
  destination: string;
  source_provider: string;
  source_username: string;
  status: "queued" | "running" | "completed" | "partial" | "failed" | string;
  raw_status?: string;
  phase?: Phase;
  folders_total: number;
  folders_done: number;
  messages_copied: number;
  bytes_copied: number;
  error?: string | null;
  source_is_preserved?: boolean;
  safe_to_repeat?: boolean;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
};
type MigrationStep = {
  phase: Phase;
  title: string;
  copy: string;
  enabled: boolean;
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
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1; }
  return `${size >= 10 || index === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[index]}`;
}

function phaseName(phase?: Phase) {
  if (phase === "delta") return "New-mail sync";
  if (phase === "final") return "Final cutover sync";
  return "Initial historical copy";
}

export default function MailMigrationPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [detection, setDetection] = useState<Detection | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [history, setHistory] = useState<MigrationJob[]>([]);
  const [job, setJob] = useState<MigrationJob | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [starting, setStarting] = useState<Phase | null>(null);
  const [resuming, setResuming] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try {
      const [readyResponse, jobsResponse] = await Promise.all([external("/migration/readiness"), external("/migration/jobs")]);
      if (!readyResponse.ok) throw new Error("Unable to check migration readiness");
      const ready = (await readyResponse.json()) as Readiness;
      setReadiness(ready);
      if (ready.source?.address) setEmail(ready.source.address);
      if (jobsResponse.ok) {
        const data = await jobsResponse.json();
        const items = (data.items || []) as MigrationJob[];
        setHistory(items);
        const active = items.find((item) => ["queued", "running"].includes(item.status));
        if (active) setJob(active);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load migration centre");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const response = await external(`/migration/jobs/${job.id}`);
        if (!response.ok) return;
        const latest = (await response.json()) as MigrationJob;
        setJob(latest);
        setHistory((current) => [latest, ...current.filter((item) => item.id !== latest.id)].slice(0, 20));
        if (!["queued", "running"].includes(latest.status)) {
          if (latest.status === "completed") setNotice(`${phaseName(latest.phase)} completed cleanly. ${latest.messages_copied.toLocaleString()} new messages copied.`);
          else if (latest.status === "partial") setError(latest.error || "Some source messages could not be copied. Resume this sync before cutover.");
          else setError(latest.error || "Migration stopped. Correct the source connection and resume safely.");
          void load();
        }
      } catch { /* polling failures do not cancel the server-side migration */ }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [job, load]);

  async function detect(address = email.trim().toLowerCase()) {
    if (!address.includes("@")) return;
    setDetecting(true); setError("");
    try {
      const response = await external(`/provider-detect?address=${encodeURIComponent(address)}`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Unable to detect mail provider");
      setDetection(data as Detection);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to detect mail provider"); }
    finally { setDetecting(false); }
  }

  async function connectSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const address = email.trim().toLowerCase();
    if (!address) return;
    setConnecting(true); setError(""); setNotice("");
    try {
      if (!detection || detection.address !== address) await detect(address);
      const response = await external("/session", { method: "POST", body: JSON.stringify({ address, username: address, password, display_name: "" }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Unable to connect source mailbox");
      setPassword("");
      setNotice("Source mailbox connected securely. Ithute only copies mail; it never deletes the source mailbox.");
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to connect source mailbox"); }
    finally { setConnecting(false); }
  }

  async function runPhase(phase: Phase) {
    if (!readiness?.ready || !readiness.destination?.address) return;
    setStarting(phase); setError(""); setNotice("");
    try {
      const response = await external("/migration/start", { method: "POST", body: JSON.stringify({ destination_address: readiness.destination.address, phase }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Unable to start migration sync");
      setJob(data.job as MigrationJob);
      setNotice(data.already_running ? "A mailbox sync is already running." : `${phaseName(phase)} queued. You may leave this page while the server copies mail.`);
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to start migration sync"); }
    finally { setStarting(null); }
  }

  async function resumeJob(row: MigrationJob) {
    setResuming(true); setError(""); setNotice("");
    try {
      const response = await external(`/migration/jobs/${row.id}/resume`, { method: "POST" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Unable to resume migration");
      setJob(data.job as MigrationJob);
      setNotice("Migration resumed safely. Already copied mail will be skipped.");
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to resume migration"); }
    finally { setResuming(false); }
  }

  const active = !!job && ["queued", "running"].includes(job.status);
  const progress = useMemo(() => !job?.folders_total ? 0 : Math.min(100, Math.round((job.folders_done / job.folders_total) * 100)), [job]);
  const initialDone = Boolean(readiness?.cutover?.initial_done) || history.some((item) => item.phase === "initial" && ["completed", "partial"].includes(item.status));
  const finalClean = Boolean(readiness?.cutover?.final_clean) || history.some((item) => item.phase === "final" && item.status === "completed");
  const retry = history.find((item) => ["failed", "partial"].includes(item.status));
  const migrationSteps: MigrationStep[] = [
    { phase: "initial", title: "Initial historical copy", copy: "Copy all existing mail now while the old provider remains live.", enabled: !initialDone },
    { phase: "delta", title: "Sync new arrivals", copy: "Run again before DNS cutover. Already copied messages are skipped automatically.", enabled: initialDone && !finalClean },
    { phase: "final", title: "Final sync & verify", copy: "After MX points to Ithute, copy the last messages that reached the old provider. A clean final run completes the cutover.", enabled: initialDone && !finalClean },
  ];

  return (
    <main className="min-h-screen bg-[#f6f8f7] text-slate-900">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 sm:px-6">
          <Link href="/webmail" className="grid h-10 w-10 place-items-center rounded-full text-slate-600 hover:bg-slate-100" aria-label="Back to iMail"><ArrowLeft size={19}/></Link>
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#123a38] text-xs font-black text-[#d8c56a]">iM</span>
          <div><p className="text-sm font-black">Move email to Ithute</p><p className="text-[11px] text-slate-500">Copy first. Switch later. Keep every message during cutover.</p></div>
          <Link href="/webmail/accounts" className="ml-auto rounded-full border border-slate-200 px-3 py-2 text-xs font-bold text-slate-600">Mail accounts</Link>
        </div>
      </header>

      <div className="mx-auto max-w-6xl space-y-5 px-4 py-6 sm:px-6 lg:py-8">
        <section className="overflow-hidden rounded-[28px] border border-[#dfe7e3] bg-white shadow-[0_18px_55px_rgba(15,23,42,.06)]">
          <div className="bg-[linear-gradient(135deg,#123a38,#174b45)] p-6 text-white sm:p-8">
            <div className="flex items-start gap-4"><span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-white/10 text-[#f1de8b]"><CloudDownload size={23}/></span><div><p className="text-[10px] font-black uppercase tracking-[.14em] text-[#f1de8b]">Zero-loss mailbox cutover</p><h1 className="mt-1 text-3xl font-black tracking-tight">Bring the old mailbox with you.</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-white/75">Ithute copies messages, attachments, folders, standard flags and original message dates. Repeated syncs skip mail already copied, so the old provider can stay live until DNS/MX cutover is complete.</p></div></div>
          </div>

          <div className="grid gap-5 p-5 sm:p-7 lg:grid-cols-[1fr_360px]">
            <div className="space-y-5">
              {error ? <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm font-semibold text-rose-800"><div className="flex gap-2"><TriangleAlert size={18} className="mt-0.5 shrink-0"/><span>{error}</span></div>{retry && readiness?.source ? <button disabled={resuming || active} onClick={() => void resumeJob(retry)} className="mt-3 rounded-xl bg-rose-800 px-4 py-2 text-xs font-black text-white disabled:opacity-50">{resuming ? "Resuming…" : `Resume ${phaseName(retry.phase)}`}</button> : null}</div> : null}
              {notice ? <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-semibold text-emerald-900">{notice}</div> : null}

              {loading ? <div className="flex items-center gap-2 py-8 text-sm text-slate-500"><Loader2 size={17} className="animate-spin"/>Checking mailbox migration readiness…</div> : readiness?.source ? (
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50/60 p-4"><div className="flex items-center gap-3"><CheckCircle2 size={20} className="text-emerald-700"/><div><p className="font-black text-emerald-950">Source connected: {readiness.source.address}</p><p className="text-xs text-emerald-800">{readiness.source.provider?.name || "External IMAP"} · {readiness.source.imap_host}</p></div></div></div>
              ) : (
                <form onSubmit={connectSource} className="rounded-2xl border border-slate-200 p-5">
                  <h2 className="font-black">1. Connect the old mailbox</h2><p className="mt-1 text-xs leading-5 text-slate-500">Use the mailbox password or provider app password. Google and Microsoft accounts may require an app password or provider-authorized credential.</p>
                  <label className="mt-4 block text-xs font-black text-slate-700">Old email address</label>
                  <div className="mt-1.5 flex gap-2"><input required type="email" value={email} onChange={(event)=>{setEmail(event.target.value);setDetection(null);}} onBlur={()=>void detect()} placeholder="name@oldprovider.com" className="h-12 min-w-0 flex-1 rounded-xl border border-slate-200 px-4 text-sm outline-none focus:border-emerald-700"/><button type="button" disabled={detecting || !email.includes("@")} onClick={()=>void detect()} className="rounded-xl border border-slate-200 px-4 text-xs font-black disabled:opacity-50">{detecting ? <Loader2 size={15} className="animate-spin"/> : "Detect"}</button></div>
                  {detection ? <p className="mt-2 text-xs text-slate-600">Detected: <b>{detection.provider.name}</b>{detection.provider.help_text ? ` — ${detection.provider.help_text}` : ""}</p> : null}
                  <label className="mt-4 block text-xs font-black text-slate-700">Mailbox / app password</label><input required type="password" value={password} onChange={(event)=>setPassword(event.target.value)} className="mt-1.5 h-12 w-full rounded-xl border border-slate-200 px-4 text-sm outline-none focus:border-emerald-700"/>
                  <button disabled={connecting} className="mt-4 inline-flex h-11 items-center gap-2 rounded-xl bg-[#123a38] px-5 text-xs font-black text-white disabled:opacity-50">{connecting ? <Loader2 size={15} className="animate-spin"/> : <Mail size={15}/>}Connect source mailbox</button>
                </form>
              )}

              {readiness?.source && readiness.destination ? <div className="space-y-3"><h2 className="text-lg font-black">Migration & cutover</h2>{migrationSteps.map((step, index) => <article key={step.phase} className="rounded-2xl border border-slate-200 bg-white p-4"><div className="flex items-start gap-3"><span className={`grid h-9 w-9 shrink-0 place-items-center rounded-full text-sm font-black ${(step.phase === "initial" && initialDone) || (step.phase === "final" && finalClean) ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-700"}`}>{(step.phase === "initial" && initialDone) || (step.phase === "final" && finalClean) ? <CheckCircle2 size={17}/> : index + 1}</span><div className="flex-1"><p className="font-black">{step.title}</p><p className="mt-1 text-xs leading-5 text-slate-500">{step.copy}</p><button disabled={!step.enabled || active || starting !== null} onClick={()=>void runPhase(step.phase)} className="mt-3 inline-flex h-10 items-center gap-2 rounded-xl bg-[#123a38] px-4 text-xs font-black text-white disabled:cursor-not-allowed disabled:opacity-35">{starting === step.phase ? <Loader2 size={14} className="animate-spin"/> : <RefreshCw size={14}/>}Run {step.phase === "initial" ? "initial copy" : step.phase === "delta" ? "new-mail sync" : "final sync"}</button></div></div></article>)}</div> : null}

              {job ? <section className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="flex items-center justify-between gap-4"><div><p className="text-xs font-black uppercase tracking-[.1em] text-slate-500">Current / latest run</p><h3 className="mt-1 font-black">{phaseName(job.phase)} · {job.status}</h3></div>{active ? <Loader2 className="animate-spin text-emerald-700" size={20}/> : job.status === "completed" ? <CheckCircle2 className="text-emerald-700" size={20}/> : null}</div><div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-200"><div className="h-full bg-emerald-700 transition-all" style={{width:`${progress}%`}}/></div><div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs"><div className="rounded-xl bg-white p-3"><b className="block text-base">{job.folders_done}/{job.folders_total || "—"}</b>folders</div><div className="rounded-xl bg-white p-3"><b className="block text-base">{job.messages_copied.toLocaleString()}</b>new messages</div><div className="rounded-xl bg-white p-3"><b className="block text-base">{prettyBytes(job.bytes_copied)}</b>copied</div></div></section> : null}
            </div>

            <aside className="space-y-4">
              <div className="rounded-2xl border border-[#d8c56a]/50 bg-[#fffdf1] p-5"><ShieldCheck size={20} className="text-[#796b22]"/><h2 className="mt-3 font-black">No-loss rules</h2><ul className="mt-3 space-y-2 text-xs leading-5 text-slate-600"><li>• Ithute never deletes mail from the old provider.</li><li>• Re-running a sync deduplicates messages already copied.</li><li>• Attachments and raw message headers move with each email.</li><li>• Folder structure, standard flags and original message dates are retained.</li><li>• Destination quota and server free-space checks prevent unsafe partial writes.</li><li>• Source IMAP must use validated TLS and a public Internet host.</li></ul></div>
              <div className="rounded-2xl border border-slate-200 bg-white p-5"><p className="text-[10px] font-black uppercase tracking-[.12em] text-slate-500">Cutover rule</p><h3 className="mt-2 font-black">Do not cancel the old hosting immediately.</h3><p className="mt-2 text-xs leading-5 text-slate-600">Keep the old mailbox active through DNS propagation. Run the initial copy, then a delta sync, point MX to Ithute, and run the final sync. Cancel the old provider only after the final sync is clean and new mail is arriving at Ithute.</p></div>
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-xs leading-5 text-amber-900"><b>Mail migration scope:</b> IMAP moves email messages and mail folders. Contacts and calendars are separate data and are not claimed as part of this mailbox migration.</div>
            </aside>
          </div>
        </section>

        {history.length ? <section className="rounded-[24px] border border-slate-200 bg-white p-5"><h2 className="font-black">Migration history</h2><div className="mt-3 divide-y divide-slate-100">{history.slice(0,10).map((row)=><div key={row.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-3 text-xs"><b className="min-w-40">{phaseName(row.phase)}</b><span className={row.status === "completed" ? "font-bold text-emerald-700" : row.status === "partial" || row.status === "failed" ? "font-bold text-rose-700" : "font-bold text-slate-600"}>{row.status}</span><span>{row.messages_copied.toLocaleString()} new messages</span><span>{prettyBytes(row.bytes_copied)}</span></div>)}</div></section> : null}
      </div>
    </main>
  );
}
