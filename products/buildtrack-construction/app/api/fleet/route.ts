import { env } from "cloudflare:workers";
import { getChatGPTUser } from "../../chatgpt-auth";

const now = () => new Date().toISOString();
const text = (value: unknown) => String(value ?? "").trim();
const number = (value: unknown) => Number(value) || 0;
const json = (body: unknown, init?: ResponseInit) => Response.json(body, init);
const requiredDocuments = ["Vehicle certificate", "Disc", "Insurance", "Operating permit", "Roadworthiness / inspection"];

function database(): D1Database {
  if (!env.DB) throw new Error("The BuildTrack data store is not available.");
  return env.DB;
}

async function workspace() {
  const user = await getChatGPTUser();
  if (!user) return null;
  const db = database();
  const timestamp = now();
  let company = await db.prepare("SELECT id FROM companies ORDER BY id LIMIT 1").first<{ id: number }>();
  if (!company) {
    await db.prepare("INSERT INTO companies (name, country, currency, created_at, updated_at) VALUES (?, ?, ?, ?, ?)").bind("Nthane Brothers", "Lesotho", "LSL", timestamp, timestamp).run();
    company = await db.prepare("SELECT id FROM companies ORDER BY id LIMIT 1").first<{ id: number }>();
  }
  if (!company) throw new Error("Unable to prepare the company workspace.");
  await db.prepare("INSERT INTO users (company_id, email, full_name, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(email) DO UPDATE SET full_name = excluded.full_name, updated_at = excluded.updated_at").bind(company.id, user.email, user.fullName, "Administrator", 1, timestamp, timestamp).run();
  return { db, companyId: company.id, user };
}

function daysUntil(value: string | null | undefined) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return null;
  return Math.ceil((date.valueOf() - Date.now()) / 86400000);
}

function deadlineStatus(value: string | null | undefined, warningDays: number) {
  const days = daysUntil(value);
  if (days === null) return { tone: "red", label: "MISSING", days };
  if (days < 0) return { tone: "red", label: "EXPIRED", days };
  if (days <= Math.max(7, Math.floor(warningDays / 3))) return { tone: "red", label: "CRITICAL", days };
  if (days <= warningDays) return { tone: "amber", label: "EXPIRES SOON", days };
  return { tone: "green", label: "VALID", days };
}

