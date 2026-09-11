import Link from "next/link";
import { redirect } from "next/navigation";

import {
  addAccidentAction,
  addAssignmentAction,
  addFuelAction,
  addMaintenanceAction,
  addReservationAction,
  addTripAction,
  cancelReservationAction,
  closeMaintenanceAction,
  completeAssignmentAction,
  returnTripAction,
} from "../operational-actions";
import { ApiError, nbrosApi } from "@/lib/backend";

type Vehicle = { id: string; registration_plate: string; make: string; model: string; vehicle_type: string };
type Driver = { id: string; full_name: string; license_category: string };
type Operations = {
  maintenance: Array<{ id: string; vehicle: string; description: string; status: string; expected_release_at: string | null }>;
  assignments: Array<{ id: string; vehicle: string; driver: string; purpose: string | null; start_at: string; end_at: string | null }>;
  trips: Array<{ id: string; vehicle: string; driver: string; destination: string; purpose: string | null; start_at: string; expected_return_at: string | null }>;
  reservations: Array<{ id: string; vehicle: string; driver: string | null; purpose: string | null; start_at: string; end_at: string }>;
};

function VehicleOptions({ vehicles }: { vehicles: Vehicle[] }) {
  return <>{vehicles.map((vehicle) => <option value={vehicle.id} key={vehicle.id}>{vehicle.registration_plate} · {vehicle.make} {vehicle.model}</option>)}</>;
}
function DriverOptions({ drivers }: { drivers: Driver[] }) {
  return <>{drivers.map((driver) => <option value={driver.id} key={driver.id}>{driver.full_name} · {driver.license_category}</option>)}</>;
}

