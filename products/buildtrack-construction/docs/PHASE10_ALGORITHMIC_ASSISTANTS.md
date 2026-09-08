# Phase 10 — Algorithmic Procurement and Tender Assistants

Phase 10 adds explainable, deterministic decision-support tools to BuildTrack. It deliberately does **not** call an AI model, infer missing commercial facts, select suppliers, approve records, submit tenders or send messages.

## Procurement Assistant

- Reviews a recorded purchase request for title, date, item, specification and estimate gaps.
- Suggests a category from transparent construction keyword rules.
- Reads readable PDF, DOCX and text quotation evidence attached through existing document control.
- Compares recorded quotation price, delivery period, warranty and payment terms using published weights: price 50, delivery 20, warranty 15 and payment terms 15.
- Prepares a non-binding purchase-order draft from the already selected controlled quotation.
- Answers narrow supplier-history questions from recorded purchase orders and quotation lines.
- Answers procurement-policy questions from the company’s stored quotation and approval policy.

## Tender Assistant

- Extracts rule-matched compliance requirements, dates, forms, technical conditions, scope/evaluation evidence, copies and bid-security terms from uploaded PDF, DOCX or readable text.
- Generates only missing checklist entries; those remain `missing` until staff verify controlled evidence.
- Answers tender questions from a saved document-review result and shows evidence snippets.
- Produces editable company-profile, technical-response, method-statement and cover-letter templates using recorded tender facts and explicit placeholders.
- Exposes 30, 14, 7 and 1-day deadline reminder events for the existing workspace or an approved future notification integration.

## Controls and limits

- Existing Phase 8 procurement and Phase 5 tender permissions, branch/site scope, document control, maker/checker approvals and audit evidence remain authoritative.
- Each run is saved as an immutable `algorithmic_assistant_analyses` snapshot with rule version, source digest, actor and output.
- PDF/DOCX extraction uses local deterministic parsers; scanned/image-only documents and legacy `.doc` files must be converted to readable PDF/DOCX or supplied as reviewed text.
- Results are recommendations, not decisions. Staff must verify source documents and use the established selection, approval and submission workflows.
