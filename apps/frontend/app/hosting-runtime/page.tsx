"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, History, RefreshCw, RotateCcw, ScrollText, ServerCog } from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";
import { PageHeader } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Me = { email: string; is_platform_owner: boolean };
type Context = { tenant_id: string; tenant_name: string; role: string; access_kind: string; permissions?: string[] };
type Project = { id: string; name: string; runtime: string; status: string; hostname?: string | null };
type Deployment = { id: string; release_number: number; image_ref: string; source_commit?: string | null; status: string; failure_message?: string | null; created_at?: string | null; completed_at?: string | null; last_health_at?: string | null };
type ProjectOperation = { id: string; operation: "restart" | "logs"; status: string; requested_lines?: number | null; output?: string | null; failure_message?: string | null; created_at?: string | null; completed_at?: string | null };

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

export default function HostingRuntimePage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [contexts, setContexts] = useState<Context[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [operations, setOperations] = useState<ProjectOperation[]>([]);
  const [logLines, setLogLines] = useState(300);
  const [selectedLog, setSelectedLog] = useState<ProjectOperation | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const context = useMemo(() => contexts.find((row) => row.tenant_id === tenantId), [contexts, tenantId]);
  const canManage = Boolean(me?.is_platform_owner || context?.role === "tenant_admin" || context?.role === "reseller_admin" || context?.permissions?.includes("hosting.manage"));
  const project = projects.find((row) => row.id === projectId);
  const activeOperation = operations.find((row) => ["queued", "claimed"].includes(row.status));

  async function loadTenant(id: string) {
    if (!id) return;
    setError("");
    const response = await api(`/tenants/${id}/hosting/projects`);
    if (!response.ok) { setProjects([]); setProjectId(""); setError(await detail(response, "Unable to load hosted projects.")); return; }
    const rows: Project[] = (await response.json()).items || [];
    setProjects(rows);
    setProjectId((current) => rows.some((row) => row.id === current) ? current : rows[0]?.id || "");
  }

  async function loadProject(id: string) {
    if (!tenantId || !id) { setDeployments([]); setOperations([]); return; }
    const [deploymentResponse, operationResponse] = await Promise.all([
      api(`/tenants/${tenantId}/hosting/projects/${id}/deployments`),
      api(`/tenants/${tenantId}/hosting/projects/${id}/operations`),
    ]);
    setDeployments(deploymentResponse.ok ? (await deploymentResponse.json()).items || [] : []);
    const rows: ProjectOperation[] = operationResponse.ok ? (await operationResponse.json()).items || [] : [];
    setOperations(rows);
    const latestLog = rows.find((row) => row.operation === "logs" && row.status === "succeeded" && row.output);
    if (latestLog) setSelectedLog(latestLog);
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
    setSelectedLog(null);
    void loadTenant(tenantId);
  }, [tenantId]);

  useEffect(() => { void loadProject(projectId); }, [projectId, tenantId]);

  useEffect(() => {
    if (!projectId || !activeOperation) return;
    const timer = window.setInterval(() => void loadProject(projectId), 2500);
    return () => window.clearInterval(timer);
  }, [projectId, activeOperation?.id, activeOperation?.status]);

  async function restartProject() {
    if (!tenantId || !projectId || !canManage || saving) return;
    if (!window.confirm(`Restart ${project?.name || "this project"}? The container will restart and Ithute will wait for the private health check to pass.`)) return;
    setSaving(true); setError(""); setMessage("");
    const response = await api(`/tenants/${tenantId}/hosting/projects/${projectId}/restart`, { method: "POST" });
    if (!response.ok) { setError(await detail(response, "Unable to queue restart.")); setSaving(false); return; }
    setMessage("Restart queued on the assigned hosting node. Ithute will verify the private health endpoint after restart.");
    await loadProject(projectId); setSaving(false);
  }

  async function requestLogs() {
    if (!tenantId || !projectId || saving) return;
    setSaving(true); setError(""); setMessage("");
    const response = await api(`/tenants/${tenantId}/hosting/projects/${projectId}/logs`, { method: "POST", body: JSON.stringify({ lines: logLines }) });
    if (!response.ok) { setError(await detail(response, "Unable to request application logs.")); setSaving(false); return; }
    setMessage(`Requested the latest ${logLines} application log lines from the hosting node.`);
    await loadProject(projectId); setSaving(false);
  }

  async function rollback(row: Deployment) {
    if (!tenantId || !projectId || !canManage || saving) return;
    if (!window.confirm(`Roll back ${project?.name || "this project"} to healthy release #${row.release_number}?`)) return;
    setSaving(true); setError(""); setMessage("");
    const response = await api(`/tenants/${tenantId}/hosting/projects/${projectId}/deployments/${row.id}/rollback`, { method: "POST" });
    if (!response.ok) { setError(await detail(response, "Unable to queue rollback.")); setSaving(false); return; }
    setMessage(`Rollback to release #${row.release_number} queued as a new deployment.`);
    await loadProject(projectId); setSaving(false);
  }

  return <ControlShell title="Runtime & logs" subtitle="Health, restarts, logs and rollback for shared hosting" userEmail={me?.email}>
    <div className="space-y-5">
      <PageHeader eyebrow="Shared hosting" title="Runtime & logs" description="Operate a hosted application without VPS access. Restart the managed container, retrieve bounded application logs, inspect deployment health and roll back to a previous healthy release." />

      <section className="surface-card p-4"><div className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end"><label><span className="eyebrow-label">Organization / managed customer</span><select className="input mt-1" value={tenantId} onChange={(event) => setTenantId(event.target.value)}>{contexts.map((row) => <option key={row.tenant_id} value={row.tenant_id}>{row.tenant_name}{row.access_kind === "reseller_customer" ? " · reseller customer" : ""}</option>)}</select></label><label><span className="eyebrow-label">Hosted project</span><select className="input mt-1" value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Select project</option>{projects.map((row) => <option key={row.id} value={row.id}>{row.name} · {row.runtime}</option>)}</select></label><button className="btn-secondary" onClick={() => void loadProject(projectId)}><RefreshCw size={14}/>Refresh</button></div></section>

      {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}

      <section className="grid gap-4 md:grid-cols-3">
        <article className="surface-card p-4"><Activity size={18}/><p className="mt-2 text-lg font-black">{project?.status || "—"}</p><p className="text-[10px] text-[var(--admin-muted)]">Project runtime status</p>{project?.hostname ? <p className="mt-2 truncate text-[10px]">{project.hostname}</p> : null}</article>
        <article className="surface-card p-4"><History size={18}/><p className="mt-2 text-lg font-black">{deployments[0] ? `#${deployments[0].release_number}` : "—"}</p><p className="text-[10px] text-[var(--admin-muted)]">Latest deployment release</p><p className="mt-2 text-[10px]">{deployments[0]?.status || "No deployment yet"}</p></article>
        <article className="surface-card p-4"><ServerCog size={18}/><p className="mt-2 text-lg font-black">{activeOperation ? activeOperation.operation : "idle"}</p><p className="text-[10px] text-[var(--admin-muted)]">Node operation</p><p className="mt-2 text-[10px]">{activeOperation?.status || "No operation queued"}</p></article>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="surface-card p-5"><div className="flex items-center gap-2"><RotateCcw size={17}/><h2 className="text-sm font-black">Restart application</h2></div><p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">The hosting node derives the container identity from the project UUID, restarts only that managed container, then waits for the configured private health endpoint to pass.</p><button className="btn-primary mt-4" disabled={!canManage || project?.status !== "running" || Boolean(activeOperation) || saving} onClick={() => void restartProject()}><RotateCcw size={14}/>{saving ? "Working…" : "Restart & health-check"}</button></div>
        <div className="surface-card p-5"><div className="flex items-center gap-2"><ScrollText size={17}/><h2 className="text-sm font-black">Application logs</h2></div><p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">Retrieve a bounded snapshot from the managed container. Logs may contain values written by the application itself, so access follows the customer's hosting read permissions.</p><div className="mt-4 flex gap-2"><select className="input" value={logLines} onChange={(event) => setLogLines(Number(event.target.value))}><option value={100}>100 lines</option><option value={300}>300 lines</option><option value={500}>500 lines</option><option value={1000}>1,000 lines</option><option value={2000}>2,000 lines</option></select><button className="btn-secondary shrink-0" disabled={!projectId || Boolean(activeOperation) || saving} onClick={() => void requestLogs()}><ScrollText size={14}/>Fetch logs</button></div></div>
      </section>

      <section className="surface-card overflow-hidden"><div className="border-b p-4"><h2 className="text-sm font-black">Latest log snapshot</h2></div><div className="p-4">{selectedLog?.output ? <pre className="max-h-[34rem] overflow-auto whitespace-pre-wrap break-words rounded-xl bg-[#0e1817] p-4 text-[11px] leading-5 text-[#dce9e4]">{selectedLog.output}</pre> : <p className="text-xs text-[var(--admin-muted)]">Request logs to display a bounded snapshot here.</p>}</div></section>

      <section className="surface-card overflow-hidden"><div className="border-b p-4"><h2 className="text-sm font-black">Deployment history & rollback</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Rollback creates a new deployment using the selected healthy release's immutable image digest.</p></div><div className="space-y-2 p-4">{deployments.map((row) => <article key={row.id} className="rounded-xl border p-3 text-xs"><div className="flex flex-wrap items-start justify-between gap-3"><div><b>Release #{row.release_number}</b><p className="mt-1 text-[10px] text-[var(--admin-muted)]">{row.status}{row.source_commit ? ` · ${row.source_commit.slice(0, 12)}` : ""}{row.last_health_at ? ` · health ${new Date(row.last_health_at).toLocaleString()}` : ""}</p></div>{row.status === "healthy" && canManage ? <button className="btn-secondary" disabled={saving || Boolean(activeOperation)} onClick={() => void rollback(row)}><History size={13}/>Rollback here</button> : null}</div>{row.failure_message ? <p className="mt-2 text-red-700">{row.failure_message}</p> : null}</article>)}{!deployments.length ? <p className="text-xs text-[var(--admin-muted)]">No deployments yet.</p> : null}</div></section>

      <section className="surface-card overflow-hidden"><div className="border-b p-4"><h2 className="text-sm font-black">Recent runtime operations</h2></div><div className="space-y-2 p-4">{operations.slice(0, 20).map((row) => <button key={row.id} className="block w-full rounded-xl border p-3 text-left text-xs" onClick={() => row.operation === "logs" && row.output ? setSelectedLog(row) : undefined}><span className="font-black">{row.operation}</span> · {row.status}{row.requested_lines ? ` · ${row.requested_lines} lines` : ""}{row.failure_message ? <span className="mt-1 block text-red-700">{row.failure_message}</span> : null}</button>)}{!operations.length ? <p className="text-xs text-[var(--admin-muted)]">No runtime operations yet.</p> : null}</div></section>
    </div>
  </ControlShell>;
}
