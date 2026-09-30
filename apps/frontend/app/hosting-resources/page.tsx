"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Database, GitBranch, HardDrive, KeyRound, PauseCircle, PlayCircle, RefreshCw, RotateCcw, ShieldCheck, Trash2, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";
import { PageHeader } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Me = { email: string; is_platform_owner: boolean };
type Context = { tenant_id: string; tenant_name: string; role: string; access_kind: string; permissions?: string[] };
type Project = { id: string; name: string; runtime: string; status: string };
type HostingDatabase = { id: string; project_id?: string | null; engine: "postgresql" | "mysql"; engine_version?: string | null; database_name: string; username: string; host?: string | null; port: number; storage_mb: number; status: string; operation?: string; failure_message?: string | null };
type Source = { id: string; source_type: "git" | "zip"; repository_url?: string | null; repository_branch?: string | null; original_filename?: string | null; size_bytes?: number | null; status: string; created_at?: string | null };
type GitCredential = { id: string; name: string; provider: string; auth_type: string; username?: string | null; status: string; has_secret: boolean };
type CreatedDatabase = HostingDatabase & { password: string; credential_warning: string };
type ResourceMeter = {
  usage: { database_count: number; database_storage_bytes: number; source_storage_bytes: number };
  limits: { database_count: number; database_storage_bytes: number; source_storage_bytes: number } | null;
  plan?: { code: string; name: string };
};

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

