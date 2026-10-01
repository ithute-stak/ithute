"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  CheckCircle2,
  CircleDollarSign,
  Database,
  Globe2,
  HardDrive,
  KeyRound,
  Mail,
  ReceiptText,
  Server,
  ShieldCheck,
} from "lucide-react";
import { ControlShell } from "@/components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Membership = { tenant_id: string; tenant_name: string };
type Subscription = {
  status: string;
  plan_code?: string;
  plan_name?: string;
  current_period_start?: string;
  current_period_end?: string;
  cancel_at_period_end?: boolean;
  past_due_since?: string | null;
  grace_ends_at?: string | null;
};
type Usage = {
  mailboxes: number;
  domains: number;
  allocated_storage_bytes: number;
  api_keys: number;
  hosted_projects: number;
  hosting_storage_bytes: number;
  hosting_database_count: number;
  hosting_database_storage_bytes: number;
  hosting_source_storage_bytes: number;
};
type Limits = {
  mailboxes: number;
  domains: number;
  storage_bytes: number;
  api_keys: number;
  hosted_projects: number;
  hosting_storage_bytes: number;
  hosting_database_count: number;
  hosting_database_storage_bytes: number;
  hosting_source_storage_bytes: number;
};
type Summary = { subscription: Subscription | null; usage: Usage; entitlements: Limits | null; within_plan: boolean };
type Invoice = { id: string; invoice_number: string; currency: string; total_minor: number; status: string; due_at?: string | null };
type Provider = { provider: string; configured: boolean; hosted_checkout: boolean };
type Contract = {
  billing_interval: "monthly" | "annual";
  auto_renew: boolean;
  invoice_lead_days: number;
  grace_days: number;
  discount_percent: number;
  credit_balance_minor: number;
  next_invoice_at?: string | null;
};
type Plan = {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  currency: string;
  monthly_price_minor: number;
  annual_price_minor?: number | null;
  setup_fee_minor?: number | null;
  included_mailboxes: number;
  included_domains: number;
  included_hosted_projects: number;
  hosting_storage_mb: number;
  hosting_database_limit: number;
  hosting_database_storage_mb: number;
  support_level: string;
  featured: boolean;
};

