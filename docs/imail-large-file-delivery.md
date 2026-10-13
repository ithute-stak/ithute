# iMail secure large-file delivery — implementation contract

## Existing constraints (verified in code)
- Hosted composer reads attachments as browser base64 and refuses an individual file >10 MiB or an aggregate >15 MiB.
- Backend hosted SMTP sender refuses aggregate decoded attachments >15 MiB.
- API attachment schemas encode binary content in JSON/base64, increasing memory usage and request size.
- Raising SMTP size limits is **not** sufficient: recipient MX servers may independently reject large messages.

## Required user experience
1. User selects files. **Inline attachment** applies within existing MIME limits; larger selections are offered **Secure file delivery** instead of simply rejected.
2. For secure delivery, browser uploads file chunks directly to a *private* object store using short-lived upload grants. Resume, progress, cancellation and retries are supported. Do not base64-encode the full file.
3. Backend completes upload only when size, digest, file count, tenant and owner match the original manifest. Async malware scanning and content policy checks place the artifact in **quarantine** until approved. No recipient download until scans are clean.
4. Sender receives a preview of file names, sizes, expiration and audience. Email contains a branded transfer card/link, NOT the raw file, plus optional small MIME attachments.
5. Recipient opens a TLS link, verifies their email using time-limited one-time code or approved SSO, then downloads via short-lived, audience-bound grants. A recipient-specific opaque token is never exposed in logs or analytics. Optional passcode must not replace identity proof for sensitive data.
6. Sender can view upload status, download audit events, expiration and revoke a transfer; status is not represented as email read-receipt evidence.
7. Retention sweeper deletes expired/revoked blobs, fragments, metadata and outstanding grants according to policy. Audit retains only minimum necessary metadata.

## Explicit security and operations requirements
- Separate storage bucket per environment with no public ACL, private encryption-at-rest, TLS and managed keys.
- Strong authenticated ownership on each upload, finalize, status and revoke route; recipient verification and per-transfer ACL on download.
- Upload session bound to tenant, mailbox, sender, expected size, SHA-256 digest and max part count. Validate MIME and magic bytes; normalize filename for display.
- Limits in the policy module are initial configurable ceilings, **not a promise that storage quotas are provisioned**: proposed 2 GiB each, 5 GiB total.
- Storage quota and rate limiting per mailbox/tenant, total stored bytes, concurrent uploads, requests and egress bandwidth. Reject excess with precise remediation.
- Idempotent finalize and send; no duplicate messages on HTTP retries. Never dispatch email until every transfer is clean and durable.
- Record transfers in PostgreSQL with states CREATED, UPLOADING, QUARANTINED, READY, SENT, EXPIRED, REVOKED, FAILED. Durable worker/outbox for scanning, messaging and cleanup.
- Defend against decompression bombs, archive traversal, malware, file spoofing, replay, cross-tenant access, SSRF, and SMTP HTML injection.
- Preserve human-readable fallback URLs; do not use tracking pixels. Downloads are not equivalent to reading the mail.

## Implementation stages
1. **Done in initial PR:** deterministic pure routing policy and boundary tests. This does not enable uploads or secure links.
2. Add database models/migrations, S3-compatible private storage abstraction, signed multipart upload creation/complete/abort endpoints, ownership checks, quotas, malware scanning, expiration worker and comprehensive adversarial tests.
3. Add branded authenticated recipient redemption/download endpoint and verified invitation-mail worker.
4. Add composer upload/resume/progress UI, fallback handling and status/revocation surface. Build Playwright mobile, light/dark, SMTP outage, malware and cross-tenant isolation tests.
5. Release under per-tenant feature flag; monitor delivery, failures, egress and quota. Keep 10/15 MiB MIME limits for compatibility.

**Deployment gate:** Secure-link mode must not be offered as functional until stages 2–4 pass integration and security tests, object storage/virus scanner are deployed, and retention/incident plans are approved.
