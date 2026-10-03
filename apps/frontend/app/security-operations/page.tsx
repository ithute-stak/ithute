"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Fingerprint,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Siren,
} from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { apiJson, apiMutation } from "@/lib/platform-api";
import { useToast } from "@/components/toast-provider";

type Severity = "info" | "low" | "medium" | "high" | "critical";
type Summary = {
  posture: "healthy" | "attention" | "critical";
  window: string;
  events_total: number;
  severity: Record<Severity, number>;
  unresolved_actionable: number;
  audit_integrity: {
    healthy: boolean;
    checked_rows: number;
    signed_rows: number;
    invalid_signatures: number;
    broken_links: number;
    unsigned_after_chain: number;
    latest_signature?: string | null;
    detail: string;
  };
  generated_at: string;
};
type SecurityEvent = {
  id: string;
  product_id?: string | null;
  severity: Severity;
  event_type: string;
  actor_ref?: string | null;
  subject_ref?: string | null;
  source_ip?: string | null;
  details?: Record<string, unknown>;
  resolved_at?: string | null;
  created_at?: string | null;
};
type EventResponse = { items: SecurityEvent[] };

function badge(severity: string) {
  if (severity === "critical") return "border-rose-300 bg-rose-50 text-rose-800";
  if (severity === "high") return "border-orange-300 bg-orange-50 text-orange-800";
  if (severity === "medium" || severity === "attention") return "border-amber-300 bg-amber-50 text-amber-800";
  if (severity === "healthy" || severity === "low") return "border-emerald-300 bg-emerald-50 text-emerald-800";
  return "border-slate-200 bg-slate-50 text-slate-700";
}

