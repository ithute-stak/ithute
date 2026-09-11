import Link from "next/link";
import { redirect } from "next/navigation";

import {
  addDocumentAction,
  addFaultAction,
  addInspectionAction,
  addServiceAction,
} from "../../actions";
import { ApiError, nbrosApi } from "@/lib/backend";

type Status = { level: "green" | "orange" | "red"; label: string; detail: string };
type VehicleProfile = {
  vehicle: {
    id: string;
    branch_id: string;
    registration_plate: string;
    make: string;
    model: string;
    vehicle_type: string;
    year: number | null;
    vin: string | null;
    engine_number: string | null;
    fuel_type: string | null;
    current_mileage: number;
    mechanical_condition: string;
  };
  decision: {
    readiness: "green" | "orange" | "red";
    documents: { overall: Status; items: Array<Status & { document_type?: string; document_number?: string | null; expiry_date?: string | null; file_url?: string | null }> };
    service: Status & { service_kit?: string | null };
    mechanical: Status;
    inspection: Status;
    availability: Status & { expected_available_at?: string | null; blockers: Status[] };
  };
  history: {
    documents: Array<{ id: string; type: string; number: string | null; issue_date: string | null; expiry_date: string | null; file_url: string | null }>;
    services: Array<{ id: string; date: string; mileage: number; type: string; cost: string | null; next_date: string | null; next_mileage: number | null; service_kit: string | null }>;
    faults: Array<{ id: string; severity: string; description: string; reported_at: string; resolved_at: string | null }>;
    inspections: Array<{ id: string; date: string; status: string; inspector: string | null; next_date: string | null }>;
    fuel: Array<{ id: string; recorded_at: string; mileage: number; litres: string; cost: string | null }>;
    accidents: Array<{ id: string; occurred_at: string; location: string | null; description: string; reference_number: string | null }>;
    assignments: Array<{ id: string; driver_id: string; purpose: string | null; start_at: string; end_at: string | null; status: string }>;
    trips: Array<{ id: string; driver_id: string; destination: string; start_at: string; expected_return_at: string | null; actual_return_at: string | null; status: string }>;
  };
};

function StatusCard({ title, status }: { title: string; status: Status }) {
  return (
    <article className={`decision-card decision-${status.level}`}>
      <span>{title}</span>
      <strong>{status.label}</strong>
      <small>{status.detail}</small>
    </article>
  );
}

