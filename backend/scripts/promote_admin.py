"""One-off operational script: promote a user to admin (D-15, issue #42).

No self-serve promotion path exists on purpose — a privilege-escalation
surface a capstone MVP doesn't need. This script, run manually against the
target database, is the only way to create an admin.

Usage (from backend/, with DATABASE_URL pointed at the target database):
    python -m scripts.promote_admin someone@example.com
"""
import sys

from app.models.db import SessionLocal, User
from app.schemas.schemas import UserRole


def promote(email: str) -> None:
    email = email.lower()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            print(f"No user found with email {email!r}", file=sys.stderr)
            sys.exit(1)
        if user.role == UserRole.admin.value:
            print(f"{email} is already an admin.")
            return
        user.role = UserRole.admin.value
        db.commit()
        print(f"Promoted {email} to admin.")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.promote_admin <email>", file=sys.stderr)
        sys.exit(1)
    promote(sys.argv[1])
