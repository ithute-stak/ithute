"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, ArrowLeft, Box, Cpu, Database, HardDrive, MemoryStick, RefreshCw, Send, Server, ShieldAlert, ShieldCheck } from "lucide-react";
import { useParams, useRouter } from "next/navigation";

import { ControlShell } from "@/components/control-shell";
import { PageHeader } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Me = { email: string; is_platform_owner: boolean };
type Point = { created_at: string; cpu_percent?: number | null; memory_percent?: number | null; disk_percent?: number | null; load_1m?: number | null; docker_running?: number | null; docker_total?: number | null };
type ContainerInventory = {
  status: string;
  expected_count?: number;
  running_count?: number;
  missing_count?: number;
  unexpected_count?: number;
  checked_at?: string | null;
  containers: Array<{ name?: string; image?: string; state?: string; project_id?: string | null }>;
};
type AgentCommand = { id: string; kind: string; status: string; error?: string | null; created_at?: string | null };
type SecuritySnapshot = { score: number; posture: string; fingerprint_sha256: string; created_at?: string | null; findings: Array<{ key: string; severity: string; title: string; evidence: string; recommendation: string }> };
type Readiness = { score: number; status: string; checks: Array<{ key: string; weight: number; passed: boolean; detail: string }>; network: { engine: string; checked: number; reachable: boolean }; security: { score?: number | null; posture: string; fingerprint_sha256?: string | null }; engine_contributions: Record<string, { preferred_engine: string }> };
type ServerData = {
  id: string; name: string; hostname: string; public_ip?: string | null; region: string; provider?: string | null; roles: string[]; health: string;
  thresholds: { cpu_percent: number; memory_percent: number; disk_percent: number; offline_minutes: number };
  alerts: Array<{ code: string; severity: "warning" | "critical"; message: string }>;
  workloads: { mailboxes: number; projects: number; databases: number };
  agent: {
    configured: boolean; online: boolean; version?: string | null; last_seen_at?: string | null; os_name?: string | null; kernel_version?: string | null; uptime_seconds?: number | null;
    telemetry: {
      cpu?: { used_percent?: number | null; load_1m?: number | null };
      memory?: { total_bytes?: number; used_bytes?: number; available_bytes?: number; used_percent?: number | null };
      disks?: Array<{ device?: string; mountpoint?: string; filesystem?: string; total_bytes?: number; used_bytes?: number; free_bytes?: number; used_percent?: number | null }>;
      docker?: { installed?: boolean; reachable?: boolean; version?: string | null; containers_running?: number; containers_total?: number };
    };
    capabilities: Record<string, boolean>;
  };
  mail: { linked: boolean; online: boolean; ready: boolean; smtp_ready: boolean; imap_ready: boolean; tls_ready: boolean; backup_ready: boolean };
  hosting: { linked: boolean; online: boolean; accepts_new_projects: boolean };
};

async function api(path: string, init?: RequestInit) {
  const options: RequestInit = { credentials: "include", ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } };
  let response = await fetch(`${API}${path}`, options);
  if (response.status === 401) {
    const refreshed = await fetch(`${API}/auth/refresh`, { method: "POST", credentials: "include" });
    if (refreshed.ok) response = await fetch(`${API}${path}`, options);
  }
  return response;
}

function Sparkline({ points, field, label }: { points: Point[]; field: keyof Point; label: string }) {
  const values = points.map((point) => Number(point[field])).filter((value) => Number.isFinite(value));
  const path = useMemo(() => {
    if (values.length < 2) return "";
    const width = 520;
    const height = 140;
    const max = 100;
    return values.map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - Math.max(0, Math.min(max, value)) / max * height;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
  }, [values]);
  const latest = values.length ? values[values.length - 1] : null;
  return <div className="rounded-2xl border border-[#dce5e0] bg-white p-4">
    <div className="flex items-center justify-between gap-3"><p className="text-xs font-black">{label}</p><b className="text-lg">{latest === null ? "—" : `${latest.toFixed(1)}%`}</b></div>
    <div className="mt-3 h-36 w-full overflow-hidden rounded-xl bg-[#f6f9f7]">
      {path ? <svg viewBox="0 0 520 140" preserveAspectRatio="none" className="h-full w-full" aria-label={`${label} trend`}><path d={path} fill="none" stroke="currentColor" strokeWidth="3" className="text-[#285b55]"/></svg> : <div className="grid h-full place-items-center text-[10px] text-[var(--admin-muted)]">Waiting for historical samples</div>}
    </div>
  </div>;
}

