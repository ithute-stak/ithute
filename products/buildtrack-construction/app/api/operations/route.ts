import { env } from "cloudflare:workers";
import { getChatGPTUser } from "../../chatgpt-auth";

type OperationRequest = {
  kind: string;
  data: Record<string, unknown>;
};

const now = () => new Date().toISOString();
const numberValue = (value: unknown) => Number(value) || 0;
const textValue = (value: unknown) => String(value ?? "").trim();

function json(body: unknown, init?: ResponseInit) {
  return Response.json(body, init);
}

function getDatabase(): D1Database {
  if (!env.DB) throw new Error("The BuildTrack data store is not available.");
  return env.DB;
}

async function getCompanyId(db: D1Database, email: string, fullName: string | null) {
  const timestamp = now();
  let company = await db.prepare("SELECT id FROM companies ORDER BY id LIMIT 1").first<{ id: number }>();

  if (!company) {
    await db
      .prepare(
        "INSERT INTO companies (name, country, currency, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
      )
      .bind("My Construction Company", "Lesotho", "LSL", timestamp, timestamp)
      .run();
    company = await db.prepare("SELECT id FROM companies ORDER BY id LIMIT 1").first<{ id: number }>();
  }

  if (!company) throw new Error("Unable to prepare the company workspace.");

  await db
    .prepare(
      "INSERT INTO users (company_id, email, full_name, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(email) DO UPDATE SET full_name = excluded.full_name, updated_at = excluded.updated_at",
    )
    .bind(company.id, email, fullName, "Administrator", 1, timestamp, timestamp)
    .run();

  return company.id;
}

async function currentWorkspace() {
  const user = await getChatGPTUser();
  if (!user) return null;
  const db = getDatabase();
  const companyId = await getCompanyId(db, user.email, user.fullName);
  return { db, companyId, user };
}

