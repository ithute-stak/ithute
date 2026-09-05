# Phase 12 Incident Operations

## Triage order

1. Confirm Prometheus and Alertmanager are reachable.
2. Check synthetic SMTP, IMAP, and authoritative DNS probe status.
3. Check backend dependency readiness and HTTP 5xx rate.
4. Check Postfix queue totals/deferred count and private mail-operations readiness.
5. Check backup last-run success and age.
6. Check host disk, memory, CPU, and container health before restarting services.

## Service-specific response

- SMTP probe failure: inspect Postfix health/logs, port 25 listener, Rspamd reachability, DNS/PTR and TLS state. Do not flush or delete queue items until the cause is understood.
- IMAP probe failure: inspect Dovecot health/logs, port 143/993 listeners, database reachability and mailbox storage mounts.
- DNS probe failure: inspect PowerDNS primary health, authoritative zone availability, delegation and secondary DNS independently.
- Deferred queue growth: inspect queue reasons and destination patterns. Use the platform-owner mail operations API for retry/flush only after correcting the underlying issue.
- Backup failure/staleness: verify Restic repository reachability, credentials, database dump access and Maildir mount; run the documented restore drill after recovery.

## Alert routing

Alertmanager groups alerts by alert name and severity. Production deployments must replace the default no-op receiver with an organization-controlled notification integration. Secrets for receivers must not be committed to source control.

## Recovery evidence

For every incident, record UTC start/end time, affected services, user impact, alert names, root cause, mitigation, validation performed, and follow-up action. A service is not considered recovered until its synthetic probe and direct health/readiness checks are both healthy.
