"use client";

import { useEffect, useMemo, useState } from "react";
import { Archive, BadgeDollarSign, Boxes, CheckCircle2, Cpu, HardDrive, Palette, Pencil, Plus, RefreshCw, Server } from "lucide-react";
import { ControlShell } from "@/components/control-shell";
import { PageHeader } from "@/components/ui-kit";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";

const PRODUCT_CATEGORIES = [
  "Website & Hosting",
  "Professional Email",
  "Application/System Hosting",
  "Logo Design",
  "Branding & Corporate Identity",
  "Company Profiles",
  "Business Documents & Templates",
  "Domains & DNS",
  "Custom Digital Services",
];

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
  included_hosted_projects: number;
  hosting_storage_mb: number;
  hosting_memory_mb_per_project: number;
  hosting_cpu_millicores_per_project: number;
  hosting_pids_per_project: number;
  product_category: string;
  description: string;
  website_pages: number;
  includes_website_design: boolean;
  includes_logo_design: boolean;
  includes_brand_guide: boolean;
  includes_company_profile: boolean;
  includes_letterhead: boolean;
  includes_page_headers_footers: boolean;
  includes_business_templates: boolean;
  included_revisions: number;
  content_updates_per_month: number;
  support_level: string;
  minimum_term_months: number;
  price_from: boolean;
  is_active: boolean;
};

type Draft = {
  code: string;
  name: string;
  monthlyPrice: string;
  mailboxes: string;
  domains: string;
  mailStorageGb: string;
  apiKeys: string;
  hostedProjects: string;
  hostingStorageGb: string;
  memoryMb: string;
  cpuMillicores: string;
  pids: string;
  productCategory: string;
  description: string;
  websitePages: string;
  includesWebsiteDesign: boolean;
  includesLogoDesign: boolean;
  includesBrandGuide: boolean;
  includesCompanyProfile: boolean;
  includesLetterhead: boolean;
  includesPageHeadersFooters: boolean;
  includesBusinessTemplates: boolean;
  includedRevisions: string;
  contentUpdatesPerMonth: string;
  supportLevel: string;
  minimumTermMonths: string;
  priceFrom: boolean;
};

type Node = {
  id: string;
  name: string;
  hostname: string;
  public_ip?: string | null;
  status: string;
  accepts_new_projects: boolean;
  allocatable: { storage_mb: number; memory_mb: number; cpu_millicores: number };
  allocated: { storage_mb: number; memory_mb: number; cpu_millicores: number; projects: number };
  available: { storage_mb: number; memory_mb: number; cpu_millicores: number };
};

const blankDraft: Draft = {
  code: "",
  name: "",
  monthlyPrice: "",
  mailboxes: "10",
  domains: "1",
  mailStorageGb: "25",
  apiKeys: "3",
  hostedProjects: "1",
  hostingStorageGb: "1",
  memoryMb: "512",
  cpuMillicores: "500",
  pids: "128",
  productCategory: "Website & Hosting",
  description: "",
  websitePages: "1",
  includesWebsiteDesign: true,
  includesLogoDesign: false,
  includesBrandGuide: false,
  includesCompanyProfile: false,
  includesLetterhead: false,
  includesPageHeadersFooters: true,
  includesBusinessTemplates: false,
  includedRevisions: "1",
  contentUpdatesPerMonth: "0",
  supportLevel: "standard",
  minimumTermMonths: "12",
  priceFrom: false,
};

function draftFrom(plan: Plan): Draft {
  return {
    code: plan.code,
    name: plan.name,
    monthlyPrice: (plan.monthly_price_minor / 100).toString(),
    mailboxes: plan.included_mailboxes.toString(),
    domains: plan.included_domains.toString(),
    mailStorageGb: (plan.included_storage_mb / 1024).toString(),
    apiKeys: plan.max_api_keys.toString(),
    hostedProjects: plan.included_hosted_projects.toString(),
    hostingStorageGb: (plan.hosting_storage_mb / 1024).toString(),
    memoryMb: plan.hosting_memory_mb_per_project.toString(),
    cpuMillicores: plan.hosting_cpu_millicores_per_project.toString(),
    pids: plan.hosting_pids_per_project.toString(),
    productCategory: plan.product_category,
    description: plan.description,
    websitePages: plan.website_pages.toString(),
    includesWebsiteDesign: plan.includes_website_design,
    includesLogoDesign: plan.includes_logo_design,
    includesBrandGuide: plan.includes_brand_guide,
    includesCompanyProfile: plan.includes_company_profile,
    includesLetterhead: plan.includes_letterhead,
    includesPageHeadersFooters: plan.includes_page_headers_footers,
    includesBusinessTemplates: plan.includes_business_templates,
    includedRevisions: plan.included_revisions.toString(),
    contentUpdatesPerMonth: plan.content_updates_per_month.toString(),
    supportLevel: plan.support_level,
    minimumTermMonths: plan.minimum_term_months.toString(),
    priceFrom: plan.price_from,
  };
}

