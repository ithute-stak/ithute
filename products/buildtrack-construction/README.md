# Nthane Brothers Construction Management System

**Developed by Ithute Solution**

The Nthane Brothers Construction Management System is a single-company construction operations platform for Nthane Brothers in Lesotho. Head Office, branches and construction sites operate inside one controlled company structure rather than as separate tenants.

The platform connects the full operating lifecycle: business development, tendering, mobilisation, daily site operations, workforce and payroll preparation, fleet and plant, procurement and stores, subcontractors, commercial control, finance, programme/resource control, HSE/quality, compliance, communications, external evidence sharing, project closeout and management intelligence.

## Product identity

- Product: **Nthane Brothers Construction Management System**
- Operating company: **Nthane Brothers**
- Developer: **Ithute Solution**
- Developer email: **thekoetlisi@gmail.com**
- Developer phone / WhatsApp: **+266 5900 1394**
- Primary currency: **Lesotho Loti / Maloti (M / LSL)**
- Primary timezone: **Africa/Maseru**
- Frontend: **http://localhost:3004** by default
- API: **http://localhost:8004** by default
- API docs: **http://localhost:8004/docs** by default

## Architecture

The active application is the monorepo under `apps/`:

- `apps/frontend` - Next.js 16, React 19, TypeScript and Redux Toolkit
- `apps/backend` - FastAPI, SQLAlchemy and Alembic
- PostgreSQL - primary operational database
- Redis - runtime infrastructure
- WebSockets - company-scoped realtime entity-change notifications
- Docker Compose - database, Redis, migration, backend and frontend orchestration

A former root application remains temporarily during the monorepo migration. New product work should target `apps/frontend` and `apps/backend` unless a migration task explicitly requires the legacy root application.

## Current implementation

The repository now contains 48 active frontend routes: the original 46 operational/authentication routes plus the full web manual at `/index` and the `/documentation` alias. Implementation work is complete through Phase 36.

| Phase | Capability | Status |
| --- | --- | --- |
| 1 | Company, branches, sites, departments, cost centres, roles, approvals, documents, numbering and audit | Complete |
| 2 | User access, scoped permissions, password/session/security controls | Complete |
| 3 | Workforce, contracts, leave, attendance, timesheets and payroll preparation | Complete |
| 4 | Fleet and plant, fuel, inspections, defects, compliance and maintenance | Complete |
| 5 | Tender pipeline, estimating, checklist, securities, clarification and submission control | Complete |
| 6 | Project mobilisation, budget, programme, team, plant, risk and readiness | Complete |
| 7 | Daily site operations, labour, plant, materials, progress, incidents and quality | Complete |
| 8 | Procurement, suppliers, quotations, purchase orders, receiving, stores and stock | Complete |
| 9 | Subcontractors, packages, bids, contracts, certificates, retention and evidence | Complete |
| 10 | Explainable procurement and tender assistants | Complete |
| 11 | Cost and commercial control | Complete |
| 12 | Management intelligence | Complete |
| 13 | Document, HSE and quality assurance | Complete |
| 14 | Mobile/offline field capture and controlled sync | Complete |
| 15 | HR development, training and credential control | Complete |
| 16 | Professional rollout, migration, UAT, security, training and recovery evidence | Complete |
| 17 | Project closeout | Complete |
| 18 | Finance and cash control | Complete |
| 19 | Programme and project controls | Complete |
| 20 | Resource planning and capacity control | Complete |
| 21 | Project communications and stakeholder control | Complete |
| 22 | Integrated compliance and policy control | Complete |
| 23 | Project data quality and readiness assurance | Complete |
| 24 | Delegated authority and Maloti approval limits | Complete |
| 25 | System change and release control | Complete |
| 26 | Service desk and support control | Complete |
| 27 | Operational knowledge and SOP support | Complete |
| 28 | Environment and sustainability control | Complete |
| 29 | Tools and calibration control | Complete |
| 30 | Controlled client document sharing | Complete |
| 31 | Supplier/subcontractor evidence collection portal | Complete |
| 32 | Business development and opportunity pipeline | Complete |
| 33 | Client account and relationship management | Complete |
| 34 | Contract control | Complete |
| 35 | Operational automation | Complete |
| 36 | Deployment, security and continuity hardening | Complete |

## Main frontend workspaces

### Overview

- `/` - Command Centre
- `/intelligence` - Management Intelligence
- `/index` - Full System Manual, task finder, roles and About the System
- `/documentation` - alias that redirects to `/index`

### Projects and sites

- `/projects` - Project Mobilisation
- `/projects/control` - Project Control
- `/projects/risks` - Project Risks
- `/planning` - Programme & Project Controls
- `/resources` - Resource Planning & Capacity Control
- `/communications` - Project Communications
- `/compliance` - Compliance & Policy Control
- `/data-quality` - Data Quality & Readiness Assurance
- `/authority` - Delegated Authority
- `/changes` - Change & Release Control
- `/site-operations` - Site Operations
- `/site-operations/control` - Site Operations Control
- `/closeout` - Project Closeout
- `/mobile` - Mobile Field Capture

### Commercial

