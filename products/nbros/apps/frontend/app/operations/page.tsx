import { redirect } from "next/navigation";

import { ApiError, nbrosApi } from "@/lib/backend";
import { decideApprovalAction, updateBudgetAction } from "./actions";
import OperationsNav from "./nav";

type Branch = { id: string; code: string; name: string; location: string | null };
type TcoVehicle = { vehicle_id: string; registration_plate: string; known_cost: number; cost_per_recorded_km: number | null; current_mileage: number };
type Executive = {
  fleet: { total: number; ready: number; attention: number; blocked: number; available_now: number; replacement_candidates: Array<{ vehicle_id: string; registration_plate: string; age_years: number | null; current_mileage: number }> };
  drivers: { active: number; licences_expiring_or_expired_30d: number };
  workshop: { open_jobs: number };
  stores: { low_stock: number };
  procurement: { pending: number };
  dispatch: { pending: number; active: number };
  risk: { open_claims: number; pending_approvals: number };
  finance: { known_operating_cost: number; vehicles: TcoVehicle[] };
};
type Approval = { id: string; workflow_key: string; entity_type: string; status: string; amount: number; reason: string | null; requested_at: string };

function money(value: number) { return `M ${value.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }

export default async function OperationsPage({ searchParams }: { searchParams: Promise<{ branch?: string }> }) {
  let branches: Branch[];
  try { branches = await nbrosApi<Branch[]>("/api/v1/fleet/branches"); }
  catch (error) { if (error instanceof ApiError && error.status === 401) redirect("/api/auth/login"); throw error; }
  if (!branches.length) redirect("/fleet");
  const params = await searchParams;
  const selected = branches.find((branch) => branch.id === params.branch) ?? branches[0];
  const [data, approvals] = await Promise.all([
    nbrosApi<Executive>(`/api/v1/operations/executive?branch_id=${selected.id}`),
    nbrosApi<Approval[]>(`/api/v1/operations/approvals?branch_id=${selected.id}&status_filter=pending`),
  ]);

  return <div className="app-shell">
    <OperationsNav branchId={selected.id} active="command" />
    <main className="workspace">
      <header className="workspace-header"><div><span className="eyebrow">Enterprise Operations</span><h1>{selected.name} command centre</h1></div><div className="header-actions"><form method="get" className="branch-picker"><select name="branch" defaultValue={selected.id}>{branches.map((branch) => <option value={branch.id} key={branch.id}>{branch.name} · {branch.code}</option>)}</select><button className="ghost-button">Switch</button></form><form action="/api/auth/logout" method="post"><button className="ghost-button">Sign out</button></form></div></header>

      <section className="metric-grid">
        <article className="metric-card"><span>Fleet ready</span><strong>{data.fleet.ready}/{data.fleet.total}</strong><small>{data.fleet.available_now} available now</small></article>
        <article className="metric-card danger-card"><span>Fleet blocked</span><strong>{data.fleet.blocked}</strong><small>{data.fleet.attention} need attention</small></article>
        <article className="metric-card"><span>Workshop</span><strong>{data.workshop.open_jobs}</strong><small>open job cards</small></article>
        <article className="metric-card"><span>Stores</span><strong>{data.stores.low_stock}</strong><small>items at/below reorder</small></article>
        <article className="metric-card"><span>Procurement</span><strong>{data.procurement.pending}</strong><small>pending workflow items</small></article>
        <article className="metric-card"><span>Dispatch</span><strong>{data.dispatch.active}</strong><small>{data.dispatch.pending} waiting approval</small></article>
        <article className="metric-card"><span>Claims</span><strong>{data.risk.open_claims}</strong><small>open insurance claims</small></article>
        <article className="metric-card danger-card"><span>Approvals</span><strong>{data.risk.pending_approvals}</strong><small>management decisions waiting</small></article>
      </section>

      <section className="two-column">
        <article className="panel"><div className="panel-heading"><div><span className="eyebrow">Financial intelligence</span><h2>Known operating cost</h2></div></div><div className="readiness-row"><div><strong>{money(data.finance.known_operating_cost)}</strong><span>recorded Fleet operating cost</span></div></div><div className="table-wrap"><table><thead><tr><th>Vehicle</th><th>Known cost</th><th>Cost / recorded km</th></tr></thead><tbody>{data.finance.vehicles.slice().sort((a,b) => b.known_cost-a.known_cost).slice(0,8).map((row) => <tr key={row.vehicle_id}><td>{row.registration_plate}</td><td>{money(row.known_cost)}</td><td>{row.cost_per_recorded_km == null ? "—" : money(row.cost_per_recorded_km)}</td></tr>)}</tbody></table></div></article>
        <article className="panel"><div className="panel-heading"><div><span className="eyebrow">Replacement intelligence</span><h2>Replacement candidates</h2></div><span className="count-badge">{data.fleet.replacement_candidates.length}</span></div>{data.fleet.replacement_candidates.length ? <div className="alert-list">{data.fleet.replacement_candidates.map((row) => <div className="alert-row alert-orange" key={row.vehicle_id}><strong>{row.registration_plate}</strong><span>{row.age_years == null ? "Age unknown" : `${row.age_years} years`} · {row.current_mileage.toLocaleString()} km</span></div>)}</div> : <div className="empty-state"><strong>No replacement threshold exceeded.</strong><span>Age and mileage thresholds are configurable per company branch.</span></div>}</article>
      </section>

      <section className="two-column">
        <article className="panel"><div className="panel-heading"><div><span className="eyebrow">Workflow engine</span><h2>Pending approvals</h2></div></div>{approvals.length ? <div className="alert-list">{approvals.slice(0,10).map((approval) => <div className="alert-row alert-orange" key={approval.id}><div><strong>{approval.workflow_key.replaceAll("_", " ")}</strong><span>{approval.reason ?? approval.entity_type} · {money(approval.amount)}</span></div><form action={decideApprovalAction} className="header-actions"><input type="hidden" name="branch_id" value={selected.id}/><input type="hidden" name="approval_id" value={approval.id}/><input type="hidden" name="return_path" value="/operations"/><button className="ghost-button" name="decision" value="reject">Reject</button><button className="primary-button" name="decision" value="approve">Approve</button></form></div>)}</div> : <div className="empty-state"><strong>No approvals waiting.</strong><span>Workshop and procurement approvals will appear here.</span></div>}</article>
        <article className="panel"><div className="panel-heading"><div><span className="eyebrow">Branch control</span><h2>Monthly Fleet budget</h2></div></div><form action={updateBudgetAction} className="form-grid"><input type="hidden" name="branch_id" value={selected.id}/><label>Year<input type="number" name="year" required defaultValue={new Date().getFullYear()}/></label><label>Month<input type="number" name="month" min="1" max="12" required defaultValue={new Date().getMonth()+1}/></label><label>Budget amount (M)<input type="number" name="budget_amount" min="0" step="0.01" required/></label><label>Notes<input name="notes"/></label><div className="form-span"><button className="primary-button">Save branch budget</button></div></form></article>
      </section>
    </main>
  </div>;
}
