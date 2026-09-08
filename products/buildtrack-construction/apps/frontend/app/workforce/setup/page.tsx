"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import styles from "../workforce.module.css";

type Row = Record<string, unknown>;
type Catalog = {
  branches: Row[];
  sites: Row[];
  departments: Row[];
  cost_centres: Row[];
  users: Row[];
  leave_types: Row[];
  shifts: Row[];
  pay_components: Row[];
  permissions: string[];
};

const API = "/api/v1";

function text(row: Row | null | undefined, key: string): string { return String(row?.[key] ?? ""); }
function num(row: Row | null | undefined, key: string): number { return Number(row?.[key] ?? 0); }
function list(value: unknown): Row[] { return Array.isArray(value) ? value as Row[] : []; }

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (response.status === 401) {
    window.location.href = `/login?returnTo=${encodeURIComponent("/workforce/setup")}`;
    throw new Error("Session expired");
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload?.detail === "string" ? payload.detail : JSON.stringify(payload?.detail ?? payload));
  return payload as T;
}

function Field({ label, children, wide = false }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return <div className={`${styles.field} ${wide ? styles.wide : ""}`}><label>{label}</label>{children}</div>;
}

function Btn({ children, variant = "", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "secondary" | "danger" | "" }) {
  return <button {...props} className={`${styles.button} ${variant ? styles[variant] : ""}`}>{children}</button>;
}

