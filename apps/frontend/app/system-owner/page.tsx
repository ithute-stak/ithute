"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Boxes,
  Building2,
  ExternalLink,
  Gauge,
  Globe2,
  HardDrive,
  KeyRound,
  Mail,
  RefreshCw,
  Server,
  ShieldCheck,
  UsersRound,
} from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { apiJson, apiMutation } from "@/lib/platform-api";

type Totals = {
  organizations: number;
  active_users: number;
  products: number;
  product_access_grants: number;
  hosted_projects: number;
  hosting_nodes: number;
  domains: number;
  mailboxes: number;
};

type Organization = {
  id: string;
  name: string;
  slug: string;
  status: string;
  members: number;
  hosted_projects: number;
  domains: number;
  mailboxes: number;
  products: { id: string; name: string; status: string; plan: string }[];
};

type Node = {
  id: string;
  name: string;
  hostname: string;
  public_ip?: string | null;
  status: string;
  accepts_new_projects: boolean;
  agent_online: boolean;
  agent_version?: string | null;
  last_seen_at?: string | null;
  projects: number;
  capacity: { storage_mb: number; memory_mb: number; cpu_millicores: number };
  allocated: { storage_mb: number; memory_mb: number; cpu_millicores: number };
  allocation_percent: { storage: number; memory: number; cpu: number };
};

type Product = {
  id: string;
  name: string;
  category: string;
  status: string;
  public_url?: string | null;
  version?: string | null;
  metrics?: Record<string, unknown>;
  last_seen_at?: string | null;
  last_error?: string | null;
  services?: Record<string, string>;
  database?: { status?: string; engine?: string | null; ownership?: string };
};

type Alert = { severity: string; title: string; detail: string };
type Audit = { id: string; action: string; resource_type: string; resource_id?: string | null; tenant_id?: string | null; created_at?: string | null };

type Overview = {
  totals: Totals;
  organizations: Organization[];
  infrastructure: Node[];
  products: Product[];
  core_operations: { status?: string; services?: Record<string, string>; mail_queue_total?: number | null; error?: string };
  alerts: Alert[];
  recent_audit: Audit[];
  generated_at: string;
};

type Registry = {
  organizations: { id: string; name: string; status: string }[];
  products: { id: string; name: string; public_url?: string | null; auth_mode: string }[];
  grants: {
    id: string;
    subject_type: string;
    subject_id: string;
    organization_name?: string | null;
    product_id: string;
    product_name: string;
    plan: string;
    status: string;
    features: Record<string, unknown>;
    updated_at?: string | null;
  }[];
};

type LiveContainer = {
  name: string;
  image?: string | null;
  cpu_percent?: number | null;
  memory_bytes?: number | null;
  memory_limit_bytes?: number | null;
  memory_percent?: number | null;
  network_receive_bytes_per_second?: number | null;
  network_transmit_bytes_per_second?: number | null;
};

type LiveInfrastructure = {
  status: string;
  sampled_at?: string | null;
  error?: string;
  container_count: number;
  host: {
    cpu_percent?: number | null;
    load_1m?: number | null;
    load_5m?: number | null;
    load_15m?: number | null;
    memory_total_bytes?: number | null;
    memory_used_bytes?: number | null;
    memory_percent?: number | null;
    disk_total_bytes?: number | null;
    disk_used_bytes?: number | null;
    disk_percent?: number | null;
    disk_read_bytes_per_second?: number | null;
    disk_write_bytes_per_second?: number | null;
    network_receive_bytes_per_second?: number | null;
    network_transmit_bytes_per_second?: number | null;
    uptime_seconds?: number | null;
  };
  containers: LiveContainer[];
};

function statusClass(value: string) {
  const key = value.toLowerCase();
  if (["ok", "online", "active", "healthy", "connected", "ready"].includes(key)) return "bg-emerald-50 text-emerald-700";
  if (["offline", "failed", "critical", "suspended", "down", "unavailable"].includes(key)) return "bg-red-50 text-red-700";
  return "bg-amber-50 text-amber-700";
}

