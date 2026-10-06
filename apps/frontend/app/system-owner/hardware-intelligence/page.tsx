"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
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
import type { LucideIcon } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { apiJson, apiMutation } from "@/lib/platform-api";

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
  cpu_native?: {
    available: boolean;
    vendor: string;
    family: number;
    model: number;
    stepping: number;
    invariant_tsc: boolean;
    rdtscp: boolean;
    aes_ni: boolean;
    avx: boolean;
    avx2: boolean;
    vmx: boolean;
    svm: boolean;
    hypervisor_present: boolean;
    hypervisor_vendor: string;
    logical_processors: number;
  };
  predictive_risk_score?: number | null;
  predictive_state: "learning" | "stable" | "watch" | "elevated" | "high";
  predictive_confidence?: number | null;
  predictive_evidence: string[];
  predictive_models?: {
    robust_baseline?: { ready?: boolean; risk_score?: number };
    isolation_forest?: { ready?: boolean; risk_score?: number; anomaly_score?: number; features?: number; trees?: number };
    change_point?: { ready?: boolean; risk_score?: number; metric?: string; shift_sigma?: number };
    survival?: { ready?: boolean; calibration?: string; median_risk_horizon_hours?: number; failure_probability_72h?: number; reason?: string };
    supervised_boosting?: { ready?: boolean; engine?: string; reason?: string };
  };
  evidence: string[];
  sampled_at?: string | null;
  maintenance: {
    active: boolean;
    reason?: string | null;
    ends_at?: string | null;
    suppress_notifications: boolean;
  };
  acknowledgement: {
    acknowledged: boolean;
    note?: string | null;
    acknowledged_at?: string | null;
  };
  incident?: {
    id: string;
    severity: string;
    status: string;
    title: string;
    summary: string;
    predictive_state: string;
    predictive_risk_score?: number | null;
    notification_suppressed: boolean;
    workflow_plan?: {
      engine?: string;
      escalation?: string;
      actions?: string[];
      recommendations?: string[];
      ranked_recommendations?: Array<{
        action: string;
        priority_score: number;
        urgency: string;
        confidence_percent: number;
        evidence: string[];
        expected_impact: string;
        drain_recommended: boolean;
        operator_approval_required: boolean;
        learned_samples?: number;
        learned_success_rate?: number;
        learning_adjustment?: number;
      }>;
    };
    deliveries?: Array<{
      channel: string;
      status: string;
      attempts: number;
      delivered_at?: string | null;
    }>;
    maintenance_task?: {
      id: string;
      priority: string;
      status: string;
      assigned_to_user_id?: string | null;
      completion_note?: string;
      remediation_action?: string;
      remediation_outcome?: string;
      outcome_recorded_at?: string | null;
      measured_outcome?: string;
      verification_confidence?: number | null;
      verification_sample_count?: number;
      verification_evidence?: string[];
      verification_evaluated_at?: string | null;
      completed_at?: string | null;
    } | null;
    opened_at?: string | null;
    last_seen_at?: string | null;
  } | null;
};

