"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  BellRing,
  Database,
  ExternalLink,
  HardDrive,
  RefreshCw,
  Server,
  ShieldCheck,
} from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { apiJson } from "@/lib/platform-api";

type LastDeployment = {
  id: string;
  version?: string | null;
  source_sha?: string | null;
  status: string;
  started_at: string;
  finished_at?: string | null;
};

type LastBackup = {
  id: string;
  status: string;
  restore_verified: boolean;
  created_at: string;
  verified_at?: string | null;
};

type ProductCard = {
  id: string;
  name: string;
  category: string;
  version?: string | null;
  status: string;
  maintenance_mode: boolean;
  public_url?: string | null;
  api_url?: string | null;
  health_url?: string | null;
  deployment_target?: string | null;
  database: { ownership: string; engine?: string | null; status: string };
  services: { auth: string; push: string; realtime: string; event_bus: string };
  containers: Record<string, unknown>;
  metrics: Record<string, unknown>;
  last_error?: string | null;
  last_seen_at?: string | null;
  last_deployment?: LastDeployment | null;
  last_backup?: LastBackup | null;
  event_count: number;
  open_security_events: number;
};

type ControlCenter = {
  products: ProductCard[];
  totals: {
    products: number;
    online: number;
    degraded: number;
    maintenance: number;
    unread_security: number;
    event_backlog: number;
  };
};

function badge(status: string) {
  const good = ["online", "healthy", "ok", "connected", "ready", "succeeded"].includes(status.toLowerCase());
  const bad = ["offline", "failed", "error"].includes(status.toLowerCase());
  return `rounded-full px-2.5 py-1 text-[9px] font-black uppercase tracking-[.08em] ${
    good ? "bg-emerald-50 text-emerald-700" : bad ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-700"
  }`;
}

function Metric({ label, value, note }: { label: string; value: number; note: string }) {
  return (
    <div className="surface-card p-4">
      <p className="text-[9px] font-black uppercase tracking-[.13em] text-[var(--admin-muted)]">{label}</p>
      <p className="mt-2 text-3xl font-black">{value}</p>
      <p className="mt-1 text-[10px] text-[var(--admin-muted)]">{note}</p>
    </div>
  );
}

export default function IthuteControlCenterPage() {
  const [data, setData] = useState<ControlCenter | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await apiJson<ControlCenter>("/platform/ithute/control-center", { ttlMs: 0, force: true }));
    } catch {
      setError("Unable to load the Ithute operating control center. Platform-owner access is required.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <ControlShell title="Ithute Platform" subtitle="Products, data boundaries, deployments, backups and service health">
      <div className="space-y-5">
        <section className="surface-card p-5 sm:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-[9px] font-black uppercase tracking-[.14em] text-[var(--admin-muted)]">Operating platform</p>
              <h1 className="mt-2 text-2xl font-black">Platform Control Center</h1>
              <p className="mt-2 max-w-3xl text-[11px] leading-5 text-[var(--admin-muted)]">
                One operational view across Mailbox, LoanHub, Ithute Pay and Ithute Tutor. Product databases remain isolated; this screen reads control-plane metadata and product heartbeats only.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link className="btn-secondary" href="/ithute-platform"><ShieldCheck size={14} />Auth & Push</Link>
              <Link className="btn-secondary" href="/ithute-account"><BellRing size={14} />Account & Apps</Link>
              <button className="btn-primary" disabled={loading} onClick={() => void load()}><RefreshCw size={14} className={loading ? "animate-spin" : ""} />Refresh</button>
            </div>
          </div>
          {error ? <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-[11px] font-bold text-red-700">{error}</div> : null}
        </section>

        {data ? (
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
            <Metric label="Products" value={data.totals.products} note="registered products" />
            <Metric label="Online" value={data.totals.online} note="healthy heartbeats" />
            <Metric label="Degraded" value={data.totals.degraded} note="needs attention" />
            <Metric label="Maintenance" value={data.totals.maintenance} note="maintenance mode" />
            <Metric label="Event backlog" value={data.totals.event_backlog} note="accepted / processing" />
            <Metric label="Security" value={data.totals.unread_security} note="open security events" />
          </section>
        ) : null}

        <section className="grid gap-4 xl:grid-cols-2">
          {data?.products.map((product) => (
            <article key={product.id} className="surface-card p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-black">{product.name}</h2>
                    <span className={badge(product.maintenance_mode ? "maintenance" : product.status)}>{product.maintenance_mode ? "maintenance" : product.status}</span>
                  </div>
                  <p className="mt-1 font-mono text-[9px] text-[var(--admin-muted)]">{product.id} · {product.category}</p>
                </div>
                {product.public_url ? <a className="icon-button" href={product.public_url} target="_blank" rel="noreferrer" title={`Open ${product.name}`}><ExternalLink size={14} /></a> : null}
              </div>

              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                <div className="rounded-xl border border-[var(--admin-line)] p-3">
                  <div className="flex items-center gap-2"><Database size={14} /><p className="text-[10px] font-black">Database</p></div>
                  <p className="mt-2 text-[10px]">{product.database.engine || "not reported"} · <span className={badge(product.database.status)}>{product.database.status}</span></p>
                  <p className="mt-2 text-[9px] text-[var(--admin-muted)]">Ownership: {product.database.ownership}</p>
                </div>
                <div className="rounded-xl border border-[var(--admin-line)] p-3">
                  <div className="flex items-center gap-2"><Server size={14} /><p className="text-[10px] font-black">Central services</p></div>
                  <p className="mt-2 text-[9px] leading-5 text-[var(--admin-muted)]">Auth {product.services.auth} · Push {product.services.push}<br />Realtime {product.services.realtime} · Events {product.services.event_bus}</p>
                </div>
              </div>

              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                <div className="rounded-xl bg-[#f7faf8] p-3"><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Version</p><p className="mt-1 text-[10px] font-black">{product.version || "unknown"}</p></div>
                <div className="rounded-xl bg-[#f7faf8] p-3"><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Events</p><p className="mt-1 text-[10px] font-black">{product.event_count}</p></div>
                <div className="rounded-xl bg-[#f7faf8] p-3"><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Security</p><p className="mt-1 text-[10px] font-black">{product.open_security_events}</p></div>
                <div className="rounded-xl bg-[#f7faf8] p-3"><p className="text-[8px] font-black uppercase text-[var(--admin-muted)]">Last seen</p><p className="mt-1 text-[9px] font-black">{product.last_seen_at ? new Date(product.last_seen_at).toLocaleString() : "No heartbeat"}</p></div>
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[var(--admin-line)] pt-4">
                <Link className="btn-secondary" href={`/ithute-platform/products/${encodeURIComponent(product.id)}`}><Activity size={14} />Open product</Link>
                <span className="ml-auto text-[9px] text-[var(--admin-muted)]">{product.deployment_target || "deployment target not reported"}</span>
              </div>
            </article>
          ))}
        </section>

        {!loading && data && !data.products.length ? (
          <div className="surface-card p-8 text-center text-sm text-[var(--admin-muted)]"><HardDrive className="mx-auto mb-3" />No products are registered.</div>
        ) : null}
      </div>
    </ControlShell>
  );
}
