# Phase 1 Architecture

## Control plane
- Next.js frontend
- FastAPI backend
- PostgreSQL system of record
- Redis for future queues, cache, rate limits and distributed locks
- Alembic migrations

## Tenant model
A platform owner exists outside any tenant. Tenant administrators and members belong to a tenant. Future domains, DNS zones, mailboxes, aliases and billing records will all carry tenant ownership.

## Production direction
The control plane is intentionally separate from the future data plane. PowerDNS, Postfix, Dovecot and Rspamd will be integrated through narrowly scoped service adapters rather than being embedded into web request handlers.

## Target topology
- panel.example.tld -> frontend
- api.example.tld -> backend
- ns1/ns2 -> dedicated PowerDNS nodes (Phase 4+)
- mail.example.tld -> dedicated mail gateway/storage nodes (Phase 6+)
- PostgreSQL/Redis on private network only