export default async function VehiclePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ branch?: string }>;
}) {
  const { id } = await params;
  const query = await searchParams;
  if (!query.branch) redirect("/fleet");

  let profile: VehicleProfile;
  try {
    profile = await nbrosApi<VehicleProfile>(`/api/v1/fleet/vehicles/${id}?branch_id=${query.branch}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/api/auth/login");
    throw error;
  }

  const v = profile.vehicle;
  const d = profile.decision;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand"><span className="mini-mark">NB</span><strong>NBros</strong></div>
        <nav>
          <span className="nav-section">Modules</span>
          <Link href={`/fleet?branch=${v.branch_id}`} className="nav-item active">Fleet Management</Link>
        </nav>
      </aside>

      <main className="workspace">
        <header className="workspace-header">
          <div>
            <Link className="back-link" href={`/fleet?branch=${v.branch_id}`}>← Fleet dashboard</Link>
            <h1>{v.registration_plate}</h1>
            <p className="vehicle-subtitle">{v.make} {v.model} · {v.vehicle_type}</p>
          </div>
          <span className={`status-pill status-${d.readiness}`}>{d.readiness.toUpperCase()} READINESS</span>
        </header>

        <section className="decision-grid">
          <StatusCard title="Documents" status={d.documents.overall} />
          <StatusCard title="Service" status={d.service} />
          <StatusCard title="Mechanical" status={d.mechanical} />
          <StatusCard title="Inspection" status={d.inspection} />
          <StatusCard title="Availability" status={d.availability} />
        </section>

        <section className="panel">
          <div className="panel-heading"><div><span className="eyebrow">Vehicle profile</span><h2>Core details</h2></div></div>
          <dl className="detail-grid">
            <div><dt>Registration</dt><dd>{v.registration_plate}</dd></div>
            <div><dt>Make / model</dt><dd>{v.make} {v.model}</dd></div>
            <div><dt>Vehicle type</dt><dd>{v.vehicle_type}</dd></div>
            <div><dt>Year</dt><dd>{v.year ?? "—"}</dd></div>
            <div><dt>VIN / chassis</dt><dd>{v.vin ?? "—"}</dd></div>
            <div><dt>Engine number</dt><dd>{v.engine_number ?? "—"}</dd></div>
            <div><dt>Fuel type</dt><dd>{v.fuel_type ?? "—"}</dd></div>
            <div><dt>Current mileage</dt><dd>{v.current_mileage.toLocaleString()} km</dd></div>
          </dl>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <div><span className="eyebrow">Compliance</span><h2>Vehicle documents</h2></div>
            <details className="inline-details">
              <summary className="primary-button">Add document</summary>
              <form action={addDocumentAction} className="form-grid popup-form" encType="multipart/form-data">
                <input type="hidden" name="branch_id" value={v.branch_id} />
                <input type="hidden" name="vehicle_id" value={v.id} />
                <label>Document type<input name="document_type" required placeholder="Insurance" /></label>
                <label>Document number<input name="document_number" /></label>
                <label>Issue date<input type="date" name="issue_date" /></label>
                <label>Expiry date<input type="date" name="expiry_date" /></label>
                <label className="form-span">PDF / image<input type="file" name="file" accept=".pdf,.jpg,.jpeg,.png,.webp" /></label>
                <div className="form-span"><button className="primary-button">Save document</button></div>
              </form>
            </details>
          </div>
          <div className="document-grid">
            {d.documents.items.map((item, index) => (
              <article className="document-card" key={`${item.document_type}-${index}`}>
                <span className={`status-pill status-${item.level}`}>{item.label}</span>
                <strong>{item.document_type ?? "Document"}</strong>
                <small>{item.document_number ?? item.detail}</small>
                {item.expiry_date && <small>Expiry: {item.expiry_date}</small>}
                {item.file_url && <a className="document-file" href={item.file_url} target="_blank" rel="noreferrer">Open file</a>}
              </article>
            ))}
          </div>
        </section>

        <section className="two-column">
          <article className="panel">
            <div className="panel-heading">
              <div><span className="eyebrow">Maintenance</span><h2>Service history</h2></div>
              <details className="inline-details">
                <summary className="ghost-button">Record service</summary>
                <form action={addServiceAction} className="form-grid popup-form">
                  <input type="hidden" name="branch_id" value={v.branch_id} />
                  <input type="hidden" name="vehicle_id" value={v.id} />
                  <label>Service date<input type="date" name="service_date" required /></label>
                  <label>Mileage<input type="number" min="0" name="mileage" required /></label>
                  <label>Service type<input name="service_type" required /></label>
                  <label>Mechanic<input name="mechanic" /></label>
                  <label>Service kit<input name="service_kit" /></label>
                  <label>Cost<input type="number" min="0" step="0.01" name="cost" /></label>
                  <label>Next date<input type="date" name="next_service_date" /></label>
                  <label>Next mileage<input type="number" min="0" name="next_service_mileage" /></label>
                  <label className="form-span">Parts used<textarea name="parts_used" /></label>
                  <div className="form-span"><button className="primary-button">Save service</button></div>
                </form>
              </details>
            </div>
            <div className="history-list">
              {profile.history.services.map((item) => (
                <div key={item.id}><strong>{item.date} · {item.type}</strong><span>{item.mileage.toLocaleString()} km{item.cost ? ` · M ${item.cost}` : ""}</span></div>
              ))}
              {profile.history.services.length === 0 && <span className="muted">No service history recorded.</span>}
            </div>
          </article>

          <article className="panel">
            <div className="panel-heading">
              <div><span className="eyebrow">Mechanical</span><h2>Fault history</h2></div>
              <details className="inline-details">
                <summary className="ghost-button">Report fault</summary>
                <form action={addFaultAction} className="form-grid popup-form">
                  <input type="hidden" name="branch_id" value={v.branch_id} />
                  <input type="hidden" name="vehicle_id" value={v.id} />
                  <label>Severity<select name="severity" defaultValue="attention"><option value="attention">Requires attention</option><option value="critical">Critical / out of service</option></select></label>
                  <label className="form-span">Description<textarea name="description" required /></label>
                  <div className="form-span"><button className="primary-button">Record fault</button></div>
                </form>
              </details>
            </div>
            <div className="history-list">
              {profile.history.faults.map((item) => (
                <div key={item.id}><strong>{item.severity.toUpperCase()} · {item.description}</strong><span>{item.resolved_at ? "Resolved" : "Open"}</span></div>
              ))}
              {profile.history.faults.length === 0 && <span className="muted">No mechanical faults recorded.</span>}
            </div>
          </article>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <div><span className="eyebrow">Inspection</span><h2>Inspection history</h2></div>
            <details className="inline-details">
              <summary className="ghost-button">Record inspection</summary>
              <form action={addInspectionAction} className="form-grid popup-form">
                <input type="hidden" name="branch_id" value={v.branch_id} />
                <input type="hidden" name="vehicle_id" value={v.id} />
                <label>Date<input type="date" name="inspection_date" required /></label>
                <label>Status<select name="status" required><option value="passed">Passed</option><option value="attention">Attention</option><option value="failed">Failed</option></select></label>
                <label>Inspector<input name="inspector" /></label>
                <label>Next inspection<input type="date" name="next_inspection_date" /></label>
                <label className="form-span">Notes<textarea name="notes" /></label>
                <div className="form-span"><button className="primary-button">Save inspection</button></div>
              </form>
            </details>
          </div>
          <div className="history-list">
            {profile.history.inspections.map((item) => (
              <div key={item.id}><strong>{item.date} · {item.status.toUpperCase()}</strong><span>{item.inspector ?? "Inspector not recorded"}{item.next_date ? ` · next ${item.next_date}` : ""}</span></div>
            ))}
            {profile.history.inspections.length === 0 && <span className="muted">No inspection history recorded.</span>}
          </div>
        </section>
      </main>
    </div>
  );
}
