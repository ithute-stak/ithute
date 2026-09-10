ALTER TABLE fleet_assets ADD COLUMN make text;
--> statement-breakpoint
ALTER TABLE fleet_assets ADD COLUMN model text;
--> statement-breakpoint
ALTER TABLE fleet_assets ADD COLUMN year integer;
--> statement-breakpoint
ALTER TABLE fleet_assets ADD COLUMN vin text;
--> statement-breakpoint
ALTER TABLE fleet_assets ADD COLUMN engine_number text;
--> statement-breakpoint
ALTER TABLE fleet_assets ADD COLUMN fuel_type text;
--> statement-breakpoint
ALTER TABLE fleet_assets ADD COLUMN branch text;
--> statement-breakpoint
ALTER TABLE fleet_assets ADD COLUMN purchase_info text;
--> statement-breakpoint
ALTER TABLE fleet_assets ADD COLUMN mechanical_status text NOT NULL DEFAULT 'Operational';
--> statement-breakpoint
ALTER TABLE fleet_assets ADD COLUMN fault_notes text;
--> statement-breakpoint
ALTER TABLE fleet_assets ADD COLUMN inspection_status text;
--> statement-breakpoint
ALTER TABLE fleet_assets ADD COLUMN inspection_due_date text;
--> statement-breakpoint
ALTER TABLE fleet_assets ADD COLUMN warning_days integer NOT NULL DEFAULT 30;
--> statement-breakpoint
ALTER TABLE fleet_assets ADD COLUMN service_warning_km integer NOT NULL DEFAULT 500;
--> statement-breakpoint
ALTER TABLE fleet_assets ADD COLUMN next_service_mileage integer;
--> statement-breakpoint
CREATE TABLE fleet_documents (
  id integer PRIMARY KEY AUTOINCREMENT NOT NULL,
  company_id integer NOT NULL,
  asset_id integer NOT NULL,
  document_type text NOT NULL,
  document_number text,
  issue_date text,
  expiry_date text,
  required integer NOT NULL DEFAULT 1,
  file_name text,
  created_at text NOT NULL,
  updated_at text NOT NULL,
  FOREIGN KEY (company_id) REFERENCES companies(id),
  FOREIGN KEY (asset_id) REFERENCES fleet_assets(id)
);
--> statement-breakpoint
CREATE INDEX idx_fleet_documents_asset_expiry ON fleet_documents(asset_id, expiry_date);
--> statement-breakpoint
CREATE TABLE fleet_services (
  id integer PRIMARY KEY AUTOINCREMENT NOT NULL,
  company_id integer NOT NULL,
  asset_id integer NOT NULL,
  service_date text NOT NULL,
  mileage integer NOT NULL DEFAULT 0,
  service_type text,
  parts_used text,
  service_kit text,
  mechanic text,
  cost_m integer NOT NULL DEFAULT 0,
  next_service_date text,
  next_service_mileage integer,
  created_at text NOT NULL,
  updated_at text NOT NULL,
  FOREIGN KEY (company_id) REFERENCES companies(id),
  FOREIGN KEY (asset_id) REFERENCES fleet_assets(id)
);
--> statement-breakpoint
CREATE INDEX idx_fleet_services_asset_date ON fleet_services(asset_id, service_date DESC);
--> statement-breakpoint
CREATE TABLE fleet_faults (
  id integer PRIMARY KEY AUTOINCREMENT NOT NULL,
  company_id integer NOT NULL,
  asset_id integer NOT NULL,
  reported_at text NOT NULL,
  description text NOT NULL,
  severity text NOT NULL DEFAULT 'Requires attention',
  status text NOT NULL DEFAULT 'Open',
  reported_by text,
  resolved_at text,
  created_at text NOT NULL,
  updated_at text NOT NULL,
  FOREIGN KEY (company_id) REFERENCES companies(id),
  FOREIGN KEY (asset_id) REFERENCES fleet_assets(id)
);
--> statement-breakpoint
CREATE INDEX idx_fleet_faults_asset_status ON fleet_faults(asset_id, status);
--> statement-breakpoint
CREATE TABLE fleet_inspections (
  id integer PRIMARY KEY AUTOINCREMENT NOT NULL,
  company_id integer NOT NULL,
  asset_id integer NOT NULL,
  inspection_date text NOT NULL,
  result text NOT NULL DEFAULT 'Passed',
  notes text,
  next_due_date text,
  inspector text,
  created_at text NOT NULL,
  updated_at text NOT NULL,
  FOREIGN KEY (company_id) REFERENCES companies(id),
  FOREIGN KEY (asset_id) REFERENCES fleet_assets(id)
);
--> statement-breakpoint
CREATE INDEX idx_fleet_inspections_asset_date ON fleet_inspections(asset_id, inspection_date DESC);
--> statement-breakpoint
CREATE TABLE fleet_assignments (
  id integer PRIMARY KEY AUTOINCREMENT NOT NULL,
  company_id integer NOT NULL,
  asset_id integer NOT NULL,
  driver_name text,
  licence_number text,
  licence_category text,
  purpose text,
  destination text,
  start_date text NOT NULL,
  expected_return_date text,
  end_date text,
  status text NOT NULL DEFAULT 'Active',
  created_at text NOT NULL,
  updated_at text NOT NULL,
  FOREIGN KEY (company_id) REFERENCES companies(id),
  FOREIGN KEY (asset_id) REFERENCES fleet_assets(id)
);
--> statement-breakpoint
CREATE INDEX idx_fleet_assignments_asset_status ON fleet_assignments(asset_id, status);
--> statement-breakpoint
CREATE TABLE fleet_requests (
  id integer PRIMARY KEY AUTOINCREMENT NOT NULL,
  company_id integer NOT NULL,
  driver_name text NOT NULL,
  licence_number text,
  licence_category text,
  vehicle_type text NOT NULL,
  purpose text,
  destination text,
  required_date text NOT NULL,
  expected_return_date text,
  status text NOT NULL DEFAULT 'Requested',
  created_at text NOT NULL,
  updated_at text NOT NULL,
  FOREIGN KEY (company_id) REFERENCES companies(id)
);
--> statement-breakpoint
CREATE INDEX idx_fleet_requests_company_date ON fleet_requests(company_id, required_date);
