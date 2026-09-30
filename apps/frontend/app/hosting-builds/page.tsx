"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Hammer, Play, RefreshCw, Rocket, Save, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";
import { PageHeader } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Me = { email: string; is_platform_owner: boolean };
type Context = { tenant_id: string; tenant_name: string; role: string; access_kind: string; permissions?: string[] };
type Project = { id: string; name: string; runtime: string; status: string };
type Source = { id: string; source_type: "git" | "zip"; repository_url?: string | null; repository_branch?: string | null; original_filename?: string | null; status: string };
type BuildSettings = { project_id: string; runtime: string; build_command?: string | null; start_command?: string | null };
type Build = { id: string; source_id: string; runtime: string; status: string; source_commit?: string | null; image_ref?: string | null; failure_message?: string | null; created_at?: string | null };

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

export default function HostingBuildsPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [contexts, setContexts] = useState<Context[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [settings, setSettings] = useState<BuildSettings | null>(null);
  const [buildCommand, setBuildCommand] = useState("");
  const [startCommand, setStartCommand] = useState("");
  const [builds, setBuilds] = useState<Build[]>([]);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const context = useMemo(() => contexts.find((row) => row.tenant_id === tenantId), [contexts, tenantId]);
  const canManage = Boolean(me?.is_platform_owner || context?.role === "tenant_admin" || context?.role === "reseller_admin" || context?.permissions?.includes("hosting.manage"));
  const selectedProject = projects.find((row) => row.id === projectId);

  async function loadTenant(id: string) {
    if (!id) return;
    const response = await api(`/tenants/${id}/hosting/projects`);
    if (!response.ok) { setError(await detail(response, "Unable to load hosted projects.")); return; }
    const rows: Project[] = (await response.json()).items || [];
    setProjects(rows);
    setProjectId((current) => rows.some((row) => row.id === current) ? current : rows[0]?.id || "");
  }

  async function loadProject(id: string) {
    if (!tenantId || !id) { setSources([]); setBuilds([]); setSettings(null); return; }
    const [sourceResponse, settingsResponse, buildsResponse] = await Promise.all([
      api(`/tenants/${tenantId}/hosting/projects/${id}/sources`),
      api(`/tenants/${tenantId}/hosting/projects/${id}/build-settings`),
      api(`/tenants/${tenantId}/hosting/projects/${id}/builds`),
    ]);
    const sourceRows: Source[] = sourceResponse.ok ? (await sourceResponse.json()).items || [] : [];
    setSources(sourceRows);
    setSourceId((current) => sourceRows.some((row) => row.id === current && row.status === "ready") ? current : sourceRows.find((row) => row.status === "ready")?.id || "");
    if (settingsResponse.ok) {
      const loaded: BuildSettings = await settingsResponse.json();
      setSettings(loaded);
      setBuildCommand(loaded.build_command || "");
      setStartCommand(loaded.start_command || "");
    }
    setBuilds(buildsResponse.ok ? (await buildsResponse.json()).items || [] : []);
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
    void loadTenant(tenantId);
  }, [tenantId]);

  useEffect(() => { void loadProject(projectId); }, [projectId, tenantId]);

  async function saveSettings(event: FormEvent) {
    event.preventDefault();
    if (!tenantId || !projectId) return;
    setSaving(true); setError(""); setMessage("");
    const response = await api(`/tenants/${tenantId}/hosting/projects/${projectId}/build-settings`, {
      method: "PATCH",
      body: JSON.stringify({ build_command: buildCommand || null, start_command: startCommand || null }),
    });
    if (!response.ok) { setError(await detail(response, "Unable to save build settings.")); setSaving(false); return; }
    const loaded: BuildSettings = await response.json();
    setSettings(loaded);
    setMessage("Build settings saved.");
    setSaving(false);
  }

  async function queueBuild() {
    if (!tenantId || !projectId || !sourceId) return;
    setSaving(true); setError(""); setMessage("");
    const response = await api(`/tenants/${tenantId}/hosting/projects/${projectId}/builds`, {
      method: "POST",
      body: JSON.stringify({ source_id: sourceId }),
    });
    if (!response.ok) { setError(await detail(response, "Unable to queue build.")); setSaving(false); return; }
    setMessage("Build queued for the isolated Ithute builder. A successful immutable image will automatically enter the deployment queue.");
    await loadProject(projectId);
    setSaving(false);
  }

  return <ControlShell title="Build & Deploy" subtitle="Isolated source builds for shared hosting" userEmail={me?.email}>
    <div className="space-y-5">
      <PageHeader eyebrow="Shared hosting" title="Build & deploy" description="Build customer Git source away from production, publish an immutable image, then hand it to the hardened hosting-node deployment agent." />

      <section className="surface-card p-4">
        <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
          <label><span className="eyebrow-label">Organization / managed customer</span><select className="input mt-1" value={tenantId} onChange={(event) => setTenantId(event.target.value)}>{contexts.map((row) => <option key={row.tenant_id} value={row.tenant_id}>{row.tenant_name}{row.access_kind === "reseller_customer" ? " · reseller customer" : ""}</option>)}</select></label>
          <label><span className="eyebrow-label">Project</span><select className="input mt-1" value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Select a project</option>{projects.map((row) => <option key={row.id} value={row.id}>{row.name} · {row.runtime}</option>)}</select></label>
          <button className="btn-secondary" onClick={() => void loadProject(projectId)}><RefreshCw size={14}/>Refresh</button>
        </div>
      </section>

      {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}

      <section className="grid gap-4 xl:grid-cols-2">
        <form className="surface-card p-5" onSubmit={saveSettings}>
          <div className="flex items-center gap-2"><Hammer size={17}/><h2 className="text-sm font-black">Build settings</h2></div>
          <p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">Runtime: <b>{selectedProject?.runtime || settings?.runtime || "—"}</b>. Leave the build command empty when Ithute's managed template can handle dependencies automatically. Dynamic runtimes may need a start command if Ithute cannot infer one safely.</p>
          <div className="mt-4 grid gap-3">
            <input className="input" value={buildCommand} onChange={(event) => setBuildCommand(event.target.value)} placeholder="Build command (optional), e.g. npm run build" maxLength={1000}/>
            <input className="input" value={startCommand} onChange={(event) => setStartCommand(event.target.value)} placeholder="Start command, e.g. npm start" maxLength={1000}/>
            <button className="btn-primary" disabled={!canManage || !projectId || saving}><Save size={14}/>{saving ? "Saving…" : "Save settings"}</button>
          </div>
        </form>

        <div className="surface-card p-5">
          <div className="flex items-center gap-2"><Rocket size={17}/><h2 className="text-sm font-black">Queue build</h2></div>
          <p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">Only sources in <b>ready</b> state can be built. ZIP remains unavailable until quarantine validation is connected.</p>
          <select className="input mt-4" value={sourceId} onChange={(event) => setSourceId(event.target.value)}><option value="">Select a ready source</option>{sources.filter((row) => row.status === "ready").map((row) => <option key={row.id} value={row.id}>{row.source_type === "git" ? `${row.repository_url} · ${row.repository_branch || "main"}` : row.original_filename}</option>)}</select>
          <button className="btn-primary mt-3" disabled={!canManage || !projectId || !sourceId || saving} onClick={() => void queueBuild()}><Play size={14}/>{saving ? "Working…" : "Build & deploy"}</button>
        </div>
      </section>

      <section className="surface-card overflow-hidden">
        <div className="border-b p-4"><h2 className="text-sm font-black">Build history</h2></div>
        <div className="space-y-2 p-4">{builds.map((row) => <div key={row.id} className="rounded-xl border p-3 text-xs"><div className="flex flex-wrap items-center justify-between gap-2"><b>{row.runtime} build</b><span>{row.status}</span></div><p className="mt-1 text-[var(--admin-muted)]">{row.source_commit ? `Commit ${row.source_commit.slice(0, 12)}` : "Awaiting source commit"}{row.image_ref ? ` · ${row.image_ref}` : ""}</p>{row.failure_message ? <p className="mt-2 text-red-700">{row.failure_message}</p> : null}</div>)}{!builds.length ? <p className="text-xs text-[var(--admin-muted)]">No builds for this project yet.</p> : null}</div>
      </section>

      <section className="rounded-3xl bg-[#123a38] p-5 text-white"><div className="flex gap-3"><ShieldCheck size={20} className="text-[#f1de8b]"/><p className="text-xs leading-6 text-white/70">The builder receives source credentials only for the claimed job and never receives production hosting-node credentials. Production accepts only digest-pinned images from the approved Ithute hosting namespace.</p></div></section>
    </div>
  </ControlShell>;
}
