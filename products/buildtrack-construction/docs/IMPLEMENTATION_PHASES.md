# Nthane Brothers Construction Management System - Implementation Phases

**Developed by Ithute Solution**

This document defines the implementation scope and operating boundaries of the Nthane Brothers Construction Management System. Nthane Brothers is one company inside the platform. Head Office, branches and sites are organisational scopes, not separate tenant accounts.

## Foundation principles

Every operational module must reuse the common company backbone: `company_id` and, where relevant, `branch_id`, `site_id`, `department_id`, `cost_centre_id` and `project_id`. New modules must not create parallel branch, site, approval, document, numbering, audit or access-control systems.

The application uses a shared role/permission model with company, branch and site scope. Controlled records use maker/checker approval where required. External execution must never be invented: the platform may control evidence for a payment, submission, dispatch or instruction, but it must not claim that the real-world action occurred unless supplied evidence confirms it.

## Phase register

| Phase | Focus | Status |
| --- | --- | --- |
| 1 | Core company platform and branch/site administration | Complete |
| 2 | User access and security | Complete |
| 3 | Workforce, attendance and payroll preparation | Complete |
| 4 | Fleet and plant | Complete |
| 5 | Tender management | Complete |
| 6 | Project mobilisation | Complete |
| 7 | Site operations | Complete |
| 8 | Procurement and stores | Complete |
| 9 | Subcontract management | Complete |
| 10 | Explainable procurement and tender assistants | Complete |
| 11 | Cost and commercial control | Complete |
| 12 | Management intelligence | Complete |
| 13 | Document, HSE and quality assurance | Complete |
| 14 | Mobile and offline field capture | Complete |
| 15 | HR development | Complete |
| 16 | Professional rollout | Complete |
| 17 | Project closeout | Complete |
| 18 | Finance and cash control | Complete |
| 19 | Programme and project controls | Complete |
| 20 | Resource planning and capacity control | Complete |
| 21 | Project communications and stakeholder control | Complete |
| 22 | Integrated compliance and policy control | Complete |
| 23 | Project data quality and readiness assurance | Complete |
| 24 | Delegated authority and approval limits | Complete |
| 25 | System change and release control | Complete |
| 26 | Service desk and support control | Complete |
| 27 | Operational knowledge and SOP support | Complete |
| 28 | Environmental and sustainability control | Complete |
| 29 | Tools and calibration control | Complete |
| 30 | Client document sharing | Complete |
| 31 | Vendor evidence collection portal | Complete |
| 32 | Business development and opportunity pipeline | Complete |
| 33 | Client account and relationship management | Complete |
| 34 | Contract control | Complete |
| 35 | Operational automation | Complete |
| 36 | Deployment, security and continuity hardening | Complete |

## Phase 1 - Core company platform

The foundation establishes Nthane Brothers, Head Office, branches, sites, departments, cost centres, reusable numbering, controlled documents, master data, settings, roles, permissions, approval workflows and audit history. Localisation defaults are Lesotho, LSL/Maloti and Africa/Maseru.

**Boundary:** branches/sites remain scopes inside the same company. Controlled documents are versioned evidence and should not be replaced by untracked attachments.

## Phase 2 - User access and security

Provides secure login, password policy/history, failed-login lockout, one-time reset tokens, server-side revocable sessions, inactivity/absolute expiry, user lifecycle, account suspension, scoped role assignments and security events. Access administration is protected from privilege escalation and the final active System Administrator is protected.

Core roles include System Administrator, Access Administrator, Head Office Executive, Branch Manager, Site Manager, Approver and Auditor/Read Only.

## Phase 3 - Workforce and payroll preparation

Provides employee master records, contracts, organisational ownership, leave, shifts, attendance, timesheets, earning/deduction components, payroll periods/runs, calculation, review, approval and export. Sensitive identity/banking fields are separated from ordinary workforce access. Human Resources Manager and Payroll Officer roles are included.

**Boundary:** payroll is prepared and controlled but salary payment is not executed. Statutory tax/pension/deduction rules must be configured from verified current requirements rather than assumed by the software.

## Phase 4 - Fleet and plant

Provides vehicle/plant register, ownership, assignments, serviceability, meter history, fuel, inspections, defects, licences/compliance, preventive maintenance, repair jobs, lifecycle cost and alerts. Fleet Manager, Fleet Officer and Fleet Inspector roles are included.

**Boundary:** the system records supplied fleet evidence and does not fabricate GPS, telematics or fuel-card transactions. Critical defects can make equipment unserviceable/out of service.

## Phase 5 - Tender management

Provides a branch-aware tender register, deadlines, team, bid/no-bid decision, compliance checklist, BOQ/estimate, securities, clarifications, commercial approval, submission approval, controlled submission evidence and award/loss outcome. Tender Manager, Estimator / Quantity Surveyor and Tender Coordinator roles are included.

