"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  HardDrive,
  Mail,
  RefreshCw,
  Server,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type NodeRow = {
  id: string;
  name: string;
  hostname: string;
  region: string;
  status: string;
  ready: boolean;
  heartbeat_fresh: boolean;
  last_heartbeat_at?: string | null;
  smtp_ready: boolean;
  imap_ready: boolean;
  tls_ready: boolean;
  backup_ready: boolean;
  readiness_error?: string | null;
  backup_error?: string | null;
  total_storage_bytes?: number | null;
  used_storage_bytes?: number | null;
  storage_percent?: number | null;
  latest_backup_at?: string | null;
  latest_backup_key?: string | null;
};

type OperationRow = {
  id: string;
  node_id: string;
  operation: string;
  status: string;
  failure_message?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
};

type Noc = {
  overall_status: "healthy" | "attention" | "critical";
  checked_at: string;
  summary: {
    nodes_total: number;
    nodes_active: number;
    nodes_ready: number;
    mailboxes_total: number;
    mailboxes_external: number;
    mail_domains: number;
    failed_recent_operations: number;
  };
  runtime: {
    status?: string;
    services?: Record<string, string>;
    mail_queue_total?: number | null;
    error?: string;
  };
  queue: Record<string, unknown>;
  tls: Record<string, unknown>;
  nodes: NodeRow[];
  recent_operations: OperationRow[];
};

async function api(path: string) {
  let response = await fetch(`${API}${path}`, { credentials: "include", cache: "no-store" });
  if (response.status === 401) {
    const refresh = await fetch(`${API}/auth/refresh`, { method: "POST", credentials: "include" });
    if (refresh.ok) response = await fetch(`${API}${path}`, { credentials: "include", cache: "no-store" });
  }
  return response;
}

function bytes(value?: number | null) {
  if (!value) return "—";
  if (value >= 1024 ** 4) return `${(value / 1024 ** 4).toFixed(1)} TB`;
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  return `${Math.round(value / 1024 ** 2)} MB`;
}

