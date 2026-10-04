"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, Database, HardDrive, Mail, RefreshCw, Server, ShieldCheck, Wrench } from "lucide-react";
import { useRouter } from "next/navigation";

import { ControlShell } from "@/components/control-shell";
import { PageHeader } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Me = { email: string; is_platform_owner: boolean };
type Capacity = {
  allocatable_storage_mb: number;
  allocated_storage_mb: number;
  available_storage_mb: number;
  allocatable_memory_mb: number;
  allocated_memory_mb: number;
  available_memory_mb: number;
  allocatable_cpu_millicores: number;
  allocated_cpu_millicores: number;
  available_cpu_millicores: number;
};
type InfrastructureServer = {
  id: string;
  name: string;
  hostname: string;
  public_ip?: string | null;
  region: string;
  provider?: string | null;
  roles: string[];
  status: string;
  health: string;
  notes?: string | null;
  workloads: { mailboxes: number; projects: number; databases: number };
  mail: {
    linked: boolean;
    node_id?: string | null;
    online: boolean;
    ready: boolean;
    last_heartbeat_at?: string | null;
    agent_version?: string | null;
    total_storage_bytes?: number | null;
    used_storage_bytes?: number | null;
    free_storage_bytes?: number | null;
    smtp_ready: boolean;
    imap_ready: boolean;
    tls_ready: boolean;
    backup_ready: boolean;
  };
  hosting: {
    linked: boolean;
    node_id?: string | null;
    online: boolean;
    accepts_new_projects: boolean;
    agent_version?: string | null;
    last_heartbeat_at?: string | null;
    capacity?: Capacity | null;
  };
  configuration_required: string[];
};

