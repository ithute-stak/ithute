"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8004/api/v1";

type Row = Record<string, unknown>;
type Summary = { company: Row; counts: Record<string, number>; phase: number; phase_status: string };
type Tab = "overview" | "company" | "branches" | "sites" | "departments" | "cost-centres" | "access" | "approvals" | "documents" | "master-data" | "settings" | "audit";

const tabs: Array<[Tab, string, string]> = [
  ["overview", "Command centre", "01"],
  ["company", "Company profile", "02"],
  ["branches", "Branches", "03"],
  ["sites", "Sites", "04"],
  ["departments", "Departments", "05"],
  ["cost-centres", "Cost centres", "06"],
  ["access", "Roles & permissions", "07"],
  ["approvals", "Approvals", "08"],
  ["documents", "Document control", "09"],
  ["master-data", "Master data", "10"],
  ["settings", "Settings & numbering", "11"],
  ["audit", "Audit trail", "12"],
];

function text(row: Row | null | undefined, key: string): string {
  return String(row?.[key] ?? "");
}

function number(row: Row | null | undefined, key: string): number {
  return Number(row?.[key] ?? 0);
}

function rows(value: unknown): Row[] {
  return Array.isArray(value) ? (value as Row[]) : [];
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = typeof payload?.detail === "string" ? payload.detail : JSON.stringify(payload?.detail ?? payload);
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function Button({ children, tone = "primary", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "primary" | "secondary" | "danger" }) {
  return <button {...props} className={`btn btn-${tone} ${props.className ?? ""}`}>{children}</button>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "green" | "amber" | "red" | "blue" }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}

function SetupWizard({ onComplete }: { onComplete: () => void }) {
  const [form, setForm] = useState({ name: "Nthane Brothers", legal_name: "Nthane Brothers", code: "NTHANE", head_office_name: "Head Office", head_office_code: "HO", head_office_district: "Maseru", phone: "", email: "", physical_address: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      await api("/foundation/bootstrap", { method: "POST", body: JSON.stringify(form) });
      onComplete();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not initialise BuildTrack");
    } finally { setBusy(false); }
  }

  return (
    <main className="setup-screen">
      <section className="setup-card">
        <div className="setup-brand"><span>BT</span><div><strong>BuildTrack</strong><small>Construction Operations</small></div></div>
        <Badge tone="blue">Phase 1 · Core Platform</Badge>
        <h1>Establish the company control structure.</h1>
        <p>This is a one-time setup. BuildTrack will create the head office, Lesotho defaults, departments, roles, permissions, approval controls, numbering sequences, master data and document governance.</p>
        {error && <div className="alert alert-error">{error}</div>}
        <form onSubmit={submit} className="form-grid">
          <Field label="Company name"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></Field>
          <Field label="Legal name"><input value={form.legal_name} onChange={(e) => setForm({ ...form, legal_name: e.target.value })} /></Field>
          <Field label="Company code"><input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} required /></Field>
          <Field label="Head office name"><input value={form.head_office_name} onChange={(e) => setForm({ ...form, head_office_name: e.target.value })} required /></Field>
          <Field label="Head office code"><input value={form.head_office_code} onChange={(e) => setForm({ ...form, head_office_code: e.target.value.toUpperCase() })} required /></Field>
          <Field label="District"><input value={form.head_office_district} onChange={(e) => setForm({ ...form, head_office_district: e.target.value })} /></Field>
          <Field label="Phone"><input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
          <Field label="Email"><input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          <Field label="Physical address"><textarea value={form.physical_address} onChange={(e) => setForm({ ...form, physical_address: e.target.value })} /></Field>
          <div className="form-actions"><Button disabled={busy}>{busy ? "Building Phase 1…" : "Create BuildTrack foundation"}</Button></div>
        </form>
      </section>
    </main>
  );
}

export default function Home() {
  const [bootstrapped, setBootstrapped] = useState<boolean | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [active, setActive] = useState<Tab>("overview");
  const [branches, setBranches] = useState<Row[]>([]);
  const [sites, setSites] = useState<Row[]>([]);
  const [departments, setDepartments] = useState<Row[]>([]);
  const [costCentres, setCostCentres] = useState<Row[]>([]);
  const [roles, setRoles] = useState<Row[]>([]);
  const [permissions, setPermissions] = useState<Row[]>([]);
  const [workflows, setWorkflows] = useState<Row[]>([]);
  const [approvalRequests, setApprovalRequests] = useState<Row[]>([]);
  const [documents, setDocuments] = useState<Row[]>([]);
  const [masterData, setMasterData] = useState<Row[]>([]);
  const [settings, setSettings] = useState<Row[]>([]);
  const [sequences, setSequences] = useState<Row[]>([]);
  const [auditLog, setAuditLog] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const currentSummary = await api<Summary>("/foundation/summary");
      setBootstrapped(true); setSummary(currentSummary);
      const [branchRows, siteRows, departmentRows, costRows, roleRows, permissionRows, workflowRows, requestRows, documentRows, masterRows, settingRows, sequenceRows, auditRows] = await Promise.all([
        api<Row[]>("/foundation/branches"), api<Row[]>("/foundation/sites"), api<Row[]>("/foundation/departments"), api<Row[]>("/foundation/cost-centres"),
        api<Row[]>("/foundation/roles"), api<Row[]>("/foundation/permissions"), api<Row[]>("/foundation/approval-workflows"), api<Row[]>("/foundation/approval-requests"),
        api<Row[]>("/foundation/documents"), api<Row[]>("/foundation/master-data/categories"), api<Row[]>("/foundation/settings"), api<Row[]>("/foundation/number-sequences"), api<Row[]>("/foundation/audit?limit=250"),
      ]);
      setBranches(branchRows); setSites(siteRows); setDepartments(departmentRows); setCostCentres(costRows); setRoles(roleRows); setPermissions(permissionRows); setWorkflows(workflowRows); setApprovalRequests(requestRows); setDocuments(documentRows); setMasterData(masterRows); setSettings(settingRows); setSequences(sequenceRows); setAuditLog(auditRows);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not load BuildTrack";
      if (message.includes("not been bootstrapped")) setBootstrapped(false); else setError(message);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  function success(message: string) {
    setNotice(message); setError("");
    window.setTimeout(() => setNotice(""), 3500);
    void refresh();
  }

  if (bootstrapped === false) return <SetupWizard onComplete={refresh} />;
  if (bootstrapped === null || (loading && !summary)) return <main className="loading-screen"><div className="spinner" /><strong>Loading BuildTrack Phase 1…</strong></main>;

  const company = summary?.company ?? {};

  return (
    <div className="foundation-shell">
      <nav className="foundation-tabs" aria-label="Foundation workspace sections">{tabs.map(([id, label, code]) => <button key={id} onClick={() => setActive(id)} className={active === id ? "active" : ""}><span>{code}</span>{label}</button>)}</nav>

      <main className="workspace">
        <header className="topbar">
          <div><p className="eyebrow">Nthane Brothers · Head office + branches</p><h1>{tabs.find(([id]) => id === active)?.[1]}</h1></div>
          <div className="top-actions"><Badge tone="green">Phase 1 operational</Badge><Button tone="secondary" onClick={() => void refresh()} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</Button></div>
        </header>
        {error && <div className="alert alert-error">{error}</div>}
        {notice && <div className="alert alert-success">{notice}</div>}

        {active === "overview" && <Overview summary={summary} branches={branches} sites={sites} workflows={workflows} requests={approvalRequests} />}
        {active === "company" && <CompanyPanel company={company} onSaved={success} setError={setError} />}
        {active === "branches" && <BranchesPanel data={branches} onSaved={success} setError={setError} />}
        {active === "sites" && <SitesPanel data={sites} branches={branches} onSaved={success} setError={setError} />}
        {active === "departments" && <DepartmentsPanel data={departments} branches={branches} onSaved={success} setError={setError} />}
        {active === "cost-centres" && <CostCentresPanel data={costCentres} branches={branches} sites={sites} departments={departments} onSaved={success} setError={setError} />}
        {active === "access" && <AccessPanel roles={roles} permissions={permissions} onSaved={success} setError={setError} />}
        {active === "approvals" && <ApprovalsPanel workflows={workflows} roles={roles} branches={branches} sites={sites} requests={approvalRequests} onSaved={success} setError={setError} />}
        {active === "documents" && <DocumentsPanel data={documents} branches={branches} sites={sites} onSaved={success} setError={setError} />}
        {active === "master-data" && <MasterDataPanel data={masterData} onSaved={success} setError={setError} />}
        {active === "settings" && <SettingsPanel settings={settings} sequences={sequences} onSaved={success} setError={setError} />}
        {active === "audit" && <AuditPanel data={auditLog} branches={branches} sites={sites} />}
      </main>
    </div>
  );
}

