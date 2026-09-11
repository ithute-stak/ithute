import Link from "next/link";
import { redirect } from "next/navigation";

import { createBranchAction, createVehicleAction } from "./actions";
import { ApiError, nbrosApi } from "@/lib/backend";

type Branch = {
  id: string;
  code: string;
  name: string;
  location: string | null;
  is_active: boolean;
};

type Status = {
  level: "green" | "orange" | "red";
  label: string;
  detail: string;
};

type Dashboard = {
  branch: { id: string; code: string; name: string };
  totals: {
    vehicles: number;
    available_now: number;
    documents_attention: number;
    service_attention: number;
    mechanical_attention: number;
    out_of_service: number;
  };
  readiness: { green: number; orange: number; red: number };
  alerts: Array<Status & { vehicle_id: string; registration_plate: string }>;
  vehicles: Array<{
    vehicle: {
      id: string;
      registration_plate: string;
      make: string;
      model: string;
      vehicle_type: string;
      current_mileage: number;
    };
    readiness: "green" | "orange" | "red";
    documents: { overall: Status };
    service: Status;
    mechanical: Status;
    inspection: Status;
    availability: Status & { expected_available_at?: string | null };
  }>;
};

function StatusPill({ level, children }: { level: string; children: React.ReactNode }) {
  return <span className={`status-pill status-${level}`}>{children}</span>;
}

