"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  Clipboard,
  Globe2,
  MailCheck,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Wrench,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { ControlShell } from "@/components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Me = { email: string; is_platform_owner: boolean };
type Membership = { tenant_id: string; tenant_name: string; role: string; status: string };
type Domain = {
  id: string;
  ascii_name: string;
  unicode_name: string;
  status: string;
  dns_mode: "platform" | "external";
  mail_enabled: boolean;
  ownership_verified_at?: string | null;
};
type HealthCheck = {
  id: string;
  label: string;
  status: "healthy" | "attention" | "pending";
  required: boolean;
  detail: string;
  observed?: unknown;
  expected?: unknown;
};
type Health = {
  domain: string;
  mail_enabled: boolean;
  dns_mode: string;
  overall_status: "healthy" | "attention" | "pending";
  score: number;
  checked_at: string;
  summary: { required: number; healthy: number; attention: number; pending: number; optional_attention: number };
  checks: HealthCheck[];
  expected_records: { name: string; type: string; value?: string; values?: string[]; purpose: string }[];
  mail_hostname: string;
  mail_public_ip?: string | null;
  dkim_selector?: string | null;
};

async function api(path: string, init?: RequestInit) {
  const options: RequestInit = {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  };
  let response = await fetch(`${API}${path}`, options);
  if (response.status === 401) {
    const refresh = await fetch(`${API}/auth/refresh`, { method: "POST", credentials: "include" });
    if (refresh.ok) response = await fetch(`${API}${path}`, options);
  }
  return response;
}

function statusClass(status: HealthCheck["status"] | Health["overall_status"]) {
  if (status === "healthy") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "pending") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-rose-200 bg-rose-50 text-rose-700";
}

function statusIcon(status: HealthCheck["status"]) {
  if (status === "healthy") return <CheckCircle2 size={16} />;
  if (status === "pending") return <CircleDot size={16} />;
  return <AlertTriangle size={16} />;
}