export default async function OperationsPage({ searchParams }: { searchParams: Promise<{ branch?: string }> }) {
  const { branch } = await searchParams;
  if (!branch) redirect("/fleet");
  let vehicles: Vehicle[];
  let drivers: Driver[];
  let operations: Operations;
  try {
    [vehicles, drivers, operations] = await Promise.all([
      nbrosApi<Vehicle[]>(`/api/v1/fleet/vehicles?branch_id=${branch}`),
      nbrosApi<Driver[]>(`/api/v1/fleet/drivers?branch_id=${branch}`),
      nbrosApi<Operations>(`/api/v1/fleet/operations?branch_id=${branch}`),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/api/auth/login");
    throw error;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand"><span className="mini-mark">NB</span><strong>NBros</strong></div>
        <nav>
          <span className="nav-section">Fleet</span>
          <Link className="nav-item" href={`/fleet?branch=${branch}`}>Dashboard</Link>
          <Link className="nav-item" href={`/fleet/drivers?branch=${branch}`}>Drivers</Link>
          <Link className="nav-item" href={`/fleet/requests?branch=${branch}`}>Vehicle requests</Link>
          <Link className="nav-item active" href={`/fleet/operations?branch=${branch}`}>Operations</Link>
          <Link className="nav-item" href={`/fleet/settings?branch=${branch}`}>Settings</Link>
        </nav>
      </aside>
      <main className="workspace">
        <header className="workspace-header"><div><span className="eyebrow">Fleet Management</span><h1>Operations</h1><p className="muted">Assignments, trips, maintenance, reservations, fuel and accidents for this company branch.</p></div><Link className="ghost-button" href={`/fleet?branch=${branch}`}>Back to fleet</Link></header>

        {vehicles.length === 0 ? <section className="panel"><div className="empty-state"><strong>Register a vehicle first.</strong><span>Operational records require a branch vehicle.</span></div></section> : <>
          <section className="operations-grid">
            <article className="panel"><span className="eyebrow">Maintenance</span><h2>Open work order</h2><form action={addMaintenanceAction} className="form-grid"><input type="hidden" name="branch_id" value={branch}/><label>Vehicle<select name="vehicle_id" required><VehicleOptions vehicles={vehicles}/></select></label><label>Expected release<input type="datetime-local" name="expected_release_at"/></label><label className="form-span">Work required<textarea name="description" required/></label><div className="form-span"><button className="primary-button">Open maintenance</button></div></form></article>
            <article className="panel"><span className="eyebrow">Assignment</span><h2>Assign vehicle</h2><form action={addAssignmentAction} className="form-grid"><input type="hidden" name="branch_id" value={branch}/><label>Vehicle<select name="vehicle_id" required><VehicleOptions vehicles={vehicles}/></select></label><label>Driver<select name="driver_id" required><DriverOptions drivers={drivers}/></select></label><label>Start<input type="datetime-local" name="start_at" required/></label><label>End<input type="datetime-local" name="end_at"/></label><label className="form-span">Purpose<input name="purpose"/></label><div className="form-span"><button className="primary-button" disabled={drivers.length === 0}>Create assignment</button></div></form></article>
            <article className="panel"><span className="eyebrow">Trip</span><h2>Start / schedule trip</h2><form action={addTripAction} className="form-grid"><input type="hidden" name="branch_id" value={branch}/><label>Vehicle<select name="vehicle_id" required><VehicleOptions vehicles={vehicles}/></select></label><label>Driver<select name="driver_id" required><DriverOptions drivers={drivers}/></select></label><label>Destination<input name="destination" required/></label><label>Purpose<input name="purpose"/></label><label>Start<input type="datetime-local" name="start_at" required/></label><label>Expected return<input type="datetime-local" name="expected_return_at"/></label><div className="form-span"><button className="primary-button" disabled={drivers.length === 0}>Record trip</button></div></form></article>
            <article className="panel"><span className="eyebrow">Reservation</span><h2>Reserve vehicle</h2><form action={addReservationAction} className="form-grid"><input type="hidden" name="branch_id" value={branch}/><label>Vehicle<select name="vehicle_id" required><VehicleOptions vehicles={vehicles}/></select></label><label>Driver (optional)<select name="driver_id"><option value="">Not assigned</option><DriverOptions drivers={drivers}/></select></label><label>From<input type="datetime-local" name="start_at" required/></label><label>To<input type="datetime-local" name="end_at" required/></label><label className="form-span">Purpose<input name="purpose"/></label><div className="form-span"><button className="primary-button">Reserve vehicle</button></div></form></article>
            <article className="panel"><span className="eyebrow">Fuel</span><h2>Record fuel</h2><form action={addFuelAction} className="form-grid"><input type="hidden" name="branch_id" value={branch}/><label>Vehicle<select name="vehicle_id" required><VehicleOptions vehicles={vehicles}/></select></label><label>Mileage<input type="number" min="0" name="mileage" required/></label><label>Litres<input type="number" min="0.01" step="0.01" name="litres" required/></label><label>Cost<input type="number" min="0" step="0.01" name="cost"/></label><label className="form-span">Station<input name="station"/></label><div className="form-span"><button className="primary-button">Save fuel record</button></div></form></article>
            <article className="panel"><span className="eyebrow">Accident</span><h2>Record incident</h2><form action={addAccidentAction} className="form-grid"><input type="hidden" name="branch_id" value={branch}/><label>Vehicle<select name="vehicle_id" required><VehicleOptions vehicles={vehicles}/></select></label><label>Driver<select name="driver_id"><option value="">Not recorded</option><DriverOptions drivers={drivers}/></select></label><label>Date & time<input type="datetime-local" name="occurred_at" required/></label><label>Location<input name="location"/></label><label>Reference<input name="reference_number"/></label><label className="form-span">Description<textarea name="description" required/></label><div className="form-span"><button className="primary-button">Save accident record</button></div></form></article>
          </section>

          <section className="panel"><div className="panel-heading"><div><span className="eyebrow">Current state</span><h2>Active operations</h2></div></div><div className="operations-grid">
            <div><h3>Maintenance</h3><div className="history-list">{operations.maintenance.length === 0 ? <span className="muted">None active.</span> : operations.maintenance.map((row) => <div key={row.id}><strong>{row.vehicle} · {row.description}</strong><span>{row.expected_release_at ? `Expected ${row.expected_release_at}` : "Release date unknown"}</span><form action={closeMaintenanceAction}><input type="hidden" name="branch_id" value={branch}/><input type="hidden" name="id" value={row.id}/><button className="mini-action">Close</button></form></div>)}</div></div>
            <div><h3>Assignments</h3><div className="history-list">{operations.assignments.length === 0 ? <span className="muted">None active.</span> : operations.assignments.map((row) => <div key={row.id}><strong>{row.vehicle} · {row.driver}</strong><span>{row.purpose ?? "Assignment"}{row.end_at ? ` · until ${row.end_at}` : ""}</span><form action={completeAssignmentAction}><input type="hidden" name="branch_id" value={branch}/><input type="hidden" name="id" value={row.id}/><button className="mini-action">Complete</button></form></div>)}</div></div>
            <div><h3>Trips</h3><div className="history-list">{operations.trips.length === 0 ? <span className="muted">None active.</span> : operations.trips.map((row) => <div key={row.id}><strong>{row.vehicle} → {row.destination}</strong><span>{row.driver}{row.expected_return_at ? ` · expected ${row.expected_return_at}` : ""}</span><form action={returnTripAction}><input type="hidden" name="branch_id" value={branch}/><input type="hidden" name="id" value={row.id}/><button className="mini-action">Mark returned</button></form></div>)}</div></div>
            <div><h3>Reservations</h3><div className="history-list">{operations.reservations.length === 0 ? <span className="muted">None active.</span> : operations.reservations.map((row) => <div key={row.id}><strong>{row.vehicle}{row.driver ? ` · ${row.driver}` : ""}</strong><span>{row.start_at} → {row.end_at}</span><form action={cancelReservationAction}><input type="hidden" name="branch_id" value={branch}/><input type="hidden" name="id" value={row.id}/><button className="mini-action">Cancel</button></form></div>)}</div></div>
          </div></section>
        </>}
      </main>
    </div>
  );
}
