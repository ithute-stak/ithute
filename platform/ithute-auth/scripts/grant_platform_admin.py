#!/usr/bin/env python3
import argparse

from sqlalchemy import or_, select

from app.db import SessionLocal
from app.models import User
from app.security import normalize_email, normalize_phone


def main() -> int:
    parser = argparse.ArgumentParser(description="Grant or revoke !thute platform-admin status for an existing central user.")
    parser.add_argument("identifier", help="Existing user's email or phone")
    parser.add_argument("--revoke", action="store_true", help="Revoke platform-admin status instead of granting it")
    args = parser.parse_args()

    email = normalize_email(args.identifier)
    phone = normalize_phone(args.identifier)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(or_(User.email == email, User.phone == phone)))
        if user is None:
            print("No matching !thute Auth user was found.")
            return 2
        user.is_platform_admin = not args.revoke
        db.commit()
        action = "revoked from" if args.revoke else "granted to"
        print(f"Platform-admin access {action} user {user.id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
