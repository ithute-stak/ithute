# Phase 20 — Resource Planning & Capacity Control

Phase 20 extends BuildTrack from programme visibility to controlled resource demand forecasting for Nthane Brothers.

## Delivered controls

- versioned `RPL` project resource plans with optional approved programme-baseline linkage;
- employee, serviceable fleet asset, material, subcontract and other demand lines with dates, quantities, units, allocation percentages and activity references;
- employee/asset capacity conflict detection across overlapping controlled plans, plus Phase 6 plant-allocation conflict checks;
- conflict-gated Branch → Head Office maker/checker approval and automatic supersession of older approved plans;
- `RQR` request records bounded by approved demand, independent approval, supplied fulfilment evidence, dashboard alerts, CSV export and audit history; and
- `/resources` browser workspace using the shared dialog-form and filtered/paginated data-table system.

## Operational boundary

This phase forecasts and governs resource demand. It does not hire an employee, change payroll, assign fleet, reserve stock, create a requisition/PO, rent equipment or fulfil a request automatically. Those outcomes still need supplied evidence and their established BuildTrack workflows.
