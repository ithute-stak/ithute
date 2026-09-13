"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Boxes, CheckCircle2, Cpu, ExternalLink, Globe2, HardDrive, Plus, RefreshCw, Server, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";
import { PageHeader } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Me = { email: string; is_platform_owner: boolean };
type Membership = { tenant_id: string; tenant_name: string; role: string; status: string };
type Domain = { id: string; ascii_name: string; status: string; ownership_verified_at?: string | null };
type HostingSummary = {
  package: {
    code: string;
    name: string;
    hosted_projects: number;
    hosting_storage_mb: number;
    memory_mb_per_project: number;
    cpu_millicores_per_project: number;
    pids_per_project: number;
  };
  usage: { hosted_projects: number; hosting_storage_bytes: number };
  rules_version: string;
};
type Project = {
  id: string;
  name: string;
  slug: string;
  hostname?: string | null;
  runtime: string;
  source_repository?: string | null;
  source_branch: string;
  storage_mb: number;
  memory_mb: number;
  cpu_millicores: number;
  pid_limit: number;
  status: string;
  rules_version: string;
};
type Rules = { version: string; title: string; service_type: string; allowed_runtimes: string[]; rules: string[] };

async function api(path: string, init?: RequestInit) {
  const options: RequestInit = { credentials: "include", ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } };
  let response = await fetch(`${API}${path}`, options);
  if (response.status === 401) {
    const refresh = await fetch(`${API}/auth/refresh`, { method: "POST", credentials: "include" });
    if (refresh.ok) response = await fetch(`${API}${path}`, options);
  }
  return response;
}

async function errorText(response: Response, fallback: string) {
  const body = await response.json().catch(() => ({}));
  return typeof body.detail === "string" ? body.detail : fallback;
}

