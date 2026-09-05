"use client";

import { useEffect, useMemo, useState } from "react";
import { Archive, BadgeDollarSign, Boxes, CheckCircle2, Pencil, Plus, RefreshCw } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { PageHeader } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

type Plan = {
  id: string;
  code: string;
  name: string;
  currency: string;
  monthly_price_minor: number;
  included_mailboxes: number;
  included_domains: number;
  included_storage_mb: number;
  max_api_keys: number;
  is_active: boolean;
};

type Draft = {
  code: string;
  name: string;
  monthlyPrice: string;
  mailboxes: string;
  domains: string;
  storageGb: string;
  apiKeys: string;
};

const blankDraft: Draft = { code: "", name: "", monthlyPrice: "", mailboxes: "10", domains: "1", storageGb: "25", apiKeys: "3" };

function draftFrom(plan: Plan): Draft {
  return {
    code: plan.code,
    name: plan.name,
    monthlyPrice: (plan.monthly_price_minor / 100).toString(),
    mailboxes: plan.included_mailboxes.toString(),
    domains: plan.included_domains.toString(),
    storageGb: (plan.included_storage_mb / 1000).toString(),
    apiKeys: plan.max_api_keys.toString(),
  };
}

function formatPrice(plan: Plan) {
  return `M ${(plan.monthly_price_minor / 100).toLocaleString()}`;
}

