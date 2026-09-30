"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { Boxes, BookOpen, Database, PackageOpen, Rocket, Server } from "lucide-react";
import { ControlShell } from "@/components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Membership = { tenant_id: string; tenant_name: string };
type Reseller = { status: string; max_customers: number; customer_count: number; discount_bps: number };
type Customer = { id: string; tenant_id: string; name: string; slug: string; status: string };
type Brand = { brand_name: string; support_email?: string | null; logo_url?: string | null; primary_color?: string | null; custom_hostname?: string | null };

async function api(path: string, init?: RequestInit) {
  return fetch(`${API}${path}`, { credentials: "include", ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
}

export default function HostingCompany() {
  const [email, setEmail] = useState("");
  const [tenant, setTenant] = useState("");
  const [tenants, setTenants] = useState<Membership[]>([]);
  const [reseller, setReseller] = useState<Reseller | null>(null);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [brand, setBrand] = useState<Brand>({ brand_name: "Ithute Hosting" });
  const [registrar, setRegistrar] = useState<{ configured: boolean; provider: string } | null>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    void (async () => {
      const me = await api("/auth/me");
      if (me.ok) setEmail((await me.json()).email || "");
      const memberships = await api("/me/memberships");
      if (memberships.ok) {
        const rows = await memberships.json();
        setTenants(rows);
        setTenant(localStorage.getItem("mailbox_dns_tenant") || rows[0]?.tenant_id || "");
      }
    })();
  }, []);

  useEffect(() => {
    if (!tenant) return;
    localStorage.setItem("mailbox_dns_tenant", tenant);
    void load();
  }, [tenant]);

  async function load() {
    const [resellerResponse, customersResponse, brandResponse, registrarResponse] = await Promise.all([
      api(`/tenants/${tenant}/reseller`),
      api(`/tenants/${tenant}/reseller/customers`),
      api(`/tenants/${tenant}/reseller/brand`),
      api(`/tenants/${tenant}/registrar/status`),
    ]);
    setReseller(resellerResponse.ok ? await resellerResponse.json() : null);
    if (customersResponse.ok) setCustomers((await customersResponse.json()).items || []);
    if (brandResponse.ok) setBrand(await brandResponse.json());
    if (registrarResponse.ok) setRegistrar(await registrarResponse.json());
  }

  async function saveBrand(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const response = await api(`/tenants/${tenant}/reseller/brand`, {
      method: "PUT",
      body: JSON.stringify({
        brand_name: form.get("brand_name"),
        support_email: form.get("support_email") || null,
        logo_url: form.get("logo_url") || null,
        primary_color: form.get("primary_color") || null,
        custom_hostname: form.get("hostname") || null,
      }),
    });
    setMsg(response.ok ? "White-label brand saved." : "Unable to save brand");
    if (response.ok) await load();
  }

  async function createCustomer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const response = await api(`/tenants/${tenant}/reseller/customers`, {
      method: "POST",
      body: JSON.stringify({
        company_name: form.get("company"),
        admin_name: form.get("admin"),
        admin_email: form.get("email"),
        admin_password: form.get("password"),
        plan_code: form.get("plan"),
      }),
    });
    const body = await response.json().catch(() => ({}));
    setMsg(response.ok ? `Customer ${body.tenant_name || "created"} provisioned.` : String(body.detail || "Unable to provision customer"));
    if (response.ok) await load();
  }

  function manageCustomer(customer: Customer) {
    localStorage.setItem("mailbox_dns_tenant", customer.tenant_id);
  }

  return (
    <ControlShell title="Hosting company" subtitle="Application hosting, packages, deployments, resellers and white-label services" userEmail={email}>
      <div className="space-y-4">
        <section className="surface-card p-5">
          <p className="eyebrow-label">Ithute hosting business</p>
          <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="text-2xl font-black">Hosting company control plane</h1>
              <p className="mt-1 max-w-3xl text-xs leading-5 text-[var(--admin-muted)]">Operate managed websites and systems alongside branding packages, domains, DNS, professional email, reseller customers and white-label services.</p>
            </div>
            <select className="input max-w-sm" value={tenant} onChange={(event) => setTenant(event.target.value)}>
              {tenants.map((row) => <option key={row.tenant_id} value={row.tenant_id}>{row.tenant_name}</option>)}
            </select>
          </div>
        </section>

        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <Link href="/hosting" className="surface-card group p-5 transition hover:-translate-y-0.5 hover:border-[#9dbbb0]">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf4f1] text-[#285b55]"><Server size={18} /></span>
            <h2 className="mt-4 text-sm font-black">Application hosting</h2>
            <p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">Allocate websites and systems under package-enforced storage, RAM, CPU and PID limits.</p>
            <p className="mt-3 text-xs font-black text-[#285b55]">Open hosted projects →</p>
          </Link>
          <Link href="/hosting-resources" className="surface-card group p-5 transition hover:-translate-y-0.5 hover:border-[#9dbbb0]">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf4f1] text-[#285b55]"><Database size={18} /></span>
            <h2 className="mt-4 text-sm font-black">Sources & databases</h2>
            <p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">Connect Git and allocate project-scoped PostgreSQL or MySQL resources.</p>
            <p className="mt-3 text-xs font-black text-[#285b55]">Open resources →</p>
          </Link>
          <Link href="/hosting-operations" className="surface-card group p-5 transition hover:-translate-y-0.5 hover:border-[#9dbbb0]">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf4f1] text-[#285b55]"><Rocket size={18} /></span>
            <h2 className="mt-4 text-sm font-black">Deployments & environment</h2>
            <p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">Queue immutable releases, protect environment values, inspect health and roll back.</p>
            <p className="mt-3 text-xs font-black text-[#285b55]">Open operations →</p>
          </Link>
          <Link href="/packages" className="surface-card group p-5 transition hover:-translate-y-0.5 hover:border-[#9dbbb0]">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf4f1] text-[#285b55]"><PackageOpen size={18} /></span>
            <h2 className="mt-4 text-sm font-black">Products & capacity</h2>
            <p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">Manage packages and declare safe sellable VPS capacity.</p>
            <p className="mt-3 text-xs font-black text-[#285b55]">Manage packages →</p>
          </Link>
          <Link href="/hosting-docs" className="surface-card group p-5 transition hover:-translate-y-0.5 hover:border-[#9dbbb0]">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf4f1] text-[#285b55]"><BookOpen size={18} /></span>
            <h2 className="mt-4 text-sm font-black">Hosting rules</h2>
            <p className="mt-2 text-[10px] leading-5 text-[var(--admin-muted)]">Read isolation, build, domain, email, resource and prohibited-workload rules.</p>
            <p className="mt-3 text-xs font-black text-[#285b55]">Open hosting manual →</p>
          </Link>
        </section>

        {msg ? <div className="surface-card p-3 text-xs font-bold">{msg}</div> : null}

        {reseller ? (
          <section className="grid gap-3 md:grid-cols-4">
            <article className="surface-card p-4"><p className="eyebrow-label">Status</p><p className="mt-2 text-xl font-black">{reseller.status}</p></article>
            <article className="surface-card p-4"><p className="eyebrow-label">Customers</p><p className="mt-2 text-xl font-black">{reseller.customer_count} / {reseller.max_customers}</p></article>
            <article className="surface-card p-4"><p className="eyebrow-label">Discount</p><p className="mt-2 text-xl font-black">{(reseller.discount_bps / 100).toFixed(2)}%</p></article>
            <article className="surface-card p-4"><p className="eyebrow-label">Registrar</p><p className="mt-2 text-xl font-black">{registrar?.configured ? "Connected" : "Credential-gated"}</p></article>
          </section>
        ) : (
          <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm"><b>This tenant is not yet enabled as a reseller.</b> Application hosting is separate from reseller status. A platform owner can enable reseller services when needed.</section>
        )}

        {reseller ? (
          <section className="grid gap-4 xl:grid-cols-2">
            <form className="surface-card p-5" onSubmit={saveBrand}>
              <h2 className="font-black">White-label brand</h2>
              <div className="mt-4 grid gap-3">
                <input className="input" name="brand_name" defaultValue={brand.brand_name} placeholder="Brand name" required />
                <input className="input" name="support_email" type="email" defaultValue={brand.support_email || ""} placeholder="Support email" />
                <input className="input" name="logo_url" defaultValue={brand.logo_url || ""} placeholder="Logo URL" />
                <input className="input" name="primary_color" defaultValue={brand.primary_color || ""} placeholder="#123a38" />
                <input className="input" name="hostname" defaultValue={brand.custom_hostname || ""} placeholder="hosting.customer.co.ls" />
                <button className="btn-primary">Save white-label brand</button>
              </div>
            </form>

            <form className="surface-card p-5" onSubmit={createCustomer}>
              <div className="flex items-center gap-2"><Boxes size={16} /><h2 className="font-black">Provision reseller customer</h2></div>
              <div className="mt-4 grid gap-3">
                <input className="input" name="company" placeholder="Customer company" required />
                <input className="input" name="admin" placeholder="Administrator name" required />
                <input className="input" type="email" name="email" placeholder="Administrator email" required />
                <input className="input" type="password" name="password" minLength={12} placeholder="Temporary strong password" required />
                <select className="input" name="plan"><option value="starter">Ithute Start — M185</option><option value="grow">Ithute Grow — M295</option><option value="business">Ithute Business — M495</option><option value="professional">Ithute Professional — M795</option><option value="enterprise">Ithute Enterprise — from M1,500</option></select>
                <button className="btn-primary">Provision customer</button>
              </div>
            </form>
          </section>
        ) : null}

        <section className="surface-card overflow-hidden">
          <div className="border-b p-4 font-black">Reseller customers</div>
          <div className="space-y-2 p-4">
            {customers.map((customer) => <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3 text-xs" key={customer.id}><div><b>{customer.name}</b><span className="ml-2 text-[var(--admin-muted)]">{customer.status}</span><p className="mt-1 text-[10px] text-[var(--admin-muted)]">{customer.slug}</p></div><div className="flex gap-2"><Link href="/hosting" className="btn-secondary" onClick={() => manageCustomer(customer)}>Hosting</Link><Link href="/hosting-resources" className="btn-secondary" onClick={() => manageCustomer(customer)}>Sources & DB</Link></div></div>)}
            {!customers.length ? <p className="text-xs text-[var(--admin-muted)]">No reseller customers yet.</p> : null}
          </div>
        </section>
      </div>
    </ControlShell>
  );
}
