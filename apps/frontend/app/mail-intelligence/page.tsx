"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Bot, FileLock2, RefreshCw, ShieldAlert, ShieldCheck, Trash2 } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { apiJson, apiMutation } from "@/lib/platform-api";

type Me = { email?: string; is_platform_owner: boolean };
type Membership = { tenant_id: string; tenant_name: string; status: string };
type Tenant = { id: string; name: string; status: string };
type Overview = { retention_policies: number; legal_holds: number; phishing_open: number; automations_enabled: number; trusted_senders: number; latest_dmarc?: { domain: string; alignment_rate: number; total_messages: number; failed_messages: number } | null };
type Retention = { id: string; name: string; retention_days: number; legal_hold: boolean; immutable_archive: boolean; mailbox_scope: string[] };
type Dmarc = { id: string; domain: string; reporter?: string | null; period_end: string; total_messages: number; aligned_messages: number; failed_messages: number; alignment_rate: number };
type Finding = { id: string; severity: string; finding_type: string; sender?: string | null; subject?: string | null; resolved: boolean; created_at: string };
type Automation = { id: string; name: string; enabled: boolean; trigger_event: string; run_count: number; last_error?: string | null };
type TrustedSender = { id: string; name: string; category: string; sender_addresses: string[]; sender_domains: string[]; allowed_link_domains: string[]; require_spf: boolean; require_dkim: boolean; require_dmarc: boolean; active: boolean };

