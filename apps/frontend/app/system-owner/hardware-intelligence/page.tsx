"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Cpu,
  Gauge,
  HardDrive,
  RefreshCw,
  Server,
  ShieldCheck,
  Thermometer,
  WifiOff,
} from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { apiJson } from "@/lib/platform-api";

type FleetItem = {
  server_id: string;
  name: string;
  hostname: string;
  provider?: string | null;
  region: string;
  roles: string[];
  status: "healthy" | "warning" | "critical" | "offline" | "unknown";
  health_score?: number | null;
  online: boolean;
  last_seen_at?: string | null;
  temperature_celsius?: number | null;
  memory_pressure_avg10?: number | null;
  io_pressure_avg10?: number | null;
  filesystem_used_percent?: number | null;
  storage_warning_count: number;
  ecc_corrected_errors?: number;
  ecc_uncorrected_errors?: number;
  bmc_critical_count?: number;
  bmc_warning_count?: number;
  ebpf_block_latency_p50_ms?: number | null;
  ebpf_block_latency_p95_ms?: number | null;
  ebpf_block_latency_p99_ms?: number | null;
  ebpf_block_latency_max_ms?: number | null;
  ebpf_latency_percentiles_capped?: boolean;
  predictive_risk_score?: number | null;
  predictive_state: "learning" | "stable" | "watch" | "elevated" | "high";
  predictive_confidence?: number | null;
  predictive_evidence: string[];
  evidence: string[];
  sampled_at?: string | null;
};

type Fleet = {
  generated_at: string;
  total: number;
  counts: Record<string, number>;
  predictive_counts: Record<string, number>;
  items: FleetItem[];
};

type History = {
  server_id: string;
  name: string;
  hostname: string;
  hours: number;
  items: Array<{
    sampled_at: string;
    health_score: number;
    health_status: string;
    temperature_celsius?: number | null;
    memory_pressure_avg10?: number | null;
    io_pressure_avg10?: number | null;
    filesystem_used_percent?: number | null;
    storage_warning_count: number;
    predictive_risk_score?: number | null;
    predictive_state: string;
    predictive_confidence?: number | null;
  }>;
};

function statusTone(status: string) {
  if (status === "critical") return "border-red-200 bg-red-50 text-red-800";
  if (status === "warning") return "border-amber-200 bg-amber-50 text-amber-800";
  if (status === "offline") return "border-slate-300 bg-slate-100 text-slate-700";
  if (status === "healthy") return "border-emerald-200 bg-emerald-50 text-emerald-800";
  return "border-blue-200 bg-blue-50 text-blue-800";
}

function predictiveTone(state: string) {
  if (state === "high") return "border-red-200 bg-red-50 text-red-800";
  if (state === "elevated") return "border-orange-200 bg-orange-50 text-orange-800";
  if (state === "watch") return "border-amber-200 bg-amber-50 text-amber-800";
  if (state === "stable") return "border-emerald-200 bg-emerald-50 text-emerald-800";
  return "border-blue-200 bg-blue-50 text-blue-800";
}

function metric(value?: number | null, suffix = "") {
  return typeof value === "number" ? `${value.toFixed(1)}${suffix}` : "—";
}