export default function PackagesPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [draft, setDraft] = useState<Draft>(blankDraft);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const editing = useMemo(() => plans.find((plan) => plan.id === editingId) || null, [plans, editingId]);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API}/platform/billing/plans`, { credentials: "include", cache: "no-store" });
      if (!response.ok) throw new Error(response.status === 403 ? "Only the platform owner can manage packages." : "Unable to load packages.");
      const body = await response.json();
      setPlans(body.items || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load packages.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  function edit(plan: Plan) {
    setEditingId(plan.id);
    setDraft(draftFrom(plan));
    setMessage("");
    setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function createNew() {
    setEditingId(null);
    setDraft(blankDraft);
    setMessage("");
    setError("");
  }

  async function save() {
    setSaving(true);
    setMessage("");
    setError("");
    const payload = {
      ...(editingId ? {} : { code: draft.code.trim().toLowerCase(), currency: "LSL", is_active: true }),
      name: draft.name.trim(),
      monthly_price_minor: Math.round(Number(draft.monthlyPrice) * 100),
      included_mailboxes: Number(draft.mailboxes),
      included_domains: Number(draft.domains),
      included_storage_mb: Math.round(Number(draft.storageGb) * 1000),
      max_api_keys: Number(draft.apiKeys),
    };
    try {
      const response = await fetch(editingId ? `${API}/platform/billing/plans/${editingId}` : `${API}/platform/billing/plans`, {
        method: editingId ? "PATCH" : "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Unable to save package.");
      setMessage(editingId ? "Package updated. Public pricing and tenant limits now use the new values." : "Package created and published to the pricing catalog.");
      await load();
      if (!editingId) createNew();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save package.");
    } finally {
      setSaving(false);
    }
  }

  async function toggle(plan: Plan) {
    setMessage("");
    setError("");
    try {
      const response = await fetch(`${API}/platform/billing/plans/${plan.id}`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !plan.is_active }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Unable to change package status.");
      setMessage(body.is_active ? `${body.name} is active and visible on pricing.` : `${body.name} has been deactivated.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to change package status.");
    }
  }

  const fields: { key: keyof Draft; label: string; helper: string; type?: string }[] = [
    { key: "name", label: "Package name", helper: "Customer-facing name, e.g. Business" },
    { key: "code", label: "Package code", helper: editing ? "Code is permanent after creation." : "Lowercase identifier, e.g. business-plus" },
    { key: "monthlyPrice", label: "Monthly price (M)", helper: "Maloti charged per month", type: "number" },
    { key: "mailboxes", label: "Included mailboxes", helper: "Maximum individual email accounts", type: "number" },
    { key: "domains", label: "Hosted domains", helper: "Maximum customer domains under this subscription", type: "number" },
    { key: "storageGb", label: "Allocated storage (GB)", helper: "Shared quota pool across the tenant", type: "number" },
    { key: "apiKeys", label: "API keys", helper: "Maximum active integration credentials", type: "number" },
  ];

  return <ControlShell title="Packages & pricing" subtitle="Create commercial packages and control the limits enforced by billing">
    <div className="space-y-5">
      <PageHeader eyebrow="Commercial catalog" title="Package control centre" description="Create and edit the packages customers see on the public pricing page. Mailbox, domain, storage and API-key values are real entitlements enforced by the platform." />

      <section className="grid gap-4 xl:grid-cols-[1.05fr_.95fr]">
        <div className="surface-card p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><p className="text-xs font-black text-[var(--admin-ink)]">{editing ? `Edit ${editing.name}` : "Create a package"}</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Pricing is stored in LSL and published as Maloti.</p></div>
            <button className="btn-secondary" onClick={createNew}><Plus size={14}/>New package</button>
          </div>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            {fields.map((field) => <label key={field.key} className="block"><span className="text-[10px] font-black uppercase tracking-[.08em] text-[#617168]">{field.label}</span><input disabled={field.key === "code" && Boolean(editing)} type={field.type || "text"} min={field.type === "number" ? 0 : undefined} step={field.key === "monthlyPrice" || field.key === "storageGb" ? "0.01" : "1"} value={draft[field.key]} onChange={(event) => setDraft((current) => ({ ...current, [field.key]: event.target.value }))} className="mt-1.5 w-full rounded-xl border border-[#dce4df] bg-white px-3 py-2.5 text-sm font-semibold outline-none focus:border-[#2b605a] disabled:bg-[#f2f4f3]"/><span className="mt-1 block text-[9px] leading-4 text-[#8a9790]">{field.helper}</span></label>)}
          </div>
          {message ? <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{message}</div> : null}
          {error ? <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}
          <button onClick={() => void save()} disabled={saving || !draft.name || (!editing && !draft.code)} className="btn-primary mt-5 disabled:opacity-50"><CheckCircle2 size={14}/>{saving ? "Saving…" : editing ? "Save package changes" : "Create package"}</button>
        </div>

        <div className="surface-card p-4 sm:p-5">
          <div className="flex items-start gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef4f1] text-[#285b55]"><BadgeDollarSign size={18}/></div><div><h2 className="text-sm font-black text-[var(--admin-ink)]">What these controls mean</h2><p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">Package limits are not marketing-only numbers. Mailbox DNS checks subscription entitlements before provisioning resources.</p></div></div>
          <div className="mt-4 space-y-3 text-[10px] leading-5 text-[#617168]"><p><b className="text-[#263a31]">Mailboxes</b> — individual addresses/users a company can create.</p><p><b className="text-[#263a31]">Hosted domains</b> — separate domains the company may onboard and manage.</p><p><b className="text-[#263a31]">Storage</b> — the total allocated mailbox quota pool for the company.</p><p><b className="text-[#263a31]">API keys</b> — active automation/integration credentials.</p></div>
          <a href="/docs#packages" className="mt-5 inline-flex text-xs font-black text-[#285b55]">Open package documentation →</a>
        </div>
      </section>

      <section className="surface-card p-4 sm:p-5">
        <div className="flex items-center justify-between gap-3"><div><h2 className="text-sm font-black text-[var(--admin-ink)]">Published package catalog</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Inactive packages disappear from new signups. A package in use cannot be deactivated until its subscriptions are moved.</p></div><button className="icon-button" onClick={() => void load()} aria-label="Refresh packages"><RefreshCw size={15}/></button></div>
        {loading ? <p className="mt-6 text-xs text-[var(--admin-muted)]">Loading packages…</p> : <div className="mt-5 grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">{plans.map((plan) => <article key={plan.id} className={`rounded-2xl border p-4 ${plan.is_active ? "border-[#dce5e0] bg-white" : "border-[#e4e5e4] bg-[#f5f6f5] opacity-75"}`}><div className="flex items-start justify-between gap-3"><div><div className="flex items-center gap-2"><Boxes size={16} className="text-[#285b55]"/><h3 className="text-sm font-black text-[#21342a]">{plan.name}</h3></div><p className="mt-1 text-[9px] font-bold uppercase tracking-[.08em] text-[#8a9790]">{plan.code} · {plan.is_active ? "Active" : "Inactive"}</p></div><p className="text-lg font-black text-[#123a38]">{formatPrice(plan)}<span className="text-[9px] text-[#819087]">/mo</span></p></div><div className="mt-4 grid grid-cols-2 gap-2 text-[10px]"><div className="rounded-xl bg-[#f4f7f5] p-2.5"><b>{plan.included_mailboxes}</b><br/>mailboxes</div><div className="rounded-xl bg-[#f4f7f5] p-2.5"><b>{plan.included_domains}</b><br/>domains</div><div className="rounded-xl bg-[#f4f7f5] p-2.5"><b>{Math.round(plan.included_storage_mb / 1000)} GB</b><br/>storage</div><div className="rounded-xl bg-[#f4f7f5] p-2.5"><b>{plan.max_api_keys}</b><br/>API keys</div></div><div className="mt-4 flex flex-wrap gap-2"><button className="btn-secondary" onClick={() => edit(plan)}><Pencil size={13}/>Edit</button><button className="btn-secondary" onClick={() => void toggle(plan)}><Archive size={13}/>{plan.is_active ? "Deactivate" : "Activate"}</button></div></article>)}</div>}
      </section>
    </div>
  </ControlShell>;
}
