"use client";

import { useEffect, useMemo, useState } from "react";
import { Boxes, CheckCircle2, Clock3, Database, Globe2, HardDrive, Mail, Plus, RefreshCw, Server } from "lucide-react";
import { ControlShell } from "@/components/control-shell";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Membership = { tenant_id: string; tenant_name: string };
type Addon = {
  id: string; code: string; name: string; description: string; currency: string;
  monthly_price_minor: number; annual_price_minor?: number | null; setup_fee_minor: number;
  resource_key: string; amount_per_quantity: number; unit_label: string; max_quantity: number;
  assignment_id?: string; quantity?: number; status?: string;
};
type CompactPlan = {
  code: string; name: string; included_mailboxes: number; included_domains: number;
  included_storage_mb: number; included_hosted_projects: number; hosting_storage_mb: number;
  hosting_database_limit: number; hosting_database_storage_mb: number; hosting_source_storage_mb: number;
};
type Payload = {
  catalog: Addon[];
  assignments: Addon[];
  entitlements: { base_plan?: CompactPlan | null; effective_plan?: CompactPlan | null; active_addons?: { code: string; name: string; amount: number; quantity: number }[] };
};

const money = (value?: number | null) => value == null ? "Custom" : `M ${(value / 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
const gb = (value: number) => `${Math.round((value / 1024) * 10) / 10} GB`;

function Capacity({ label, base, effective }: { label: string; base: string | number; effective: string | number }) {
  const changed = String(base) !== String(effective);
  return <div className="rounded-2xl border border-[#e1e8e4] bg-white p-4"><p className="text-[9px] font-black uppercase tracking-[.11em] text-[#7d8d85]">{label}</p><p className="mt-2 text-xl font-black text-[#20342a]">{effective}</p><p className={`mt-1 text-[10px] font-bold ${changed ? "text-emerald-700" : "text-[#8a9891]"}`}>{changed ? `Base package: ${base}` : "Included in package"}</p></div>;
}

export default function AddonsPage() {
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [tenant, setTenant] = useState("");
  const [data, setData] = useState<Payload | null>(null);
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const response = await fetch(`${API}/me/memberships`, { credentials: "include", cache: "no-store" });
        if (!response.ok) throw new Error("Unable to load your company memberships.");
        const rows = (await response.json()) as Membership[];
        setMemberships(rows);
        const saved = window.localStorage.getItem("mailbox_dns_tenant");
        setTenant(rows.find((row) => row.tenant_id === saved)?.tenant_id || rows[0]?.tenant_id || "");
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Unable to load companies.");
        setLoading(false);
      }
    })();
  }, []);

  async function load(selected = tenant) {
    if (!selected) return;
    setLoading(true); setError("");
    try {
      window.localStorage.setItem("mailbox_dns_tenant", selected);
      const response = await fetch(`${API}/tenants/${selected}/addons`, { credentials: "include", cache: "no-store" });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Unable to load add-ons.");
      setData(body);
      setQuantities(Object.fromEntries((body.catalog || []).map((item: Addon) => [item.id, 1])));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load add-ons.");
    } finally { setLoading(false); }
  }

  useEffect(() => { if (tenant) void load(tenant); }, [tenant]);

  async function request(addon: Addon) {
    const quantity = Math.max(1, Math.min(addon.max_quantity, quantities[addon.id] || 1));
    setBusy(addon.id); setError(""); setMessage("");
    try {
      const response = await fetch(`${API}/tenants/${tenant}/addons/${addon.id}/request`, {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ quantity }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Unable to request add-on.");
      setMessage(`${addon.name} has been requested. Capacity increases after Ithute activates the add-on.`);
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to request add-on."); }
    finally { setBusy(null); }
  }

  const assigned = useMemo(() => new Map((data?.assignments || []).map((item) => [item.id, item])), [data]);
  const base = data?.entitlements?.base_plan;
  const effective = data?.entitlements?.effective_plan || base;

  return <ControlShell title="Add-ons & capacity" subtitle="Increase hosting, email, database and domain capacity without changing your whole package.">
    <div className="space-y-5">
      <section className="relative overflow-hidden rounded-[28px] bg-[#123a38] p-6 text-white shadow-[0_20px_55px_rgba(18,58,56,.17)] sm:p-7">
        <div className="absolute -right-20 -top-24 h-64 w-64 rounded-full bg-[#d8c56a]/10 blur-2xl" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between"><div><div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[.06] px-3 py-2 text-[9px] font-black uppercase tracking-[.13em] text-[#d8c56a]"><Boxes size={13}/> Flexible capacity</div><h1 className="mt-4 text-3xl font-black tracking-[-.045em]">Grow only what you need.</h1><p className="mt-3 max-w-2xl text-sm leading-7 text-white/65">Add mailboxes, domains, application storage, websites, databases or source storage. Requests remain pending until activated, so your enforced quota always matches your approved services.</p></div><div className="flex gap-2"><select value={tenant} onChange={(event)=>setTenant(event.target.value)} className="min-h-11 rounded-xl border border-white/15 bg-white/10 px-3 text-xs font-bold text-white outline-none">{memberships.map(item=><option className="text-black" key={item.tenant_id} value={item.tenant_id}>{item.tenant_name}</option>)}</select><button onClick={()=>void load()} className="grid h-11 w-11 place-items-center rounded-xl border border-white/15 bg-white/10" aria-label="Refresh add-ons"><RefreshCw size={15} className={loading?"animate-spin":""}/></button></div></div>
      </section>

      {message?<div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-xs font-bold text-emerald-800">{message}</div>:null}
      {error?<div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-xs font-bold text-red-700">{error}</div>:null}

      {base && effective ? <section><div className="mb-3 flex items-center justify-between"><div><p className="text-[10px] font-black uppercase tracking-[.12em] text-[#718078]">Effective entitlement</p><h2 className="mt-1 text-xl font-black text-[#20342a]">{base.name}{effective.code!==base.code?" + active add-ons":""}</h2></div></div><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Capacity label="Professional email" base={base.included_mailboxes} effective={effective.included_mailboxes}/><Capacity label="Managed domains" base={base.included_domains} effective={effective.included_domains}/><Capacity label="Hosted apps" base={base.included_hosted_projects} effective={effective.included_hosted_projects}/><Capacity label="App storage" base={gb(base.hosting_storage_mb)} effective={gb(effective.hosting_storage_mb)}/><Capacity label="Managed databases" base={base.hosting_database_limit} effective={effective.hosting_database_limit}/><Capacity label="Database storage" base={gb(base.hosting_database_storage_mb)} effective={gb(effective.hosting_database_storage_mb)}/><Capacity label="Git/ZIP source storage" base={gb(base.hosting_source_storage_mb)} effective={gb(effective.hosting_source_storage_mb)}/><Capacity label="Mailbox storage pool" base={gb(base.included_storage_mb)} effective={gb(effective.included_storage_mb)}/></div></section>:null}

      <section><div className="mb-3"><p className="text-[10px] font-black uppercase tracking-[.12em] text-[#718078]">Available upgrades</p><h2 className="mt-1 text-xl font-black text-[#20342a]">Add capacity</h2></div>{loading?<div className="grid min-h-48 place-items-center rounded-3xl border border-[#dfe7e2] bg-white text-sm font-semibold text-[#718078]">Loading capacity options…</div>:<div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{(data?.catalog||[]).map(addon=>{const current=assigned.get(addon.id);const q=quantities[addon.id]||1;return <article key={addon.id} className="rounded-[24px] border border-[#dfe7e2] bg-white p-5 shadow-sm"><div className="flex items-start justify-between gap-3"><div className="grid h-11 w-11 place-items-center rounded-2xl bg-[#edf4f1] text-[#285b55]">{addon.resource_key.includes("mail")?<Mail size={19}/>:addon.resource_key.includes("database")?<Database size={19}/>:addon.resource_key.includes("domain")?<Globe2 size={19}/>:addon.resource_key.includes("storage")?<HardDrive size={19}/>:<Server size={19}/>}</div>{current?<span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[9px] font-black uppercase ${current.status==="active"?"bg-emerald-50 text-emerald-700":"bg-amber-50 text-amber-700"}`}>{current.status==="active"?<CheckCircle2 size={11}/>:<Clock3 size={11}/>} {current.status}</span>:null}</div><h3 className="mt-4 text-base font-black text-[#20342a]">{addon.name}</h3><p className="mt-2 min-h-10 text-[11px] leading-5 text-[#718078]">{addon.description}</p><div className="mt-4 rounded-2xl bg-[#f7faf8] p-3"><div className="flex items-end justify-between gap-3"><div><p className="text-[9px] font-black uppercase tracking-[.1em] text-[#83928a]">Annual</p><p className="mt-1 text-lg font-black text-[#20342a]">{money(addon.annual_price_minor)}</p><p className="text-[9px] font-bold text-[#8a9891]">or {money(addon.monthly_price_minor)}/month</p></div><div className="text-right"><p className="text-[9px] font-black uppercase tracking-[.1em] text-[#83928a]">Per unit</p><p className="mt-1 text-xs font-black">+{addon.amount_per_quantity.toLocaleString()} {addon.unit_label}</p></div></div></div><div className="mt-4 flex gap-2"><input aria-label={`Quantity for ${addon.name}`} type="number" min={1} max={addon.max_quantity} value={q} onChange={event=>setQuantities(value=>({...value,[addon.id]:Math.max(1,Number(event.target.value)||1)}))} className="w-20 rounded-xl border border-[#d7e1dc] px-3 text-xs font-bold outline-none focus:border-[#285b55]"/><button disabled={busy===addon.id} onClick={()=>void request(addon)} className="flex min-h-11 flex-1 items-center justify-center gap-2 rounded-xl bg-[#123a38] px-4 text-xs font-black text-white disabled:opacity-60"><Plus size={14}/>{busy===addon.id?"Requesting…":current?.status==="active"?"Change quantity":"Request add-on"}</button></div></article>})}</div>}</section>

      {(data?.assignments||[]).length?<section className="rounded-[24px] border border-[#dfe7e2] bg-white p-5"><h2 className="text-lg font-black text-[#20342a]">Your add-on requests</h2><div className="mt-4 overflow-x-auto"><table className="w-full min-w-[620px] text-left text-xs"><thead><tr className="border-b text-[9px] font-black uppercase tracking-[.09em] text-[#829087]"><th className="p-3">Add-on</th><th className="p-3">Quantity</th><th className="p-3">Status</th><th className="p-3">Requested</th></tr></thead><tbody>{data!.assignments.map(item=><tr key={item.assignment_id} className="border-b border-[#edf1ef]"><td className="p-3 font-black">{item.name}</td><td className="p-3">{item.quantity}</td><td className="p-3 capitalize">{item.status}</td><td className="p-3 text-[#718078]">{item.assignment_id?"Recorded":"—"}</td></tr>)}</tbody></table></div></section>:null}
    </div>
  </ControlShell>;
}