function fmtUptime(seconds?: number | null) {
  if (!seconds) return "—";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return days ? `${days}d ${hours}h` : `${hours}h`;
}

export default function InfrastructureServerDetailPage() {
  const params = useParams<{ serverId: string }>();
  const router = useRouter();
  const serverId = params.serverId;
  const [me, setMe] = useState<Me | null>(null);
  const [server, setServer] = useState<ServerData | null>(null);
  const [history, setHistory] = useState<Point[]>([]);
  const [inventory, setInventory] = useState<ContainerInventory | null>(null);
  const [commands, setCommands] = useState<AgentCommand[]>([]);
  const [security, setSecurity] = useState<SecuritySnapshot | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [hours, setHours] = useState(24);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    setLoading(true); setError("");
    const [serverResponse, historyResponse, inventoryResponse, commandsResponse, securityResponse, readinessResponse] = await Promise.all([
      api(`/platform/infrastructure/servers/${serverId}`),
      api(`/platform/infrastructure/servers/${serverId}/history?hours=${hours}&limit=1000`),
      api(`/platform/infrastructure/servers/${serverId}/container-inventory`),
      api(`/platform/infrastructure/servers/${serverId}/commands?limit=10`),
      api(`/platform/infrastructure/servers/${serverId}/security?limit=1`),
      api(`/platform/infrastructure/servers/${serverId}/readiness`),
    ]);
    if (!serverResponse.ok) { setError("Unable to load server monitoring."); setLoading(false); return; }
    setServer(await serverResponse.json());
    setHistory(historyResponse.ok ? ((await historyResponse.json()).items || []) : []);
    setInventory(inventoryResponse.ok ? await inventoryResponse.json() : null);
    setCommands(commandsResponse.ok ? ((await commandsResponse.json()).items || []) : []);
    if (securityResponse.ok) {
      const body = await securityResponse.json();
      setSecurity((body.items || [])[0] || null);
    } else {
      setSecurity(null);
    }
    setReadiness(readinessResponse.ok ? await readinessResponse.json() : null);
    setLoading(false);
  }

  useEffect(() => {
    void (async () => {
      const response = await api("/auth/me");
      if (response.status === 401) { router.replace("/login"); return; }
      if (!response.ok) { setError("Unable to load account."); setLoading(false); return; }
      const current: Me = await response.json();
      setMe(current);
      if (!current.is_platform_owner) { setError("Platform owner access is required."); setLoading(false); return; }
      await load();
    })();
  }, [router, serverId, hours]);

  useEffect(() => {
    const timer = window.setInterval(() => void load(), 60000);
    return () => window.clearInterval(timer);
  }, [serverId, hours]);

  async function pingAgent() {
    setMessage(""); setError("");
    const response = await api(`/platform/infrastructure/servers/${serverId}/commands`, {
      method: "POST",
      body: JSON.stringify({ kind: "agent.ping", payload: {} }),
    });
    if (!response.ok) { setError("Unable to queue agent ping."); return; }
    setMessage("Structured agent ping queued. The VPS agent will claim it on its next poll.");
    await load();
  }

  async function saveThresholds(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const response = await api(`/platform/infrastructure/servers/${serverId}`, {
      method: "PATCH",
      body: JSON.stringify({
        cpu_alert_percent: Number(data.get("cpu")),
        memory_alert_percent: Number(data.get("memory")),
        disk_alert_percent: Number(data.get("disk")),
        offline_alert_minutes: Number(data.get("offline")),
      }),
    });
    if (!response.ok) { setError("Unable to save monitoring thresholds."); return; }
    setMessage("Monitoring thresholds updated.");
    await load();
  }

  return <ControlShell title={server?.name || "Server monitoring"} subtitle="Physical server telemetry, service health and alerts" userEmail={me?.email}>
    <div className="space-y-5">
      <div className="flex items-center gap-3"><Link href="/infrastructure/servers" className="btn-secondary"><ArrowLeft size={13}/>Servers</Link><button className="icon-button" onClick={() => void load()} aria-label="Refresh"><RefreshCw size={14}/></button></div>
      <PageHeader eyebrow="Infrastructure monitoring" title={server?.name || "Server"} description={server ? `${server.hostname}${server.public_ip ? ` · ${server.public_ip}` : ""} · ${server.provider || "Provider not set"} · ${server.region}` : "Loading server details…"} />

      {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}
      {loading && !server ? <p className="text-xs text-[var(--admin-muted)]">Loading monitoring data…</p> : null}

      {server ? <>
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div className="surface-card p-4"><Cpu size={18}/><p className="mt-3 text-2xl font-black">{server.agent.telemetry.cpu?.used_percent ?? "—"}%</p><p className="text-[10px] font-bold text-[var(--admin-muted)]">CPU usage</p></div>
          <div className="surface-card p-4"><MemoryStick size={18}/><p className="mt-3 text-2xl font-black">{server.agent.telemetry.memory?.used_percent ?? "—"}%</p><p className="text-[10px] font-bold text-[var(--admin-muted)]">RAM usage</p></div>
          <div className="surface-card p-4"><HardDrive size={18}/><p className="mt-3 text-2xl font-black">{server.agent.telemetry.disks?.reduce((max, disk) => Math.max(max, disk.used_percent || 0), 0) ?? "—"}%</p><p className="text-[10px] font-bold text-[var(--admin-muted)]">Highest disk usage</p></div>
          <div className="surface-card p-4"><Activity size={18}/><p className="mt-3 text-2xl font-black">{fmtUptime(server.agent.uptime_seconds)}</p><p className="text-[10px] font-bold text-[var(--admin-muted)]">Server uptime</p></div>
        </section>

        {server.alerts.length ? <section className="space-y-2">{server.alerts.map((alert) => <div key={alert.code} className={`flex items-start gap-2 rounded-xl border p-3 text-xs font-semibold ${alert.severity === "critical" ? "border-red-200 bg-red-50 text-red-800" : "border-amber-200 bg-amber-50 text-amber-800"}`}><AlertTriangle size={15} className="mt-0.5 shrink-0"/>{alert.message}</div>)}</section> : <section className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800"><ShieldCheck size={15}/>No current infrastructure alerts.</section>}

        <section className="surface-card p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2"><ShieldAlert size={16}/><h2 className="text-sm font-black">Production readiness & host security</h2></div><p className="mt-1 max-w-3xl text-[10px] text-[var(--admin-muted)]">Consumed from the donor control plane. Ithute combines fresh agent state, workload health, container drift, Go network probes, Rust-fingerprinted host security evidence and backup readiness into one server score.</p></div><div className="text-right"><p className="text-3xl font-black">{readiness?.score ?? "—"}{readiness ? "/100" : ""}</p><p className="text-[9px] font-black uppercase tracking-[.12em]">{(readiness?.status || "awaiting data").replaceAll("_", " ")}</p></div></div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">{readiness?.checks?.map((check) => <div key={check.key} className={"rounded-xl border p-3 text-[10px] " + (check.passed ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-900")}><div className="flex items-center justify-between gap-2"><b className="capitalize">{check.key.replaceAll("_", " ")}</b><span className="text-[9px] font-black">{check.passed ? "+" + check.weight : "0/" + check.weight}</span></div><p className="mt-1 leading-4">{check.detail}</p></div>)}</div>
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            <div className="rounded-xl border border-[#dfe7e2] p-3"><div className="flex items-center justify-between gap-2"><p className="text-[10px] font-black">Host security posture</p><b className="text-lg">{security?.score ?? "—"}/100</b></div><p className="mt-1 text-[9px] text-[var(--admin-muted)]">Fingerprint {security?.fingerprint_sha256 ? security.fingerprint_sha256.slice(0, 16) + "…" : "awaiting agent"} · SHA-256 via Rust</p>{security?.findings?.length ? <div className="mt-3 space-y-2">{security.findings.slice(0, 6).map((finding) => <div key={finding.key} className="rounded-lg bg-[#f8faf9] p-2 text-[9px]"><div className="flex items-center justify-between gap-2"><b>{finding.title}</b><span className="font-black uppercase">{finding.severity}</span></div><p className="mt-1 text-[var(--admin-muted)]">{finding.evidence}</p><p className="mt-1">{finding.recommendation}</p></div>)}</div> : <p className="mt-3 text-[9px] text-emerald-700">{security ? "No host-security findings in the latest snapshot." : "Awaiting the v3 server-agent security scan."}</p>}</div>
            <div className="rounded-xl border border-[#dfe7e2] p-3"><p className="text-[10px] font-black">Specialist engine contribution</p><p className="mt-1 text-[9px] text-[var(--admin-muted)]">Go performs role-aware network probes. Rust fingerprints security evidence. Java remains the enterprise/XML engine and C++ remains the native blob/fingerprint accelerator where benchmarked.</p><div className="mt-3 flex flex-wrap gap-1.5">{readiness?.engine_contributions ? Object.entries(readiness.engine_contributions).slice(0, 12).map(([operation, info]) => <span key={operation} className="rounded-full border border-[#dce5e0] bg-white px-2 py-1 text-[8px] font-black">{operation} → {info.preferred_engine}</span>) : <span className="text-[9px] text-[var(--admin-muted)]">Engine routing will appear with readiness data.</span>}</div></div>
          </div>
        </section>
        <section className="surface-card p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-sm font-black">Telemetry history</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Five-minute samples are retained for seven days.</p></div><select className="input w-auto" value={hours} onChange={(e) => setHours(Number(e.target.value))}><option value={6}>Last 6 hours</option><option value={24}>Last 24 hours</option><option value={72}>Last 3 days</option><option value={168}>Last 7 days</option></select></div>
          <div className="mt-4 grid gap-4 xl:grid-cols-3"><Sparkline points={history} field="cpu_percent" label="CPU"/><Sparkline points={history} field="memory_percent" label="RAM"/><Sparkline points={history} field="disk_percent" label="Disk pressure"/></div>
        </section>

        <div className="grid gap-5 xl:grid-cols-2">
          <section className="surface-card p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-sm font-black">Agent operations & container drift</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Consumed from the VPS control-plane donor: agents claim allowlisted commands and container inventory is compared with Ithute-managed projects.</p></div><button className="btn-secondary" disabled={!server.agent.configured} onClick={() => void pingAgent()}><Send size={13}/>Ping agent</button></div>
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 text-[10px]"><div className="rounded-xl bg-[#f5f8f6] p-3"><Box size={13}/><b className="mt-2 block text-lg">{inventory?.running_count ?? "—"}</b>running</div><div className="rounded-xl bg-[#f5f8f6] p-3"><b className="block text-lg">{inventory?.expected_count ?? "—"}</b>expected</div><div className="rounded-xl bg-[#f5f8f6] p-3"><b className="block text-lg">{inventory?.missing_count ?? "—"}</b>missing</div><div className="rounded-xl bg-[#f5f8f6] p-3"><b className="block text-lg">{inventory?.unexpected_count ?? "—"}</b>unexpected</div></div>
            <p className={"mt-3 text-[10px] font-black " + (inventory?.status === "healthy" ? "text-emerald-700" : inventory?.status === "attention" ? "text-amber-700" : "text-[var(--admin-muted)]")}>Drift status: {(inventory?.status || "awaiting agent").replaceAll("_", " ")}</p>
            {inventory?.containers?.length ? <div className="mt-3 space-y-1">{inventory.containers.slice(0, 8).map((item, index) => <div key={(item.name || "container") + index} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#e4e9e6] px-3 py-2 text-[9px]"><span><b>{item.name || "unnamed"}</b> · {item.image || "image unknown"}</span><span className="font-bold">{item.state || "unknown"}{item.project_id ? " · managed" : ""}</span></div>)}</div> : null}
            <div className="mt-4"><p className="text-[10px] font-black">Recent structured commands</p><div className="mt-2 flex flex-wrap gap-1.5">{commands.length ? commands.map((command) => <span key={command.id} className="rounded-full border border-[#dce5e0] bg-white px-2 py-1 text-[8px] font-black">{command.kind} · {command.status}</span>) : <span className="text-[9px] text-[var(--admin-muted)]">No agent commands yet.</span>}</div></div>
          </section>

          <section className="surface-card p-4 sm:p-5"><h2 className="text-sm font-black">Service & capability health</h2><div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">{Object.entries(server.agent.capabilities || {}).map(([name, enabled]) => <div key={name} className={`rounded-xl border p-3 text-[10px] font-black ${enabled ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-slate-200 bg-slate-50 text-slate-500"}`}><Database size={13}/><p className="mt-2 capitalize">{name}</p><p className="mt-1 text-[9px]">{enabled ? "Detected" : "Not detected"}</p></div>)}</div><div className="mt-4 rounded-xl bg-[#f5f8f6] p-3 text-[10px]"><b>Docker:</b> {server.agent.telemetry.docker?.reachable ? `online · ${server.agent.telemetry.docker.version || "version unknown"} · ${server.agent.telemetry.docker.containers_running || 0}/${server.agent.telemetry.docker.containers_total || 0} containers running` : "not reachable"}</div></section>

          <section className="surface-card p-4 sm:p-5"><h2 className="text-sm font-black">Alert thresholds</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">These limits control the warnings shown for this server.</p><form onSubmit={saveThresholds} className="mt-4 grid grid-cols-2 gap-3"><label className="text-[10px] font-bold">CPU %<input name="cpu" type="number" min="50" max="100" defaultValue={server.thresholds.cpu_percent} className="input mt-1"/></label><label className="text-[10px] font-bold">RAM %<input name="memory" type="number" min="50" max="100" defaultValue={server.thresholds.memory_percent} className="input mt-1"/></label><label className="text-[10px] font-bold">Disk %<input name="disk" type="number" min="50" max="100" defaultValue={server.thresholds.disk_percent} className="input mt-1"/></label><label className="text-[10px] font-bold">Offline after minutes<input name="offline" type="number" min="2" max="1440" defaultValue={server.thresholds.offline_minutes} className="input mt-1"/></label><button className="btn-primary col-span-2">Save thresholds</button></form></section>
        </div>

        <section className="surface-card p-4 sm:p-5"><h2 className="text-sm font-black">Managed workloads</h2><div className="mt-4 grid grid-cols-3 gap-3 text-center"><div className="rounded-xl bg-[#f5f8f6] p-4"><b className="text-xl">{server.workloads.mailboxes}</b><p className="text-[10px]">Mailboxes</p></div><div className="rounded-xl bg-[#f5f8f6] p-4"><b className="text-xl">{server.workloads.projects}</b><p className="text-[10px]">Applications</p></div><div className="rounded-xl bg-[#f5f8f6] p-4"><b className="text-xl">{server.workloads.databases}</b><p className="text-[10px]">Databases</p></div></div><div className="mt-4 flex flex-wrap gap-2">{server.mail.linked ? <Link href="/mail-nodes" className="btn-secondary">Mail node controls</Link> : null}{server.hosting.linked ? <Link href="/hosting-nodes" className="btn-secondary">Hosting node controls</Link> : null}</div></section>
      </> : null}
    </div>
  </ControlShell>;
}