function readiness(asset: Record<string, any>, documents: Record<string, any>[], services: Record<string, any>[], faults: Record<string, any>[], inspections: Record<string, any>[], assignments: Record<string, any>[]) {
  const warningDays = number(asset.warning_days) || 30;
  const documentRows = requiredDocuments.map((type) => {
    const row = documents.find((entry) => entry.document_type === type);
    return { type, ...deadlineStatus(row?.expiry_date, warningDays), record: row ?? null };
  });
  const expired = documentRows.filter((row) => row.label === "EXPIRED" || row.label === "MISSING");
  const expiring = documentRows.filter((row) => row.label === "EXPIRES SOON" || row.label === "CRITICAL");
  const documentsState = expired.length ? { tone: "red", label: expired.some((row) => row.label === "MISSING") ? "DOCUMENTS INCOMPLETE" : "DOCUMENTS EXPIRED" } : expiring.length ? { tone: "amber", label: "DOCUMENTS EXPIRING SOON" } : { tone: "green", label: "DOCUMENTS VALID" };
  const latestService = services[0];
  const serviceDate = latestService?.next_service_date ?? asset.next_service_date;
  const serviceMileage = number(latestService?.next_service_mileage ?? asset.next_service_mileage);
  const serviceByDate = deadlineStatus(serviceDate, warningDays);
  const serviceByMileage = serviceMileage && number(asset.odometer) >= serviceMileage ? { tone: "red", label: "OVERDUE" } : serviceMileage && number(asset.odometer) >= serviceMileage - number(asset.service_warning_km || 500) ? { tone: "amber", label: "DUE SOON" } : null;
  const serviceState = serviceByDate.label === "MISSING" ? { tone: "amber", label: "SERVICE PLAN REQUIRED" } : serviceByDate.label === "EXPIRED" || serviceByDate.label === "CRITICAL" || serviceByMileage?.tone === "red" ? { tone: "red", label: "SERVICE OVERDUE" } : serviceByDate.tone === "amber" || serviceByMileage?.tone === "amber" ? { tone: "amber", label: "SERVICE DUE SOON" } : { tone: "green", label: "SERVICE CURRENT" };
  const activeFault = faults.find((fault) => fault.status !== "Resolved");
  const mechanical = activeFault?.severity === "Critical" || asset.mechanical_status === "Out of service" ? { tone: "red", label: "OUT OF SERVICE", detail: activeFault?.description ?? asset.fault_notes } : activeFault || asset.mechanical_status === "Requires attention" ? { tone: "amber", label: "REQUIRES ATTENTION", detail: activeFault?.description ?? asset.fault_notes } : { tone: "green", label: "OPERATIONAL", detail: "" };
  const latestInspection = inspections[0];
  const inspectionDeadline = deadlineStatus(latestInspection?.next_due_date ?? asset.inspection_due_date, warningDays);
  const inspection = latestInspection?.result === "Failed" ? { tone: "red", label: "INSPECTION FAILED" } : inspectionDeadline.label === "MISSING" ? { tone: "amber", label: "INSPECTION PLAN REQUIRED" } : inspectionDeadline.tone === "red" ? { tone: "red", label: "INSPECTION OVERDUE" } : inspectionDeadline.tone === "amber" ? { tone: "amber", label: "INSPECTION DUE SOON" } : { tone: "green", label: "INSPECTION CURRENT" };
  const activeAssignment = assignments.find((entry) => entry.status === "Active" || entry.status === "Reserved");
  const blockers = [
    ...(documentsState.tone === "red" ? [documentsState.label] : []),
    ...(serviceState.tone === "red" ? [serviceState.label] : []),
    ...(mechanical.tone === "red" ? [mechanical.label] : []),
    ...(inspection.tone === "red" ? [inspection.label] : []),
    ...(activeAssignment ? [activeAssignment.status === "Reserved" ? "RESERVED" : "ASSIGNED"] : []),
  ];
  const releaseDate = activeAssignment?.expected_return_date ?? activeAssignment?.end_date ?? null;
  const availability = blockers.length ? { tone: "red", label: "NOT AVAILABLE", blockers, releaseDate } : activeAssignment ? { tone: "amber", label: "RESERVED", blockers: ["RESERVED"], releaseDate } : { tone: "green", label: "AVAILABLE", blockers: [], releaseDate: null };
  return { documents: documentsState, documentRows, service: { ...serviceState, nextDate: serviceDate, nextMileage: serviceMileage || null, kit: latestService?.service_kit ?? "" }, mechanical, inspection, availability, score: (documentsState.tone === "green" ? 4 : 0) + (serviceState.tone === "green" ? 3 : 0) + (mechanical.tone === "green" ? 2 : 0) + (inspection.tone === "green" ? 1 : 0) };
}

