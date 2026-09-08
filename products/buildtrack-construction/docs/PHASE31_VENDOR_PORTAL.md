# Phase 31 — Supplier & Subcontractor Evidence Portal

Phase 31 provides a constrained external route for collecting compliance evidence from a named existing supplier or subcontractor. It is not a supplier account or procurement portal.

## Lifecycle

1. An authorised staff member creates a branch/site-scoped `VER` request for one active supplier or subcontractor, with a specific evidence type and due date.
2. The request is submitted and independently published. Company no-self-approval policy applies.
3. The publisher receives one opaque link once. BuildTrack stores only the SHA-256 token hash.
4. The vendor sees the request text and uploads one file with its contact details. The request then leaves the public state automatically.
5. A scoped internal reviewer checks the original file and explicitly verifies the received evidence before relying on it.

## Safety controls

- Public paths are restricted to the opaque request view and its single evidence-upload action; management, evidence review and downloads remain authenticated and branch/site-scoped.
- Requests expire on the due date, can be revoked immediately before use, and are unavailable after evidence is received.
- Uploads are restricted to 25 MB, safely named, content-hashed and stored beneath the company/request media path.
- External audit events record views and received evidence without retaining a raw link token.

## Boundary

Phase 31 does not create a vendor login, approve a vendor, amend supplier or subcontractor data, award work, accept a quotation, make a payment, decide regulatory compliance, or expose any BuildTrack operational, commercial, staff, tender, project or other-vendor information. Internal staff must still validate the original evidence and complete the existing Procurement and Subcontract workflows.
