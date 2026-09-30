"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Database, GitBranch, KeyRound, RefreshCw, ShieldCheck, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";
import { PageHeader } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Me = { email: string; is_platform_owner: boolean };
type Context = { tenant_id: string; tenant_name: string; role: string; access_kind: string; permissions?: string[] };
type Project = { id: string; name: string; runtime: string; status: string };
type HostingDatabase = {
  id: string;
  project_id?: string | null;
  engine: "postgresql" | "mysql";
  engine_version?: string | null;
  database_name: string;
  username: string;
  host?: string | null;
  port: number;
  storage_mb: number;
  status: string;
};
type Source = {
  id: string;
  source_type: "git" | "zip";
  repository_url?: string | null;
  repository_branch?: string | null;
  original_filename?: string | null;
  status: string;
  created_at?: string | null;
};
type CreatedDatabase = HostingDatabase & { password: string; credential_warning: string };

async function api(path: string, init?: RequestInit) {
  const options: RequestInit = { credentials: "include", ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } };
  let response = await fetch(`${API}${path}`, options);
  if (response.status === 401) {
    const refresh = await fetch(`${API}/auth/refresh`, { method: "POST", credentials: "include" });
    if (refresh.ok) response = await fetch(`${API}${path}`, options);
  }
  return response;
}

async function detail(response: Response, fallback: string) {
  const body = await response.json().catch(() => ({}));
  return typeof body.detail === "string" ? body.detail : fallback;
}