function Overview({ summary, branches, sites, workflows, requests }: { summary: Summary | null; branches: Row[]; sites: Row[]; workflows: Row[]; requests: Row[] }) {
  const counts = summary?.counts ?? {};
  const cards = [
    ["Branches", counts.branches ?? 0, "All operational branches under one company"], ["Sites", counts.sites ?? 0, "Branch-owned operational and project locations"],
    ["Departments", counts.departments ?? 0, "Company or branch organisational units"], ["Cost centres", counts.cost_centres ?? 0, "Financial ownership backbone"],
    ["Roles", counts.roles ?? 0, "Scope-aware access-control foundation"], ["Pending approvals", counts.pending_approvals ?? 0, "Controlled decisions waiting for action"],
    ["Documents", counts.documents ?? 0, "Version-controlled records"], ["Number sequences", counts.number_sequences ?? 0, "Shared references for future modules"],
  ];
  return <div className="stack">
    <section className="hero-panel"><div><Badge tone="green">Phase 1 · 100% scope</Badge><h2>Company control plane established.</h2><p>Every later BuildTrack module inherits one organisational structure: company, branch, site, department and cost centre—with approvals, audit history, numbering and document governance already available.</p></div><div className="hero-stat"><small>Currency</small><strong>M</strong><span>LSL · Africa/Maseru</span></div></section>
    <section className="metric-grid">{cards.map(([label, value, detail]) => <article className="metric" key={String(label)}><small>{label}</small><strong>{value}</strong><p>{detail}</p></article>)}</section>
    <section className="two-col"><div className="panel"><div className="panel-head"><div><h3>Organisation footprint</h3><p>Head office and branch/site ownership.</p></div></div><div className="mini-list">{branches.map((branch) => <div key={number(branch, "id")}><span className="avatar">{text(branch, "code").slice(0, 2)}</span><div><strong>{text(branch, "name")}</strong><small>{text(branch, "district") || "District not set"} · {sites.filter((site) => number(site, "branch_id") === number(branch, "id")).length} site(s)</small></div><Badge tone={Boolean(branch.is_active) ? "green" : "neutral"}>{text(branch, "branch_type").replaceAll("_", " ")}</Badge></div>)}</div></div>
      <div className="panel"><div className="panel-head"><div><h3>Approval governance</h3><p>Reusable workflows for future phases.</p></div></div><div className="mini-list">{workflows.map((workflow) => <div key={number(workflow, "id")}><span className="avatar approval">{rows(workflow.steps).length}</span><div><strong>{text(workflow, "name")}</strong><small>{text(workflow, "module")} · {rows(workflow.steps).length} step(s)</small></div></div>)}{!workflows.length && <Empty>No approval workflows yet.</Empty>}</div><div className="panel-foot">{requests.filter((request) => text(request, "status") === "pending").length} pending request(s)</div></div>
    </section>
  </div>;
}

function CompanyPanel({ company, onSaved, setError }: { company: Row; onSaved: (m: string) => void; setError: (m: string) => void }) {
  const [form, setForm] = useState(() => ({ name: text(company, "name"), legal_name: text(company, "legal_name"), registration_number: text(company, "registration_number"), tax_number: text(company, "tax_number"), phone: text(company, "phone"), email: text(company, "email"), physical_address: text(company, "physical_address"), postal_address: text(company, "postal_address"), fiscal_year_start_month: number(company, "fiscal_year_start_month") || 4 }));
  async function submit(e: FormEvent) { e.preventDefault(); try { await api("/foundation/company", { method: "PATCH", body: JSON.stringify(form) }); onSaved("Company profile updated"); } catch (err) { setError(err instanceof Error ? err.message : "Update failed"); } }
  return <section className="panel"><div className="panel-head"><div><h3>Company profile</h3><p>One legal company. Branches and sites sit below this record.</p></div><div><Badge tone="blue">{text(company, "code")}</Badge></div></div><form className="form-grid" onSubmit={submit}>
    <Field label="Trading name"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></Field><Field label="Legal name"><input value={form.legal_name} onChange={(e) => setForm({ ...form, legal_name: e.target.value })} /></Field><Field label="Registration number"><input value={form.registration_number} onChange={(e) => setForm({ ...form, registration_number: e.target.value })} /></Field><Field label="Tax number"><input value={form.tax_number} onChange={(e) => setForm({ ...form, tax_number: e.target.value })} /></Field><Field label="Phone"><input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field><Field label="Email"><input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field><Field label="Physical address"><textarea value={form.physical_address} onChange={(e) => setForm({ ...form, physical_address: e.target.value })} /></Field><Field label="Postal address"><textarea value={form.postal_address} onChange={(e) => setForm({ ...form, postal_address: e.target.value })} /></Field><Field label="Fiscal year starts"><select value={form.fiscal_year_start_month} onChange={(e) => setForm({ ...form, fiscal_year_start_month: Number(e.target.value) })}>{[1,2,3,4,5,6,7,8,9,10,11,12].map((m) => <option key={m} value={m}>{new Date(2026, m - 1, 1).toLocaleString("en", { month: "long" })}</option>)}</select></Field>
    <div className="locked-field"><span>Localisation locked for first rollout</span><strong>Lesotho · LSL · M · Africa/Maseru</strong></div><div className="form-actions"><Button>Save company profile</Button></div></form></section>;
}

