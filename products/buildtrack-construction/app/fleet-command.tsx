"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type Tone = "green" | "amber" | "red";
type Readiness = {
  documents: { tone: Tone; label: string };
  service: { tone: Tone; label: string; nextDate?: string | null; nextMileage?: number | null; kit?: string };
  mechanical: { tone: Tone; label: string; detail?: string };
  inspection: { tone: Tone; label: string };
  availability: { tone: Tone; label: string; blockers: string[]; releaseDate?: string | null };
  documentRows: Array<{ type: string; tone: Tone; label: string; days: number | null }>;
  score: number;
};
type Asset = { id: number; asset_no: string; description: string; registration?: string; type: string; odometer: number; make?: string; model?: string; branch?: string; readiness: Readiness; documents: unknown[]; services: unknown[]; faults: unknown[]; inspections: unknown[]; assignments: unknown[]; fuel: unknown[]; maintenance: unknown[] };
type FleetData = { assets: Asset[]; alerts: Array<{ assetId: number; asset: string; label: string; tone: Tone }>; requests: Array<Record<string, string>>; requiredDocuments: string[] };

const formLabels: Record<string, string> = {
  asset: "Register vehicle or plant", document: "Add compliance document", service: "Record service", fault: "Report mechanical condition", inspection: "Record inspection", assignment: "Allocate vehicle", request: "Request vehicle", fuel: "Record fuel",
};

const fields: Record<string, Array<[string, string, string?]>> = {
  asset: [["assetNo", "Asset number", "FLT-001"], ["description", "Vehicle or plant description", "Toyota Hilux 2.4 GD-6"], ["registration", "Registration / number plate", "B 0000"], ["type", "Asset type", "Vehicle, plant or equipment"], ["make", "Make", "Toyota"], ["model", "Model", "Hilux"], ["year", "Year", "2026"], ["vin", "VIN / chassis number"], ["engineNumber", "Engine number"], ["fuelType", "Fuel type", "Diesel"], ["branch", "Branch / base"], ["purchaseInfo", "Purchase information"], ["odometer", "Current mileage / hours", "0"], ["warningDays", "Expiry warning days", "30"], ["serviceWarningKm", "Mileage warning interval", "500"]],
  document: [["assetId", "Asset ID", "Choose from register"], ["documentType", "Document type", "Insurance, Disc, Permit…"], ["documentNumber", "Document number"], ["issueDate", "Issue date", "date"], ["expiryDate", "Expiry date", "date"], ["fileName", "Uploaded file reference"]],
  service: [["assetId", "Asset ID"], ["serviceDate", "Service date", "date"], ["mileage", "Mileage / hours"], ["serviceType", "Service type", "Scheduled service"], ["partsUsed", "Parts used"], ["serviceKit", "Service kit / parts requirement"], ["mechanic", "Mechanic / workshop"], ["costM", "Service cost M"], ["nextServiceDate", "Next service date", "date"], ["nextServiceMileage", "Next service mileage"]],
  fault: [["assetId", "Asset ID"], ["reportedAt", "Reported date", "date"], ["severity", "Severity", "Requires attention or Critical"], ["description", "Fault / mechanical condition"]],
  inspection: [["assetId", "Asset ID"], ["inspectionDate", "Inspection date", "date"], ["result", "Result", "Passed or Failed"], ["inspector", "Inspector"], ["notes", "Notes"], ["nextDueDate", "Next inspection due", "date"]],
  assignment: [["assetId", "Asset ID"], ["driverName", "Driver"], ["licenceNumber", "Licence number"], ["licenceCategory", "Licence category"], ["purpose", "Purpose / reason"], ["destination", "Destination"], ["startDate", "Start date", "date"], ["expectedReturnDate", "Expected return", "date"], ["status", "Allocation status", "Active or Reserved"]],
  request: [["driverName", "Driver"], ["licenceNumber", "Licence number"], ["licenceCategory", "Licence category"], ["vehicleType", "Vehicle type requested"], ["purpose", "Purpose / reason"], ["destination", "Destination"], ["requiredDate", "Required date", "date"], ["expectedReturnDate", "Expected return", "date"]],
  fuel: [["assetId", "Asset ID"], ["fillDate", "Fill date", "date"], ["litres", "Litres"], ["costM", "Fuel cost M"], ["odometer", "Odometer / hours"]],
};