function gb(bytes: number) {
  return (bytes / 1024 / 1024 / 1024).toFixed(bytes >= 10 * 1024 * 1024 * 1024 ? 0 : 1);
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
  const [credentials, setCredentials] = useState<GitCredential[]>([]);
  const [meter, setMeter] = useState<ResourceMeter | null>(null);
  const [createdDatabase, setCreatedDatabase] = useState<CreatedDatabase | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  const selectedContext = useMemo(() => contexts.find((row) => row.tenant_id === tenantId), [contexts, tenantId]);
  const canManage = Boolean(me?.is_platform_owner || selectedContext?.role === "tenant_admin" || selectedContext?.role === "reseller_admin" || selectedContext?.permissions?.includes("hosting.manage"));

  async function loadTenant(id: string) {
    if (!id) return;
    setError("");
    const [projectsResponse, databasesResponse, meterResponse] = await Promise.all([
      api(`/tenants/${id}/hosting/projects`),
      api(`/tenants/${id}/hosting/databases`),
      api(`/tenants/${id}/hosting/resource-meter`),
    ]);
    if (!projectsResponse.ok) {
      setProjects([]); setDatabases([]); setMeter(null); setError(await detail(projectsResponse, "Unable to load hosting resources.")); return;
    }
    const loadedProjects: Project[] = (await projectsResponse.json()).items || [];
    setProjects(loadedProjects);
    setDatabases(databasesResponse.ok ? (await databasesResponse.json()).items || [] : []);
    setMeter(meterResponse.ok ? await meterResponse.json() : null);
    setProjectId((current) => loadedProjects.some((row) => row.id === current) ? current : loadedProjects[0]?.id || "");
  }

  async function loadProjectResources(id: string) {
    if (!tenantId || !id) { setSources([]); setCredentials([]); return; }
    const [sourceResponse, credentialResponse] = await Promise.all([
      api(`/tenants/${tenantId}/hosting/projects/${id}/sources`),
      api(`/tenants/${tenantId}/hosting/projects/${id}/source-credentials`),
    ]);
    setSources(sourceResponse.ok ? (await sourceResponse.json()).items || [] : []);
    setCredentials(credentialResponse.ok ? (await credentialResponse.json()).items || [] : []);
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

  useEffect(() => { void loadProjectResources(projectId); }, [projectId, tenantId]);

  async function createDatabase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!tenantId) return;
    setSaving(true); setError(""); setMessage(""); setCreatedDatabase(null);
    const form = event.currentTarget; const data = new FormData(form);
    const response = await api(`/tenants/${tenantId}/hosting/databases`, { method: "POST", body: JSON.stringify({ engine: String(data.get("engine") || "postgresql"), name: String(data.get("name") || ""), project_id: String(data.get("project_id") || "") || null, storage_mb: Math.round(Number(data.get("storage_gb") || 1) * 1024) }) });
    if (!response.ok) { setError(await detail(response, "Unable to create database.")); setSaving(false); return; }
    const created: CreatedDatabase = await response.json(); setCreatedDatabase(created); setMessage("Database provisioning has been queued. Save the generated password now; it will not be shown again."); form.reset(); await loadTenant(tenantId); setSaving(false);
  }

  async function databaseAction(row: HostingDatabase, action: "rotate-password" | "suspend" | "resume" | "delete") {
    if (!tenantId || saving) return;
    if (action === "delete" && !window.confirm(`Delete database ${row.database_name}? This queues permanent database and user removal on the hosting node.`)) return;
    setSaving(true); setError(""); setMessage("");
    const response = await api(`/tenants/${tenantId}/hosting/databases/${row.id}${action === "delete" ? "" : `/${action}`}`, { method: action === "delete" ? "DELETE" : "POST" });
    if (!response.ok) { setError(await detail(response, `Unable to ${action.replace("-", " ")} database.`)); setSaving(false); return; }
    if (action === "rotate-password") { const rotated: CreatedDatabase = await response.json(); setCreatedDatabase(rotated); setMessage("Password rotation is queued. Save the replacement password now and update the application secret after the database returns to ready."); }
    else { setCreatedDatabase(null); setMessage(action === "delete" ? "Database deletion is queued." : `Database ${action} is queued.`); }
    await loadTenant(tenantId); setSaving(false);
  }

  async function createCredential(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!tenantId || !projectId) return;
    setSaving(true); setError(""); setMessage("");
    const form = event.currentTarget; const data = new FormData(form);
    const response = await api(`/tenants/${tenantId}/hosting/projects/${projectId}/source-credentials`, { method: "POST", body: JSON.stringify({ name: data.get("name"), provider: data.get("provider"), auth_type: data.get("auth_type"), username: data.get("username") || null, secret: data.get("secret") }) });
    if (!response.ok) { setError(await detail(response, "Unable to save Git credential.")); setSaving(false); return; }
    form.reset(); setMessage("Git credential encrypted and saved. The secret will never be displayed back in the dashboard."); await loadProjectResources(projectId); setSaving(false);
  }

  async function revokeCredential(row: GitCredential) {
    if (!tenantId || !projectId || !canManage || row.status === "revoked") return;
    if (!window.confirm(`Revoke Git credential ${row.name}? Existing private-source builds using it will stop authenticating.`)) return;
    setSaving(true); setError("");
    const response = await api(`/tenants/${tenantId}/hosting/projects/${projectId}/source-credentials/${row.id}`, { method: "DELETE" });
    if (!response.ok) setError(await detail(response, "Unable to revoke Git credential.")); else setMessage("Git credential revoked.");
    await loadProjectResources(projectId); setSaving(false);
  }

  async function registerGit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!tenantId || !projectId) return;
    setSaving(true); setError(""); setMessage("");
    const form = event.currentTarget; const data = new FormData(form); const credentialId = String(data.get("credential_id") || "");
    const endpoint = credentialId ? `/tenants/${tenantId}/hosting/projects/${projectId}/sources/private-git` : `/tenants/${tenantId}/hosting/projects/${projectId}/sources/git`;
    const payload = credentialId ? { repository_url: data.get("repository_url"), branch: data.get("branch") || "main", credential_id: credentialId } : { repository_url: data.get("repository_url"), branch: data.get("branch") || "main" };
    const response = await api(endpoint, { method: "POST", body: JSON.stringify(payload) });
    if (!response.ok) { setError(await detail(response, "Unable to register Git source.")); setSaving(false); return; }
    form.reset(); setMessage(credentialId ? "Private Git source connected with an encrypted project credential." : "Public Git source registered."); await loadProjectResources(projectId); setSaving(false);
  }

  return <ControlShell title="Hosting resources" subtitle="Databases and deployment sources for shared hosting" userEmail={me?.email}>
    <div className="space-y-5">
      <PageHeader eyebrow="Shared hosting" title="Sources & databases" description="Connect Git or verified ZIP source code and allocate isolated PostgreSQL or MySQL credentials without exposing the VPS, Docker socket or host database administration." />
      <section className="surface-card p-4"><div className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end"><label><span className="eyebrow-label">Organization / managed customer</span><select className="input mt-1" value={tenantId} onChange={(event) => setTenantId(event.target.value)}>{contexts.map((row) => <option key={row.tenant_id} value={row.tenant_id}>{row.tenant_name}{row.access_kind === "reseller_customer" ? " · reseller customer" : ""}</option>)}</select></label><label><span className="eyebrow-label">Hosted project</span><select className="input mt-1" value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Select a project</option>{projects.map((row) => <option key={row.id} value={row.id}>{row.name} · {row.runtime}</option>)}</select></label><button className="btn-secondary" onClick={() => void loadTenant(tenantId)}><RefreshCw size={14}/>Refresh</button></div></section>

      {meter?.limits ? <section className="grid gap-3 md:grid-cols-3">
        <article className="surface-card p-4"><Database size={17}/><p className="mt-2 text-xl font-black">{meter.usage.database_count} / {meter.limits.database_count}</p><p className="text-[10px] text-[var(--admin-muted)]">Hosted databases · {meter.plan?.name || "current plan"}</p></article>
        <article className="surface-card p-4"><HardDrive size={17}/><p className="mt-2 text-xl font-black">{gb(meter.usage.database_storage_bytes)} / {gb(meter.limits.database_storage_bytes)} GB</p><p className="text-[10px] text-[var(--admin-muted)]">Database storage reserved</p></article>
        <article className="surface-card p-4"><Upload size={17}/><p className="mt-2 text-xl font-black">{gb(meter.usage.source_storage_bytes)} / {gb(meter.limits.source_storage_bytes)} GB</p><p className="text-[10px] text-[var(--admin-muted)]">Verified/uploading ZIP source storage</p></article>
      </section> : null}

      {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}
      {createdDatabase ? <section className="rounded-2xl border border-amber-300 bg-amber-50 p-5"><div className="flex items-start gap-3"><KeyRound size={18} className="mt-0.5"/><div><h2 className="text-sm font-black">Save this password now</h2><p className="mt-1 text-xs text-amber-900">{createdDatabase.credential_warning}</p><div className="mt-3 grid gap-2 text-xs md:grid-cols-2"><p><b>Engine:</b> {createdDatabase.engine}</p><p><b>Database:</b> {createdDatabase.database_name}</p><p><b>Username:</b> {createdDatabase.username}</p><p className="break-all"><b>Password:</b> <code>{createdDatabase.password}</code></p></div></div></div></section> : null}

      <section className="grid gap-4 xl:grid-cols-2">
        <form className="surface-card p-5" onSubmit={createDatabase}><div className="flex items-center gap-2"><Database size={17}/><h2 className="text-sm font-black">Create database</h2></div><p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">A unique database user and strong password are generated for every database. Database count and allocated storage are enforced against the customer package before provisioning is queued.</p><div className="mt-4 grid gap-3"><select className="input" name="engine"><option value="postgresql">PostgreSQL</option><option value="mysql">MySQL</option></select><input className="input" name="name" placeholder="customer_app" required minLength={2} maxLength={48}/><select className="input" name="project_id" defaultValue={projectId}><option value="">Shared for this customer</option>{projects.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select><input className="input" name="storage_gb" type="number" min="0.125" max="100" step="0.125" defaultValue="1"/><button className="btn-primary" disabled={!canManage || saving}><Database size={14}/>{saving ? "Saving…" : "Create database"}</button></div></form>
        <form className="surface-card p-5" onSubmit={createCredential}><div className="flex items-center gap-2"><KeyRound size={17}/><h2 className="text-sm font-black">Private Git credential</h2></div><p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">Store a project-scoped token or SSH private key encrypted at rest. It is never rendered back after submission.</p><div className="mt-4 grid gap-3"><input className="input" name="name" placeholder="GitHub deploy credential" required/><select className="input" name="provider"><option value="github">GitHub</option><option value="gitlab">GitLab</option><option value="bitbucket">Bitbucket</option><option value="generic">Generic Git</option></select><select className="input" name="auth_type"><option value="https_token">HTTPS token</option><option value="ssh_key">SSH private key</option></select><input className="input" name="username" placeholder="Username (required for generic HTTPS)"/><textarea className="input min-h-28" name="secret" placeholder="Token or private key" required minLength={12}/><button className="btn-primary" disabled={!canManage || !projectId || saving}><KeyRound size={14}/>Encrypt credential</button></div></form>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <form className="surface-card p-5" onSubmit={registerGit}><div className="flex items-center gap-2"><GitBranch size={17}/><h2 className="text-sm font-black">Connect Git source</h2></div><p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">Public repositories need no credential. For private repositories, select one of the encrypted credentials for this project.</p><div className="mt-4 grid gap-3"><input className="input" name="repository_url" placeholder="https://github.com/company/project.git" required/><input className="input" name="branch" placeholder="main" defaultValue="main" required/><select className="input" name="credential_id"><option value="">Public repository · no credential</option>{credentials.filter((row) => row.status === "active").map((row) => <option key={row.id} value={row.id}>{row.name} · {row.provider} · {row.auth_type}</option>)}</select><button className="btn-primary" disabled={!canManage || !projectId || saving}><GitBranch size={14}/>{saving ? "Saving…" : "Connect repository"}</button></div></form>
        <section className="surface-card overflow-hidden"><div className="border-b p-4"><h2 className="text-sm font-black">Project Git credentials</h2></div><div className="space-y-2 p-4">{credentials.map((row) => <div key={row.id} className="rounded-xl border p-3 text-xs"><div className="flex items-start justify-between gap-3"><div><b>{row.name}</b><p className="mt-1 text-[var(--admin-muted)]">{row.provider} · {row.auth_type}{row.username ? ` · ${row.username}` : ""}</p></div><span>{row.status}</span></div>{canManage && row.status === "active" ? <button className="btn-secondary mt-3" disabled={saving} onClick={() => void revokeCredential(row)}><Trash2 size={13}/>Revoke</button> : null}</div>)}{!credentials.length ? <p className="text-xs text-[var(--admin-muted)]">No private Git credentials for this project.</p> : null}</div></section>
      </section>

      <section className="surface-card p-5"><div className="flex flex-wrap items-start justify-between gap-4"><div className="flex items-start gap-3"><Upload size={17}/><div><h2 className="text-sm font-black">ZIP deployment</h2><p className="mt-1 max-w-3xl text-xs leading-5 text-[var(--admin-muted)]">ZIP uploads use Ithute's isolated quarantine service. Archive size is reserved against the package before upload; checksum, path traversal, symlink and compression-ratio checks must pass before the builder can consume the source.</p></div></div><a className="btn-primary" href="/hosting-upload"><Upload size={14}/>Open secure ZIP upload</a></div></section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="surface-card overflow-hidden"><div className="border-b p-4"><h2 className="text-sm font-black">Databases</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Provisioning, credential rotation and access changes are executed by the hosting-node agent.</p></div><div className="space-y-2 p-4">{databases.map((row) => <div key={row.id} className="rounded-xl border p-3 text-xs"><div className="flex flex-wrap items-start justify-between gap-3"><div><b>{row.database_name}</b><p className="mt-1 text-[var(--admin-muted)]">{row.engine}{row.engine_version ? ` ${row.engine_version}` : ""} · {row.username} · {row.storage_mb} MB</p>{row.host ? <p className="mt-1 text-[var(--admin-muted)]">{row.host}:{row.port}</p> : null}</div><span className="rounded-full bg-[#f4f7f5] px-2 py-1 text-[9px] font-black uppercase">{row.operation && row.operation !== "none" ? `${row.status} · ${row.operation}` : row.status}</span></div>{row.failure_message ? <p className="mt-2 rounded-lg bg-red-50 p-2 text-red-700">{row.failure_message}</p> : null}{canManage ? <div className="mt-3 flex flex-wrap gap-2">{row.status === "ready" && (!row.operation || row.operation === "none") ? <><button className="btn-secondary" disabled={saving} onClick={() => void databaseAction(row, "rotate-password")}><RotateCcw size={13}/>Rotate password</button><button className="btn-secondary" disabled={saving} onClick={() => void databaseAction(row, "suspend")}><PauseCircle size={13}/>Suspend</button></> : null}{row.status === "suspended" && (!row.operation || row.operation === "none") ? <button className="btn-secondary" disabled={saving} onClick={() => void databaseAction(row, "resume")}><PlayCircle size={13}/>Resume</button> : null}{!["queued","working","deleting"].includes(row.status) ? <button className="btn-secondary" disabled={saving} onClick={() => void databaseAction(row, "delete")}><Trash2 size={13}/>Delete</button> : null}</div> : null}</div>)}{!databases.length ? <p className="text-xs text-[var(--admin-muted)]">No hosting databases yet.</p> : null}</div></div>
        <div className="surface-card overflow-hidden"><div className="border-b p-4"><h2 className="text-sm font-black">Sources for selected project</h2></div><div className="space-y-2 p-4">{sources.map((row) => <div key={row.id} className="rounded-xl border p-3 text-xs"><div className="flex justify-between gap-3"><b>{row.source_type === "git" ? row.repository_url : row.original_filename}</b><span>{row.status}</span></div>{row.repository_branch ? <p className="mt-1 text-[var(--admin-muted)]">Branch: {row.repository_branch}</p> : null}{row.source_type === "zip" && row.size_bytes ? <p className="mt-1 text-[var(--admin-muted)]">Archive: {(row.size_bytes / 1024 / 1024).toFixed(1)} MB</p> : null}</div>)}{!sources.length ? <p className="text-xs text-[var(--admin-muted)]">No source records for this project.</p> : null}</div></div>
      </section>
      <section className="rounded-3xl bg-[#123a38] p-5 text-white"><div className="flex gap-3"><ShieldCheck size={20} className="text-[#f1de8b]"/><p className="text-xs leading-6 text-white/70">Database passwords and private-Git credentials are control-plane secrets. Hosted applications receive only project-scoped values; they never receive Ithute host, mail, DNS, Docker or other-customer credentials.</p></div></section>
    </div>
  </ControlShell>;
}