export default function HostingPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [contexts, setContexts] = useState<Membership[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [summary, setSummary] = useState<HostingSummary | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [domains, setDomains] = useState<Domain[]>([]);
  const [rules, setRules] = useState<Rules | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const selected = useMemo(() => contexts.find((row) => row.tenant_id === tenantId), [contexts, tenantId]);
  const canManage = Boolean(me?.is_platform_owner || selected?.role === "tenant_admin");
  const verifiedDomains = domains.filter((domain) => domain.status === "verified" && domain.ownership_verified_at);

  async function loadTenant(id: string) {
    if (!id) return;
    setLoading(true);
    setError("");
    const [summaryResponse, projectsResponse, domainsResponse] = await Promise.all([
      api(`/tenants/${id}/hosting/summary`),
      api(`/tenants/${id}/hosting/projects`),
      api(`/tenants/${id}/domains?limit=200`),
    ]);
    if (!summaryResponse.ok) {
      setSummary(null);
      setProjects([]);
      setError(await errorText(summaryResponse, "This organization does not currently have an application-hosting entitlement."));
      setLoading(false);
      return;
    }
    setSummary(await summaryResponse.json());
    setProjects(projectsResponse.ok ? (await projectsResponse.json()).items || [] : []);
    setDomains(domainsResponse.ok ? (await domainsResponse.json()).items || [] : []);
    setLoading(false);
  }

  useEffect(() => {
    void (async () => {
      const meResponse = await api("/auth/me");
      if (meResponse.status === 401) { router.replace("/login"); return; }
      if (!meResponse.ok) return;
      const current: Me = await meResponse.json();
      setMe(current);
      const rulesResponse = await api("/hosting/rules");
      if (rulesResponse.ok) setRules(await rulesResponse.json());

      let rows: Membership[] = [];
      if (current.is_platform_owner) {
        const response = await api("/tenants");
        if (response.ok) rows = (await response.json()).map((tenant: { id: string; name: string; status: string }) => ({ tenant_id: tenant.id, tenant_name: tenant.name, role: "platform_owner", status: tenant.status }));
      } else {
        const response = await api("/me/memberships");
        if (response.ok) rows = await response.json();
      }
      setContexts(rows);
      const remembered = window.localStorage.getItem("mailbox_dns_tenant");
      const initial = rows.find((row) => row.tenant_id === remembered)?.tenant_id || rows[0]?.tenant_id || "";
      setTenantId(initial);
    })();
  }, [router]);

  useEffect(() => {
    if (!tenantId) return;
    window.localStorage.setItem("mailbox_dns_tenant", tenantId);
    void loadTenant(tenantId);
  }, [tenantId]);

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tenantId) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setSaving(true);
    setError("");
    setMessage("");
    const domainId = String(data.get("domain_id") || "");
    const payload = {
      name: String(data.get("name") || ""),
      slug: String(data.get("slug") || "") || null,
      runtime: String(data.get("runtime") || "static"),
      source_repository: String(data.get("source_repository") || "") || null,
      source_branch: String(data.get("source_branch") || "main"),
      domain_id: domainId || null,
      hostname: String(data.get("hostname") || "") || null,
      container_port: Number(data.get("container_port") || 8080),
      health_path: String(data.get("health_path") || "/"),
      storage_mb: Math.round(Number(data.get("storage_gb") || 1) * 1024),
      memory_mb: Number(data.get("memory_mb") || 512),
      cpu_millicores: Number(data.get("cpu_millicores") || 500),
      pid_limit: Number(data.get("pid_limit") || 128),
      accept_hosting_rules: data.get("accept_rules") === "on",
    };
    const response = await api(`/tenants/${tenantId}/hosting/projects`, { method: "POST", body: JSON.stringify(payload) });
    if (!response.ok) {
      setError(await errorText(response, "Unable to create hosted project."));
      setSaving(false);
      return;
    }
    form.reset();
    setShowCreate(false);
    setMessage("Hosted project allocated successfully. Its CPU, RAM, storage and process limits are now reserved on the shared hosting node.");
    await loadTenant(tenantId);
    setSaving(false);
  }

  async function setStatus(project: Project, status: "configured" | "suspended") {
    const response = await api(`/tenants/${tenantId}/hosting/projects/${project.id}`, { method: "PATCH", body: JSON.stringify({ status }) });
    if (!response.ok) { setError(await errorText(response, "Unable to change project status.")); return; }
    setMessage(status === "suspended" ? `${project.name} is suspended.` : `${project.name} is enabled for hosting.`);
    await loadTenant(tenantId);
  }

  const usedStorageMb = summary ? Math.round((summary.usage.hosting_storage_bytes || 0) / 1024 / 1024) : 0;

  return <ControlShell title="Application hosting" subtitle="Managed shared hosting for websites and simple business systems" userEmail={me?.email}>
    <div className="space-y-5">
      <PageHeader eyebrow="Ithute application hosting" title="Hosted projects" description="Run customer websites and simple systems on shared Ithute infrastructure with package-enforced storage, RAM, CPU and process limits. This is managed application hosting—not customer root VPS access." />

      <section className="surface-card p-4 sm:p-5">
        <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-[10px] font-black uppercase tracking-[.1em] text-[var(--admin-muted)]">Organization</p><select className="input mt-1 min-w-72" value={tenantId} onChange={(event) => setTenantId(event.target.value)}>{contexts.map((row) => <option key={row.tenant_id} value={row.tenant_id}>{row.tenant_name}</option>)}</select></div><div className="flex gap-2"><button className="btn-secondary" onClick={() => void loadTenant(tenantId)}><RefreshCw size={14}/>Refresh</button>{canManage ? <button className="btn-primary" onClick={() => setShowCreate((value) => !value)}><Plus size={14}/>New hosted project</button> : null}</div></div>
      </section>

      {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}

      {summary ? <section className="grid gap-3 md:grid-cols-4"><article className="surface-card p-4"><Boxes size={17} className="text-[#285b55]"/><p className="mt-2 text-xl font-black">{summary.usage.hosted_projects} / {summary.package.hosted_projects}</p><p className="text-[10px] text-[var(--admin-muted)]">Hosted projects</p></article><article className="surface-card p-4"><HardDrive size={17} className="text-[#285b55]"/><p className="mt-2 text-xl font-black">{(usedStorageMb / 1024).toFixed(1)} / {(summary.package.hosting_storage_mb / 1024).toFixed(1)} GB</p><p className="text-[10px] text-[var(--admin-muted)]">Allocated app storage</p></article><article className="surface-card p-4"><Server size={17} className="text-[#285b55]"/><p className="mt-2 text-xl font-black">{summary.package.memory_mb_per_project} MB</p><p className="text-[10px] text-[var(--admin-muted)]">RAM ceiling / project</p></article><article className="surface-card p-4"><Cpu size={17} className="text-[#285b55]"/><p className="mt-2 text-xl font-black">{(summary.package.cpu_millicores_per_project / 1000).toFixed(2)} CPU</p><p className="text-[10px] text-[var(--admin-muted)]">CPU ceiling / project</p></article></section> : null}

      {showCreate && summary ? <form className="surface-card p-5" onSubmit={createProject}><div className="flex items-start justify-between gap-4"><div><h2 className="text-sm font-black">Allocate a hosted project</h2><p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">The scheduler reserves capacity on a system-owner approved hosting node. A project cannot exceed its package limits.</p></div><a className="text-xs font-black text-[#285b55]" href="/docs#hosting" target="_blank">Rules <ExternalLink size={12} className="inline"/></a></div><div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3"><label><span className="eyebrow-label">Project name</span><input className="input mt-1" name="name" placeholder="Company website" required/></label><label><span className="eyebrow-label">Slug</span><input className="input mt-1" name="slug" placeholder="company-website"/></label><label><span className="eyebrow-label">Runtime</span><select className="input mt-1" name="runtime">{(rules?.allowed_runtimes || ["static","node","python","dotnet"]).map((runtime) => <option key={runtime} value={runtime}>{runtime}</option>)}</select></label><label><span className="eyebrow-label">Source repository</span><input className="input mt-1" name="source_repository" type="url" placeholder="https://github.com/company/site"/></label><label><span className="eyebrow-label">Source branch</span><input className="input mt-1" name="source_branch" defaultValue="main"/></label><label><span className="eyebrow-label">Verified domain</span><select className="input mt-1" name="domain_id"><option value="">No public hostname yet</option>{verifiedDomains.map((domain) => <option key={domain.id} value={domain.id}>{domain.ascii_name}</option>)}</select></label><label><span className="eyebrow-label">Hostname</span><input className="input mt-1" name="hostname" placeholder="www.example.co.ls"/></label><label><span className="eyebrow-label">App port</span><input className="input mt-1" name="container_port" type="number" min="1024" max="65535" defaultValue="8080"/></label><label><span className="eyebrow-label">Health path</span><input className="input mt-1" name="health_path" defaultValue="/"/></label><label><span className="eyebrow-label">Storage (GB)</span><input className="input mt-1" name="storage_gb" type="number" min="0.125" max={summary.package.hosting_storage_mb / 1024} step="0.125" defaultValue="1"/></label><label><span className="eyebrow-label">RAM (MB)</span><input className="input mt-1" name="memory_mb" type="number" min="128" max={summary.package.memory_mb_per_project} step="128" defaultValue={Math.min(512, summary.package.memory_mb_per_project)}/></label><label><span className="eyebrow-label">CPU (millicores)</span><input className="input mt-1" name="cpu_millicores" type="number" min="100" max={summary.package.cpu_millicores_per_project} step="100" defaultValue={Math.min(500, summary.package.cpu_millicores_per_project)}/></label><label><span className="eyebrow-label">Process limit</span><input className="input mt-1" name="pid_limit" type="number" min="32" max={summary.package.pids_per_project} step="16" defaultValue={Math.min(128, summary.package.pids_per_project)}/></label></div><label className="mt-5 flex items-start gap-3 rounded-2xl border border-[#dce5e0] bg-[#f6f9f7] p-4 text-xs leading-5"><input className="mt-1" type="checkbox" name="accept_rules" required/><span><b>I accept Hosting Rules v{rules?.version || summary.rules_version} for this project.</b> No root/SSH/Docker-socket access, no privileged workloads, no arbitrary public ports, no spam/mining/malware/open proxies, and resources remain inside the package limits.</span></label><button className="btn-primary mt-5" disabled={saving}><ShieldCheck size={14}/>{saving ? "Allocating…" : "Accept rules & allocate project"}</button></form> : null}

      <section className="surface-card overflow-hidden"><div className="border-b border-[#e4e9e6] p-4"><h2 className="text-sm font-black">Projects on shared hosting</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Each allocation reserves sellable node capacity even while suspended, so resource accounting remains predictable.</p></div><div className="grid gap-3 p-4 lg:grid-cols-2">{projects.map((project) => <article key={project.id} className="rounded-2xl border border-[#dce5e0] bg-white p-4"><div className="flex items-start justify-between gap-3"><div><h3 className="text-sm font-black">{project.name}</h3><p className="mt-1 text-[9px] font-bold uppercase tracking-[.08em] text-[var(--admin-muted)]">{project.runtime} · {project.status} · rules {project.rules_version}</p></div><span className={`rounded-full px-2 py-1 text-[9px] font-black ${project.status === "suspended" ? "bg-amber-50 text-amber-700" : "bg-emerald-50 text-emerald-700"}`}>{project.status}</span></div>{project.hostname ? <p className="mt-3 flex items-center gap-2 text-xs"><Globe2 size={14}/>{project.hostname}</p> : <p className="mt-3 text-xs text-[var(--admin-muted)]">No public hostname assigned yet.</p>}<div className="mt-3 grid grid-cols-4 gap-2 text-[9px]"><div className="rounded-xl bg-[#f4f7f5] p-2"><b>{(project.storage_mb / 1024).toFixed(1)} GB</b><br/>storage</div><div className="rounded-xl bg-[#f4f7f5] p-2"><b>{project.memory_mb} MB</b><br/>RAM</div><div className="rounded-xl bg-[#f4f7f5] p-2"><b>{(project.cpu_millicores / 1000).toFixed(2)}</b><br/>CPU</div><div className="rounded-xl bg-[#f4f7f5] p-2"><b>{project.pid_limit}</b><br/>PIDs</div></div>{project.source_repository ? <p className="mt-3 truncate text-[10px] text-[var(--admin-muted)]">Source: {project.source_repository} · {project.source_branch}</p> : null}{canManage ? <div className="mt-4"><button className="btn-secondary" onClick={() => void setStatus(project, project.status === "suspended" ? "configured" : "suspended")}>{project.status === "suspended" ? "Enable" : "Suspend"}</button></div> : null}</article>)}{!loading && !projects.length ? <div className="rounded-2xl border border-dashed border-[#d6dfda] p-6 text-center text-xs text-[var(--admin-muted)]">No hosted projects yet. Create one after the system owner has registered sellable hosting-node capacity.</div> : null}</div></section>

      <section className="rounded-3xl bg-[#123a38] p-6 text-white"><div className="flex items-start gap-4"><ShieldCheck size={22} className="mt-1 shrink-0 text-[#f1de8b]"/><div><h2 className="text-lg font-black">Hosting is isolated by policy and quota.</h2><p className="mt-2 max-w-3xl text-xs leading-6 text-white/65">Customer projects never receive host SSH, root access or Docker control. Public traffic must pass through Ithute ingress, builds must happen through an approved isolated build pipeline, and every project is bounded by package CPU, memory, storage and PID allocations.</p><a href="/docs#hosting" className="mt-3 inline-flex text-xs font-black text-[#f1de8b]">Read the complete hosting rules →</a></div></div></section>
    </div>
  </ControlShell>;
}