function fmt(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function statusClass(value: string) {
  if (value === "healthy" || value === "ok" || value === "completed" || value === "ready") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (value === "critical" || value === "failed" || value === "down") return "border-rose-200 bg-rose-50 text-rose-700";
  return "border-amber-200 bg-amber-50 text-amber-700";
}

export default function MailOperationsNocPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [data, setData] = useState<Noc | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const failedOps = useMemo(() => data?.recent_operations.filter((item) => item.status === "failed") || [], [data]);

  async function load() {
    setLoading(true);
    setError("");
    const [meResponse, nocResponse] = await Promise.all([api("/auth/me"), api("/operations/mail-noc")]);
    if (meResponse.status === 401) {
      router.replace("/login");
      return;
    }
    if (meResponse.ok) {
      const me = await meResponse.json();
      setEmail(me.email || "");
      if (!me.is_platform_owner) {
        setError("Platform owner access is required.");
        setLoading(false);
        return;
      }
    }
    if (!nocResponse.ok) {
      setError(nocResponse.status === 403 ? "Platform owner access is required." : "Unable to load mail operations data.");
      setLoading(false);
      return;
    }
    setData(await nocResponse.json());
    setLoading(false);
  }

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 30000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <ControlShell title="Mail operations" subtitle="Network operations centre for Ithute email infrastructure" userEmail={email}>
      <div className="space-y-4">
        <section className="panel">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="eyebrow-admin"><Activity size={13}/>Operations · NOC</p>
              <h1 className="mt-2 text-2xl font-black tracking-tight text-[#21342a]">Mail operations centre</h1>
              <p className="mt-1 max-w-3xl text-xs leading-5 text-[var(--admin-muted)]">
                One operator view for service health, mail-node readiness, storage, backups, mail queues and infrastructure failures.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link href="/mail-nodes" className="btn-secondary"><Server size={14}/>Manage mail nodes</Link>
              <Link href="/delivery" className="btn-secondary"><Mail size={14}/>Delivery & queues</Link>
              <button className="btn-primary" onClick={() => void load()} disabled={loading}>
                <RefreshCw size={14} className={loading ? "animate-spin" : ""}/>{loading ? "Refreshing…" : "Refresh"}
              </button>
            </div>
          </div>
        </section>

        {error ? <div className="alert-error"><AlertTriangle size={15}/>{error}</div> : null}

        {data ? (
          <>
            <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
              <div className="panel">
                <p className="section-kicker">Overall</p>
                <div className="mt-2 flex items-center justify-between">
                  <strong className="text-lg font-black capitalize">{data.overall_status}</strong>
                  <span className={`rounded-full border px-2 py-1 text-[9px] font-black uppercase ${statusClass(data.overall_status)}`}>{data.overall_status}</span>
                </div>
              </div>
              <div className="panel"><p className="section-kicker">Mail nodes</p><p className="mt-2 text-2xl font-black">{data.summary.nodes_ready}/{data.summary.nodes_active}</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">ready / active</p></div>
              <div className="panel"><p className="section-kicker">Mailboxes</p><p className="mt-2 text-2xl font-black">{data.summary.mailboxes_total}</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">{data.summary.mailboxes_external} on external nodes</p></div>
              <div className="panel"><p className="section-kicker">Mail domains</p><p className="mt-2 text-2xl font-black">{data.summary.mail_domains}</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">mail-enabled domains</p></div>
              <div className="panel"><p className="section-kicker">Queue</p><p className="mt-2 text-2xl font-black">{data.runtime.mail_queue_total ?? "—"}</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">messages reported by telemetry</p></div>
              <div className="panel"><p className="section-kicker">Failed ops</p><p className="mt-2 text-2xl font-black text-rose-700">{data.summary.failed_recent_operations}</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">recent node operations</p></div>
            </section>

            <section className="grid gap-4 xl:grid-cols-[1.35fr_.65fr]">
              <div className="panel">
                <div className="flex items-center justify-between">
                  <div><p className="section-kicker"><Server size={12} className="mr-1 inline"/>Fleet</p><h2 className="section-title">Mail-node readiness</h2></div>
                  <span className="text-[10px] text-[var(--admin-muted)]">Checked {fmt(data.checked_at)}</span>
                </div>
                <div className="mt-4 space-y-3">
                  {data.nodes.length ? data.nodes.map((node) => (
                    <article key={node.id} className="rounded-xl border border-[var(--admin-line)] p-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="font-black text-[#21342a]">{node.name}</p>
                            <span className={`rounded-full border px-2 py-1 text-[9px] font-black uppercase ${statusClass(node.ready ? "ready" : node.status)}`}>
                              {node.ready ? "ready" : node.status}
                            </span>
                          </div>
                          <p className="mt-1 text-[10px] text-[var(--admin-muted)]">{node.hostname} · {node.region} · heartbeat {fmt(node.last_heartbeat_at)}</p>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {[
                            ["SMTP", node.smtp_ready],
                            ["IMAP", node.imap_ready],
                            ["TLS", node.tls_ready],
                            ["Backup", node.backup_ready],
                          ].map(([label, ok]) => (
                            <span key={String(label)} className={`rounded-full border px-2 py-1 text-[9px] font-black ${statusClass(ok ? "ready" : "attention")}`}>{label} {ok ? "✓" : "!"}</span>
                          ))}
                        </div>
                      </div>
                      <div className="mt-3 grid gap-3 sm:grid-cols-3">
                        <div className="rounded-lg bg-[#f6f8f7] p-3"><p className="section-kicker">Storage</p><p className="mt-1 text-xs font-black">{bytes(node.used_storage_bytes)} / {bytes(node.total_storage_bytes)}</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">{node.storage_percent === null || node.storage_percent === undefined ? "Awaiting capacity" : `${node.storage_percent}% used`}</p></div>
                        <div className="rounded-lg bg-[#f6f8f7] p-3"><p className="section-kicker">Latest backup</p><p className="mt-1 text-xs font-black">{fmt(node.latest_backup_at)}</p><p className="mt-1 truncate text-[10px] text-[var(--admin-muted)]">{node.latest_backup_key || "No ready snapshot"}</p></div>
                        <div className="rounded-lg bg-[#f6f8f7] p-3"><p className="section-kicker">Readiness</p><p className="mt-1 text-xs font-black">{node.heartbeat_fresh ? "Heartbeat fresh" : "Heartbeat stale"}</p><p className="mt-1 text-[10px] text-rose-700">{node.readiness_error || node.backup_error || "No reported error"}</p></div>
                      </div>
                    </article>
                  )) : <p className="py-6 text-center text-xs text-[var(--admin-muted)]">No mail nodes registered.</p>}
                </div>
              </div>

              <div className="space-y-4">
                <section className="panel">
                  <p className="section-kicker"><ShieldCheck size={12} className="mr-1 inline"/>Core services</p>
                  <h2 className="section-title">Runtime status</h2>
                  <div className="mt-4 space-y-2">
                    {Object.entries(data.runtime.services || {}).map(([name, value]) => (
                      <div key={name} className="flex items-center justify-between rounded-lg bg-[#f6f8f7] px-3 py-2 text-xs">
                        <span className="font-bold capitalize">{name.replaceAll("_", " ")}</span>
                        <span className={`rounded-full border px-2 py-1 text-[9px] font-black uppercase ${statusClass(value)}`}>{value}</span>
                      </div>
                    ))}
                    {data.runtime.error ? <p className="text-[10px] text-rose-700">{data.runtime.error}</p> : null}
                  </div>
                </section>

                <section className="panel">
                  <p className="section-kicker"><HardDrive size={12} className="mr-1 inline"/>Transport</p>
                  <h2 className="section-title">Queue & TLS diagnostics</h2>
                  <div className="mt-3 space-y-3 text-[10px]">
                    <div className="rounded-lg bg-[#f6f8f7] p-3"><p className="font-black">Queue summary</p><pre className="mt-2 whitespace-pre-wrap break-words text-[9px] text-[var(--admin-muted)]">{JSON.stringify(data.queue, null, 2)}</pre></div>
                    <div className="rounded-lg bg-[#f6f8f7] p-3"><p className="font-black">TLS status</p><pre className="mt-2 whitespace-pre-wrap break-words text-[9px] text-[var(--admin-muted)]">{JSON.stringify(data.tls, null, 2)}</pre></div>
                  </div>
                </section>
              </div>
            </section>

            <section className="panel">
              <div className="flex items-center justify-between"><div><p className="section-kicker"><Wrench size={12} className="mr-1 inline"/>Operations</p><h2 className="section-title">Recent mail-node operations</h2></div><span className="text-[10px] text-[var(--admin-muted)]">{failedOps.length} failed</span></div>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[760px] text-left text-xs">
                  <thead><tr className="border-b text-[10px] uppercase tracking-[.08em] text-[var(--admin-muted)]"><th className="px-3 py-2">Operation</th><th className="px-3 py-2">Node</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">Created</th><th className="px-3 py-2">Failure</th></tr></thead>
                  <tbody>
                    {data.recent_operations.map((operation) => (
                      <tr key={operation.id} className="border-b border-[var(--admin-line)] last:border-0">
                        <td className="px-3 py-3 font-black">{operation.operation.replaceAll("_", " ")}</td>
                        <td className="px-3 py-3 font-mono text-[10px]">{operation.node_id.slice(0, 8)}…</td>
                        <td className="px-3 py-3"><span className={`rounded-full border px-2 py-1 text-[9px] font-black uppercase ${statusClass(operation.status)}`}>{operation.status}</span></td>
                        <td className="px-3 py-3 text-[10px]">{fmt(operation.created_at)}</td>
                        <td className="max-w-[360px] px-3 py-3 text-[10px] text-rose-700">{operation.failure_message || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        ) : loading ? (
          <section className="panel flex items-center gap-3 text-xs text-[var(--admin-muted)]"><RefreshCw size={16} className="animate-spin"/>Loading mail operations telemetry…</section>
        ) : null}
      </div>
    </ControlShell>
  );
}
