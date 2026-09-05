#!/usr/bin/env python3
"""Re-encrypt stored DKIM keys with the currently configured Phase 10 key.

Use after setting a dedicated DKIM_ENCRYPTION_KEY or after changing the current
key id/key in a maintenance window where the old ciphertext is still readable.
The script never prints private-key material.
"""

from sqlalchemy import select

from app.core.security import decrypt_dkim_secret, encrypt_dkim_secret
from app.db.session import SessionLocal
from app.models import DkimKey


def main() -> int:
    db = SessionLocal()
    changed = 0
    try:
        rows = db.scalars(select(DkimKey)).all()
        for row in rows:
            plaintext = decrypt_dkim_secret(row.private_key_encrypted)
            wrapped = encrypt_dkim_secret(plaintext)
            if wrapped != row.private_key_encrypted:
                row.private_key_encrypted = wrapped
                changed += 1
        db.commit()
        print(f"Rewrapped {changed} DKIM key(s); private material was not printed.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
