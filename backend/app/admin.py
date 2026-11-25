"""Run after migrations: python -m app.admin create | reset."""
import argparse
import getpass
from sqlalchemy import delete
from app.core.db import session_factory
from app.core.security import hash_password, now, audit
from app.models import User, LoginSession

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["create", "reset"])
    parser.add_argument("--username", default="admin")
    args = parser.parse_args()
    if not 1 <= len(args.username) <= 80:
        parser.error("Username must contain 1–80 characters")
    password = getpass.getpass("Password (12–128 characters): ")
    if not 12 <= len(password) <= 128 or password != getpass.getpass("Confirm password: "):
        parser.error("Password length or confirmation invalid")
    with session_factory()() as db:
        user = db.get(User, 1, with_for_update=True)
        if args.action == "create":
            if user:
                parser.error("Administrator already exists; use reset")
            user = User(id=1, username=args.username, password_hash=hash_password(password),
                        created_at=now(), failed_attempts=0, locked_until=0)
            db.add(user)
            db.flush()
        else:
            if not user:
                parser.error("Administrator does not exist; use create")
            user.password_hash = hash_password(password)
            user.failed_attempts = 0
            user.locked_until = 0
            db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
        audit(db, "admin." + args.action, user.id)
        db.commit()
    print("Administrator " + args.action + " successful")

if __name__ == "__main__":
    main()
