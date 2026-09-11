import Link from "next/link";
import { redirect } from "next/navigation";

import { ApiError, nbrosApi } from "@/lib/backend";

type Driver = { id: string; full_name: string; license_category: string; license_expiry: string };
type MatchResult = {
  recommended: null | { vehicle: { id: string; registration_plate: string; make: string; model: string; vehicle_type: string; current_mileage: number }; readiness: string; score: number };
  available: Array<{ vehicle: { id: string; registration_plate: string; make: string; model: string; vehicle_type: string; current_mileage: number }; readiness: string; score: number }>;
  excluded: Array<{ vehicle_id: string; registration_plate: string; reasons: string[]; expected_available_at: string | null }>;
  driver_error: string | null;
  next_expected_availability: string | null;
};

export default async function RequestsPage({
  searchParams,
}: {
  searchParams: Promise<{ branch?: string; vehicle_type?: string; start_at?: string; end_at?: string; driver_id?: string }>;
}) {
  const query = await searchParams;
  if (!query.branch) redirect("/fleet");
  const branch = query.branch;
  let drivers: Driver[];
  try {
    drivers = await nbrosApi<Driver[]>(`/api/v1/fleet/drivers?branch_id=${branch}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/api/auth/login");
    throw error;
  }

  let result: MatchResult | null = null;
  if (query.vehicle_type && query.start_at && query.end_at) {
    result = await nbrosApi<MatchResult>("/api/v1/fleet/match", {
      method: "POST",
      body: JSON.stringify({
        branch_id: branch,
        vehicle_type: query.vehicle_type,
        start_at: query.start_at,
        end_at: query.end_at,
        driver_id: query.driver_id || null,
      }),
    });
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand"><span className="mini-mark">NB</span><strong>NBros</strong></div>
        <nav>
          <span className="nav-section">Fleet</span>
          <Link className="nav-item" href={`/fleet?branch=${branch}`}>Dashboard</Link>
          <Link className="nav-item" href={`/fleet/drivers?branch=${branch}`}>Drivers</Link>
          <Link className="nav-item active" href={`/fleet/requests?branch=${branch}`}>Vehicle requests</Link>
          <Link className="nav-item" href={`/fleet/operations?branch=${branch}`}>Operations</Link>
          <Link className="nav-item" href={`/fleet/settings?branch=${branch}`}>Settings</Link>
        </nav>
      </aside>

      <main className="workspace">
        <header className="workspace-header">
          <div><span className="eyebrow">Decision engine</span><h1>Vehicle request & matching</h1><p className="muted">The system validates the driver, removes conflicting or unsafe vehicles, then recommends the best match.</p></div>
          <Link className="ghost-button" href={`/fleet?branch=${branch}`}>Back to fleet</Link>
        </header>

        <section className="panel">
          <form method="get" className="form-grid">
            <input type="hidden" name="branch" value={branch} />
            <label>Vehicle type<input name="vehicle_type" required defaultValue={query.vehicle_type ?? ""} placeholder="Toyota Land Cruiser" /></label>
            <label>Driver<select name="driver_id" defaultValue={query.driver_id ?? ""}><option value="">No driver selected</option>{drivers.map((driver) => <option value={driver.id} key={driver.id}>{driver.full_name} · {driver.license_category}</option>)}</select></label>
            <label>Required from<input type="datetime-local" name="start_at" required defaultValue={query.start_at ?? ""} /></label>
            <label>Expected return<input type="datetime-local" name="end_at" required defaultValue={query.end_at ?? ""} /></label>
            <div className="form-span"><button className="primary-button">Find suitable vehicle</button></div>
          </form>
        </section>

        {result && <>
          {result.driver_error ? (
            <section className="panel decision-red"><span className="eyebrow">Driver validation</span><h2>Request cannot proceed</h2><p>{result.driver_error}</p></section>
          ) : result.recommended ? (
            <section className="panel recommendation-panel">
              <span className="eyebrow">Recommended vehicle</span>
              <h2>{result.recommended.vehicle.registration_plate} · {result.recommended.vehicle.make} {result.recommended.vehicle.model}</h2>
              <p className="muted">Readiness: {result.recommended.readiness.toUpperCase()} · Mileage: {result.recommended.vehicle.current_mileage.toLocaleString()} km</p>
              <Link className="primary-button" href={`/fleet/vehicles/${result.recommended.vehicle.id}?branch=${branch}`}>Open vehicle profile</Link>
            </section>
          ) : (
            <section className="panel decision-red">
              <span className="eyebrow">No vehicle available</span>
              <h2>No suitable {query.vehicle_type} is available for this period.</h2>
              <p>{result.next_expected_availability ? `Next recorded expected availability: ${result.next_expected_availability}` : "No reliable future release date is currently recorded."}</p>
            </section>
          )}

          <section className="two-column">
            <article className="panel">
              <div className="panel-heading"><div><span className="eyebrow">Eligible</span><h2>Available matches</h2></div><span className="count-badge">{result.available.length}</span></div>
              <div className="history-list">{result.available.length === 0 ? <span className="muted">No eligible vehicles.</span> : result.available.map((row) => <div key={row.vehicle.id}><strong>{row.vehicle.registration_plate} · {row.vehicle.make} {row.vehicle.model}</strong><span>{row.readiness.toUpperCase()} · {row.vehicle.current_mileage.toLocaleString()} km</span></div>)}</div>
            </article>
            <article className="panel">
              <div className="panel-heading"><div><span className="eyebrow">Excluded</span><h2>Why vehicles are unavailable</h2></div><span className="count-badge">{result.excluded.length}</span></div>
              <div className="history-list">{result.excluded.length === 0 ? <span className="muted">No exclusions.</span> : result.excluded.map((row) => <div key={row.vehicle_id}><strong>{row.registration_plate}</strong><span>{row.reasons.join(" · ")}{row.expected_available_at ? ` · expected ${row.expected_available_at}` : ""}</span></div>)}</div>
            </article>
          </section>
        </>}
      </main>
    </div>
  );
}