export default async function FleetPage({
  searchParams,
}: {
  searchParams: Promise<{ branch?: string }>;
}) {
  let branches: Branch[];
  try {
    branches = await nbrosApi<Branch[]>("/api/v1/fleet/branches");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/api/auth/login");
    throw error;
  }

  const params = await searchParams;

  if (branches.length === 0) {
    return (
      <div className="app-shell">
        <aside className="sidebar">
          <div className="sidebar-brand"><span className="mini-mark">NB</span><strong>NBros</strong></div>
          <nav>
            <span className="nav-section">Modules</span>
            <a className="nav-item active">Fleet Management</a>
          </nav>
        </aside>
        <main className="workspace">
          <header className="workspace-header">
            <div>
              <span className="eyebrow">Fleet Management</span>
              <h1>Set up the first company branch</h1>
            </div>
            <form action="/api/auth/logout" method="post"><button className="ghost-button">Sign out</button></form>
          </header>
          <section className="panel setup-panel">
            <h2>Company branch</h2>
            <p>
              Every Fleet record belongs to one Nthane Brothers branch. Create the branch
              before adding vehicles, drivers, services or assignments.
            </p>
            <form action={createBranchAction} className="form-grid">
              <label>Branch code<input name="code" required placeholder="HQ" /></label>
              <label>Branch name<input name="name" required placeholder="Ha Foso" /></label>
              <label className="form-span">Location<input name="location" placeholder="Ha Foso, Maseru" /></label>
              <div className="form-span"><button className="primary-button" type="submit">Create branch & enable Fleet</button></div>
            </form>
          </section>
        </main>
      </div>
    );
  }

  const selected = branches.find((branch) => branch.id === params.branch) ?? branches[0];
  const dashboard = await nbrosApi<Dashboard>(`/api/v1/fleet/dashboard?branch_id=${selected.id}`);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand"><span className="mini-mark">NB</span><strong>NBros</strong></div>
        <nav>
          <span className="nav-section">Modules</span>
          <a className="nav-item active">Fleet Management</a>
        </nav>
        <div className="sidebar-footer">Nthane Brothers</div>
      </aside>

      <main className="workspace">
        <header className="workspace-header">
          <div>
            <span className="eyebrow">Fleet Management System</span>
            <h1>{selected.name}</h1>
          </div>
          <div className="header-actions">
            <form method="get" className="branch-picker">
              <select name="branch" defaultValue={selected.id} aria-label="Company branch">
                {branches.map((branch) => <option value={branch.id} key={branch.id}>{branch.name} · {branch.code}</option>)}
              </select>
              <button className="ghost-button" type="submit">Switch</button>
            </form>
            <form action="/api/auth/logout" method="post"><button className="ghost-button">Sign out</button></form>
          </div>
        </header>

        <section className="metric-grid">
          <article className="metric-card"><span>Total fleet</span><strong>{dashboard.totals.vehicles}</strong><small>registered vehicles</small></article>
          <article className="metric-card"><span>Available now</span><strong>{dashboard.totals.available_now}</strong><small>all checks passed</small></article>
          <article className="metric-card"><span>Documents</span><strong>{dashboard.totals.documents_attention}</strong><small>need attention</small></article>
          <article className="metric-card"><span>Service</span><strong>{dashboard.totals.service_attention}</strong><small>due / overdue</small></article>
          <article className="metric-card"><span>Mechanical</span><strong>{dashboard.totals.mechanical_attention}</strong><small>attention required</small></article>
          <article className="metric-card danger-card"><span>Out of service</span><strong>{dashboard.totals.out_of_service}</strong><small>critical condition</small></article>
        </section>

        <section className="two-column">
          <article className="panel">
            <div className="panel-heading"><div><span className="eyebrow">Decision engine</span><h2>Fleet readiness</h2></div></div>
            <div className="readiness-row">
              <div><span className="readiness-dot green-dot" /><strong>{dashboard.readiness.green}</strong><span>Ready</span></div>
              <div><span className="readiness-dot orange-dot" /><strong>{dashboard.readiness.orange}</strong><span>Attention</span></div>
              <div><span className="readiness-dot red-dot" /><strong>{dashboard.readiness.red}</strong><span>Blocked</span></div>
            </div>
          </article>
          <article className="panel">
            <div className="panel-heading"><div><span className="eyebrow">Branch control</span><h2>{selected.code}</h2></div></div>
            <p className="muted">All records displayed on this screen are isolated to <strong>{selected.name}</strong>.</p>
          </article>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <div><span className="eyebrow">Operational fleet</span><h2>Vehicles</h2></div>
            <details className="inline-details">
              <summary className="primary-button">Register vehicle</summary>
              <form action={createVehicleAction} className="form-grid popup-form">
                <input type="hidden" name="branch_id" value={selected.id} />
                <label>Registration / plate<input name="registration_plate" required /></label>
                <label>Vehicle type<input name="vehicle_type" required placeholder="Light vehicle" /></label>
                <label>Make<input name="make" required /></label>
                <label>Model<input name="model" required /></label>
                <label>Year<input name="year" type="number" min="1900" max="2200" /></label>
                <label>Current mileage<input name="current_mileage" type="number" min="0" defaultValue="0" /></label>
                <label>VIN / chassis<input name="vin" /></label>
                <label>Engine number<input name="engine_number" /></label>
                <label>Fuel type<input name="fuel_type" /></label>
                <label>Purchase date<input name="purchase_date" type="date" /></label>
                <label>Purchase price<input name="purchase_price" type="number" min="0" step="0.01" /></label>
                <label>Supplier<input name="purchase_supplier" /></label>
                <label className="form-span">Notes<textarea name="notes" rows={3} /></label>
                <div className="form-span"><button className="primary-button" type="submit">Save vehicle</button></div>
              </form>
            </details>
          </div>

          {dashboard.vehicles.length === 0 ? (
            <div className="empty-state"><strong>No vehicles registered yet.</strong><span>Use “Register vehicle” to begin the branch fleet.</span></div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Vehicle</th><th>Readiness</th><th>Documents</th><th>Service</th><th>Mechanical</th><th>Availability</th></tr></thead>
                <tbody>
                  {dashboard.vehicles.map((row) => (
                    <tr key={row.vehicle.id}>
                      <td>
                        <Link className="vehicle-link" href={`/fleet/vehicles/${row.vehicle.id}?branch=${selected.id}`}>
                          <strong>{row.vehicle.registration_plate}</strong>
                          <span>{row.vehicle.make} {row.vehicle.model} · {row.vehicle.vehicle_type}</span>
                        </Link>
                      </td>
                      <td><StatusPill level={row.readiness}>{row.readiness.toUpperCase()}</StatusPill></td>
                      <td><StatusPill level={row.documents.overall.level}>{row.documents.overall.label}</StatusPill></td>
                      <td><StatusPill level={row.service.level}>{row.service.label}</StatusPill></td>
                      <td><StatusPill level={row.mechanical.level}>{row.mechanical.label}</StatusPill></td>
                      <td><StatusPill level={row.availability.level}>{row.availability.label}</StatusPill></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-heading"><div><span className="eyebrow">Automatic alerts</span><h2>Actions requiring attention</h2></div><span className="count-badge">{dashboard.alerts.length}</span></div>
          {dashboard.alerts.length === 0 ? (
            <div className="empty-state"><strong>No fleet alerts.</strong><span>The decision engine has not found an exception.</span></div>
          ) : (
            <div className="alert-list">
              {dashboard.alerts.map((alert, index) => (
                <Link href={`/fleet/vehicles/${alert.vehicle_id}?branch=${selected.id}`} className={`alert-row alert-${alert.level}`} key={`${alert.vehicle_id}-${index}`}>
                  <StatusPill level={alert.level}>{alert.label}</StatusPill>
                  <strong>{alert.registration_plate}</strong>
                  <span>{alert.detail}</span>
                </Link>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
