import { redirect } from "next/navigation";

import { ApiError, nbrosApi } from "@/lib/backend";
import { updateBudgetAction, updateFuelSettingsAction } from "../actions";
import OperationsNav from "../nav";

type Branch = { id: string; code: string; name: string };
type Budget = { id: string; year: number; month: number; budget_amount: number; notes: string | null };
type VehicleCost = { vehicle_id: string; registration_plate: string; known_cost: number; cost_per_recorded_km: number | null; fuel: number; service: number; workshop_labour: number; external_repairs: number; tyres: number; insurance_excess: number };
type Report = {
  year: number;
  budget: { annual_budget: number; known_cost: number; open_procurement_commitments: number; forecast_committed_total: number; variance_to_budget: number };
  categories: Record<string, number>;
  fuel: {
    settings: { anomaly_l_per_100km: number; price_deviation_percent: number; minimum_distance_km: number };
    summary: { records: number; litres: number; cost: number; average_price_per_litre: number | null; anomalies: number };
    vehicles: Array<{ vehicle_id: string; registration_plate: string; fills: number; litres: number; cost: number; average_l_per_100km: number | null }>;
    anomalies: Array<{ record_id: string; vehicle_id: string; registration_plate: string; recorded_at: string; mileage: number; litres: number; cost: number; consumption_l_per_100km: number | null; reasons: string[] }>;
  };
  top_cost_vehicles: VehicleCost[];
  cost_per_vehicle: number;
};
function money(value: number) { return `M ${value.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }

export default async function FinancePage({ searchParams }: { searchParams: Promise<{ branch?: string }> }) {
  let branches: Branch[];
  try { branches = await nbrosApi<Branch[]>("/api/v1/fleet/branches"); }
  catch (error) { if (error instanceof ApiError && error.status === 401) redirect("/api/auth/login"); throw error; }
  if (!branches.length) redirect("/fleet");
  const params = await searchParams;
  const selected = branches.find((branch) => branch.id === params.branch) ?? branches[0];
  const [report, budgets] = await Promise.all([
    nbrosApi<Report>(`/api/v1/operations/finance/management-report?branch_id=${selected.id}`),
    nbrosApi<Budget[]>(`/api/v1/operations/finance/budgets?branch_id=${selected.id}`),
  ]);
  const currentBudgets = budgets.filter((row) => row.year === report.year);

  return <div className="app-shell"><OperationsNav branchId={selected.id} active="finance"/><main className="workspace">
    <header className="workspace-header"><div><span className="eyebrow">Finance & Fuel Intelligence</span><h1>{selected.name} operating economics</h1><p className="muted">Known TCO, procurement commitments, branch budgets and deterministic fuel anomalies in one control view.</p></div><form method="get" className="branch-picker"><select name="branch" defaultValue={selected.id}>{branches.map((branch)=><option key={branch.id} value={branch.id}>{branch.name} · {branch.code}</option>)}</select><button className="ghost-button">Switch</button></form></header>

    <section className="metric-grid"><article className="metric-card"><span>{report.year} budget</span><strong>{money(report.budget.annual_budget)}</strong><small>{currentBudgets.length} monthly budgets configured</small></article><article className="metric-card"><span>Known operating cost</span><strong>{money(report.budget.known_cost)}</strong><small>{money(report.cost_per_vehicle)} per vehicle average</small></article><article className="metric-card"><span>Open commitments</span><strong>{money(report.budget.open_procurement_commitments)}</strong><small>issued / partly received POs</small></article><article className={`metric-card ${report.budget.variance_to_budget < 0 ? "danger-card" : ""}`}><span>Budget variance</span><strong>{money(report.budget.variance_to_budget)}</strong><small>after known cost + commitments</small></article><article className="metric-card"><span>Fuel spend</span><strong>{money(report.fuel.summary.cost)}</strong><small>{report.fuel.summary.litres.toLocaleString()} litres recorded</small></article><article className={`metric-card ${report.fuel.summary.anomalies ? "danger-card" : ""}`}><span>Fuel anomalies</span><strong>{report.fuel.summary.anomalies}</strong><small>deterministic exceptions</small></article></section>

    <section className="two-column"><article className="panel"><div className="panel-heading"><div><span className="eyebrow">Budget control</span><h2>Set monthly Fleet budget</h2></div></div><form action={updateBudgetAction} className="form-grid"><input type="hidden" name="branch_id" value={selected.id}/><label>Year<input type="number" name="year" min="2000" max="2200" defaultValue={report.year} required/></label><label>Month<input type="number" name="month" min="1" max="12" required/></label><label>Budget amount (M)<input type="number" name="budget_amount" min="0" step="0.01" required/></label><label>Notes<input name="notes"/></label><div className="form-span"><button className="primary-button">Save budget</button></div></form>{currentBudgets.length ? <div className="table-wrap"><table><thead><tr><th>Month</th><th>Budget</th><th>Notes</th></tr></thead><tbody>{currentBudgets.sort((a,b)=>a.month-b.month).map((row)=><tr key={row.id}><td>{row.month}</td><td>{money(row.budget_amount)}</td><td>{row.notes ?? "—"}</td></tr>)}</tbody></table></div> : null}</article>
    <article className="panel"><div className="panel-heading"><div><span className="eyebrow">Fuel controls</span><h2>Anomaly thresholds</h2></div></div><form action={updateFuelSettingsAction} className="form-grid"><input type="hidden" name="branch_id" value={selected.id}/><label>High consumption threshold (L/100km)<input type="number" name="anomaly_l_per_100km" min="1" max="200" step="0.1" defaultValue={report.fuel.settings.anomaly_l_per_100km} required/></label><label>Price deviation (%)<input type="number" name="price_deviation_percent" min="0" max="500" step="0.1" defaultValue={report.fuel.settings.price_deviation_percent} required/></label><label>Minimum distance (km)<input type="number" name="minimum_distance_km" min="1" max="5000" defaultValue={report.fuel.settings.minimum_distance_km} required/></label><div className="form-span"><button className="primary-button">Update fuel controls</button></div></form><div className="alert-row"><strong>Branch average fuel price</strong><span>{report.fuel.summary.average_price_per_litre == null ? "Not enough data" : `${money(report.fuel.summary.average_price_per_litre)} / litre`}</span></div></article></section>

    <section className="two-column"><article className="panel"><div className="panel-heading"><div><span className="eyebrow">Spend mix</span><h2>Recorded cost categories</h2></div></div><div className="table-wrap"><table><thead><tr><th>Category</th><th>Known cost</th></tr></thead><tbody>{Object.entries(report.categories).sort((a,b)=>b[1]-a[1]).map(([key,amount])=><tr key={key}><td>{key.replaceAll("_"," ")}</td><td>{money(amount)}</td></tr>)}</tbody></table></div></article>
    <article className="panel"><div className="panel-heading"><div><span className="eyebrow">Fuel efficiency</span><h2>Vehicle consumption</h2></div></div>{report.fuel.vehicles.length ? <div className="table-wrap"><table><thead><tr><th>Vehicle</th><th>Fills</th><th>Litres</th><th>Cost</th><th>L/100km</th></tr></thead><tbody>{report.fuel.vehicles.map((row)=><tr key={row.vehicle_id}><td><strong>{row.registration_plate}</strong></td><td>{row.fills}</td><td>{row.litres.toLocaleString()}</td><td>{money(row.cost)}</td><td>{row.average_l_per_100km == null ? "—" : row.average_l_per_100km.toFixed(2)}</td></tr>)}</tbody></table></div> : <div className="empty-state"><strong>No fuel records yet.</strong></div>}</article></section>

    <section className="panel"><div className="panel-heading"><div><span className="eyebrow">Exception engine</span><h2>Fuel anomalies</h2></div><span className="count-badge">{report.fuel.anomalies.length}</span></div>{report.fuel.anomalies.length ? <div className="alert-list">{report.fuel.anomalies.map((row)=><div className="alert-row alert-red" key={row.record_id}><div><strong>{row.registration_plate} · {row.mileage.toLocaleString()} km</strong><span>{new Date(row.recorded_at).toLocaleString()} · {row.litres} L · {money(row.cost)}</span></div><span>{row.reasons.join(" · ")}</span></div>)}</div> : <div className="empty-state"><strong>No fuel anomalies.</strong><span>Recorded fuel events are inside configured thresholds.</span></div>}</section>

    <section className="panel"><div className="panel-heading"><div><span className="eyebrow">TCO ranking</span><h2>Highest-cost vehicles</h2></div></div>{report.top_cost_vehicles.length ? <div className="table-wrap"><table><thead><tr><th>Vehicle</th><th>Total</th><th>Cost / km</th><th>Fuel</th><th>Service</th><th>Workshop</th><th>External</th><th>Tyres</th></tr></thead><tbody>{report.top_cost_vehicles.map((row)=><tr key={row.vehicle_id}><td><strong>{row.registration_plate}</strong></td><td>{money(row.known_cost)}</td><td>{row.cost_per_recorded_km == null ? "—" : money(row.cost_per_recorded_km)}</td><td>{money(row.fuel)}</td><td>{money(row.service)}</td><td>{money(row.workshop_labour)}</td><td>{money(row.external_repairs)}</td><td>{money(row.tyres)}</td></tr>)}</tbody></table></div> : <div className="empty-state"><strong>No cost data yet.</strong></div>}</section>
  </main></div>;
}