export async function GET() {
  try {
    const workspace = await currentWorkspace();
    if (!workspace) return json({ error: "Sign in is required." }, { status: 401 });

    const { db, companyId, user } = workspace;
    const [company, projects, tenders, employees, fleet, subcontracts, documents, payroll] = await Promise.all([
      db.prepare("SELECT name, country, currency FROM companies WHERE id = ?").bind(companyId).first(),
      db.prepare("SELECT * FROM projects WHERE company_id = ? ORDER BY updated_at DESC").bind(companyId).all(),
      db.prepare("SELECT * FROM tenders WHERE company_id = ? ORDER BY submission_date ASC").bind(companyId).all(),
      db.prepare("SELECT * FROM employees WHERE company_id = ? ORDER BY full_name ASC").bind(companyId).all(),
      db.prepare("SELECT * FROM fleet_assets WHERE company_id = ? ORDER BY asset_no ASC").bind(companyId).all(),
      db.prepare("SELECT * FROM subcontracts WHERE company_id = ? ORDER BY updated_at DESC").bind(companyId).all(),
      db.prepare("SELECT * FROM documents WHERE company_id = ? ORDER BY created_at DESC").bind(companyId).all(),
      db.prepare("SELECT * FROM payroll_periods WHERE company_id = ? ORDER BY end_date DESC").bind(companyId).all(),
    ]);

    return json({
      company,
      currentUser: { name: user.displayName, email: user.email },
      records: {
        projects: projects.results,
        tenders: tenders.results,
        employees: employees.results,
        fleet: fleet.results,
        subcontracts: subcontracts.results,
        documents: documents.results,
        payroll: payroll.results,
      },
    });
  } catch (error) {
    return json({ error: error instanceof Error ? error.message : "Unable to load BuildTrack." }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const workspace = await currentWorkspace();
    if (!workspace) return json({ error: "Sign in is required." }, { status: 401 });

    const body = (await request.json()) as OperationRequest;
    const { db, companyId, user } = workspace;
    const data = body.data ?? {};
    const timestamp = now();

    switch (body.kind) {
      case "tender": {
        if (!textValue(data.reference) || !textValue(data.title)) throw new Error("Tender reference and title are required.");
        const result = await db.prepare("INSERT INTO tenders (company_id, reference, title, client, category, status, value_m, submission_date, owner, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
          .bind(companyId, textValue(data.reference), textValue(data.title), textValue(data.client), textValue(data.category) || "Construction", "In preparation", numberValue(data.valueM), textValue(data.submissionDate) || null, user.displayName, timestamp, timestamp).run();
        return json({ ok: true, id: result.meta.last_row_id });
      }
      case "project": {
        if (!textValue(data.code) || !textValue(data.name)) throw new Error("Project code and name are required.");
        const result = await db.prepare("INSERT INTO projects (company_id, code, name, client, site, manager, status, budget_m, spent_m, progress, start_date, target_date, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
          .bind(companyId, textValue(data.code), textValue(data.name), textValue(data.client), textValue(data.site), textValue(data.manager), "Planning", numberValue(data.budgetM), 0, 0, textValue(data.startDate) || null, textValue(data.targetDate) || null, timestamp, timestamp).run();
        return json({ ok: true, id: result.meta.last_row_id });
      }
      case "employee": {
        if (!textValue(data.employeeNo) || !textValue(data.fullName) || !textValue(data.role)) throw new Error("Employee number, name and role are required.");
        const result = await db.prepare("INSERT INTO employees (company_id, employee_no, full_name, role, department, phone, employment_status, pay_rate_m, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
          .bind(companyId, textValue(data.employeeNo), textValue(data.fullName), textValue(data.role), textValue(data.department) || "Operations", textValue(data.phone), "Active", numberValue(data.payRateM), timestamp, timestamp).run();
        return json({ ok: true, id: result.meta.last_row_id });
      }
      case "fleet": {
        if (!textValue(data.assetNo) || !textValue(data.description)) throw new Error("Asset number and description are required.");
        const result = await db.prepare("INSERT INTO fleet_assets (company_id, asset_no, registration, description, type, status, odometer, next_service_date, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
          .bind(companyId, textValue(data.assetNo), textValue(data.registration), textValue(data.description), textValue(data.type) || "Vehicle", "Available", numberValue(data.odometer), textValue(data.nextServiceDate) || null, timestamp, timestamp).run();
        return json({ ok: true, id: result.meta.last_row_id });
      }
      case "subcontractor": {
        if (!textValue(data.name) || !textValue(data.trade)) throw new Error("Subcontractor name and trade are required.");
        const result = await db.prepare("INSERT INTO subcontractors (company_id, name, trade, contact_name, phone, compliance_status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
          .bind(companyId, textValue(data.name), textValue(data.trade), textValue(data.contactName), textValue(data.phone), "Pending review", timestamp, timestamp).run();
        return json({ ok: true, id: result.meta.last_row_id });
      }
      case "subcontract": {
        if (!textValue(data.reference) || !textValue(data.scope) || !numberValue(data.projectId) || !numberValue(data.subcontractorId)) throw new Error("Reference, scope, project and subcontractor are required.");
        const result = await db.prepare("INSERT INTO subcontracts (company_id, project_id, subcontractor_id, reference, scope, status, value_m, retention_m, start_date, end_date, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
          .bind(companyId, numberValue(data.projectId), numberValue(data.subcontractorId), textValue(data.reference), textValue(data.scope), "Draft", numberValue(data.valueM), numberValue(data.retentionM), textValue(data.startDate) || null, textValue(data.endDate) || null, timestamp, timestamp).run();
        return json({ ok: true, id: result.meta.last_row_id });
      }
      case "attendance": {
        if (!numberValue(data.employeeId) || !textValue(data.workDate)) throw new Error("Employee and work date are required.");
        const result = await db.prepare("INSERT INTO attendance (company_id, employee_id, project_id, work_date, status, hours, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")
          .bind(companyId, numberValue(data.employeeId), numberValue(data.projectId) || null, textValue(data.workDate), textValue(data.status) || "Present", numberValue(data.hours) || 8, textValue(data.notes), timestamp, timestamp).run();
        return json({ ok: true, id: result.meta.last_row_id });
      }
      default:
        return json({ error: "That BuildTrack action is not recognised." }, { status: 400 });
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to save the record.";
    const status = /UNIQUE constraint/i.test(message) ? 409 : 400;
    return json({ error: message }, { status });
  }
}
