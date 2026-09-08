"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useBuildTrackUi } from "../components/ui";
import styles from "../workforce/workforce.module.css";

type Row = Record<string, unknown>;

const API = "/api/v1";
const text = (row: Row | null | undefined, key: string) => String(row?.[key] ?? "");
const number = (row: Row | null | undefined, key: string) => Number(row?.[key] ?? 0);
const list = (value: unknown): Row[] => Array.isArray(value) ? value.filter((item): item is Row => Boolean(item) && typeof item === "object") : [];
const money = (value: unknown) => `M ${Number(value ?? 0).toLocaleString("en-LS", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const today = () => new Date().toISOString().slice(0, 10);
const nextYear = () => new Date(Date.now() + 365 * 86400000).toISOString().slice(0, 10);

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...init, credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  if (response.status === 401) {
    window.location.href = `/login?returnTo=${encodeURIComponent("/closeout")}`;
    throw new Error("Session expired");
  }
  const payload: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload && typeof payload === "object" ? (payload as Row).detail : "";
    throw new Error(typeof detail === "string" ? detail : "Project closeout action failed.");
  }
  return payload as T;
}

function badge(value: string) {
  if (["closed", "completed", "approved"].includes(value)) return styles.green;
  if (["submitted", "defects_liability", "in_progress"].includes(value)) return styles.amber;
  if (["rejected", "open", "critical", "high"].includes(value)) return styles.red;
  return styles.blue;
}

export default function CloseoutPage() {
  const { confirm, promptText } = useBuildTrackUi();
  const [projects, setProjects] = useState<Row[]>([]);
  const [cases, setCases] = useState<Row[]>([]);
  const [approvals, setApprovals] = useState<Row[]>([]);
  const [audit, setAudit] = useState<Row[]>([]);
  const [dashboard, setDashboard] = useState<Row>({});
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<Row | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [form, setForm] = useState({ project_id: "", practical_completion_date: today(), defects_liability_end_date: nextYear(), final_account_value: "0", retention_release_amount: "0", practical_completion_document_id: "", client_acceptance_document_id: "", final_account_document_id: "", retention_release_document_id: "", notes: "" });
  const [defect, setDefect] = useState({ category: "general", title: "", description: "", priority: "normal", raised_date: today(), due_date: "", evidence_document_id: "", notes: "" });

  const refresh = useCallback(async () => {
    try {
      const [catalog, nextCases, nextDashboard, nextApprovals, nextAudit] = await Promise.all([
        api<{ projects: Row[] }>("/closeout/catalog"), api<Row[]>("/closeout/cases"), api<Row>("/closeout/dashboard"), api<Row[]>("/closeout/approvals"), api<Row[]>("/closeout/audit?limit=120"),
      ]);
      setProjects(catalog.projects);
      setCases(nextCases);
      setDashboard(nextDashboard);
      setApprovals(nextApprovals);
      setAudit(nextAudit);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load Project Closeout. Initialise Phase 17 first.");
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  function done(message: string) {
    setNotice(message);
    setError("");
    window.setTimeout(() => setNotice(""), 4000);
    void refresh();
    if (selectedId) void choose(selectedId);
  }

  async function initialise() {
    try {
      await api("/closeout/bootstrap", { method: "POST" });
      done("Phase 17 roles, approvals, numbering and closeout policy are ready.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not initialise Phase 17");
    }
  }

  async function choose(id: number) {
    try {
      setSelectedId(id);
      setDetail(await api<Row>(`/closeout/cases/${id}`));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load closeout detail");
    }
  }

  async function createCase(event: FormEvent) {
    event.preventDefault();
    try {
      const created = await api<Row>("/closeout/cases", { method: "POST", body: JSON.stringify({ ...form, project_id: Number(form.project_id), final_account_value: Number(form.final_account_value), retention_release_amount: Number(form.retention_release_amount), practical_completion_document_id: form.practical_completion_document_id ? Number(form.practical_completion_document_id) : null, client_acceptance_document_id: form.client_acceptance_document_id ? Number(form.client_acceptance_document_id) : null, final_account_document_id: form.final_account_document_id ? Number(form.final_account_document_id) : null, retention_release_document_id: form.retention_release_document_id ? Number(form.retention_release_document_id) : null, notes: form.notes || null }) });
      setForm({ ...form, project_id: "", final_account_value: "0", retention_release_amount: "0", practical_completion_document_id: "", client_acceptance_document_id: "", final_account_document_id: "", retention_release_document_id: "", notes: "" });
      await choose(number(created, "id"));
      done("Controlled project closeout register and required handover checklist created.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not start project closeout");
    }
  }

  async function completeChecklist(row: Row) {
    const documentId = await promptText({ title: "Complete closeout control", description: "Link the controlled evidence document before completing this closeout requirement.", label: "Controlled document ID", placeholder: "e.g. 123", required: true, confirmLabel: "Complete control" });
    if (!documentId) return;
    try {
      await api(`/closeout/checklist/${number(row, "id")}`, { method: "PUT", body: JSON.stringify({ status: "completed", evidence_document_id: Number(documentId), notes: null }) });
      done("Closeout control completed with controlled evidence.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not complete closeout control");
    }
  }

  async function waiveChecklist(row: Row) {
    const notes = await promptText({ title: "Waive closeout control", description: "Record the authorised reason for this non-required item. The waiver remains in the project closeout audit trail.", label: "Waiver reason", multiline: true, required: true, confirmLabel: "Record waiver" });
    if (!notes) return;
    try {
      await api(`/closeout/checklist/${number(row, "id")}`, { method: "PUT", body: JSON.stringify({ status: "waived", evidence_document_id: null, notes }) });
      done("Closeout control formally waived with its recorded reason.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not waive closeout control");
    }
  }

  async function createDefect(event: FormEvent) {
    event.preventDefault();
    if (!selectedId) return;
    try {
      await api(`/closeout/cases/${selectedId}/defects`, { method: "POST", body: JSON.stringify({ ...defect, due_date: defect.due_date || null, evidence_document_id: defect.evidence_document_id ? Number(defect.evidence_document_id) : null, notes: defect.notes || null }) });
      setDefect({ ...defect, title: "", description: "", evidence_document_id: "", notes: "" });
      done("Defects-liability item registered with an auditable reference.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not record defect");
    }
  }

  async function defectStatus(row: Row, status: "in_progress" | "closed") {
    const documentId = status === "closed" ? await promptText({ title: "Close defects-liability item", description: "Link the controlled evidence that proves this defect was rectified.", label: "Controlled close-out document ID", required: true, placeholder: "e.g. 123", confirmLabel: "Close defect" }) : "";
    if (status === "closed" && !documentId) return;
    try {
      await api(`/closeout/defects/${number(row, "id")}`, { method: "PUT", body: JSON.stringify({ status, closeout_document_id: documentId ? Number(documentId) : null, notes: null }) });
      done(status === "closed" ? "Defect closed with controlled completion evidence." : "Defect moved to in-progress treatment.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update defect");
    }
  }

  async function submitCase() {
    if (!selectedId) return;
    const accepted = await confirm({ title: "Submit project closeout?", description: "This checks completion and creates the controlled maker/checker approval request.", confirmLabel: "Submit for approval" });
    if (!accepted) return;
    try {
      await api(`/closeout/cases/${selectedId}/submit`, { method: "POST" });
      done("Project closeout submitted for independent branch/HQ approval.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Closeout readiness gate is not complete");
    }
  }

  async function decide(row: Row, decision: "approve" | "reject") {
    const comment = await promptText({ title: decision === "approve" ? "Approve project closeout" : "Reject project closeout", description: "Record a decision comment in the immutable maker/checker approval trail.", label: "Decision comment", multiline: true, required: true, confirmLabel: decision === "approve" ? "Approve" : "Reject" });
    if (comment === null) return;
    try {
      await api(`/closeout/approvals/${number(row, "id")}/decision`, { method: "POST", body: JSON.stringify({ decision, comment }) });
      done(`Closeout approval ${decision}d.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not record closeout approval decision");
    }
  }

  async function finalClose() {
    if (!selectedId) return;
    const accepted = await confirm({ title: "Close this project permanently?", description: "The defects-liability period must have ended and every defect must be closed. This changes the project status to closed.", confirmLabel: "Close project", destructive: true });
    if (!accepted) return;
    try {
      await api(`/closeout/cases/${selectedId}/close`, { method: "POST" });
      done("Project closed after its controlled defects-liability completion gate.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Project cannot yet be finally closed");
    }
  }

  const checklist = list(detail?.checklist);
  const defects = list(detail?.defects);
  return <main className={styles.page}>
    <header className={styles.header}><div className={styles.brand}><div className={styles.brandMark}>CO</div><div><small>BuildTrack · Phase 17</small><h1>Project Closeout</h1><p>Practical completion · handover · defects liability · final closure</p></div></div><div className={styles.headerActions}><Link className={styles.link} href="/projects">Project Mobilisation</Link><Link className={styles.link} href="/commercial">Commercial Control</Link><Link className={styles.link} href="/assurance">HSE &amp; Quality</Link></div></header>
    <div className={styles.shell}>{error && <div className={styles.error}>{error}</div>}{notice && <div className={styles.notice}>{notice}</div>}
      <section className={styles.hero}><div className={styles.heroCard}><span className={styles.phase}>Completion gate</span><h2>Evidence before closure.</h2><p>Practical completion, as-builts, manuals, warranties, client handover, final account and retention evidence remain controlled records.</p></div><div className={styles.heroCard}><small>Open defects</small><h2>{text(dashboard, "open_defects")}</h2><p>{text(dashboard, "overdue_defects")} overdue · high/critical items block closeout approval.</p></div><div className={styles.heroCard}><small>Final closure due</small><h2>{text(dashboard, "due_for_final_close")}</h2><p>Approved defects-liability periods ready for final project closure.</p></div></section>
      <section className={styles.metrics}><div className={styles.metric}><small>Closeouts</small><strong>{text(dashboard, "closeouts")}</strong><span>{text(dashboard, "draft")} draft / returned</span></div><div className={styles.metric}><small>Awaiting approval</small><strong>{text(dashboard, "awaiting_approval")}</strong><span>maker/checker queue</span></div><div className={styles.metric}><small>Defects liability</small><strong>{text(dashboard, "defects_liability")}</strong><span>active correction window</span></div><div className={styles.metric}><small>Closed projects</small><strong>{text(dashboard, "closed")}</strong><span>controlled final closure</span></div></section>
      <section className={styles.panel}><div className={styles.panelHead}><div><h3>Start a controlled project closeout</h3><p>Creates the permanent completion checklist. Financial values are evidence only; BuildTrack never issues a payment instruction.</p></div><button className={styles.mini} onClick={() => void initialise()}>Initialise Phase 17</button></div><form className={styles.form} onSubmit={createCase}><div className={styles.field}><label>Project</label><select required value={form.project_id} onChange={(event) => setForm({ ...form, project_id: event.target.value })}><option value="">Select project</option>{projects.map((row) => <option key={number(row, "id")} value={String(row.id)}>{text(row, "project_number")} · {text(row, "name")}</option>)}</select></div><div className={styles.field}><label>Practical completion</label><input required type="date" value={form.practical_completion_date} onChange={(event) => setForm({ ...form, practical_completion_date: event.target.value })}/></div><div className={styles.field}><label>Defects-liability end</label><input required type="date" value={form.defects_liability_end_date} onChange={(event) => setForm({ ...form, defects_liability_end_date: event.target.value })}/></div><div className={styles.field}><label>Final account value</label><input type="number" min="0" step=".01" value={form.final_account_value} onChange={(event) => setForm({ ...form, final_account_value: event.target.value })}/></div><div className={styles.field}><label>Retention release amount</label><input type="number" min="0" step=".01" value={form.retention_release_amount} onChange={(event) => setForm({ ...form, retention_release_amount: event.target.value })}/></div><div className={styles.field}><label>Practical completion document ID</label><input type="number" value={form.practical_completion_document_id} onChange={(event) => setForm({ ...form, practical_completion_document_id: event.target.value })}/></div><div className={styles.field}><label>Client acceptance document ID</label><input type="number" value={form.client_acceptance_document_id} onChange={(event) => setForm({ ...form, client_acceptance_document_id: event.target.value })}/></div><div className={styles.field}><label>Final account document ID</label><input type="number" value={form.final_account_document_id} onChange={(event) => setForm({ ...form, final_account_document_id: event.target.value })}/></div><div className={styles.field}><label>Retention evidence document ID</label><input type="number" value={form.retention_release_document_id} onChange={(event) => setForm({ ...form, retention_release_document_id: event.target.value })}/></div><div className={`${styles.field} ${styles.wide}`}><label>Closeout notes</label><textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })}/></div><div className={styles.formActions}><button className={styles.button}>Create closeout register</button></div></form></section>
      <section className={styles.panel}><div className={styles.panelHead}><div><h3>Project closeout register</h3><p>Choose a closeout record to complete handover controls, manage the defects-liability register and request approval.</p></div><a className={styles.button} href="/api/v1/closeout/exports/cases.csv">Export CSV</a></div><div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Closeout</th><th>Project</th><th>Practical completion</th><th>Defects liability end</th><th>Final account</th><th>Retention</th><th>Status</th></tr></thead><tbody>{cases.map((row) => <tr key={number(row, "id")} className={styles.clickable} onClick={() => void choose(number(row, "id"))}><td><strong>{text(row, "closeout_number")}</strong></td><td>{text(row, "project_number")}<br/><small>{text(row, "project_name")}</small></td><td>{text(row, "practical_completion_date")}</td><td>{text(row, "defects_liability_end_date")}</td><td>{money(row.final_account_value)}</td><td>{money(row.retention_release_amount)}</td><td><span className={`${styles.badge} ${badge(text(row, "status"))}`}>{text(row, "status")}</span></td></tr>)}</tbody></table></div></section>
      {detail && <><section className={styles.panel}><div className={styles.panelHead}><div><h3>{text(detail, "closeout_number")} · {text(detail, "project_name")}</h3><p>Current status: <strong>{text(detail, "status")}</strong> · practical completion {text(detail, "practical_completion_date")} · defects liability ends {text(detail, "defects_liability_end_date")}</p></div><div className={styles.actions}>{["draft", "rejected"].includes(text(detail, "status")) && <button className={styles.button} onClick={() => void submitCase()}>Submit closeout</button>}{text(detail, "status") === "defects_liability" && <button className={`${styles.button} ${styles.danger}`} onClick={() => void finalClose()}>Final project closure</button>}</div></div><div className={styles.detail}><div><small>Final account evidence</small><strong>{money(detail.final_account_value)}</strong></div><div><small>Retention evidence</small><strong>{money(detail.retention_release_amount)}</strong></div><div><small>Checklist controls</small><strong>{checklist.filter((row) => ["completed", "waived"].includes(text(row, "status"))).length}/{checklist.length}</strong></div><div><small>Defects</small><strong>{defects.filter((row) => text(row, "status") !== "closed").length} open</strong></div></div></section>
        <section className={styles.grid2}><div className={styles.panel}><div className={styles.panelHead}><div><h3>Handover and completion controls</h3><p>Complete with controlled documents or record a formal waiver before approval.</p></div></div><div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Control</th><th>Due</th><th>Required</th><th>Status</th><th>Evidence</th><th>Action</th></tr></thead><tbody>{checklist.map((row) => <tr key={number(row, "id")}><td>{text(row, "title")}</td><td>{text(row, "due_date")}</td><td>{String(Boolean(row.required))}</td><td><span className={`${styles.badge} ${badge(text(row, "status"))}`}>{text(row, "status")}</span></td><td>{text(row, "evidence_document_id") || "—"}</td><td>{["draft", "rejected"].includes(text(detail, "status")) && text(row, "status") === "open" && <div className={styles.actions}><button className={`${styles.mini} ${styles.good}`} onClick={() => void completeChecklist(row)}>Complete</button>{!Boolean(row.required) && <button className={styles.mini} onClick={() => void waiveChecklist(row)}>Waive</button>}</div>}</td></tr>)}</tbody></table></div></div>
          <div className={styles.panel}><div className={styles.panelHead}><div><h3>Register defects-liability item</h3><p>Every high or critical outstanding item blocks closeout approval under the default policy.</p></div></div><form className={styles.form} onSubmit={createDefect}><div className={styles.field}><label>Category</label><input value={defect.category} onChange={(event) => setDefect({ ...defect, category: event.target.value })}/></div><div className={styles.field}><label>Priority</label><select value={defect.priority} onChange={(event) => setDefect({ ...defect, priority: event.target.value })}>{["low", "normal", "high", "critical"].map((value) => <option key={value}>{value}</option>)}</select></div><div className={styles.field}><label>Raised date</label><input type="date" value={defect.raised_date} onChange={(event) => setDefect({ ...defect, raised_date: event.target.value })}/></div><div className={styles.field}><label>Due date</label><input type="date" value={defect.due_date} onChange={(event) => setDefect({ ...defect, due_date: event.target.value })}/></div><div className={styles.field}><label>Title</label><input required value={defect.title} onChange={(event) => setDefect({ ...defect, title: event.target.value })}/></div><div className={styles.field}><label>Evidence document ID</label><input type="number" value={defect.evidence_document_id} onChange={(event) => setDefect({ ...defect, evidence_document_id: event.target.value })}/></div><div className={`${styles.field} ${styles.wide}`}><label>Description</label><textarea required value={defect.description} onChange={(event) => setDefect({ ...defect, description: event.target.value })}/></div><div className={`${styles.field} ${styles.wide}`}><label>Notes</label><textarea value={defect.notes} onChange={(event) => setDefect({ ...defect, notes: event.target.value })}/></div><div className={styles.formActions}><button className={styles.button}>Record defect</button></div></form></div></section>
        <section className={styles.panel}><div className={styles.panelHead}><div><h3>Defects-liability register</h3><p>Closing a defect requires a controlled close-out document.</p></div></div><div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Defect</th><th>Category</th><th>Priority</th><th>Raised</th><th>Due</th><th>Status</th><th>Close-out evidence</th><th>Action</th></tr></thead><tbody>{defects.map((row) => <tr key={number(row, "id")}><td><strong>{text(row, "defect_number")}</strong><br/><small>{text(row, "title")}</small></td><td>{text(row, "category")}</td><td><span className={`${styles.badge} ${badge(text(row, "priority"))}`}>{text(row, "priority")}</span></td><td>{text(row, "raised_date")}</td><td>{text(row, "due_date") || "—"}</td><td>{text(row, "status")}</td><td>{text(row, "closeout_document_id") || "—"}</td><td>{text(row, "status") !== "closed" && <div className={styles.actions}><button className={styles.mini} onClick={() => void defectStatus(row, "in_progress")}>Treat</button><button className={`${styles.mini} ${styles.good}`} onClick={() => void defectStatus(row, "closed")}>Close</button></div>}</td></tr>)}</tbody></table></div></section></>}
      <section className={styles.grid2}><div className={styles.panel}><div className={styles.panelHead}><div><h3>Closeout approval queue</h3><p>Closeout preparers cannot approve their own controlled submission under the company no-self-approval policy.</p></div></div><div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Reference</th><th>Closeout</th><th>Project</th><th>Amount</th><th>Step</th><th>Action</th></tr></thead><tbody>{approvals.map((row) => <tr key={number(row, "id")}><td>{text(row, "reference")}</td><td>{text(row, "closeout_number")}</td><td>{text(row, "project_number")}</td><td>{money(row.amount)}</td><td>{text(row, "current_step_order")}</td><td><div className={styles.actions}><button className={`${styles.mini} ${styles.good}`} onClick={() => void decide(row, "approve")}>Approve</button><button className={`${styles.mini} ${styles.bad}`} onClick={() => void decide(row, "reject")}>Reject</button></div></td></tr>)}</tbody></table></div></div>
        <div className={styles.panel}><div className={styles.panelHead}><div><h3>Closeout audit</h3><p>Latest Phase 17 completion, defect, approval and final-closure actions.</p></div></div><div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Project</th><th>Entity</th></tr></thead><tbody>{audit.map((row, index) => <tr key={String(row.id ?? index)}><td>{text(row, "occurred_at")}</td><td>{text(row, "actor")}</td><td>{text(row, "action")}</td><td>{text(row, "project_id")}</td><td>{text(row, "entity_type")} #{text(row, "entity_id")}</td></tr>)}</tbody></table></div></div></section>
    </div>
  </main>;
}
