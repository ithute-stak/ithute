"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Activity, ArrowLeft, Database, HardDrive, PauseCircle, PlayCircle, RefreshCw, RotateCcw, Server, ShieldCheck } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { apiJson, apiMutation } from "@/lib/platform-api";

type Deployment = { id: string; version?: string | null; source_sha?: string | null; status: string; started_at: string; finished_at?: string | null; error?: string | null };
type Backup = { id: string; kind: string; status: string; restore_verified: boolean; size_bytes?: number | null; created_at: string; verified_at?: string | null };
type Product = {
  id: string; name: string; category: string; version?: string | null; status: string; maintenance_mode: boolean;
  public_url?: string | null; api_url?: string | null; health_url?: string | null; deployment_target?: string | null;
  database: { ownership: string; engine?: string | null; status: string };
  services: { auth: string; push: string; realtime: string; event_bus: string };
  containers: Record<string, unknown>; metrics: Record<string, unknown>; last_error?: string | null; last_seen_at?: string | null;
  metadata: Record<string, unknown>; deployments: Deployment[]; backups: Backup[];
};

function prettyBytes(value?: number | null) {
  if (!value) return "—";
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${value} B`;
}

export default function IthuteProductPage() {
  const params = useParams<{ productId: string }>();
  const productId = decodeURIComponent(params.productId || "");
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!productId) return;
    setLoading(true); setError("");
    try { setProduct(await apiJson<Product>(`/platform/ithute/products/${encodeURIComponent(productId)}`, { ttlMs: 0, force: true })); }
    catch { setError("Unable to load product operating data."); }
    finally { setLoading(false); }
  }, [productId]);

  useEffect(() => { void load(); }, [load]);

  async function command(commandType: string) {
    setNotice(""); setError("");
    try {
      await apiMutation(`/platform/ithute/products/${encodeURIComponent(productId)}/commands`, {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command_type: commandType, payload: {} }),
      });
      setNotice(`${commandType} queued for the authenticated ${productId} operations agent.`);
      await load();
    } catch { setError(`Unable to queue ${commandType}.`); }
  }

  return (
    <ControlShell title={product?.name || "Ithute Product"} subtitle="Product operations without cross-database access">
      <div className="space-y-5">
        <section className="surface-card p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <Link href="/ithute-platform/control-center" className="inline-flex items-center gap-1 text-[10px] font-black text-[var(--admin-pine)]"><ArrowLeft size={12} />Control Center</Link>
              <h1 className="mt-2 text-2xl font-black">{product?.name || productId}</h1>
              <p className="mt-1 text-[10px] text-[var(--admin-muted)]">{product?.category || "Loading"} · status {product?.status || "unknown"} · version {product?.version || "unknown"}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="btn-secondary" disabled={loading} onClick={() => void load()}><RefreshCw size={14} className={loading ? "animate-spin" : ""} />Refresh</button>
              {product?.maintenance_mode ? <button className="btn-secondary" onClick={() => void command("maintenance.disable")}><PlayCircle size={14} />End maintenance</button> : <button className="btn-secondary" onClick={() => void command("maintenance.enable")}><PauseCircle size={14} />Maintenance</button>}
              <button className="btn-secondary" onClick={() => void command("backup")}><HardDrive size={14} />Backup</button>
              <button className="btn-secondary" onClick={() => void command("healthcheck")}><Activity size={14} />Health check</button>
            </div>
          </div>
          {notice ? <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-[10px] font-bold text-emerald-700">{notice}</div> : null}
          {error ? <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-[10px] font-bold text-red-700">{error}</div> : null}
        </section>

        {product ? <>
          <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div className="surface-card p-4"><Database size={17} /><p className="mt-3 text-[9px] font-black uppercase text-[var(--admin-muted)]">Database</p><p className="mt-1 text-sm font-black">{product.database.status}</p><p className="mt-1 text-[9px] text-[var(--admin-muted)]">{product.database.engine || "unknown"} · ownership {product.database.ownership}</p></div>
            <div className="surface-card p-4"><ShieldCheck size={17} /><p className="mt-3 text-[9px] font-black uppercase text-[var(--admin-muted)]">Auth / Push</p><p className="mt-1 text-sm font-black">{product.services.auth} / {product.services.push}</p><p className="mt-1 text-[9px] text-[var(--admin-muted)]">Central infrastructure only</p></div>
            <div className="surface-card p-4"><Server size={17} /><p className="mt-3 text-[9px] font-black uppercase text-[var(--admin-muted)]">Realtime / Events</p><p className="mt-1 text-sm font-black">{product.services.realtime} / {product.services.event_bus}</p><p className="mt-1 text-[9px] text-[var(--admin-muted)]">Product business state stays local</p></div>
            <div className="surface-card p-4"><Activity size={17} /><p className="mt-3 text-[9px] font-black uppercase text-[var(--admin-muted)]">Last heartbeat</p><p className="mt-1 text-sm font-black">{product.last_seen_at ? new Date(product.last_seen_at).toLocaleString() : "Not reported"}</p><p className="mt-1 text-[9px] text-[var(--admin-muted)]">{product.last_error || "No current error"}</p></div>
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <div className="surface-card p-5"><h2 className="text-sm font-black">Containers</h2><pre className="mt-3 max-h-72 overflow-auto rounded-xl bg-[#f7faf8] p-3 text-[9px] leading-5">{JSON.stringify(product.containers || {}, null, 2)}</pre></div>
            <div className="surface-card p-5"><h2 className="text-sm font-black">Metrics</h2><pre className="mt-3 max-h-72 overflow-auto rounded-xl bg-[#f7faf8] p-3 text-[9px] leading-5">{JSON.stringify(product.metrics || {}, null, 2)}</pre></div>
          </section>

          <section className="surface-card p-5">
            <div className="flex items-center gap-2"><RotateCcw size={16} /><h2 className="text-sm font-black">Deployments</h2></div>
            <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[720px] text-left text-[10px]"><thead><tr><th className="p-2">Started</th><th className="p-2">Version</th><th className="p-2">Commit</th><th className="p-2">Status</th><th className="p-2">Error</th></tr></thead><tbody>{product.deployments.map(item => <tr key={item.id} className="border-t border-[var(--admin-line)]"><td className="p-2">{new Date(item.started_at).toLocaleString()}</td><td className="p-2">{item.version || "—"}</td><td className="p-2 font-mono">{item.source_sha?.slice(0, 12) || "—"}</td><td className="p-2 font-black">{item.status}</td><td className="p-2 text-[var(--admin-muted)]">{item.error || "—"}</td></tr>)}</tbody></table></div>
          </section>

          <section className="surface-card p-5">
            <div className="flex items-center gap-2"><HardDrive size={16} /><h2 className="text-sm font-black">Backups</h2></div>
            <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[650px] text-left text-[10px]"><thead><tr><th className="p-2">Created</th><th className="p-2">Kind</th><th className="p-2">Size</th><th className="p-2">Status</th><th className="p-2">Restore verified</th></tr></thead><tbody>{product.backups.map(item => <tr key={item.id} className="border-t border-[var(--admin-line)]"><td className="p-2">{new Date(item.created_at).toLocaleString()}</td><td className="p-2">{item.kind}</td><td className="p-2">{prettyBytes(item.size_bytes)}</td><td className="p-2 font-black">{item.status}</td><td className="p-2">{item.restore_verified ? "Yes" : "No"}</td></tr>)}</tbody></table></div>
          </section>
        </> : null}
      </div>
    </ControlShell>
  );
}