function BranchesPanel({ data, onSaved, setError }: { data: Row[]; onSaved: (m: string) => void; setError: (m: string) => void }) {
  const blank = { code: "", name: "", branch_type: "branch", district: "", address: "", phone: "", email: "", manager_name: "", manager_email: "", manager_phone: "", is_active: true };
  const [form, setForm] = useState(blank); const [editing, setEditing] = useState<number | null>(null);
  function edit(row: Row) { setEditing(number(row, "id")); setForm({ code: text(row, "code"), name: text(row, "name"), branch_type: text(row, "branch_type") || "branch", district: text(row, "district"), address: text(row, "address"), phone: text(row, "phone"), email: text(row, "email"), manager_name: text(row, "manager_name"), manager_email: text(row, "manager_email"), manager_phone: text(row, "manager_phone"), is_active: Boolean(row.is_active) }); }
  async function submit(e: FormEvent) { e.preventDefault(); try { await api(`/foundation/branches${editing ? `/${editing}` : ""}`, { method: editing ? "PUT" : "POST", body: JSON.stringify(form) }); setForm(blank); setEditing(null); onSaved(editing ? "Branch updated" : "Branch created"); } catch (err) { setError(err instanceof Error ? err.message : "Could not save branch"); } }
  return <CrudLayout title="Branch register" detail="Head office and every branch remain inside the same Nthane Brothers company record." form={<form className="compact-form" onSubmit={submit}><Field label="Code"><input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} required /></Field><Field label="Branch name"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></Field><Field label="Type"><select value={form.branch_type} onChange={(e) => setForm({ ...form, branch_type: e.target.value })}><option value="branch">Branch</option><option value="regional_office">Regional office</option><option value="yard">Yard</option><option value="workshop">Workshop</option><option value="head_office">Head office</option></select></Field><Field label="District"><input value={form.district} onChange={(e) => setForm({ ...form, district: e.target.value })} /></Field><Field label="Manager"><input value={form.manager_name} onChange={(e) => setForm({ ...form, manager_name: e.target.value })} /></Field><Field label="Manager phone"><input value={form.manager_phone} onChange={(e) => setForm({ ...form, manager_phone: e.target.value })} /></Field><Field label="Phone"><input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field><Field label="Email"><input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field><Field label="Address"><textarea value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></Field><label className="check"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />Active</label><div className="form-actions"><Button>{editing ? "Update branch" : "Add branch"}</Button>{editing && <Button type="button" tone="secondary" onClick={() => { setEditing(null); setForm(blank); }}>Cancel</Button>}</div></form>}>
    <DataTable columns={["Code", "Branch", "District", "Manager", "Type", "Status", ""]} rows={data.map((row) => [text(row,"code"), text(row,"name"), text(row,"district") || "—", text(row,"manager_name") || "—", text(row,"branch_type").replaceAll("_"," "), Boolean(row.is_active) ? <Badge tone="green">Active</Badge> : <Badge>Inactive</Badge>, <button className="link-btn" onClick={() => edit(row)} key={`e-${number(row,"id")}`}>Edit</button>])} />
  </CrudLayout>;
}

function SitesPanel({ data, branches, onSaved, setError }: { data: Row[]; branches: Row[]; onSaved: (m: string) => void; setError: (m: string) => void }) {
  const blank = { branch_id: "", code: "", name: "", site_type: "project_site", district: "", location: "", responsible_officer: "", responsible_phone: "", is_active: true };
  const [form, setForm] = useState(blank); const [editing, setEditing] = useState<number | null>(null);
  function edit(row: Row) { setEditing(number(row,"id")); setForm({ branch_id: text(row,"branch_id"), code: text(row,"code"), name: text(row,"name"), site_type: text(row,"site_type"), district: text(row,"district"), location: text(row,"location"), responsible_officer: text(row,"responsible_officer"), responsible_phone: text(row,"responsible_phone"), is_active: Boolean(row.is_active) }); }
  async function submit(e: FormEvent) { e.preventDefault(); try { const body = { ...form, branch_id: Number(form.branch_id) }; await api(`/foundation/sites${editing ? `/${editing}` : ""}`, { method: editing ? "PUT" : "POST", body: JSON.stringify(body) }); setEditing(null); setForm(blank); onSaved(editing ? "Site updated" : "Site created"); } catch (err) { setError(err instanceof Error ? err.message : "Could not save site"); } }
  return <CrudLayout title="Site register" detail="Sites always belong to a branch, enabling project/site ownership in later phases." form={<form className="compact-form" onSubmit={submit}><Field label="Branch"><select value={form.branch_id} onChange={(e) => setForm({ ...form, branch_id: e.target.value })} required><option value="">Select branch</option>{branches.map((b) => <option key={number(b,"id")} value={number(b,"id")}>{text(b,"code")} · {text(b,"name")}</option>)}</select></Field><Field label="Site code"><input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} required /></Field><Field label="Site name"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></Field><Field label="Site type"><select value={form.site_type} onChange={(e) => setForm({ ...form, site_type: e.target.value })}><option value="project_site">Project site</option><option value="workshop">Workshop</option><option value="yard">Yard</option><option value="office">Office</option><option value="store">Store</option></select></Field><Field label="District"><input value={form.district} onChange={(e) => setForm({ ...form, district: e.target.value })} /></Field><Field label="Responsible officer"><input value={form.responsible_officer} onChange={(e) => setForm({ ...form, responsible_officer: e.target.value })} /></Field><Field label="Phone"><input value={form.responsible_phone} onChange={(e) => setForm({ ...form, responsible_phone: e.target.value })} /></Field><Field label="Location"><textarea value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></Field><label className="check"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />Active</label><div className="form-actions"><Button>{editing ? "Update site" : "Add site"}</Button>{editing && <Button type="button" tone="secondary" onClick={() => { setEditing(null); setForm(blank); }}>Cancel</Button>}</div></form>}>
    <DataTable columns={["Code", "Site", "Branch", "District", "Responsible", "Status", ""]} rows={data.map((row) => [text(row,"code"), text(row,"name"), text(branches.find((b) => number(b,"id") === number(row,"branch_id")),"name"), text(row,"district") || "—", text(row,"responsible_officer") || "—", Boolean(row.is_active) ? <Badge tone="green">Active</Badge> : <Badge>Inactive</Badge>, <button className="link-btn" onClick={() => edit(row)} key={`e-${number(row,"id")}`}>Edit</button>])} />
  </CrudLayout>;
}

