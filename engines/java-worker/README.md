# Ithute Java worker

Java is the enterprise document/integration engine. Python remains authoritative
for authorization, tenancy, business policy and database writes.

Current capabilities:

- hardened DMARC aggregate XML parsing;
- DTD and external entity resolution disabled;
- bounded request payloads;
- deterministic Push transport policy (Realtime -> Ithute -> native fallback);
- no database credentials;
- JSON-only result contracts returned to Python.

The Java worker is internal-only and should never be exposed directly through
the public edge.