export default function HostingResourcesPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [contexts, setContexts] = useState<Context[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [databases, setDatabases] = useState<HostingDatabase[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [createdDatabase, setCreatedDatabase] = useState<CreatedDatabase | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  const selectedContext = useMemo(() => contexts.find((row) => row.tenant_id === tenantId), [contexts, tenantId]);
  const canManage = Boolean(me?.is_platform_owner || selectedContext?.role === "tenant_admin" || selectedContext?.role === "reseller_admin" || selectedContext?.permissions?.includes("hosting.manage"));

  async function loadTenant(id: string) {
    if (!id) return;
    setError("");
    const [projectsResponse, databasesResponse] = await Promise.all([
      api(`/tenants/${id}/hosting/projects`),
      api(`/tenants/${id}/hosting/databases`),
    ]);
    if (!projectsResponse.ok) {
      setProjects([]);
      setDatabases([]);
      setError(await detail(projectsResponse, "Unable to load hosting resources."));
      return;
    }
    const loadedProjects: Project[] = (await projectsResponse.json()).items || [];
    setProjects(loadedProjects);
    setDatabases(databasesResponse.ok ? (await databasesResponse.json()).items || [] : []);
    setProjectId((current) => loadedProjects.some((row) => row.id === current) ? current : loadedProjects[0]?.id || "");
  }

  async function loadSources(id: string) {
    if (!tenantId || !id) { setSources([]); return; }
    const response = await api(`/tenants/${tenantId}/hosting/projects/${id}/sources`);
    setSources(response.ok ? (await response.json()).items || [] : []);
  }

  useEffect(() => {
    void (async () => {
      const meResponse = await api("/auth/me");
      if (meResponse.status === 401) { router.replace("/login"); return; }
      if (!meResponse.ok) return;
      setMe(await meResponse.json());
      const contextsResponse = await api("/me/service-contexts");
      const rows: Context[] = contextsResponse.ok ? (await contextsResponse.json()).items || [] : [];
      setContexts(rows);
      const remembered = window.localStorage.getItem("mailbox_dns_tenant");
      setTenantId(rows.find((row) => row.tenant_id === remembered)?.tenant_id || rows[0]?.tenant_id || "");
    })();
  }, [router]);

  useEffect(() => {
    if (!tenantId) return;
    window.localStorage.setItem("mailbox_dns_tenant", tenantId);
    setCreatedDatabase(null);
    void loadTenant(tenantId);
  }, [tenantId]);

  useEffect(() => { void loadSources(projectId); }, [projectId, tenantId]);

  async function createDatabase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tenantId) return;
    setSaving(true); setError(""); setMessage(""); setCreatedDatabase(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    const response = await api(`/tenants/${tenantId}/hosting/databases`, {
      method: "POST",
      body: JSON.stringify({
        engine: String(data.get("engine") || "postgresql"),
        name: String(data.get("name") || ""),
        project_id: String(data.get("project_id") || "") || null,
        storage_mb: Math.round(Number(data.get("storage_gb") || 1) * 1024),
      }),
    });
    if (!response.ok) { setError(await detail(response, "Unable to create database.")); setSaving(false); return; }
    const created: CreatedDatabase = await response.json();
    setCreatedDatabase(created);
    setMessage("Database provisioning has been queued. Save the generated password now; it will not be shown again.");
    form.reset();
    await loadTenant(tenantId);
    setSaving(false);
  }

  async function registerGit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tenantId || !projectId) return;
    setSaving(true); setError(""); setMessage("");
    const form = event.currentTarget;
    const data = new FormData(form);
    const response = await api(`/tenants/${tenantId}/hosting/projects/${projectId}/sources/git`, {
      method: "POST",
      body: JSON.stringify({ repository_url: data.get("repository_url"), branch: data.get("branch") || "main" }),
    });
    if (!response.ok) { setError(await detail(response, "Unable to register Git source.")); setSaving(false); return; }
    form.reset();
    setMessage("Git source registered. Credentials must be configured separately and encrypted; never place tokens in the repository URL.");
    await loadSources(projectId);
    setSaving(false);
  }

  return <ControlShell title="Hosting resources" subtitle="Databases and deployment sources for shared hosting" userEmail={me?.email}>
    <div className="space-y-5">
      <PageHeader eyebrow="Shared hosting" title="Sources & databases" description="Connect Git source code and allocate isolated PostgreSQL or MySQL credentials without exposing the VPS, Docker socket or host database administration." />

      <section className="surface-card p-4">
        <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
          <label><span className="eyebrow-label">Organization / managed customer</span><select className="input mt-1" value={tenantId} onChange={(event) => setTenantId(event.target.value)}>{contexts.map((row) => <option key={row.tenant_id} value={row.tenant_id}>{row.tenant_name}{row.access_kind === "reseller_customer" ? " · reseller customer" : ""}</option>)}</select></label>
          <label><span className="eyebrow-label">Hosted project</span><select className="input mt-1" value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Select a project</option>{projects.map((row) => <option key={row.id} value={row.id}>{row.name} · {row.runtime}</option>)}</select></label>
          <button className="btn-secondary" onClick={() => void loadTenant(tenantId)}><RefreshCw size={14}/>Refresh</button>
        </div>
      </section>

      {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}

      {createdDatabase ? <section className="rounded-2xl border border-amber-300 bg-amber-50 p-5"><div className="flex items-start gap-3"><KeyRound size={18} className="mt-0.5"/><div className="min-w-0"><h2 className="text-sm font-black">Save this password now</h2><p className="mt-1 text-xs text-amber-900">{createdDatabase.credential_warning}</p><div className="mt-3 grid gap-2 text-xs md:grid-cols-2"><p><b>Engine:</b> {createdDatabase.engine}</p><p><b>Database:</b> {createdDatabase.database_name}</p><p><b>Username:</b> {createdDatabase.username}</p><p className="break-all"><b>Password:</b> <code>{createdDatabase.password}</code></p></div></div></div></section> : null}

      <section className="grid gap-4 xl:grid-cols-2">
        <form className="surface-card p-5" onSubmit={createDatabase}>
          <div className="flex items-center gap-2"><Database size={17}/><h2 className="text-sm font-black">Create database</h2></div>
          <p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">A unique database user and strong password are generated for every database. The password is encrypted at rest and returned in plaintext only once.</p>
          <div className="mt-4 grid gap-3">
            <select className="input" name="engine"><option value="postgresql">PostgreSQL</option><option value="mysql">MySQL</option></select>
            <input className="input" name="name" placeholder="customer_app" required minLength={2} maxLength={48}/>
            <select className="input" name="project_id" defaultValue={projectId}><option value="">Shared for this customer</option>{projects.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select>
            <input className="input" name="storage_gb" type="number" min="0.125" max="100" step="0.125" defaultValue="1"/>
            <button className="btn-primary" disabled={!canManage || saving}><Database size={14}/>{saving ? "Saving…" : "Create database"}</button>
          </div>
        </form>

        <form className="surface-card p-5" onSubmit={registerGit}>
          <div className="flex items-center gap-2"><GitBranch size={17}/><h2 className="text-sm font-black">Connect Git source</h2></div>
          <p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">Use HTTPS without embedded credentials, SSH, or the standard git@host:path form. Private-repository credentials will use a separate encrypted deployment credential.</p>
          <div className="mt-4 grid gap-3">
            <input className="input" name="repository_url" placeholder="https://github.com/company/project.git" required/>
            <input className="input" name="branch" placeholder="main" defaultValue="main" required/>
            <button className="btn-primary" disabled={!canManage || !projectId || saving}><GitBranch size={14}/>{saving ? "Saving…" : "Connect repository"}</button>
          </div>
        </form>
      </section>

      <section className="surface-card p-5">
        <div className="flex items-start gap-3"><Upload size={17}/><div><h2 className="text-sm font-black">ZIP deployment</h2><p className="mt-1 text-xs leading-5 text-[var(--admin-muted)]">The control-plane metadata and quarantine contract are already in place. Direct browser byte upload stays disabled here until the isolated upload store and checksum/ZIP-bomb validation service are connected; Ithute will not write untrusted ZIPs into the application container or production source tree.</p></div></div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="surface-card overflow-hidden"><div className="border-b p-4"><h2 className="text-sm font-black">Databases</h2></div><div className="space-y-2 p-4">{databases.map((row) => <div key={row.id} className="rounded-xl border p-3 text-xs"><div className="flex justify-between gap-3"><b>{row.database_name}</b><span>{row.status}</span></div><p className="mt-1 text-[var(--admin-muted)]">{row.engine} · {row.username} · {row.storage_mb} MB</p></div>)}{!databases.length ? <p className="text-xs text-[var(--admin-muted)]">No hosting databases yet.</p> : null}</div></div>
        <div className="surface-card overflow-hidden"><div className="border-b p-4"><h2 className="text-sm font-black">Sources for selected project</h2></div><div className="space-y-2 p-4">{sources.map((row) => <div key={row.id} className="rounded-xl border p-3 text-xs"><div className="flex justify-between gap-3"><b>{row.source_type === "git" ? row.repository_url : row.original_filename}</b><span>{row.status}</span></div>{row.repository_branch ? <p className="mt-1 text-[var(--admin-muted)]">Branch: {row.repository_branch}</p> : null}</div>)}{!sources.length ? <p className="text-xs text-[var(--admin-muted)]">No source records for this project.</p> : null}</div></div>
      </section>

      <section className="rounded-3xl bg-[#123a38] p-5 text-white"><div className="flex gap-3"><ShieldCheck size={20} className="text-[#f1de8b]"/><p className="text-xs leading-6 text-white/70">Database passwords and future private-Git credentials are control-plane secrets. Hosted applications receive only project-scoped values; they never receive Ithute host, mail, DNS, Docker or other-customer credentials.</p></div></section>
    </div>
  </ControlShell>;
}
