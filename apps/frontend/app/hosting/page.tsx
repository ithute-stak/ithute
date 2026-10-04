"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Boxes, Cpu, ExternalLink, Globe2, HardDrive, Plus, RefreshCw, Server, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";
import { PageHeader } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Me = { email: string; is_platform_owner: boolean };
type ServiceContext = {
  tenant_id: string;
  tenant_name: string;
  role: string;
  status: string;
  access_kind?: "membership" | "reseller_customer" | "platform_owner";
  reseller_tenant_id?: string | null;
  permissions?: string[];
};
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
  node_id?: string | null;
  failover_policy: "manual" | "stateless_auto";
  rules_version: string;
};
type FailoverAttempt = {
  id: string;
  source_node_id: string;
  target_node_id?: string | null;
  deployment_id?: string | null;
  status: string;
  reason?: string | null;
  edge_status?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
};
type Rules = { version: string; title: string; service_type: string; allowed_runtimes: string[]; rules: string[] };
type ProvisioningWorkflow = {
  id: string;
  status: string;
  failure_message?: string | null;
  stages: Record<string, { status: string; hostname?: string | null; application_id?: string | null }>;
};
type HostingNode = { id: string; name: string; hostname: string; status: string; accepts_new_projects: boolean; available: { storage_mb: number; memory_mb: number; cpu_millicores: number } };

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
  const [contexts, setContexts] = useState<ServiceContext[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [summary, setSummary] = useState<HostingSummary | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [domains, setDomains] = useState<Domain[]>([]);
  const [rules, setRules] = useState<Rules | null>(null);
  const [hostingNodes, setHostingNodes] = useState<HostingNode[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [provisioning, setProvisioning] = useState<Record<string, ProvisioningWorkflow | null>>({});
  const [databaseEngine, setDatabaseEngine] = useState<Record<string, string>>({});
  const [failovers, setFailovers] = useState<Record<string, FailoverAttempt[]>>({});
  const [relocationTarget, setRelocationTarget] = useState<Record<string, string>>({});

  const selected = useMemo(() => contexts.find((row) => row.tenant_id === tenantId), [contexts, tenantId]);
  const canManage = Boolean(
    me?.is_platform_owner
    || selected?.role === "tenant_admin"
    || selected?.role === "reseller_admin"
    || selected?.permissions?.includes("hosting.manage")
  );
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
    const projectRows: Project[] = projectsResponse.ok ? (await projectsResponse.json()).items || [] : [];
    setProjects(projectRows);
    setDomains(domainsResponse.ok ? (await domainsResponse.json()).items || [] : []);
    const workflowRows = await Promise.all(projectRows.map(async (project) => {
      const [workflowResponse, failoverResponse] = await Promise.all([
        api(`/tenants/${id}/hosting/projects/${project.id}/provisioning`),
        api(`/tenants/${id}/hosting/projects/${project.id}/failovers`),
      ]);
      const workflowBody = workflowResponse.ok ? await workflowResponse.json() : { workflow: null };
      const failoverBody = failoverResponse.ok ? await failoverResponse.json() : { items: [] };
      return { projectId: project.id, workflow: workflowBody.workflow || null, failovers: failoverBody.items || [] };
    }));
    setProvisioning(Object.fromEntries(workflowRows.map((row) => [row.projectId, row.workflow])));
    setFailovers(Object.fromEntries(workflowRows.map((row) => [row.projectId, row.failovers])));
    setLoading(false);
  }

  useEffect(() => {
    void (async () => {
      const meResponse = await api("/auth/me");
      if (meResponse.status === 401) { router.replace("/login"); return; }
      if (!meResponse.ok) return;
      const current: Me = await meResponse.json();
      setMe(current);
      const [rulesResponse, contextsResponse] = await Promise.all([
        api("/hosting/rules"),
        api("/me/service-contexts"),
      ]);
      if (rulesResponse.ok) setRules(await rulesResponse.json());
      if (current.is_platform_owner) {
        const nodeResponse = await api("/platform/hosting/nodes");
        if (nodeResponse.ok) setHostingNodes((await nodeResponse.json()).items || []);
      }
      const rows: ServiceContext[] = contextsResponse.ok ? (await contextsResponse.json()).items || [] : [];
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

  useEffect(() => {
    if (!tenantId) return;
    const active = Object.values(provisioning).some((workflow) =>
      workflow && ["queued", "provisioning", "building", "deploying", "edge_pending"].includes(workflow.status)
    );
    if (!active) return;
    const timer = window.setInterval(() => {
      void (async () => {
        const rows = await Promise.all(projects.map(async (project) => {
          const response = await api(`/tenants/${tenantId}/hosting/projects/${project.id}/provisioning`);
          const body = response.ok ? await response.json() : { workflow: null };
          return [project.id, body.workflow || null] as const;
        }));
        setProvisioning(Object.fromEntries(rows));
      })();
    }, 10000);
    return () => window.clearInterval(timer);
  }, [tenantId, projects, provisioning]);

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
      node_id: me?.is_platform_owner && String(data.get("node_id") || "") ? String(data.get("node_id")) : null,
    };
    const response = await api(`/tenants/${tenantId}/hosting/projects`, { method: "POST", body: JSON.stringify(payload) });
    if (!response.ok) {
      setError(await errorText(response, "Unable to create hosted project."));
      setSaving(false);
      return;
    }
    form.reset();
    setShowCreate(false);
    setMessage("Hosted project allocated successfully. Ithute selected a healthy hosting node and reserved its CPU, RAM, storage and process capacity.");
    await loadTenant(tenantId);
    setSaving(false);
  }

  async function provisionProject(project: Project) {
    if (!tenantId) return;
    setSaving(true);
    setError("");
    setMessage("");
    const engine = databaseEngine[project.id] || "";
    const response = await api(`/tenants/${tenantId}/hosting/projects/${project.id}/provision`, {
      method: "POST",
      body: JSON.stringify({
        database_engine: engine || null,
        database_name: engine ? `${project.slug}_db` : null,
        database_storage_mb: 1024,
        environment: {},
        create_edge_application: true,
      }),
    });
    if (!response.ok) {
      setError(await errorText(response, "Unable to start automatic provisioning."));
      setSaving(false);
      return;
    }
    const workflow = await response.json();
    setProvisioning((current) => ({ ...current, [project.id]: workflow }));
    setMessage(`Automatic provisioning started for ${project.name}. Ithute will build, provision dependencies and track deployment readiness.`);
    setSaving(false);
  }

  async function setFailoverPolicy(project: Project, policy: "manual" | "stateless_auto") {
    setError(""); setMessage("");
    const response = await api(`/tenants/${tenantId}/hosting/projects/${project.id}/failover-policy`, {
      method: "PUT",
      body: JSON.stringify({
        policy,
        confirm_local_data_disposable: policy === "stateless_auto",
      }),
    });
    if (!response.ok) { setError(await errorText(response, "Unable to update failover policy.")); return; }
    setMessage(policy === "stateless_auto"
      ? `${project.name} can now be automatically relocated after a sustained node failure. Its local /data is treated as disposable.`
      : `${project.name} now requires manual recovery; Ithute will not discard its local /data automatically.`);
    await loadTenant(tenantId);
  }

  async function relocateProject(project: Project) {
    setError(""); setMessage("");
    const target = relocationTarget[project.id] || "";
    const response = await api(`/tenants/${tenantId}/hosting/projects/${project.id}/relocate`, {
      method: "POST",
      body: JSON.stringify({ target_node_id: target || null }),
    });
    if (!response.ok) { setError(await errorText(response, "Unable to queue project relocation.")); return; }
    setMessage(`Replacement deployment queued for ${project.name}. Ithute will switch traffic only after the new instance and edge route are healthy.`);
    await loadTenant(tenantId);
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
        <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-[10px] font-black uppercase tracking-[.1em] text-[var(--admin-muted)]">Organization / managed customer</p><select className="input mt-1 min-w-72" value={tenantId} onChange={(event) => setTenantId(event.target.value)}>{contexts.map((row) => <option key={row.tenant_id} value={row.tenant_id}>{row.tenant_name}{row.access_kind === "reseller_customer" ? " · reseller customer" : ""}</option>)}</select>{selected?.access_kind === "reseller_customer" ? <p className="mt-1 text-[10px] font-bold text-[#285b55]">Managed through your active Ithute reseller account.</p> : null}</div><div className="flex gap-2"><button className="btn-secondary" onClick={() => void loadTenant(tenantId)}><RefreshCw size={14}/>Refresh</button>{canManage ? <button className="btn-primary" onClick={() => setShowCreate((value) => !value)}><Plus size={14}/>New hosted project</button> : null}</div></div>
      </section>

      {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}

      {summary ? <section className="grid gap-3 md:grid-cols-4"><article className="surface-card p-4"><Boxes size={17} className="text-[#285b55]"/><p className="mt-2 text-xl font-black">{summary.usage.hosted_projects} / {summary.package.hosted_projects}</p><p className="text-[10px] text-[var(--admin-muted)]">Hosted projects</p></article><article className="surface-card p-4"><HardDrive size={17} className="text-[#285b55]"/><p className="mt-2 text-xl font-black">{(usedStorageMb / 1024).toFixed(1)} / {(summary.package.hosting_storage_mb / 1024).toFixed(1)} GB</p><p className="text-[10px] text-[var(--admin-muted)]">Allocated app storage</p></article><article className="surface-card p-4"><Server size={17} className="text-[#285b55]"/><p className="mt-2 text-xl font-black">{summary.package.memory_mb_per_project} MB</p><p className="text-[10px] text-[var(--admin-muted)]">RAM ceiling / project</p></article><article className="surface-card p-4"><Cpu size={17} className="text-[#285b55]"/><p className="mt-2 text-xl font-black">{(summary.package.cpu_millicores_per_project / 1000).toFixed(2)} CPU</p><p className="text-[10px] text-[var(--admin-muted)]">CPU ceiling / project</p></article></section> : null}

      {showCreate && summary ? <form className="surface-card p-5" onSubmit={createProject}><div className="flex items-start justify-between gap-4"><div><h2 className="text-sm font-black">Allocate a hosted project</h2><p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">The scheduler reserves capacity on a system-owner approved hosting node. A project cannot exceed its package limits.</p></div><a className="text-xs font-black text-[#285b55]" href="/docs#hosting" target="_blank">Rules <ExternalLink size={12} className="inline"/></a></div><div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3"><label><span className="eyebrow-label">Project name</span><input className="input mt-1" name="name" placeholder="Company website" required/></label><label><span className="eyebrow-label">Slug</span><input className="input mt-1" name="slug" placeholder="company-website"/></label><label><span className="eyebrow-label">Runtime</span><select className="input mt-1" name="runtime">{(rules?.allowed_runtimes || ["static","node","python","php","dotnet","java","go","ruby","rust","dockerfile"]).map((runtime) => <option key={runtime} value={runtime}>{runtime}</option>)}</select></label><label><span className="eyebrow-label">Source repository</span><input className="input mt-1" name="source_repository" type="url" placeholder="https://github.com/company/site"/></label><label><span className="eyebrow-label">Source branch</span><input className="input mt-1" name="source_branch" defaultValue="main"/></label><label><span className="eyebrow-label">Verified domain</span><select className="input mt-1" name="domain_id"><option value="">No public hostname yet</option>{verifiedDomains.map((domain) => <option key={domain.id} value={domain.id}>{domain.ascii_name}</option>)}</select></label><label><span className="eyebrow-label">Hostname</span><input className="input mt-1" name="hostname" placeholder="www.example.co.ls"/></label><label><span className="eyebrow-label">App port</span><input className="input mt-1" name="container_port" type="number" min="1024" max="65535" defaultValue="8080"/></label><label><span className="eyebrow-label">Health path</span><input className="input mt-1" name="health_path" defaultValue="/"/></label><label><span className="eyebrow-label">Storage (GB)</span><input className="input mt-1" name="storage_gb" type="number" min="0.125" max={summary.package.hosting_storage_mb / 1024} step="0.125" defaultValue="1"/></label><label><span className="eyebrow-label">RAM (MB)</span><input className="input mt-1" name="memory_mb" type="number" min="128" max={summary.package.memory_mb_per_project} step="128" defaultValue={Math.min(512, summary.package.memory_mb_per_project)}/></label><label><span className="eyebrow-label">CPU (millicores)</span><input className="input mt-1" name="cpu_millicores" type="number" min="100" max={summary.package.cpu_millicores_per_project} step="100" defaultValue={Math.min(500, summary.package.cpu_millicores_per_project)}/></label><label><span className="eyebrow-label">Process limit</span><input className="input mt-1" name="pid_limit" type="number" min="32" max={summary.package.pids_per_project} step="16" defaultValue={Math.min(128, summary.package.pids_per_project)}/></label>{me?.is_platform_owner ? <label><span className="eyebrow-label">Workload placement</span><select className="input mt-1" name="node_id"><option value="">Automatic · healthiest available node</option>{hostingNodes.map((node) => <option key={node.id} value={node.id} disabled={node.status !== "active" || !node.accepts_new_projects}>{node.name} · {node.hostname} · {(node.available.storage_mb / 1024).toFixed(1)} GB free</option>)}</select><span className="mt-1 block text-[9px] text-[var(--admin-muted)]">Automatic placement considers live CPU, RAM, disk pressure, role capability and remaining sellable capacity.</span></label> : null}</div><label className="mt-5 flex items-start gap-3 rounded-2xl border border-[#dce5e0] bg-[#f6f9f7] p-4 text-xs leading-5"><input className="mt-1" type="checkbox" name="accept_rules" required/><span><b>I accept Hosting Rules v{rules?.version || summary.rules_version} for this project.</b> No root/SSH/Docker-socket access, no privileged workloads, no arbitrary public ports, no spam/mining/malware/open proxies, and resources remain inside the package limits.</span></label><button className="btn-primary mt-5" disabled={saving}><ShieldCheck size={14}/>{saving ? "Allocating…" : "Accept rules & allocate project"}</button></form> : null}

      <section className="surface-card overflow-hidden"><div className="border-b border-[#e4e9e6] p-4"><h2 className="text-sm font-black">Projects on shared hosting</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Each allocation reserves sellable node capacity even while suspended, so resource accounting remains predictable.</p></div><div className="grid gap-3 p-4 lg:grid-cols-2">{projects.map((project) => <article key={project.id} className="rounded-2xl border border-[#dce5e0] bg-white p-4"><div className="flex items-start justify-between gap-3"><div><h3 className="text-sm font-black">{project.name}</h3><p className="mt-1 text-[9px] font-bold uppercase tracking-[.08em] text-[var(--admin-muted)]">{project.runtime} · {project.status} · rules {project.rules_version}</p></div><span className={`rounded-full px-2 py-1 text-[9px] font-black ${project.status === "suspended" ? "bg-amber-50 text-amber-700" : "bg-emerald-50 text-emerald-700"}`}>{project.status}</span></div>{project.hostname ? <p className="mt-3 flex items-center gap-2 text-xs"><Globe2 size={14}/>{project.hostname}</p> : <p className="mt-3 text-xs text-[var(--admin-muted)]">No public hostname assigned yet.</p>}<div className="mt-3 grid grid-cols-4 gap-2 text-[9px]"><div className="rounded-xl bg-[#f4f7f5] p-2"><b>{(project.storage_mb / 1024).toFixed(1)} GB</b><br/>storage</div><div className="rounded-xl bg-[#f4f7f5] p-2"><b>{project.memory_mb} MB</b><br/>RAM</div><div className="rounded-xl bg-[#f4f7f5] p-2"><b>{(project.cpu_millicores / 1000).toFixed(2)}</b><br/>CPU</div><div className="rounded-xl bg-[#f4f7f5] p-2"><b>{project.pid_limit}</b><br/>PIDs</div></div>{project.source_repository ? <p className="mt-3 truncate text-[10px] text-[var(--admin-muted)]">Source: {project.source_repository} · {project.source_branch}</p> : null}{canManage ? <div className="mt-4 space-y-3">
  <div className="rounded-xl border border-[#dce5e0] bg-[#f8fbf9] p-3">
    <div className="flex flex-wrap items-end gap-2">
      <label className="min-w-44 flex-1"><span className="eyebrow-label">Automatic provisioning</span><select className="input mt-1" value={databaseEngine[project.id] || ""} onChange={(event) => setDatabaseEngine((current) => ({ ...current, [project.id]: event.target.value }))}><option value="">Application only</option><option value="postgresql">Application + PostgreSQL</option><option value="mysql">Application + MySQL</option></select></label>
      <button className="btn-primary" disabled={saving || ["provisioning","building","deploying","edge_pending"].includes(provisioning[project.id]?.status || "")} onClick={() => void provisionProject(project)}><ShieldCheck size={14}/>{provisioning[project.id] ? "Continue provisioning" : "Provision automatically"}</button>
    </div>
    {provisioning[project.id] ? <div className="mt-3">
      <div className="flex flex-wrap gap-1.5">{Object.entries(provisioning[project.id]?.stages || {}).map(([name, stage]) => <span key={name} className="rounded-full border border-[#dce5e0] bg-white px-2 py-1 text-[8px] font-black capitalize">{name}: {stage.status.replaceAll("_", " ")}</span>)}</div>
      <p className="mt-2 text-[9px] font-bold text-[#285b55]">Workflow: {provisioning[project.id]?.status.replaceAll("_", " ")}</p>
      {provisioning[project.id]?.failure_message ? <p className="mt-1 text-[9px] font-semibold text-red-700">{provisioning[project.id]?.failure_message}</p> : null}
    </div> : <p className="mt-2 text-[9px] text-[var(--admin-muted)]">Creates/uses source, queues the build, optionally provisions a managed database, injects credentials securely and prepares protected edge/TLS state for hosted domains.</p>}
  </div>
  <div className="rounded-xl border border-[#dce5e0] bg-white p-3">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 flex-1"><p className="text-[10px] font-black">Failover & rebalancing</p><p className="mt-1 text-[9px] leading-4 text-[var(--admin-muted)]">{project.failover_policy === "stateless_auto" ? "Stateless auto-failover is enabled. Local /data is considered disposable; managed databases on the failed node still block automatic application relocation." : "Manual recovery is the safe default. Ithute will not discard this project's local /data automatically."}</p></div>
      <button className="btn-secondary" onClick={() => void setFailoverPolicy(project, project.failover_policy === "stateless_auto" ? "manual" : "stateless_auto")}>{project.failover_policy === "stateless_auto" ? "Require manual recovery" : "Enable stateless failover"}</button>
    </div>
    {project.failover_policy === "stateless_auto" ? <div className="mt-3 flex flex-wrap items-end gap-2">
      {me?.is_platform_owner ? <label className="min-w-48 flex-1"><span className="eyebrow-label">Rebalance target</span><select className="input mt-1" value={relocationTarget[project.id] || ""} onChange={(event) => setRelocationTarget((current) => ({ ...current, [project.id]: event.target.value }))}><option value="">Automatic · healthiest other node</option>{hostingNodes.filter((node) => node.id !== project.node_id).map((node) => <option key={node.id} value={node.id} disabled={node.status !== "active" || !node.accepts_new_projects}>{node.name} · {(node.available.storage_mb / 1024).toFixed(1)} GB free</option>)}</select></label> : null}
      <button className="btn-secondary" onClick={() => void relocateProject(project)}>Move safely</button>
    </div> : null}
    {(failovers[project.id] || []).slice(0, 3).map((attempt) => <div key={attempt.id} className="mt-2 rounded-lg bg-[#f6f9f7] px-3 py-2 text-[8px]"><b className="capitalize">{attempt.status.replaceAll("_", " ")}</b>{attempt.edge_status ? ` · edge ${attempt.edge_status.replaceAll("_", " ")}` : ""}{attempt.reason ? <span className="block mt-1 text-[var(--admin-muted)]">{attempt.reason}</span> : null}</div>)}
  </div>
  <button className="btn-secondary" onClick={() => void setStatus(project, project.status === "suspended" ? "configured" : "suspended")}>{project.status === "suspended" ? "Enable" : "Suspend"}</button>
</div> : null}</article>)}{!loading && !projects.length ? <div className="rounded-2xl border border-dashed border-[#d6dfda] p-6 text-center text-xs text-[var(--admin-muted)]">No hosted projects yet. Create one after the system owner has registered sellable hosting-node capacity.</div> : null}</div></section>

      <section className="rounded-3xl bg-[#123a38] p-6 text-white"><div className="flex items-start gap-4"><ShieldCheck size={22} className="mt-1 shrink-0 text-[#f1de8b]"/><div><h2 className="text-lg font-black">Hosting is isolated by policy and quota.</h2><p className="mt-2 max-w-3xl text-xs leading-6 text-white/65">Customer projects never receive host SSH, root access or Docker control. Public traffic must pass through Ithute ingress, builds must happen through an approved isolated build pipeline, and every project is bounded by package CPU, memory, storage and PID allocations.</p><a href="/docs#hosting" className="mt-3 inline-flex text-xs font-black text-[#f1de8b]">Read the complete hosting rules →</a></div></div></section>
    </div>
  </ControlShell>;
}
