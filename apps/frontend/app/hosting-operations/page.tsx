"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { CheckCircle2, History, KeyRound, RefreshCw, Rocket, RotateCcw, ShieldCheck, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";
import { PageHeader } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Me = { email: string; is_platform_owner: boolean };
type Membership = { tenant_id: string; tenant_name: string; role: string; status: string };
type Project = { id: string; name: string; slug: string; status: string; hostname?: string | null; runtime: string; image_ref?: string | null };
type EnvironmentRow = { key: string; is_secret: boolean; has_value: boolean; updated_at?: string | null };
type Deployment = {
  id: string;
  release_number: number;
  image_ref: string;
  image_digest: string;
  source_commit?: string | null;
  status: string;
  failure_message?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
  last_health_at?: string | null;
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

async function errorText(response: Response, fallback: string) {
  const body = await response.json().catch(() => ({}));
  return typeof body.detail === "string" ? body.detail : fallback;
}

function deploymentBadge(status: string) {
  if (status === "healthy") return "bg-emerald-50 text-emerald-700";
  if (status === "failed") return "bg-red-50 text-red-700";
  if (status === "running" || status === "claimed") return "bg-blue-50 text-blue-700";
  return "bg-amber-50 text-amber-700";
}

export default function HostingOperationsPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [contexts, setContexts] = useState<Membership[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [environment, setEnvironment] = useState<EnvironmentRow[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const selectedContext = useMemo(() => contexts.find((row) => row.tenant_id === tenantId), [contexts, tenantId]);
  const selectedProject = useMemo(() => projects.find((row) => row.id === projectId), [projects, projectId]);
  const canManage = Boolean(me?.is_platform_owner || selectedContext?.role === "tenant_admin");

  async function loadProjects(id: string) {
    if (!id) return;
    setLoading(true);
    const response = await api(`/tenants/${id}/hosting/projects`);
    if (!response.ok) {
      setProjects([]);
      setProjectId("");
      setError(await errorText(response, "Unable to load hosted projects."));
      setLoading(false);
      return;
    }
    const rows: Project[] = (await response.json()).items || [];
    setProjects(rows);
    setProjectId((current) => rows.some((row) => row.id === current) ? current : rows[0]?.id || "");
    setLoading(false);
  }

  async function loadOperations(id: string) {
    if (!tenantId || !id) {
      setEnvironment([]);
      setDeployments([]);
      return;
    }
    const [environmentResponse, deploymentsResponse] = await Promise.all([
      api(`/tenants/${tenantId}/hosting/projects/${id}/environment`),
      api(`/tenants/${tenantId}/hosting/projects/${id}/deployments`),
    ]);
    if (environmentResponse.ok) setEnvironment((await environmentResponse.json()).items || []);
    if (deploymentsResponse.ok) setDeployments((await deploymentsResponse.json()).items || []);
  }

  useEffect(() => {
    void (async () => {
      const meResponse = await api("/auth/me");
      if (meResponse.status === 401) { router.replace("/login"); return; }
      if (!meResponse.ok) return;
      const current: Me = await meResponse.json();
      setMe(current);
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
      setTenantId(rows.find((row) => row.tenant_id === remembered)?.tenant_id || rows[0]?.tenant_id || "");
    })();
  }, [router]);

  useEffect(() => {
    if (!tenantId) return;
    window.localStorage.setItem("mailbox_dns_tenant", tenantId);
    setMessage("");
    setError("");
    void loadProjects(tenantId);
  }, [tenantId]);

  useEffect(() => { void loadOperations(projectId); }, [projectId, tenantId]);

  async function saveEnvironment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const key = String(data.get("key") || "").trim().toUpperCase();
    setSaving(true); setError(""); setMessage("");
    const response = await api(`/tenants/${tenantId}/hosting/projects/${projectId}/environment/${encodeURIComponent(key)}`, {
      method: "PUT",
      body: JSON.stringify({ value: String(data.get("value") || ""), is_secret: data.get("secret") === "on" }),
    });
    if (!response.ok) setError(await errorText(response, "Unable to save environment variable."));
    else {
      setMessage(`${key} saved. Values are encrypted and are never returned to the browser after write.`);
      form.reset();
      await loadOperations(projectId);
    }
    setSaving(false);
  }

  async function removeEnvironment(key: string) {
    const response = await api(`/tenants/${tenantId}/hosting/projects/${projectId}/environment/${encodeURIComponent(key)}`, { method: "DELETE" });
    if (!response.ok) setError(await errorText(response, "Unable to delete environment variable."));
    else { setMessage(`${key} removed.`); await loadOperations(projectId); }
  }

  async function queueDeployment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setSaving(true); setError(""); setMessage("");
    const response = await api(`/tenants/${tenantId}/hosting/projects/${projectId}/deployments`, {
      method: "POST",
      body: JSON.stringify({ image_ref: String(data.get("image_ref") || ""), source_commit: String(data.get("source_commit") || "") || null }),
    });
    if (!response.ok) setError(await errorText(response, "Unable to queue deployment."));
    else {
      const deployment = await response.json();
      setMessage(`Release #${deployment.release_number} queued for the assigned hosting node.`);
      form.reset();
      await loadOperations(projectId);
      await loadProjects(tenantId);
    }
    setSaving(false);
  }

  async function rollback(deployment: Deployment) {
    const response = await api(`/tenants/${tenantId}/hosting/projects/${projectId}/deployments/${deployment.id}/rollback`, { method: "POST" });
    if (!response.ok) setError(await errorText(response, "Unable to queue rollback."));
    else { const created = await response.json(); setMessage(`Rollback queued as release #${created.release_number}.`); await loadOperations(projectId); }
  }

  return <ControlShell title="Hosting operations" subtitle="Immutable releases, encrypted environment values and rollback history" userEmail={me?.email}>
    <div className="space-y-5">
      <PageHeader eyebrow="Application runtime" title="Deployments & environment" description="Operate hosted projects through immutable container-image releases. The web control plane never receives Docker-host access; a scoped node agent claims deployment manifests and reports health." />

      <section className="surface-card p-4 sm:p-5"><div className="grid gap-3 md:grid-cols-2"><label><span className="eyebrow-label">Organization</span><select className="input mt-1" value={tenantId} onChange={(event) => setTenantId(event.target.value)}>{contexts.map((row) => <option key={row.tenant_id} value={row.tenant_id}>{row.tenant_name}</option>)}</select></label><label><span className="eyebrow-label">Hosted project</span><select className="input mt-1" value={projectId} onChange={(event) => setProjectId(event.target.value)} disabled={!projects.length}>{projects.map((project) => <option key={project.id} value={project.id}>{project.name} · {project.status}</option>)}</select></label></div><div className="mt-3 flex items-center justify-between gap-3"><p className="text-[10px] text-[var(--admin-muted)]">{selectedProject ? `${selectedProject.runtime}${selectedProject.hostname ? ` · ${selectedProject.hostname}` : ""}` : loading ? "Loading projects…" : "No hosted project selected."}</p><button className="btn-secondary" onClick={() => void loadOperations(projectId)} disabled={!projectId}><RefreshCw size={14}/>Refresh</button></div></section>

      {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}

      {projectId ? <section className="grid gap-4 xl:grid-cols-2">
        <div className="surface-card p-5"><div className="flex items-start gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf4f1] text-[#285b55]"><Rocket size={18}/></span><div><h2 className="text-sm font-black">Queue immutable release</h2><p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">Build outside production, then supply the content-addressed image. Mutable tags such as <code>:latest</code> are rejected.</p></div></div>{canManage ? <form className="mt-5 space-y-3" onSubmit={queueDeployment}><label className="block"><span className="eyebrow-label">Container image</span><input className="input mt-1" name="image_ref" required placeholder="ghcr.io/company/app@sha256:…"/></label><label className="block"><span className="eyebrow-label">Source commit</span><input className="input mt-1" name="source_commit" placeholder="Git commit SHA (optional)"/></label><button className="btn-primary" disabled={saving}><Rocket size={14}/>Queue deployment</button></form> : <p className="mt-5 text-xs text-[var(--admin-muted)]">Read-only access.</p>}</div>

        <div className="surface-card p-5"><div className="flex items-start gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf4f1] text-[#285b55]"><KeyRound size={18}/></span><div><h2 className="text-sm font-black">Environment configuration</h2><p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">Values are encrypted at rest. The browser can see names and metadata after save, never stored values.</p></div></div>{canManage ? <form className="mt-5 grid gap-3 sm:grid-cols-[1fr_1.4fr_auto]" onSubmit={saveEnvironment}><input className="input" name="key" required pattern="[A-Za-z_][A-Za-z0-9_]*" placeholder="DATABASE_URL"/><input className="input" name="value" type="password" required placeholder="Value"/><label className="flex items-center gap-2 rounded-xl border border-[#dce5e0] px-3 text-[10px] font-bold"><input type="checkbox" name="secret" defaultChecked/>Secret</label><button className="btn-primary sm:col-span-3" disabled={saving}><ShieldCheck size={14}/>Encrypt & save</button></form> : null}<div className="mt-4 space-y-2">{environment.map((row) => <div key={row.key} className="flex items-center justify-between gap-3 rounded-xl border border-[#e3e9e6] p-3"><div><p className="text-xs font-black">{row.key}</p><p className="mt-0.5 text-[9px] text-[var(--admin-muted)]">{row.is_secret ? "Secret" : "Protected value"} · value hidden</p></div>{canManage ? <button className="icon-button" aria-label={`Delete ${row.key}`} onClick={() => void removeEnvironment(row.key)}><Trash2 size={14}/></button> : null}</div>)}{!environment.length ? <p className="text-[10px] text-[var(--admin-muted)]">No environment values configured.</p> : null}</div></div>
      </section> : null}

      {projectId ? <section className="surface-card overflow-hidden"><div className="flex items-center gap-3 border-b border-[#e4e9e6] p-4"><History size={17} className="text-[#285b55]"/><div><h2 className="text-sm font-black">Release history</h2><p className="text-[10px] text-[var(--admin-muted)]">Healthy historical releases remain eligible as rollback targets.</p></div></div><div className="space-y-2 p-4">{deployments.map((deployment) => <article key={deployment.id} className="rounded-2xl border border-[#dce5e0] bg-white p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-black">Release #{deployment.release_number}</p><p className="mt-1 max-w-3xl break-all text-[9px] text-[var(--admin-muted)]">{deployment.image_ref}</p></div><span className={`rounded-full px-2 py-1 text-[9px] font-black ${deploymentBadge(deployment.status)}`}>{deployment.status}</span></div><div className="mt-3 flex flex-wrap items-center gap-3 text-[9px] text-[var(--admin-muted)]"><span>{deployment.source_commit ? `commit ${deployment.source_commit.slice(0, 12)}` : "no source commit"}</span><span>{deployment.created_at ? new Date(deployment.created_at).toLocaleString() : ""}</span>{deployment.last_health_at ? <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircle2 size={12}/>healthy {new Date(deployment.last_health_at).toLocaleString()}</span> : null}</div>{deployment.failure_message ? <p className="mt-3 rounded-xl bg-red-50 p-3 text-[10px] text-red-700">{deployment.failure_message}</p> : null}{canManage && deployment.status === "healthy" ? <button className="btn-secondary mt-3" onClick={() => void rollback(deployment)}><RotateCcw size={13}/>Rollback to this release</button> : null}</article>)}{!deployments.length ? <p className="p-3 text-xs text-[var(--admin-muted)]">No releases yet. Build an image in the approved isolated pipeline and queue its immutable digest here.</p> : null}</div></section> : null}
    </div>
  </ControlShell>;
}