type OperationsSummary = {
  open_incidents: number;
  incidents_by_severity: Record<string, number>;
  tasks: Record<string, number>;
  deliveries: Record<string, number>;
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

function Sparkline({ values, label = "Hardware metric trend" }: { values: number[]; label?: string }) {
  if (values.length < 2) return <div className="h-16 rounded-xl bg-[#f7faf8]" aria-label={label} />;
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
    <svg viewBox={`0 0 ${width} ${height}`} className="h-20 w-full rounded-xl bg-[#f7faf8] p-2" role="img" aria-label={label}>
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function TrendCard({ label, value, suffix, values, note }: { label: string; value?: number | null; suffix?: string; values: number[]; note: string }) {
  return (
    <article className="rounded-xl border border-[var(--admin-line)] bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[8px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">{label}</p>
        <p className="text-sm font-black">{metric(value, suffix || "")}</p>
      </div>
      <div className="mt-2 text-[#18524d]"><Sparkline values={values} label={`${label} 24-hour trend`} /></div>
      <p className="mt-2 text-[8px] leading-4 text-[var(--admin-muted)]">{note}</p>
    </article>
  );
}

export default function HardwareIntelligencePage() {
  const searchParams = useSearchParams();
  const requestedServer = searchParams.get("server") || "";
  const [fleet, setFleet] = useState<Fleet | null>(null);
  const [operations, setOperations] = useState<OperationsSummary | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [history, setHistory] = useState<History | null>(null);
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [maintenanceReason, setMaintenanceReason] = useState("");
  const [maintenanceHours, setMaintenanceHours] = useState("2");
  const [ackNote, setAckNote] = useState("");
  const [taskNote, setTaskNote] = useState("");
  const [taskAction, setTaskAction] = useState("");
  const [taskOutcome, setTaskOutcome] = useState("");
  const [actionLoading, setActionLoading] = useState(false);

  const loadFleet = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [next, ops] = await Promise.all([
        apiJson<Fleet>("/hardware-intelligence/fleet", { ttlMs: 0, force: true }),
        apiJson<OperationsSummary>("/hardware-intelligence/operations-summary", { ttlMs: 0, force: true }),
      ]);
      setFleet(next);
      setOperations(ops);
      setSelected((current) => {
        if (requestedServer && next.items.some((item) => item.server_id === requestedServer)) return requestedServer;
        return current || next.items[0]?.server_id || "";
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load Hardware Intelligence.");
    } finally {
      setLoading(false);
    }
  }, [requestedServer]);

  const createMaintenance = useCallback(async () => {
    if (!selected || !maintenanceReason.trim()) return;
    const hours = Math.max(0.25, Math.min(24 * 30, Number(maintenanceHours) || 2));
    const starts = new Date();
    const ends = new Date(starts.getTime() + hours * 3_600_000);
    setActionLoading(true);
    setActionError("");
    try {
      await apiMutation(`/hardware-intelligence/servers/${selected}/maintenance-windows`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          starts_at: starts.toISOString(),
          ends_at: ends.toISOString(),
          reason: maintenanceReason.trim(),
          suppress_notifications: true,
        }),
      }, ["/hardware-intelligence/fleet"]);
      setMaintenanceReason("");
      await loadFleet();
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Unable to create maintenance window.");
    } finally {
      setActionLoading(false);
    }
  }, [selected, maintenanceReason, maintenanceHours, loadFleet]);

  const acknowledgeCurrent = useCallback(async () => {
    if (!selected) return;
    setActionLoading(true);
    setActionError("");
    try {
      await apiMutation(`/hardware-intelligence/servers/${selected}/acknowledge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: ackNote.trim() }),
      }, ["/hardware-intelligence/fleet"]);
      setAckNote("");
      await loadFleet();
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Unable to acknowledge hardware alert.");
    } finally {
      setActionLoading(false);
    }
  }, [selected, ackNote, loadFleet]);

  const updateMaintenanceTask = useCallback(async (status: "in_progress" | "completed" | "cancelled") => {
    const taskId = fleet?.items.find((item) => item.server_id === selected)?.incident?.maintenance_task?.id;
    if (!taskId) return;
    setActionLoading(true);
    setActionError("");
    try {
      await apiMutation(`/hardware-intelligence/maintenance-tasks/${taskId}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status,
          note: taskNote.trim(),
          remediation_action: status === "completed" ? taskAction : "",
          outcome: status === "completed" ? taskOutcome : "",
        }),
      }, ["/hardware-intelligence/fleet"]);
      setTaskNote("");
      if (status === "completed") {
        setTaskAction("");
        setTaskOutcome("");
      }
      await loadFleet();
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Unable to update maintenance task.");
    } finally {
      setActionLoading(false);
    }
  }, [fleet, selected, taskNote, taskAction, taskOutcome, loadFleet]);

  const retryIncidentNotifications = useCallback(async () => {
    const incident = fleet?.items.find((item) => item.server_id === selected)?.incident;
    if (!incident) return;
    setActionLoading(true);
    setActionError("");
    try {
      await apiMutation(`/hardware-intelligence/incidents/${incident.id}/retry-notifications`, {
        method: "POST",
      }, ["/hardware-intelligence/fleet", "/hardware-intelligence/operations-summary"]);
      await loadFleet();
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Unable to retry hardware incident notifications.");
    } finally {
      setActionLoading(false);
    }
  }, [fleet, selected, loadFleet]);

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
  const temperatureTrend = history?.items.map((item) => item.temperature_celsius).filter((value): value is number => typeof value === "number") || [];
  const memoryTrend = history?.items.map((item) => item.memory_pressure_avg10).filter((value): value is number => typeof value === "number") || [];
  const ioTrend = history?.items.map((item) => item.io_pressure_avg10).filter((value): value is number => typeof value === "number") || [];
  const storageTrend = history?.items.map((item) => item.filesystem_used_percent).filter((value): value is number => typeof value === "number") || [];
  const firstRisk = predictiveTrend[0];
  const latestRisk = predictiveTrend[predictiveTrend.length - 1];
  const riskDelta = typeof firstRisk === "number" && typeof latestRisk === "number" ? latestRisk - firstRisk : null;
  const sampledPoints = history?.items.length || 0;

  return (
    <ControlShell title="Hardware Intelligence" subtitle="Early-warning hardware and kernel health across every Ithute-managed server">
      <div className="space-y-5 pb-20">
        <section className="surface-card overflow-hidden">
          <div className="bg-[linear-gradient(120deg,#123a38,#18524d)] p-6 text-white">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-[9px] font-black uppercase tracking-[.16em] text-[#d8c56a]">Assembly · C + eBPF · Rust · Go · Python · Java</p>
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
          {([
            ["Healthy", fleet?.counts.healthy ?? 0, ShieldCheck],
            ["Warning", fleet?.counts.warning ?? 0, AlertTriangle],
            ["Critical", fleet?.counts.critical ?? 0, Thermometer],
            ["Offline", fleet?.counts.offline ?? 0, WifiOff],
            ["Total servers", fleet?.total ?? 0, Server],
          ] satisfies Array<[string, number, LucideIcon]>).map(([label, value, Icon]) => (
            <article key={String(label)} className="surface-card p-4">
              <div className="flex items-center justify-between"><p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">{String(label)}</p><Icon size={15} /></div>
              <p className="mt-3 text-3xl font-black">{String(value)}</p>
            </article>
          ))}
        </section>

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ["Open incidents", operations?.open_incidents ?? 0],
            ["Maintenance work", (operations?.tasks.open ?? 0) + (operations?.tasks.in_progress ?? 0)],
            ["Delivery retries", operations?.deliveries.retry ?? 0],
            ["Delivery failures", operations?.deliveries.failed ?? 0],
          ].map(([label, value]) => (
            <article key={String(label)} className="surface-card p-4">
              <p className="text-[8px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">{String(label)}</p>
              <p className="mt-2 text-2xl font-black">{String(value)}</p>
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

        <section className="surface-card p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Intelligence pipeline</p>
              <h2 className="mt-1 text-lg font-black">From silicon evidence to operator decision</h2>
              <p className="mt-1 max-w-3xl text-[10px] leading-4 text-[var(--admin-muted)]">Every stage stays visible: low-level signals, validation, transport, prediction, workflow policy and human approval.</p>
            </div>
            <div className="rounded-xl border border-[var(--admin-line)] bg-[#f7faf8] px-4 py-3 text-right">
              <p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">24-hour samples · selected server</p>
              <p className="mt-1 text-xl font-black">{sampledPoints}</p>
            </div>
          </div>
          <div className="mt-4 grid gap-2 md:grid-cols-3 xl:grid-cols-6">
            {[
              ["C + eBPF", "Hardware + kernel signals"],
              ["Rust", "Validation + hardening"],
              ["Go", "Collection + transport"],
              ["Python", "Prediction + drift"],
              ["Java", "Rules + remediation"],
              ["Operator", "Approval + evidence"],
            ].map(([engine, role], index) => (
              <div key={engine} className="rounded-xl border border-[var(--admin-line)] bg-white p-3">
                <p className="text-[8px] font-black uppercase text-[#18524d]">{index + 1}. {engine}</p>
                <p className="mt-1 text-[9px] font-bold">{role}</p>
              </div>
            ))}
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
                {selectedServer.incident ? (
                  <div className={`rounded-xl border p-4 ${selectedServer.incident.severity === "critical" ? "border-red-200 bg-red-50 text-red-800" : "border-orange-200 bg-orange-50 text-orange-800"}`}>
                    <p className="text-[8px] font-black uppercase">Active hardware incident</p>
                    <p className="mt-2 text-[11px] font-black">{selectedServer.incident.title}</p>
                    <p className="mt-1 text-[9px] leading-4">{selectedServer.incident.summary}</p>
                    <div className="mt-2 flex flex-wrap gap-2 text-[8px] font-black uppercase">
                      <span>Severity {selectedServer.incident.severity}</span>
                      <span>Risk {selectedServer.incident.predictive_risk_score ?? "—"}</span>
                      {selectedServer.incident.workflow_plan?.engine ? <span>Workflow {selectedServer.incident.workflow_plan.engine}</span> : null}
                      {selectedServer.incident.workflow_plan?.escalation ? <span>Escalation {selectedServer.incident.workflow_plan.escalation}</span> : null}
                      {selectedServer.incident.notification_suppressed ? <span>Notifications suppressed by maintenance</span> : null}
                    </div>
                    {(selectedServer.incident.deliveries || []).some((delivery) => ["failed", "retry"].includes(delivery.status)) && !selectedServer.incident.notification_suppressed ? (
                      <button disabled={actionLoading} onClick={() => void retryIncidentNotifications()} className="mt-3 rounded-lg border border-current/30 bg-white/70 px-3 py-2 text-[8px] font-black uppercase disabled:opacity-50">
                        Retry failed notifications
                      </button>
                    ) : null}
                    {selectedServer.incident.workflow_plan?.ranked_recommendations?.length ? (
                      <div className="mt-3 rounded-lg border border-current/20 bg-white/60 p-3">
                        <p className="text-[8px] font-black uppercase">Ranked remediation</p>
                        <div className="mt-2 space-y-2">
                          {selectedServer.incident.workflow_plan.ranked_recommendations.map((item, index) => (
                            <div key={`${item.action}-${index}`} className="rounded-lg border border-current/15 bg-white/70 p-2">
                              <div className="flex flex-wrap items-center gap-2 text-[8px] font-black uppercase">
                                <span>#{index + 1}</span>
                                <span>Priority {item.priority_score}/100</span>
                                <span>{item.urgency}</span>
                                <span>Confidence {item.confidence_percent}%</span>
                                {item.drain_recommended ? <span>Drain recommended</span> : null}
                              </div>
                              <p className="mt-1 text-[10px] font-black">{item.action.replaceAll("_", " ")}</p>
                              <p className="mt-1 text-[9px] leading-4">{item.expected_impact}</p>
                              {item.evidence?.length ? (
                                <p className="mt-1 text-[8px] font-bold opacity-80">Evidence: {item.evidence.join(" · ")}</p>
                              ) : null}
                              {typeof item.learned_samples === "number" ? (
                                <p className="mt-1 text-[8px] font-bold opacity-80">Outcome learning: {item.learned_samples} confirmed cases · {item.learned_success_rate ?? 0}% weighted success · ranking {Number(item.learning_adjustment || 0) >= 0 ? "+" : ""}{item.learning_adjustment || 0}</p>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : selectedServer.incident.workflow_plan?.recommendations?.length ? (
                      <div className="mt-3 rounded-lg border border-current/20 bg-white/60 p-3">
                        <p className="text-[8px] font-black uppercase">Recommended remediation</p>
                        <ul className="mt-2 space-y-1 text-[9px]">
                          {selectedServer.incident.workflow_plan.recommendations.map((item) => (
                            <li key={item}>• {item.replaceAll("_", " ")}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {selectedServer.incident.deliveries?.length ? (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {selectedServer.incident.deliveries.map((delivery) => (
                          <span key={`${delivery.channel}-${delivery.status}`} className="rounded-full border border-current/20 bg-white/60 px-2 py-1 text-[8px] font-black uppercase">
                            {delivery.channel}: {delivery.status}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    {selectedServer.incident.maintenance_task ? (
                      <div className="mt-3 rounded-lg border border-current/20 bg-white/60 p-2 text-[9px]">
                        <span className="font-black uppercase">Maintenance task</span>
                        <span className="ml-2 font-bold">{selectedServer.incident.maintenance_task.status} · {selectedServer.incident.maintenance_task.priority}</span>
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <div className="rounded-xl border border-[var(--admin-line)] p-4">
                  <p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Operations</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <span className={`rounded-full border px-2 py-1 text-[8px] font-black uppercase ${selectedServer.maintenance.active ? "border-blue-200 bg-blue-50 text-blue-800" : "border-slate-200 bg-slate-50 text-slate-600"}`}>
                      {selectedServer.maintenance.active ? "Maintenance active" : "No maintenance"}
                    </span>
                    <span className={`rounded-full border px-2 py-1 text-[8px] font-black uppercase ${selectedServer.acknowledgement.acknowledged ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"}`}>
                      {selectedServer.acknowledgement.acknowledged ? "Current sample acknowledged" : "Unacknowledged"}
                    </span>
                  </div>
                  {selectedServer.maintenance.active ? <p className="mt-2 text-[9px] text-[var(--admin-muted)]">{selectedServer.maintenance.reason} · until {selectedServer.maintenance.ends_at ? new Date(selectedServer.maintenance.ends_at).toLocaleString() : "unknown"}</p> : null}
                  {selectedServer.acknowledgement.acknowledged && selectedServer.acknowledgement.note ? <p className="mt-2 text-[9px] text-[var(--admin-muted)]">Ack note: {selectedServer.acknowledgement.note}</p> : null}
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
                  <div className="flex items-center justify-between"><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">CPU precision layer</p><Cpu size={12}/></div>
                  {selectedServer.cpu_native?.available ? (
                    <>
                      <p className="mt-2 text-[10px] font-black">{selectedServer.cpu_native.vendor || "x86_64 CPU"} · family {selectedServer.cpu_native.family} · model {selectedServer.cpu_native.model} · stepping {selectedServer.cpu_native.stepping}</p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {[
                          ["Invariant TSC", selectedServer.cpu_native.invariant_tsc],
                          ["RDTSCP", selectedServer.cpu_native.rdtscp],
                          ["AES-NI", selectedServer.cpu_native.aes_ni],
                          ["AVX", selectedServer.cpu_native.avx],
                          ["AVX2", selectedServer.cpu_native.avx2],
                          ["VMX", selectedServer.cpu_native.vmx],
                          ["SVM", selectedServer.cpu_native.svm],
                        ].map(([label, enabled]) => (
                          <span key={String(label)} className={`rounded-full border px-2 py-1 text-[8px] font-black ${enabled ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-slate-200 bg-slate-50 text-slate-500"}`}>{String(label)}</span>
                        ))}
                      </div>
                      <p className="mt-2 text-[9px] font-bold text-[var(--admin-muted)]">
                        {selectedServer.cpu_native.hypervisor_present
                          ? `Virtualized · ${selectedServer.cpu_native.hypervisor_vendor || "hypervisor vendor not exposed"} · ${selectedServer.cpu_native.logical_processors} logical CPU(s)`
                          : `Bare-metal or hypervisor bit not exposed · ${selectedServer.cpu_native.logical_processors} logical CPU(s)`}
                      </p>
                    </>
                  ) : <p className="mt-2 text-[9px] text-[var(--admin-muted)]">Assembly CPU telemetry is unavailable on this host architecture.</p>}
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
          <section className="surface-card p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Live signal matrix</p>
                <h2 className="mt-1 text-lg font-black">24-hour hardware behaviour</h2>
                <p className="mt-1 text-[10px] text-[var(--admin-muted)]">The model stays explainable: operators can inspect the raw operating trends behind each prediction.</p>
              </div>
              <div className="rounded-xl border border-[var(--admin-line)] px-3 py-2 text-right">
                <p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Risk movement</p>
                <p className={`mt-1 text-sm font-black ${typeof riskDelta === "number" && riskDelta > 0 ? "text-red-700" : "text-emerald-700"}`}>
                  {typeof riskDelta === "number" ? `${riskDelta > 0 ? "+" : ""}${riskDelta.toFixed(1)} points` : "Learning"}
                </p>
              </div>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              {[
                ["Robust baseline", selectedServer.predictive_models?.robust_baseline?.ready, selectedServer.predictive_models?.robust_baseline?.risk_score, "Median/MAD + trend"],
                ["Isolation Forest", selectedServer.predictive_models?.isolation_forest?.ready, selectedServer.predictive_models?.isolation_forest?.risk_score, selectedServer.predictive_models?.isolation_forest?.ready ? `${selectedServer.predictive_models.isolation_forest.trees || 0} trees · anomaly ${Number(selectedServer.predictive_models.isolation_forest.anomaly_score || 0).toFixed(3)}` : "Learning baseline"],
                ["Change point", selectedServer.predictive_models?.change_point?.ready, selectedServer.predictive_models?.change_point?.risk_score, selectedServer.predictive_models?.change_point?.ready ? `${(selectedServer.predictive_models.change_point.metric || "signal").replaceAll("_", " ")} · ${Number(selectedServer.predictive_models.change_point.shift_sigma || 0).toFixed(1)}σ shift` : "No comparable window"],
                ["72h survival risk", selectedServer.predictive_models?.survival?.ready, selectedServer.predictive_models?.survival?.failure_probability_72h, selectedServer.predictive_models?.survival?.ready ? `Prior-only · horizon ${Number(selectedServer.predictive_models.survival.median_risk_horizon_hours || 0).toFixed(0)}h` : "Not enough risk/confidence"],
                ["Supervised boost", selectedServer.predictive_models?.supervised_boosting?.ready, null, selectedServer.predictive_models?.supervised_boosting?.ready ? "Calibrated labels available" : "Waiting for confirmed failure labels"],
              ].map(([label, ready, score, detail]) => (
                <div key={String(label)} className="rounded-xl border border-[var(--admin-line)] bg-[#f7faf8] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">{String(label)}</p>
                    <span className={`rounded-full border px-2 py-0.5 text-[7px] font-black uppercase ${ready ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-slate-200 bg-slate-50 text-slate-500"}`}>{ready ? "active" : "guarded"}</span>
                  </div>
                  <p className="mt-2 text-xl font-black">{typeof score === "number" ? `${Number(score).toFixed(0)}/100` : "—"}</p>
                  <p className="mt-1 text-[8px] leading-4 text-[var(--admin-muted)]">{String(detail)}</p>
                </div>
              ))}
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <TrendCard label="Temperature" value={selectedServer.temperature_celsius} suffix="°C" values={temperatureTrend} note="Thermal drift can precede throttling, fan or cooling failures." />
              <TrendCard label="Memory pressure" value={selectedServer.memory_pressure_avg10} suffix="%" values={memoryTrend} note="PSI pressure exposes contention before application memory starvation." />
              <TrendCard label="I/O pressure" value={selectedServer.io_pressure_avg10} suffix="%" values={ioTrend} note="Sustained I/O stalls can reveal saturation or storage degradation." />
              <TrendCard label="Filesystem used" value={selectedServer.filesystem_used_percent} suffix="%" values={storageTrend} note="Capacity growth is tracked before a disk-full event becomes an outage." />
            </div>
          </section>
        ) : null}

        {selectedServer?.incident?.maintenance_task ? (
          <section className="surface-card p-5">
            <p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Recovery assurance</p>
            <h2 className="mt-1 text-lg font-black">Remediation evidence and trust boundary</h2>
            <div className="mt-4 grid gap-3 lg:grid-cols-4">
              <div className="rounded-xl border border-[var(--admin-line)] p-4">
                <p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Operator action</p>
                <p className="mt-2 text-[11px] font-black">{selectedServer.incident.maintenance_task.remediation_action ? selectedServer.incident.maintenance_task.remediation_action.replaceAll("_", " ") : "Not completed yet"}</p>
                <p className="mt-2 text-[9px] text-[var(--admin-muted)]">Human action remains explicit and auditable. Ithute does not silently execute destructive hardware remediation.</p>
              </div>
              <div className="rounded-xl border border-[var(--admin-line)] p-4">
                <p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Reported outcome</p>
                <p className="mt-2 text-[11px] font-black">{selectedServer.incident.maintenance_task.remediation_outcome ? selectedServer.incident.maintenance_task.remediation_outcome.replaceAll("_", " ") : "Awaiting operator evidence"}</p>
                <p className="mt-2 text-[9px] text-[var(--admin-muted)]">This is the operator-observed result and is not treated as proof by itself.</p>
              </div>
              <div className="rounded-xl border border-[var(--admin-line)] p-4">
                <p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Telemetry-verified outcome</p>
                <p className="mt-2 text-[11px] font-black">{selectedServer.incident.maintenance_task.measured_outcome ? selectedServer.incident.maintenance_task.measured_outcome.replaceAll("_", " ") : "Collecting evidence"}</p>
                <p className="mt-1 text-[9px] font-bold text-[var(--admin-muted)]">
                  {selectedServer.incident.maintenance_task.verification_sample_count ?? 0} post-action samples
                  {typeof selectedServer.incident.maintenance_task.verification_confidence === "number" ? ` · ${(selectedServer.incident.maintenance_task.verification_confidence * 100).toFixed(0)}% confidence` : ""}
                </p>
                {selectedServer.incident.maintenance_task.verification_evidence?.length ? (
                  <ul className="mt-2 space-y-1 text-[8px] leading-4 text-[var(--admin-muted)]">
                    {selectedServer.incident.maintenance_task.verification_evidence.slice(0, 4).map((item, index) => <li key={`${item}-${index}`}>• {item}</li>)}
                  </ul>
                ) : <p className="mt-2 text-[8px] text-[var(--admin-muted)]">Ithute needs at least three fresh telemetry samples after completion before it verifies the result.</p>}
              </div>
              <div className="rounded-xl border border-[var(--admin-line)] p-4">
                <p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Current measured state</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <span className={`rounded-full border px-2 py-1 text-[8px] font-black uppercase ${statusTone(selectedServer.status)}`}>{selectedServer.status}</span>
                  <span className={`rounded-full border px-2 py-1 text-[8px] font-black uppercase ${predictiveTone(selectedServer.predictive_state)}`}>{selectedServer.predictive_state} risk</span>
                </div>
                <p className="mt-2 text-[9px] text-[var(--admin-muted)]">Health {selectedServer.health_score ?? "—"}/100 · risk {selectedServer.predictive_risk_score ?? "—"}/100 · last seen {relativeTime(selectedServer.last_seen_at)}.</p>
              </div>
            </div>
          </section>
        ) : null}

        {selectedServer ? (
          <section className="surface-card p-5">
            <p className="text-[9px] font-black uppercase tracking-[.12em] text-[var(--admin-muted)]">Operator controls</p>
            <h2 className="mt-1 text-lg font-black">Acknowledge, schedule or execute maintenance</h2>
            {actionError ? <div className="mt-3 rounded-xl border border-red-200 bg-red-50 p-3 text-[10px] font-bold text-red-700">{actionError}</div> : null}
            <div className="mt-4 grid gap-4 lg:grid-cols-3">
              <div className="rounded-xl border border-[var(--admin-line)] p-4">
                <p className="text-[9px] font-black uppercase text-[var(--admin-muted)]">Maintenance window</p>
                <p className="mt-1 text-[10px] text-[var(--admin-muted)]">Health continues to be measured, but notification workflows can suppress planned-maintenance noise.</p>
                <input value={maintenanceReason} onChange={(event) => setMaintenanceReason(event.target.value)} placeholder="Reason, e.g. kernel upgrade" className="mt-3 w-full rounded-xl border border-[var(--admin-line)] bg-white px-3 py-2 text-[10px]" />
                <div className="mt-2 flex gap-2">
                  <input value={maintenanceHours} onChange={(event) => setMaintenanceHours(event.target.value)} type="number" min="0.25" max="720" step="0.25" className="w-28 rounded-xl border border-[var(--admin-line)] bg-white px-3 py-2 text-[10px]" />
                  <span className="self-center text-[9px] font-bold text-[var(--admin-muted)]">hours</span>
                  <button disabled={actionLoading || !maintenanceReason.trim()} onClick={() => void createMaintenance()} className="ml-auto rounded-xl bg-[#18524d] px-4 py-2 text-[9px] font-black text-white disabled:opacity-50">Start maintenance</button>
                </div>
              </div>
              <div className="rounded-xl border border-[var(--admin-line)] p-4">
                <p className="text-[9px] font-black uppercase text-[var(--admin-muted)]">Acknowledge current sample</p>
                <p className="mt-1 text-[10px] text-[var(--admin-muted)]">Acknowledgement applies only to the latest telemetry snapshot. New telemetry requires a new acknowledgement.</p>
                <input value={ackNote} onChange={(event) => setAckNote(event.target.value)} placeholder="Optional operator note" className="mt-3 w-full rounded-xl border border-[var(--admin-line)] bg-white px-3 py-2 text-[10px]" />
                <button disabled={actionLoading || selectedServer.acknowledgement.acknowledged} onClick={() => void acknowledgeCurrent()} className="mt-2 rounded-xl bg-[#d8c56a] px-4 py-2 text-[9px] font-black text-[#123a38] disabled:opacity-50">{selectedServer.acknowledgement.acknowledged ? "Acknowledged" : "Acknowledge current sample"}</button>
              </div>
              {selectedServer.incident?.maintenance_task ? (
                <div className="rounded-xl border border-[var(--admin-line)] p-4">
                  <p className="text-[9px] font-black uppercase text-[var(--admin-muted)]">Incident maintenance task</p>
                  <p className="mt-1 text-[10px] text-[var(--admin-muted)]">Track the physical/host remediation separately from automatic health recovery.</p>
                  <p className="mt-2 text-[10px] font-black uppercase">Status: {selectedServer.incident.maintenance_task.status}</p>
                  {selectedServer.incident.maintenance_task.remediation_action ? <p className="mt-1 text-[9px] font-bold">Action: {selectedServer.incident.maintenance_task.remediation_action.replaceAll("_", " ")}</p> : null}
                  {selectedServer.incident.maintenance_task.remediation_outcome ? <p className="mt-1 text-[9px] font-bold">Outcome: {selectedServer.incident.maintenance_task.remediation_outcome.replaceAll("_", " ")}</p> : null}
                  {!["completed", "cancelled"].includes(selectedServer.incident.maintenance_task.status) ? (
                    <>
                      <select value={taskAction} onChange={(event) => setTaskAction(event.target.value)} className="mt-3 w-full rounded-xl border border-[var(--admin-line)] bg-white px-3 py-2 text-[10px]">
                        <option value="">Remediation actually performed</option>
                        {(selectedServer.incident.workflow_plan?.ranked_recommendations || []).map((item) => <option key={item.action} value={item.action}>{item.action.replaceAll("_", " ")}</option>)}
                      </select>
                      <select value={taskOutcome} onChange={(event) => setTaskOutcome(event.target.value)} className="mt-2 w-full rounded-xl border border-[var(--admin-line)] bg-white px-3 py-2 text-[10px]">
                        <option value="">Observed outcome</option>
                        <option value="resolved">Resolved the incident</option>
                        <option value="improved">Improved the condition</option>
                        <option value="no_change">No measurable change</option>
                        <option value="worsened">Condition worsened</option>
                      </select>
                    </>
                  ) : null}
                  <input value={taskNote} onChange={(event) => setTaskNote(event.target.value)} placeholder="Operator note / evidence" className="mt-3 w-full rounded-xl border border-[var(--admin-line)] bg-white px-3 py-2 text-[10px]" />
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button disabled={actionLoading || selectedServer.incident.maintenance_task.status !== "open"} onClick={() => void updateMaintenanceTask("in_progress")} className="rounded-xl border border-[var(--admin-line)] px-3 py-2 text-[9px] font-black disabled:opacity-50">Start work</button>
                    <button disabled={actionLoading || ["completed", "cancelled"].includes(selectedServer.incident.maintenance_task.status) || !taskAction || !taskOutcome} onClick={() => void updateMaintenanceTask("completed")} className="rounded-xl bg-[#18524d] px-3 py-2 text-[9px] font-black text-white disabled:opacity-50">Complete + record outcome</button>
                    <button disabled={actionLoading || ["completed", "cancelled"].includes(selectedServer.incident.maintenance_task.status)} onClick={() => void updateMaintenanceTask("cancelled")} className="rounded-xl border border-red-200 px-3 py-2 text-[9px] font-black text-red-700 disabled:opacity-50">Cancel</button>
                  </div>
                </div>
              ) : null}
            </div>
          </section>
        ) : null}

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
