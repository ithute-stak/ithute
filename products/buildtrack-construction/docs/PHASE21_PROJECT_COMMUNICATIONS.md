# Phase 21 — Project Communications & Stakeholder Control

Phase 21 adds a project-scoped stakeholder/contact register, an evidence-led inbound/outbound correspondence register, formal outgoing correspondence approval, controlled dispatch and response evidence, meeting minutes, assigned actions, independent action verification, alerts, CSV export and audit history.

## Control contract

- Every record is owned by one company, branch, site and project and is protected by role plus branch/site scope.
- A formal outgoing correspondence item starts as a draft, requires its controlled source document, then goes through the shared Branch → Head Office maker/checker workflow. Approval does not send anything; dispatch can only be recorded afterwards with supplied evidence.
- Incoming, operational and internal correspondence becomes a recorded evidence item after submission. A recorded item is only closed when a controlled response document is supplied.
- Meeting minutes require a controlled minutes document and independent approval. Action lines cannot be changed during review.
- Meeting actions require controlled completion evidence and independent verification; the person who marked completion cannot verify it unless the company expressly allows self-approval.
- This phase neither sends email nor issues notices. It does not replace Phase 13 RFIs/site instructions, Phase 11 claims/contract controls, or controlled Phase 1 document management.

Initialise it at **Project Communications** (`/communications`) after Phase 1 access roles exist. The migration revision is `0022_phase21_comms`.
