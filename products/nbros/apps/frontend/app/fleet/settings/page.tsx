import Link from "next/link";
import { redirect } from "next/navigation";

import {
  addDocumentRequirementAction,
  addLicenceRuleAction,
  addServiceKitRuleAction,
  updateFleetSettingsAction,
} from "../operational-actions";
import { ApiError, nbrosApi } from "@/lib/backend";

type SettingsView = {
  settings: { document_warning_days: number; document_critical_days: number; service_warning_days: number; service_mileage_warning: number };
  document_requirements: Array<{ id: string; document_type: string; vehicle_type: string | null; is_required: boolean; warning_days: number | null; critical_days: number | null }>;
  licence_rules: Array<{ id: string; vehicle_type: string; license_category: string }>;
  service_kit_rules: Array<{ id: string; make: string; model: string; service_type: string; kit_name: string }>;
};

export default async function SettingsPage({ searchParams }: { searchParams: Promise<{ branch?: string }> }) {
  const { branch } = await searchParams;
  if (!branch) redirect("/fleet");
  let view: SettingsView;
  try {
    view = await nbrosApi<SettingsView>(`/api/v1/fleet/settings?branch_id=${branch}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/api/auth/login");
    throw error;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar"><div className="sidebar-brand"><span className="mini-mark">NB</span><strong>NBros</strong></div><nav><span className="nav-section">Fleet</span><Link className="nav-item" href={`/fleet?branch=${branch}`}>Dashboard</Link><Link className="nav-item" href={`/fleet/drivers?branch=${branch}`}>Drivers</Link><Link className="nav-item" href={`/fleet/requests?branch=${branch}`}>Vehicle requests</Link><Link className="nav-item" href={`/fleet/operations?branch=${branch}`}>Operations</Link><Link className="nav-item active" href={`/fleet/settings?branch=${branch}`}>Settings</Link></nav></aside>
      <main className="workspace">
        <header className="workspace-header"><div><span className="eyebrow">Fleet administration</span><h1>Decision rules & settings</h1><p className="muted">Branch-specific thresholds and matching rules used by the deterministic decision engine.</p></div><Link className="ghost-button" href={`/fleet?branch=${branch}`}>Back to fleet</Link></header>

        <section className="panel"><div className="panel-heading"><div><span className="eyebrow">Thresholds</span><h2>Warnings & service forecast</h2></div></div><form action={updateFleetSettingsAction} className="form-grid"><input type="hidden" name="branch_id" value={branch}/><label>Document warning (days)<input name="document_warning_days" type="number" min="1" defaultValue={view.settings.document_warning_days}/></label><label>Document critical (days)<input name="document_critical_days" type="number" min="1" defaultValue={view.settings.document_critical_days}/></label><label>Service warning (days)<input name="service_warning_days" type="number" min="1" defaultValue={view.settings.service_warning_days}/></label><label>Service mileage warning (km)<input name="service_mileage_warning" type="number" min="0" defaultValue={view.settings.service_mileage_warning}/></label><div className="form-span"><button className="primary-button">Save thresholds</button></div></form></section>

        <section className="two-column">
          <article className="panel"><span className="eyebrow">Compliance</span><h2>Required documents</h2><div className="history-list">{view.document_requirements.map((row) => <div key={row.id}><strong>{row.document_type}</strong><span>{row.vehicle_type ? `Vehicle type: ${row.vehicle_type}` : "All vehicle types"}{row.warning_days ? ` · warn ${row.warning_days}d` : ""}</span></div>)}</div><hr/><form action={addDocumentRequirementAction} className="form-grid"><input type="hidden" name="branch_id" value={branch}/><label>Document type<input name="document_type" required/></label><label>Vehicle type<input name="vehicle_type" placeholder="Optional"/></label><label>Warning days<input name="warning_days" type="number" min="1"/></label><label>Critical days<input name="critical_days" type="number" min="1"/></label><div className="form-span"><button className="ghost-button">Add requirement</button></div></form></article>

          <article className="panel"><span className="eyebrow">Driver validation</span><h2>Licence-category rules</h2><div className="history-list">{view.licence_rules.length === 0 ? <span className="muted">No category restrictions configured yet.</span> : view.licence_rules.map((row) => <div key={row.id}><strong>{row.vehicle_type}</strong><span>Allowed licence: {row.license_category}</span></div>)}</div><hr/><form action={addLicenceRuleAction} className="form-grid"><input type="hidden" name="branch_id" value={branch}/><label>Vehicle type<input name="vehicle_type" required/></label><label>Licence category<input name="license_category" required/></label><div className="form-span"><button className="ghost-button">Add licence rule</button></div></form></article>
        </section>

        <section className="panel"><span className="eyebrow">Service forecasting</span><h2>Service-kit rules</h2><div className="table-wrap"><table><thead><tr><th>Make</th><th>Model</th><th>Service type</th><th>Required kit</th></tr></thead><tbody>{view.service_kit_rules.map((row) => <tr key={row.id}><td>{row.make}</td><td>{row.model}</td><td>{row.service_type}</td><td>{row.kit_name}</td></tr>)}</tbody></table></div><form action={addServiceKitRuleAction} className="form-grid top-gap"><input type="hidden" name="branch_id" value={branch}/><label>Make<input name="make" required/></label><label>Model<input name="model" required/></label><label>Service type<input name="service_type" required/></label><label>Service kit<input name="kit_name" required/></label><div className="form-span"><button className="ghost-button">Add service-kit rule</button></div></form></section>
      </main>
    </div>
  );
}