function DepartmentsPanel({ data, branches, onSaved, setError }: { data: Row[]; branches: Row[]; onSaved: (m: string) => void; setError: (m: string) => void }) {
  const blank = { branch_id: "", code: "", name: "", description: "", manager_name: "", is_active: true }; const [form,setForm] = useState(blank); const [editing,setEditing] = useState<number|null>(null);
  function edit(row: Row) { setEditing(number(row,"id")); setForm({ branch_id: text(row,"branch_id"), code: text(row,"code"), name: text(row,"name"), description: text(row,"description"), manager_name: text(row,"manager_name"), is_active: Boolean(row.is_active) }); }
  async function submit(e: FormEvent) { e.preventDefault(); try { await api(`/foundation/departments${editing ? `/${editing}` : ""}`, { method: editing ? "PUT" : "POST", body: JSON.stringify({ ...form, branch_id: form.branch_id ? Number(form.branch_id) : null }) }); setForm(blank); setEditing(null); onSaved(editing ? "Department updated" : "Department created"); } catch(err){ setError(err instanceof Error ? err.message : "Could not save department"); } }
  return <CrudLayout title="Department structure" detail="Company-wide departments can be shared by branches; branch-specific departments are also supported." form={<form className="compact-form" onSubmit={submit}><Field label="Scope"><select value={form.branch_id} onChange={(e)=>setForm({...form,branch_id:e.target.value})}><option value="">Company-wide</option>{branches.map((b)=><option key={number(b,"id")} value={number(b,"id")}>{text(b,"name")}</option>)}</select></Field><Field label="Code"><input value={form.code} onChange={(e)=>setForm({...form,code:e.target.value.toUpperCase()})} required /></Field><Field label="Name"><input value={form.name} onChange={(e)=>setForm({...form,name:e.target.value})} required /></Field><Field label="Manager"><input value={form.manager_name} onChange={(e)=>setForm({...form,manager_name:e.target.value})} /></Field><Field label="Description"><textarea value={form.description} onChange={(e)=>setForm({...form,description:e.target.value})} /></Field><label className="check"><input type="checkbox" checked={form.is_active} onChange={(e)=>setForm({...form,is_active:e.target.checked})}/>Active</label><div className="form-actions"><Button>{editing?"Update department":"Add department"}</Button>{editing&&<Button type="button" tone="secondary" onClick={()=>{setEditing(null);setForm(blank)}}>Cancel</Button>}</div></form>}><DataTable columns={["Code","Department","Scope","Manager","Status",""]} rows={data.map((row)=>[text(row,"code"),text(row,"name"),text(branches.find((b)=>number(b,"id")===number(row,"branch_id")),"name")||"Company-wide",text(row,"manager_name")||"—",Boolean(row.is_active)?<Badge tone="green">Active</Badge>:<Badge>Inactive</Badge>,<button className="link-btn" onClick={()=>edit(row)} key={number(row,"id")}>Edit</button>])}/></CrudLayout>;
}

function CostCentresPanel({ data, branches, sites, departments, onSaved, setError }: { data:Row[]; branches:Row[]; sites:Row[]; departments:Row[]; onSaved:(m:string)=>void; setError:(m:string)=>void }) {
  const blank={branch_id:"",site_id:"",department_id:"",code:"",name:"",cost_centre_type:"operational",description:"",is_active:true}; const [form,setForm]=useState(blank); const [editing,setEditing]=useState<number|null>(null);
  function edit(row:Row){setEditing(number(row,"id"));setForm({branch_id:text(row,"branch_id"),site_id:text(row,"site_id"),department_id:text(row,"department_id"),code:text(row,"code"),name:text(row,"name"),cost_centre_type:text(row,"cost_centre_type"),description:text(row,"description"),is_active:Boolean(row.is_active)})}
  async function submit(e:FormEvent){e.preventDefault();try{await api(`/foundation/cost-centres${editing?`/${editing}`:""}`,{method:editing?"PUT":"POST",body:JSON.stringify({...form,branch_id:form.branch_id?Number(form.branch_id):null,site_id:form.site_id?Number(form.site_id):null,department_id:form.department_id?Number(form.department_id):null})});setForm(blank);setEditing(null);onSaved(editing?"Cost centre updated":"Cost centre created")}catch(err){setError(err instanceof Error?err.message:"Could not save cost centre")}}
  const availableSites=form.branch_id?sites.filter((s)=>number(s,"branch_id")===Number(form.branch_id)):sites;
  return <CrudLayout title="Cost centre register" detail="Common financial ownership dimension for payroll, fleet, procurement, projects and commercial control." form={<form className="compact-form" onSubmit={submit}><Field label="Code"><input value={form.code} onChange={(e)=>setForm({...form,code:e.target.value.toUpperCase()})} required/></Field><Field label="Name"><input value={form.name} onChange={(e)=>setForm({...form,name:e.target.value})} required/></Field><Field label="Type"><select value={form.cost_centre_type} onChange={(e)=>setForm({...form,cost_centre_type:e.target.value})}><option value="operational">Operational</option><option value="project">Project</option><option value="overhead">Overhead</option><option value="fleet">Fleet</option><option value="department">Department</option></select></Field><Field label="Branch"><select value={form.branch_id} onChange={(e)=>setForm({...form,branch_id:e.target.value,site_id:""})}><option value="">Company-wide</option>{branches.map((b)=><option key={number(b,"id")} value={number(b,"id")}>{text(b,"name")}</option>)}</select></Field><Field label="Site"><select value={form.site_id} onChange={(e)=>setForm({...form,site_id:e.target.value})}><option value="">No site</option>{availableSites.map((s)=><option key={number(s,"id")} value={number(s,"id")}>{text(s,"name")}</option>)}</select></Field><Field label="Department"><select value={form.department_id} onChange={(e)=>setForm({...form,department_id:e.target.value})}><option value="">No department</option>{departments.map((d)=><option key={number(d,"id")} value={number(d,"id")}>{text(d,"name")}</option>)}</select></Field><Field label="Description"><textarea value={form.description} onChange={(e)=>setForm({...form,description:e.target.value})}/></Field><label className="check"><input type="checkbox" checked={form.is_active} onChange={(e)=>setForm({...form,is_active:e.target.checked})}/>Active</label><div className="form-actions"><Button>{editing?"Update cost centre":"Add cost centre"}</Button>{editing&&<Button type="button" tone="secondary" onClick={()=>{setEditing(null);setForm(blank)}}>Cancel</Button>}</div></form>}><DataTable columns={["Code","Name","Type","Branch","Site","Status",""]} rows={data.map((row)=>[text(row,"code"),text(row,"name"),text(row,"cost_centre_type"),text(branches.find((b)=>number(b,"id")===number(row,"branch_id")),"name")||"Company",text(sites.find((s)=>number(s,"id")===number(row,"site_id")),"name")||"—",Boolean(row.is_active)?<Badge tone="green">Active</Badge>:<Badge>Inactive</Badge>,<button className="link-btn" onClick={()=>edit(row)} key={number(row,"id")}>Edit</button>])}/></CrudLayout>;
}