**Boundary:** tender requirements, certificates, quotations, securities, competitor information and award notices must come from real supplied evidence. An awarded tender is deliberately handed to Phase 6; it does not become a live project automatically.

## Phase 6 - Project mobilisation

Converts an eligible awarded tender into a project, site and project cost centre. Provides project team, versioned budget baselines, programme/milestones, mobilisation checklist, handover documents, plant allocation, risk register and readiness approval. Project Manager and Project Controls roles are included.

Readiness requires the latest approved budget, complete weighted programme, project manager assignment, required checklist/documents, acceptable risk position and valid plant/serviceability evidence. Final approval freezes the readiness snapshot.

## Phase 7 - Site operations

Activates only readiness-approved projects/sites and records daily diaries, labour, plant usage, material movement evidence, measured progress, photos/documents, incidents and quality controls. Submitted daily reports use controlled approval and approved snapshots are immutable. Site Supervisor, HSE Officer and Quality Officer roles are included.

**Boundary:** site labour does not automatically become payroll; site material evidence does not replace the stores ledger; plant usage does not replace the fleet meter/fuel/maintenance ledger.

## Phase 8 - Procurement and stores

Provides suppliers, store locations, stock items/balances, requisitions, quotations, purchase orders, goods receiving, stock issue/return and transfers. Procurement Manager, Procurement Officer and Storekeeper roles are included.

**Boundary:** purchasing records require real supplier/quotation/delivery evidence. Stock cannot be silently created or moved without controlled transactions.

## Phase 9 - Subcontract management

Provides subcontractor register, project packages/scope, invitations, bids, evaluation, awards, contracts, variations, certificates, retention, supplied payment evidence and performance review. Subcontract Manager, Subcontract Officer and Site Commercial Officer roles are included.

**Boundary:** certificates record approved value; they do not execute payment. Award/bid/measurement/compliance facts must be supplied rather than invented.

## Phase 10 - Explainable assistants

Provides deterministic procurement/tender checks, quotation comparison, readable-document review, checklist suggestions, recorded-data questions, non-binding drafting and deadline feeds.

**Boundary:** assistance does not select a supplier, approve a transaction, submit a tender, send reminders externally or invent company credentials/technical claims. Staff remain responsible for original evidence and controlled decisions.

## Phase 11 - Cost and commercial control

Provides client contracts, project cost transactions, variations, valuations, invoices/receipts evidence, claims, cash-flow forecasts and project commercial position including procurement/subcontract commitments. Commercial Manager, Quantity Surveyor and Project Commercial Officer roles are included.

**Boundary:** actual cost corrections use controlled reversal rather than deletion. Claims and schedule/commercial indicators are records, not legal determinations. The module does not move money.

## Phase 12 - Management intelligence

Provides director/company portfolio view, branch comparison, tender pipeline, project health, fleet performance, materials intelligence, receivables/exposure and exception reporting.

**Boundary:** intelligence is derived from controlled source records and does not replace the owning module or approval workflow.

## Phase 13 - Document, HSE and quality assurance

Provides RFIs, site instructions, permits, toolbox talks, HSE inspections, quality non-conformances, corrective actions, controlled evidence and independent review.

**Boundary:** the preparer cannot independently close/review their own controlled record where no-self-review is enforced.

## Phase 14 - Mobile/offline field capture

Provides a phone-oriented local queue for daily diary, attendance, material delivery, plant use, photo and inspection evidence and synchronises submissions when connectivity returns.

**Boundary:** offline capture never auto-posts authoritative payroll, finance, stores, fleet or site transactions. Synchronised evidence still passes through normal review.

## Phase 15 - HR development

Provides recruitment, onboarding, training, licence/certification expiry, performance evidence and employee development actions.

**Boundary:** development/training evidence does not automatically change payroll or statutory status.

## Phase 16 - Professional rollout

Provides rollout readiness for backups, recovery tests, data migration, UAT, security review, user training and phased branch launch.

**Boundary:** production readiness must be supported by evidence, including tested restoration rather than the existence of an untested backup file.

## Phase 17 - Project closeout

Provides practical completion, handover checklist/evidence, final-account evidence, defects-liability tracking and controlled final closure.

**Boundary:** closure should not hide unresolved defects, commercial evidence or assurance actions; historical project evidence remains readable after closure.

## Phase 18 - Finance and cash control

Provides financial periods, chart of accounts, balanced journals, supplier invoices, payment requests/evidence, posting and AP/AR visibility. Finance Manager, Finance Officer and Finance Reviewer roles are included.

**Boundary:** journals must balance and can post only into eligible open periods after required approval. A payment request does not transfer money; evidence is recorded after real settlement.

## Phase 19 - Programme and project controls

Provides versioned approved programme baselines, WBS activities, dependencies, weighted progress, six-week lookahead, delay evidence and schedule alerts.

