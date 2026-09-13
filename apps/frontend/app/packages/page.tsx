"use client";

import { useEffect, useMemo, useState } from "react";
import { Archive, BadgeDollarSign, Boxes, CheckCircle2, Cpu, HardDrive, Pencil, Plus, RefreshCw, Server } from "lucide-react";
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
  included_hosted_projects: number;
  hosting_storage_mb: number;
  hosting_memory_mb_per_project: number;
  hosting_cpu_millicores_per_project: number;
  hosting_pids_per_project: number;
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
  };
}

function formatPrice(plan: Plan) {
  return `M ${(plan.monthly_price_minor / 100).toLocaleString()}`;
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
      setMessage(editingId ? "Package updated. Hosting, email and DNS entitlements now use the new values." : "Hosting package created and published to the pricing catalog.");
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
    setMessage("Hosting node capacity registered. New projects can now be allocated without consuming the reserved platform headroom.");
    await load();
  }

  const fields: { key: keyof Draft; label: string; helper: string; type?: string }[] = [
    { key: "name", label: "Package name", helper: "Customer-facing name, e.g. Business Hosting" },
    { key: "code", label: "Package code", helper: editing ? "Code is permanent after creation." : "Lowercase identifier, e.g. business-hosting" },
    { key: "monthlyPrice", label: "Monthly price (M)", helper: "Maloti charged per month", type: "number" },
    { key: "hostedProjects", label: "Hosted projects", helper: "Websites or simple systems this organization may host", type: "number" },
    { key: "hostingStorageGb", label: "App storage (GB)", helper: "Total application storage pool. Commercial packages are limited to 1–10 GB.", type: "number" },
    { key: "memoryMb", label: "RAM per project (MB)", helper: "Hard memory ceiling for each hosted workload", type: "number" },
    { key: "cpuMillicores", label: "CPU per project (millicores)", helper: "1000 millicores = 1 CPU core", type: "number" },
    { key: "pids", label: "Processes per project", helper: "Maximum process/PID count for each workload", type: "number" },
    { key: "domains", label: "Hosted domains", helper: "Maximum customer domains under this subscription", type: "number" },
    { key: "mailboxes", label: "Included mailboxes", helper: "Optional professional email accounts; 0 makes a hosting-only package", type: "number" },
    { key: "mailStorageGb", label: "Mail storage (GB)", helper: "Separate mailbox quota pool; it never shares the app-storage quota", type: "number" },
    { key: "apiKeys", label: "API keys", helper: "Maximum active integration credentials", type: "number" },
  ];

  return <ControlShell title="Packages & pricing" subtitle="Create complete website, system, email and DNS hosting packages">
    <div className="space-y-5">
      <PageHeader eyebrow="Ithute hosting catalog" title="Hosting package control centre" description="The system owner decides exactly what is sold: hosted projects, 1–10 GB application storage, RAM, CPU, process limits, domains, email and API capacity. These values are enforced by the control plane." />

      <section className="grid gap-4 xl:grid-cols-[1.15fr_.85fr]">
        <div className="surface-card p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><p className="text-xs font-black text-[var(--admin-ink)]">{editing ? `Edit ${editing.name}` : "Create a hosting package"}</p><p className="mt-1 text-[10px] text-[var(--admin-muted)]">A package can include application hosting, email and authoritative DNS in one subscription.</p></div>
            <button className="btn-secondary" onClick={createNew}><Plus size={14}/>New package</button>
          </div>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            {fields.map((field) => <label key={field.key} className="block"><span className="text-[10px] font-black uppercase tracking-[.08em] text-[#617168]">{field.label}</span><input disabled={field.key === "code" && Boolean(editing)} type={field.type || "text"} min={field.type === "number" ? 0 : undefined} max={field.key === "hostingStorageGb" ? 10 : undefined} step={field.key === "monthlyPrice" || field.key === "hostingStorageGb" || field.key === "mailStorageGb" ? "0.01" : "1"} value={draft[field.key]} onChange={(event) => setDraft((current) => ({ ...current, [field.key]: event.target.value }))} className="mt-1.5 w-full rounded-xl border border-[#dce4df] bg-white px-3 py-2.5 text-sm font-semibold outline-none focus:border-[#2b605a] disabled:bg-[#f2f4f3]"/><span className="mt-1 block text-[9px] leading-4 text-[#8a9790]">{field.helper}</span></label>)}
          </div>
          {message ? <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">{message}</div> : null}
          {error ? <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div> : null}
          <button onClick={() => void save()} disabled={saving || !draft.name || (!editing && !draft.code)} className="btn-primary mt-5 disabled:opacity-50"><CheckCircle2 size={14}/>{saving ? "Saving…" : editing ? "Save package changes" : "Create hosting package"}</button>
        </div>

        <div className="surface-card p-4 sm:p-5">
          <div className="flex items-start gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef4f1] text-[#285b55]"><BadgeDollarSign size={18}/></div><div><h2 className="text-sm font-black text-[var(--admin-ink)]">Shared VPS protection</h2><p className="mt-1 text-[10px] leading-5 text-[var(--admin-muted)]">Selling disk space alone is unsafe. Every hosted project is also constrained by RAM, CPU and process limits and is assigned only from capacity the system owner marks as sellable.</p></div></div>
          <div className="mt-4 space-y-3 text-[10px] leading-5 text-[#617168]"><p><b className="text-[#263a31]">Application storage</b> — a separate 1–10 GB pool; websites cannot consume mailbox storage.</p><p><b className="text-[#263a31]">RAM + CPU</b> — per-project ceilings so one customer cannot starve the VPS.</p><p><b className="text-[#263a31]">Processes</b> — limits fork/process storms inside a workload.</p><p><b className="text-[#263a31]">No root VPS access</b> — customers receive managed app hosting, never SSH or the Docker socket of the shared server.</p></div>
          <a href="/docs#hosting" className="mt-5 inline-flex text-xs font-black text-[#285b55]">Read mandatory hosting rules →</a>
        </div>
      </section>

      <section className="surface-card p-4 sm:p-5">
        <div className="flex items-center justify-between gap-3"><div><h2 className="text-sm font-black text-[var(--admin-ink)]">Published package catalog</h2><p className="mt-1 text-[10px] text-[var(--admin-muted)]">Inactive packages disappear from new signups. Existing subscriptions must be moved before a package can be deactivated.</p></div><button className="icon-button" onClick={() => void load()} aria-label="Refresh packages"><RefreshCw size={15}/></button></div>
        {loading ? <p className="mt-6 text-xs text-[var(--admin-muted)]">Loading packages…</p> : <div className="mt-5 grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">{plans.map((plan) => <article key={plan.id} className={`rounded-2xl border p-4 ${plan.is_active ? "border-[#dce5e0] bg-white" : "border-[#e4e5e4] bg-[#f5f6f5] opacity-75"}`}><div className="flex items-start justify-between gap-3"><div><div className="flex items-center gap-2"><Boxes size={16} className="text-[#285b55]"/><h3 className="text-sm font-black text-[#21342a]">{plan.name}</h3></div><p className="mt-1 text-[9px] font-bold uppercase tracking-[.08em] text-[#8a9790]">{plan.code} · {plan.is_active ? "Active" : "Inactive"}</p></div><p className="text-lg font-black text-[#123a38]">{formatPrice(plan)}<span className="text-[9px] text-[#819087]">/mo</span></p></div><div className="mt-4 grid grid-cols-2 gap-2 text-[10px]"><div className="rounded-xl bg-[#f4f7f5] p-2.5"><b>{plan.included_hosted_projects}</b><br/>projects</div><div className="rounded-xl bg-[#f4f7f5] p-2.5"><b>{(plan.hosting_storage_mb / 1024).toFixed(plan.hosting_storage_mb % 1024 ? 1 : 0)} GB</b><br/>app storage</div><div className="rounded-xl bg-[#f4f7f5] p-2.5"><b>{plan.hosting_memory_mb_per_project} MB</b><br/>RAM / project</div><div className="rounded-xl bg-[#f4f7f5] p-2.5"><b>{(plan.hosting_cpu_millicores_per_project / 1000).toFixed(2)} CPU</b><br/>per project</div><div className="rounded-xl bg-[#f4f7f5] p-2.5"><b>{plan.included_domains}</b><br/>domains</div><div className="rounded-xl bg-[#f4f7f5] p-2.5"><b>{plan.included_mailboxes}</b><br/>mailboxes</div></div><div className="mt-4 flex flex-wrap gap-2"><button className="btn-secondary" onClick={() => edit(plan)}><Pencil size={13}/>Edit</button><button className="btn-secondary" onClick={() => void toggle(plan)}><Archive size={13}/>{plan.is_active ? "Deactivate" : "Activate"}</button></div></article>)}</div>}
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