function AccessPanel({ roles, permissions, onSaved, setError }: { roles:Row[]; permissions:Row[]; onSaved:(m:string)=>void; setError:(m:string)=>void }) {
  const blank={code:"",name:"",description:"",scope_level:"branch",permission_ids:[] as number[],is_active:true};const[form,setForm]=useState(blank);const[editing,setEditing]=useState<number|null>(null);
  const grouped=useMemo(()=>Array.from(new Set(permissions.map((p)=>text(p,"module")))),[permissions]);
  function edit(role:Row){setEditing(number(role,"id"));setForm({code:text(role,"code"),name:text(role,"name"),description:text(role,"description"),scope_level:text(role,"scope_level"),permission_ids:rows(role.permission_ids).map(()=>0).filter(Boolean) as number[],is_active:Boolean(role.is_active)});const raw=role.permission_ids;setForm((prev)=>({...prev,permission_ids:Array.isArray(raw)?raw.map(Number):[]}))}
  async function submit(e:FormEvent){e.preventDefault();try{await api(`/foundation/roles${editing?`/${editing}`:""}`,{method:editing?"PUT":"POST",body:JSON.stringify(form)});setForm(blank);setEditing(null);onSaved(editing?"Role permissions updated":"Role created")}catch(err){setError(err instanceof Error?err.message:"Could not save role")}}
  function toggle(id:number){setForm({...form,permission_ids:form.permission_ids.includes(id)?form.permission_ids.filter((value)=>value!==id):[...form.permission_ids,id]})}
  return <div className="stack"><section className="panel"><div className="panel-head"><div><h3>Role & permission foundation</h3><p>Authentication and user assignment arrive in Phase 2; the access model and branch/site scopes are established here.</p></div><Badge tone="blue">{permissions.length} permissions</Badge></div><form onSubmit={submit} className="form-grid"><Field label="Role code"><input value={form.code} disabled={Boolean(editing&&roles.find((r)=>number(r,"id")===editing)?.is_system)} onChange={(e)=>setForm({...form,code:e.target.value.toUpperCase()})} required/></Field><Field label="Role name"><input value={form.name} onChange={(e)=>setForm({...form,name:e.target.value})} required/></Field><Field label="Scope"><select value={form.scope_level} onChange={(e)=>setForm({...form,scope_level:e.target.value})}><option value="company">Company</option><option value="branch">Branch</option><option value="site">Site</option></select></Field><Field label="Description"><textarea value={form.description} onChange={(e)=>setForm({...form,description:e.target.value})}/></Field><div className="permissions-box">{grouped.map((module)=><div key={module}><strong>{module.replaceAll("_"," ")}</strong><div>{permissions.filter((p)=>text(p,"module")===module).map((permission)=><label key={number(permission,"id")}><input type="checkbox" checked={form.permission_ids.includes(number(permission,"id"))} onChange={()=>toggle(number(permission,"id"))}/>{text(permission,"action")}</label>)}</div></div>)}</div><div className="form-actions"><Button>{editing?"Save role permissions":"Create role"}</Button>{editing&&<Button type="button" tone="secondary" onClick={()=>{setEditing(null);setForm(blank)}}>Cancel</Button>}</div></form></section><section className="panel"><DataTable columns={["Code","Role","Scope","Permissions","Type",""]} rows={roles.map((role)=>[text(role,"code"),text(role,"name"),text(role,"scope_level"),Array.isArray(role.permission_ids)?role.permission_ids.length:0,Boolean(role.is_system)?<Badge tone="blue">System</Badge>:<Badge>Custom</Badge>,<button className="link-btn" onClick={()=>edit(role)} key={number(role,"id")}>Edit</button>])}/></section></div>;
}