async function api(path: string, init?: RequestInit) {
  return fetch(`${API}${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
}

function bytes(value = 0) {
  const gb = value / 1024 / 1024 / 1024;
  if (gb >= 1) return `${gb.toFixed(gb >= 10 ? 0 : 1)} GB`;
  return `${Math.round(value / 1024 / 1024)} MB`;
}

function money(value = 0, currency = "LSL") {
  return `${currency === "LSL" ? "M" : `${currency} `}${(value / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function UsageCard({ label, used, limit, icon }: { label: string; used: string | number; limit: string | number; icon: React.ReactNode }) {
  return (
    <article className="surface-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="eyebrow-label">{label}</p>
          <p className="mt-2 text-xl font-black text-[var(--admin-ink)]">{used} <span className="text-xs font-bold text-[var(--admin-muted)]">/ {limit}</span></p>
        </div>
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#edf4f1] text-[#285b55]">{icon}</span>
      </div>
    </article>
  );
}

export default function Billing() {
  const [email, setEmail] = useState("");
  const [owner, setOwner] = useState(false);
  const [tenant, setTenant] = useState("");
  const [tenants, setTenants] = useState<Membership[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [provider, setProvider] = useState<Provider | null>(null);
  const [contract, setContract] = useState<Contract | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => {
    void (async () => {
      const [me, memberships, payment, pricing] = await Promise.all([
        api("/auth/me"),
        api("/me/memberships"),
        api("/public/payment-provider"),
        api("/public/pricing"),
      ]);
      if (me.ok) {
        const body = await me.json();
        setEmail(body.email || "");
        setOwner(Boolean(body.is_platform_owner));
      }
      if (memberships.ok) {
        const rows = await memberships.json();
        setTenants(rows);
        setTenant(localStorage.getItem("mailbox_dns_tenant") || rows[0]?.tenant_id || "");
      }
      if (payment.ok) setProvider(await payment.json());
      if (pricing.ok) setPlans((await pricing.json()).items || []);
    })();
  }, []);

  useEffect(() => {
    if (!tenant) return;
    localStorage.setItem("mailbox_dns_tenant", tenant);
    void load();
  }, [tenant]);

  async function load() {
    setError("");
    const [summaryResponse, invoiceResponse, contractResponse] = await Promise.all([
      api(`/tenants/${tenant}/billing/summary`),
      api(`/tenants/${tenant}/billing/invoices`),
      api(`/tenants/${tenant}/commercial/contract`),
    ]);
    if (summaryResponse.ok) setSummary(await summaryResponse.json());
    else setError("Unable to load subscription status.");
    if (invoiceResponse.ok) setInvoices((await invoiceResponse.json()).items || []);
    if (contractResponse.ok) setContract(await contractResponse.json());
  }

  async function invoice() {
    setBusy("invoice");
    setError("");
    const response = await api(`/tenants/${tenant}/billing/manual-invoice`, { method: "POST" });
    const body = await response.json().catch(() => ({}));
    setMsg(response.ok ? `Invoice ${body.invoice_number} generated.` : "");
    if (!response.ok) setError(String(body.detail || "Unable to generate invoice"));
    if (response.ok) await load();
    setBusy("");
  }

  async function pay(item: Invoice) {
    setBusy(item.id);
    setError("");
    const response = await api(`/tenants/${tenant}/billing/invoices/${item.id}/dpo-checkout`, { method: "POST" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      setError(String(body.detail || "Unable to start payment"));
      setBusy("");
      return;
    }
    window.location.href = body.checkout_url;
  }

  async function changePlan(plan: Plan) {
    if (!summary?.subscription) return;
    const confirmed = window.confirm(`Change ${summary.subscription.plan_name || "your current package"} to ${plan.name}? Ithute will apply a capacity upgrade immediately. A safe downgrade is scheduled for the end of the current paid period.`);
    if (!confirmed) return;
    setBusy(`plan:${plan.id}`);
    setMsg("");
    setError("");
    const response = await api(`/tenants/${tenant}/commercial/change-plan/${plan.id}`, { method: "POST" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      setError(typeof body.detail === "string" ? body.detail : "Unable to change package");
    } else if (body.mode === "immediate") {
      setMsg(`${plan.name} is now active. Your new capacity is available immediately.`);
      await load();
    } else if (body.mode === "period_end") {
      setMsg(`${plan.name} is scheduled for ${body.effective_at ? new Date(body.effective_at).toLocaleDateString() : "the end of the current period"}.`);
    } else {
      setMsg("No package change was required.");
    }
    setBusy("");
  }

  const status = summary?.subscription?.status || "inactive";
  const canChangePlan = status === "active" || status === "trialing";
  const overdueInvoice = useMemo(() => invoices.find((item) => item.status !== "paid" && item.status !== "void"), [invoices]);
  const graceDate = summary?.subscription?.grace_ends_at ? new Date(summary.subscription.grace_ends_at) : null;
  const graceExpired = status === "past_due" && (!graceDate || graceDate.getTime() <= Date.now());

  return (
    <ControlShell title="Billing & subscription" subtitle="Package, capacity, invoices and commercial account" userEmail={email}>
      <div className="space-y-4">
        <section className="surface-card p-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="eyebrow-label">Commercial account</p>
              <h1 className="mt-2 text-2xl font-black">Subscription & service capacity</h1>
              <p className="mt-1 max-w-3xl text-xs text-[var(--admin-muted)]">Your package controls hosting, email, domains, databases, storage and API capacity. The same limits are enforced by the backend even when resources are created through APIs.</p>
            </div>
            <select className="input max-w-sm" value={tenant} onChange={(event) => setTenant(event.target.value)}>
              {tenants.map((item) => <option key={item.tenant_id} value={item.tenant_id}>{item.tenant_name}</option>)}
            </select>
          </div>
        </section>

        {status === "past_due" ? (
          <section className={`rounded-2xl border p-4 ${graceExpired ? "border-red-200 bg-red-50 text-red-800" : "border-amber-200 bg-amber-50 text-amber-900"}`}>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex gap-3">
                <AlertTriangle size={20} className="mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm font-black">{graceExpired ? "Service changes are restricted" : "Payment is overdue — grace period active"}</p>
                  <p className="mt-1 text-xs leading-5">{graceExpired ? "Your existing data and read-only access remain available, but new DNS, mail, hosting and API-key changes are blocked until payment restores the subscription." : `Your services remain manageable during the grace period${graceDate ? ` until ${graceDate.toLocaleDateString()}` : ""}. Pay the outstanding invoice before the grace period ends.`}</p>
                </div>
              </div>
              {overdueInvoice && provider?.configured ? <button disabled={busy === overdueInvoice.id} className="btn-primary whitespace-nowrap" onClick={() => void pay(overdueInvoice)}>Pay {money(overdueInvoice.total_minor, overdueInvoice.currency)}</button> : <Link href="#invoices" className="btn-secondary whitespace-nowrap">View invoice</Link>}
            </div>
          </section>
        ) : null}

        {status === "canceled" ? (
          <section className="rounded-2xl border border-red-200 bg-red-50 p-4 text-red-800">
            <div className="flex gap-3"><ShieldCheck size={20} className="mt-0.5 shrink-0"/><div><p className="text-sm font-black">Subscription is canceled</p><p className="mt-1 text-xs leading-5">Service-changing operations are locked. Billing and account access remain available so the subscription can be recovered without exposing infrastructure controls.</p></div></div>
          </section>
        ) : null}

        {msg ? <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-xs font-bold text-emerald-800">{msg}</div> : null}
        {error ? <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-xs font-bold text-red-800">{error}</div> : null}

        {summary ? (
          <>
            <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <article className="surface-card p-5 md:col-span-2">
                <p className="eyebrow-label">Current package</p>
                <div className="mt-2 flex flex-wrap items-center gap-3"><p className="text-2xl font-black">{summary.subscription?.plan_name || "No package"}</p><span className={`rounded-full px-2.5 py-1 text-[9px] font-black uppercase ${status === "active" || status === "trialing" ? "bg-emerald-50 text-emerald-700" : status === "past_due" ? "bg-amber-50 text-amber-700" : "bg-red-50 text-red-700"}`}>{status.replaceAll("_", " ")}</span></div>
                <p className="mt-2 text-xs text-[var(--admin-muted)]">{contract ? `${contract.billing_interval === "annual" ? "Annual" : "Monthly"} billing · ${contract.auto_renew ? "Auto-renew on" : "Auto-renew off"} · ${contract.grace_days}-day grace period` : "Commercial terms loading…"}</p>
                {summary.subscription?.current_period_end ? <p className="mt-1 text-[10px] text-[var(--admin-muted)]">Current period ends {new Date(summary.subscription.current_period_end).toLocaleDateString()}</p> : null}
              </article>
              <article className="surface-card p-5"><p className="eyebrow-label">Account credit</p><p className="mt-2 text-2xl font-black">{money(contract?.credit_balance_minor || 0)}</p><p className="mt-2 text-[10px] text-[var(--admin-muted)]">Applied automatically to the next invoice.</p></article>
              <article className="surface-card p-5"><p className="eyebrow-label">Capacity status</p><p className={`mt-2 flex items-center gap-2 text-lg font-black ${summary.within_plan ? "text-emerald-700" : "text-red-700"}`}>{summary.within_plan ? <CheckCircle2 size={18}/> : <AlertTriangle size={18}/>} {summary.within_plan ? "Within package" : "Over package"}</p><Link href="/addons" className="mt-3 inline-flex items-center gap-1 text-[10px] font-black text-[#285b55]">Add capacity <ArrowRight size={11}/></Link></article>
            </section>

            <section>
              <div className="mb-3 flex flex-wrap items-end justify-between gap-2"><div><p className="eyebrow-label">Usage & entitlements</p><h2 className="mt-1 text-xl font-black">Your live package capacity</h2></div><Link href="/addons" className="btn-secondary">Add capacity</Link></div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                <UsageCard label="Mailboxes" used={summary.usage.mailboxes} limit={summary.entitlements?.mailboxes ?? 0} icon={<Mail size={16}/>} />
                <UsageCard label="Domains" used={summary.usage.domains} limit={summary.entitlements?.domains ?? 0} icon={<Globe2 size={16}/>} />
                <UsageCard label="Hosted projects" used={summary.usage.hosted_projects} limit={summary.entitlements?.hosted_projects ?? 0} icon={<Server size={16}/>} />
                <UsageCard label="Databases" used={summary.usage.hosting_database_count} limit={summary.entitlements?.hosting_database_count ?? 0} icon={<Database size={16}/>} />
                <UsageCard label="Mailbox storage" used={bytes(summary.usage.allocated_storage_bytes)} limit={bytes(summary.entitlements?.storage_bytes || 0)} icon={<HardDrive size={16}/>} />
                <UsageCard label="App storage" used={bytes(summary.usage.hosting_storage_bytes)} limit={bytes(summary.entitlements?.hosting_storage_bytes || 0)} icon={<HardDrive size={16}/>} />
                <UsageCard label="Database storage" used={bytes(summary.usage.hosting_database_storage_bytes)} limit={bytes(summary.entitlements?.hosting_database_storage_bytes || 0)} icon={<Database size={16}/>} />
                <UsageCard label="Source storage" used={bytes(summary.usage.hosting_source_storage_bytes)} limit={bytes(summary.entitlements?.hosting_source_storage_bytes || 0)} icon={<Boxes size={16}/>} />
                <UsageCard label="API keys" used={summary.usage.api_keys} limit={summary.entitlements?.api_keys ?? 0} icon={<KeyRound size={16}/>} />
              </div>
            </section>
          </>
        ) : null}

        <section className="surface-card p-5">
          <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="eyebrow-label">Package management</p><h2 className="mt-1 text-xl font-black">Upgrade or change your package</h2><p className="mt-1 text-xs text-[var(--admin-muted)]">Capacity upgrades apply immediately. Safe downgrades are scheduled for renewal and are rejected when your current usage is above the target package.</p></div><Link href="/addons" className="btn-secondary">Need only extra capacity?</Link></div>
          {!canChangePlan && summary?.subscription ? <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs font-bold text-amber-800">Package changes are available only while the subscription is active or trialing. Settle overdue billing or reactivate the account first.</div> : null}
          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {plans.map((plan) => {
              const current = plan.code === summary?.subscription?.plan_code;
              const price = contract?.billing_interval === "monthly" ? plan.monthly_price_minor : (plan.annual_price_minor ?? plan.monthly_price_minor * 12);
              return <article key={plan.id} className={`rounded-2xl border p-4 ${current ? "border-[#285b55] bg-[#f3f8f5]" : plan.featured ? "border-[#d8c56a] bg-[#fffdf4]" : "border-[#e1e8e4] bg-white"}`}>
                <div className="flex items-start justify-between gap-3"><div><p className="text-sm font-black">{plan.name}</p><p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">{plan.description}</p></div>{current ? <span className="rounded-full bg-[#285b55] px-2 py-1 text-[8px] font-black uppercase text-white">Current</span> : plan.featured ? <span className="rounded-full bg-[#d8c56a] px-2 py-1 text-[8px] font-black uppercase text-[#123a38]">Featured</span> : null}</div>
                <p className="mt-4 text-2xl font-black">{money(price, plan.currency)} <span className="text-[10px] font-bold text-[var(--admin-muted)]">/{contract?.billing_interval === "monthly" ? "month" : "year"}</span></p>
                <div className="mt-4 grid grid-cols-2 gap-2 text-[10px] text-[var(--admin-muted)]"><span>{plan.included_mailboxes} mailboxes</span><span>{plan.included_domains} domains</span><span>{plan.included_hosted_projects} apps</span><span>{plan.hosting_database_limit} databases</span><span>{Math.round(plan.hosting_storage_mb / 1024)} GB app storage</span><span>{plan.support_level} support</span></div>
                <button disabled={current || !canChangePlan || busy === `plan:${plan.id}`} onClick={() => void changePlan(plan)} className="btn-primary mt-4 w-full disabled:cursor-not-allowed disabled:opacity-50">{current ? "Current package" : busy === `plan:${plan.id}` ? "Applying…" : "Choose package"}</button>
              </article>;
            })}
          </div>
        </section>

        {owner ? (
          <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <Link href="/finance" className="surface-card flex items-start gap-3 p-4"><ReceiptText size={18} className="text-[#285b55]"/><div><p className="text-sm font-black">Finance & invoices</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Platform finance workspace.</p></div></Link>
            <Link href="/packages" className="surface-card flex items-start gap-3 p-4"><Boxes size={18} className="text-[#285b55]"/><div><p className="text-sm font-black">Packages & pricing</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Owner-managed catalogue and limits.</p></div></Link>
            <Link href="/package-lifecycle" className="surface-card flex items-start gap-3 p-4"><ShieldCheck size={18} className="text-[#285b55]"/><div><p className="text-sm font-black">Package lifecycle</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Sellable, hidden, legacy and archived states.</p></div></Link>
          </section>
        ) : null}

        <section id="invoices" className="surface-card overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4"><div><h2 className="font-black">Invoices & payments</h2><p className="text-[10px] text-[var(--admin-muted)]">{provider?.configured ? "Secure DPO checkout is available." : "Online payment is not configured; manual/EFT invoicing remains available."}</p></div><button disabled={busy === "invoice"} className="btn-secondary" onClick={() => void invoice()}><CircleDollarSign size={14}/> {busy === "invoice" ? "Generating…" : "Generate current invoice"}</button></div>
          <div className="overflow-x-auto"><table className="min-w-full text-left text-xs"><thead><tr><th className="p-3">Invoice</th><th className="p-3">Amount</th><th className="p-3">Status</th><th className="p-3">Due</th><th className="p-3"/></tr></thead><tbody>{invoices.length ? invoices.map((item) => <tr key={item.id} className="border-t"><td className="p-3 font-mono font-bold">{item.invoice_number}</td><td className="p-3 font-black">{money(item.total_minor, item.currency)}</td><td className="p-3"><span className={`rounded-full px-2 py-1 text-[9px] font-black uppercase ${item.status === "paid" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{item.status}</span></td><td className="p-3">{item.due_at ? new Date(item.due_at).toLocaleDateString() : "—"}</td><td className="p-3">{provider?.configured && item.status !== "paid" && item.status !== "void" ? <button disabled={busy === item.id} className="btn-primary" onClick={() => void pay(item)}>Pay securely</button> : null}</td></tr>) : <tr><td colSpan={5} className="p-6 text-center text-[var(--admin-muted)]">No invoices yet.</td></tr>}</tbody></table></div>
        </section>
      </div>
    </ControlShell>
  );
}
