# Ithute engine contracts

Python/FastAPI remains the authoritative control plane. These contracts define
the narrow messages that specialist engines may process.

Rules:

1. Business authorization, tenancy, billing and policy decisions stay in Python.
2. Engines receive already-authorized, bounded work.
3. Engine outputs are data/results, never independent business decisions.
4. Contract version `1` is backward compatible within its major version.
5. Secrets are not permitted in generic engine task payloads unless a specific
   operation contract explicitly requires and bounds them.

The first shared envelope is `engine-task.schema.json`. More specialized
contracts may be added under this directory without coupling the engines to
Python ORM/database models.
