"use client";

import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import { FileArchive, RefreshCw, ShieldCheck, UploadCloud } from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";
import { PageHeader } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";
const MAX_ZIP_BYTES = 2 * 1024 * 1024 * 1024;

type Me = { email: string; is_platform_owner: boolean };
type Context = { tenant_id: string; tenant_name: string; role: string; access_kind: string; permissions?: string[] };
type Project = { id: string; name: string; runtime: string; status: string };
type Source = { id: string; status: string; original_filename?: string | null };
type Ticket = { upload_token: string; upload_url: string | null; expires_at: string; method: string; content_type: string };

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

function uploadZip(url: string, token: string, file: File, onProgress: (percent: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url, true);
    xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.setRequestHeader("Content-Type", "application/zip");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
    };
    xhr.onerror = () => reject(new Error("Network error while uploading ZIP archive."));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) { onProgress(100); resolve(); return; }
      try {
        const body = JSON.parse(xhr.responseText || "{}");
        reject(new Error(typeof body.detail === "string" ? body.detail : `ZIP upload failed with HTTP ${xhr.status}.`));
      } catch {
        reject(new Error(`ZIP upload failed with HTTP ${xhr.status}.`));
      }
    };
    xhr.send(file);
  });
}

export default function HostingUploadPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [contexts, setContexts] = useState<Context[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState<"idle" | "registering" | "uploading" | "verifying" | "complete">("idle");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const selectedContext = useMemo(() => contexts.find((row) => row.tenant_id === tenantId), [contexts, tenantId]);
  const canManage = Boolean(me?.is_platform_owner || selectedContext?.role === "tenant_admin" || selectedContext?.role === "reseller_admin" || selectedContext?.permissions?.includes("hosting.manage"));
  const busy = stage !== "idle" && stage !== "complete";

  async function loadProjects(id: string) {
    if (!id) return;
    const response = await api(`/tenants/${id}/hosting/projects`);
    if (!response.ok) { setProjects([]); setProjectId(""); setError(await detail(response, "Unable to load hosted projects.")); return; }
    const rows: Project[] = (await response.json()).items || [];
    setProjects(rows);
    setProjectId((current) => rows.some((row) => row.id === current) ? current : rows[0]?.id || "");
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
    void loadProjects(tenantId);
  }, [tenantId]);

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    setError(""); setMessage(""); setProgress(0); setStage("idle");
    const selected = event.target.files?.[0] || null;
    if (!selected) { setFile(null); return; }
    if (!selected.name.toLowerCase().endsWith(".zip")) { setFile(null); setError("Choose a .zip source archive."); return; }
    if (selected.size <= 0 || selected.size > MAX_ZIP_BYTES) { setFile(null); setError("ZIP archives must be larger than 0 bytes and no larger than 2 GiB."); return; }
    setFile(selected);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tenantId || !projectId || !file || !canManage || busy) return;
    setError(""); setMessage(""); setProgress(0); setStage("registering");
    try {
      const register = await api(`/tenants/${tenantId}/hosting/projects/${projectId}/sources/zip`, {
        method: "POST",
        body: JSON.stringify({ original_filename: file.name, size_bytes: file.size, sha256: null }),
      });
      if (!register.ok) throw new Error(await detail(register, "Unable to register ZIP source."));
      const source: Source = await register.json();

      const ticketResponse = await api(`/tenants/${tenantId}/hosting/projects/${projectId}/sources/${source.id}/upload-ticket`, { method: "POST" });
      if (!ticketResponse.ok) throw new Error(await detail(ticketResponse, "Unable to create secure ZIP upload ticket."));
      const ticket: Ticket = await ticketResponse.json();
      if (!ticket.upload_url) throw new Error("ZIP upload service is not configured for this Ithute environment.");

      setStage("uploading");
      await uploadZip(ticket.upload_url, ticket.upload_token, file, setProgress);
      setStage("verifying");
      const sourcesResponse = await api(`/tenants/${tenantId}/hosting/projects/${projectId}/sources`);
      if (!sourcesResponse.ok) throw new Error("ZIP uploaded, but Ithute could not refresh verification status.");
      const sources: Source[] = (await sourcesResponse.json()).items || [];
      const verified = sources.find((row) => row.id === source.id);
      if (!verified || verified.status !== "ready") throw new Error("Upload completed but the source is not verified yet. Refresh the source list before building.");
      setStage("complete");
      setMessage(`${file.name} passed quarantine checks and is ready for an isolated build.`);
    } catch (exc) {
      setStage("idle");
      setError(exc instanceof Error ? exc.message : "ZIP upload failed.");
    }
  }

  return <ControlShell title="ZIP source upload" subtitle="Quarantined source intake for shared hosting" userEmail={me?.email}>
    <div className="space-y-5">
      <PageHeader eyebrow="Shared hosting" title="Upload source ZIP" description="ZIP archives go directly to Ithute's isolated quarantine service. They are hashed and inspected before the build system can see them." />

      <section className="surface-card p-5">
        <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
          <label><span className="eyebrow-label">Organization / managed customer</span><select className="input mt-1" value={tenantId} disabled={busy} onChange={(event) => setTenantId(event.target.value)}>{contexts.map((row) => <option key={row.tenant_id} value={row.tenant_id}>{row.tenant_name}{row.access_kind === "reseller_customer" ? " · reseller customer" : ""}</option>)}</select></label>
          <label><span className="eyebrow-label">Hosted project</span><select className="input mt-1" value={projectId} disabled={busy} onChange={(event) => setProjectId(event.target.value)}><option value="">Select project</option>{projects.map((row) => <option key={row.id} value={row.id}>{row.name} · {row.runtime}</option>)}</select></label>
          <button className="btn-secondary" disabled={busy} onClick={() => void loadProjects(tenantId)}><RefreshCw size={14}/>Refresh</button>
        </div>
      </section>

      {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}

      <form className="surface-card p-5" onSubmit={submit}>
        <div className="flex items-start gap-3"><FileArchive size={22} className="mt-1 text-[#285b55]"/><div><h2 className="text-sm font-black">Source archive</h2><p className="mt-1 text-xs leading-5 text-[var(--admin-muted)]">Maximum 2 GiB compressed, 2 GiB unpacked, 100,000 files and 512 MiB per file. Traversal paths, symlinks, encrypted ZIPs, special files and extreme compression ratios are rejected.</p></div></div>
        <label className="mt-5 block rounded-2xl border border-dashed border-[#c8d5cf] bg-[#f7faf8] p-6 text-center"><UploadCloud size={26} className="mx-auto text-[#285b55]"/><span className="mt-2 block text-xs font-black">Choose ZIP source archive</span><input className="mt-3 text-xs" type="file" accept=".zip,application/zip" disabled={busy} onChange={chooseFile}/></label>
        {file ? <div className="mt-4 rounded-xl bg-[#f4f7f5] p-3 text-xs"><b>{file.name}</b> · {(file.size / 1024 / 1024).toFixed(2)} MB</div> : null}
        {busy || stage === "complete" ? <div className="mt-4"><div className="flex justify-between text-[10px] font-bold uppercase tracking-[.08em]"><span>{stage}</span><span>{progress}%</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-[#e4e9e6]"><div className="h-full bg-[#285b55] transition-all" style={{ width: `${progress}%` }}/></div></div> : null}
        <button className="btn-primary mt-5" disabled={!canManage || !projectId || !file || busy}><ShieldCheck size={14}/>{busy ? "Uploading securely…" : "Quarantine & verify ZIP"}</button>
      </form>

      <section className="rounded-3xl bg-[#123a38] p-6 text-white"><div className="flex items-start gap-4"><ShieldCheck size={22} className="mt-1 shrink-0 text-[#f1de8b]"/><div><h2 className="text-lg font-black">Untrusted ZIP bytes never pass through the main Ithute backend.</h2><p className="mt-2 max-w-3xl text-xs leading-6 text-white/65">The browser uploads directly with a short-lived one-time ticket. The quarantine service validates the archive and only verified bytes become visible to the isolated builder.</p></div></div></section>
    </div>
  </ControlShell>;
}
