import { integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

const timestamps = {
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
};

export const companies = sqliteTable("companies", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  name: text("name").notNull(),
  country: text("country").notNull().default("Lesotho"),
  currency: text("currency").notNull().default("LSL"),
  ...timestamps,
});

export const users = sqliteTable("users", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  email: text("email").notNull().unique(),
  fullName: text("full_name"),
  role: text("role").notNull().default("Operations Viewer"),
  active: integer("active", { mode: "boolean" }).notNull().default(true),
  ...timestamps,
});

export const projects = sqliteTable("projects", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  code: text("code").notNull().unique(),
  name: text("name").notNull(),
  client: text("client"),
  site: text("site"),
  manager: text("manager"),
  status: text("status").notNull().default("Planning"),
  budgetM: integer("budget_m").notNull().default(0),
  spentM: integer("spent_m").notNull().default(0),
  progress: integer("progress").notNull().default(0),
  startDate: text("start_date"),
  targetDate: text("target_date"),
  ...timestamps,
});

export const tenders = sqliteTable("tenders", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  reference: text("reference").notNull().unique(),
  title: text("title").notNull(),
  client: text("client"),
  category: text("category").notNull().default("Construction"),
  status: text("status").notNull().default("In preparation"),
  valueM: integer("value_m").notNull().default(0),
  submissionDate: text("submission_date"),
  owner: text("owner"),
  ...timestamps,
});

export const employees = sqliteTable("employees", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  employeeNo: text("employee_no").notNull().unique(),
  fullName: text("full_name").notNull(),
  role: text("role").notNull(),
  department: text("department").notNull().default("Operations"),
  phone: text("phone"),
  employmentStatus: text("employment_status").notNull().default("Active"),
  payRateM: integer("pay_rate_m").notNull().default(0),
  ...timestamps,
});

export const attendance = sqliteTable("attendance", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  employeeId: integer("employee_id").notNull().references(() => employees.id),
  projectId: integer("project_id").references(() => projects.id),
  workDate: text("work_date").notNull(),
  status: text("status").notNull().default("Present"),
  hours: integer("hours").notNull().default(8),
  notes: text("notes"),
  ...timestamps,
});

export const payrollPeriods = sqliteTable("payroll_periods", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  periodLabel: text("period_label").notNull(),
  startDate: text("start_date").notNull(),
  endDate: text("end_date").notNull(),
  status: text("status").notNull().default("Draft"),
  grossM: integer("gross_m").notNull().default(0),
  netM: integer("net_m").notNull().default(0),
  ...timestamps,
});

export const fleetAssets = sqliteTable("fleet_assets", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  assetNo: text("asset_no").notNull().unique(),
  registration: text("registration"),
  description: text("description").notNull(),
  type: text("type").notNull().default("Vehicle"),
  status: text("status").notNull().default("Available"),
  odometer: integer("odometer").notNull().default(0),
  make: text("make"),
  model: text("model"),
  year: integer("year"),
  vin: text("vin"),
  engineNumber: text("engine_number"),
  fuelType: text("fuel_type"),
  branch: text("branch"),
  purchaseInfo: text("purchase_info"),
  mechanicalStatus: text("mechanical_status").notNull().default("Operational"),
  faultNotes: text("fault_notes"),
  inspectionStatus: text("inspection_status"),
  inspectionDueDate: text("inspection_due_date"),
  warningDays: integer("warning_days").notNull().default(30),
  serviceWarningKm: integer("service_warning_km").notNull().default(500),
  nextServiceDate: text("next_service_date"),
  nextServiceMileage: integer("next_service_mileage"),
  ...timestamps,
});

export const fleetDocuments = sqliteTable("fleet_documents", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  assetId: integer("asset_id").notNull().references(() => fleetAssets.id),
  documentType: text("document_type").notNull(),
  documentNumber: text("document_number"),
  issueDate: text("issue_date"),
  expiryDate: text("expiry_date"),
  required: integer("required").notNull().default(1),
  fileName: text("file_name"),
  ...timestamps,
});