function formatPrice(plan: Plan) {
  return `${plan.price_from ? "From " : ""}M ${(plan.monthly_price_minor / 100).toLocaleString()}`;
}

function packageHighlights(plan: Plan) {
  const rows: string[] = [];
  if (plan.includes_website_design) rows.push(`${plan.website_pages || "Custom"} website page${plan.website_pages === 1 ? "" : "s"}`);
  if (plan.includes_logo_design) rows.push("Logo");
  if (plan.includes_brand_guide) rows.push("Brand guide");
  if (plan.includes_company_profile) rows.push("Company profile");
  if (plan.includes_letterhead) rows.push("Letterhead");
  if (plan.includes_page_headers_footers) rows.push("Headers & footers");
  if (plan.includes_business_templates) rows.push("Business templates");
  return rows;
}

export default function PackagesPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [nodes, setNodes] = useState<Node[]>([]);
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
      const [plansResponse, nodesResponse] = await Promise.all([
        fetch(`${API}/platform/billing/plans`, { credentials: "include", cache: "no-store" }),
        fetch(`${API}/platform/hosting/nodes`, { credentials: "include", cache: "no-store" }),
      ]);
      if (!plansResponse.ok) throw new Error(plansResponse.status === 403 ? "Only the system owner can manage packages." : "Unable to load packages.");
      const plansBody = await plansResponse.json();
      setPlans(plansBody.items || []);
      if (nodesResponse.ok) setNodes((await nodesResponse.json()).items || []);
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
    const hostedProjects = Number(draft.hostedProjects);
    const payload = {
      ...(editingId ? {} : { code: draft.code.trim().toLowerCase(), currency: "LSL", is_active: true }),
      name: draft.name.trim(),
      monthly_price_minor: Math.round(Number(draft.monthlyPrice) * 100),
      included_mailboxes: Number(draft.mailboxes),
      included_domains: Number(draft.domains),
      included_storage_mb: Math.round(Number(draft.mailStorageGb) * 1024),
      max_api_keys: Number(draft.apiKeys),
      included_hosted_projects: hostedProjects,
      hosting_storage_mb: hostedProjects > 0 ? Math.round(Number(draft.hostingStorageGb) * 1024) : 0,
      hosting_memory_mb_per_project: hostedProjects > 0 ? Number(draft.memoryMb) : 0,
      hosting_cpu_millicores_per_project: hostedProjects > 0 ? Number(draft.cpuMillicores) : 0,
      hosting_pids_per_project: hostedProjects > 0 ? Number(draft.pids) : 0,
      product_category: draft.productCategory,
      description: draft.description.trim(),
      website_pages: Number(draft.websitePages),
      includes_website_design: draft.includesWebsiteDesign,
      includes_logo_design: draft.includesLogoDesign,
      includes_brand_guide: draft.includesBrandGuide,
      includes_company_profile: draft.includesCompanyProfile,
      includes_letterhead: draft.includesLetterhead,
      includes_page_headers_footers: draft.includesPageHeadersFooters,
      includes_business_templates: draft.includesBusinessTemplates,
      included_revisions: Number(draft.includedRevisions),
      content_updates_per_month: Number(draft.contentUpdatesPerMonth),
      support_level: draft.supportLevel,
      minimum_term_months: Number(draft.minimumTermMonths),
      price_from: draft.priceFrom,
    };
    try {
      const response = await fetch(editingId ? `${API}/platform/billing/plans/${editingId}` : `${API}/platform/billing/plans`, {
        method: editingId ? "PATCH" : "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Unable to save package.");
      setMessage(editingId ? "Package updated. Commercial deliverables and resource entitlements now use the new values." : "Package created and published to the pricing catalog.");
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

  async function createNode(form: HTMLFormElement) {
    const data = new FormData(form);
    setMessage("");
    setError("");
    const payload = {
      name: String(data.get("node_name") || ""),
      hostname: String(data.get("node_hostname") || ""),
      public_ip: String(data.get("node_ip") || "") || null,
      allocatable_storage_mb: Math.round(Number(data.get("node_storage_gb")) * 1024),
      allocatable_memory_mb: Number(data.get("node_memory_mb")),
      allocatable_cpu_millicores: Math.round(Number(data.get("node_cpu_cores")) * 1000),
      accepts_new_projects: true,
    };
    const response = await fetch(`${API}/platform/hosting/nodes`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      setError(typeof body.detail === "string" ? body.detail : "Unable to register hosting capacity.");
      return;
    }
    form.reset();
    setMessage("Hosting node capacity registered. New projects can now be allocated without consuming reserved platform headroom.");
    await load();
  }

  const resourceFields: { key: keyof Pick<Draft, "name" | "code" | "monthlyPrice" | "hostedProjects" | "hostingStorageGb" | "memoryMb" | "cpuMillicores" | "pids" | "domains" | "mailboxes" | "mailStorageGb" | "apiKeys">; label: string; helper: string; type?: string }[] = [
    { key: "name", label: "Package name", helper: "Customer-facing name, e.g. Ithute Business" },
    { key: "code", label: "Package code", helper: editing ? "Code is permanent after creation." : "Lowercase identifier, e.g. business-hosting" },
    { key: "monthlyPrice", label: "Monthly price (M)", helper: "Maloti charged per month", type: "number" },
    { key: "hostedProjects", label: "Hosted projects", helper: "Websites or simple systems this organization may host", type: "number" },
    { key: "hostingStorageGb", label: "App storage (GB)", helper: "Total application storage pool. Commercial packages are limited to 1–10 GB.", type: "number" },
    { key: "memoryMb", label: "RAM per project (MB)", helper: "Hard memory ceiling for each hosted workload", type: "number" },
    { key: "cpuMillicores", label: "CPU per project (millicores)", helper: "1000 millicores = 1 CPU core", type: "number" },
    { key: "pids", label: "Processes per project", helper: "Maximum process/PID count for each workload", type: "number" },
    { key: "domains", label: "Hosted domains", helper: "Maximum customer domains under this subscription", type: "number" },
    { key: "mailboxes", label: "Included mailboxes", helper: "Professional email accounts included in the subscription", type: "number" },
    { key: "mailStorageGb", label: "Mail storage (GB)", helper: "Separate mailbox quota pool; never shared with app storage", type: "number" },
    { key: "apiKeys", label: "API keys", helper: "Maximum active integration credentials", type: "number" },
  ];

  const creativeToggles: { key: keyof Pick<Draft, "includesWebsiteDesign" | "includesLogoDesign" | "includesBrandGuide" | "includesCompanyProfile" | "includesLetterhead" | "includesPageHeadersFooters" | "includesBusinessTemplates">; label: string }[] = [
    { key: "includesWebsiteDesign", label: "Website design" },
    { key: "includesLogoDesign", label: "Logo design / setup" },
    { key: "includesBrandGuide", label: "Brand identity guide" },
    { key: "includesCompanyProfile", label: "Company profile" },
    { key: "includesLetterhead", label: "Letterhead" },
    { key: "includesPageHeadersFooters", label: "Page headers & footers" },
    { key: "includesBusinessTemplates", label: "Invoice / quotation / document templates" },
  ];

  return <ControlShell title="Packages & pricing" subtitle="Create website, branding, document, hosting, email and DNS packages">
    <div className="space-y-5">
      <PageHeader eyebrow="Ithute commercial catalog" title="Product & package control centre" description="Define the monthly price, creative deliverables and hard hosting entitlements in one product. The public pricing page reads directly from this catalogue." />

      <section className="grid gap-4 xl:grid-cols-[1.2fr_.8fr]">
        <div className="surface-card p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><p className="text-xs font-black text-[var(--admin-ink)]">{editing ? `Edit ${editing.name}` : "Create a commercial package"}</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Creative services and technical capacity are sold together but tracked separately.</p></div>
            <button className="btn-secondary" onClick={createNew}><Plus size={14}/>New package</button>
          </div>

          <div className="mt-5 rounded-2xl border border-[#e0e6e2] bg-[#fafbfa] p-4">
            <div className="flex items-center gap-2"><BadgeDollarSign size={16} className="text-[#285b55]"/><h2 className="text-xs font-black">Commercial identity</h2></div>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <label className="block"><span className="text-[10px] font-black uppercase tracking-[.08em] text-[#617168]">Product category</span><select className="input mt-1.5 w-full" value={draft.productCategory} onChange={(event) => setDraft((current) => ({ ...current, productCategory: event.target.value }))}>{PRODUCT_CATEGORIES.map((category) => <option key={category}>{category}</option>)}</select></label>
              <label className="block"><span className="text-[10px] font-black uppercase tracking-[.08em] text-[#617168]">Support level</span><select className="input mt-1.5 w-full" value={draft.supportLevel} onChange={(event) => setDraft((current) => ({ ...current, supportLevel: event.target.value }))}><option value="standard">Standard</option><option value="priority">Priority</option><option value="dedicated">Dedicated</option></select></label>
              <label className="block sm:col-span-2"><span className="text-[10px] font-black uppercase tracking-[.08em] text-[#617168]">Customer-facing description</span><textarea className="input mt-1.5 min-h-24 w-full resize-y" maxLength={500} value={draft.description} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} placeholder="What the customer receives and who this package is for"/></label>
              <label className="block"><span className="text-[10px] font-black uppercase tracking-[.08em] text-[#617168]">Minimum term (months)</span><input className="input mt-1.5 w-full" type="number" min="0" max="36" value={draft.minimumTermMonths} onChange={(event) => setDraft((current) => ({ ...current, minimumTermMonths: event.target.value }))}/><span className="mt-1 block text-[9px] text-[#8a9790]">Use 12 months when the package includes initial creative build work.</span></label>
              <label className="flex items-center gap-3 rounded-xl border border-[#dce4df] bg-white px-3 py-3 text-xs font-bold"><input type="checkbox" checked={draft.priceFrom} onChange={(event) => setDraft((current) => ({ ...current, priceFrom: event.target.checked }))}/>Display price as “From”</label>
            </div>
          </div>

          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            {resourceFields.map((field) => <label key={field.key} className="block"><span className="text-[10px] font-black uppercase tracking-[.08em] text-[#617168]">{field.label}</span><input disabled={field.key === "code" && Boolean(editing)} type={field.type || "text"} min={field.type === "number" ? 0 : undefined} max={field.key === "hostingStorageGb" ? 10 : undefined} step={field.key === "monthlyPrice" || field.key === "hostingStorageGb" || field.key === "mailStorageGb" ? "0.01" : "1"} value={draft[field.key]} onChange={(event) => setDraft((current) => ({ ...current, [field.key]: event.target.value }))} className="mt-1.5 w-full rounded-xl border border-[#dce4df] bg-white px-3 py-2.5 text-sm font-semibold outline-none focus:border-[#2b605a] disabled:bg-[#f2f4f3]"/><span className="mt-1 block text-[9px] leading-4 text-[#8a9790]">{field.helper}</span></label>)}
          </div>

          <div className="mt-5 rounded-2xl border border-[#e0e6e2] bg-[#fafbfa] p-4">
            <div className="flex items-center gap-2"><Palette size={16} className="text-[#285b55]"/><h2 className="text-xs font-black">Creative & document deliverables</h2></div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{creativeToggles.map((item) => <label key={item.key} className="flex items-center gap-3 rounded-xl border border-[#dce4df] bg-white px-3 py-3 text-[11px] font-bold"><input type="checkbox" checked={draft[item.key]} onChange={(event) => setDraft((current) => ({ ...current, [item.key]: event.target.checked }))}/>{item.label}</label>)}</div>
            <div className="mt-4 grid gap-4 sm:grid-cols-4">
              <label><span className="text-[10px] font-black uppercase tracking-[.08em] text-[#617168]">Website pages</span><input className="input mt-1.5 w-full" type="number" min="0" max="100" value={draft.websitePages} onChange={(event) => setDraft((current) => ({ ...current, websitePages: event.target.value }))}/></label>
              <label><span className="text-[10px] font-black uppercase tracking-[.08em] text-[#617168]">Initial revisions</span><input className="input mt-1.5 w-full" type="number" min="0" max="100" value={draft.includedRevisions} onChange={(event) => setDraft((current) => ({ ...current, includedRevisions: event.target.value }))}/></label>
              <label><span className="text-[10px] font-black uppercase tracking-[.08em] text-[#617168]">Content updates / month</span><input className="input mt-1.5 w-full" type="number" min="0" max="100" value={draft.contentUpdatesPerMonth} onChange={(event) => setDraft((current) => ({ ...current, contentUpdatesPerMonth: event.target.value }))}/></label>
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-[9px] leading-4 text-amber-900"><b>Keep scope bounded.</b><br/>Revisions and monthly updates prevent “unlimited design” from being implied by a low monthly price.</div>
            </div>
          </div>

          {message ? <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{message}</div> : null}
          {error ? <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}
          <button onClick={() => void save()} disabled={saving || !draft.name || (!editing && !draft.code)} className="btn-primary mt-5 disabled:opacity-50"><CheckCircle2 size={14}/>{saving ? "Saving…" : editing ? "Save package changes" : "Create & publish package"}</button>
        </div>

        <div className="space-y-4">
          <div className="surface-card p-4 sm:p-5"><div className="flex items-start gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef4f1] text-[#285b55]"><BadgeDollarSign size={18}/></div><div><h2 className="text-sm font-black text-[var(--admin-ink)]">Monthly commercial model</h2><p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">The starter package is positioned at M185/month. When creative build work is included, use a defined minimum term and revision allowance so the recurring price remains sustainable.</p></div></div><div className="mt-4 rounded-xl border border-[#e2e6e3] p-3 text-[10px] leading-5"><b>Recommended ladder</b><br/>Start M185 · Grow M295 · Business M495 · Professional M795 · Enterprise from M1,500.</div></div>
          <div className="surface-card p-4 sm:p-5"><div className="flex items-start gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef4f1] text-[#285b55]"><Server size={18}/></div><div><h2 className="text-sm font-black text-[var(--admin-ink)]">Shared VPS protection</h2><p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">Creative services do not change runtime isolation. Every hosted project is constrained by storage, RAM, CPU and process limits and is allocated only from capacity marked as sellable.</p></div></div><div className="mt-4 space-y-3 text-[10px] leading-5 text-[#617168]"><p><b className="text-[#263a31]">Application storage</b> — separate from mailbox storage.</p><p><b className="text-[#263a31]">RAM + CPU</b> — per-project ceilings protect other customers.</p><p><b className="text-[#263a31]">No root VPS access</b> — managed hosting never exposes host SSH or Docker socket access.</p></div><a href="/hosting-docs" className="mt-5 inline-flex text-xs font-black text-[#285b55]">Read mandatory hosting rules →</a></div>
        </div>
      </section>

      <section className="surface-card p-4 sm:p-5">
        <div className="flex items-center justify-between gap-3"><div><h2 className="text-sm font-black text-[var(--admin-ink)]">Published product catalogue</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">These cards feed the public monthly pricing page. Existing subscriptions must be moved before a package can be deactivated.</p></div><button className="icon-button" onClick={() => void load()} aria-label="Refresh packages"><RefreshCw size={15}/></button></div>
        {loading ? <p className="mt-6 text-xs text-[var(--admin-muted)]">Loading packages…</p> : <div className="mt-5 grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">{plans.map((plan) => <article key={plan.id} className={`rounded-2xl border p-4 ${plan.is_active ? "border-[#dce5e0] bg-white" : "border-[#e4e5e4] bg-[#f5f6f5] opacity-75"}`}><div className="flex items-start justify-between gap-3"><div><div className="flex items-center gap-2"><Boxes size={16} className="text-[#285b55]"/><h3 className="text-sm font-black text-[#21342a]">{plan.name}</h3></div><p className="mt-1 text-[9px] font-bold uppercase tracking-[.08em] text-[#8a9790]">{plan.code} · {plan.product_category} · {plan.is_active ? "Active" : "Inactive"}</p></div><p className="text-right text-lg font-black text-[#123a38]">{formatPrice(plan)}<span className="block text-[9px] text-[#819087]">/ month</span></p></div><p className="mt-3 text-[10px] leading-5 text-[#718078]">{plan.description}</p><div className="mt-3 flex flex-wrap gap-1.5">{packageHighlights(plan).map((item) => <span key={item} className="rounded-full bg-[#edf4f1] px-2 py-1 text-[8px] font-bold text-[#285b55]">{item}</span>)}</div><div className="mt-4 grid grid-cols-2 gap-2 text-[10px]"><div className="rounded-xl bg-[#f4f7f5] p-2.5"><b>{plan.included_hosted_projects}</b><br/>projects</div><div className="rounded-xl bg-[#f4f7f5] p-2.5"><b>{(plan.hosting_storage_mb / 1024).toFixed(plan.hosting_storage_mb % 1024 ? 1 : 0)} GB</b><br/>app storage</div><div className="rounded-xl bg-[#f4f7f5] p-2.5"><b>{plan.included_domains}</b><br/>domains</div><div className="rounded-xl bg-[#f4f7f5] p-2.5"><b>{plan.included_mailboxes}</b><br/>mailboxes</div></div><div className="mt-3 text-[9px] text-[#718078]">{plan.minimum_term_months ? `${plan.minimum_term_months}-month minimum term` : "No minimum term"} · <span className="capitalize">{plan.support_level}</span> support · {plan.included_revisions} initial revisions</div><div className="mt-4 flex flex-wrap gap-2"><button className="btn-secondary" onClick={() => edit(plan)}><Pencil size={13}/>Edit</button><button className="btn-secondary" onClick={() => void toggle(plan)}><Archive size={13}/>{plan.is_active ? "Deactivate" : "Activate"}</button></div></article>)}</div>}
      </section>

      <section className="surface-card p-4 sm:p-5">
        <div className="flex items-start gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef4f1] text-[#285b55]"><Server size={18}/></div><div><h2 className="text-sm font-black text-[var(--admin-ink)]">Sellable hosting-node capacity</h2><p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">Register only the part of a VPS that may be sold. Leave deliberate headroom for Ithute, mail, DNS, databases and the operating system.</p></div></div>
        <form className="mt-5 grid gap-3 md:grid-cols-3 xl:grid-cols-6" onSubmit={(event) => { event.preventDefault(); void createNode(event.currentTarget); }}>
          <input className="input" name="node_name" placeholder="Node name" required />
          <input className="input" name="node_hostname" placeholder="server.example.com" required />
          <input className="input" name="node_ip" placeholder="Public IP (optional)" />
          <input className="input" name="node_storage_gb" type="number" min="1" step="1" placeholder="Sellable GB" required />
          <input className="input" name="node_memory_mb" type="number" min="512" step="128" placeholder="Sellable RAM MB" required />
          <div className="flex gap-2"><input className="input min-w-0" name="node_cpu_cores" type="number" min="0.5" step="0.1" placeholder="CPU cores" required /><button className="btn-primary shrink-0" type="submit"><Plus size={14}/></button></div>
        </form>
        <div className="mt-5 grid gap-3 lg:grid-cols-2">{nodes.map((node) => <article key={node.id} className="rounded-2xl border border-[#dce5e0] bg-white p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-xs font-black">{node.name}</p><p className="text-[9px] text-[var(--admin-muted)]">{node.hostname} · {node.status}</p></div><span className="rounded-full bg-emerald-50 px-2 py-1 text-[9px] font-black text-emerald-700">{node.allocated.projects} projects</span></div><div className="mt-3 grid grid-cols-3 gap-2 text-[9px]"><div className="rounded-xl bg-[#f4f7f5] p-2"><HardDrive size={13}/><b className="mt-1 block">{(node.available.storage_mb / 1024).toFixed(1)} GB</b>storage free</div><div className="rounded-xl bg-[#f4f7f5] p-2"><Server size={13}/><b className="mt-1 block">{node.available.memory_mb} MB</b>RAM free</div><div className="rounded-xl bg-[#f4f7f5] p-2"><Cpu size={13}/><b className="mt-1 block">{(node.available.cpu_millicores / 1000).toFixed(2)}</b>CPU free</div></div></article>)}{!nodes.length ? <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900"><b>No sellable hosting capacity is registered yet.</b> Packages may be published, but customer projects cannot be allocated until the system owner registers safe VPS headroom here.</div> : null}</div>
      </section>
    </div>
  </ControlShell>;
}
