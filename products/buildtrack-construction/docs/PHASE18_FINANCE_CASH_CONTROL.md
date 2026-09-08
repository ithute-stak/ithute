# Phase 18 — Finance & Cash Control

Phase 18 adds a controlled finance layer for Nthane Brothers. It uses the Phase 1 organisation, Phase 2 scoped access, Phase 8 supplier/purchase-order records and Phase 11 client-invoice records; it does not create a second company, payment or document system.

## Delivered controls

- company financial periods with no-overlap validation and a close gate that requires every period journal to be posted;
- a company chart of accounts with generic asset, liability, equity, revenue and expense starter records plus controlled extension;
- `FJN` numbered journals with branch/site/project/cost-centre ownership, supporting evidence, debit/credit lines and exact balance validation;
- independent Branch → HQ maker/checker approval before a journal can be posted, plus immutable posting and closed-period protection;
- `SIN` numbered supplier invoices linked to active Phase 8 suppliers and optionally to a matching purchase order;
- accounts-payable outstanding, due-date and payment-request controls that prevent payment requests from exceeding an approved invoice balance;
- `SPY` payment requests requiring independent approval and supplied controlled payment evidence before an invoice balance is updated;
- dashboard visibility for approved supplier payables and existing Phase 11 client-invoice receivables, controlled CSV export and audit history; and
- a Finance & Cash Control workspace integrated with the shared dialog-form and filtered/paginated data-table system.

## Operational boundary

BuildTrack records company financial evidence. It does not create a bank account, connect to a bank, send a payment, calculate tax/VAT, create statutory accounts, choose accounting policy or replace a configured accounting system. Starter chart accounts are neutral operational controls and must be reviewed by the company’s finance professional before production accounting.
