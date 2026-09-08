import type { ManualEntry } from "./system-manual";

export type ManualDetail = {
  useWhen: string;
  before: string[];
  screenAreas: string[];
  keyData: string[];
  controls: string[];
  sourceOfTruth: string;
  commonMistakes: string[];
  result: string;
  next: string[];
  example?: string;
};

const DETAILS: Record<string, ManualDetail> = {
  "/": {
    useWhen: "Use the Command Centre at the start of a work session to understand what needs attention across the company, branch or site before opening a specialist module.",
    before: ["Make sure you are signed in with the correct role and operational scope.", "If figures look wrong, identify the owning module before attempting to correct them."],
    screenAreas: ["Phase / operational status banner", "Company structure and organisation footprint", "Pending approvals and governance queues", "Counts for roles, documents, number sequences and other foundation records"],
    keyData: ["No new operational transaction is normally created here; this page summarises controlled data from other modules."],
    controls: ["Visibility follows your role and scope.", "Dashboard figures are management indicators and should not be edited as if they were source records."],
    sourceOfTruth: "The Command Centre is a summary layer. Correct the underlying record in its owning module.",
    commonMistakes: ["Treating dashboard totals as editable master data.", "Assuming a zero count means a feature is unavailable rather than simply having no records yet."],
    result: "You leave the screen knowing which area requires action and which operational module owns that action.",
    next: ["Open the relevant module from the sidebar.", "Use Management Intelligence for deeper reporting.", "Use Approval Authority or the owning control screen when an approval is pending."],
    example: "If pending approvals increase, identify whether they belong to Tender, Procurement, Project, Site or another controlled workflow, then open that module's control screen."
  },
  "/intelligence": {
    useWhen: "Use Management Intelligence when you need cross-module reporting, trends, exceptions or management-level comparison rather than transaction entry.",
    before: ["Know the period, branch, project or business question you are investigating.", "Confirm source modules have been updated before relying on the report."],
    screenAreas: ["Company/director overview", "Branch comparison", "Project health", "Tender pipeline", "Fleet and materials intelligence", "Commercial/finance exposure and exceptions"],
    keyData: ["Filters such as branch, project and reporting period", "KPI values and exception indicators", "Links back to source modules"],
    controls: ["Intelligence is read-only decision support.", "A management figure should be corrected only through the source transaction that produced it."],
    sourceOfTruth: "Each KPI is derived from its operational owner: tenders from Tender Management, fleet from Fleet & Plant, stock from Procurement & Stores, finance from Finance, and so on.",
    commonMistakes: ["Using stale source data and assuming the dashboard is wrong.", "Trying to reconcile a figure without applying the same branch/project/period filters."],
    result: "You identify trends, exceptions and records that require management attention.",
    next: ["Open the source module to investigate an exception.", "Export or report the filtered view where supported.", "Escalate unresolved exceptions to the responsible manager."]
  },
  "/projects": {
    useWhen: "Use Project Mobilisation after work has been awarded and Nthane Brothers must turn the award into a controlled delivery project.",
    before: ["Have the awarded tender/contract evidence available.", "Know the branch, site/location, project manager, dates, commercial baseline and mobilisation requirements.", "Confirm required employees and plant already exist in their master registers."],
    screenAreas: ["Project identity and award information", "Project team", "Budget baseline", "Programme/milestones", "Mobilisation checklist", "Handover documents", "Plant allocation", "Readiness and risks"],
    keyData: ["Project/client identity and contract value", "Branch/site and cost centre", "Project manager/team", "Budget lines", "Programme dates and milestones", "Required mobilisation evidence", "Plant assignments and risks"],
    controls: ["A project should not be treated as ready merely because it exists.", "Readiness depends on approved/current baseline information and required evidence.", "Maker/checker approval applies where configured."],
    sourceOfTruth: "This module owns mobilisation and the initial approved operating baseline. Daily delivery evidence belongs to Site Operations after mobilisation.",
    commonMistakes: ["Creating a project before award evidence is final.", "Leaving the newest budget/programme revision unapproved.", "Allocating unavailable or unserviceable plant.", "Assuming a checklist tick is sufficient without required evidence."],
    result: "A governed project baseline exists and can proceed to operational site execution once readiness is approved.",
    next: ["Use Project Control for governance.", "Use Project Risks for active risk management.", "Use Site Operations once mobilisation readiness is approved."]
  },
  "/projects/control": {
    useWhen: "Use Project Control when managers need to review project governance, mobilisation status, milestones, exceptions and control checkpoints.",
    before: ["Select the correct project and reporting context.", "Make sure project mobilisation and source records are current."],
    screenAreas: ["Project control indicators", "Readiness / milestone exceptions", "Governance actions and review status", "Links to source project records"],
    keyData: ["Project status", "Control exception", "Owner", "Due date or milestone", "Supporting evidence or explanation"],
    controls: ["Reviewers should not silently alter source evidence to make an exception disappear.", "Use independent review/approval where required."],
    sourceOfTruth: "Project Control reviews the project; Project Mobilisation, Programme, Site Operations, Commercial and other source modules own their underlying records.",
    commonMistakes: ["Closing a control item before its source record is corrected.", "Reviewing the wrong project or old reporting period."],
    result: "Project exceptions are visible, owned and followed through to correction or acceptance.",
    next: ["Correct the source record in the owning module.", "Use Data Quality for structured readiness findings.", "Escalate unresolved items to the Project/Branch Manager."]
  },
  "/projects/risks": {
    useWhen: "Use Project Risks whenever a threat or opportunity could affect safety, cost, time, quality, resources or delivery.",
    before: ["Understand the risk cause, possible event and consequence.", "Know who can realistically own the mitigation."],
    screenAreas: ["Risk register", "Likelihood / impact rating", "Owner and mitigation", "Target dates", "Open/closed/accepted status"],
    keyData: ["Cause", "Risk event", "Consequence", "Likelihood", "Impact", "Owner", "Mitigation", "Target date", "Evidence/status"],
    controls: ["Ratings should reflect the defined project risk method.", "Critical/open risks may affect mobilisation/readiness decisions."],
    sourceOfTruth: "This is the authoritative project risk register; issues that have already occurred may also require records in Site Operations, Assurance, Commercial or Programme Control.",
    commonMistakes: ["Writing vague risks without cause or consequence.", "Assigning an owner who cannot act.", "Closing a risk without evidence that the exposure is removed or formally accepted."],
    result: "The project has an actionable risk record with ownership, rating and mitigation.",
    next: ["Review risks at project meetings.", "Update mitigation status.", "Escalate critical risks into project control/readiness decisions."]
  },
  "/planning": {
    useWhen: "Use Programme Control to establish an approved programme, maintain activity progress, plan near-term work and record internal delay evidence.",
    before: ["Have project dates, WBS/activity structure, dependencies and approved planning assumptions.", "Know which programme version is currently approved."],
    screenAreas: ["Programme baselines", "Activities and dependencies", "Progress updates", "Look-ahead planning", "Delay records", "Schedule alerts"],
    keyData: ["Baseline/version", "Activity/WBS code", "Start/finish dates", "Predecessor", "Weight/progress", "Owner", "Delay event/date/evidence"],
    controls: ["Do not overwrite an approved baseline to hide slippage.", "Progress should not move backwards without a controlled correction.", "Delay records are internal control evidence, not legal entitlement."],
    sourceOfTruth: "Programme Control owns schedule baselines, activity progress and delay records. Formal contractual notices belong to Contract Control.",
    commonMistakes: ["Editing an old baseline instead of creating/using the correct revision.", "Recording a delay without dates/evidence.", "Treating critical-path or forecast indicators as automatic contractual entitlement."],
    result: "The project has an auditable schedule position and near-term plan.",
    next: ["Use Contract Control if a formal notice is required.", "Use Resource Capacity to check labour/plant demand.", "Use Site Operations to capture actual field progress."]
  },
  "/resources": {
    useWhen: "Use Resource Capacity to forecast labour, plant, material, subcontract or other demand and identify shortages or conflicts before execution.",
    before: ["Have an approved/current project programme where possible.", "Know required resource, quantity, dates and project/site demand."],
    screenAreas: ["Resource plans", "Demand lines", "Capacity/conflict indicators", "Resource requests", "Fulfilment evidence"],
    keyData: ["Resource type", "Named employee/asset where applicable", "Quantity/unit", "Required dates", "Project/site", "Allocation percentage", "Request/fulfilment evidence"],
    controls: ["Planning a resource does not hire, assign, reserve or procure it automatically.", "Overlapping named employee/asset demand should be resolved rather than ignored."],
    sourceOfTruth: "This module owns resource planning. Actual employee records belong to Workforce, asset assignments to Fleet, stock/procurement to Procurement & Stores.",
    commonMistakes: ["Treating a plan as proof the resource is actually available.", "Requesting more than the approved demand.", "Failing to update plan dates when the programme moves."],
    result: "Resource demand and shortages are visible before they become site disruption.",
    next: ["Fulfil labour through Workforce/management processes.", "Fulfil plant through Fleet.", "Fulfil materials through Procurement & Stores.", "Update the plan after material programme changes."]
  },
  "/communications": {
    useWhen: "Use Communications to keep a controlled record of stakeholders, incoming/outgoing correspondence, meetings and follow-up actions.",
    before: ["Know the project/site and stakeholder involved.", "Have the original correspondence or meeting evidence where applicable."],
    screenAreas: ["Stakeholder register", "Correspondence register", "Meetings/minutes", "Action items", "Dispatch/response evidence"],
    keyData: ["Stakeholder/contact", "Direction/type", "Subject", "Date", "Reference", "Owner", "Due date", "Evidence/document", "Response/closeout"],
    controls: ["Recording correspondence does not mean the system sent it externally.", "Formal contractual notices should follow Contract Control when required."],
    sourceOfTruth: "This module owns the project communication register. RFIs/site instructions may belong to Assurance/Document controls; contractual notices belong to Contract Control.",
    commonMistakes: ["Recording a letter without the real document/reference.", "Marking an action complete without evidence.", "Using ordinary correspondence where a formal contract notice is required."],
    result: "Project communication is traceable with responsible people and follow-up.",
    next: ["Track open actions.", "Link contractual events to Contract Control.", "Use meetings/actions during project review."]
  },
  "/compliance": {
    useWhen: "Use Compliance Control to record verified policies/obligations, assign owners and review whether supplied evidence meets the requirement.",
    before: ["Have a verified policy, contract, legal or company source.", "Know the scope, owner, due/review date and evidence requirement."],
    screenAreas: ["Policy/obligation register", "Applicability/scope", "Review dates", "Evidence and findings", "Corrective actions"],
    keyData: ["Requirement", "Source/reference", "Owner", "Effective/review date", "Evidence", "Status", "Corrective action"],
    controls: ["Do not invent legal requirements.", "A completed review must be supported by evidence appropriate to the obligation."],
    sourceOfTruth: "Compliance Control owns the obligation/review record; the underlying operational evidence remains in its owning module.",
    commonMistakes: ["Creating obligations from memory without a source.", "Using expired evidence.", "Closing a finding because a task was assigned rather than completed and verified."],
    result: "Applicable obligations are visible, owned and reviewed against evidence.",
    next: ["Correct operational gaps in the owning module.", "Attach verified evidence.", "Schedule the next review where recurring."]
  },
  "/data-quality": {
    useWhen: "Use Data Quality when management needs a structured snapshot of missing, inconsistent or unready project information across modules.",
    before: ["Source modules should contain the latest known records.", "Select the correct project/scope before generating or reviewing a snapshot."],
    screenAreas: ["Quality/readiness snapshot", "Findings by severity/module", "Remediation owner", "Verification", "Score/status"],
    keyData: ["Snapshot/project", "Finding", "Severity", "Owning module", "Remediation", "Evidence", "Verifier/status"],
    controls: ["Snapshots must not silently repair source records.", "A finding is closed only after the source is corrected and remediation is verified."],
    sourceOfTruth: "Data Quality diagnoses and verifies; the source module remains authoritative.",
    commonMistakes: ["Editing only the finding narrative instead of correcting the source record.", "Reusing an old snapshot after major project changes.", "Self-verifying remediation where independent review is required."],
    result: "Management has a defensible view of project data readiness and outstanding corrections.",
    next: ["Correct each finding in its source module.", "Record remediation evidence.", "Run/review a new snapshot when appropriate."]
  },
  "/authority": {
    useWhen: "Use Approval Authority to define who may approve a transaction value, in what module/scope and during what effective period.",
    before: ["Know the role, branch/site scope, module/transaction type and Maloti value threshold.", "Confirm the user also has the underlying operational permission."],
    screenAreas: ["Authority rules", "Role/scope", "Transaction/module", "Value limits", "Effective dates", "Approval status"],
    keyData: ["Role", "Branch/site", "Module", "Transaction type", "Maximum value", "Start/end date", "Evidence/approval"],
    controls: ["Authority does not grant a permission the role does not otherwise possess.", "Avoid overlapping or contradictory effective periods.", "Changes should be approved before becoming effective."],
    sourceOfTruth: "This module owns delegated value limits; user role/scope assignments remain in Access & Security.",
    commonMistakes: ["Giving a high value limit to a role that should not approve that transaction.", "Leaving expired authority active.", "Creating overlapping rules that are difficult to interpret."],
    result: "Approval decisions can be evaluated against a clear, effective-dated authority rule.",
    next: ["Test the rule using a representative transaction.", "Review authority when staff responsibilities change.", "Use Access & Security for role assignment changes."]
  },
  "/changes": {
    useWhen: "Use Change Control for significant system/process changes that need impact assessment, testing, approval and release evidence.",
    before: ["Define the requested change, business reason, affected users/modules and risk.", "Know how the change will be tested and rolled back if necessary."],
    screenAreas: ["Change request", "Impact/risk assessment", "Pilot/UAT evidence", "Approval", "Release/implementation evidence", "Closure"],
    keyData: ["Change description", "Reason", "Impact", "Risk", "Owner", "Test/UAT evidence", "Release date", "Verification"],
    controls: ["Approval is not a substitute for testing.", "Production changes should retain evidence and rollback/recovery considerations."],
    sourceOfTruth: "Change Control owns governance of the change; source code/deployment tools execute the actual technical change.",
    commonMistakes: ["Implementing before approval/testing.", "Closing without verifying the production result.", "Failing to identify affected workflows/data."],
    result: "The change has a traceable decision, test record and release/verification trail.",
    next: ["Complete testing/UAT.", "Release through the approved process.", "Record post-release verification and lessons."]
  },
  "/site-operations": {
    useWhen: "Use Site Operations every working day to capture what actually happened on a project site.",
    before: ["The project/site should be operationally ready.", "Know the reporting date/shift and have actual field evidence for labour, plant, materials, progress, incidents and quality items."],
    screenAreas: ["Daily site report header", "Labour", "Plant/equipment use", "Materials", "Measured progress", "Documents/photos", "HSE incidents", "Quality checks", "Submission"],
    keyData: ["Project/site/date/shift", "Work completed/planned/blockers", "Labour hours", "Plant hours/meters", "Material quantities", "Progress measurement", "Incident/quality facts", "Evidence"],
    controls: ["Do not invent attendance, weather, quantities, incidents or test results.", "Submitted reports should be reviewed independently.", "Approved report snapshots are auditable and should not be rewritten."],
    sourceOfTruth: "Site Operations owns daily field evidence. Payroll hours remain in Workforce; stock ledger remains in Procurement & Stores; fleet meter/fuel/maintenance remain in Fleet.",
    commonMistakes: ["Using site labour as if payroll has automatically been approved.", "Recording material consumption without keeping stores movements up to date.", "Submitting an activity day with no supporting evidence or work summary.", "Leaving serious incidents or failed quality items without actions."],
    result: "A complete, auditable daily record explains site activity for that date/shift.",
    next: ["Submit for Site Operations Control review.", "Update stores/fleet/payroll source records where required.", "Follow up incidents, quality findings and blockers."]
  },
  "/site-operations/control": {
    useWhen: "Use Site Operations Control to review submitted daily reports, HSE/quality exceptions and site operational governance.",
    before: ["Ensure the report is submitted and supporting evidence is available.", "Reviewer should be independent where maker/checker applies."],
    screenAreas: ["Pending report queue", "Report/evidence review", "Incident closeout", "Quality/NCR closeout", "Site activation/governance"],
    keyData: ["Report date/site", "Completeness", "Evidence", "Exceptions", "Reviewer decision", "Return reason or approval"],
    controls: ["Do not approve your own prepared report where no-self-approval applies.", "Return incomplete records instead of approving with undocumented assumptions."],
    sourceOfTruth: "This screen controls review; daily report details remain owned by Site Operations.",
    commonMistakes: ["Approving without opening supporting evidence.", "Rejecting without a clear correction reason.", "Closing HSE/quality items before corrective evidence is complete."],
    result: "Daily reports and field exceptions receive an auditable independent decision.",
    next: ["Approved reports feed management/commercial intelligence.", "Returned reports go back to the site preparer.", "Track open HSE/quality actions to closure."]
  },
  "/closeout": {
    useWhen: "Use Project Closeout when the project is approaching practical completion, handover, defects liability or final closure.",
    before: ["Know contract/project completion position.", "Collect handover, defects, commercial, document and assurance evidence.", "Identify all outstanding obligations."],
    screenAreas: ["Completion/closeout checklist", "Handover evidence", "Outstanding/snags", "Defects liability", "Final account/retention evidence", "Closure approval"],
    keyData: ["Completion dates/status", "Outstanding item", "Owner", "Due date", "Evidence", "Defect status", "Commercial closeout status"],
    controls: ["Do not close a project to hide open defects, claims, obligations or missing handover evidence.", "Final closure should be independently approved where configured."],
    sourceOfTruth: "Project Closeout owns the closure process; underlying finance/commercial/quality documents remain in their source modules.",
    commonMistakes: ["Closing before all handover documents are accepted.", "Ignoring retention/final account evidence.", "Losing visibility of defects after practical completion."],
    result: "The project transitions through completion and defects liability into controlled final closure.",
    next: ["Track defects to closure.", "Complete final commercial/finance actions.", "Retain project evidence for audit/history."]
  },
  "/mobile": {
    useWhen: "Use Field Capture when site staff need to capture supported evidence on a mobile device, including when connectivity is unreliable.",
    before: ["Open/synchronise while connected before going offline where possible.", "Confirm the device/user is working in the correct project/site context."],
    screenAreas: ["Local/offline queue", "Supported field capture forms", "Pending sync status", "Sync result/conflicts"],
    keyData: ["Project/site", "Capture type", "Local timestamp", "Evidence", "Sync status"],
    controls: ["Queued evidence must not silently become an authoritative payroll/finance/stores transaction.", "Review the queue before synchronising."],
    sourceOfTruth: "Field Capture is an evidence/sync layer. Authoritative records are created/reviewed in their operational modules.",
    commonMistakes: ["Assuming unsynchronised data is already on the server.", "Capturing under the wrong site before going offline.", "Deleting local evidence before successful sync."],
    result: "Field evidence is safely queued and synchronised into the controlled review process.",
    next: ["Synchronise when connected.", "Review imported evidence in the owning module.", "Resolve any rejected/conflicting sync item."]
  },
  "/tenders": {
    useWhen: "Use Tender Management from the moment a bid is formally being pursued through pricing, compliance, approval, submission evidence and outcome.",
    before: ["Have the real tender documents and deadlines.", "Know client/employer, reference, branch, submission method and bid team.", "Collect actual certificates, securities and quotation/estimate evidence."],
    screenAreas: ["Tender register", "Bid/no-bid", "Team", "Compliance checklist", "BOQ/estimate", "Pricing/margin", "Securities", "Clarifications", "Approval status", "Submission evidence", "Outcome"],
    keyData: ["Tender reference/client", "Issue/submission/clarification dates", "Checklist requirements", "BOQ quantities/rates", "Security details", "Clarifications", "Approval/submission evidence", "Outcome"],
    controls: ["Do not fabricate employer requirements, quotations, securities or submission acknowledgements.", "Complete required checklist and approval gates before controlled submission.", "Pricing calculations should come from entered BOQ/estimate data."],
    sourceOfTruth: "Tender Management owns bid preparation and submission evidence. Opportunities before formal bidding belong to Business Development; awarded work moves to Project Mobilisation.",
    commonMistakes: ["Entering deadlines from memory instead of the tender document.", "Marking a checklist item complete without evidence.", "Submitting before approvals/securities are ready.", "Recording 'submitted' without real submission evidence."],
    result: "The bid file shows exactly how the tender was prepared, approved, submitted and concluded.",
    next: ["Use Tender Control for independent gate review.", "Record award/loss outcome.", "Mobilise an awarded tender through Project Mobilisation."]
  },
  "/tenders/control": {
    useWhen: "Use Tender Control for management/commercial review of tender readiness, approvals and submission gates.",
    before: ["Tender preparation, pricing, checklist and required evidence should be substantially complete.", "Reviewer should have the correct authority and be independent where required."],
    screenAreas: ["Tender review queue", "Readiness/compliance summary", "Commercial/submission approval", "Exceptions and return reasons"],
    keyData: ["Tender", "Checklist completeness", "Price/margin", "Securities", "Clarifications", "Approval decision", "Comments"],
    controls: ["Do not approve incomplete evidence simply to meet a deadline.", "Check delegated authority/no-self-approval rules."],
    sourceOfTruth: "Tender Management owns preparation; Tender Control owns the independent review decision.",
    commonMistakes: ["Reviewing only price and ignoring compliance/securities.", "Approving your own prepared tender.", "Returning a tender without specific correction instructions."],
    result: "Tender readiness has a defensible independent decision.",
    next: ["Return deficiencies to the tender team.", "Approve submission when all gates pass.", "Record actual submission evidence in Tender Management."]
  },
  "/procurement": {
    useWhen: "Use Procurement & Stores for suppliers, material/service requests, quotations, purchase orders, goods receiving and stock control.",
    before: ["Know project/site/store, item/service specification, required date and budget/cost context.", "Use real supplier quotations and delivery evidence."],
    screenAreas: ["Supplier register", "Stores/items/balances", "Requisitions", "RFQ/quotations", "Comparison", "Purchase orders", "Goods receipts", "Issues/returns/transfers", "Stock ledger"],
    keyData: ["Supplier", "Item/specification", "Quantity/unit", "Required date", "Project/site/cost centre", "Quote price/tax/delivery", "PO terms", "Received/rejected quantity", "Store movement evidence"],
    controls: ["Do not create stock without a controlled receipt/adjustment.", "POs should follow approved requisitions/sourcing controls.", "Accepted receipt quantities drive stock increases.", "Negative stock and uncontrolled transfers should be prevented."],
    sourceOfTruth: "Procurement & Stores owns the supplier purchasing and stock ledger. Site Operations may record material use evidence but does not replace this ledger.",
    commonMistakes: ["Raising a vague requisition without specification.", "Comparing quotes with different scopes/units.", "Receiving the full PO when only part arrived.", "Recording site material use but forgetting the stores issue.", "Using a suspended/non-compliant supplier."],
    result: "Purchasing and stock movements are traceable from request through sourcing, order, receipt and inventory.",
    next: ["Use Procurement Control for approvals.", "Issue/transfer stock to the correct project/site.", "Link material evidence to Site Operations where appropriate."]
  },
  "/procurement/control": {
    useWhen: "Use Procurement Control to independently review requisitions, sourcing, purchase orders and procurement exceptions.",
    before: ["Requisition/PO should contain complete scope, quantity, value and supporting sourcing evidence.", "Reviewer must have appropriate authority."],
    screenAreas: ["Pending procurement approvals", "Quote/sourcing evidence", "Value/authority check", "Exceptions/waivers", "Decision history"],
    keyData: ["Request/PO number", "Supplier", "Value", "Quote count/comparison", "Budget/scope", "Authority", "Decision/comments"],
    controls: ["No-self-approval applies where configured.", "Low-value or quote-count exceptions need explicit policy/waiver evidence.", "Approval should not be used to cure missing specifications."],
    sourceOfTruth: "Procurement & Stores owns transactions; Procurement Control owns review/approval decisions.",
    commonMistakes: ["Approving based only on lowest price.", "Ignoring delivery/specification differences.", "Approving above delegated authority.", "Using verbal justification with no recorded evidence."],
    result: "Procurement commitments are independently reviewed before becoming binding internal records.",
    next: ["Return incomplete requests.", "Approve compliant items.", "Continue receiving/stock control in Procurement & Stores."]
  },
  "/subcontracts": {
    useWhen: "Use Subcontract Management for subcontractor qualification, packages, bids, awards/contracts, variations, certificates and performance evidence.",
    before: ["Have project scope/BOQ information.", "Use actual subcontractor registrations/compliance evidence and real bids.", "Know measurement/certification basis before preparing certificates."],
    screenAreas: ["Subcontractor register", "Work packages/scope lines", "Invitations/bids", "Evaluation", "Award/contract", "Variations", "Certificates/retention", "Payment proof", "Performance"],
    keyData: ["Subcontractor", "Trade/package", "Scope/quantities", "Bid price", "Evaluation", "Contract sum", "Variation", "Measured/certified value", "Retention/deductions", "Evidence"],
    controls: ["Awards/certificates follow maker/checker/authority controls.", "Certificates must not exceed approved contract position.", "Recording payment proof does not execute payment."],
    sourceOfTruth: "This module owns subcontract commitments and certificates. Actual finance posting/payment remains in Finance.",
    commonMistakes: ["Inviting/awarding an inactive subcontractor.", "Comparing incomplete bids.", "Certifying work without measurement evidence.", "Ignoring retention/approved variations.", "Treating payment proof entry as a banking action."],
    result: "Subcontract commercial history is controlled from prequalification through final certification/performance.",
    next: ["Use Subcontract Control for approvals.", "Feed approved commitments/costs into commercial oversight.", "Record real payment evidence after the external payment process."]
  },
  "/subcontracts/control": {
    useWhen: "Use Subcontract Control for independent review of package awards, contracts, variations and certificates.",
    before: ["Open the complete package/bid/contract/certificate evidence.", "Confirm value and delegated authority."],
    screenAreas: ["Approval queue", "Bid/evaluation evidence", "Contract/variation position", "Certificate/retention review", "Exceptions"],
    keyData: ["Package/contract", "Selected bid", "Value", "Approved variations", "Previous/cumulative certification", "Retention/deductions", "Decision"],
    controls: ["Review independently.", "Do not approve beyond current contract/variation ceiling.", "Return unsupported measurement or commercial assumptions."],
    sourceOfTruth: "Subcontract Management owns source records; this screen records the control decision.",
    commonMistakes: ["Approving a certificate without checking cumulative certified value.", "Ignoring open variation status.", "Approving your own preparation."],
    result: "Subcontract commitments/certificates have an auditable maker/checker decision.",
    next: ["Return corrections or approve.", "Record subsequent payment evidence only after real payment.", "Track subcontract performance."]
  },
  "/commercial": {
    useWhen: "Use Cost & Commercial to control client contracts, project cost position, valuations, claims, variations and cash-flow/commercial exposure.",
    before: ["Confirm the project/client contract and current approved commercial baseline.", "Have measurement, cost, variation, claim and invoice evidence."],
    screenAreas: ["Client contract", "Budget/commitment/cost position", "Variations", "Valuations", "Claims", "Invoices/receipts evidence", "Cash flow", "Commercial dashboard"],
    keyData: ["Contract sum", "Cost code/amount", "Variation value/status", "Measured value", "Previous/cumulative valuation", "Claim basis/evidence", "Forecast receipts/payments"],
    controls: ["Do not delete historical actual costs to correct mistakes; use controlled correction/reversal patterns where implemented.", "Commercial indicators are not legal determinations.", "Formal notices belong in Contract Control."],
    sourceOfTruth: "Commercial owns project commercial position. Procurement/Subcontracts/Finance remain owners of their transactions; Programme owns schedule evidence.",
    commonMistakes: ["Mixing forecast with actual cost.", "Preparing valuation without measurement evidence.", "Treating an unapproved variation as fully authorised.", "Using a claim record as if it were a formal notice."],
    result: "Management can see contract value, commitments, actual/forecast position, valuations and exposure.",
    next: ["Use Contract Control for notices/contract events.", "Use Finance for accounting/payment evidence.", "Use Intelligence for portfolio reporting."]
  },
  "/finance": {
    useWhen: "Use Finance & Cash Control for accounting periods, chart accounts, journals, invoices, payment requests/evidence and controlled posting.",
    before: ["Confirm the correct financial period and account coding.", "Have original invoice/journal/payment support.", "Know whether approval is required before posting/payment evidence."],
    screenAreas: ["Financial periods", "Chart of accounts", "Journals", "Supplier/client invoices", "Payment requests", "Payment evidence", "Posting/review status"],
    keyData: ["Period", "Account", "Debit/credit", "Invoice reference/date/value", "Supplier/client", "Payment request", "Approval", "Bank/payment evidence reference"],
    controls: ["Journals must balance.", "Closed/ineligible periods should not accept posting.", "The system does not transfer money.", "Independent finance review applies where configured."],
    sourceOfTruth: "Finance owns accounting/posting/payment evidence. Procurement and Commercial retain their originating operational/commercial records.",
    commonMistakes: ["Posting into the wrong period.", "Using the wrong account/cost context.", "Recording payment evidence before real payment occurred.", "Approving your own finance preparation.", "Duplicating an invoice reference."],
    result: "Financial records have a controlled period, coding, approval and evidence trail.",
    next: ["Post approved entries.", "Record real payment evidence after settlement.", "Reconcile finance views with Commercial/Procurement source records."]
  },
  "/assistants": {
    useWhen: "Use Algorithmic Assistants when you want explainable checks, comparisons or drafting support based on already recorded tender/procurement evidence.",
    before: ["Make sure the source documents/records are readable and current.", "Understand that the output is decision support, not approval."],
    screenAreas: ["Assistant selection", "Source inputs", "Rule/explanation", "Recommendation/draft", "Analysis history"],
    keyData: ["Source record/document", "Requested analysis", "Rule/version", "Generated result", "User review"],
    controls: ["The assistant must not select a supplier, approve a purchase, submit a tender or fabricate evidence.", "Human users remain responsible for checking original sources."],
    sourceOfTruth: "Tender and Procurement source modules remain authoritative; assistant output is an analysis snapshot.",
    commonMistakes: ["Treating a recommendation as approval.", "Expecting image-only/scanned documents to be understood without readable text.", "Using outdated source records."],
    result: "You receive an explainable recommendation/check that can support—but not replace—the controlled workflow.",
    next: ["Verify against original evidence.", "Make the real decision in Tender/Procurement.", "Retain the analysis where useful for audit."]
  },
  "/contract-control": {
    useWhen: "Use Contract Control for formal contractual notices, instructions, extension-related events, variation events and contract deadlines that need a controlled record.",
    before: ["Have the signed contract/verified clause or instruction source.", "Know event date, notice requirement, due date, addressee and supporting evidence.", "Get commercial/legal review where the matter requires professional interpretation."],
    screenAreas: ["Contract register/context", "Notices/events", "Due dates", "Instructions/variations", "Evidence", "Issue/review status"],
    keyData: ["Contract/project", "Event date", "Notice type", "Subject", "Contract reference/clause", "Due date", "Narrative", "Evidence", "Reviewer/issue status"],
    controls: ["The system records the notice and issue evidence; it does not provide legal entitlement by itself.", "Maker/checker applies to controlled issue where configured."],
    sourceOfTruth: "Contract Control owns formal contract event/notice records. Programme delays and Commercial claims can provide supporting evidence but do not replace the notice.",
    commonMistakes: ["Waiting until after a notice deadline to create the record.", "Using Programme delay notes as a substitute for a formal notice.", "Issuing without correct contract reference/addressee/evidence.", "Self-issuing where independent review is required."],
    result: "The contract file contains a traceable event, deadline, notice content and review/issue evidence.",
    next: ["Track responses and follow-up.", "Link commercial claims/variations as appropriate.", "Update Programme/Communications with related operational evidence."]
  },
  "/workforce": {
    useWhen: "Use Workforce for employee master records, employment contracts, leave, attendance, timesheets and payroll preparation.",
    before: ["Have verified employee identity/contact/employment information.", "Know branch/site/department/cost centre and employment terms.", "Configure payroll/leave policies before relying on calculations."],
    screenAreas: ["Employees", "Contracts", "Leave", "Attendance", "Timesheets", "Payroll periods/runs", "Payroll-sensitive details", "Exports/review"],
    keyData: ["Employee identity/contact", "Employment status", "Contract/pay basis/rate", "Bank/payroll-sensitive details", "Leave type/dates", "Attendance/hours", "Timesheet project/cost centre", "Payroll components"],
    controls: ["Sensitive banking/payroll data requires appropriate permissions.", "Timesheets/payroll use approval controls.", "Payroll preparation does not execute salary payments.", "Do not hard-code unverified statutory deductions."],
    sourceOfTruth: "Workforce owns employee/time/payroll preparation. Site Operations labour is field evidence and should not silently replace payroll timesheets.",
    commonMistakes: ["Creating duplicate employees.", "Missing contract/branch/cost-centre information.", "Using unapproved timesheets in payroll.", "Assuming site diary hours are payroll-approved.", "Entering statutory rates without verified configuration."],
    result: "Employee and payroll-preparation records are complete, scoped and reviewable.",
    next: ["Use Workforce Setup for reference configuration.", "Review/approve timesheets and payroll.", "Use HR Development for training/credentials."]
  },
  "/workforce/setup": {
    useWhen: "Use Workforce Setup before operational HR/payroll processing when reference values, leave/payroll configuration or reusable workforce settings must be maintained.",
    before: ["Know the company-approved policy values.", "Verify any legal/statutory values from current authoritative sources before entry."],
    screenAreas: ["Workforce reference data", "Leave/payroll configuration", "Reusable options/policies"],
    keyData: ["Reference name/code", "Effective value", "Dates", "Policy basis", "Active status"],
    controls: ["Configuration changes can affect many employees/payroll runs.", "Do not invent statutory values or silently change historical meaning."],
    sourceOfTruth: "This module owns workforce configuration; individual employee transactions remain in Workforce.",
    commonMistakes: ["Changing configuration in the middle of a payroll cycle without review.", "Using outdated statutory assumptions.", "Deleting reference values already used historically."],
    result: "Workforce processes use approved, reusable configuration.",
    next: ["Return to Workforce for employee/time/payroll processing.", "Document policy changes through Change/Compliance controls if material."]
  },
  "/development": {
    useWhen: "Use HR Development for recruitment/onboarding support, training, competencies, licences/certificates and employee development tracking.",
    before: ["Employee should exist in Workforce where applicable.", "Have real training/credential evidence and validity dates."],
    screenAreas: ["Recruitment/onboarding", "Training/development", "Credentials/licences", "Expiry alerts", "Performance/development actions"],
    keyData: ["Employee/candidate", "Training/credential", "Provider/reference", "Issue/completion date", "Expiry", "Evidence", "Development action"],
    controls: ["A record does not certify competence unless supported by valid evidence.", "Training records do not automatically change payroll/employment status."],
    sourceOfTruth: "HR Development owns learning/credential evidence; employment master data remains in Workforce.",
    commonMistakes: ["Recording certificates without expiry/evidence.", "Keeping expired credentials as if valid.", "Duplicating the employee instead of linking the existing record."],
    result: "Management can see capability, training and credential gaps.",
    next: ["Renew expiring credentials.", "Plan development actions.", "Use Workforce for employment/payroll changes."]
  },
  "/fleet": {
    useWhen: "Use Fleet & Plant for the complete operational history of vehicles and plant: registration, assignment, fuel, inspections, defects, compliance, maintenance and cost.",
    before: ["Have asset registration/serial/VIN details and ownership data.", "Know meter basis and current reading.", "Use real fuel receipts, inspection evidence and maintenance invoices."],
    screenAreas: ["Asset register", "Assignments", "Meter readings", "Fuel", "Inspections", "Defects", "Compliance", "Maintenance", "Lifecycle cost"],
    keyData: ["Asset identity", "Branch/site/project assignment", "Odometer/engine hours", "Fuel litres/unit price/receipt", "Inspection checklist", "Defect severity", "Licence/insurance expiry", "Maintenance cost/downtime"],
    controls: ["Meters should not move backwards.", "Critical defects can make an asset unserviceable.", "Do not fabricate telematics/fuel-card data.", "Maintenance/inspection approvals apply where configured."],
    sourceOfTruth: "Fleet owns asset condition, fuel and maintenance history. Site Operations may record daily plant use but does not replace Fleet records.",
    commonMistakes: ["Fuel entry against the wrong asset/meter.", "Assigning one asset to overlapping locations.", "Ignoring critical defects.", "Letting licence/insurance expire.", "Recording site plant use without updating relevant fleet meter/maintenance evidence."],
    result: "Each asset has a traceable availability, cost, compliance and maintenance history.",
    next: ["Use Fleet Control for exceptions/approval.", "Resolve defects before deployment.", "Use Resource Capacity/Projects for planning while Fleet remains the asset owner."]
  },
  "/fleet/control": {
    useWhen: "Use Fleet Control to review readiness, overdue maintenance/compliance, critical defects, cost exceptions and governance decisions.",
    before: ["Fleet source records should be current.", "Open the affected asset evidence before making a control decision."],
    screenAreas: ["Readiness/availability", "Overdue maintenance", "Compliance expiry", "Defect exceptions", "Cost/assignment review"],
    keyData: ["Asset", "Exception", "Due/expiry date", "Serviceability", "Cost/status", "Reviewer action"],
    controls: ["Do not clear an exception without correcting the Fleet source record.", "Independent review applies where configured."],
    sourceOfTruth: "Fleet & Plant owns underlying asset records; Fleet Control governs exceptions.",
    commonMistakes: ["Manually dismissing an alert without renewal/repair evidence.", "Returning an asset to service before critical defects are closed."],
    result: "Fleet exceptions have clear ownership and resolution evidence.",
    next: ["Correct the asset in Fleet & Plant.", "Verify repair/compliance.", "Return the asset to service only when evidence supports it."]
  },
  "/assurance": {
    useWhen: "Use HSE & Quality for inspections, incidents/assurance findings, RFIs, nonconformances and corrective-action evidence that require formal quality/safety control.",
    before: ["Select the correct project/site and assurance type.", "Have the original observation, specification/reference and evidence."],
    screenAreas: ["HSE/quality inspections", "Findings/NCRs", "Corrective actions", "Evidence", "Verification/closeout", "RFIs/site instructions where implemented"],
    keyData: ["Inspection/type", "Reference/specification", "Finding", "Severity/result", "Owner", "Due date", "Corrective action", "Evidence", "Verifier"],
    controls: ["Failed/serious findings require documented action.", "Do not self-verify where independent review is required.", "Evidence must reflect real site conditions."],
    sourceOfTruth: "Assurance owns formal HSE/quality control records. Daily site reporting may reference related facts but does not replace these controlled records.",
    commonMistakes: ["Closing a finding when work is only planned.", "Missing evidence/reference.", "Using generic descriptions that cannot be verified.", "Self-closing controlled actions."],
    result: "Safety/quality issues are documented, corrected and independently verified.",
    next: ["Track corrective actions.", "Link significant issues to Site/Project Control.", "Use Compliance for recurring obligation-level review."]
  },
  "/support": {
    useWhen: "Use Support Centre when a user needs help, encounters a system/process problem or needs an approved SOP/knowledge article.",
    before: ["Search existing knowledge first.", "Capture the exact screen, action, time and error/behaviour.", "Take a screenshot or supporting evidence when useful."],
    screenAreas: ["Knowledge/SOP search", "Support tickets", "Priority/status", "Resolution evidence", "Verification/closure"],
    keyData: ["Affected user/scope", "Screen/route", "Problem", "Steps to reproduce", "Priority", "Evidence", "Resolution", "Verifier"],
    controls: ["Do not close a ticket merely because a workaround was suggested; verify resolution where required.", "Knowledge articles should be controlled/reviewed before being treated as SOP."],
    sourceOfTruth: "Support Centre owns support history and published operational guidance; source business records remain in their modules.",
    commonMistakes: ["Submitting 'system not working' without screen/error details.", "Creating duplicate tickets for the same known issue.", "Publishing outdated guidance."],
    result: "The issue has a traceable owner, resolution and reusable learning where appropriate.",
    next: ["Verify the fix.", "Publish/update knowledge if the resolution is reusable.", "Use Change Control when a system change is required."]
  },
  "/environment": {
    useWhen: "Use Environment & Sustainability for project environmental plans, waste evidence, environmental inspections and remediation.",
    before: ["Know the project/site requirement and verified environmental source/plan.", "Have actual waste/inspection evidence."],
    screenAreas: ["Environmental plans", "Waste register", "Inspections", "Findings/remediation", "Evidence/verification"],
    keyData: ["Project/site", "Environmental aspect/requirement", "Waste type/quantity", "Inspection finding", "Owner", "Due date", "Evidence"],
    controls: ["Do not claim legal/environmental compliance without verified requirements/evidence.", "Hazardous or controlled waste evidence must reflect the real external process."],
    sourceOfTruth: "This module owns environmental operational records; broader obligations may also be tracked in Compliance.",
    commonMistakes: ["Entering estimated waste as actual without distinction.", "Closing findings without remediation evidence.", "Using an expired plan/review."],
    result: "Environmental actions and evidence are traceable by project/site.",
    next: ["Close remediation.", "Update Compliance obligations if relevant.", "Report significant issues through project/HSE governance."]
  },
  "/tools": {
    useWhen: "Use Tools & Calibration for controlled small tools/equipment, custody, project/site issue/return and calibration validity.",
    before: ["Have unique tool identity/serial information.", "Know whether calibration is required and have the certificate where applicable."],
    screenAreas: ["Tool register", "Custody/issue", "Return/condition", "Calibration certificates", "Due/expired alerts"],
    keyData: ["Tool identity", "Serial", "Custodian", "Project/site", "Issue/return date", "Condition", "Calibration date/expiry", "Certificate"],
    controls: ["A calibration-required tool should not be presented as deployable when calibration is missing/expired.", "Custody changes should be recorded."],
    sourceOfTruth: "Tools owns small-tool custody/calibration; vehicles/heavy plant remain in Fleet.",
    commonMistakes: ["Using Fleet for small calibrated tools.", "Failing to record returns.", "Uploading a certificate without expiry/reference.", "Issuing an expired calibration tool."],
    result: "The organisation can identify who has each controlled tool and whether it is valid for use.",
    next: ["Return/transfer custody properly.", "Renew calibration.", "Investigate lost/damaged tools through the appropriate governance process."]
  },
  "/client-portal": {
    useWhen: "Use Client Portal when staff need to deliberately share approved public-classified project evidence with an external client through a controlled link.",
    before: ["Confirm the document is the correct active approved/public document.", "Confirm client/recipient, expiry and message.", "Do not include internal/confidential information."],
    screenAreas: ["Share pack preparation", "Selected document", "Client/expiry", "Publication approval", "Link status", "Access audit/revocation"],
    keyData: ["Project/site", "Client", "Document", "Message", "Expiry", "Publisher/reviewer", "Published/revoked status"],
    controls: ["Only deliberately selected public evidence should be shared.", "Publication may require independent approval.", "The system creates a link; it does not guarantee the external message was sent/received."],
    sourceOfTruth: "Client Portal owns controlled publication; Document Control owns the underlying document.",
    commonMistakes: ["Sharing the wrong revision.", "Selecting confidential/internal evidence.", "Leaving a link active longer than needed.", "Assuming link creation equals client receipt."],
    result: "The client can access only the intended published evidence within the controlled link boundary.",
    next: ["Send the link through the real approved communication channel.", "Monitor/revoke when no longer needed.", "Record relevant correspondence in Communications."]
  },
  "/vendor-portal": {
    useWhen: "Use Vendor Portal when Procurement/Subcontracts needs a supplier or subcontractor to upload requested evidence without giving them an internal account.",
    before: ["Vendor must already exist in the relevant internal register.", "Define exactly one evidence request, instructions and due/expiry date."],
    screenAreas: ["Evidence requests", "Vendor/request details", "Publication/link", "Received upload", "Internal review/verification", "Expiry/revocation"],
    keyData: ["Supplier/subcontractor", "Evidence type", "Instructions", "Due/expiry", "Submitted file/contact", "Verifier/status"],
    controls: ["Public link exposes only the named request.", "Received evidence does not automatically approve/compliance-enable the vendor.", "Internal verification is required."],
    sourceOfTruth: "Vendor Portal owns the evidence request/upload flow; supplier/subcontractor master status remains in Procurement/Subcontracts.",
    commonMistakes: ["Creating a request for the wrong vendor.", "Treating uploaded evidence as verified.", "Leaving expired/revoked links in circulation.", "Requesting unnecessary sensitive data."],
    result: "External evidence is collected through a narrow, auditable channel and awaits internal verification.",
    next: ["Review/verify evidence.", "Update supplier/subcontractor status only through its owning module.", "Reissue a new request if evidence must be corrected."]
  },
  "/business-development": {
    useWhen: "Use Business Development for leads/opportunities before they become a formal tender.",
    before: ["Have real client/opportunity information and a responsible owner.", "Know next action, expected bid date/value/probability only where supplied or reasonably assessed by staff."],
    screenAreas: ["Opportunity register", "Pipeline stage", "Qualification", "Client/value/probability", "Owner/next action", "Tender handoff"],
    keyData: ["Client", "Opportunity", "Source", "Scope", "Estimated value", "Probability", "Stage", "Owner", "Next action/date", "Qualification evidence"],
    controls: ["Pipeline values/probabilities are decision support, not guaranteed revenue.", "Do not create a tender automatically before the opportunity qualifies."],
    sourceOfTruth: "Business Development owns pre-tender opportunity history; formal bid preparation moves to Tender Management.",
    commonMistakes: ["Leaving opportunities without next actions.", "Inflating probability/value without basis.", "Duplicating a client/opportunity.", "Using this screen after the work is already a formal tender instead of handing it off."],
    result: "Management sees a current, owned opportunity pipeline with clear next actions.",
    next: ["Qualify the opportunity.", "Create/link the formal tender when ready.", "Use Client Accounts for relationship information."]
  },
  "/client-accounts": {
    useWhen: "Use Client Accounts for controlled client organisation/contact information, relationship activity and client-supplied feedback.",
    before: ["Have verified client/contact details.", "Know branch/site ownership and responsible account manager."],
    screenAreas: ["Client account", "Contacts", "Relationship notes/interactions", "Feedback", "Remediation/verification"],
    keyData: ["Legal/trading name", "Contact details", "Sector", "Account manager", "Interaction", "Feedback score/comment", "Remediation owner/evidence"],
    controls: ["Do not infer satisfaction or invent feedback.", "This module does not replace tender/project/contract/correspondence records."],
    sourceOfTruth: "Client Accounts owns relationship master/feedback; operational work remains in Business Development, Tender, Project, Commercial and Communications.",
    commonMistakes: ["Creating the same client repeatedly.", "Recording internal opinion as client feedback.", "Closing remediation without independent verification."],
    result: "Client relationships and supplied feedback are visible without mixing them with transaction modules.",
    next: ["Use Business Development for new opportunities.", "Use Communications for formal correspondence.", "Use relevant operational modules for project/tender actions."]
  },
  "/access": {
    useWhen: "Use Access & Security to create/suspend users, assign roles/scopes, reset passwords, review sessions and revoke access.",
    before: ["Know the person's job responsibilities and minimum required scope.", "Understand company/branch/site scope before assigning roles.", "Verify identity before performing sensitive recovery actions."],
    screenAreas: ["User accounts", "Role/scope assignments", "Account status", "Password reset", "Sessions", "Security events"],
    keyData: ["Username/email/name", "Active/suspended status", "Role", "Company/branch/site scope", "Temporary/reset token", "Session/security event"],
    controls: ["Use least privilege.", "Protect the final active System Administrator.", "Reset tokens are one-time/expiring.", "Revoke sessions when access should stop immediately."],
    sourceOfTruth: "Access & Security owns internal user identity, roles and sessions. Approval Authority separately controls transaction value limits.",
    commonMistakes: ["Giving company-wide scope when branch/site scope is enough.", "Sharing accounts.", "Leaving former staff active.", "Using a role as a substitute for delegated value authority.", "Sending reset tokens to an unverified recipient."],
    result: "The user has only the access required for their responsibilities and scope.",
    next: ["Ask the user to sign in and verify access.", "Use Approval Authority for value limits.", "Revoke roles/sessions promptly when responsibilities change."]
  },
  "/rollout": {
    useWhen: "Use Professional Rollout to evidence migration, UAT, training, backup/recovery, security and go-live readiness.",
    before: ["Define rollout scope/branch and readiness criteria.", "Collect real test, training, backup/restore and security evidence."],
    screenAreas: ["Readiness areas", "Evidence items", "Owner/status", "Independent verification", "Launch/go-live gate"],
    keyData: ["Control area", "Requirement", "Owner", "Status", "Evidence", "Verifier", "Date/result"],
    controls: ["A backup file alone is not proof of recoverability—test restoration.", "Do not mark UAT/training/security ready without evidence.", "Launch decisions should be based on completed required controls."],
    sourceOfTruth: "Rollout owns implementation-readiness evidence; production systems/tools remain the source of actual technical state.",
    commonMistakes: ["Using screenshots instead of meaningful test evidence.", "Marking training complete without attendance/competence confirmation.", "Skipping recovery tests.", "Launching with unresolved critical readiness items."],
    result: "Go-live/branch rollout decisions are supported by traceable evidence.",
    next: ["Resolve failed readiness items.", "Obtain independent verification.", "Record post-launch review and continuity tests."]
  },
  "/automation": {
    useWhen: "Use Operational Automation to configure auditable alert/reminder rules for repeatable operational conditions.",
    before: ["Define the exact trigger, intended recipients/channel and what the automation is allowed to do.", "Confirm the rule will not bypass approval or alter controlled records silently."],
    screenAreas: ["Automation rules", "Trigger/condition", "Delivery channel", "Status", "Execution/audit history"],
    keyData: ["Rule name", "Trigger", "Scope", "Recipient/channel", "Active status", "Last/next execution or result"],
    controls: ["Automation should notify or assist, not become a hidden approval bypass.", "External delivery depends on the configured real channel/integration."],
    sourceOfTruth: "Automation owns rule configuration; the business record that triggers the rule remains in its operational module.",
    commonMistakes: ["Creating vague rules that fire too often.", "Using automation to change controlled records without approval.", "Assuming a configured channel is working without testing.", "Leaving obsolete rules active."],
    result: "A repeatable alert/action rule is configured with a visible audit trail.",
    next: ["Test with a safe condition.", "Review delivery results.", "Disable/update rules when business processes change."]
  },
  "/login": {
    useWhen: "Use Sign In to authenticate an existing internal user and enter the system with their assigned roles/scopes.",
    before: ["Use your own username/email and password.", "If following a manual link, keep the return-to destination in the URL so the system can return you after login."],
    screenAreas: ["Username/email", "Password", "Sign-in status/error", "Password-reset link", "Documentation link"],
    keyData: ["Username/email", "Password"],
    controls: ["Do not share credentials.", "Repeated failed attempts may trigger lockout depending on security policy."],
    sourceOfTruth: "Access & Security owns the user account, password/reset and session state.",
    commonMistakes: ["Using another employee's account.", "Removing the returnTo parameter when trying to open a manual-linked screen.", "Repeatedly guessing a forgotten password instead of using the controlled reset process."],
    result: "A valid server-side session is established and the user enters the authorised application scope.",
    next: ["Open the requested screen.", "Use Reset Password if a valid reset token has been issued.", "Contact an Access Administrator when locked out."]
  },
  "/reset-password": {
    useWhen: "Use Reset Password only when an authorised administrator has issued a valid one-time reset token.",
    before: ["Obtain the reset token through the approved identity-verified support process.", "Choose a password that satisfies current policy."],
    screenAreas: ["Reset token", "New password", "Confirmation", "Success/error message", "Back to sign in"],
    keyData: ["One-time token", "New password", "Password confirmation"],
    controls: ["Tokens expire and are one-time.", "Never send a new password back to an administrator."],
    sourceOfTruth: "Access & Security owns password policy and token validity.",
    commonMistakes: ["Using an expired/already-used token.", "Copying extra spaces into the token.", "Choosing a password that does not meet policy.", "Sharing the new password."],
    result: "The account receives a new compliant password and the token can no longer be reused.",
    next: ["Return to Sign In.", "Ask an Access Administrator for a new token if the existing token is invalid."]
  },
  "/setup": {
    useWhen: "Use First-Time Setup only on a new installation before the company foundation and first System Administrator exist.",
    before: ["Know the official company name/code, Head Office details and first administrator identity.", "Confirm this is genuinely a fresh installation."],
    screenAreas: ["Company foundation", "Head Office", "Company contact/location", "First System Administrator"],
    keyData: ["Company/legal name", "Code", "Head Office name/code/district", "Contact/address", "Administrator name/username/email/phone/password"],
    controls: ["This is bootstrap—not daily administration.", "Protect the first System Administrator credentials and move ongoing user provisioning to Access & Security."],
    sourceOfTruth: "Foundation records created here become the company/Head Office master; ongoing user administration belongs to Access & Security.",
    commonMistakes: ["Running setup on an already established environment.", "Using temporary/incorrect company identity data.", "Creating a weak/shared administrator account."],
    result: "The installation has the Nthane Brothers company foundation and first secure administrator.",
    next: ["Sign in.", "Create controlled users/roles in Access & Security.", "Complete required organisational setup and rollout readiness."]
  },
  "/vendor-submissions/[token]": {
    useWhen: "Use this public page only when a supplier/subcontractor has received a valid evidence-request link.",
    before: ["Open the exact issued link.", "Prepare only the requested evidence and correct vendor contact details.", "Check the due/expiry information shown."],
    screenAreas: ["Request summary", "Instructions", "Vendor contact fields", "File upload", "Submission result"],
    keyData: ["Valid token", "Contact details", "Requested evidence file"],
    controls: ["The link gives no internal system account or wider data access.", "Submission does not mean internal verification/approval."],
    sourceOfTruth: "The external page receives the evidence; internal verification and vendor status remain in Vendor Portal/Procurement/Subcontracts.",
    commonMistakes: ["Using an expired/revoked link.", "Uploading the wrong document.", "Assuming upload means compliance is approved.", "Sharing the link unnecessarily."],
    result: "The requested evidence is received for internal review.",
    next: ["Internal staff review the submission in Vendor Portal.", "A new request/link may be required if evidence is rejected or expired."]
  }
};

