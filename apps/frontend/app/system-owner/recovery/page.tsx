"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, DatabaseBackup, History, RefreshCw, ShieldAlert } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { apiJson } from "@/lib/platform-api";

type BackupStatus = {
  healthy: boolean;
  severity: string;
  reasons: string[];
  operator_action?: string | null;
  last_run?: Record<string, unknown> | null;
  repository_health?: Record<string, unknown> | null;
  last_success_age_seconds?: number | null;
  max_age_seconds?: number;
  checked_at?: string;
};

type Drills = { items: Record<string, unknown>[] };

function age(seconds?: number | null) {
  if (typeof seconds !== "number") return "Not available";
  if (seconds < 3600) return `${Math.round(seconds / 60)} minutes`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} hours`;
  return `${(seconds / 86400).toFixed(1)} days`;
}

export default function RecoveryCentrePage() {
  const [status, setStatus] = useState<BackupStatus | null>(null);
  const [drills, setDrills] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [backup, history] = await Promise.all([
        apiJson<BackupStatus>("/backups/status", { ttlMs: 0, force: true }),
        apiJson<Drills>("/backups/restore-drills?limit=30", { ttlMs: 0, force: true }),
      ]);
      setStatus(backup);
      setDrills(history.items || []);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load backup assurance.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return (
    <ControlShell title="Backup & Recovery" subtitle="Owner assurance for backup freshness, repository health and tested restores">
      <div className="space-y-5 pb-20">
        <section className="surface-card overflow-hidden">
          <div className="bg-[linear-gradient(120deg,#123a38,#18524d)] p-6 text-white"><div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-[9px] font-black uppercase tracking-[.16em] text-[#d8c56a]">Disaster recovery</p><h1 className="mt-2 text-3xl font-black">Backup & Recovery Assurance</h1><p className="mt-2 max-w-2xl text-[11px] leading-5 text-[#c8d8d2]">A successful backup is only trusted when it is fresh, its repository is healthy and a controlled restore has been proven.</p></div><button disabled={loading} onClick={() => void load()} className="rounded-xl bg-[#d8c56a] px-4 py-2.5 text-[10px] font-black text-[#123a38]"><RefreshCw size={14} className={`mr-1 inline ${loading ? "animate-spin" : ""}`} />Refresh</button></div></div>
          {error ? <div className="border-t border-red-200 bg-red-50 p-3 text-[10px] font-bold text-red-700">{error}</div> : null}
        </section>

        <section className={`surface-card border p-5 ${status?.healthy ? "border-emerald-200" : "border-red-200"}`}>
          <div className="flex gap-3">{status?.healthy ? <CheckCircle2 className="text-emerald-600" /> : <ShieldAlert className="text-red-600" />}<div><p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Current assurance</p><h2 className="mt-1 text-xl font-black">{status?.healthy ? "Backup posture healthy" : "Backup posture needs attention"}</h2><p className="mt-2 text-[10px] text-[var(--admin-muted)]">Last successful backup: {age(status?.last_success_age_seconds)}</p></div></div>
          {status?.reasons?.length ? <div className="mt-4 space-y-2">{status.reasons.map((reason) => <div key={reason} className="rounded-xl border border-red-200 bg-red-50 p-3 text-[10px] font-bold text-red-700">{reason}</div>)}</div> : null}
          {status?.operator_action ? <div className="mt-4 rounded-xl bg-[#f7faf8] p-3 text-[10px]"><b>Operator action:</b> {status.operator_action}</div> : null}
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
          <div className="surface-card p-5"><div className="flex items-center justify-between"><div><p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Scheduled backup</p><h2 className="mt-1 text-lg font-black">Last run metadata</h2></div><DatabaseBackup size={18} /></div><pre className="mt-4 max-h-80 overflow-auto rounded-xl bg-[#f7faf8] p-4 text-[9px] leading-4">{JSON.stringify(status?.last_run || { status: "No metadata available" }, null, 2)}</pre></div>
          <div className="surface-card p-5"><div className="flex items-center justify-between"><div><p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Repository</p><h2 className="mt-1 text-lg font-black">Backup repository health</h2></div><CheckCircle2 size={18} /></div><pre className="mt-4 max-h-80 overflow-auto rounded-xl bg-[#f7faf8] p-4 text-[9px] leading-4">{JSON.stringify(status?.repository_health || { healthy: false, detail: "No repository-health metadata available" }, null, 2)}</pre></div>
        </section>

        <section className="surface-card p-5"><div className="flex items-center justify-between"><div><p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Recovery evidence</p><h2 className="mt-1 text-lg font-black">Restore drill history</h2></div><History size={18} /></div><div className="mt-4 space-y-2">{drills.map((drill, index) => <pre key={index} className="overflow-auto rounded-xl border border-[var(--admin-line)] p-3 text-[9px] leading-4">{JSON.stringify(drill, null, 2)}</pre>)}{!drills.length ? <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-[10px] font-bold text-amber-800">No controlled restore drill has been recorded. The System Owner operations view will keep this as an open warning until recovery evidence exists.</div> : null}</div></section>
      </div>
    </ControlShell>
  );
}
