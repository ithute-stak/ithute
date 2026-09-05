# Production topology

## Minimum commercial launch

### Primary platform host
- Caddy HTTPS edge on TCP/UDP 443 and HTTP 80 for ACME redirects/challenges.
- Next.js control panel.
- FastAPI control plane.
- PostgreSQL and application Redis on private Docker networking.
- PowerDNS primary authoritative server on public TCP/UDP 53.
- Postfix submission/SMTP, Dovecot IMAP/LMTP and Rspamd/Unbound.
- Backup scheduler targeting independent encrypted Restic storage.
- Prometheus/Grafana/Alertmanager accessible only to operators.

### Independent DNS secondary
- A second public VPS/provider/failure domain.
- PowerDNS secondary with its own database.
- TCP/UDP 53 public.
- AXFR/NOTIFY restricted to the primary.
- `NAMESERVER_2` points to this host.

### Off-site backup
- Restic repository must not be on the same failure domain as the primary host.
- S3-compatible storage, SFTP, REST server or another independent target is suitable.

## Network exposure

Public: 25/tcp, 53/tcp+udp, 80/tcp, 443/tcp+udp, 587/tcp, 993/tcp.
Private/operator-only: PostgreSQL, Redis, Rspamd worker, LMTP/auth sockets, PowerDNS HTTP API, Postfix ops API, Prometheus, Alertmanager and Grafana.

Use the VPS/provider firewall in addition to Docker networking. Do not expose the PowerDNS or Postfix operations HTTP APIs to the Internet.

## Mail production requirements

- A globally routable clean static IP.
- `MAIL_HOSTNAME` A/AAAA points to that IP.
- Provider PTR/rDNS points the IP back to `MAIL_HOSTNAME`.
- Valid public TLS certificate; `MAIL_TLS_MODE=acme` or `external`.
- SPF, DKIM and DMARC aligned for every sending domain.
- Port 25 inbound/outbound permitted by the provider.
- Sender ownership and outbound rate controls enabled.

## Launch

1. Copy `.env.example` to `.env` and replace every placeholder.
2. Set `ENVIRONMENT=production`, `COOKIE_SECURE=true`, `PANEL_HOSTNAME`, `API_HOSTNAME`, `ACME_EMAIL`, mail identity, DNS nameservers and off-site Restic repository.
3. Run `sh scripts/prod-preflight.sh`.
4. Run `sh scripts/prod-up.sh`.
5. Verify public HTTPS, SMTP/IMAPS, DNS, PTR, DKIM/SPF/DMARC and off-site restore before moving customer MX records.