export default function WorkforceSetupPage() {
  const [catalog, setCatalog] = useState<Catalog>({ branches: [], sites: [], departments: [], cost_centres: [], users: [], leave_types: [], shifts: [], pay_components: [], permissions: [] });
  const [employees, setEmployees] = useState<Row[]>([]);
  const [periods, setPeriods] = useState<Row[]>([]);
  const [shiftAssignments, setShiftAssignments] = useState<Row[]>([]);
  const [selectedEmployeeId, setSelectedEmployeeId] = useState("");
  const [employeeDetail, setEmployeeDetail] = useState<Row | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  const [leaveBalance, setLeaveBalance] = useState({ employee_id: "", leave_type_id: "", year: String(new Date().getFullYear()), opening_days: "0", accrued_days: "0", adjusted_days: "0" });
  const [payAssignment, setPayAssignment] = useState({ employee_id: "", component_id: "", value: "0", effective_from: new Date().toISOString().slice(0, 10), effective_to: "", notes: "" });
  const [shiftAssignment, setShiftAssignment] = useState({ employee_id: "", shift_id: "", effective_from: new Date().toISOString().slice(0, 10), effective_to: "" });
  const [linkUser, setLinkUser] = useState({ employee_id: "", user_id: "" });
  const [lifecycle, setLifecycle] = useState({ employee_id: "", employment_status: "active", termination_date: "", reason: "", revoke_linked_user_access: false });
  const [activation, setActivation] = useState({ contract_id: "", employee_signed: false, company_signed: false });

  const permissions = useMemo(() => new Set(catalog.permissions), [catalog.permissions]);
  const canPeopleManage = permissions.has("people.manage");
  const canPeopleApprove = permissions.has("people.approve");
  const canPeopleExport = permissions.has("people.export");
  const canLeaveManage = permissions.has("leave.manage");
  const canAttendanceManage = permissions.has("attendance.manage");
  const canPayrollManage = permissions.has("payroll.manage");
  const canPayrollApprove = permissions.has("payroll.approve");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const [c, e, p, s] = await Promise.all([
        api<Catalog>("/workforce/catalog"),
        api<Row[]>("/workforce/employees"),
        api<Row[]>("/workforce/payroll-periods").catch(() => []),
        api<Row[]>("/workforce/shift-assignments").catch(() => []),
      ]);
      setCatalog(c);
      setEmployees(e);
      setPeriods(p);
      setShiftAssignments(s);
      if (selectedEmployeeId) setEmployeeDetail(await api<Row>(`/workforce/employees/${Number(selectedEmployeeId)}`).catch(() => null));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load Workforce Setup");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, []);

  function success(message: string) {
    setNotice(message);
    setError("");
    window.setTimeout(() => setNotice(""), 3500);
    void refresh();
  }

  async function chooseEmployee(id: string) {
    setSelectedEmployeeId(id);
    setActivation({ contract_id: "", employee_signed: false, company_signed: false });
    if (!id) { setEmployeeDetail(null); return; }
    try { setEmployeeDetail(await api<Row>(`/workforce/employees/${Number(id)}`)); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not load employee details"); }
  }

  async function saveLeaveBalance(event: FormEvent) {
    event.preventDefault();
    try {
      await api("/workforce/leave-balances", { method: "PUT", body: JSON.stringify({ ...leaveBalance, employee_id: Number(leaveBalance.employee_id), leave_type_id: Number(leaveBalance.leave_type_id), year: Number(leaveBalance.year), opening_days: Number(leaveBalance.opening_days), accrued_days: Number(leaveBalance.accrued_days), adjusted_days: Number(leaveBalance.adjusted_days) }) });
      success("Leave balance saved and auditable.");
    } catch (err) { setError(err instanceof Error ? err.message : "Could not save leave balance"); }
  }

  async function savePayAssignment(event: FormEvent) {
    event.preventDefault();
    try {
      await api("/workforce/employee-pay-components", { method: "PUT", body: JSON.stringify({ ...payAssignment, employee_id: Number(payAssignment.employee_id), component_id: Number(payAssignment.component_id), value: Number(payAssignment.value), effective_to: payAssignment.effective_to || null, notes: payAssignment.notes || null }) });
      success("Recurring employee pay component assigned.");
    } catch (err) { setError(err instanceof Error ? err.message : "Could not assign pay component"); }
  }

  async function saveShiftAssignment(event: FormEvent) {
    event.preventDefault();
    try {
      await api("/workforce/shift-assignments", { method: "POST", body: JSON.stringify({ ...shiftAssignment, employee_id: Number(shiftAssignment.employee_id), shift_id: Number(shiftAssignment.shift_id), effective_to: shiftAssignment.effective_to || null }) });
      success("Shift assignment saved.");
    } catch (err) { setError(err instanceof Error ? err.message : "Could not assign shift"); }
  }

  async function saveUserLink(event: FormEvent) {
    event.preventDefault();
    try {
      await api(`/workforce/employees/${Number(linkUser.employee_id)}/link-user`, { method: "POST", body: JSON.stringify({ user_id: linkUser.user_id ? Number(linkUser.user_id) : null }) });
      success(linkUser.user_id ? "Employee linked to system user." : "Employee login link removed.");
    } catch (err) { setError(err instanceof Error ? err.message : "Could not update employee login link"); }
  }

  async function saveLifecycle(event: FormEvent) {
    event.preventDefault();
    try {
      await api(`/workforce/employees/${Number(lifecycle.employee_id)}/lifecycle`, { method: "POST", body: JSON.stringify({ ...lifecycle, termination_date: lifecycle.employment_status === "terminated" ? lifecycle.termination_date || null : null, reason: lifecycle.reason || null }) });
      success("Employee lifecycle status updated.");
    } catch (err) { setError(err instanceof Error ? err.message : "Could not update employee lifecycle"); }
  }

  async function activateContract(event: FormEvent) {
    event.preventDefault();
    try {
      await api(`/workforce/contracts/${Number(activation.contract_id)}/activate-signed`, { method: "POST", body: JSON.stringify({ employee_signed: activation.employee_signed, company_signed: activation.company_signed }) });
      success("Contract signatures confirmed and contract activated.");
      if (selectedEmployeeId) await chooseEmployee(selectedEmployeeId);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not activate contract"); }
  }

  async function closePeriod(periodId: number) {
    try {
      await api(`/workforce/payroll-periods/${periodId}/close-reviewed`, { method: "POST" });
      success("Payroll period closed after approved-run verification.");
    } catch (err) { setError(err instanceof Error ? err.message : "Could not close payroll period"); }
  }

  if (loading) return <main className={styles.page}><div className={styles.loading}><strong>Loading Workforce Setup…</strong></div></main>;

  return <main className={styles.page}>
    <header className={styles.header}>
      <div className={styles.brand}><span className={styles.brandMark}>BT</span><div><small>BuildTrack Construction Operations</small><h1>Workforce Setup</h1><p>Controlled HR/payroll administration · Phase 3</p></div></div>
      <div className={styles.headerActions}><Link className={styles.link} href="/workforce">Workforce operations</Link><Link className={styles.link} href="/access">Access & Security</Link><Link className={styles.link} href="/">Core platform</Link></div>
    </header>
    <div className={styles.shell}>
      {error && <div className={styles.error}>{error}</div>}
      {notice && <div className={styles.notice}>{notice}</div>}
      <div className={styles.warning}>This console changes workforce master data. Payroll approval still prepares auditable data only; it does not send salary payments and it does not invent statutory tax or pension rates.</div>

      <section className={styles.hero}>
        <div className={styles.heroCard}><span className={styles.phase}>Phase 3 · Administration</span><h2>Finish the controls behind daily workforce operations.</h2><p>Manage balances, shifts, recurring pay components, employee login links, lifecycle status, contract signature activation and exports without bypassing branch/site permissions.</p></div>
        <div className={styles.heroCard}><small>Visible workforce</small><h2>{employees.length}</h2><p>{catalog.branches.length} branch scope(s) · {catalog.sites.length} site scope(s)</p></div>
      </section>

      <div className={styles.grid2}>
        {canLeaveManage && <section className={styles.panel}><div className={styles.panelHead}><div><h3>Leave balance setup</h3><p>Set opening/accrued/adjustment days before leave approval.</p></div></div><form className={styles.form} onSubmit={saveLeaveBalance}><Field label="Employee" wide><select required value={leaveBalance.employee_id} onChange={e => setLeaveBalance({ ...leaveBalance, employee_id: e.target.value })}><option value="">Select</option>{employees.map(employee => <option key={num(employee,"id")} value={num(employee,"id")}>{text(employee,"employee_number")} · {text(employee,"full_name")}</option>)}</select></Field><Field label="Leave type" wide><select required value={leaveBalance.leave_type_id} onChange={e => setLeaveBalance({ ...leaveBalance, leave_type_id: e.target.value })}><option value="">Select</option>{catalog.leave_types.map(item => <option key={num(item,"id")} value={num(item,"id")}>{text(item,"code")} · {text(item,"name")}</option>)}</select></Field><Field label="Year"><input type="number" min="2000" max="2200" value={leaveBalance.year} onChange={e => setLeaveBalance({ ...leaveBalance, year: e.target.value })}/></Field><Field label="Opening days"><input type="number" step="0.5" min="0" value={leaveBalance.opening_days} onChange={e => setLeaveBalance({ ...leaveBalance, opening_days: e.target.value })}/></Field><Field label="Accrued days"><input type="number" step="0.5" min="0" value={leaveBalance.accrued_days} onChange={e => setLeaveBalance({ ...leaveBalance, accrued_days: e.target.value })}/></Field><Field label="Adjustment"><input type="number" step="0.5" value={leaveBalance.adjusted_days} onChange={e => setLeaveBalance({ ...leaveBalance, adjusted_days: e.target.value })}/></Field><div className={styles.formActions}><Btn>Save balance</Btn></div></form></section>}

        {canPayrollManage && <section className={styles.panel}><div className={styles.panelHead}><div><h3>Recurring pay assignment</h3><p>Assign configured earning/deduction components to an employee.</p></div></div><form className={styles.form} onSubmit={savePayAssignment}><Field label="Employee" wide><select required value={payAssignment.employee_id} onChange={e => setPayAssignment({ ...payAssignment, employee_id: e.target.value })}><option value="">Select</option>{employees.map(employee => <option key={num(employee,"id")} value={num(employee,"id")}>{text(employee,"employee_number")} · {text(employee,"full_name")}</option>)}</select></Field><Field label="Component" wide><select required value={payAssignment.component_id} onChange={e => setPayAssignment({ ...payAssignment, component_id: e.target.value })}><option value="">Select</option>{catalog.pay_components.map(item => <option key={num(item,"id")} value={num(item,"id")}>{text(item,"code")} · {text(item,"name")}</option>)}</select></Field><Field label="Value"><input required type="number" min="0" step="0.0001" value={payAssignment.value} onChange={e => setPayAssignment({ ...payAssignment, value: e.target.value })}/></Field><Field label="Effective from"><input required type="date" value={payAssignment.effective_from} onChange={e => setPayAssignment({ ...payAssignment, effective_from: e.target.value })}/></Field><Field label="Effective to"><input type="date" value={payAssignment.effective_to} onChange={e => setPayAssignment({ ...payAssignment, effective_to: e.target.value })}/></Field><Field label="Notes"><input value={payAssignment.notes} onChange={e => setPayAssignment({ ...payAssignment, notes: e.target.value })}/></Field><div className={styles.formActions}><Btn>Assign component</Btn></div></form></section>}

        {canAttendanceManage && <section className={styles.panel}><div className={styles.panelHead}><div><h3>Shift assignment</h3><p>Assign a controlled shift to an employee with effective dates.</p></div></div><form className={styles.form} onSubmit={saveShiftAssignment}><Field label="Employee" wide><select required value={shiftAssignment.employee_id} onChange={e => setShiftAssignment({ ...shiftAssignment, employee_id: e.target.value })}><option value="">Select</option>{employees.map(employee => <option key={num(employee,"id")} value={num(employee,"id")}>{text(employee,"employee_number")} · {text(employee,"full_name")}</option>)}</select></Field><Field label="Shift" wide><select required value={shiftAssignment.shift_id} onChange={e => setShiftAssignment({ ...shiftAssignment, shift_id: e.target.value })}><option value="">Select</option>{catalog.shifts.map(item => <option key={num(item,"id")} value={num(item,"id")}>{text(item,"code")} · {text(item,"name")}</option>)}</select></Field><Field label="Effective from"><input required type="date" value={shiftAssignment.effective_from} onChange={e => setShiftAssignment({ ...shiftAssignment, effective_from: e.target.value })}/></Field><Field label="Effective to"><input type="date" value={shiftAssignment.effective_to} onChange={e => setShiftAssignment({ ...shiftAssignment, effective_to: e.target.value })}/></Field><div className={styles.formActions}><Btn>Assign shift</Btn></div></form><div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Employee</th><th>Shift</th><th>From</th><th>To</th></tr></thead><tbody>{shiftAssignments.slice(0,50).map(row => <tr key={num(row,"id")}><td>{text(row,"employee_number")} · {text(row,"employee_name")}</td><td>{text(row,"shift_code")} · {text(row,"shift_name")}</td><td>{text(row,"effective_from")}</td><td>{text(row,"effective_to") || "Open"}</td></tr>)}</tbody></table></div></section>}

        {canPeopleManage && <section className={styles.panel}><div className={styles.panelHead}><div><h3>Employee account link</h3><p>Employees can exist without a login. Link only when system access is required.</p></div></div><form className={styles.form} onSubmit={saveUserLink}><Field label="Employee" wide><select required value={linkUser.employee_id} onChange={e => setLinkUser({ ...linkUser, employee_id: e.target.value })}><option value="">Select</option>{employees.map(employee => <option key={num(employee,"id")} value={num(employee,"id")}>{text(employee,"employee_number")} · {text(employee,"full_name")}</option>)}</select></Field><Field label="System user" wide><select value={linkUser.user_id} onChange={e => setLinkUser({ ...linkUser, user_id: e.target.value })}><option value="">No linked login</option>{catalog.users.map(user => <option key={num(user,"id")} value={num(user,"id")}>{text(user,"username")} · {text(user,"full_name")}</option>)}</select></Field><div className={styles.formActions}><Btn>Save user link</Btn></div></form>{catalog.users.length === 0 && <div className={styles.sectionNote}>No user catalogue is visible. Linking accounts requires company-level user visibility; employee/payroll records themselves do not require login accounts.</div>}</section>}

        {canPeopleManage && <section className={styles.panel}><div className={styles.panelHead}><div><h3>Employee lifecycle</h3><p>Suspend, deactivate or terminate while optionally revoking linked user sessions.</p></div></div><form className={styles.form} onSubmit={saveLifecycle}><Field label="Employee" wide><select required value={lifecycle.employee_id} onChange={e => setLifecycle({ ...lifecycle, employee_id: e.target.value })}><option value="">Select</option>{employees.map(employee => <option key={num(employee,"id")} value={num(employee,"id")}>{text(employee,"employee_number")} · {text(employee,"full_name")}</option>)}</select></Field><Field label="Status"><select value={lifecycle.employment_status} onChange={e => setLifecycle({ ...lifecycle, employment_status: e.target.value })}>{["active","on_leave","suspended","inactive","terminated"].map(status => <option key={status} value={status}>{status.replaceAll("_"," ")}</option>)}</select></Field><Field label="Termination date"><input type="date" disabled={lifecycle.employment_status !== "terminated"} required={lifecycle.employment_status === "terminated"} value={lifecycle.termination_date} onChange={e => setLifecycle({ ...lifecycle, termination_date: e.target.value })}/></Field><Field label="Reason" wide><input value={lifecycle.reason} onChange={e => setLifecycle({ ...lifecycle, reason: e.target.value })}/></Field><Field label="Revoke linked login"><select value={lifecycle.revoke_linked_user_access ? "yes" : "no"} onChange={e => setLifecycle({ ...lifecycle, revoke_linked_user_access: e.target.value === "yes" })}><option value="no">No</option><option value="yes">Yes</option></select></Field><div className={styles.formActions}><Btn variant={lifecycle.employment_status === "terminated" ? "danger" : ""}>Apply lifecycle change</Btn></div></form></section>}

        {canPeopleApprove && <section className={styles.panel}><div className={styles.panelHead}><div><h3>Contract signature activation</h3><p>Activation requires explicit employee and company signature confirmations.</p></div></div><Field label="Employee" wide><select value={selectedEmployeeId} onChange={e => void chooseEmployee(e.target.value)}><option value="">Select</option>{employees.map(employee => <option key={num(employee,"id")} value={num(employee,"id")}>{text(employee,"employee_number")} · {text(employee,"full_name")}</option>)}</select></Field><form className={styles.form} onSubmit={activateContract} style={{marginTop:12}}><Field label="Draft contract" wide><select required value={activation.contract_id} onChange={e => setActivation({ ...activation, contract_id: e.target.value })}><option value="">Select</option>{list(employeeDetail?.contracts).filter(contract => text(contract,"status") === "draft").map(contract => <option key={num(contract,"id")} value={num(contract,"id")}>{text(contract,"contract_number")} · {text(contract,"job_title")}</option>)}</select></Field><Field label="Employee signed"><select value={activation.employee_signed ? "yes" : "no"} onChange={e => setActivation({ ...activation, employee_signed: e.target.value === "yes" })}><option value="no">Not confirmed</option><option value="yes">Confirmed</option></select></Field><Field label="Company signed"><select value={activation.company_signed ? "yes" : "no"} onChange={e => setActivation({ ...activation, company_signed: e.target.value === "yes" })}><option value="no">Not confirmed</option><option value="yes">Confirmed</option></select></Field><div className={styles.formActions}><Btn>Confirm signatures & activate</Btn></div></form></section>}
      </div>

      <div className={styles.grid2}>
        {canPeopleExport && <section className={styles.panel}><div className={styles.panelHead}><div><h3>Employee export</h3><p>Exports only employees visible in your authorised scope. Restricted pay data remains blank without sensitive access.</p></div></div><div className={styles.toolbar}><a className={styles.button} href="/api/v1/workforce/employees/export.csv">Download employee CSV</a></div></section>}
        {canPayrollApprove && <section className={styles.panel}><div className={styles.panelHead}><div><h3>Payroll period close</h3><p>A period can close only when every run in it is approved.</p></div></div><div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Period</th><th>Dates</th><th>Status</th><th/></tr></thead><tbody>{periods.map(period => <tr key={num(period,"id")}><td>{text(period,"code")} · {text(period,"name")}</td><td>{text(period,"start_date")} → {text(period,"end_date")}</td><td>{text(period,"status")}</td><td>{text(period,"status") === "open" && <button className={styles.mini} onClick={() => void closePeriod(num(period,"id"))}>Close approved period</button>}</td></tr>)}</tbody></table></div></section>}
      </div>
    </div>
  </main>;
}