function ApprovalsPanel({ workflows, roles, branches, sites, requests, onSaved, setError }: { workflows:Row[];roles:Row[];branches:Row[];sites:Row[];requests:Row[];onSaved:(m:string)=>void;setError:(m:string)=>void }) {
  const [wf,setWf]=useState({code:"",name:"",module:"procurement",branch_id:"",description:"",min_amount:"0",max_amount:""});const[step,setStep]=useState({workflow_id:"",step_order:"1",name:"",role_id:"",required_approvals:"1",escalation_hours:"24"});const[request,setRequest]=useState({workflow_id:"",branch_id:"",site_id:"",entity_type:"phase1_test",entity_id:"",title:"",amount:"",requested_by:"Phase 1 Admin"});const[action,setAction]=useState({request_id:"",role_id:"",actor_name:"Phase 1 Admin",action:"approve",comment:""});
  async function save(path:string,body:Record<string,unknown>,message:string){try{await api(path,{method:"POST",body:JSON.stringify(body)});onSaved(message)}catch(err){setError(err instanceof Error?err.message:"Approval operation failed")}}
  return <div className="stack"><section className="panel"><div className="panel-head"><div><h3>Approval workflow designer</h3><p>Reusable sequential approval routing with role authority, thresholds, escalation targets and immutable action history.</p></div></div><div className="three-col-forms"><form onSubmit={(e)=>{e.preventDefault();void save("/foundation/approval-workflows",{...wf,branch_id:wf.branch_id?Number(wf.branch_id):null,min_amount:wf.min_amount?wf.min_amount:null,max_amount:wf.max_amount?wf.max_amount:null},"Workflow created")}}><h4>New workflow</h4><Field label="Code"><input value={wf.code} onChange={(e)=>setWf({...wf,code:e.target.value.toUpperCase()})} required/></Field><Field label="Name"><input value={wf.name} onChange={(e)=>setWf({...wf,name:e.target.value})} required/></Field><Field label="Module"><input value={wf.module} onChange={(e)=>setWf({...wf,module:e.target.value})} required/></Field><Field label="Branch scope"><select value={wf.branch_id} onChange={(e)=>setWf({...wf,branch_id:e.target.value})}><option value="">Company-wide</option>{branches.map((b)=><option key={number(b,"id")} value={number(b,"id")}>{text(b,"name")}</option>)}</select></Field><div className="inline-fields"><Field label="Min M"><input type="number" value={wf.min_amount} onChange={(e)=>setWf({...wf,min_amount:e.target.value})}/></Field><Field label="Max M"><input type="number" value={wf.max_amount} onChange={(e)=>setWf({...wf,max_amount:e.target.value})}/></Field></div><Button>Create workflow</Button></form>
  <form onSubmit={(e)=>{e.preventDefault();void save(`/foundation/approval-workflows/${step.workflow_id}/steps`,{step_order:Number(step.step_order),name:step.name,role_id:Number(step.role_id),required_approvals:Number(step.required_approvals),escalation_hours:step.escalation_hours?Number(step.escalation_hours):null},"Approval step added")}}><h4>Add workflow step</h4><Field label="Workflow"><select value={step.workflow_id} onChange={(e)=>setStep({...step,workflow_id:e.target.value})} required><option value="">Select</option>{workflows.map((w)=><option key={number(w,"id")} value={number(w,"id")}>{text(w,"name")}</option>)}</select></Field><Field label="Step name"><input value={step.name} onChange={(e)=>setStep({...step,name:e.target.value})} required/></Field><Field label="Role"><select value={step.role_id} onChange={(e)=>setStep({...step,role_id:e.target.value})} required><option value="">Select role</option>{roles.map((r)=><option key={number(r,"id")} value={number(r,"id")}>{text(r,"name")}</option>)}</select></Field><div className="inline-fields"><Field label="Order"><input type="number" min="1" value={step.step_order} onChange={(e)=>setStep({...step,step_order:e.target.value})}/></Field><Field label="Approvals"><input type="number" min="1" value={step.required_approvals} onChange={(e)=>setStep({...step,required_approvals:e.target.value})}/></Field></div><Field label="Escalation hours"><input type="number" value={step.escalation_hours} onChange={(e)=>setStep({...step,escalation_hours:e.target.value})}/></Field><Button>Add step</Button></form>
  <form onSubmit={(e)=>{e.preventDefault();void save("/foundation/approval-requests",{...request,workflow_id:Number(request.workflow_id),branch_id:request.branch_id?Number(request.branch_id):null,site_id:request.site_id?Number(request.site_id):null,amount:request.amount?request.amount:null},"Approval request submitted")}}><h4>Test / submit request</h4><Field label="Workflow"><select value={request.workflow_id} onChange={(e)=>setRequest({...request,workflow_id:e.target.value})} required><option value="">Select</option>{workflows.map((w)=><option key={number(w,"id")} value={number(w,"id")}>{text(w,"name")}</option>)}</select></Field><Field label="Title"><input value={request.title} onChange={(e)=>setRequest({...request,title:e.target.value})} required/></Field><Field label="Entity ID"><input value={request.entity_id} onChange={(e)=>setRequest({...request,entity_id:e.target.value})} required/></Field><Field label="Amount M"><input type="number" value={request.amount} onChange={(e)=>setRequest({...request,amount:e.target.value})}/></Field><Field label="Branch"><select value={request.branch_id} onChange={(e)=>setRequest({...request,branch_id:e.target.value,site_id:""})}><option value="">Company</option>{branches.map((b)=><option key={number(b,"id")} value={number(b,"id")}>{text(b,"name")}</option>)}</select></Field><Field label="Site"><select value={request.site_id} onChange={(e)=>setRequest({...request,site_id:e.target.value})}><option value="">No site</option>{sites.filter((s)=>!request.branch_id||number(s,"branch_id")===Number(request.branch_id)).map((s)=><option key={number(s,"id")} value={number(s,"id")}>{text(s,"name")}</option>)}</select></Field><Button>Submit request</Button></form></div></section>
  <section className="panel"><div className="panel-head"><div><h3>Approval requests</h3><p>Act on the current step with an authorised role.</p></div></div><form className="action-bar" onSubmit={(e)=>{e.preventDefault();void save(`/foundation/approval-requests/${action.request_id}/actions`,{role_id:Number(action.role_id),actor_name:action.actor_name,action:action.action,comment:action.comment},`Request ${action.action}d`)}}><select value={action.request_id} onChange={(e)=>setAction({...action,request_id:e.target.value})} required><option value="">Select pending request</option>{requests.filter((r)=>text(r,"status")==="pending").map((r)=><option key={number(r,"id")} value={number(r,"id")}>{text(r,"reference")} · {text(r,"title")}</option>)}</select><select value={action.role_id} onChange={(e)=>setAction({...action,role_id:e.target.value})} required><option value="">Acting role</option>{roles.map((r)=><option key={number(r,"id")} value={number(r,"id")}>{text(r,"name")}</option>)}</select><select value={action.action} onChange={(e)=>setAction({...action,action:e.target.value})}><option value="approve">Approve</option><option value="reject">Reject</option></select><input placeholder="Comment" value={action.comment} onChange={(e)=>setAction({...action,comment:e.target.value})}/><Button>Record action</Button></form><DataTable columns={["Reference","Title","Amount M","Status","Step","Requested by"]} rows={requests.map((r)=>[text(r,"reference"),text(r,"title"),text(r,"amount")||"—",<Badge tone={text(r,"status")==="approved"?"green":text(r,"status")==="rejected"?"red":"amber"}>{text(r,"status")}</Badge>,text(r,"current_step_order"),text(r,"requested_by")])}/></section></div>;
}