function inputType(hint?: string) { return hint === "date" ? "date" : ["year", "mileage", "odometer", "cost", "days", "interval", "litres"].some((word) => (hint ?? "").toLowerCase().includes(word)) ? "number" : "text"; }

export function FleetCommand() {
  const [data, setData] = useState<FleetData | null>(null);
  const [form, setForm] = useState<string | null>(null);
  const [selected, setSelected] = useState<Asset | null>(null);
  const [message, setMessage] = useState("");
  const load = () => fetch("/api/fleet").then((response) => response.json()).then((payload) => { if (payload.error) throw new Error(payload.error); setData(payload); }).catch((error) => setMessage(error.message || "Fleet data is unavailable."));
  useEffect(load, []);
  const summary = useMemo(() => ({ available: data?.assets.filter((asset) => asset.readiness.availability.label === "AVAILABLE").length ?? 0, attention: data?.alerts.length ?? 0, unavailable: data?.assets.filter((asset) => asset.readiness.availability.tone === "red").length ?? 0 }), [data]);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form) return;
    const data = Object.fromEntries(new FormData(event.currentTarget).entries());
    try {
      const response = await fetch("/api/fleet", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ action: form, data }) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Unable to save fleet record.");
      setMessage("Fleet record saved. Readiness decisions have been updated.");
      setForm(null); load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to save fleet record."); }
  };
  return <><div className="fleet-command-head"><div><p className="eyebrow">Fleet decision engine</p><h1>Fleet and plant readiness</h1><p>Every asset is checked against compliance, service, mechanical condition, inspection and allocation before it can be released.</p></div><div className="fleet-actions"><button className="button button-secondary" onClick={() => setForm("request")}>Request vehicle</button><button className="button button-primary" onClick={() => setForm("asset")}>+ Register asset</button></div></div><div className="fleet-metrics"><Metric label="Available now" value={summary.available} detail="Passed all readiness checks" icon="●"/><Metric label="Unavailable" value={summary.unavailable} detail="Blocked from release" icon="!"/><Metric label="Attention alerts" value={summary.attention} detail="Compliance, service or condition" icon="△" warning/><Metric label="Vehicle requests" value={data?.requests.length ?? 0} detail="Awaiting allocation decision" icon="↗"/></div><div className="fleet-toolbar"><button onClick={() => setForm("document")}>Compliance document</button><button onClick={() => setForm("service")}>Record service</button><button onClick={() => setForm("fault")}>Report fault</button><button onClick={() => setForm("inspection")}>Inspection</button><button onClick={() => setForm("assignment")}>Allocate asset</button><button onClick={() => setForm("fuel")}>Fuel log</button></div>{message ? <p className="fleet-message">{message}</p> : null}<section className="surface table-surface"><div className="surface-heading"><div><p className="eyebrow">Asset register</p><h2>Operational release decisions</h2></div><span className="fleet-caption">Select an asset for its complete history</span></div><div className="table-scroll"><table><thead><tr><th>Asset</th><th>Readiness</th><th>Documents</th><th>Service</th><th>Mechanical</th><th>Availability</th><th/></tr></thead><tbody>{(data?.assets ?? []).map((asset) => <tr key={asset.id}><td><strong>{asset.description}</strong><span>{asset.asset_no} · {asset.registration || asset.type}</span></td><td><Status tone={asset.readiness.score >= 8 ? "green" : asset.readiness.score >= 4 ? "amber" : "red"}>{asset.readiness.score}/10</Status></td><td><Status tone={asset.readiness.documents.tone}>{asset.readiness.documents.label}</Status></td><td><Status tone={asset.readiness.service.tone}>{asset.readiness.service.label}</Status></td><td><Status tone={asset.readiness.mechanical.tone}>{asset.readiness.mechanical.label}</Status></td><td><Status tone={asset.readiness.availability.tone}>{asset.readiness.availability.label}</Status></td><td><button className="row-menu" onClick={() => setSelected(asset)} aria-label={"Open " + asset.asset_no}>Open</button></td></tr>)}</tbody></table></div>{!data?.assets.length ? <p className="fleet-empty">Register the first Nthane Brothers vehicle or plant item to begin compliance and availability control.</p> : null}</section><section className="fleet-alerts"><div><p className="eyebrow">Action queue</p><h2>What needs attention</h2></div><div>{(data?.alerts ?? []).length ? data?.alerts.map((alert, index) => <p key={index}><Status tone={alert.tone}>{alert.label}</Status><span>{alert.asset}</span></p>) : <p><Status tone="green">CLEAR</Status><span>No fleet compliance, service, mechanical or inspection alerts.</span></p>}</div></section>{form ? <FleetForm kind={form} assets={data?.assets ?? []} onClose={() => setForm(null)} onSubmit={submit}/> : null}{selected ? <AssetHistory asset={selected} onClose={() => setSelected(null)}/> : null}</>;
}

