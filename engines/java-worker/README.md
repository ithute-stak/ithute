# Ithute Java worker

Java is the enterprise document/integration engine. Python remains authoritative
for authorization, tenancy, business policy and database writes.

Initial capability:

- hardened DMARC aggregate XML parsing;
- DTD and external entity resolution disabled;
- bounded request payloads;
- no database credentials;
- JSON-only result contract returned to Python.

The Java worker is internal-only and should never be exposed directly through
the public edge.
