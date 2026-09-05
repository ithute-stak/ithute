# Phase 9 — Webmail

Phase 9 adds a browser-based mailbox experience on top of the Phase 6–8 Postfix/Dovecot/Rspamd mail data plane.

## Implemented

- Mailbox-address/password login against live IMAP.
- Opaque HttpOnly webmail session cookie with encrypted password material stored server-side in Redis and automatic expiry.
- Folder listing, message listing, message open, server-side search, offset/limit pagination.
- Read/unread, starred and answered IMAP flags.
- Archive/move, Trash and permanent-delete lifecycle.
- Draft creation.
- Attachment send and authenticated attachment download.
- SMTP submission with Sent-folder copy.
- Reply/forward threading metadata support.
- Sanitized HTML composition using a strict allow-list.
- Saved HTML signatures, sanitized server-side.
- Personal contacts and autocomplete APIs/UI.
- Per-folder message and unread counts.
- Junk-folder move and restore controls.
- Responsive webmail, rich-compose and preferences routes.

## Security boundaries

Mailbox passwords are never returned to the browser after login. Session tokens are opaque, stored only as hashes in Redis keys, and credentials are encrypted at rest using the application secret-derived Fernet key. HTML is sanitized server-side before storage or SMTP composition. Attachment downloads require an authenticated webmail session.

The internal IMAP/SMTP clients connect over the private Docker mail network. Production public SMTP/IMAP TLS remains governed by the Phase 8 ACME/external certificate lifecycle.

## Acceptance

Run:

```sh
sh scripts/verify-phase9.sh
```

The gate first executes the complete Phase 8 regression suite, rebuilds backend/frontend images, verifies the production frontend build and webmail routes, then performs three live mailbox smoke suites covering basic delivery, mailbox actions/attachments, and final HTML/signature/contact/count/Junk behavior.

Phase 9 is accepted only after the verifier prints:

```text
Phase 9 FINAL acceptance verification PASSED.
```
