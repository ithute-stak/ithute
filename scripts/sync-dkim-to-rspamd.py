"""Synchronize active encrypted DKIM keys into Rspamd's private Redis signing store.

Run inside the backend container. Private keys are decrypted only in memory and are
written to Redis; they are never printed or returned by the control-plane API.
"""
from app.db.session import SessionLocal
from app.services.dkim_sync import sync_active_dkim_keys


def main() -> None:
    with SessionLocal() as db:
        count = sync_active_dkim_keys(db)
    print(f"Synchronized {count} active DKIM signing domain(s) to Rspamd.")


if __name__ == "__main__":
    main()