function relativeTime(value?: string | null) {
  if (!value) return "Never";
  const ms = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(ms)) return "Unknown";
  if (ms < 60_000) return "Just now";
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)} min ago`;
  if (ms < 86_400_000) return `${(ms / 3_600_000).toFixed(1)} h ago`;
  return `${(ms / 86_400_000).toFixed(1)} d ago`;
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return <div className="h-16 rounded-xl bg-[#f7faf8]" />;
  const width = 520;
  const height = 90;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(1, max - min);
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / span) * (height - 12) - 6;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-20 w-full rounded-xl bg-[#f7faf8] p-2" role="img" aria-label="Hardware health trend">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export default function HardwareIntelligencePage() {
  const [fleet, setFleet] = useState<Fleet | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [history, setHistory] = useState<History | null>(null);
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState("");

  const loadFleet = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const next = await apiJson<Fleet>("/hardware-intelligence/fleet", { ttlMs: 0, force: true });
      setFleet(next);
      setSelected((current) => current || next.items[0]?.server_id || "");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load Hardware Intelligence.");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadHistory = useCallback(async (serverId: string) => {
    if (!serverId) {
      setHistory(null);
      return;
    }
    setHistoryLoading(true);
    try {
      setHistory(await apiJson<History>(`/hardware-intelligence/servers/${serverId}/history?hours=24&limit=288`, { ttlMs: 0, force: true }));
    } catch {
      setHistory(null);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadFleet();
    const timer = window.setInterval(() => void loadFleet(), 20_000);
    return () => window.clearInterval(timer);
  }, [loadFleet]);

  useEffect(() => {
    void loadHistory(selected);
  }, [selected, loadHistory]);

  const selectedServer = useMemo(() => fleet?.items.find((item) => item.server_id === selected) || null, [fleet, selected]);
  const trend = history?.items.map((item) => item.health_score) || [];
  const predictiveTrend = history?.items.map((item) => item.predictive_risk_score).filter((value): value is number => typeof value === "number") || [];

  return (
    <ControlShell title="Hardware Intelligence" subtitle="Early-warning hardware and kernel health across every Ithute-managed server">
      <div className="space-y-5 pb-20">
        <section className="surface-card overflow-hidden">
          <div className="bg-[linear-gradient(120deg,#123a38,#18524d)] p-6 text-white">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-[9px] font-black uppercase tracking-[.16em] text-[#d8c56a]">C + eBPF · Rust · Go · Python</p>
                <h1 className="mt-2 text-3xl font-black">Hardware Intelligence</h1>
                <p className="mt-2 max-w-3xl text-[11px] leading-5 text-[#c8d8d2]">See which servers are healthy, degrading, critical or offline. Every warning is backed by measurable evidence rather than an unexplained score.</p>
              </div>
              <button onClick={() => void loadFleet()} disabled={loading} className="rounded-xl bg-[#d8c56a] px-4 py-2.5 text-[10px] font-black text-[#123a38]">
                <RefreshCw size={14} className={`mr-1 inline ${loading ? "animate-spin" : ""}`} />Refresh
              </button>
            </div>
          </div>
          {error ? <div className="border-t border-red-200 bg-red-50 p-3 text-[10px] font-bold text-red-700">{error}</div> : null}
        </section>

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {[
            ["Healthy", fleet?.counts.healthy ?? 0, ShieldCheck],
            ["Warning", fleet?.counts.warning ?? 0, AlertTriangle],
            ["Critical", fleet?.counts.critical ?? 0, Thermometer],
            ["Offline", fleet?.counts.offline ?? 0, WifiOff],
            ["Total servers", fleet?.total ?? 0, Server],
          ].map(([label, value, Icon]) => (
            <article key={String(label)} className="surface-card p-4">
              <div className="flex items-center justify-between"><p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">{String(label)}</p><Icon size={15} /></div>
              <p className="mt-3 text-3xl font-black">{String(value)}</p>
            </article>
          ))}
        </section>

        <section className="surface-card p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Predictive baseline</p>
              <h2 className="mt-1 text-lg font-black">Early drift detection</h2>
              <p className="mt-1 max-w-2xl text-[10px] leading-4 text-[var(--admin-muted)]">Each server learns its own normal temperature, pressure and storage-growth behaviour before Ithute raises trend-based risk.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {[
                ["High", fleet?.predictive_counts.high ?? 0, "high"],
                ["Elevated", fleet?.predictive_counts.elevated ?? 0, "elevated"],
                ["Watch", fleet?.predictive_counts.watch ?? 0, "watch"],
                ["Stable", fleet?.predictive_counts.stable ?? 0, "stable"],
                ["Learning", fleet?.predictive_counts.learning ?? 0, "learning"],
              ].map(([label, value, state]) => (
                <div key={String(label)} className={`rounded-xl border px-3 py-2 ${predictiveTone(String(state))}`}>
                  <p className="text-[8px] font-black uppercase">{String(label)}</p>
                  <p className="mt-1 text-lg font-black">{String(value)}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.25fr_.75fr]">
          <div className="surface-card overflow-hidden">
            <div className="border-b border-[var(--admin-line)] p-5">
              <p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Fleet</p>
              <h2 className="mt-1 text-lg font-black">Managed servers</h2>
            </div>
            <div className="divide-y divide-[var(--admin-line)]">
              {fleet?.items.map((item) => (
                <button key={item.server_id} onClick={() => setSelected(item.server_id)} className={`grid w-full gap-3 p-4 text-left transition hover:bg-[#f7faf8] sm:grid-cols-[1.5fr_.7fr_.7fr_.8fr] ${selected === item.server_id ? "bg-[#f0f7f4]" : ""}`}>
                  <div>
                    <div className="flex items-center gap-2"><span className={`rounded-full border px-2 py-0.5 text-[8px] font-black uppercase ${statusTone(item.status)}`}>{item.status}</span><p className="text-[11px] font-black">{item.name}</p></div>
                    <p className="mt-1 text-[9px] text-[var(--admin-muted)]">{item.hostname} · {item.provider || "provider not set"} · {item.region}</p>
                    {item.predictive_state !== "stable" ? <p className="mt-1 text-[9px] font-bold text-blue-700">Prediction: {item.predictive_state} · risk {item.predictive_risk_score ?? 0}/100</p> : null}{item.evidence[0] ? <p className="mt-1 text-[9px] font-bold text-amber-700">{item.evidence[0]}</p> : null}
                  </div>
                  <div><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Health</p><p className="mt-1 text-lg font-black">{item.health_score ?? "—"}</p></div>
                  <div><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Temperature</p><p className="mt-1 text-sm font-black">{metric(item.temperature_celsius, "°C")}</p></div>
                  <div><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Last seen</p><p className="mt-1 text-[10px] font-bold">{relativeTime(item.last_seen_at)}</p></div>
                </button>
              ))}
              {fleet && !fleet.items.length ? <div className="p-6 text-[10px] text-[var(--admin-muted)]">No infrastructure servers are registered yet.</div> : null}
            </div>
          </div>

          <div className="surface-card p-5">
            <p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Selected server</p>
            <h2 className="mt-1 text-lg font-black">{selectedServer?.name || "Select a server"}</h2>
            {selectedServer ? (
              <div className="mt-4 space-y-3">
                <div className={`rounded-xl border p-4 ${statusTone(selectedServer.status)}`}>
                  <p className="text-[8px] font-black uppercase">Hardware health</p>
                  <div className="mt-2 flex items-end justify-between"><p className="text-4xl font-black">{selectedServer.health_score ?? "—"}</p><p className="text-[10px] font-black uppercase">{selectedServer.status}</p></div>
                </div>
                <div className={`rounded-xl border p-4 ${predictiveTone(selectedServer.predictive_state)}`}>
                  <p className="text-[8px] font-black uppercase">Predictive risk</p>
                  <div className="mt-2 flex items-end justify-between"><p className="text-4xl font-black">{selectedServer.predictive_risk_score ?? 0}</p><p className="text-[10px] font-black uppercase">{selectedServer.predictive_state}</p></div>
                  <p className="mt-2 text-[9px] font-bold">Confidence {metric(selectedServer.predictive_confidence ? selectedServer.predictive_confidence * 100 : 0, "%")}</p>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-xl border border-[var(--admin-line)] p-3"><Thermometer size={14}/><p className="mt-2 text-[8px] font-black uppercase text-[var(--admin-muted)]">Temperature</p><p className="mt-1 text-sm font-black">{metric(selectedServer.temperature_celsius, "°C")}</p></div>
                  <div className="rounded-xl border border-[var(--admin-line)] p-3"><Activity size={14}/><p className="mt-2 text-[8px] font-black uppercase text-[var(--admin-muted)]">Memory PSI</p><p className="mt-1 text-sm font-black">{metric(selectedServer.memory_pressure_avg10, "%")}</p></div>
                  <div className="rounded-xl border border-[var(--admin-line)] p-3"><Cpu size={14}/><p className="mt-2 text-[8px] font-black uppercase text-[var(--admin-muted)]">I/O PSI</p><p className="mt-1 text-sm font-black">{metric(selectedServer.io_pressure_avg10, "%")}</p></div>
                  <div className="rounded-xl border border-[var(--admin-line)] p-3"><HardDrive size={14}/><p className="mt-2 text-[8px] font-black uppercase text-[var(--admin-muted)]">Root used</p><p className="mt-1 text-sm font-black">{metric(selectedServer.filesystem_used_percent, "%")}</p></div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-xl border border-[var(--admin-line)] p-3">
                    <p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">ECC memory</p>
                    <p className="mt-1 text-sm font-black">{selectedServer.ecc_uncorrected_errors ?? 0} UE · {selectedServer.ecc_corrected_errors ?? 0} CE</p>
                  </div>
                  <div className="rounded-xl border border-[var(--admin-line)] p-3">
                    <p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">BMC sensors</p>
                    <p className="mt-1 text-sm font-black">{selectedServer.bmc_critical_count ?? 0} critical · {selectedServer.bmc_warning_count ?? 0} warning</p>
                  </div>
                </div>
                <div className="rounded-xl border border-[var(--admin-line)] p-3">
                  <div className="flex items-center justify-between"><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Kernel block latency</p><HardDrive size={12}/></div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-[10px] sm:grid-cols-4">
                    <div><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">p50</p><p className="mt-1 font-black">{metric(selectedServer.ebpf_block_latency_p50_ms, " ms")}</p></div>
                    <div><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">p95</p><p className="mt-1 font-black">{metric(selectedServer.ebpf_block_latency_p95_ms, " ms")}</p></div>
                    <div><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">p99</p><p className="mt-1 font-black">{metric(selectedServer.ebpf_block_latency_p99_ms, " ms")}</p></div>
                    <div><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Max</p><p className="mt-1 font-black">{metric(selectedServer.ebpf_block_latency_max_ms, " ms")}</p></div>
                  </div>
                  {selectedServer.ebpf_latency_percentiles_capped ? <p className="mt-2 text-[8px] font-bold text-amber-700">A percentile entered the open-ended &gt;2s bucket, so the displayed percentile is a lower bound.</p> : null}
                </div>
                <div className="rounded-xl border border-[var(--admin-line)] p-3">
                  <div className="flex items-center justify-between"><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">24-hour health trend</p>{historyLoading ? <RefreshCw size={12} className="animate-spin"/> : <Gauge size={12}/>}</div>
                  <div className="mt-2 text-[#18524d]"><Sparkline values={trend} /></div>
                  <div className="mt-3 flex items-center justify-between"><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Predictive risk trend</p><span className="text-[8px] font-bold text-[var(--admin-muted)]">0–100</span></div>
                  <div className="mt-2 text-amber-700"><Sparkline values={predictiveTrend} /></div>
                </div>
              </div>
            ) : null}
          </div>
        </section>

        {selectedServer ? (
          <>
            <section className="surface-card p-5">
              <p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Predictive evidence</p>
              <h2 className="mt-1 text-lg font-black">What is drifting from this server&apos;s baseline</h2>
              <div className="mt-4 grid gap-2 md:grid-cols-2">
                {selectedServer.predictive_evidence.map((item, index) => <div key={`prediction-${item}-${index}`} className={`rounded-xl border p-3 text-[10px] font-bold ${predictiveTone(selectedServer.predictive_state)}`}>{item}</div>)}
                {!selectedServer.predictive_evidence.length ? <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-[10px] font-bold text-blue-700">Ithute is still learning this server&apos;s normal operating baseline.</div> : null}
              </div>
            </section>
            <section className="surface-card p-5">
              <p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Threshold evidence</p>
              <h2 className="mt-1 text-lg font-black">Why Ithute assigned the current health status</h2>
              <div className="mt-4 grid gap-2 md:grid-cols-2">
                {selectedServer.evidence.map((item, index) => <div key={`${item}-${index}`} className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-[10px] font-bold text-amber-800">{item}</div>)}
                {!selectedServer.evidence.length ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-[10px] font-bold text-emerald-700">No active threshold-based hardware warning evidence for this server.</div> : null}
              </div>
            </section>
          </>
        ) : null}
      </div>
    </ControlShell>
  );
}
