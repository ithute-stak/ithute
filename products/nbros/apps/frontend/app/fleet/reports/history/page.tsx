import Link from "next/link";
import { redirect } from "next/navigation";
import { ApiError, nbrosApi } from "@/lib/backend";

type History = { vehicle: { registration_plate: string; make: string; model: string; vehicle_type: string }; events: Array<{ kind: string; at: string; title: string; detail: string; resolved_at?: string | null }> };

export default async function VehicleHistoryPage({ searchParams }: { searchParams: Promise<{ branch?: string; vehicle?: string }> }) {
  const { branch, vehicle } = await searchParams;
  if (!branch || !vehicle) redirect("/fleet");
  let history: History;
  try { history = await nbrosApi<History>(`/api/v1/fleet/reports/vehicle-history?branch_id=${branch}&vehicle_id=${vehicle}`); }
  catch (error) { if (error instanceof ApiError && error.status === 401) redirect("/api/auth/login"); throw error; }
  return <div className="app-shell"><aside className="sidebar"><div className="sidebar-brand"><span className="mini-mark">NB</span><strong>NBros</strong></div><nav><span className="nav-section">Fleet</span><Link className="nav-item" href={`/fleet?branch=${branch}`}>Dashboard</Link><Link className="nav-item active" href={`/fleet/reports?branch=${branch}`}>Reports</Link></nav></aside><main className="workspace"><header className="workspace-header"><div><span className="eyebrow">Complete Fleet history</span><h1>{history.vehicle.registration_plate}</h1><p className="muted">{history.vehicle.make} {history.vehicle.model} · {history.vehicle.vehicle_type}</p></div><Link className="ghost-button" href={`/fleet/reports?branch=${branch}`}>Back to reports</Link></header><section className="panel"><div className="panel-heading"><div><span className="eyebrow">Traceable timeline</span><h2>All recorded Fleet events</h2></div><span className="count-badge">{history.events.length}</span></div>{history.events.length === 0 ? <div className="empty-state"><strong>No history recorded.</strong><span>Fleet records will appear here as they are added.</span></div> : <div className="history-list">{history.events.map((event, index) => <div key={`${event.at}-${event.kind}-${index}`}><strong>{event.kind.toUpperCase()} · {event.title}</strong><span>{event.detail}</span><small className="muted">{new Date(event.at).toLocaleString()}{event.resolved_at ? ` · resolved ${new Date(event.resolved_at).toLocaleString()}` : ""}</small></div>)}</div>}</section></main></div>;
}