export async function GET() {
  try {
    const current = await workspace();
    if (!current) return json({ error: "Sign in is required." }, { status: 401 });
    const { db, companyId } = current;
    const [assets, documents, services, faults, inspections, assignments, requests, fuel, maintenance] = await db.batch([
      db.prepare("SELECT * FROM fleet_assets WHERE company_id = ? ORDER BY asset_no").bind(companyId),
      db.prepare("SELECT * FROM fleet_documents WHERE company_id = ? ORDER BY expiry_date").bind(companyId),
      db.prepare("SELECT * FROM fleet_services WHERE company_id = ? ORDER BY service_date DESC").bind(companyId),
      db.prepare("SELECT * FROM fleet_faults WHERE company_id = ? ORDER BY reported_at DESC").bind(companyId),
      db.prepare("SELECT * FROM fleet_inspections WHERE company_id = ? ORDER BY inspection_date DESC").bind(companyId),
      db.prepare("SELECT * FROM fleet_assignments WHERE company_id = ? AND status IN ('Active','Reserved') ORDER BY expected_return_date").bind(companyId),
      db.prepare("SELECT * FROM fleet_requests WHERE company_id = ? ORDER BY required_date DESC").bind(companyId),
      db.prepare("SELECT * FROM fuel_logs WHERE company_id = ? ORDER BY fill_date DESC").bind(companyId),
      db.prepare("SELECT * FROM maintenance_records WHERE company_id = ? ORDER BY service_date DESC").bind(companyId),
    ]);
    const records = assets.results.map((asset: Record<string, any>) => {
      const assetDocuments = documents.results.filter((row: Record<string, any>) => row.asset_id === asset.id);
      const assetServices = services.results.filter((row: Record<string, any>) => row.asset_id === asset.id);
      const assetFaults = faults.results.filter((row: Record<string, any>) => row.asset_id === asset.id);
      const assetInspections = inspections.results.filter((row: Record<string, any>) => row.asset_id === asset.id);
      const assetAssignments = assignments.results.filter((row: Record<string, any>) => row.asset_id === asset.id);
      return { ...asset, readiness: readiness(asset, assetDocuments, assetServices, assetFaults, assetInspections, assetAssignments), documents: assetDocuments, services: assetServices, faults: assetFaults, inspections: assetInspections, assignments: assetAssignments, fuel: fuel.results.filter((row: Record<string, any>) => row.asset_id === asset.id), maintenance: maintenance.results.filter((row: Record<string, any>) => row.asset_id === asset.id) };
    });
    const alerts = records.flatMap((asset: any) => [asset.readiness.documents, asset.readiness.service, asset.readiness.mechanical, asset.readiness.inspection].filter((item: any) => item.tone !== "green").map((item: any) => ({ assetId: asset.id, asset: asset.asset_no, label: item.label, tone: item.tone })));
    return json({ assets: records, requests: requests.results, alerts, requiredDocuments });
  } catch (error) {
    return json({ error: error instanceof Error ? error.message : "Unable to load fleet management." }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const current = await workspace();
    if (!current) return json({ error: "Sign in is required." }, { status: 401 });
    const { db, companyId, user } = current;
    const { action, data = {} } = await request.json() as { action: string; data: Record<string, unknown> };
    const timestamp = now();
    const assetId = number(data.assetId);
    if (action === "asset") {
      if (!text(data.assetNo) || !text(data.description)) throw new Error("Asset number and description are required.");
      const result = await db.prepare("INSERT INTO fleet_assets (company_id, asset_no, registration, description, type, odometer, make, model, year, vin, engine_number, fuel_type, branch, purchase_info, mechanical_status, warning_days, service_warning_km, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Operational', ?, ?, ?, ?)").bind(companyId, text(data.assetNo), text(data.registration), text(data.description), text(data.type) || "Vehicle", number(data.odometer), text(data.make), text(data.model), number(data.year), text(data.vin), text(data.engineNumber), text(data.fuelType), text(data.branch), text(data.purchaseInfo), number(data.warningDays) || 30, number(data.serviceWarningKm) || 500, timestamp, timestamp).run();
      return json({ ok: true, id: result.meta.last_row_id });
    }
    if (!assetId) throw new Error("Choose a fleet asset.");
    if (action === "document") {
      if (!text(data.documentType)) throw new Error("Document type is required.");
      const result = await db.prepare("INSERT INTO fleet_documents (company_id, asset_id, document_type, document_number, issue_date, expiry_date, required, file_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)").bind(companyId, assetId, text(data.documentType), text(data.documentNumber), text(data.issueDate) || null, text(data.expiryDate) || null, number(data.required) === 0 ? 0 : 1, text(data.fileName), timestamp, timestamp).run();
      return json({ ok: true, id: result.meta.last_row_id });
    }
    if (action === "service") {
      const result = await db.prepare("INSERT INTO fleet_services (company_id, asset_id, service_date, mileage, service_type, parts_used, service_kit, mechanic, cost_m, next_service_date, next_service_mileage, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)").bind(companyId, assetId, text(data.serviceDate) || timestamp.slice(0, 10), number(data.mileage), text(data.serviceType), text(data.partsUsed), text(data.serviceKit), text(data.mechanic), number(data.costM), text(data.nextServiceDate) || null, number(data.nextServiceMileage) || null, timestamp, timestamp).run();
      await db.prepare("UPDATE fleet_assets SET odometer = CASE WHEN ? > odometer THEN ? ELSE odometer END, next_service_date = ?, next_service_mileage = ?, status = 'Available', updated_at = ? WHERE id = ? AND company_id = ?").bind(number(data.mileage), number(data.mileage), text(data.nextServiceDate) || null, number(data.nextServiceMileage) || null, timestamp, assetId, companyId).run();
      return json({ ok: true, id: result.meta.last_row_id });
    }
    if (action === "fault") {
      const severity = text(data.severity) || "Requires attention";
      const result = await db.prepare("INSERT INTO fleet_faults (company_id, asset_id, reported_at, description, severity, status, reported_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'Open', ?, ?, ?)").bind(companyId, assetId, text(data.reportedAt) || timestamp.slice(0, 10), text(data.description), severity, user.displayName, timestamp, timestamp).run();
      await db.prepare("UPDATE fleet_assets SET mechanical_status = ?, fault_notes = ?, status = CASE WHEN ? = 'Critical' THEN 'Out of service' ELSE status END, updated_at = ? WHERE id = ? AND company_id = ?").bind(severity === "Critical" ? "Out of service" : "Requires attention", text(data.description), severity, timestamp, assetId, companyId).run();
      return json({ ok: true, id: result.meta.last_row_id });
    }
    if (action === "inspection") {
      const result = await db.prepare("INSERT INTO fleet_inspections (company_id, asset_id, inspection_date, result, notes, next_due_date, inspector, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)").bind(companyId, assetId, text(data.inspectionDate) || timestamp.slice(0, 10), text(data.result) || "Passed", text(data.notes), text(data.nextDueDate) || null, text(data.inspector), timestamp, timestamp).run();
      await db.prepare("UPDATE fleet_assets SET inspection_status = ?, inspection_due_date = ?, updated_at = ? WHERE id = ? AND company_id = ?").bind(text(data.result) || "Passed", text(data.nextDueDate) || null, timestamp, assetId, companyId).run();
      return json({ ok: true, id: result.meta.last_row_id });
    }
    if (action === "assignment") {
      const result = await db.prepare("INSERT INTO fleet_assignments (company_id, asset_id, driver_name, licence_number, licence_category, purpose, destination, start_date, expected_return_date, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)").bind(companyId, assetId, text(data.driverName), text(data.licenceNumber), text(data.licenceCategory), text(data.purpose), text(data.destination), text(data.startDate) || timestamp.slice(0, 10), text(data.expectedReturnDate) || null, text(data.status) || "Active", timestamp, timestamp).run();
      await db.prepare("UPDATE fleet_assets SET status = 'Assigned', updated_at = ? WHERE id = ? AND company_id = ?").bind(timestamp, assetId, companyId).run();
      return json({ ok: true, id: result.meta.last_row_id });
    }
    if (action === "request") {
      if (!text(data.driverName) || !text(data.vehicleType) || !text(data.requiredDate)) throw new Error("Driver, vehicle type and required date are required.");
      const result = await db.prepare("INSERT INTO fleet_requests (company_id, driver_name, licence_number, licence_category, vehicle_type, purpose, destination, required_date, expected_return_date, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Requested', ?, ?)").bind(companyId, text(data.driverName), text(data.licenceNumber), text(data.licenceCategory), text(data.vehicleType), text(data.purpose), text(data.destination), text(data.requiredDate), text(data.expectedReturnDate) || null, timestamp, timestamp).run();
      return json({ ok: true, id: result.meta.last_row_id });
    }
    if (action === "fuel") {
      const result = await db.prepare("INSERT INTO fuel_logs (company_id, asset_id, fill_date, litres, cost_m, odometer, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)").bind(companyId, assetId, text(data.fillDate) || timestamp.slice(0, 10), number(data.litres), number(data.costM), number(data.odometer), timestamp, timestamp).run();
      await db.prepare("UPDATE fleet_assets SET odometer = CASE WHEN ? > odometer THEN ? ELSE odometer END, updated_at = ? WHERE id = ? AND company_id = ?").bind(number(data.odometer), number(data.odometer), timestamp, assetId, companyId).run();
      return json({ ok: true, id: result.meta.last_row_id });
    }
    throw new Error("Unknown fleet operation.");
  } catch (error) {
    return json({ error: error instanceof Error ? error.message : "Unable to save fleet record." }, { status: 400 });
  }
}