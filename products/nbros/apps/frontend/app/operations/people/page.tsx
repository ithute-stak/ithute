import { redirect } from "next/navigation";

import { ApiError, nbrosApi } from "@/lib/backend";
import { createDriverCredentialAction, createDriverTrainingAction } from "../actions";
import OperationsNav from "../nav";

type Branch = { id: string; code: string; name: string };
type DriverCompliance = {
  driver_id: string;
  full_name: string;
  employee_number: string | null;
  license_number: string;
  license_category: string;
  license_expiry: string;
  compliance: "green" | "orange" | "red";
  credentials: Array<{ id: string; credential_type: string; reference: string | null; issue_date: string | null; expiry_date: string | null; status: string }>;
  training: Array<{ id: string; course_name: string; provider: string | null; completed_date: string; expiry_date: string | null; certificate_reference: string | null; status: string }>;
};

export default async function PeoplePage({ searchParams }: { searchParams: Promise<{ branch?: string }> }) {
  let branches: Branch[];
  try { branches = await nbrosApi<Branch[]>("/api/v1/fleet/branches"); }
  catch (error) { if (error instanceof ApiError && error.status === 401) redirect("/api/auth/login"); throw error; }
  if (!branches.length) redirect("/fleet");
  const params = await searchParams;
  const selected = branches.find((branch) => branch.id === params.branch) ?? branches[0];
  const drivers = await nbrosApi<DriverCompliance[]>(`/api/v1/operations/drivers/compliance?branch_id=${selected.id}`);
  const attention = drivers.filter((driver) => driver.compliance !== "green");
  const expired = drivers.filter((driver) => driver.compliance === "red");

  return <div className="app-shell"><OperationsNav branchId={selected.id} active="people"/><main className="workspace">
    <header className="workspace-header"><div><span className="eyebrow">Driver Compliance</span><h1>{selected.name} people readiness</h1><p className="muted">Licences, credentials and training are evaluated together before operational assignment.</p></div><form method="get" className="branch-picker"><select name="branch" defaultValue={selected.id}>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name} · {branch.code}</option>)}</select><button className="ghost-button">Switch</button></form></header>
    <section className="metric-grid"><article className="metric-card"><span>Active register</span><strong>{drivers.length}</strong><small>drivers assessed</small></article><article className="metric-card"><span>Compliant</span><strong>{drivers.length-attention.length}</strong><small>green readiness</small></article><article className="metric-card"><span>Attention</span><strong>{attention.length-expired.length}</strong><small>expiry within 30 days</small></article><article className="metric-card danger-card"><span>Blocked</span><strong>{expired.length}</strong><small>expired licence / credential / training</small></article></section>

    <section className="two-column"><article className="panel"><div className="panel-heading"><div><span className="eyebrow">Compliance document</span><h2>Add credential</h2></div></div><form action={createDriverCredentialAction} className="form-grid"><input type="hidden" name="branch_id" value={selected.id}/><label>Driver<select name="driver_id" required><option value="">Select driver</option>{drivers.map((driver)=><option key={driver.driver_id} value={driver.driver_id}>{driver.full_name} · {driver.license_number}</option>)}</select></label><label>Credential type<input name="credential_type" required placeholder="Defensive driving / permit / medical"/></label><label>Reference<input name="reference"/></label><label>Issue date<input type="date" name="issue_date"/></label><label>Expiry date<input type="date" name="expiry_date"/></label><label className="form-span">Notes<textarea name="notes" rows={2}/></label><div className="form-span"><button className="primary-button">Add credential</button></div></form></article>
    <article className="panel"><div className="panel-heading"><div><span className="eyebrow">Training register</span><h2>Record training</h2></div></div><form action={createDriverTrainingAction} className="form-grid"><input type="hidden" name="branch_id" value={selected.id}/><label>Driver<select name="driver_id" required><option value="">Select driver</option>{drivers.map((driver)=><option key={driver.driver_id} value={driver.driver_id}>{driver.full_name}</option>)}</select></label><label>Course<input name="course_name" required placeholder="Defensive driving"/></label><label>Provider<input name="provider"/></label><label>Completed<input type="date" name="completed_date" required/></label><label>Expiry / refresher<input type="date" name="expiry_date"/></label><label>Certificate reference<input name="certificate_reference"/></label><label className="form-span">Notes<textarea name="notes" rows={2}/></label><div className="form-span"><button className="primary-button">Record training</button></div></form></article></section>

    <section className="panel"><div className="panel-heading"><div><span className="eyebrow">Integrated compliance matrix</span><h2>Driver readiness</h2></div><span className="count-badge">{drivers.length}</span></div>{drivers.length ? <div className="table-wrap"><table><thead><tr><th>Driver</th><th>Licence</th><th>Compliance</th><th>Credentials</th><th>Training</th></tr></thead><tbody>{drivers.map((driver)=><tr key={driver.driver_id}><td><strong>{driver.full_name}</strong><div className="muted">{driver.employee_number ?? "No employee number"}</div></td><td>{driver.license_number} · {driver.license_category}<div className="muted">Expires {driver.license_expiry}</div></td><td><span className={`status-pill status-${driver.compliance}`}>{driver.compliance.toUpperCase()}</span></td><td>{driver.credentials.length ? driver.credentials.map((row)=><div key={row.id}><strong>{row.credential_type}</strong> · <span className={`status-pill ${row.status === "expired" ? "status-red" : row.status === "expiring" ? "status-orange" : "status-green"}`}>{row.status}</span>{row.expiry_date ? <span className="muted"> · {row.expiry_date}</span> : null}</div>) : <span className="muted">None recorded</span>}</td><td>{driver.training.length ? driver.training.map((row)=><div key={row.id}><strong>{row.course_name}</strong> · <span className={`status-pill ${row.status === "expired" ? "status-red" : row.status === "expiring" ? "status-orange" : "status-green"}`}>{row.status}</span>{row.expiry_date ? <span className="muted"> · {row.expiry_date}</span> : null}</div>) : <span className="muted">None recorded</span>}</td></tr>)}</tbody></table></div> : <div className="empty-state"><strong>No drivers registered.</strong><span>Register drivers from Fleet before adding compliance records.</span></div>}</section>
  </main></div>;
}