export default function MailIntelligencePage() {
  const [me, setMe] = useState<Me | null>(null);
  const [contexts, setContexts] = useState<Membership[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [retention, setRetention] = useState<Retention[]>([]);
  const [dmarc, setDmarc] = useState<Dmarc[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [trustedSenders, setTrustedSenders] = useState<TrustedSender[]>([]);
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
      const [o, r, d, p, a, t] = await Promise.all([
        apiJson<Overview>(`/mail-intelligence/tenants/${tenantId}/overview`, { ttlMs: 0, force: true }),
        apiJson<Retention[]>(`/mail-intelligence/tenants/${tenantId}/retention`, { ttlMs: 0, force: true }),
        apiJson<Dmarc[]>(`/mail-intelligence/tenants/${tenantId}/dmarc?limit=30`, { ttlMs: 0, force: true }),
        apiJson<Finding[]>(`/mail-intelligence/tenants/${tenantId}/phishing?limit=50`, { ttlMs: 0, force: true }),
        apiJson<Automation[]>(`/mail-intelligence/tenants/${tenantId}/automations`, { ttlMs: 0, force: true }),
        apiJson<TrustedSender[]>(`/mail-intelligence/tenants/${tenantId}/trusted-senders`, { ttlMs: 0, force: true }),
      ]); setOverview(o); setRetention(r); setDmarc(d); setFindings(p); setAutomations(a); setTrustedSenders(t);
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

  async function createTrustedSender(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const split = (value: FormDataEntryValue | null) => String(value || "").split(",").map(item => item.trim()).filter(Boolean);
    try {
      await apiMutation(`/mail-intelligence/tenants/${tenantId}/trusted-senders`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.get("name"),
          category: form.get("category") || "business_partner",
          sender_addresses: split(form.get("sender_addresses")),
          sender_domains: split(form.get("sender_domains")),
          allowed_link_domains: split(form.get("allowed_link_domains")),
          require_spf: Boolean(form.get("require_spf")),
          require_dkim: Boolean(form.get("require_dkim")),
          require_dmarc: Boolean(form.get("require_dmarc")),
          active: true,
        }),
      });
      setNotice("Trusted sender profile created. Ithute will still verify authentication and links before granting trust.");
      event.currentTarget.reset(); await load();
    } catch { setError("Unable to create trusted sender profile. Check addresses, domains and authentication requirements."); }
  }

  async function deleteTrustedSender(id: string) {
    try {
      await apiMutation(`/mail-intelligence/tenants/${tenantId}/trusted-senders/${id}`, { method: "DELETE", credentials: "include" });
      setNotice("Trusted sender profile removed."); await load();
    } catch { setError("Unable to remove trusted sender profile."); }
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
    {overview ? <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">{[["Retention policies", overview.retention_policies],["Legal holds",overview.legal_holds],["Open phishing",overview.phishing_open],["Trusted senders",overview.trusted_senders],["Automations",overview.automations_enabled],["DMARC alignment",overview.latest_dmarc ? `${overview.latest_dmarc.alignment_rate}%` : "—"]].map(([label,value]) => <div key={String(label)} className="surface-card p-4"><p className="text-[9px] font-black uppercase text-[var(--admin-muted)]">{label}</p><p className="mt-2 text-2xl font-black">{value}</p></div>)}</section> : null}
    <section className="surface-card p-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div><div className="flex items-center gap-2"><ShieldCheck size={16}/><h2 className="text-sm font-black">Trusted Sender Registry</h2></div><p className="mt-2 max-w-3xl text-[10px] leading-5 text-[var(--admin-muted)]">Register banks, suppliers, government agencies and business partners. A registry match is never a blind allowlist: Ithute still requires the selected SPF/DKIM/DMARC checks and approved link domains before granting trust credit.</p></div>
        <span className="rounded-full bg-emerald-50 px-3 py-1 text-[9px] font-black uppercase text-emerald-700">{trustedSenders.filter(item => item.active).length} active</span>
      </div>
      <form onSubmit={createTrustedSender} className="mt-4 grid gap-2 lg:grid-cols-2 xl:grid-cols-4">
        <input className="input" name="name" placeholder="Partner name" required/>
        <select className="input" name="category" defaultValue="business_partner"><option value="business_partner">Business partner</option><option value="bank">Bank</option><option value="government">Government</option><option value="supplier">Supplier</option><option value="payroll">Payroll</option><option value="security">Security provider</option></select>
        <input className="input" name="sender_addresses" placeholder="alerts@partner.co.ls, billing@partner.co.ls"/>
        <input className="input" name="sender_domains" placeholder="partner.co.ls"/>
        <input className="input" name="allowed_link_domains" placeholder="partner.co.ls, payments.partner.co.ls"/>
        <div className="flex flex-wrap items-center gap-4 rounded-xl border border-[var(--admin-line)] px-3 py-2 text-[10px]">
          <label className="flex items-center gap-2"><input type="checkbox" name="require_spf" defaultChecked/>SPF</label>
          <label className="flex items-center gap-2"><input type="checkbox" name="require_dkim" defaultChecked/>DKIM</label>
          <label className="flex items-center gap-2"><input type="checkbox" name="require_dmarc" defaultChecked/>DMARC</label>
        </div>
        <button className="btn-primary lg:col-span-2 xl:col-span-1">Add trusted sender</button>
      </form>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        {trustedSenders.map(item => <div key={item.id} className="rounded-2xl border border-[var(--admin-line)] p-4">
          <div className="flex items-start justify-between gap-3"><div><p className="text-xs font-black">{item.name}</p><p className="mt-1 text-[9px] font-black uppercase tracking-[.08em] text-[var(--admin-muted)]">{item.category.replaceAll("_", " ")}</p></div><button className="rounded-lg p-2 text-[var(--admin-muted)] hover:bg-red-50 hover:text-red-700" onClick={() => void deleteTrustedSender(item.id)} aria-label={`Remove ${item.name}`}><Trash2 size={14}/></button></div>
          <div className="mt-3 space-y-1 text-[10px]"><p><span className="font-black">Addresses:</span> {item.sender_addresses.join(", ") || "Any matching configured domain"}</p><p><span className="font-black">Domains:</span> {item.sender_domains.join(", ") || "—"}</p><p><span className="font-black">Approved links:</span> {item.allowed_link_domains.join(", ") || "Sender domain only"}</p></div>
          <div className="mt-3 flex flex-wrap gap-2">{[["SPF",item.require_spf],["DKIM",item.require_dkim],["DMARC",item.require_dmarc]].map(([label,on]) => <span key={String(label)} className={`rounded-full px-2 py-1 text-[9px] font-black ${on ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>{label} {on ? "required" : "optional"}</span>)}</div>
        </div>)}
        {!trustedSenders.length ? <div className="rounded-2xl border border-dashed border-[var(--admin-line)] p-5 text-[10px] text-[var(--admin-muted)]">No tenant-specific trusted senders yet. Ithute first-party security identities remain protected by the immutable system registry.</div> : null}
      </div>
    </section>
    <section className="grid gap-4 xl:grid-cols-2"><div className="surface-card p-5"><div className="flex items-center gap-2"><FileLock2 size={16}/><h2 className="text-sm font-black">Retention & legal hold</h2></div><form onSubmit={createRetention} className="mt-4 grid gap-2 sm:grid-cols-[1fr_150px_auto]"><input className="input" name="name" placeholder="Policy name" required/><input className="input" name="retention_days" type="number" min="1" defaultValue="2555"/><button className="btn-primary">Create</button><label className="flex items-center gap-2 text-[10px] sm:col-span-3"><input name="legal_hold" type="checkbox"/>Enable legal hold immediately</label></form><div className="mt-4 space-y-2">{retention.map(item => <div key={item.id} className="rounded-xl border border-[var(--admin-line)] p-3 text-[10px]"><div className="flex justify-between gap-3"><span className="font-black">{item.name}</span><span>{item.retention_days} days</span></div><p className="mt-1 text-[var(--admin-muted)]">Legal hold {item.legal_hold ? "on" : "off"} · immutable archive {item.immutable_archive ? "on" : "off"}</p></div>)}</div></div>
    <div className="surface-card p-5"><div className="flex items-center gap-2"><Bot size={16}/><h2 className="text-sm font-black">Mail automation</h2></div><form onSubmit={createAutomation} className="mt-4 grid gap-2 sm:grid-cols-[1fr_180px_auto]"><input className="input" name="name" placeholder="Automation name" required/><select className="input" name="trigger_event" defaultValue="mail.received"><option value="mail.received">mail.received</option><option value="mail.delivery_failed">mail.delivery_failed</option><option value="mailbox.quota_warning">mailbox.quota_warning</option></select><button className="btn-primary">Create</button></form><div className="mt-4 space-y-2">{automations.map(item => <div key={item.id} className="rounded-xl border border-[var(--admin-line)] p-3 text-[10px]"><div className="flex justify-between"><span className="font-black">{item.name}</span><span>{item.enabled ? "Enabled" : "Disabled"}</span></div><p className="mt-1 text-[var(--admin-muted)]">{item.trigger_event} · {item.run_count} runs</p></div>)}</div></div></section>
    <section className="surface-card p-5"><h2 className="text-sm font-black">DMARC analytics</h2><div className="mt-4 overflow-x-auto"><table className="w-full min-w-[720px] text-left text-[10px]"><thead><tr><th className="p-2">Domain</th><th className="p-2">Period end</th><th className="p-2">Messages</th><th className="p-2">Aligned</th><th className="p-2">Failed</th><th className="p-2">Alignment</th></tr></thead><tbody>{dmarc.map(item => <tr key={item.id} className="border-t border-[var(--admin-line)]"><td className="p-2 font-black">{item.domain}</td><td className="p-2">{new Date(item.period_end).toLocaleString()}</td><td className="p-2">{item.total_messages}</td><td className="p-2">{item.aligned_messages}</td><td className="p-2">{item.failed_messages}</td><td className="p-2">{item.alignment_rate}%</td></tr>)}</tbody></table></div></section>
    <section className="surface-card p-5"><div className="flex items-center gap-2"><ShieldAlert size={16}/><h2 className="text-sm font-black">Phishing findings</h2></div><div className="mt-4 space-y-2">{findings.map(item => <div key={item.id} className="grid gap-2 rounded-xl border border-[var(--admin-line)] p-3 text-[10px] sm:grid-cols-[100px_1fr_auto]"><span className="font-black uppercase">{item.severity}</span><div><p className="font-black">{item.finding_type}</p><p className="mt-1 text-[var(--admin-muted)]">{item.sender || "unknown sender"} · {item.subject || "no subject"}</p></div><span>{item.resolved ? "Resolved" : "Open"}</span></div>)}</div></section>
  </div></ControlShell>;
}
