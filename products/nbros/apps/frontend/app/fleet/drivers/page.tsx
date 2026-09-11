import Link from "next/link";
import { redirect } from "next/navigation";

import { createDriverAction } from "../operational-actions";
import { ApiError, nbrosApi } from "@/lib/backend";

type Driver = {
  id: string;
  full_name: string;
  employee_number: string | null;
  license_number: string;
  license_category: string;
  license_expiry: string;
  is_active: boolean;
};

export default async function DriversPage({ searchParams }: { searchParams: Promise<{ branch?: string }> }) {
  const { branch } = await searchParams;
  if (!branch) redirect("/fleet");

  let drivers: Driver[];
  try {
    drivers = await nbrosApi<Driver[]>(`/api/v1/fleet/drivers?branch_id=${branch}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/api/auth/login");
    throw error;
  }

  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand"><span className="mini-mark">NB</span><strong>NBros</strong></div>
        <nav>
          <span className="nav-section">Fleet</span>
          <Link className="nav-item" href={`/fleet?branch=${branch}`}>Dashboard</Link>
          <Link className="nav-item active" href={`/fleet/drivers?branch=${branch}`}>Drivers</Link>
          <Link className="nav-item" href={`/fleet/requests?branch=${branch}`}>Vehicle requests</Link>
          <Link className="nav-item" href={`/fleet/operations?branch=${branch}`}>Operations</Link>
          <Link className="nav-item" href={`/fleet/settings?branch=${branch}`}>Settings</Link>
        </nav>
      </aside>
      <main className="workspace">
        <header className="workspace-header">
          <div><span className="eyebrow">Fleet Management</span><h1>Drivers</h1><p className="muted">Driver licences and categories are validated before vehicle matching.</p></div>
          <Link className="ghost-button" href={`/fleet?branch=${branch}`}>Back to fleet</Link>
        </header>

        <section className="panel">
          <div className="panel-heading"><div><span className="eyebrow">Driver register</span><h2>Registered drivers</h2></div></div>
          <form action={createDriverAction} className="form-grid compact-form">
            <input type="hidden" name="branch_id" value={branch} />
            <label>Full name<input name="full_name" required /></label>
            <label>Employee number<input name="employee_number" /></label>
            <label>Licence number<input name="license_number" required /></label>
            <label>Licence category<input name="license_category" required placeholder="B" /></label>
            <label>Licence expiry<input name="license_expiry" type="date" required /></label>
            <div className="form-span"><button className="primary-button">Register driver</button></div>
          </form>
        </section>

        <section className="panel">
          {drivers.length === 0 ? <div className="empty-state"><strong>No drivers registered.</strong><span>Add the first branch driver above.</span></div> : (
            <div className="table-wrap"><table>
              <thead><tr><th>Driver</th><th>Employee</th><th>Licence</th><th>Category</th><th>Expiry</th><th>Status</th></tr></thead>
              <tbody>{drivers.map((driver) => {
                const expired = driver.license_expiry < today;
                return <tr key={driver.id}>
                  <td><strong>{driver.full_name}</strong></td>
                  <td>{driver.employee_number ?? "—"}</td>
                  <td>{driver.license_number}</td>
                  <td>{driver.license_category}</td>
                  <td>{driver.license_expiry}</td>
                  <td><span className={`status-pill status-${!driver.is_active || expired ? "red" : "green"}`}>{!driver.is_active ? "INACTIVE" : expired ? "EXPIRED" : "VALID"}</span></td>
                </tr>;
              })}</tbody>
            </table></div>
          )}
        </section>
      </main>
    </div>
  );
}
