CREATE TABLE `attendance` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`company_id` integer NOT NULL,
	`employee_id` integer NOT NULL,
	`project_id` integer,
	`work_date` text NOT NULL,
	`status` text DEFAULT 'Present' NOT NULL,
	`hours` integer DEFAULT 8 NOT NULL,
	`notes` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`company_id`) REFERENCES `companies`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`employee_id`) REFERENCES `employees`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `companies` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`name` text NOT NULL,
	`country` text DEFAULT 'Lesotho' NOT NULL,
	`currency` text DEFAULT 'LSL' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `documents` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`company_id` integer NOT NULL,
	`owner_type` text NOT NULL,
	`owner_id` integer,
	`file_name` text NOT NULL,
	`content_type` text,
	`object_key` text NOT NULL,
	`uploaded_by` text NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`company_id`) REFERENCES `companies`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `documents_object_key_unique` ON `documents` (`object_key`);--> statement-breakpoint
CREATE TABLE `employees` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`company_id` integer NOT NULL,
	`employee_no` text NOT NULL,
	`full_name` text NOT NULL,
	`role` text NOT NULL,
	`department` text DEFAULT 'Operations' NOT NULL,
	`phone` text,
	`employment_status` text DEFAULT 'Active' NOT NULL,
	`pay_rate_m` integer DEFAULT 0 NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`company_id`) REFERENCES `companies`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `employees_employee_no_unique` ON `employees` (`employee_no`);--> statement-breakpoint
CREATE TABLE `fleet_assets` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`company_id` integer NOT NULL,
	`asset_no` text NOT NULL,
	`registration` text,
	`description` text NOT NULL,
	`type` text DEFAULT 'Vehicle' NOT NULL,
	`status` text DEFAULT 'Available' NOT NULL,
	`odometer` integer DEFAULT 0 NOT NULL,
	`next_service_date` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`company_id`) REFERENCES `companies`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `fleet_assets_asset_no_unique` ON `fleet_assets` (`asset_no`);--> statement-breakpoint
CREATE TABLE `fuel_logs` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`company_id` integer NOT NULL,
	`asset_id` integer NOT NULL,
	`project_id` integer,
	`fill_date` text NOT NULL,
	`litres` integer NOT NULL,
	`cost_m` integer NOT NULL,
	`odometer` integer,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`company_id`) REFERENCES `companies`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`asset_id`) REFERENCES `fleet_assets`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `maintenance_records` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`company_id` integer NOT NULL,
	`asset_id` integer NOT NULL,
	`service_date` text NOT NULL,
	`description` text NOT NULL,
	`cost_m` integer DEFAULT 0 NOT NULL,
	`status` text DEFAULT 'Completed' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`company_id`) REFERENCES `companies`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`asset_id`) REFERENCES `fleet_assets`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `payroll_periods` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`company_id` integer NOT NULL,
	`period_label` text NOT NULL,
	`start_date` text NOT NULL,
	`end_date` text NOT NULL,
	`status` text DEFAULT 'Draft' NOT NULL,
	`gross_m` integer DEFAULT 0 NOT NULL,
	`net_m` integer DEFAULT 0 NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`company_id`) REFERENCES `companies`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `projects` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`company_id` integer NOT NULL,
	`code` text NOT NULL,
	`name` text NOT NULL,
	`client` text,
	`site` text,
	`manager` text,
	`status` text DEFAULT 'Planning' NOT NULL,
	`budget_m` integer DEFAULT 0 NOT NULL,
	`spent_m` integer DEFAULT 0 NOT NULL,
	`progress` integer DEFAULT 0 NOT NULL,
	`start_date` text,
	`target_date` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`company_id`) REFERENCES `companies`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `projects_code_unique` ON `projects` (`code`);--> statement-breakpoint
CREATE TABLE `subcontractors` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`company_id` integer NOT NULL,
	`name` text NOT NULL,
	`trade` text NOT NULL,
	`contact_name` text,
	`phone` text,
	`compliance_status` text DEFAULT 'Pending review' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`company_id`) REFERENCES `companies`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `subcontracts` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`company_id` integer NOT NULL,
	`project_id` integer NOT NULL,
	`subcontractor_id` integer NOT NULL,
	`reference` text NOT NULL,
	`scope` text NOT NULL,
	`status` text DEFAULT 'Draft' NOT NULL,
	`value_m` integer DEFAULT 0 NOT NULL,
	`retention_m` integer DEFAULT 0 NOT NULL,
	`start_date` text,
	`end_date` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`company_id`) REFERENCES `companies`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`subcontractor_id`) REFERENCES `subcontractors`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `subcontracts_reference_unique` ON `subcontracts` (`reference`);--> statement-breakpoint
CREATE TABLE `tenders` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`company_id` integer NOT NULL,
	`reference` text NOT NULL,
	`title` text NOT NULL,
	`client` text,
	`category` text DEFAULT 'Construction' NOT NULL,
	`status` text DEFAULT 'In preparation' NOT NULL,
	`value_m` integer DEFAULT 0 NOT NULL,
	`submission_date` text,
	`owner` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`company_id`) REFERENCES `companies`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `tenders_reference_unique` ON `tenders` (`reference`);--> statement-breakpoint
CREATE TABLE `users` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`company_id` integer NOT NULL,
	`email` text NOT NULL,
	`full_name` text,
	`role` text DEFAULT 'Operations Viewer' NOT NULL,
	`active` integer DEFAULT true NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`company_id`) REFERENCES `companies`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `users_email_unique` ON `users` (`email`);