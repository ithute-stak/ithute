"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Bot, FileLock2, RefreshCw, ShieldAlert } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { apiJson, apiMutation } from "@/lib/platform-api";

type Me = { email?: string; is_platform_owner: boolean };
type Membership = { tenant_id: string; tenant_name: string; status: string };
type Tenant = { id: string; name: string; status: string };
type Overview = { retention_policies: number; legal_holds: number; phishing_open: number; automations_enabled: number; latest_dmarc?: { domain: string; alignment_rate: number; total_messages: number; failed_messages: number } | null };
type Retention = { id: string; name: string; retention_days: number; legal_hold: boolean; immutable_archive: boolean; mailbox_scope: string[] };
type Dmarc = { id: string; domain: string; reporter?: string | null; period_end: string; total_messages: number; aligned_messages: number; failed_messages: number; alignment_rate: number };
type Finding = { id: string; severity: string; finding_type: string; sender?: string | null; subject?: string | null; resolved: boolean; created_at: string };
type Automation = { id: string; name: string; enabled: boolean; trigger_event: string; run_count: number; last_error?: string | null };

export default function MailIntelligencePage() {
  const [me, setMe] = useState<Me | null>(null);
  const [contexts, setContexts] = useState<Membership[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [retention, setRetention] = useState<Retention[]>([]);
  const [dmarc, setDmarc] = useState<Dmarc[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        const account = await apiJson<Me>("/auth/me", { ttlMs: 0, force: true }); setMe(account);
        let rows: Membership[];
        if (account.is_platform_owner) {
          const tenants = await apiJson<Tenant[]>("/tenants", { ttlMs: 0, force: true });
          rows = tenants.map(t => ({ tenant_id: t.id, tenant_name: t.name, status: t.status }));
        } else rows = await apiJson<Membership[]>("/me/memberships", { ttlMs: 0, force: true });
        rows = rows.filter(row => row.status === "active"); setContexts(rows); setTenantId(rows[0]?.tenant_id || "");
      } catch { setError("Unable to load mail intelligence access."); setLoading(false); }
    })();
  }, []);

  const load = useCallback(async () => {
    if (!tenantId) { setLoading(false); return; }
    setLoading(true); setError("");
    try {
      const [o, r, d, p, a] = await Promise.all([
        apiJson<Overview>(`/mail-intelligence/tenants/${tenantId}/overview`, { ttlMs: 0, force: true }),
        apiJson<Retention[]>(`/mail-intelligence/tenants/${tenantId}/retention`, { ttlMs: 0, force: true }),
        apiJson<Dmarc[]>(`/mail-intelligence/tenants/${tenantId}/dmarc?limit=30`, { ttlMs: 0, force: true }),
        apiJson<Finding[]>(`/mail-intelligence/tenants/${tenantId}/phishing?limit=50`, { ttlMs: 0, force: true }),
        apiJson<Automation[]>(`/mail-intelligence/tenants/${tenantId}/automations`, { ttlMs: 0, force: true }),
      ]); setOverview(o); setRetention(r); setDmarc(d); setFindings(p); setAutomations(a);
    } catch { setError("Unable to load mail intelligence data for this organization."); }
    finally { setLoading(false); }
  }, [tenantId]);

  useEffect(() => { void load(); }, [load]);

  async function createRetention(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    try {
      await apiMutation(`/mail-intelligence/tenants/${tenantId}/retention`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: form.get("name"), retention_days: Number(form.get("retention_days") || 2555), legal_hold: Boolean(form.get("legal_hold")), immutable_archive: true, mailbox_scope: [] }) });
      setNotice("Retention policy created."); event.currentTarget.reset(); await load();
    } catch { setError("Unable to create retention policy."); }
  }

  async function createAutomation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    try {
      await apiMutation(`/mail-intelligence/tenants/${tenantId}/automations`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: form.get("name"), enabled: true, trigger_event: form.get("trigger_event") || "mail.received", conditions: {}, actions: [] }) });
      setNotice("Automation rule shell created. Add conditions/actions through the API as integrations are connected."); event.currentTarget.reset(); await load();
    } catch { setError("Unable to create automation rule."); }
  }

  return <ControlShell title="Mail Intelligence" subtitle="Retention, DMARC, phishing findings and cross-product automation" userEmail={me?.email}><div className="space-y-5">
    <section className="surface-card p-5"><div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><div><p className="text-[9px] font-black uppercase tracking-[.14em] text-[var(--admin-muted)]">Enterprise mail controls</p><h1 className="mt-2 text-2xl font-black">Mail Intelligence</h1><p className="mt-2 text-[11px] text-[var(--admin-muted)]">Policy and analytics metadata stays tenant-scoped in Mailbox. Message bodies are not copied into the Ithute platform registry.</p></div><div className="flex gap-2"><select className="input min-w-[220px]" value={tenantId} onChange={e => setTenantId(e.target.value)}>{contexts.map(row => <option key={row.tenant_id} value={row.tenant_id}>{row.tenant_name}</option>)}</select><button className="btn-secondary" onClick={() => void load()}><RefreshCw size={14} className={loading ? "animate-spin" : ""} /></button></div></div>{notice ? <div className="mt-3 rounded-xl bg-emerald-50 p-3 text-[10px] font-bold text-emerald-700">{notice}</div> : null}{error ? <div className="mt-3 rounded-xl bg-red-50 p-3 text-[10px] font-bold text-red-700">{error}</div> : null}</section>
    {overview ? <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">{[["Retention policies", overview.retention_policies],["Legal holds",overview.legal_holds],["Open phishing",overview.phishing_open],["Automations",overview.automations_enabled],["DMARC alignment",overview.latest_dmarc ? `${overview.latest_dmarc.alignment_rate}%` : "—"]].map(([label,value]) => <div key={String(label)} className="surface-card p-4"><p className="text-[9px] font-black uppercase text-[var(--admin-muted)]">{label}</p><p className="mt-2 text-2xl font-black">{value}</p></div>)}</section> : null}
    <section className="grid gap-4 xl:grid-cols-2"><div className="surface-card p-5"><div className="flex items-center gap-2"><FileLock2 size={16}/><h2 className="text-sm font-black">Retention & legal hold</h2></div><form onSubmit={createRetention} className="mt-4 grid gap-2 sm:grid-cols-[1fr_150px_auto]"><input className="input" name="name" placeholder="Policy name" required/><input className="input" name="retention_days" type="number" min="1" defaultValue="2555"/><button className="btn-primary">Create</button><label className="flex items-center gap-2 text-[10px] sm:col-span-3"><input name="legal_hold" type="checkbox"/>Enable legal hold immediately</label></form><div className="mt-4 space-y-2">{retention.map(item => <div key={item.id} className="rounded-xl border border-[var(--admin-line)] p-3 text-[10px]"><div className="flex justify-between gap-3"><span className="font-black">{item.name}</span><span>{item.retention_days} days</span></div><p className="mt-1 text-[var(--admin-muted)]">Legal hold {item.legal_hold ? "on" : "off"} · immutable archive {item.immutable_archive ? "on" : "off"}</p></div>)}</div></div>
    <div className="surface-card p-5"><div className="flex items-center gap-2"><Bot size={16}/><h2 className="text-sm font-black">Mail automation</h2></div><form onSubmit={createAutomation} className="mt-4 grid gap-2 sm:grid-cols-[1fr_180px_auto]"><input className="input" name="name" placeholder="Automation name" required/><select className="input" name="trigger_event" defaultValue="mail.received"><option value="mail.received">mail.received</option><option value="mail.delivery_failed">mail.delivery_failed</option><option value="mailbox.quota_warning">mailbox.quota_warning</option></select><button className="btn-primary">Create</button></form><div className="mt-4 space-y-2">{automations.map(item => <div key={item.id} className="rounded-xl border border-[var(--admin-line)] p-3 text-[10px]"><div className="flex justify-between"><span className="font-black">{item.name}</span><span>{item.enabled ? "Enabled" : "Disabled"}</span></div><p className="mt-1 text-[var(--admin-muted)]">{item.trigger_event} · {item.run_count} runs</p></div>)}</div></div></section>
    <section className="surface-card p-5"><h2 className="text-sm font-black">DMARC analytics</h2><div className="mt-4 overflow-x-auto"><table className="w-full min-w-[720px] text-left text-[10px]"><thead><tr><th className="p-2">Domain</th><th className="p-2">Period end</th><th className="p-2">Messages</th><th className="p-2">Aligned</th><th className="p-2">Failed</th><th className="p-2">Alignment</th></tr></thead><tbody>{dmarc.map(item => <tr key={item.id} className="border-t border-[var(--admin-line)]"><td className="p-2 font-black">{item.domain}</td><td className="p-2">{new Date(item.period_end).toLocaleString()}</td><td className="p-2">{item.total_messages}</td><td className="p-2">{item.aligned_messages}</td><td className="p-2">{item.failed_messages}</td><td className="p-2">{item.alignment_rate}%</td></tr>)}</tbody></table></div></section>
    <section className="surface-card p-5"><div className="flex items-center gap-2"><ShieldAlert size={16}/><h2 className="text-sm font-black">Phishing findings</h2></div><div className="mt-4 space-y-2">{findings.map(item => <div key={item.id} className="grid gap-2 rounded-xl border border-[var(--admin-line)] p-3 text-[10px] sm:grid-cols-[100px_1fr_auto]"><span className="font-black uppercase">{item.severity}</span><div><p className="font-black">{item.finding_type}</p><p className="mt-1 text-[var(--admin-muted)]">{item.sender || "unknown sender"} · {item.subject || "no subject"}</p></div><span>{item.resolved ? "Resolved" : "Open"}</span></div>)}</div></section>
  </div></ControlShell>;
}