function DocumentsPanel({ data, branches, sites, onSaved, setError }: { data:Row[];branches:Row[];sites:Row[];onSaved:(m:string)=>void;setError:(m:string)=>void }) {
  const[form,setForm]=useState({branch_id:"",site_id:"",title:"",category:"Corporate",entity_type:"",entity_id:"",confidentiality:"internal",created_by:"Phase 1 Admin"});const[uploadDoc,setUploadDoc]=useState("");const[file,setFile]=useState<File|null>(null);const[note,setNote]=useState("");
  async function create(e:FormEvent){e.preventDefault();try{await api("/foundation/documents",{method:"POST",body:JSON.stringify({...form,branch_id:form.branch_id?Number(form.branch_id):null,site_id:form.site_id?Number(form.site_id):null,entity_type:form.entity_type||null,entity_id:form.entity_id||null})});setForm({...form,title:"",entity_type:"",entity_id:""});onSaved("Document record created")}catch(err){setError(err instanceof Error?err.message:"Could not create document")}}
  async function upload(e:FormEvent){e.preventDefault();if(!file||!uploadDoc)return;try{const body=new FormData();body.append("file",file);body.append("uploaded_by","Phase 1 Admin");body.append("note",note);const response=await fetch(`${API}/foundation/documents/${uploadDoc}/versions`,{method:"POST",body});if(!response.ok){const payload=await response.json().catch(()=>({}));throw new Error(String(payload?.detail??"Upload failed"))}setFile(null);setNote("");onSaved("Document version uploaded")}catch(err){setError(err instanceof Error?err.message:"Upload failed")}}
  return <div className="stack"><section className="two-col"><div className="panel"><div className="panel-head"><div><h3>Register document</h3><p>Every document gets a controlled number and optional branch/site/entity ownership.</p></div></div><form className="compact-form" onSubmit={create}><Field label="Title"><input value={form.title} onChange={(e)=>setForm({...form,title:e.target.value})} required/></Field><Field label="Category"><input value={form.category} onChange={(e)=>setForm({...form,category:e.target.value})} required/></Field><Field label="Branch"><select value={form.branch_id} onChange={(e)=>setForm({...form,branch_id:e.target.value,site_id:""})}><option value="">Company-wide</option>{branches.map((b)=><option key={number(b,"id")} value={number(b,"id")}>{text(b,"name")}</option>)}</select></Field><Field label="Site"><select value={form.site_id} onChange={(e)=>setForm({...form,site_id:e.target.value})}><option value="">No site</option>{sites.filter((s)=>!form.branch_id||number(s,"branch_id")===Number(form.branch_id)).map((s)=><option key={number(s,"id")} value={number(s,"id")}>{text(s,"name")}</option>)}</select></Field><Field label="Related entity type"><input placeholder="tender / employee / vehicle / project" value={form.entity_type} onChange={(e)=>setForm({...form,entity_type:e.target.value})}/></Field><Field label="Related entity ID"><input value={form.entity_id} onChange={(e)=>setForm({...form,entity_id:e.target.value})}/></Field><Field label="Confidentiality"><select value={form.confidentiality} onChange={(e)=>setForm({...form,confidentiality:e.target.value})}><option value="public">Public</option><option value="internal">Internal</option><option value="confidential">Confidential</option><option value="restricted">Restricted</option></select></Field><Button>Create document</Button></form></div>
  <div className="panel"><div className="panel-head"><div><h3>Upload new version</h3><p>Files are SHA-256 hashed, versioned and stored on the persistent media volume.</p></div></div><form className="compact-form" onSubmit={upload}><Field label="Document"><select value={uploadDoc} onChange={(e)=>setUploadDoc(e.target.value)} required><option value="">Select document</option>{data.map((d)=><option key={number(d,"id")} value={number(d,"id")}>{text(d,"document_number")} · {text(d,"title")}</option>)}</select></Field><Field label="File"><input type="file" onChange={(e)=>setFile(e.target.files?.[0]??null)} required/></Field><Field label="Version note"><textarea value={note} onChange={(e)=>setNote(e.target.value)}/></Field><Button>Upload version</Button></form></div></section>
  <section className="panel"><DataTable columns={["Number","Title","Category","Scope","Versions","Latest file"]} rows={data.map((d)=>{const versions=rows(d.versions);const latest=versions[0];return[text(d,"document_number"),text(d,"title"),text(d,"category"),text(d,"branch_id")?text(branches.find((b)=>number(b,"id")===number(d,"branch_id")),"name"):"Company",versions.length,latest?<a className="link-btn" href={`${API}/foundation/documents/${number(d,"id")}/versions/${number(latest,"id")}/download`}>Download v{number(latest,"version_number")}</a>:"No file"]})}/></section></div>;
}

function MasterDataPanel({ data, onSaved, setError }: { data:Row[];onSaved:(m:string)=>void;setError:(m:string)=>void }) {
  const[category,setCategory]=useState({code:"",name:"",description:""});const[item,setItem]=useState({category_id:"",code:"",name:"",value:"{}",sort_order:"0"});
  async function save(path:string,body:Record<string,unknown>,message:string){try{await api(path,{method:"POST",body:JSON.stringify(body)});onSaved(message)}catch(err){setError(err instanceof Error?err.message:"Could not save master data")}}
  return <div className="stack"><section className="two-col"><div className="panel"><h3>New master-data category</h3><form className="compact-form" onSubmit={(e)=>{e.preventDefault();void save("/foundation/master-data/categories",category,"Category created")}}><Field label="Code"><input value={category.code} onChange={(e)=>setCategory({...category,code:e.target.value.toUpperCase()})} required/></Field><Field label="Name"><input value={category.name} onChange={(e)=>setCategory({...category,name:e.target.value})} required/></Field><Field label="Description"><textarea value={category.description} onChange={(e)=>setCategory({...category,description:e.target.value})}/></Field><Button>Create category</Button></form></div><div className="panel"><h3>Add master-data item</h3><form className="compact-form" onSubmit={(e)=>{e.preventDefault();let value:Record<string,unknown>={};try{value=JSON.parse(item.value) as Record<string,unknown>}catch{setError("Master-data value must be valid JSON");return}void save(`/foundation/master-data/categories/${item.category_id}/items`,{code:item.code,name:item.name,value,sort_order:Number(item.sort_order)},"Master-data item added")}}><Field label="Category"><select value={item.category_id} onChange={(e)=>setItem({...item,category_id:e.target.value})} required><option value="">Select</option>{data.map((c)=><option key={number(c,"id")} value={number(c,"id")}>{text(c,"name")}</option>)}</select></Field><Field label="Code"><input value={item.code} onChange={(e)=>setItem({...item,code:e.target.value.toUpperCase()})} required/></Field><Field label="Name"><input value={item.name} onChange={(e)=>setItem({...item,name:e.target.value})} required/></Field><Field label="JSON value"><textarea value={item.value} onChange={(e)=>setItem({...item,value:e.target.value})}/></Field><Button>Add item</Button></form></div></section><section className="master-grid">{data.map((category)=><article className="panel" key={number(category,"id")}><div className="panel-head"><div><h3>{text(category,"name")}</h3><p>{text(category,"code")}</p></div><Badge>{rows(category.items).length} items</Badge></div><div className="tag-list">{rows(category.items).map((entry)=><span key={number(entry,"id")}>{text(entry,"name")}</span>)}</div></article>)}</section></div>;
}