function FleetForm({ kind, assets, onClose, onSubmit }: { kind: string; assets: Asset[]; onClose: () => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  return <div className="drawer-backdrop"><aside className="record-drawer fleet-drawer"><div className="drawer-head"><div><p className="eyebrow">Fleet control</p><h2>{formLabels[kind]}</h2><p>All decisions remain traceable to this underlying record.</p></div><button onClick={onClose} aria-label="Close">×</button></div><form onSubmit={onSubmit}>{fields[kind].map(([name, label, hint]) => <label key={name}>{label}{name === "assetId" ? <select name={name} required><option value="">Choose asset</option>{assets.map((asset) => <option value={asset.id} key={asset.id}>{asset.asset_no} — {asset.description}</option>)}</select> : <input name={name} type={inputType(label + " " + hint)} required={["assetNo","description","documentType","serviceType","driverName","vehicleType","requiredDate","severity","fault"].some((key) => name.toLowerCase().includes(key.toLowerCase()))} placeholder={hint === "date" ? "" : hint || ""}/>}</label>)}<div className="drawer-actions"><button type="button" className="button button-secondary" onClick={onClose}>Cancel</button><button type="submit" className="button button-primary">Save record</button></div></form></aside></div>;
}

function AssetHistory({ asset, onClose }: { asset: Asset; onClose: () => void }) {
  const readiness = asset.readiness;
  return <div className="drawer-backdrop"><aside className="record-drawer fleet-history"><div className="drawer-head"><div><p className="eyebrow">{asset.asset_no}</p><h2>{asset.description}</h2><p>{asset.registration || asset.type} · {asset.odometer.toLocaleString()} km / hours</p></div><button onClick={onClose} aria-label="Close">×</button></div><div className="fleet-history-body"><h3>Vehicle readiness</h3><Readiness label="Documents" item={readiness.documents}/><Readiness label="Service" item={readiness.service}/><Readiness label="Mechanical" item={readiness.mechanical}/><Readiness label="Inspection" item={readiness.inspection}/><Readiness label="Availability" item={readiness.availability}/><h3>Document register</h3>{readiness.documentRows.map((row) => <p className="fleet-history-row" key={row.type}><span>{row.type}</span><Status tone={row.tone}>{row.label}{row.days !== null ? ` · ${row.days} days` : ""}</Status></p>)}<h3>Traceable history</h3><p className="fleet-history-row"><span>Services recorded</span><b>{asset.services.length}</b></p><p className="fleet-history-row"><span>Open faults</span><b>{asset.faults.length}</b></p><p className="fleet-history-row"><span>Inspections</span><b>{asset.inspections.length}</b></p><p className="fleet-history-row"><span>Fuel transactions</span><b>{asset.fuel.length}</b></p><p className="fleet-history-row"><span>Maintenance records</span><b>{asset.maintenance.length}</b></p>{readiness.availability.blockers.length ? <p className="fleet-blockers"><b>Release blocked by:</b> {readiness.availability.blockers.join(", ")}{readiness.availability.releaseDate ? ` · expected release ${readiness.availability.releaseDate}` : ""}</p> : null}</div></aside></div>;
}

function Readiness({ label, item }: { label: string; item: { tone: Tone; label: string } }) { return <p className="fleet-history-row"><span>{label}</span><Status tone={item.tone}>{item.label}</Status></p>; }
function Status({ tone, children }: { tone: Tone; children: React.ReactNode }) { return <span className={"status status-" + tone}>{children}</span>; }
function Metric({ label, value, detail, icon, warning }: { label: string; value: string | number; detail: string; icon: string; warning?: boolean }) { return <article className={"metric " + (warning ? "metric-warning" : "")}><div className="metric-top"><span>{label}</span><i>{icon}</i></div><strong>{value}</strong><small>{detail}</small></article>; }