function display(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function DomainMailHealthPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [contexts, setContexts] = useState<Membership[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [domains, setDomains] = useState<Domain[]>([]);
  const [domainId, setDomainId] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const selectedContext = useMemo(() => contexts.find((item) => item.tenant_id === tenantId), [contexts, tenantId]);
  const selectedDomain = useMemo(() => domains.find((item) => item.id === domainId), [domains, domainId]);
  const canManage = Boolean(me?.is_platform_owner || ["tenant_admin", "dns_admin"].includes(selectedContext?.role || ""));

  useEffect(() => {
    void (async () => {
      const meResponse = await api("/auth/me");
      if (meResponse.status === 401) {
        router.replace("/login");
        return;
      }
      const current: Me = await meResponse.json();
      setMe(current);
      let rows: Membership[] = [];
      if (current.is_platform_owner) {
        const tenantResponse = await api("/tenants");
        rows = (await tenantResponse.json()).map((tenant: { id: string; name: string; status: string }) => ({
          tenant_id: tenant.id,
          tenant_name: tenant.name,
          role: "platform_owner",
          status: tenant.status,
        }));
      } else {
        const memberships = await api("/me/memberships");
        rows = await memberships.json();
      }
      rows = rows.filter((row) => row.status === "active");
      setContexts(rows);
      setTenantId(rows[0]?.tenant_id || "");
    })();
  }, [router]);

  useEffect(() => {
    if (!tenantId) return;
    setHealth(null);
    void (async () => {
      const response = await api(`/tenants/${tenantId}/domains?limit=200`);
      if (!response.ok) {
        setError("Unable to load domains.");
        return;
      }
      const data = await response.json();
      const rows = (data.items || []).filter((domain: Domain) => domain.status !== "archived");
      setDomains(rows);
      setDomainId(rows[0]?.id || "");
    })();
  }, [tenantId]);

  useEffect(() => {
    if (tenantId && domainId) void loadHealth();
  }, [tenantId, domainId]);

  async function loadHealth() {
    if (!tenantId || !domainId) return;
    setLoading(true);
    setError("");
    const response = await api(`/tenants/${tenantId}/domains/${domainId}/mail-health`);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setError(String(body.detail || "Unable to run mail-domain health checks."));
      setHealth(null);
      setLoading(false);
      return;
    }
    setHealth(await response.json());
    setLoading(false);
  }

  async function reconcile() {
    if (!selectedDomain || !tenantId || !domainId || reconciling) return;
    setReconciling(true);
    setError("");
    setMessage("");
    const response = await api(`/tenants/${tenantId}/domains/${domainId}/dns/mail/reconcile`, { method: "POST" });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setError(String(body.detail || "Mail DNS reconciliation failed."));
      setReconciling(false);
      return;
    }
    setMessage("Mail DNS reconciled. Public DNS may take time to propagate; health has been checked again.");
    await loadHealth();
    setReconciling(false);
  }

  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setMessage("Copied to clipboard.");
    } catch {
      setError("Clipboard access was blocked. Select and copy the value manually.");
    }
  }

  return (
    <ControlShell title="Mail domain health" subtitle="MX, SPF, DKIM, DMARC, routing and client-discovery readiness" userEmail={me?.email}>
      <div className="space-y-4">
        <section className="panel">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <p className="eyebrow-admin"><MailCheck size={13}/>Mail readiness</p>
              <h1 className="mt-2 text-2xl font-black tracking-tight text-[#21342a]">Domain health centre</h1>
              <p className="mt-1 max-w-3xl text-xs leading-5 text-[var(--admin-muted)]">
                See the public DNS and infrastructure conditions that affect receiving mail, sender authentication and client setup.
              </p>
            </div>
            <div className="grid gap-2 sm:grid-cols-2 xl:min-w-[560px]">
              <select className="input" value={tenantId} onChange={(event) => setTenantId(event.target.value)}>
                {contexts.map((row) => <option key={row.tenant_id} value={row.tenant_id}>{row.tenant_name}</option>)}
              </select>
              <select className="input" value={domainId} onChange={(event) => setDomainId(event.target.value)}>
                {domains.map((domain) => <option key={domain.id} value={domain.id}>{domain.unicode_name}</option>)}
              </select>
            </div>
          </div>
        </section>

        {error ? <div className="alert-error"><AlertTriangle size={15}/>{error}</div> : null}
        {message ? <div className="alert-success"><CheckCircle2 size={15}/>{message}</div> : null}

        {!selectedDomain && !loading ? (
          <section className="panel text-center">
            <Globe2 className="mx-auto text-[var(--admin-muted)]" size={28}/>
            <p className="mt-3 text-sm font-black">No domain selected</p>
            <p className="mt-1 text-xs text-[var(--admin-muted)]">Add a domain first, then Ithute can assess its mail readiness.</p>
          </section>
        ) : null}

        {health ? (
          <>
            <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              <div className="panel sm:col-span-2 xl:col-span-1">
                <p className="section-kicker">Overall</p>
                <div className="mt-2 flex items-center justify-between gap-3">
                  <span className={`rounded-full border px-2.5 py-1 text-[10px] font-black uppercase tracking-[.08em] ${statusClass(health.overall_status)}`}>
                    {health.overall_status}
                  </span>
                  <strong className="text-2xl font-black text-[#21342a]">{health.score}%</strong>
                </div>
                <p className="mt-2 text-[10px] text-[var(--admin-muted)]">Required checks passing</p>
              </div>
              <div className="panel"><p className="section-kicker">Healthy</p><p className="mt-2 text-2xl font-black text-emerald-700">{health.summary.healthy}</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">of {health.summary.required} required</p></div>
              <div className="panel"><p className="section-kicker">Attention</p><p className="mt-2 text-2xl font-black text-rose-700">{health.summary.attention}</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">required fixes</p></div>
              <div className="panel"><p className="section-kicker">Pending</p><p className="mt-2 text-2xl font-black text-amber-700">{health.summary.pending}</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">awaiting setup</p></div>
              <div className="panel"><p className="section-kicker">Optional</p><p className="mt-2 text-2xl font-black text-[#285b55]">{health.summary.optional_attention}</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">client-setup improvements</p></div>
            </section>

            <section className="panel">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="section-kicker"><ShieldCheck size={12} className="mr-1 inline"/>Live checks</p>
                  <h2 className="section-title">{health.domain}</h2>
                  <p className="mt-1 text-[11px] text-[var(--admin-muted)]">
                    Mail host: {health.mail_hostname}{health.mail_public_ip ? ` · ${health.mail_public_ip}` : ""}{health.dkim_selector ? ` · DKIM ${health.dkim_selector}` : ""}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {canManage && selectedDomain?.dns_mode === "platform" && selectedDomain?.status === "verified" && selectedDomain?.mail_enabled ? (
                    <button className="btn-primary" disabled={reconciling || loading} onClick={() => void reconcile()}>
                      <Wrench size={14}/>{reconciling ? "Reconciling…" : "Reconcile mail DNS"}
                    </button>
                  ) : null}
                  <button className="btn-secondary" disabled={loading} onClick={() => void loadHealth()}>
                    <RefreshCw size={14} className={loading ? "animate-spin" : ""}/>{loading ? "Checking…" : "Check again"}
                  </button>
                </div>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {health.checks.map((check) => (
                  <article key={check.id} className="rounded-xl border border-[var(--admin-line)] bg-white p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg border ${statusClass(check.status)}`}>{statusIcon(check.status)}</span>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-black text-[#21342a]">{check.label}</p>
                          <p className="mt-0.5 text-[9px] font-black uppercase tracking-[.08em] text-[var(--admin-muted)]">{check.required ? "Required" : "Optional"}</p>
                        </div>
                      </div>
                      <span className={`rounded-full border px-2 py-1 text-[9px] font-black uppercase ${statusClass(check.status)}`}>{check.status}</span>
                    </div>
                    <p className="mt-3 min-h-10 text-[11px] leading-5 text-[var(--admin-muted)]">{check.detail}</p>
                    {(check.expected !== undefined || check.observed !== undefined) ? (
                      <div className="mt-3 space-y-2 rounded-lg bg-[#f6f8f7] p-3 text-[10px]">
                        {check.expected !== undefined ? <div><span className="font-black text-[#52645b]">Expected</span><p className="mt-0.5 break-all">{display(check.expected)}</p></div> : null}
                        {check.observed !== undefined ? <div><span className="font-black text-[#52645b]">Observed</span><p className="mt-0.5 break-all">{display(check.observed)}</p></div> : null}
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>
            </section>

            <section className="panel">
              <div>
                <p className="section-kicker"><Sparkles size={12} className="mr-1 inline"/>DNS guidance</p>
                <h2 className="section-title">Expected mail records</h2>
                <p className="mt-1 text-xs text-[var(--admin-muted)]">
                  Platform-hosted DNS can be reconciled automatically. For external DNS, publish these values with the current DNS provider.
                </p>
              </div>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[720px] text-left text-xs">
                  <thead><tr className="border-b text-[10px] uppercase tracking-[.08em] text-[var(--admin-muted)]"><th className="px-3 py-2">Purpose</th><th className="px-3 py-2">Name</th><th className="px-3 py-2">Type</th><th className="px-3 py-2">Value</th><th className="w-12 px-3 py-2"></th></tr></thead>
                  <tbody>
                    {health.expected_records.map((record, index) => {
                      const value = record.value || record.values?.join(" | ") || "";
                      return <tr key={`${record.purpose}-${record.name}-${index}`} className="border-b border-[var(--admin-line)] last:border-0">
                        <td className="px-3 py-3 font-black capitalize">{record.purpose.replaceAll("-", " ")}</td>
                        <td className="px-3 py-3 font-mono text-[10px]">{record.name}</td>
                        <td className="px-3 py-3 font-black">{record.type}</td>
                        <td className="max-w-[520px] break-all px-3 py-3 font-mono text-[10px]">{value}</td>
                        <td className="px-3 py-3"><button className="icon-button" title="Copy value" onClick={() => void copy(value)}><Clipboard size={13}/></button></td>
                      </tr>;
                    })}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-[10px] text-[var(--admin-muted)]">Last checked {new Date(health.checked_at).toLocaleString()}.</p>
            </section>
          </>
        ) : loading ? (
          <section className="panel flex items-center gap-3 text-xs text-[var(--admin-muted)]"><RefreshCw className="animate-spin" size={16}/>Checking public DNS and mail infrastructure…</section>
        ) : null}
      </div>
    </ControlShell>
  );
}