**Boundary:** critical-path and forecast indicators are planning support, not contractual entitlement or legal opinion. Delay records do not send notices automatically.

## Phase 20 - Resource planning and capacity control

Provides versioned resource plans for labour, plant, materials, subcontract and other demand; checks named employee/asset allocation conflicts; manages controlled resource requests and supplied fulfilment evidence.

**Boundary:** approval does not hire a person, assign/rent plant, reserve stock, create a purchase order or fulfil a request automatically.

## Phase 21 - Project communications and stakeholder control

Provides stakeholder register, correspondence, meeting minutes, actions, dispatch/response/completion evidence, approval, verification and audit.

**Boundary:** formal communication can be controlled and evidenced but the platform does not itself send the external message.

## Phase 22 - Integrated compliance and policy control

Provides versioned policies, source-referenced obligations, due dates, evidence reviews, corrective actions, approval and audit.

**Boundary:** legal/regulatory/company obligations must be created from verified supplied sources; the software does not invent legal requirements.

## Phase 23 - Project data quality and readiness assurance

Provides deterministic project snapshots, scores/findings, remediation evidence and independent verification.

**Boundary:** snapshots read source records; they do not silently correct them. Corrections happen in the owning module followed by a new snapshot.

## Phase 24 - Delegated authority and approval limits

Provides effective-dated Maloti approval limits by role, branch/site, module and transaction type.

**Boundary:** only approved/effective limits are evaluated and delegated authority never grants a module permission the user does not otherwise possess.

## Phase 25 - System change and release control

Provides change requests, impact/risk assessment, pilot/UAT/release evidence, approval and audit.

**Boundary:** production change approval is not a substitute for testing, evidence and controlled rollout.

## Phase 26 - Service desk and support control

Provides controlled service/support tickets, resolution evidence, independent verification and audit.

## Phase 27 - Operational knowledge and SOP support

Provides evidence-backed knowledge/SOP articles, independent publication, review dates and acknowledgements.

**Boundary:** outdated knowledge should be reviewed/superseded rather than silently edited after operational reliance.

## Phase 28 - Environmental and sustainability control

Provides project environmental plans, waste evidence, inspections, findings, remediation and independent verification.

**Boundary:** environmental/regulatory claims depend on supplied evidence and verified obligations.

## Phase 29 - Tools and calibration control

Provides tool custody, project/site issue and return, calibration certificates, due dates and independent verification.

**Boundary:** expired/out-of-calibration tools must not be presented as valid simply because the tool record exists.

## Phase 30 - Controlled client document sharing

Provides a staff workspace for preparing a share pack containing exactly one selected active document already classified `public`, independent publication, opaque token link, expiry/revocation and external view/download audit.

**Boundary:** no external account is created; internal dashboards, people, cost and approvals remain inaccessible. The platform does not send the link by email automatically.

## Phase 31 - Vendor evidence collection portal

Provides a staff request to one existing supplier/subcontractor for one evidence file, independent publication, opaque token link, public upload, internal review/verification, expiry/revocation and audit.

**Boundary:** the vendor receives no internal account and the received file does not automatically approve or modify the supplier/subcontractor master record.

## Phase 32 - Business development and opportunity pipeline

Provides branch-scoped opportunity registration, qualification, follow-up, staff-entered probability/value indicators and deliberate handoff to a real Phase 5 tender.

**Boundary:** qualification does not invent value/probability/client facts and does not create/submit/award a tender automatically.

## Phase 33 - Client account and relationship management

Provides branch/site-scoped client accounts, contacts, client-supplied feedback, remediation plans and independent verification.

**Boundary:** the module does not infer satisfaction, send client communications or modify a tender/project/contract.

## Phase 34 - Contract control

Provides dedicated project contract register, obligations, key dates, controlled contract evidence, actions, exceptions and audit.

**Boundary:** the system records verified contractual sources and does not provide legal interpretation.

## Phase 35 - Operational automation

Provides controlled automation of repeatable operating tasks where explicitly configured.

**Boundary:** automation remains subject to permissions and workflow rules and must never become a hidden bypass of required approval or evidence.

## Phase 36 - Deployment, security and continuity hardening

Provides production health/readiness controls, security headers, sensitive-endpoint rate limits, environment configuration, deployment documentation and continuity evidence.

**Boundary:** a technically running container is not by itself proof of production readiness; secrets, backup/recovery, security, monitoring and operational ownership must be configured for the deployment environment.

## Ownership rule for future development

Every future capability must preserve the shared company/branch/site/project ownership model and use the existing access, approval, controlled-document, numbering and audit structures. Integration work should feed evidence into the module that owns the business record instead of creating uncontrolled parallel data stores.

---

Nthane Brothers Construction Management System - developed by **Ithute Solution**.
