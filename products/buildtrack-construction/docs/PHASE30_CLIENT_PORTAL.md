# Phase 30 — Client Portal & Controlled External Sharing

Phase 30 provides a deliberately narrow client-facing boundary. BuildTrack staff prepare a numbered client share pack for one active, explicitly `public` controlled document from the selected project's own site. The feature never exposes a project dashboard, staff data, cost data, approvals, records, or a document catalogue.

## Controlled lifecycle

1. A scoped Client Portal Officer or Project Manager prepares a draft pack with its project, client, title, message, one selected document and expiry date.
2. The draft is submitted for publication.
3. A separately authorised Client Portal Reviewer publishes it. Company no-self-approval policy is enforced.
4. BuildTrack returns the opaque public token once. Only its SHA-256 hash is retained, so the same link cannot be recovered from BuildTrack later.
5. The public route offers the selected document's minimal metadata and a read-only download. It expires automatically and a scoped manager can revoke it immediately.

## Safety controls

- Share packs carry company, branch, site and project ownership and use the established scoped permission model.
- Only an active `public` document from the pack's exact project site can be selected; internal, confidential and restricted documents are rejected.
- Public access is limited to `/api/v1/client-portal/public/{token}` and its selected-document download route. All management routes remain authenticated and origin-protected.
- The raw token is never recorded in a database, audit event or response after initial publication. Public views and downloads are audit logged without the token.
- Revocation clears the stored hash; expiry, revocation or later document deactivation causes the link to return unavailable.

## Boundary

Phase 30 is external-document sharing, not a client self-service system. It does not grant an external account, accept instructions, send messages, expose operational/commercial/HSE/security data, replace document-control approvals or prove that a client has received a document. Staff remain responsible for confirming the suitability and recipient of a public controlled document before independent publication.
