"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, AlertTriangle, DatabaseBackup, HardDrive, RefreshCw, Server, ShieldCheck } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { apiJson } from "@/lib/platform-api";

type Alert = { severity: string; source: string; title: string; detail: string };
type Ops = {
  status: string;
  alerts: Alert[];
  live_infrastructure: {
    status: string;
    sampled_at?: string | null;
    host?: {
      cpu_percent?: number | null;
      memory_percent?: number | null;
      disk_percent?: number | null;
      load_1m?: number | null;
      load_5m?: number | null;
      load_15m?: number | null;
      uptime_seconds?: number | null;
      network_receive_bytes_per_second?: number | null;
      network_transmit_bytes_per_second?: number | null;
      disk_read_bytes_per_second?: number | null;
      disk_write_bytes_per_second?: number | null;
    };
    container_count?: number;
  };
  backup: {
    healthy?: boolean;
    severity?: string;
    reasons?: string[];
    last_success_age_seconds?: number | null;
    last_run?: Record<string, unknown> | null;
    repository_health?: Record<string, unknown> | null;
    checked_at?: string | null;
  };
  restore_drills: Record<string, unknown>[];
};

function pct(value?: number | null) {
  return typeof value === "number" ? `${value.toFixed(1)}%` : "—";
}

function bytes(value?: number | null) {
  if (typeof value !== "number") return "—";
  const units = ["B/s", "KB/s", "MB/s", "GB/s"];
  let n = value;
  let index = 0;
  while (n >= 1024 && index < units.length - 1) { n /= 1024; index += 1; }
  return `${n.toFixed(index ? 1 : 0)} ${units[index]}`;
}

function age(value?: number | null) {
  if (typeof value !== "number") return "Not reported";
  if (value < 3600) return `${Math.round(value / 60)} min`;
  if (value < 86400) return `${(value / 3600).toFixed(1)} h`;
  return `${(value / 86400).toFixed(1)} days`;
}

function tone(severity: string) {
  const key = severity.toLowerCase();
  if (["critical", "high"].includes(key)) return "border-red-200 bg-red-50 text-red-800";
  if (["warning", "medium"].includes(key)) return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-emerald-200 bg-emerald-50 text-emerald-800";
}

export default function OwnerOperationsPage() {
  const [data, setData] = useState<Ops | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await apiJson<Ops>("/platform/ithute/system-owner/operations", { ttlMs: 0, force: true }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load operations assurance.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 20000);
    return () => window.clearInterval(timer);
  }, [load]);

  const host = data?.live_infrastructure.host || {};
  const latestDrill = data?.restore_drills?.[0];

  return (
    <ControlShell title="Operations Assurance" subtitle="Live infrastructure, backup health and recovery assurance for the IDS platform">
      <div className="space-y-5 pb-20">
        <section className="surface-card overflow-hidden">
          <div className="bg-[linear-gradient(120deg,#123a38,#18524d)] p-6 text-white">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-[9px] font-black uppercase tracking-[.16em] text-[#d8c56a]">Production operations</p>
                <h1 className="mt-2 text-3xl font-black">Operations Assurance</h1>
                <p className="mt-2 max-w-2xl text-[11px] leading-5 text-[#c8d8d2]">Physical VPS utilisation is kept separate from sellable hosting allocations. Backup and restore assurance is treated as a first-class production signal.</p>
              </div>
              <button onClick={() => void load()} disabled={loading} className="rounded-xl bg-[#d8c56a] px-4 py-2.5 text-[10px] font-black text-[#123a38]"><RefreshCw size={14} className={`mr-1 inline ${loading ? "animate-spin" : ""}`} />Refresh</button>
            </div>
          </div>
          {error ? <div className="border-t border-red-200 bg-red-50 p-3 text-[10px] font-bold text-red-700">{error}</div> : null}
        </section>

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ["CPU", pct(host.cpu_percent), Server],
            ["Memory", pct(host.memory_percent), Activity],
            ["Root disk", pct(host.disk_percent), HardDrive],
            ["Containers", String(data?.live_infrastructure.container_count ?? "—"), ShieldCheck],
          ].map(([label, value, Icon]) => (
            <article key={String(label)} className="surface-card p-4">
              <div className="flex items-center justify-between"><p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">{String(label)}</p><Icon size={15} /></div>
              <p className="mt-3 text-3xl font-black">{String(value)}</p>
            </article>
          ))}
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.1fr_.9fr]">
          <div className="surface-card p-5">
            <div className="flex items-center justify-between"><div><p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Attention</p><h2 className="mt-1 text-lg font-black">Operational alerts</h2></div><AlertTriangle size={18} /></div>
            <div className="mt-4 space-y-2">
              {data?.alerts.map((alert, index) => <article key={`${alert.source}-${alert.title}-${index}`} className={`rounded-xl border p-3 ${tone(alert.severity)}`}><p className="text-[9px] font-black uppercase tracking-[.1em]">{alert.source} · {alert.severity}</p><p className="mt-1 text-[11px] font-black">{alert.title}</p><p className="mt-1 text-[9px] leading-4 opacity-80">{alert.detail}</p></article>)}
              {data && !data.alerts.length ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-[10px] font-bold text-emerald-700">No owner-level operations alerts are open.</div> : null}
            </div>
          </div>

          <div className="surface-card p-5">
            <div className="flex items-center justify-between"><div><p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Backup assurance</p><h2 className="mt-1 text-lg font-black">Backup & restore posture</h2></div><DatabaseBackup size={18} /></div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl bg-[#f7faf8] p-3"><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Backup health</p><p className="mt-2 text-sm font-black">{data?.backup.healthy ? "Healthy" : "Needs attention"}</p></div>
              <div className="rounded-xl bg-[#f7faf8] p-3"><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Last success age</p><p className="mt-2 text-sm font-black">{age(data?.backup.last_success_age_seconds)}</p></div>
            </div>
            <div className="mt-3 rounded-xl border border-[var(--admin-line)] p-3"><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Latest restore drill</p><pre className="mt-2 max-h-36 overflow-auto whitespace-pre-wrap text-[9px] leading-4">{latestDrill ? JSON.stringify(latestDrill, null, 2) : "No restore drill recorded yet."}</pre></div>
          </div>
        </section>

        <section className="surface-card p-5">
          <p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Throughput</p>
          <h2 className="mt-1 text-lg font-black">Host activity</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4 text-[10px]">
            <div className="rounded-xl border border-[var(--admin-line)] p-3"><b>Network in</b><p className="mt-1">{bytes(host.network_receive_bytes_per_second)}</p></div>
            <div className="rounded-xl border border-[var(--admin-line)] p-3"><b>Network out</b><p className="mt-1">{bytes(host.network_transmit_bytes_per_second)}</p></div>
            <div className="rounded-xl border border-[var(--admin-line)] p-3"><b>Disk read</b><p className="mt-1">{bytes(host.disk_read_bytes_per_second)}</p></div>
            <div className="rounded-xl border border-[var(--admin-line)] p-3"><b>Disk write</b><p className="mt-1">{bytes(host.disk_write_bytes_per_second)}</p></div>
          </div>
        </section>
      </div>
    </ControlShell>
  );
}
