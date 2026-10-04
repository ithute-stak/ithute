from __future__ import annotations

import json

from app.db.session import SessionLocal
from app.services.hosting_provisioning_reconcile import run_hosting_provisioning_reconcile


def main() -> None:
    db = SessionLocal()
    try:
        print(json.dumps(run_hosting_provisioning_reconcile(db), sort_keys=True))
    finally:
        db.close()


if __name__ == "__main__":
    main()
