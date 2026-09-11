import { redirect } from "next/navigation";

import { ApiError, nbrosApi } from "@/lib/backend";
import { approveDispatchAction, completeDispatchAction, createDispatchAction, startDispatchAction } from "../actions";
import OperationsNav from "../nav";

type Branch = { id: string; code: string; name: string };
type Driver = { id: string; full_name: string; license_category: string; license_expiry: string; is_active: boolean };
type Dispatch = { id: string; vehicle_type: string; driver_id: string | null; assigned_vehicle_id: string | null; destination: string; purpose: string; start_at: string; end_at: string; status: string };
type FleetDashboard = { vehicles: Array<{ vehicle: { id: string; registration_plate: string; make: string; model: string; vehicle_type: string } }> };

export default async function DispatchPage({ searchParams }: { searchParams: Promise<{ branch?: string }> }) {
  let branches: Branch[];
  try { branches = await nbrosApi<Branch[]>("/api/v1/fleet/branches"); }
  catch (error) { if (error instanceof ApiError && error.status === 401) redirect("/api/auth/login"); throw error; }
  if (!branches.length) redirect("/fleet");
  const params = await searchParams; const selected = branches.find((branch) => branch.id === params.branch) ?? branches[0];
  const [requests, drivers, fleet] = await Promise.all([
    nbrosApi<Dispatch[]>(`/api/v1/operations/dispatch?branch_id=${selected.id}`),
    nbrosApi<Driver[]>(`/api/v1/fleet/drivers?branch_id=${selected.id}`),
    nbrosApi<FleetDashboard>(`/api/v1/fleet/dashboard?branch_id=${selected.id}`),
  ]);
  const driverNames = new Map(drivers.map((driver) => [driver.id, driver.full_name]));
  const vehicleNames = new Map(fleet.vehicles.map((row) => [row.vehicle.id, row.vehicle.registration_plate]));
  const vehicleTypes = [...new Set(fleet.vehicles.map((row) => row.vehicle.vehicle_type))].sort();

  return <div className="app-shell"><OperationsNav branchId={selected.id} active="dispatch"/><main className="workspace">
    <header className="workspace-header"><div><span className="eyebrow">Dispatch & Transport</span><h1>{selected.name} dispatch control</h1></div><form method="get" className="branch-picker"><select name="branch" defaultValue={selected.id}>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name} · {branch.code}</option>)}</select><button className="ghost-button">Switch</button></form></header>
    <section className="metric-grid"><article className="metric-card"><span>Pending</span><strong>{requests.filter((row) => row.status === "pending").length}</strong><small>waiting vehicle decision</small></article><article className="metric-card"><span>Approved</span><strong>{requests.filter((row) => row.status === "approved").length}</strong><small>ready for departure</small></article><article className="metric-card"><span>Active</span><strong>{requests.filter((row) => row.status === "active").length}</strong><small>trips underway</small></article><article className="metric-card"><span>Drivers</span><strong>{drivers.filter((row) => row.is_active).length}</strong><small>active branch drivers</small></article></section>

    <section className="panel"><div className="panel-heading"><div><span className="eyebrow">Transport request</span><h2>Request vehicle & driver</h2></div></div><form action={createDispatchAction} className="form-grid"><input type="hidden" name="branch_id" value={selected.id}/><label>Vehicle type<select name="vehicle_type" required><option value="">Select type</option>{vehicleTypes.map((type) => <option value={type} key={type}>{type}</option>)}</select></label><label>Driver<select name="driver_id"><option value="">Assign later</option>{drivers.filter((driver) => driver.is_active).map((driver) => <option key={driver.id} value={driver.id}>{driver.full_name} · {driver.license_category}</option>)}</select></label><label>Destination<input name="destination" required/></label><label>Purpose<input name="purpose" required/></label><label>Start<input type="datetime-local" name="start_at" required/></label><label>End / expected return<input type="datetime-local" name="end_at" required/></label><label>Passengers<input type="number" name="passenger_count" min="0" defaultValue="0"/></label><label>Load description<input name="load_description"/></label><div className="form-span"><button className="primary-button">Submit dispatch request</button></div></form></section>

    <section className="panel"><div className="panel-heading"><div><span className="eyebrow">Decision-driven allocation</span><h2>Dispatch board</h2></div><span className="count-badge">{requests.length}</span></div>{requests.length ? <div className="table-wrap"><table><thead><tr><th>Destination</th><th>Type</th><th>Driver</th><th>Vehicle</th><th>Period</th><th>Status</th><th>Control</th></tr></thead><tbody>{requests.map((row) => <tr key={row.id}><td><strong>{row.destination}</strong><br/><small>{row.purpose}</small></td><td>{row.vehicle_type}</td><td>{row.driver_id ? driverNames.get(row.driver_id) ?? row.driver_id : "Unassigned"}</td><td>{row.assigned_vehicle_id ? vehicleNames.get(row.assigned_vehicle_id) ?? row.assigned_vehicle_id : "Pending match"}</td><td>{new Date(row.start_at).toLocaleString()}<br/><small>to {new Date(row.end_at).toLocaleString()}</small></td><td><span className={`status-pill ${row.status === "active" ? "status-green" : row.status === "pending" ? "status-orange" : row.status === "completed" ? "status-green" : "status-orange"}`}>{row.status.toUpperCase()}</span></td><td>{row.status === "pending" ? <form action={approveDispatchAction}><input type="hidden" name="branch_id" value={selected.id}/><input type="hidden" name="request_id" value={row.id}/><button className="primary-button">Auto-match & approve</button></form> : row.status === "approved" ? <form action={startDispatchAction}><input type="hidden" name="branch_id" value={selected.id}/><input type="hidden" name="request_id" value={row.id}/><button className="primary-button">Start trip</button></form> : row.status === "active" ? <form action={completeDispatchAction}><input type="hidden" name="branch_id" value={selected.id}/><input type="hidden" name="request_id" value={row.id}/><button className="ghost-button">Complete trip</button></form> : "—"}</td></tr>)}</tbody></table></div> : <div className="empty-state"><strong>No dispatch requests.</strong><span>The matching engine will recommend only Fleet-eligible vehicles and drivers.</span></div>}</section>
  </main></div>;
}
