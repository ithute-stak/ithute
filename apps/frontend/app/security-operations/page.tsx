"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw, ShieldAlert, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";
import { apiJson } from "@/lib/platform-api";

type Me = { email?: string; is_platform_owner?: boolean };
type Integrity = {
  status: "healthy" | "broken";
  rows_scanned: number;
  sealed_rows: number;
  legacy_unsealed_rows: number;
  verified_rows: number;
  broken_rows: Array<{ id: string; continuity_ok: boolean; hash_ok: boolean }>;
  chain_head?: string | null;
  truncated: boolean;
};
type Event = {
  id: string;
  tenant_id?: string | null;
  actor_user_id?: string | null;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  category: string;
  severity: "high" | "medium" | "info";
  metadata?: Record<string, unknown> | null;
  sealed: boolean;
  event_hash?: string | null;
  created_at?: string | null;
};
type EventResponse = { items: Event[]; summary: { high: number; medium: number; unsealed: number } };

function severityClass(value: string) {
  if (value === "high" || value === "broken") return "border-red-200 bg-red-50 text-red-700";
  if (value === "medium") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-emerald-200 bg-emerald-50 text-emerald-700";
}

export default function SecurityOperationsPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [integrity, setIntegrity] = useState<Integrity | null>(null);
  const [events, setEvents] = useState<EventResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const me = await apiJson<Me>("/auth/me", { ttlMs: 0, force: true });
      if (!me.is_platform_owner) {
        setError("Platform owner access is required.");
        return;
      }
      setEmail(me.email || "");
      const [proof, feed] = await Promise.all([
        apiJson<Integrity>("/audit/platform/integrity", { ttlMs: 0, force: true }),
        apiJson<EventResponse>("/audit/security-events?limit=300", { ttlMs: 0, force: true }),
      ]);
      setIntegrity(proof);
      setEvents(feed);
    } catch (cause) {
      const status = (cause as { status?: number }).status;
      if (status === 401) router.replace("/login");
      else setError(cause instanceof Error ? cause.message : "Unable to load Security Operations.");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 30000);
    return () => window.clearInterval(timer);
  }, [load]);

  const filtered = useMemo(
    () => (events?.items || []).filter((event) => filter === "all" || event.severity === filter || event.category === filter),
    [events, filter],
  );

  return (
    <ControlShell title="Security operations" subtitle="Tamper-evident audit integrity and high-value security events" userEmail={email}>
      <div className="space-y-4">
        <section className="surface-card overflow-hidden">
          <div className="bg-[linear-gradient(120deg,#123a38,#18524d)] p-6 text-white">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-[9px] font-black uppercase tracking-[.16em] text-[#d8c56a]">Security operations centre</p>
                <h1 className="mt-2 text-3xl font-black">Audit integrity & threat events</h1>
                <p className="mt-2 max-w-3xl text-[11px] leading-5 text-[#c8d8d2]">Verify the append-only audit chain and review security-sensitive platform changes, failures, revocations and infrastructure operations.</p>
              </div>
              <button className="rounded-xl bg-[#d8c56a] px-4 py-2.5 text-[10px] font-black text-[#123a38]" onClick={() => void load()} disabled={loading}>
                <RefreshCw size={14} className={`mr-1 inline ${loading ? "animate-spin" : ""}`}/>Refresh
              </button>
            </div>
          </div>
        </section>

        {error ? <div className="surface-card border-red-200 bg-red-50 p-3 text-xs font-bold text-red-700"><AlertTriangle size={15} className="mr-2 inline"/>{error}</div> : null}

        {integrity && events ? <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <article className="surface-card p-4">
              <p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Ledger integrity</p>
              <div className="mt-3 flex items-center gap-2">
                {integrity.status === "healthy" ? <CheckCircle2 size={20} className="text-emerald-600"/> : <ShieldAlert size={20} className="text-red-600"/>}
                <span className={`rounded-full border px-2 py-1 text-[9px] font-black uppercase ${severityClass(integrity.status)}`}>{integrity.status}</span>
              </div>
            </article>
            <article className="surface-card p-4"><p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Verified events</p><p className="mt-3 text-3xl font-black">{integrity.verified_rows}</p><p className="text-[9px] text-[var(--admin-muted)]">{integrity.sealed_rows} sealed</p></article>
            <article className="surface-card p-4"><p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">High severity</p><p className="mt-3 text-3xl font-black text-red-700">{events.summary.high}</p><p className="text-[9px] text-[var(--admin-muted)]">recent security events</p></article>
            <article className="surface-card p-4"><p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Medium severity</p><p className="mt-3 text-3xl font-black text-amber-700">{events.summary.medium}</p><p className="text-[9px] text-[var(--admin-muted)]">review recommended</p></article>
            <article className="surface-card p-4"><p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Legacy unsealed</p><p className="mt-3 text-3xl font-black">{integrity.legacy_unsealed_rows}</p><p className="text-[9px] text-[var(--admin-muted)]">pre-ledger rows retained</p></article>
          </section>

          {integrity.status === "broken" ? (
            <section className="surface-card border-red-200 bg-red-50 p-4">
              <div className="flex gap-3"><ShieldAlert className="text-red-700" size={20}/><div><h2 className="font-black text-red-800">Audit chain integrity failure</h2><p className="mt-1 text-[10px] leading-5 text-red-700">{integrity.broken_rows.length} sealed audit rows failed continuity or hash verification. Treat this as a security incident and preserve database/storage evidence.</p></div></div>
            </section>
          ) : null}

          <section className="surface-card p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div><p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Threat & control events</p><h2 className="mt-1 text-lg font-black">Security event stream</h2></div>
              <select className="input min-w-[210px]" value={filter} onChange={(event) => setFilter(event.target.value)}>
                <option value="all">All events</option><option value="high">High severity</option><option value="medium">Medium severity</option><option value="identity">Identity</option><option value="security">Security</option><option value="infrastructure">Infrastructure</option>
              </select>
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[920px] text-left text-[10px]">
                <thead><tr className="border-b border-[var(--admin-line)] text-[8px] font-black uppercase tracking-[.1em] text-[var(--admin-muted)]"><th className="p-3">Time</th><th className="p-3">Severity</th><th className="p-3">Category</th><th className="p-3">Action</th><th className="p-3">Resource</th><th className="p-3">Proof</th></tr></thead>
                <tbody>{filtered.map((event) => <tr key={event.id} className="border-b border-[var(--admin-line)] last:border-0">
                  <td className="p-3 whitespace-nowrap">{event.created_at ? new Date(event.created_at).toLocaleString() : "—"}</td>
                  <td className="p-3"><span className={`rounded-full border px-2 py-1 font-black uppercase ${severityClass(event.severity)}`}>{event.severity}</span></td>
                  <td className="p-3 font-bold capitalize">{event.category}</td>
                  <td className="p-3 font-black">{event.action}</td>
                  <td className="p-3"><p className="font-bold">{event.resource_type}</p><p className="max-w-[220px] truncate font-mono text-[8px] text-[var(--admin-muted)]">{event.resource_id || "—"}</p></td>
                  <td className="p-3">{event.sealed ? <span className="inline-flex items-center gap-1 text-emerald-700"><ShieldCheck size={12}/>sealed</span> : <span className="text-[var(--admin-muted)]">legacy</span>}</td>
                </tr>)}</tbody>
              </table>
            </div>
          </section>
        </> : loading ? <section className="surface-card p-6 text-xs text-[var(--admin-muted)]">Loading security operations…</section> : null}
      </div>
    </ControlShell>
  );
}