function Status({ value }: { value: string }) {
  return <span className={`rounded-full px-2.5 py-1 text-[9px] font-black uppercase tracking-[.08em] ${statusClass(value)}`}>{value}</span>;
}

function Metric({ icon: Icon, label, value, note }: { icon: typeof Building2; label: string; value: number; note: string }) {
  return (
    <div className="surface-card p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[9px] font-black uppercase tracking-[.13em] text-[var(--admin-muted)]">{label}</p>
        <Icon size={15} className="text-[var(--admin-pine)]" />
      </div>
      <p className="mt-3 text-3xl font-black">{value}</p>
      <p className="mt-1 text-[10px] text-[var(--admin-muted)]">{note}</p>
    </div>
  );
}

function CapacityBar({ label, value, used, total }: { label: string; value: number; used: number; total: number }) {
  const width = Math.min(100, Math.max(0, value));
  return (
    <div>
      <div className="flex items-center justify-between text-[9px] font-bold">
        <span>{label}</span>
        <span>{value.toFixed(1)}%</span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-[#e8efec]">
        <div className={`h-full rounded-full ${value >= 90 ? "bg-red-500" : value >= 75 ? "bg-amber-500" : "bg-emerald-600"}`} style={{ width: `${width}%` }} />
      </div>
      <p className="mt-1 text-[8px] text-[var(--admin-muted)]">{used.toLocaleString()} / {total.toLocaleString()}</p>
    </div>
  );
}

function RuntimeBar({ label, value, note }: { label: string; value?: number | null; note: string }) {
  const resolved = value ?? 0;
  const width = Math.min(100, Math.max(0, resolved));
  return (
    <div className="rounded-xl border border-[var(--admin-line)] p-3">
      <div className="flex items-center justify-between text-[9px] font-black"><span>{label}</span><span>{value == null ? "—" : `${value.toFixed(1)}%`}</span></div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-[#e8efec]"><div className={`h-full rounded-full ${resolved >= 90 ? "bg-red-500" : resolved >= 75 ? "bg-amber-500" : "bg-emerald-600"}`} style={{ width: `${width}%` }} /></div>
      <p className="mt-2 text-[8px] text-[var(--admin-muted)]">{note}</p>
    </div>
  );
}

function formatBytes(value?: number | null) {
  if (value == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let resolved = Math.max(0, value);
  let index = 0;
  while (resolved >= 1024 && index < units.length - 1) { resolved /= 1024; index += 1; }
  return `${resolved >= 10 || index === 0 ? resolved.toFixed(0) : resolved.toFixed(1)} ${units[index]}`;
}

function formatRate(value?: number | null) {
  return value == null ? "—" : `${formatBytes(value)}/s`;
}

function formatUptime(value?: number | null) {
  if (value == null) return "—";
  const days = Math.floor(value / 86400);
  const hours = Math.floor((value % 86400) / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  return days ? `${days}d ${hours}h` : `${hours}h ${minutes}m`;
}

export default function SystemOwnerPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [registry, setRegistry] = useState<Registry | null>(null);
  const [telemetry, setTelemetry] = useState<LiveInfrastructure | null>(null);
  const [loading, setLoading] = useState(true);
  const [telemetryLoading, setTelemetryLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [productId, setProductId] = useState("");
  const [plan, setPlan] = useState("business");
  const [grantStatus, setGrantStatus] = useState("active");

  const loadTelemetry = useCallback(async () => {
    setTelemetryLoading(true);
    try {
      setTelemetry(await apiJson<LiveInfrastructure>("/platform/ithute/system-owner/live-infrastructure", { ttlMs: 0, force: true }));
    } catch {
      setTelemetry({ status: "unavailable", sampled_at: null, host: {}, containers: [], container_count: 0, error: "Unable to load live infrastructure telemetry." });
    } finally {
      setTelemetryLoading(false);
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [ownerOverview, productRegistry] = await Promise.all([
        apiJson<Overview>("/platform/ithute/system-owner/overview", { ttlMs: 0, force: true }),
        apiJson<Registry>("/platform/ithute/system-owner/product-access", { ttlMs: 0, force: true }),
      ]);
      setOverview(ownerOverview);
      setRegistry(productRegistry);
      setTenantId((value) => value || productRegistry.organizations[0]?.id || "");
      setProductId((value) => value || productRegistry.products[0]?.id || "");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load System Owner Command Centre. Platform-owner access is required.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); void loadTelemetry(); }, [load, loadTelemetry]);
  useEffect(() => {
    const timer = window.setInterval(() => { void loadTelemetry(); }, 20_000);
    return () => window.clearInterval(timer);
  }, [loadTelemetry]);

  const openAlerts = overview?.alerts.length || 0;
  const sortedGrants = useMemo(() => registry?.grants.filter((grant) => ["tenant", "organization"].includes(grant.subject_type)) || [], [registry]);

  async function saveAccess() {
    if (!tenantId || !productId) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await apiMutation(
        "/platform/ithute/system-owner/product-access",
        {
          method: "PUT",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tenant_id: tenantId, product_id: productId, plan, status: grantStatus, features: {} }),
        },
        ["/platform/ithute/system-owner", "/platform/ithute/access"],
      );
      setMessage("Product access updated. The organisation can use the app launcher through central Ithute identity.");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to update product access.");
    } finally {
      setSaving(false);
    }
  }

  const host = telemetry?.host || {};

  return (
    <ControlShell title="System Owner" subtitle="IDS-wide organisations, infrastructure, product access and operational health">
      <div className="space-y-5">
        <section className="surface-card overflow-hidden">
          <div className="bg-[linear-gradient(120deg,#123a38,#18524d)] p-5 text-white sm:p-7">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <div className="flex items-center gap-2 text-[9px] font-black uppercase tracking-[.16em] text-[#d8c56a]"><ShieldCheck size={14} />IDS private control plane</div>
                <h1 className="mt-3 text-3xl font-black tracking-[-.03em] sm:text-4xl">System Owner Command Centre</h1>
                <p className="mt-3 max-w-3xl text-[11px] leading-5 text-[#c8d8d2]">One owner-only view of every organisation, assigned IDS product, hosting allocation and live physical VPS/container telemetry. Product business data remains inside each independent product database.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link href="/ithute-platform" className="rounded-xl border border-white/20 px-3 py-2 text-[10px] font-black hover:bg-white/10"><KeyRound size={14} className="mr-1 inline" />Auth & Push</Link>
                <Link href="/ithute-platform/control-center" className="rounded-xl border border-white/20 px-3 py-2 text-[10px] font-black hover:bg-white/10"><Activity size={14} className="mr-1 inline" />Product operations</Link>
                <button disabled={loading || telemetryLoading} onClick={() => { void load(); void loadTelemetry(); }} className="rounded-xl bg-[#d8c56a] px-3 py-2 text-[10px] font-black text-[#123a38]"><RefreshCw size={14} className={`mr-1 inline ${loading || telemetryLoading ? "animate-spin" : ""}`} />Refresh</button>
              </div>
            </div>
          </div>
          {error ? <div className="border-t border-red-200 bg-red-50 p-3 text-[10px] font-bold text-red-700">{error}</div> : null}
          {message ? <div className="border-t border-emerald-200 bg-emerald-50 p-3 text-[10px] font-bold text-emerald-700">{message}</div> : null}
        </section>

        {overview ? (
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-8">
            <Metric icon={Building2} label="Organisations" value={overview.totals.organizations} note="IDS tenants" />
            <Metric icon={UsersRound} label="Users" value={overview.totals.active_users} note="active accounts" />
            <Metric icon={Boxes} label="Products" value={overview.totals.products} note="registered IDS apps" />
            <Metric icon={KeyRound} label="Access" value={overview.totals.product_access_grants} note="active grants" />
            <Metric icon={Server} label="Hosted apps" value={overview.totals.hosted_projects} note="managed projects" />
            <Metric icon={Gauge} label="Nodes" value={overview.totals.hosting_nodes} note="hosting nodes" />
            <Metric icon={Globe2} label="Domains" value={overview.totals.domains} note="managed domains" />
            <Metric icon={Mail} label="Mailboxes" value={overview.totals.mailboxes} note="managed mailboxes" />
          </section>
        ) : null}

        <section className="grid gap-4 xl:grid-cols-[.9fr_1.1fr]">
          <div className="surface-card p-5">
            <div className="flex items-start justify-between gap-4">
              <div><p className="text-[9px] font-black uppercase tracking-[.13em] text-[var(--admin-muted)]">Live production host</p><h2 className="mt-1 text-lg font-black">Physical VPS utilisation</h2><p className="mt-1 text-[9px] text-[var(--admin-muted)]">Auto-refreshes every 20 seconds from the private Prometheus collectors.</p></div>
              <Status value={telemetry?.status || (telemetryLoading ? "loading" : "unavailable")} />
            </div>
            {telemetry?.error ? <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-[9px] font-bold text-amber-800">{telemetry.error}</div> : null}
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <RuntimeBar label="CPU" value={host.cpu_percent} note={`Load ${host.load_1m ?? "—"} / ${host.load_5m ?? "—"} / ${host.load_15m ?? "—"}`} />
              <RuntimeBar label="Memory" value={host.memory_percent} note={`${formatBytes(host.memory_used_bytes)} / ${formatBytes(host.memory_total_bytes)}`} />
              <RuntimeBar label="Disk" value={host.disk_percent} note={`${formatBytes(host.disk_used_bytes)} / ${formatBytes(host.disk_total_bytes)}`} />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <div className="rounded-xl bg-[#f7faf8] p-3"><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Network in</p><p className="mt-1 text-[11px] font-black">{formatRate(host.network_receive_bytes_per_second)}</p></div>
              <div className="rounded-xl bg-[#f7faf8] p-3"><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Network out</p><p className="mt-1 text-[11px] font-black">{formatRate(host.network_transmit_bytes_per_second)}</p></div>
              <div className="rounded-xl bg-[#f7faf8] p-3"><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Disk read/write</p><p className="mt-1 text-[10px] font-black">{formatRate(host.disk_read_bytes_per_second)} / {formatRate(host.disk_write_bytes_per_second)}</p></div>
              <div className="rounded-xl bg-[#f7faf8] p-3"><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Uptime</p><p className="mt-1 text-[11px] font-black">{formatUptime(host.uptime_seconds)}</p></div>
            </div>
            <p className="mt-3 text-right text-[8px] text-[var(--admin-muted)]">{telemetry?.sampled_at ? `Sampled ${new Date(telemetry.sampled_at).toLocaleString()}` : "Waiting for first telemetry sample"}</p>
          </div>

          <div className="surface-card p-5">
            <div className="flex items-start justify-between gap-4"><div><p className="text-[9px] font-black uppercase tracking-[.13em] text-[var(--admin-muted)]">Container telemetry</p><h2 className="mt-1 text-lg font-black">Docker resource usage</h2></div><span className="rounded-full bg-[#eef5f2] px-2.5 py-1 text-[9px] font-black text-[var(--admin-pine)]">{telemetry?.container_count || 0} containers</span></div>
            <div className="mt-4 max-h-[360px] overflow-auto"><table className="w-full min-w-[650px] text-left text-[9px]"><thead className="sticky top-0 bg-white"><tr className="border-b border-[var(--admin-line)] text-[8px] font-black uppercase tracking-[.08em] text-[var(--admin-muted)]"><th className="p-2">Container</th><th className="p-2">CPU</th><th className="p-2">Memory</th><th className="p-2">Net in</th><th className="p-2">Net out</th></tr></thead><tbody>{telemetry?.containers.slice(0, 20).map((item) => <tr key={item.name} className="border-b border-[var(--admin-line)] last:border-0"><td className="p-2"><p className="font-black">{item.name}</p><p className="max-w-[270px] truncate text-[7px] text-[var(--admin-muted)]">{item.image || "image not reported"}</p></td><td className="p-2 font-black">{item.cpu_percent == null ? "—" : `${item.cpu_percent.toFixed(2)}%`}</td><td className="p-2"><p className="font-black">{formatBytes(item.memory_bytes)}</p><p className="text-[7px] text-[var(--admin-muted)]">{item.memory_percent == null ? "" : `${item.memory_percent.toFixed(1)}% of limit`}</p></td><td className="p-2">{formatRate(item.network_receive_bytes_per_second)}</td><td className="p-2">{formatRate(item.network_transmit_bytes_per_second)}</td></tr>)}</tbody></table>{!telemetryLoading && !telemetry?.containers.length ? <p className="py-8 text-center text-[10px] text-[var(--admin-muted)]">No container metrics are available yet.</p> : null}</div>
          </div>
        </section>

        {overview ? (
          <section className="grid gap-4 xl:grid-cols-[1.2fr_.8fr]">
            <div className="surface-card p-5">
              <div className="flex items-center justify-between gap-3"><div><p className="text-[9px] font-black uppercase tracking-[.13em] text-[var(--admin-muted)]">Infrastructure allocation</p><h2 className="mt-1 text-lg font-black">Hosting capacity & node heartbeat</h2></div><Server size={18} /></div>
              <div className="mt-4 space-y-3">
                {overview.infrastructure.map((node) => (
                  <article key={node.id} className="rounded-2xl border border-[var(--admin-line)] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div><div className="flex items-center gap-2"><p className="text-sm font-black">{node.name}</p><Status value={node.agent_online ? "online" : "offline"} /></div><p className="mt-1 font-mono text-[9px] text-[var(--admin-muted)]">{node.hostname}{node.public_ip ? ` · ${node.public_ip}` : ""}</p></div>
                      <div className="text-right text-[9px] text-[var(--admin-muted)]"><p>{node.projects} hosted projects</p><p>{node.last_seen_at ? `Heartbeat ${new Date(node.last_seen_at).toLocaleString()}` : "No agent heartbeat"}</p></div>
                    </div>
                    <div className="mt-4 grid gap-4 sm:grid-cols-3">
                      <CapacityBar label="Storage MB" value={node.allocation_percent.storage} used={node.allocated.storage_mb} total={node.capacity.storage_mb} />
                      <CapacityBar label="Memory MB" value={node.allocation_percent.memory} used={node.allocated.memory_mb} total={node.capacity.memory_mb} />
                      <CapacityBar label="CPU millicores" value={node.allocation_percent.cpu} used={node.allocated.cpu_millicores} total={node.capacity.cpu_millicores} />
                    </div>
                  </article>
                ))}
                {!overview.infrastructure.length ? <p className="py-7 text-center text-[10px] text-[var(--admin-muted)]">No hosting nodes registered yet.</p> : null}
              </div>
            </div>

            <div className="surface-card p-5">
              <div className="flex items-center justify-between gap-3"><div><p className="text-[9px] font-black uppercase tracking-[.13em] text-[var(--admin-muted)]">Attention</p><h2 className="mt-1 text-lg font-black">Operational alerts</h2></div><span className="rounded-full bg-[#f5efe0] px-2.5 py-1 text-[9px] font-black">{openAlerts}</span></div>
              <div className="mt-4 space-y-2">
                {overview.alerts.map((alert, index) => <article key={`${alert.title}-${index}`} className={`rounded-xl border p-3 ${alert.severity === "high" ? "border-red-200 bg-red-50" : "border-amber-200 bg-amber-50"}`}><div className="flex gap-2"><AlertTriangle size={14} className={alert.severity === "high" ? "text-red-600" : "text-amber-600"} /><div><p className="text-[10px] font-black">{alert.title}</p><p className="mt-1 text-[9px] leading-4 text-[var(--admin-muted)]">{alert.detail}</p></div></div></article>)}
                {!overview.alerts.length ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-[10px] font-bold text-emerald-700">No owner-level alerts. Current control-plane signals are healthy.</div> : null}
              </div>
              <div className="mt-4 border-t border-[var(--admin-line)] pt-4"><div className="flex items-center justify-between"><p className="text-[10px] font-black">Core operations</p><Status value={overview.core_operations.status || "unknown"} /></div><div className="mt-2 flex flex-wrap gap-2">{Object.entries(overview.core_operations.services || {}).map(([name, state]) => <span key={name} className="rounded-lg border border-[var(--admin-line)] px-2 py-1 text-[9px]"><b>{name}</b> · {state}</span>)}</div></div>
            </div>
          </section>
        ) : null}

        <section className="surface-card p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div><p className="text-[9px] font-black uppercase tracking-[.13em] text-[var(--admin-muted)]">Product access + SSO</p><h2 className="mt-1 text-lg font-black">Organisation product registry</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Assign an IDS product to an organisation. Members inherit the organisation grant and launch the product through its central Ithute identity integration.</p></div><Link href="/ithute-account" className="btn-secondary">Open my app launcher <ExternalLink size={13} /></Link></div>
          <div className="mt-4 grid gap-3 rounded-2xl border border-[var(--admin-line)] bg-[#f8faf9] p-4 md:grid-cols-4 xl:grid-cols-6">
            <label className="md:col-span-2"><span className="text-[9px] font-black uppercase text-[var(--admin-muted)]">Organisation</span><select value={tenantId} onChange={(event) => setTenantId(event.target.value)} className="mt-1 w-full rounded-xl border border-[var(--admin-line)] bg-white px-3 py-2.5 text-[11px]">{registry?.organizations.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label><span className="text-[9px] font-black uppercase text-[var(--admin-muted)]">Product</span><select value={productId} onChange={(event) => setProductId(event.target.value)} className="mt-1 w-full rounded-xl border border-[var(--admin-line)] bg-white px-3 py-2.5 text-[11px]">{registry?.products.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label><span className="text-[9px] font-black uppercase text-[var(--admin-muted)]">Plan</span><input value={plan} onChange={(event) => setPlan(event.target.value)} className="mt-1 w-full rounded-xl border border-[var(--admin-line)] bg-white px-3 py-2.5 text-[11px]" /></label>
            <label><span className="text-[9px] font-black uppercase text-[var(--admin-muted)]">Status</span><select value={grantStatus} onChange={(event) => setGrantStatus(event.target.value)} className="mt-1 w-full rounded-xl border border-[var(--admin-line)] bg-white px-3 py-2.5 text-[11px]"><option value="active">Active</option><option value="demo">Demo</option><option value="suspended">Suspended</option><option value="expired">Expired</option></select></label>
            <button disabled={saving || !tenantId || !productId} onClick={() => void saveAccess()} className="btn-primary self-end"><KeyRound size={14} />{saving ? "Saving…" : "Apply access"}</button>
          </div>
          <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[720px] text-left text-[10px]"><thead><tr className="border-b border-[var(--admin-line)] text-[8px] font-black uppercase tracking-[.1em] text-[var(--admin-muted)]"><th className="p-3">Organisation</th><th className="p-3">Product</th><th className="p-3">Plan</th><th className="p-3">Status</th><th className="p-3">Identity</th><th className="p-3">Updated</th></tr></thead><tbody>{sortedGrants.map((grant) => <tr key={grant.id} className="border-b border-[var(--admin-line)] last:border-0"><td className="p-3 font-black">{grant.organization_name || grant.subject_id}</td><td className="p-3">{grant.product_name}</td><td className="p-3">{grant.plan}</td><td className="p-3"><Status value={grant.status} /></td><td className="p-3">Central Ithute SSO</td><td className="p-3 text-[var(--admin-muted)]">{grant.updated_at ? new Date(grant.updated_at).toLocaleString() : "—"}</td></tr>)}</tbody></table>{!sortedGrants.length ? <p className="py-6 text-center text-[10px] text-[var(--admin-muted)]">No organisation product grants yet.</p> : null}</div>
        </section>

        {overview ? <section className="surface-card p-5"><div><p className="text-[9px] font-black uppercase tracking-[.13em] text-[var(--admin-muted)]">Customers</p><h2 className="mt-1 text-lg font-black">Organisation estate</h2></div><div className="mt-4 overflow-x-auto"><table className="w-full min-w-[850px] text-left text-[10px]"><thead><tr className="border-b border-[var(--admin-line)] text-[8px] font-black uppercase tracking-[.1em] text-[var(--admin-muted)]"><th className="p-3">Organisation</th><th className="p-3">Members</th><th className="p-3">Domains</th><th className="p-3">Mailboxes</th><th className="p-3">Hosted apps</th><th className="p-3">Products</th><th className="p-3">Status</th></tr></thead><tbody>{overview.organizations.map((org) => <tr key={org.id} className="border-b border-[var(--admin-line)] last:border-0"><td className="p-3"><p className="font-black">{org.name}</p><p className="text-[8px] text-[var(--admin-muted)]">{org.slug}</p></td><td className="p-3">{org.members}</td><td className="p-3">{org.domains}</td><td className="p-3">{org.mailboxes}</td><td className="p-3">{org.hosted_projects}</td><td className="p-3"><div className="flex max-w-[360px] flex-wrap gap-1">{org.products.map((item) => <span key={item.id} className="rounded-full bg-[#eef5f2] px-2 py-1 text-[8px] font-bold">{item.name} · {item.plan}</span>)}{!org.products.length ? <span className="text-[var(--admin-muted)]">Control Centre only</span> : null}</div></td><td className="p-3"><Status value={org.status} /></td></tr>)}</tbody></table></div></section> : null}

        {overview ? <section className="grid gap-4 xl:grid-cols-[1.2fr_.8fr]"><div className="surface-card p-5"><div><p className="text-[9px] font-black uppercase tracking-[.13em] text-[var(--admin-muted)]">Product telemetry</p><h2 className="mt-1 text-lg font-black">IDS product health</h2></div><div className="mt-4 grid gap-3 sm:grid-cols-2">{overview.products.map((product) => <article key={product.id} className="rounded-2xl border border-[var(--admin-line)] p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-sm font-black">{product.name}</p><p className="mt-1 text-[8px] text-[var(--admin-muted)]">{product.category} · {product.version || "version not reported"}</p></div><Status value={product.status} /></div><div className="mt-3 grid grid-cols-2 gap-2 text-[9px]"><div className="rounded-xl bg-[#f7faf8] p-2.5"><b>Database</b><br />{product.database?.status || "unknown"}</div><div className="rounded-xl bg-[#f7faf8] p-2.5"><b>Last heartbeat</b><br />{product.last_seen_at ? new Date(product.last_seen_at).toLocaleString() : "not reported"}</div></div>{product.public_url ? <a href={product.public_url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-[9px] font-black text-[var(--admin-pine)]">Open product <ExternalLink size={11} /></a> : null}</article>)}</div></div><div className="surface-card p-5"><div><p className="text-[9px] font-black uppercase tracking-[.13em] text-[var(--admin-muted)]">Audit</p><h2 className="mt-1 text-lg font-black">Recent control activity</h2></div><div className="mt-4 space-y-2">{overview.recent_audit.map((item) => <article key={item.id} className="rounded-xl border border-[var(--admin-line)] p-3"><p className="text-[9px] font-black">{item.action}</p><p className="mt-1 text-[8px] text-[var(--admin-muted)]">{item.resource_type}{item.resource_id ? ` · ${item.resource_id}` : ""}</p><p className="mt-1 text-[8px] text-[var(--admin-muted)]">{item.created_at ? new Date(item.created_at).toLocaleString() : ""}</p></article>)}</div></div></section> : null}

        <p className="pb-2 text-center text-[8px] uppercase tracking-[.12em] text-[var(--admin-muted)]"><HardDrive size={10} className="mr-1 inline" />Live percentages are physical VPS utilisation; package allocation remains a separate sellable-capacity boundary.</p>
      </div>
    </ControlShell>
  );
}