# Phase 6 — Core Mail Infrastructure

Phase 6 introduces the actual mail data plane. The custom Mailbox DNS control plane continues to own tenants, domains and future mailbox administration, while mature open-source engines handle SMTP, mailbox access, LMTP delivery, message filtering and local DNS recursion for mail security checks.

## Components

- **Postfix** — SMTP reception, authenticated submission and queueing.
- **Dovecot CE** — IMAP/IMAPS access, SMTP authentication and LMTP delivery into Maildir storage.
- **Rspamd** — Postfix milter integration for message scanning and policy enforcement.
- **Unbound** — local recursive DNS resolver dedicated to Rspamd DNS/RBL/SPF/DKIM/DMARC lookups.
- **Redis** — shared state/statistics backend for Rspamd.
- **Maildir volume** — persistent local mailbox storage for the development acceptance environment.

Rspamd publishes an official Docker image and recommends persistent local configuration/data plus a local recursive resolver rather than public DNS for reputation-list traffic. Dovecot CE also publishes Docker images, but Phase 6 uses a small Debian-packaged Dovecot image so the local integration environment can exercise standard IMAP/IMAPS ports and predictable LMTP/auth listeners alongside Postfix.

## Development topology

Use:

```sh
docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml up -d --build
```

Default host mappings:

- SMTP 25 -> `2525`
- submission 587 -> `2587`
- IMAP 143 -> `2143`
- IMAPS 993 -> `2993`

Unbound is not published to the host. It lives on a dedicated internal bridge and Rspamd is explicitly configured to query it at `172.31.56.53`. The resolver is therefore isolated from public access while remaining independent from Docker's embedded service-discovery resolver.

The local acceptance mailbox is intentionally a development fixture only:

- address: `phase6@phase6.test`
- password: `Phase6Strong!Pass`

Do not use this credential in production. Phase 7 replaces the static mailbox fixture with database-backed tenant mailbox administration and generated password hashes.

## Security behavior already enforced

- SMTP submission requires STARTTLS before authentication.
- Submission authentication is delegated from Postfix to Dovecot.
- Unauthenticated SMTP relay is rejected and checked by the verifier.
- Local recipient acceptance is restricted by Postfix virtual mailbox maps.
- Postfix sends accepted local mail to Dovecot over LMTP.
- Rspamd sits in the SMTP path through Postfix milter configuration.
- If the Rspamd milter is unavailable, the current Phase 6 policy tempfails instead of silently bypassing filtering.
- Rspamd uses a dedicated local Unbound recursive resolver instead of a public DNS resolver.
- Dovecot IMAPS is enabled and plaintext authentication is disabled on the external IMAP path without TLS.
- Mail data is stored on a persistent Docker volume and is checked after Dovecot restart.
- Development TLS certificates are generated locally and are self-signed.
- LMTP and Dovecot auth listeners remain private container-network services rather than host-published ports.

## Verification gate

Run:

```sh
sh scripts/verify-phase6.sh
```

The verifier first reruns the complete Phase 5 regression gate. It then builds and starts Unbound, Postfix, Dovecot and Rspamd, validates their configuration, proves recursive DNS readiness, verifies the Postfix milter and LMTP paths, rejects an unauthenticated external relay attempt, and performs an authenticated end-to-end message flow:

1. verify local recursive DNS through Unbound;
2. connect to submission port 587;
3. require STARTTLS;
4. authenticate through Dovecot;
5. submit a unique message;
6. pass the message through the Rspamd milter path;
7. deliver it to Dovecot over LMTP;
8. retrieve the same message using IMAPS;
9. restart Dovecot and verify Maildir data remains present;
10. smoke-test frontend and backend readiness.

Acceptance requires the exact final line:

```text
Phase 6 verification PASSED.
```

## Production boundary

Local success proves the software integration, not public deliverability. Production still requires a dedicated public mail host, valid public TLS certificates, correct MX/A records, PTR/reverse DNS, firewall rules for 25/587/993, provider permission for outbound SMTP, durable backups, monitoring and a clean static IP reputation. SPF, DKIM, DMARC, bounce/reputation policy and complete deliverability hardening are finalized in Phase 8.

The remaining pre-Phase-7 technical debt is intentionally narrow: the static Phase 6 mailbox fixture and development certificates must not cross into production. Phase 7 replaces the mailbox fixture with database-backed mailbox administration; production TLS/secrets and public deliverability controls are completed during the later hardening phases.
