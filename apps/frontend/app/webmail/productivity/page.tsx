"use client";

import Link from "next/link";
import { ArrowLeft, CalendarClock, CheckCircle2, Clock3, Filter, Loader2, Play, Plus, RefreshCw, Send, Trash2, TriangleAlert } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { API, splitAddresses } from "../mail-types";

type Account = { id: string; address: string; display_name: string; provider: string; status: string };
type Rule = { id: string; name: string; enabled: boolean; connected_account_id?: string | null; conditions: Record<string, unknown>; actions: Array<Record<string, unknown>>; run_count: number; last_run_at?: string | null; last_error?: string | null };
type Scheduled = { id: string; connected_account_id?: string | null; source_key: string; to: string[]; subject: string; scheduled_at: string; status: string; error?: string | null; sent_at?: string | null };

async function api(path: string, init?: RequestInit) {
  return fetch(`${API}/webmail${path}`, { credentials: "include", ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
}

function when(value?: string | null) {
  if (!value) return "Never";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function MailProductivityPage() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [scheduled, setScheduled] = useState<Scheduled[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [ruleName, setRuleName] = useState("");
  const [ruleSource, setRuleSource] = useState("");
  const [conditionType, setConditionType] = useState("from_contains");
  const [conditionValue, setConditionValue] = useState("");
  const [actionType, setActionType] = useState("move_to");
  const [actionValue, setActionValue] = useState("Archive");
  const [sendFrom, setSendFrom] = useState("");
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sendAt, setSendAt] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [ruleResponse, scheduledResponse, accountsResponse] = await Promise.all([api("/rules"), api("/scheduled"), api("/connected-accounts")]);
      if ([ruleResponse.status, scheduledResponse.status, accountsResponse.status].includes(401)) { window.location.assign("/webmail"); return; }
      if (!ruleResponse.ok || !scheduledResponse.ok || !accountsResponse.ok) throw new Error("Unable to load Webmail productivity settings");
      setRules((await ruleResponse.json()).items || []);
      setScheduled((await scheduledResponse.json()).items || []);
      setAccounts((await accountsResponse.json()).items || []);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to load productivity tools"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  async function createRule(event: FormEvent) {
    event.preventDefault(); setBusy("rule"); setError(""); setNotice("");
    try {
      const conditions: Record<string, unknown> = {};
      if (conditionType === "has_attachment" || conditionType === "unread") conditions[conditionType] = true;
      else conditions[conditionType] = conditionValue.trim();
      const action: Record<string, unknown> = { type: actionType };
      if (actionType === "move_to") action.folder = actionValue.trim();
      const response = await api("/rules", { method: "POST", body: JSON.stringify({ name: ruleName.trim(), connected_account_id: ruleSource || null, conditions, actions: [action] }) });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Unable to create rule");
      setRuleName(""); setConditionValue(""); setNotice("Rule created. It is scoped to this mailbox only."); await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to create rule"); }
    finally { setBusy(""); }
  }

  async function removeRule(id: string) {
    setBusy(`delete:${id}`);
    try { const response = await api(`/rules/${id}`, { method: "DELETE" }); if (!response.ok) throw new Error("Unable to delete rule"); await refresh(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to delete rule"); }
    finally { setBusy(""); }
  }

  async function runRules() {
    setBusy("run"); setError("");
    try { const response = await api("/rules/run", { method: "POST", body: "{}" }); const payload = await response.json().catch(() => ({})); if (!response.ok) throw new Error(payload.detail || "Unable to run rules"); setNotice(`Rules checked ${payload.messages_checked || 0} messages and applied ${payload.actions_applied || 0} actions.`); await refresh(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to run rules"); }
    finally { setBusy(""); }
  }

  async function schedule(event: FormEvent) {
    event.preventDefault(); setBusy("schedule"); setError(""); setNotice("");
    try {
      const date = new Date(sendAt);
      if (Number.isNaN(date.getTime())) throw new Error("Choose a valid future date and time");
      const response = await api("/scheduled", { method: "POST", body: JSON.stringify({ connected_account_id: sendFrom || null, to: splitAddresses(to), cc: [], bcc: [], subject, body_text: body, body_html: "", attachments: [], scheduled_at: date.toISOString() }) });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Unable to schedule message");
      setTo(""); setSubject(""); setBody(""); setSendAt(""); setNotice("Message scheduled. You can cancel it before delivery."); await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to schedule message"); }
    finally { setBusy(""); }
  }

  async function cancelScheduled(id: string) {
    setBusy(`cancel:${id}`);
    try { const response = await api(`/scheduled/${id}/cancel`, { method: "POST", body: "{}" }); const payload = await response.json().catch(() => ({})); if (!response.ok) throw new Error(payload.detail || "Unable to cancel scheduled mail"); setNotice("Scheduled message cancelled."); await refresh(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to cancel scheduled mail"); }
    finally { setBusy(""); }
  }

  return <main className="min-h-screen bg-[#f6f8fc] text-[#202124] dark:bg-[#0f1418] dark:text-slate-100">
    <header className="sticky top-0 z-20 flex min-h-16 items-center justify-between gap-3 border-b border-[#e2e6ea] bg-white/95 px-4 backdrop-blur dark:border-white/10 dark:bg-[#111820]/95 sm:px-6">
      <div className="flex min-w-0 items-center gap-3"><Link href="/webmail" className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10"><ArrowLeft size={18}/></Link><span className="grid h-9 w-9 place-items-center rounded-xl bg-[#0c6f55] text-xs font-black text-white">iM</span><div className="min-w-0"><h1 className="truncate text-base font-black">Rules & scheduled mail</h1><p className="truncate text-xs text-slate-500">Automate your inbox and send at the right time</p></div></div>
      <button onClick={() => void refresh()} className="grid h-9 w-9 place-items-center rounded-full text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10"><RefreshCw size={16}/></button>
    </header>
    <div className="mx-auto max-w-7xl space-y-5 px-4 py-5 sm:px-6">
      {error ? <div className="flex gap-2 rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200"><TriangleAlert size={17}/>{error}</div> : null}
      {notice ? <div className="flex gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-200"><CheckCircle2 size={17}/>{notice}</div> : null}
      {loading ? <div className="grid min-h-48 place-items-center"><Loader2 className="animate-spin text-[#0b57d0]" size={28}/></div> : <div className="grid gap-5 xl:grid-cols-2">
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-[#141b20] sm:p-6">
          <div className="mb-5 flex items-start justify-between gap-3"><div><h2 className="text-lg font-black">Inbox rules</h2><p className="mt-1 text-sm text-slate-500">Rules belong only to this signed-in business mailbox.</p></div><Filter className="text-[#0b57d0]" size={22}/></div>
          <form onSubmit={createRule} className="grid gap-3 rounded-2xl bg-slate-50 p-4 dark:bg-white/[.035]">
            <input required minLength={2} value={ruleName} onChange={e=>setRuleName(e.target.value)} placeholder="Rule name" className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-blue-400 dark:border-white/10 dark:bg-white/5"/>
            <select value={ruleSource} onChange={e=>setRuleSource(e.target.value)} className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm dark:border-white/10 dark:bg-[#172027]"><option value="">Hosted iMail inbox</option>{accounts.map(a=><option key={a.id} value={a.id}>{a.address}</option>)}</select>
            <div className="grid gap-2 sm:grid-cols-2"><select value={conditionType} onChange={e=>setConditionType(e.target.value)} className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm dark:border-white/10 dark:bg-[#172027]"><option value="from_contains">Sender contains</option><option value="to_contains">Recipient contains</option><option value="subject_contains">Subject contains</option><option value="has_attachment">Has attachment</option><option value="unread">Is unread</option></select>{!['has_attachment','unread'].includes(conditionType)?<input required value={conditionValue} onChange={e=>setConditionValue(e.target.value)} placeholder="Match value" className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm dark:border-white/10 dark:bg-white/5"/>:<div className="grid h-10 place-items-center rounded-xl border border-slate-200 bg-white text-xs text-slate-500 dark:border-white/10 dark:bg-white/5">Condition is enabled</div>}</div>
            <div className="grid gap-2 sm:grid-cols-2"><select value={actionType} onChange={e=>setActionType(e.target.value)} className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm dark:border-white/10 dark:bg-[#172027]"><option value="move_to">Move to folder</option><option value="mark_read">Mark read</option><option value="mark_unread">Mark unread</option><option value="star">Star</option><option value="unstar">Remove star</option></select>{actionType==='move_to'?<input required value={actionValue} onChange={e=>setActionValue(e.target.value)} placeholder="Folder" className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm dark:border-white/10 dark:bg-white/5"/>:<div/>}</div>
            <button disabled={busy==='rule'} className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-[#0b57d0] px-4 text-sm font-bold text-white disabled:opacity-50">{busy==='rule'?<Loader2 size={15} className="animate-spin"/>:<Plus size={15}/>} Add rule</button>
          </form>
          <div className="mt-4 space-y-2">{rules.map(rule=><div key={rule.id} className="flex items-center gap-3 rounded-2xl border border-slate-200 p-3 dark:border-white/10"><span className={`h-2.5 w-2.5 rounded-full ${rule.enabled?'bg-emerald-500':'bg-slate-300'}`}/><div className="min-w-0 flex-1"><p className="truncate text-sm font-bold">{rule.name}</p><p className="truncate text-[11px] text-slate-500">Ran {rule.run_count} times · last {when(rule.last_run_at)}</p>{rule.last_error?<p className="truncate text-[11px] text-amber-600">{rule.last_error}</p>:null}</div><button onClick={()=>void removeRule(rule.id)} className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10"><Trash2 size={15}/></button></div>)}{!rules.length?<p className="rounded-2xl border border-dashed border-slate-200 p-5 text-center text-sm text-slate-500 dark:border-white/10">No rules yet.</p>:null}</div>
          <button onClick={()=>void runRules()} disabled={busy==='run'} className="mt-4 inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-4 text-sm font-bold hover:bg-slate-50 disabled:opacity-50 dark:border-white/10 dark:hover:bg-white/5">{busy==='run'?<Loader2 size={15} className="animate-spin"/>:<Play size={15}/>} Run rules now</button>
        </section>

        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-[#141b20] sm:p-6">
          <div className="mb-5 flex items-start justify-between gap-3"><div><h2 className="text-lg font-black">Schedule a message</h2><p className="mt-1 text-sm text-slate-500">Works with hosted iMail and persistent connected accounts.</p></div><CalendarClock className="text-[#0b57d0]" size={22}/></div>
          <form onSubmit={schedule} className="grid gap-3 rounded-2xl bg-slate-50 p-4 dark:bg-white/[.035]">
            <select value={sendFrom} onChange={e=>setSendFrom(e.target.value)} className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm dark:border-white/10 dark:bg-[#172027]"><option value="">Send from hosted iMail</option>{accounts.filter(a=>a.status==='active').map(a=><option key={a.id} value={a.id}>Send from {a.address}</option>)}</select>
            <input required value={to} onChange={e=>setTo(e.target.value)} placeholder="To — comma-separated recipients" className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm dark:border-white/10 dark:bg-white/5"/>
            <input value={subject} onChange={e=>setSubject(e.target.value)} placeholder="Subject" className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm dark:border-white/10 dark:bg-white/5"/>
            <textarea value={body} onChange={e=>setBody(e.target.value)} placeholder="Message" rows={6} className="resize-y rounded-xl border border-slate-200 bg-white p-3 text-sm outline-none focus:border-blue-400 dark:border-white/10 dark:bg-white/5"/>
            <label className="text-xs font-bold text-slate-600 dark:text-slate-300">Send date and time<input required type="datetime-local" value={sendAt} onChange={e=>setSendAt(e.target.value)} className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-normal dark:border-white/10 dark:bg-[#172027]"/></label>
            <button disabled={busy==='schedule'} className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-[#0b57d0] px-4 text-sm font-bold text-white disabled:opacity-50">{busy==='schedule'?<Loader2 size={15} className="animate-spin"/>:<Send size={15}/>} Schedule send</button>
          </form>
          <div className="mt-4 space-y-2">{scheduled.map(item=><div key={item.id} className="flex items-center gap-3 rounded-2xl border border-slate-200 p-3 dark:border-white/10"><Clock3 size={17} className={item.status==='failed'?'text-red-500':item.status==='sent'?'text-emerald-500':'text-blue-500'}/><div className="min-w-0 flex-1"><p className="truncate text-sm font-bold">{item.subject || '(no subject)'}</p><p className="truncate text-[11px] text-slate-500">{item.to.join(', ')} · {item.status} · {when(item.scheduled_at)}</p>{item.error?<p className="truncate text-[11px] text-red-600">{item.error}</p>:null}</div>{['queued','failed'].includes(item.status)?<button onClick={()=>void cancelScheduled(item.id)} disabled={busy===`cancel:${item.id}`} className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-[11px] font-bold hover:bg-red-50 hover:text-red-600 dark:border-white/10 dark:hover:bg-red-500/10">Cancel</button>:null}</div>)}{!scheduled.length?<p className="rounded-2xl border border-dashed border-slate-200 p-5 text-center text-sm text-slate-500 dark:border-white/10">No scheduled messages.</p>:null}</div>
        </section>
      </div>}
    </div>
  </main>;
}