export const fleetServices = sqliteTable("fleet_services", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  assetId: integer("asset_id").notNull().references(() => fleetAssets.id),
  serviceDate: text("service_date").notNull(),
  mileage: integer("mileage").notNull().default(0),
  serviceType: text("service_type"),
  partsUsed: text("parts_used"),
  serviceKit: text("service_kit"),
  mechanic: text("mechanic"),
  costM: integer("cost_m").notNull().default(0),
  nextServiceDate: text("next_service_date"),
  nextServiceMileage: integer("next_service_mileage"),
  ...timestamps,
});

export const fleetFaults = sqliteTable("fleet_faults", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  assetId: integer("asset_id").notNull().references(() => fleetAssets.id),
  reportedAt: text("reported_at").notNull(),
  description: text("description").notNull(),
  severity: text("severity").notNull().default("Requires attention"),
  status: text("status").notNull().default("Open"),
  reportedBy: text("reported_by"),
  resolvedAt: text("resolved_at"),
  ...timestamps,
});

export const fleetInspections = sqliteTable("fleet_inspections", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  assetId: integer("asset_id").notNull().references(() => fleetAssets.id),
  inspectionDate: text("inspection_date").notNull(),
  result: text("result").notNull().default("Passed"),
  notes: text("notes"),
  nextDueDate: text("next_due_date"),
  inspector: text("inspector"),
  ...timestamps,
});

export const fleetAssignments = sqliteTable("fleet_assignments", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  assetId: integer("asset_id").notNull().references(() => fleetAssets.id),
  driverName: text("driver_name"),
  licenceNumber: text("licence_number"),
  licenceCategory: text("licence_category"),
  purpose: text("purpose"),
  destination: text("destination"),
  startDate: text("start_date").notNull(),
  expectedReturnDate: text("expected_return_date"),
  endDate: text("end_date"),
  status: text("status").notNull().default("Active"),
  ...timestamps,
});

export const fleetRequests = sqliteTable("fleet_requests", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  driverName: text("driver_name").notNull(),
  licenceNumber: text("licence_number"),
  licenceCategory: text("licence_category"),
  vehicleType: text("vehicle_type").notNull(),
  purpose: text("purpose"),
  destination: text("destination"),
  requiredDate: text("required_date").notNull(),
  expectedReturnDate: text("expected_return_date"),
  status: text("status").notNull().default("Requested"),
  ...timestamps,
});

export const fuelLogs = sqliteTable("fuel_logs", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  assetId: integer("asset_id").notNull().references(() => fleetAssets.id),
  projectId: integer("project_id").references(() => projects.id),
  fillDate: text("fill_date").notNull(),
  litres: integer("litres").notNull(),
  costM: integer("cost_m").notNull(),
  odometer: integer("odometer"),
  ...timestamps,
});

export const maintenanceRecords = sqliteTable("maintenance_records", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  assetId: integer("asset_id").notNull().references(() => fleetAssets.id),
  serviceDate: text("service_date").notNull(),
  description: text("description").notNull(),
  costM: integer("cost_m").notNull().default(0),
  status: text("status").notNull().default("Completed"),
  ...timestamps,
});

export const subcontractors = sqliteTable("subcontractors", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  name: text("name").notNull(),
  trade: text("trade").notNull(),
  contactName: text("contact_name"),
  phone: text("phone"),
  complianceStatus: text("compliance_status").notNull().default("Pending review"),
  ...timestamps,
});

export const subcontracts = sqliteTable("subcontracts", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  projectId: integer("project_id").notNull().references(() => projects.id),
  subcontractorId: integer("subcontractor_id").notNull().references(() => subcontractors.id),
  reference: text("reference").notNull().unique(),
  scope: text("scope").notNull(),
  status: text("status").notNull().default("Draft"),
  valueM: integer("value_m").notNull().default(0),
  retentionM: integer("retention_m").notNull().default(0),
  startDate: text("start_date"),
  endDate: text("end_date"),
  ...timestamps,
});

export const documents = sqliteTable("documents", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  companyId: integer("company_id").notNull().references(() => companies.id),
  ownerType: text("owner_type").notNull(),
  ownerId: integer("owner_id"),
  fileName: text("file_name").notNull(),
  contentType: text("content_type"),
  objectKey: text("object_key").notNull().unique(),
  uploadedBy: text("uploaded_by").notNull(),
  ...timestamps,
});