function SettingsPanel({ settings, sequences, onSaved, setError }: { settings:Row[];sequences:Row[];onSaved:(m:string)=>void;setError:(m:string)=>void }) {
  const[setting,setSetting]=useState({key:"",value:"{}",description:""});const[sequence,setSequence]=useState({code:"",name:"",prefix:"",next_number:"1",padding:"5",reset_period:"yearly"});
  async function saveSetting(e:FormEvent){e.preventDefault();try{const value=JSON.parse(setting.value) as Record<string,unknown>;await api(`/foundation/settings/${setting.key}`,{method:"PUT",body:JSON.stringify({key:setting.key,value,description:setting.description})});onSaved("Setting saved")}catch(err){setError(err instanceof Error?err.message:"Setting value must be valid JSON")}}
  async function saveSequence(e:FormEvent){e.preventDefault();try{await api("/foundation/number-sequences",{method:"POST",body:JSON.stringify({...sequence,next_number:Number(sequence.next_number),padding:Number(sequence.padding)})});onSaved("Number sequence created")}catch(err){setError(err instanceof Error?err.message:"Could not create sequence")}}
  async function issue(id:number){try{const result=await api<{reference:string}>(`/foundation/number-sequences/${id}/next`,{method:"POST"});onSaved(`Issued ${result.reference}`)}catch(err){setError(err instanceof Error?err.message:"Could not issue number")}}
  return <div className="stack"><section className="two-col"><div className="panel"><h3>Company settings</h3><form className="compact-form" onSubmit={saveSetting}><Field label="Key"><input value={setting.key} onChange={(e)=>setSetting({...setting,key:e.target.value.toLowerCase()})} required/></Field><Field label="JSON value"><textarea value={setting.value} onChange={(e)=>setSetting({...setting,value:e.target.value})}/></Field><Field label="Description"><input value={setting.description} onChange={(e)=>setSetting({...setting,description:e.target.value})}/></Field><Button>Save setting</Button></form></div><div className="panel"><h3>New numbering sequence</h3><form className="compact-form" onSubmit={saveSequence}><Field label="Code"><input value={sequence.code} onChange={(e)=>setSequence({...sequence,code:e.target.value.toUpperCase()})} required/></Field><Field label="Name"><input value={sequence.name} onChange={(e)=>setSequence({...sequence,name:e.target.value})} required/></Field><Field label="Prefix"><input value={sequence.prefix} onChange={(e)=>setSequence({...sequence,prefix:e.target.value.toUpperCase()})} required/></Field><Field label="Reset"><select value={sequence.reset_period} onChange={(e)=>setSequence({...sequence,reset_period:e.target.value})}><option value="never">Never</option><option value="yearly">Yearly</option><option value="monthly">Monthly</option></select></Field><Button>Create sequence</Button></form></div></section><section className="panel"><h3>Configured controls</h3><DataTable columns={["Setting","Value","Description"]} rows={settings.map((s)=>[text(s,"key"),<code key={number(s,"id")}>{JSON.stringify(s.value)}</code>,text(s,"description")])}/></section><section className="panel"><h3>Number sequences</h3><DataTable columns={["Code","Name","Prefix","Next","Reset",""]} rows={sequences.map((s)=>[text(s,"code"),text(s,"name"),text(s,"prefix"),text(s,"next_number"),text(s,"reset_period"),<button className="link-btn" onClick={()=>void issue(number(s,"id"))} key={number(s,"id")}>Issue test number</button>])}/></section></div>;
}

function AuditPanel({ data, branches, sites }: { data:Row[];branches:Row[];sites:Row[] }) {
  return <section className="panel"><div className="panel-head"><div><h3>Immutable operational audit trail</h3><p>Phase 1 mutations record actor, action, entity, scope and timestamp. Phase 2 will bind actors to authenticated users.</p></div><Badge tone="blue">Latest {data.length}</Badge></div><DataTable columns={["When","Actor","Action","Entity","Branch / site","Detail"]} rows={data.map((row)=>[new Date(text(row,"occurred_at")).toLocaleString(),text(row,"actor"),<code key={`a-${number(row,"id")}`}>{text(row,"action")}</code>,`${text(row,"entity_type")} #${text(row,"entity_id")}`,`${text(branches.find((b)=>number(b,"id")===number(row,"branch_id")),"code")||"—"} / ${text(sites.find((s)=>number(s,"id")===number(row,"site_id")),"code")||"—"}`,<code className="detail-code" key={`d-${number(row,"id")}`}>{JSON.stringify(row.detail)}</code>])}/></section>;
}

function CrudLayout({ title, detail, form, children }: { title:string;detail:string;form:React.ReactNode;children:React.ReactNode }) { return <div className="crud-layout"><section className="panel form-panel"><div className="panel-head"><div><h3>{title}</h3><p>{detail}</p></div></div>{form}</section><section className="panel table-panel">{children}</section></div>; }

function DataTable({ columns, rows: tableRows }: { columns:string[];rows:React.ReactNode[][] }) { return <div className="table-wrap"><table><thead><tr>{columns.map((column,index)=><th key={`${column}-${index}`}>{column}</th>)}</tr></thead><tbody>{tableRows.length?tableRows.map((row,rowIndex)=><tr key={rowIndex}>{row.map((cell,index)=><td key={index}>{cell}</td>)}</tr>):<tr><td colSpan={columns.length}><Empty>No records yet.</Empty></td></tr>}</tbody></table></div>; }