const ROLE_LABELS: Record<string, string> = {
  mail: "Mail",
  application: "Applications",
  database: "Database",
  storage: "Storage",
  build: "Build",
  backup: "Backup",
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

async function detail(response: Response, fallback: string) {
  const body = await response.json().catch(() => ({}));
  return typeof body.detail === "string" ? body.detail : fallback;
}

function bytes(value?: number | null) {
  if (value === null || value === undefined) return "Awaiting agent";
  if (value >= 1024 ** 4) return `${(value / 1024 ** 4).toFixed(1)} TB`;
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  return `${Math.round(value / 1024 ** 2)} MB`;
}

function gb(value?: number | null) {
  if (value === null || value === undefined) return "—";
  return `${(value / 1024).toFixed(value % 1024 ? 1 : 0)} GB`;
}

function heartbeat(value?: string | null) {
  if (!value) return "No heartbeat yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function healthClass(value: string) {
  if (value === "healthy") return "bg-emerald-50 text-emerald-700";
  if (value === "registered") return "bg-blue-50 text-blue-700";
  if (value === "maintenance" || value === "configuration_required" || value === "degraded") return "bg-amber-50 text-amber-800";
  return "bg-red-50 text-red-700";
}

export default function InfrastructureServersPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [servers, setServers] = useState<InfrastructureServer[]>([]);
  const [roles, setRoles] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const healthy = useMemo(() => servers.filter((server) => server.health === "healthy").length, [servers]);
  const configured = useMemo(() => servers.filter((server) => !server.configuration_required.length).length, [servers]);
  const workloads = useMemo(() => servers.reduce((sum, server) => sum + server.workloads.mailboxes + server.workloads.projects + server.workloads.databases, 0), [servers]);

  async function load() {
    setLoading(true);
    setError("");
    const response = await api("/platform/infrastructure/servers");
    if (!response.ok) {
      setError(await detail(response, "Unable to load infrastructure servers."));
      setLoading(false);
      return;
    }
    const payload = await response.json();
    setServers(payload.items || []);
    setRoles(payload.roles || []);
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
  }, [router]);

  async function createServer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true); setMessage(""); setError("");
    const form = event.currentTarget;
    const data = new FormData(form);
    const selectedRoles = roles.filter((role) => data.get(`role_${role}`) === "on");
    const response = await api("/platform/infrastructure/servers", {
      method: "POST",
      body: JSON.stringify({
        name: data.get("name"),
        hostname: data.get("hostname"),
        public_ip: data.get("public_ip") || null,
        region: data.get("region") || "lesotho",
        provider: data.get("provider") || null,
        roles: selectedRoles.length ? selectedRoles : ["application"],
        notes: data.get("notes") || null,
      }),
    });
    if (!response.ok) { setError(await detail(response, "Unable to register server.")); setSaving(false); return; }
    form.reset();
    setMessage("Server registered in the central infrastructure inventory.");
    await load();
    setSaving(false);
  }

  async function importExisting() {
    setSaving(true); setMessage(""); setError("");
    const response = await api("/platform/infrastructure/servers/import-existing", { method: "POST" });
    if (!response.ok) { setError(await detail(response, "Unable to import existing nodes.")); setSaving(false); return; }
    const body = await response.json();
    setMessage(`Infrastructure inventory synchronized: ${body.imported} server(s) imported and ${body.linked} workload node(s) linked.`);
    await load();
    setSaving(false);
  }

  async function updateRoles(server: InfrastructureServer, role: string) {
    const next = server.roles.includes(role) ? server.roles.filter((item) => item !== role) : [...server.roles, role];
    if (!next.length) return;
    setMessage(""); setError("");
    const response = await api(`/platform/infrastructure/servers/${server.id}`, {
      method: "PATCH",
      body: JSON.stringify({ roles: next }),
    });
    if (!response.ok) { setError(await detail(response, "Unable to update server roles.")); return; }
    await load();
  }

  return <ControlShell title="Infrastructure servers" subtitle="One physical-server inventory across mail, applications, databases, storage, build and backup" userEmail={me?.email}>
    <div className="space-y-5">
      <PageHeader
        eyebrow="Infrastructure control plane"
        title="Servers & VPS nodes"
        description="Register each physical or virtual server once. Ithute links mail and hosting workload nodes underneath it, so the same VPS can be monitored centrally without pretending that mail, application and database workloads are the same service."
      />

      {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="surface-card p-4"><Server size={18} className="text-[#285b55]"/><p className="mt-3 text-2xl font-black">{servers.length}</p><p className="text-[10px] font-bold text-[var(--admin-muted)]">Registered servers</p></div>
        <div className="surface-card p-4"><ShieldCheck size={18} className="text-emerald-600"/><p className="mt-3 text-2xl font-black">{healthy}</p><p className="text-[10px] font-bold text-[var(--admin-muted)]">Healthy</p></div>
        <div className="surface-card p-4"><Wrench size={18} className="text-amber-600"/><p className="mt-3 text-2xl font-black">{configured}/{servers.length}</p><p className="text-[10px] font-bold text-[var(--admin-muted)]">Role links configured</p></div>
        <div className="surface-card p-4"><Activity size={18} className="text-blue-600"/><p className="mt-3 text-2xl font-black">{workloads}</p><p className="text-[10px] font-bold text-[var(--admin-muted)]">Managed workloads</p></div>
      </section>

      <section className="surface-card p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><h2 className="text-sm font-black">Existing Ithute infrastructure</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Import current Mail Nodes and Hosting Nodes into this central server inventory. Existing workload configuration is not deleted or recreated.</p></div>
          <button className="btn-secondary" disabled={saving} onClick={() => void importExisting()}><RefreshCw size={13}/>Synchronize existing nodes</button>
        </div>
      </section>

      <section className="surface-card p-4 sm:p-5">
        <div className="mb-4"><h2 className="text-sm font-black">Register physical server / VPS</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">This records the machine itself. Workload-specific agents and capacity remain controlled by their dedicated Mail Nodes and Hosting Nodes modules.</p></div>
        <form onSubmit={createServer} className="grid gap-3 lg:grid-cols-2">
          <input name="name" required minLength={2} maxLength={120} className="admin-input" placeholder="Server name, e.g. Maseru VPS 01"/>
          <input name="hostname" required className="admin-input" placeholder="Hostname, e.g. vps01.ithute.co.ls"/>
          <input name="public_ip" className="admin-input" placeholder="Public IP (optional)"/>
          <input name="provider" className="admin-input" placeholder="Provider, e.g. DataBank / Oracle"/>
          <input name="region" defaultValue="lesotho" className="admin-input" placeholder="Region"/>
          <input name="notes" className="admin-input" placeholder="Notes (optional)"/>
          <div className="lg:col-span-2">
            <p className="mb-2 text-[10px] font-black uppercase tracking-[.1em] text-[var(--admin-muted)]">Server roles</p>
            <div className="flex flex-wrap gap-2">{roles.map((role) => <label key={role} className="flex items-center gap-2 rounded-xl border border-[#dce5e0] bg-white px-3 py-2 text-[10px] font-bold"><input name={`role_${role}`} type="checkbox" defaultChecked={role === "application"}/>{ROLE_LABELS[role] || role}</label>)}</div>
          </div>
          <button disabled={saving} className="btn-primary lg:col-span-2"><Server size={14}/>{saving ? "Saving…" : "Register server"}</button>
        </form>
      </section>

      <section className="surface-card p-4 sm:p-5">
        <div className="flex items-center justify-between gap-3"><div><h2 className="text-sm font-black">Infrastructure inventory</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Health is derived from the linked workload agents and readiness checks.</p></div><button className="icon-button" onClick={() => void load()} aria-label="Refresh servers"><RefreshCw size={15}/></button></div>
        {loading ? <p className="mt-6 text-xs text-[var(--admin-muted)]">Loading servers…</p> : <div className="mt-5 grid gap-4 2xl:grid-cols-2">
          {servers.map((server) => <article key={server.id} className="rounded-2xl border border-[#dce5e0] bg-white p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[#edf4f1] text-[#285b55]"><Server size={19}/></span><div className="min-w-0"><h3 className="truncate text-sm font-black">{server.name}</h3><p className="truncate text-[9px] text-[var(--admin-muted)]">{server.hostname}{server.public_ip ? ` · ${server.public_ip}` : ""}</p><p className="mt-0.5 text-[9px] text-[var(--admin-muted)]">{server.provider || "Provider not set"} · {server.region}</p></div></div>
              <span className={`rounded-full px-2.5 py-1 text-[9px] font-black ${healthClass(server.health)}`}>{server.health.replaceAll("_", " ")}</span>
            </div>

            <div className="mt-4 flex flex-wrap gap-1.5">{roles.map((role) => <button key={role} type="button" onClick={() => void updateRoles(server, role)} className={`rounded-full border px-2.5 py-1 text-[9px] font-black transition ${server.roles.includes(role) ? "border-[#285b55] bg-[#285b55] text-white" : "border-[#dce5e0] bg-white text-[#718078] hover:border-[#a9c1b6]"}`}>{ROLE_LABELS[role] || role}</button>)}</div>

            {server.configuration_required.length ? <div className="mt-3 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-[10px] font-semibold text-amber-800"><AlertTriangle size={14} className="mt-0.5 shrink-0"/>Role selected but workload setup is still required for: {server.configuration_required.join(", ")}.</div> : null}

            <div className="mt-4 grid grid-cols-3 gap-2 text-center text-[9px]"><div className="rounded-xl bg-[#f5f8f6] p-2.5"><b className="text-sm">{server.workloads.mailboxes}</b><br/>mailboxes</div><div className="rounded-xl bg-[#f5f8f6] p-2.5"><b className="text-sm">{server.workloads.projects}</b><br/>apps</div><div className="rounded-xl bg-[#f5f8f6] p-2.5"><b className="text-sm">{server.workloads.databases}</b><br/>databases</div></div>

            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              <div className="rounded-xl border border-[#e4e9e6] p-3">
                <div className="flex items-center justify-between gap-2"><p className="flex items-center gap-2 text-[10px] font-black"><Mail size={13}/>Mail role</p><span className={`h-2 w-2 rounded-full ${server.mail.online && server.mail.ready ? "bg-emerald-500" : "bg-slate-300"}`}/></div>
                {server.mail.linked ? <><p className="mt-2 text-[9px] text-[var(--admin-muted)]">{server.mail.online ? "Agent online" : "Agent offline"} · {server.mail.ready ? "SMTP/IMAP/TLS ready" : "Readiness incomplete"}</p><p className="mt-1 text-[9px] text-[var(--admin-muted)]">{heartbeat(server.mail.last_heartbeat_at)}</p><div className="mt-2 flex items-center gap-2 text-[9px]"><HardDrive size={12}/><b>{bytes(server.mail.used_storage_bytes)}</b> used / {bytes(server.mail.total_storage_bytes)}</div><Link href="/mail-nodes" className="mt-3 inline-flex text-[9px] font-black text-[#285b55] hover:underline">Open Mail Nodes →</Link></> : <p className="mt-2 text-[9px] text-[var(--admin-muted)]">No Mail Node is linked to this machine yet.</p>}
              </div>
              <div className="rounded-xl border border-[#e4e9e6] p-3">
                <div className="flex items-center justify-between gap-2"><p className="flex items-center gap-2 text-[10px] font-black"><Database size={13}/>Hosting & databases</p><span className={`h-2 w-2 rounded-full ${server.hosting.online ? "bg-emerald-500" : "bg-slate-300"}`}/></div>
                {server.hosting.linked ? <><p className="mt-2 text-[9px] text-[var(--admin-muted)]">{server.hosting.online ? "Hosting agent online" : "Hosting agent offline"} · {server.hosting.accepts_new_projects ? "Accepting projects" : "Not accepting projects"}</p><p className="mt-1 text-[9px] text-[var(--admin-muted)]">{heartbeat(server.hosting.last_heartbeat_at)}</p>{server.hosting.capacity ? <div className="mt-2 grid grid-cols-3 gap-1 text-[8px]"><span><b>{gb(server.hosting.capacity.available_storage_mb)}</b><br/>disk free</span><span><b>{server.hosting.capacity.available_memory_mb} MB</b><br/>RAM free</span><span><b>{(server.hosting.capacity.available_cpu_millicores / 1000).toFixed(1)}</b><br/>CPU free</span></div> : null}<Link href="/hosting-nodes" className="mt-3 inline-flex text-[9px] font-black text-[#285b55] hover:underline">Open Hosting Nodes →</Link></> : <p className="mt-2 text-[9px] text-[var(--admin-muted)]">No Hosting Node is linked to this machine yet.</p>}
              </div>
            </div>
          </article>)}
          {!servers.length ? <p className="text-xs text-[var(--admin-muted)]">No servers registered yet. Synchronize existing nodes or register a VPS above.</p> : null}
        </div>}
      </section>
    </div>
  </ControlShell>;
}