const GROUP_DEFAULTS: Record<string, Pick<ManualDetail, "controls" | "commonMistakes" | "next">> = {
  "Overview": {
    controls: ["Respect role/scope visibility and correct records in their owning module."],
    commonMistakes: ["Treating a summary screen as the editable source of truth."],
    next: ["Open the owning operational module for action."]
  },
  "Projects & sites": {
    controls: ["Keep project/site scope correct and retain evidence for controlled decisions."],
    commonMistakes: ["Working under the wrong project/site or using stale baseline information."],
    next: ["Continue the project workflow in the next owning module."]
  },
  "Commercial": {
    controls: ["Use actual commercial evidence, maker/checker approval and delegated authority where required."],
    commonMistakes: ["Treating forecasts, drafts or unapproved values as final commitments."],
    next: ["Complete independent review and update the relevant source record."]
  },
  "People & control": {
    controls: ["Use the correct role/scope and preserve audit/evidence requirements."],
    commonMistakes: ["Bypassing the owning master record or approval path."],
    next: ["Complete the controlled follow-up in the owning module."]
  },
  "Authentication & external": {
    controls: ["Protect credentials/tokens and expose only the intended public boundary."],
    commonMistakes: ["Sharing credentials/tokens or assuming public submission equals internal approval."],
    next: ["Continue through the authorised internal workflow."]
  }
};

export function getManualDetail(entry: ManualEntry): ManualDetail {
  const exact = DETAILS[entry.route];
  if (exact) return exact;
  const defaults = GROUP_DEFAULTS[entry.group] ?? GROUP_DEFAULTS["Overview"];
  return {
    useWhen: `Use ${entry.title} when you need to perform the tasks described for this screen.`,
    before: ["Confirm you are in the correct company, branch, site or project scope.", "Have the real source information and evidence required for the record."],
    screenAreas: entry.find,
    keyData: (entry.forms ?? []).map((form) => `${form.label}: ${form.purpose}`),
    controls: defaults.controls,
    sourceOfTruth: `${entry.title} owns the records described on this screen unless the manual explicitly points to another source module.`,
    commonMistakes: defaults.commonMistakes,
    result: `The ${entry.title} record is complete enough for the next controlled step.`,
    next: defaults.next
  };
}
