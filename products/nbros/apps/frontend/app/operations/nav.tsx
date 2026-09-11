import Link from "next/link";

export default function OperationsNav({ branchId, active }: { branchId: string; active: string }) {
  const query = `branch=${branchId}`;
  const item = (key: string, href: string, label: string) => (
    <Link className={`nav-item${active === key ? " active" : ""}`} href={`${href}?${query}`}>{label}</Link>
  );
  return (
    <aside className="sidebar">
      <div className="sidebar-brand"><span className="mini-mark">NB</span><strong>NBros</strong></div>
      <nav>
        <span className="nav-section">Operations</span>
        {item("command", "/operations", "Command centre")}
        {item("workshop", "/operations/workshop", "Workshop")}
        {item("stores", "/operations/stores", "Stores & procurement")}
        {item("dispatch", "/operations/dispatch", "Dispatch")}
        {item("assets", "/operations/assets", "Tyres, claims & telematics")}
        <span className="nav-section">Fleet</span>
        <Link className="nav-item" href={`/fleet?${query}`}>Fleet dashboard</Link>
        <Link className="nav-item" href={`/fleet/reports?${query}`}>Fleet reports</Link>
      </nav>
      <div className="sidebar-footer">Nthane Brothers</div>
    </aside>
  );
}