function time(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function SecurityOperationsPage() {
  const toast = useToast();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [severity, setSeverity] = useState<Severity | "">("");
  const [unresolvedOnly, setUnresolvedOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState("");

  const load = useCallback(async (force = false) => {
    setLoading(true);
    try {
      const query = new URLSearchParams();
      query.set("limit", "250");
      if (severity) query.set("severity", severity);
      if (unresolvedOnly) query.set("unresolved_only", "true");
      const [nextSummary, eventResponse] = await Promise.all([
        apiJson<Summary>("/security/operations/summary", { ttlMs: 10_000, force }),
        apiJson<EventResponse>(`/security/operations/events?${query.toString()}`, { ttlMs: 10_000, force }),
      ]);
      setSummary(nextSummary);
      setEvents(eventResponse.items || []);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to load security operations", "Security Operations unavailable");
    } finally {
      setLoading(false);
    }
  }, [severity, toast, unresolvedOnly]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(true), 30_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const actionable = useMemo(
    () => events.filter((item) => !item.resolved_at && ["medium", "high", "critical"].includes(item.severity)),
    [events],
  );

  async function resolve(item: SecurityEvent) {
    setResolving(item.id);
    try {
      await apiMutation(
        `/security/operations/events/${item.id}/resolve`,
        { method: "POST" },
        ["/security/operations"],
      );
      toast.success("Security event marked resolved");
      await load(true);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to resolve event");
    } finally {
      setResolving("");
    }
  }

  return (
    <ControlShell title="Security operations" subtitle="Threat signals, incident posture and tamper-evident audit integrity">
      <div className="space-y-4 pb-16">
        <section className="overflow-hidden rounded-2xl border border-[#173c36]/10 bg-white shadow-sm">
          <div className="bg-[linear-gradient(120deg,#102f2d,#154b46)] p-5 text-white sm:p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <p className="flex items-center gap-2 text-[9px] font-black uppercase tracking-[.16em] text-[#d8c56a]"><Siren size={13}/>Security Operations Centre</p>
                <h1 className="mt-2 text-3xl font-black tracking-tight">Ithute SOC</h1>
                <p className="mt-2 max-w-3xl text-[11px] leading-5 text-[#c9dad4]">
                  Correlates product security events with privileged application actions and continuously verifies the signed audit chain.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link href="/system-owner/security" className="rounded-xl border border-white/20 bg-white/10 px-3 py-2 text-[10px] font-black text-white hover:bg-white/15">
                  <Fingerprint size={14} className="mr-1 inline"/>Identity security
                </Link>
                <button onClick={() => void load(true)} disabled={loading} className="rounded-xl bg-[#d8c56a] px-4 py-2 text-[10px] font-black text-[#123a38]">
                  <RefreshCw size={14} className={`mr-1 inline ${loading ? "animate-spin" : ""}`}/>Refresh
                </button>
              </div>
            </div>
          </div>
        </section>

        {summary ? (
          <>
            <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
              <article className="surface-card p-4">
                <p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Posture</p>
                <div className="mt-3 flex items-center justify-between gap-2">
                  <p className="text-xl font-black capitalize">{summary.posture}</p>
                  <span className={`rounded-full border px-2 py-1 text-[8px] font-black uppercase ${badge(summary.posture)}`}>{summary.posture}</span>
                </div>
              </article>
              {(["critical","high","medium","low"] as Severity[]).map((level) => (
                <article key={level} className="surface-card p-4">
                  <p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">{level}</p>
                  <p className="mt-3 text-3xl font-black">{summary.severity[level] || 0}</p>
                  <p className="mt-1 text-[9px] text-[var(--admin-muted)]">last {summary.window}</p>
                </article>
              ))}
              <article className="surface-card p-4">
                <p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Unresolved</p>
                <p className="mt-3 text-3xl font-black">{summary.unresolved_actionable}</p>
                <p className="mt-1 text-[9px] text-[var(--admin-muted)]">medium+ events</p>
              </article>
            </section>

            <section className={`rounded-2xl border p-4 ${summary.audit_integrity.healthy ? "border-emerald-200 bg-emerald-50/60" : "border-rose-300 bg-rose-50"}`}>
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex gap-3">
                  {summary.audit_integrity.healthy ? <ShieldCheck className="mt-0.5 text-emerald-700" size={20}/> : <ShieldAlert className="mt-0.5 text-rose-700" size={20}/>}
                  <div>
                    <p className="text-sm font-black">Audit integrity {summary.audit_integrity.healthy ? "verified" : "FAILED"}</p>
                    <p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">{summary.audit_integrity.detail}</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 text-[9px] sm:grid-cols-4">
                  <span className="rounded-lg bg-white/70 px-3 py-2"><b>{summary.audit_integrity.signed_rows}</b> signed</span>
                  <span className="rounded-lg bg-white/70 px-3 py-2"><b>{summary.audit_integrity.invalid_signatures}</b> invalid</span>
                  <span className="rounded-lg bg-white/70 px-3 py-2"><b>{summary.audit_integrity.broken_links}</b> broken links</span>
                  <span className="rounded-lg bg-white/70 px-3 py-2"><b>{summary.audit_integrity.unsigned_after_chain}</b> unsigned gaps</span>
                </div>
              </div>
            </section>
          </>
        ) : null}

        <section className="surface-card p-4 sm:p-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Event stream</p>
              <h2 className="mt-1 text-lg font-black">Security events</h2>
              <p className="mt-1 text-[10px] text-[var(--admin-muted)]">{actionable.length} actionable events in the current result set.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <select value={severity} onChange={(event) => setSeverity(event.target.value as Severity | "")} className="rounded-xl border border-[var(--admin-line)] bg-white px-3 py-2 text-[10px] font-bold">
                <option value="">All severities</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
                <option value="info">Info</option>
              </select>
              <label className="flex items-center gap-2 rounded-xl border border-[var(--admin-line)] px-3 py-2 text-[10px] font-bold">
                <input type="checkbox" checked={unresolvedOnly} onChange={(event) => setUnresolvedOnly(event.target.checked)}/>
                Unresolved only
              </label>
            </div>
          </div>

          <div className="mt-4 space-y-2">
            {events.map((item) => (
              <article key={item.id} className="rounded-xl border border-[var(--admin-line)] p-3.5">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded-full border px-2 py-1 text-[8px] font-black uppercase ${badge(item.severity)}`}>{item.severity}</span>
                      <p className="break-all text-[11px] font-black">{item.event_type}</p>
                      {item.resolved_at ? <span className="flex items-center gap-1 text-[9px] font-bold text-emerald-700"><CheckCircle2 size={11}/>Resolved</span> : null}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[9px] text-[var(--admin-muted)]">
                      <span>{time(item.created_at)}</span>
                      {item.product_id ? <span>Product: {item.product_id}</span> : null}
                      {item.source_ip ? <span>Source: {item.source_ip}</span> : null}
                      {item.actor_ref ? <span className="max-w-[260px] truncate">Actor: {item.actor_ref}</span> : null}
                    </div>
                    {item.details && Object.keys(item.details).length ? (
                      <pre className="mt-3 max-h-32 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-[#f7f9f8] p-2.5 text-[8px] text-[#65756d]">{JSON.stringify(item.details, null, 2)}</pre>
                    ) : null}
                  </div>
                  {!item.resolved_at && ["medium","high","critical"].includes(item.severity) ? (
                    <button disabled={resolving === item.id} onClick={() => void resolve(item)} className="btn-secondary shrink-0">
                      <CheckCircle2 size={13}/>{resolving === item.id ? "Resolving…" : "Resolve"}
                    </button>
                  ) : null}
                </div>
              </article>
            ))}
            {!events.length && !loading ? (
              <div className="py-10 text-center text-[10px] text-[var(--admin-muted)]">
                <ShieldCheck size={20} className="mx-auto mb-2 text-emerald-700"/>No security events match this filter.
              </div>
            ) : null}
            {loading && !events.length ? <div className="flex items-center justify-center gap-2 py-10 text-[10px] text-[var(--admin-muted)]"><Activity size={14} className="animate-pulse"/>Loading security telemetry…</div> : null}
          </div>
        </section>

        {summary && !summary.audit_integrity.healthy ? (
          <section className="flex items-start gap-3 rounded-2xl border border-rose-300 bg-rose-50 p-4 text-rose-900">
            <AlertTriangle size={18} className="mt-0.5 shrink-0"/>
            <div><p className="text-xs font-black">Treat audit-integrity failure as a security incident</p><p className="mt-1 text-[10px] leading-5">Do not clear this warning by editing the database. Preserve logs and backups, compare the latest external audit anchor, and investigate the affected control-plane host.</p></div>
          </section>
        ) : null}
      </div>
    </ControlShell>
  );
}
