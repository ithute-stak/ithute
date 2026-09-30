"use client";

import { useEffect, useMemo, useState } from "react";
import { Database, HardDrive, History, RefreshCw, RotateCcw, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";
import { PageHeader } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Me = { email: string; is_platform_owner: boolean };
type Context = { tenant_id: string; tenant_name: string; role: string; access_kind?: string; permissions?: string[] };
type HostingDatabase = { id: string; engine: string; database_name: string; status: string; operation?: string; storage_mb: number };
type Backup = {
  id: string;
  database_id: string;
  source_backup_id?: string | null;
  operation: "backup" | "restore";
  status: string;
  sha256?: string | null;
  size_bytes?: number | null;
  failure_message?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
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

function sizeLabel(bytes?: number | null) {
  if (!bytes) return "—";
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function HostingBackupsPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [contexts, setContexts] = useState<Context[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [databases, setDatabases] = useState<HostingDatabase[]>([]);
  const [databaseId, setDatabaseId] = useState("");
  const [backups, setBackups] = useState<Backup[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const selectedContext = useMemo(() => contexts.find((row) => row.tenant_id === tenantId), [contexts, tenantId]);
  const selectedDatabase = useMemo(() => databases.find((row) => row.id === databaseId), [databases, databaseId]);
  const canManage = Boolean(me?.is_platform_owner || selectedContext?.role === "tenant_admin" || selectedContext?.role === "reseller_admin" || selectedContext?.permissions?.includes("hosting.manage"));
  const activeOperation = backups.some((row) => ["queued", "claimed"].includes(row.status));

  async function loadDatabases(id: string) {
    if (!id) return;
    setError("");
    const response = await api(`/tenants/${id}/hosting/databases`);
    if (!response.ok) {
      setDatabases([]); setDatabaseId(""); setBackups([]);
      setError(await errorText(response, "Unable to load hosting databases."));
      return;
    }
    const rows: HostingDatabase[] = (await response.json()).items || [];
    setDatabases(rows);
    setDatabaseId((current) => rows.some((row) => row.id === current) ? current : rows[0]?.id || "");
  }

  async function loadBackups(id: string) {
    if (!tenantId || !id) { setBackups([]); return; }
    const response = await api(`/tenants/${tenantId}/hosting/databases/${id}/backups`);
    if (!response.ok) {
      setBackups([]);
      setError(await errorText(response, "Unable to load database backups."));
      return;
    }
    setBackups((await response.json()).items || []);
  }

  async function queueBackup() {
    if (!tenantId || !databaseId || !canManage || saving) return;
    setSaving(true); setError(""); setMessage("");
    const response = await api(`/tenants/${tenantId}/hosting/databases/${databaseId}/backups`, { method: "POST" });
    if (!response.ok) setError(await errorText(response, "Unable to queue database backup."));
    else setMessage("Database backup queued. The hosting node will create and checksum the native database dump.");
    await loadBackups(databaseId);
    setSaving(false);
  }

  async function restoreBackup(row: Backup) {
    if (!tenantId || !databaseId || !selectedDatabase || !canManage || saving) return;
    if (selectedDatabase.status !== "suspended") {
      setError("Suspend the database first. Ithute intentionally blocks restore while applications may still be writing to it.");
      return;
    }
    if (!window.confirm(`Restore ${selectedDatabase.database_name} from this verified backup? Existing database contents will be replaced.`)) return;
    setSaving(true); setError(""); setMessage("");
    const response = await api(`/tenants/${tenantId}/hosting/databases/${databaseId}/backups/${row.id}/restore`, { method: "POST" });
    if (!response.ok) setError(await errorText(response, "Unable to queue database restore."));
    else setMessage("Restore queued. The node will verify backup size and SHA-256 again before restoring it.");
    await loadBackups(databaseId);
    setSaving(false);
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
    void loadDatabases(tenantId);
  }, [tenantId]);

  useEffect(() => { void loadBackups(databaseId); }, [databaseId, tenantId]);

  return <ControlShell title="Database backups" subtitle="Verified PostgreSQL and MySQL backup and restore" userEmail={me?.email}>
    <div className="space-y-5">
      <PageHeader eyebrow="Shared hosting · disaster recovery" title="Database backups & restore" description="Create native PostgreSQL/MySQL backups and restore only from verified checksummed backups. Restore is deliberately restricted to suspended databases so application writes cannot race recovery." />

      <section className="surface-card p-4"><div className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end"><label><span className="eyebrow-label">Organization / managed customer</span><select className="input mt-1" value={tenantId} onChange={(event) => setTenantId(event.target.value)}>{contexts.map((row) => <option key={row.tenant_id} value={row.tenant_id}>{row.tenant_name}{row.access_kind === "reseller_customer" ? " · reseller customer" : ""}</option>)}</select></label><label><span className="eyebrow-label">Database</span><select className="input mt-1" value={databaseId} onChange={(event) => setDatabaseId(event.target.value)}><option value="">Select a database</option>{databases.map((row) => <option key={row.id} value={row.id}>{row.database_name} · {row.engine} · {row.status}</option>)}</select></label><button className="btn-secondary" onClick={() => databaseId ? void loadBackups(databaseId) : void loadDatabases(tenantId)}><RefreshCw size={14}/>Refresh</button></div></section>

      {message ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{message}</div> : null}
      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}

      {selectedDatabase ? <section className="grid gap-3 md:grid-cols-3"><article className="surface-card p-4"><Database size={17}/><p className="mt-2 text-lg font-black">{selectedDatabase.database_name}</p><p className="text-[10px] text-[var(--admin-muted)]">{selectedDatabase.engine} · {selectedDatabase.status}</p></article><article className="surface-card p-4"><HardDrive size={17}/><p className="mt-2 text-lg font-black">{(selectedDatabase.storage_mb / 1024).toFixed(1)} GB</p><p className="text-[10px] text-[var(--admin-muted)]">Allocated database storage</p></article><article className="surface-card p-4"><History size={17}/><p className="mt-2 text-lg font-black">{backups.filter((row) => row.operation === "backup" && row.status === "succeeded").length}</p><p className="text-[10px] text-[var(--admin-muted)]">Verified restore points</p></article></section> : null}

      <section className="surface-card p-5"><div className="flex flex-wrap items-center justify-between gap-4"><div><h2 className="text-sm font-black">Create restore point</h2><p className="mt-1 text-xs text-[var(--admin-muted)]">Backups are generated by the hosting-node agent using native database tooling and stored outside the database service.</p></div><button className="btn-primary" disabled={!canManage || !databaseId || saving || activeOperation || !selectedDatabase || !["ready", "suspended"].includes(selectedDatabase.status)} onClick={() => void queueBackup()}><HardDrive size={14}/>{saving ? "Working…" : "Back up now"}</button></div></section>

      <section className="surface-card overflow-hidden"><div className="border-b p-4"><h2 className="text-sm font-black">Backup & restore history</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">A restore never accepts an arbitrary file: the source must be a successful verified backup created for this same database.</p></div><div className="space-y-3 p-4">{backups.map((row) => <article key={row.id} className="rounded-2xl border p-4 text-xs"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-black">{row.operation === "backup" ? "Backup" : "Restore"}</p><p className="mt-1 text-[var(--admin-muted)]">{row.created_at ? new Date(row.created_at).toLocaleString() : "Queued"} · {sizeLabel(row.size_bytes)}</p>{row.sha256 ? <p className="mt-1 break-all font-mono text-[9px] text-[var(--admin-muted)]">sha256:{row.sha256}</p> : null}</div><span className="rounded-full bg-[#f4f7f5] px-2 py-1 text-[9px] font-black uppercase">{row.status}</span></div>{row.failure_message ? <p className="mt-3 rounded-lg bg-red-50 p-2 text-red-700">{row.failure_message}</p> : null}{canManage && row.operation === "backup" && row.status === "succeeded" ? <button className="btn-secondary mt-3" disabled={saving || activeOperation} onClick={() => void restoreBackup(row)}><RotateCcw size={13}/>Restore this backup</button> : null}</article>)}{!backups.length ? <p className="py-6 text-center text-xs text-[var(--admin-muted)]">No backup or restore history for this database.</p> : null}</div></section>

      <section className="rounded-3xl bg-[#123a38] p-5 text-white"><div className="flex gap-3"><ShieldCheck size={20} className="shrink-0 text-[#f1de8b]"/><p className="text-xs leading-6 text-white/70">Before restore, Ithute requires the database to remain suspended and the node verifies the stored backup size and SHA-256 again. PostgreSQL restores use pg_restore; MySQL restores use the managed mysql client with node-local administrative credentials.</p></div></section>
    </div>
  </ControlShell>;
}