- `/tenders` - Tender Management
- `/tenders/control` - Tender Control
- `/procurement` - Procurement & Stores
- `/procurement/control` - Procurement Control
- `/subcontracts` - Subcontract Management
- `/subcontracts/control` - Subcontract Control
- `/commercial` - Cost & Commercial Control
- `/contract-control` - Contract Control
- `/finance` - Finance & Cash Control
- `/assistants` - Explainable Algorithmic Assistants

### People and control

- `/workforce` - Workforce & Payroll
- `/workforce/setup` - Workforce Setup
- `/development` - HR Development
- `/fleet` - Fleet & Plant
- `/fleet/control` - Fleet Control
- `/assurance` - HSE & Quality Assurance
- `/support` - Support Centre
- `/environment` - Environment & Sustainability
- `/tools` - Tools & Calibration
- `/client-portal` - Controlled Client Sharing
- `/vendor-portal` - Vendor Evidence Portal
- `/business-development` - Business Development
- `/client-accounts` - Client Accounts
- `/access` - Access & Security
- `/rollout` - Professional Rollout
- `/automation` - Operational Automation

### Authentication and external routes

- `/login`
- `/reset-password`
- `/setup`
- `/vendor-submissions/[token]`

## Web user manual

`/index` is the public, navigation-first operating manual. It is intentionally readable before authentication so a new user can understand the product before signing in.

The manual includes:

- all 46 original system screens and routes;
- a searchable **Where do I find…?** task index;
- direct screen links;
- automatic sign-in-and-return links for unauthenticated users;
- complete role guidance;
- operating steps for each screen;
- common forms/actions for each module;
- source-of-truth guidance so users know which module owns a record;
- end-to-end operating workflow guidance;
- developer/support contact information.

The Sign In, Password Reset and First-Time Setup screens expose a **Documentation & User Manual** button in their public header. Authenticated users also have **System Manual** in the application sidebar.

## Global navigation and form finder

Authenticated users have two global search tools available across the application:

- **Double-tap Shift** to open global route search.
- **Shift + double-click** on a non-form area as an alternative route-search gesture.
- **Press and release Ctrl + Shift** to open the global form/action finder.

The form finder supports search plus a module selector, allowing users to search actions such as `Fuel transaction`, `Purchase order`, `Employee`, `Daily site report`, `Contract notice`, `Invoice`, or `Payroll batch` and jump to the owning screen.

Modifier handling deliberately avoids stealing longer browser shortcuts such as Ctrl+Shift+I and Ctrl+Shift+T.

## Security and governance model

The application combines permission and scope. A role assignment can be company-, branch- or site-scoped. The platform supports multiple assignments per user and uses the shared permission system throughout later operational modules.

Core roles include System Administrator, Access Administrator, Head Office Executive, Branch Manager, Site Manager, Approver and Auditor/Read Only. Operational phases add specialist roles for HR/payroll, fleet, tendering, project controls, site operations, procurement/stores, subcontract control, commercial management and finance.

Controlled workflows use maker/checker approval. Where the company no-self-approval policy is active, a user cannot independently approve or verify the record they prepared.

## Important operating boundaries

The system controls records and evidence; it deliberately does not pretend that an external action occurred when it did not.

- Payroll prepares and approves payroll data; it does not execute salary payments.
- Finance records payment requests and supplied payment evidence; it does not move money.
- Project Communications records correspondence and dispatch/response evidence; it does not send external messages.
- Programme delay records support internal control; they do not issue legal notices or determine contractual entitlement.
- Client and vendor public links expose only deliberately selected evidence; they do not create external internal-system accounts.
- Procurement records supplier quotations and supporting evidence; it does **not** fabricate quotations or supplier responses.
- Algorithmic assistants provide explainable decision support; they do not approve transactions or submit tenders.

## Docker startup

For local development/testing:

No `.env` file is required for local development; the Compose stack has safe local defaults, while production/VPS deployments must provide their own secure environment values.

```bash
docker compose up --build
```

The compose stack starts PostgreSQL and Redis, runs Alembic migrations, starts the FastAPI backend after database readiness, then starts the Next.js frontend after backend health checks pass.

Production/VPS environments must override development defaults such as database password and public URLs in environment configuration.

## Quality checks

Frontend checks:

```bash
cd apps/frontend
npm run typecheck
npm run lint
npm run build
```

Backend tests:

```bash
cd apps/backend
pytest
```

The backend test suite contains migration, health, Docker-contract and phase-specific regression coverage.

## Documentation

- `/index` - live web user manual and About the System page
- `docs/IMPLEMENTATION_PHASES.md` - detailed implementation contracts and operating boundaries
- `docs/MONOREPO_MIGRATION.md` - monorepo migration notes
- phase-specific documents under `docs/`

PDF user-guide and product-presentation artifacts can be maintained alongside the live documentation, but the web manual is the primary in-product navigation reference.

## Development ownership

The Nthane Brothers Construction Management System is developed by **Ithute Solution** for Nthane Brothers. Product naming, user-facing documentation and release material should use this identity consistently.

For developer or support contact:

- Email: **thekoetlisi@gmail.com**
- Phone: **+266 5900 1394**
- WhatsApp: **https://wa.me/26659001394**
