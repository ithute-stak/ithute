# Phase 8 — Procurement & Stores Completion Contract

Phase 8 is complete when a branch/site/project need can become an approved purchase commitment and then controlled physical stock without introducing parallel supplier, project, site, approval or document concepts.

## Completed operating scope

- one company supplier register with automatic supplier numbers, contact/compliance evidence, payment terms and active/suspended/blacklisted status;
- branch/site store locations reusing Phase 1 Branch/Site ownership and optional responsible Phase 3 employee;
- one company stock-item master with SKU, unit, category, reorder/max levels and default reference cost;
- stock balance per store/item with on-hand/reserved quantities and weighted-average accepted receipt cost;
- branch/site/project/cost-centre procurement requisitions with automatic `PR` numbering, required dates, priority, estimated values and editable draft lines;
- requisition approval through shared Phase 1 `ApprovalWorkflow`, `ApprovalRequest` and `ApprovalAction` with Branch Manager review, HQ approval and the company no-self-approval policy;
- supplier quotations against approved requisitions, requiring every requisition line to be priced exactly once;
- quotation comparison, configurable minimum quote count and a controlled low-value waiver threshold;
- selected quotations are the only source for purchase-order creation;
- purchase orders with automatic `PO` numbering, selected supplier/quotation evidence, delivery store, expected date, commercial totals and configurable overrun tolerance against the approved requisition;
- PO maker/checker approval through the shared approval engine; approval creates a commitment but never creates stock;
- goods receipts with automatic `GRN` numbering, delivery evidence, accepted/rejected quantities and protection against receiving beyond the outstanding PO quantity;
- only accepted receipt quantities increase stock; rejected quantities remain outstanding for replacement/redelivery;
- accepted stock receipt recalculates weighted-average inventory cost;
- immutable stock movements for receipt, issue, return, transfer-out, transfer-in and adjustment;
- stock issue/return scope validation across branch, site, linked Phase 6 project and cost centre;
- optional link from Phase 8 stock movement to Phase 7 `SiteMaterialEntry`, without rewriting the approved site diary;
- negative-stock prevention on issues, transfers and negative adjustments;
- store transfers with automatic `TRF` numbering and controlled `draft → in_transit → received` lifecycle; source transfer cost is carried into the destination weighted-average balance;
- controlled stock adjustments requiring `stores.adjust` permission and an explicit reason;
- Procurement Manager, Procurement Officer and Storekeeper roles plus reconciled permissions for system/HQ/branch/site/approver/auditor roles;
- procurement/stores dashboards for pending approvals, open PO commitments, stock valuation, low stock, required-date and overdue-delivery alerts;
- branch-safe stock and purchase-order CSV exports plus immutable procurement audit history;
- responsive `/procurement` daily operations workspace and `/procurement/control` governance workspace;
- regression coverage for the requisition → approval → quote → selected quote → PO → approval → goods receipt → weighted-average stock → issue → negative-stock block → transfer chain.

## Governance boundaries

Phase 8 does not invent supplier quotations, tax/VAT rates, invoices, delivery notes, quantities or acceptance results. Quotation and PO tax values are supplied commercial evidence; statutory tax logic is not hard-coded without verified requirements. A purchase-order approval is a commitment only and cannot increase stock. Stock increases only when accepted goods are physically recorded on a posted goods receipt.

Phase 7 remains the owner of approved daily site-operational evidence. Phase 8 can reference a Phase 7 material entry when stores issue/return evidence relates to it, but it does not mutate the approved site report snapshot.

## Migration

- Revision: `0010_phase8_procurement`
- Down revision: `0009_phase7_site_ops`
- Revision ID remains within Alembic's 32-character version-column limit.
