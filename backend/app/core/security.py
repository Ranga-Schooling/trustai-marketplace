"""Identity & access context — password hashing and JWT handling.

Workstream: E1 Authentication & User Management (owner: Ranga)
Stories: US-1.1 (register), US-1.2 (sign in), US-1.3 (protected access)

Implementation notes for the owner:
- Hash passwords with bcrypt (`bcrypt` package). Never store or log plaintext.
- Tokens are JWTs (`pyjwt`), HS256, expiry from settings (default 24h),
  with the user id in the `sub` claim as a string.
- `get_current_user` is the FastAPI dependency every protected route uses.
  It must raise 401 (with a WWW-Authenticate: Bearer header) for a missing,
  malformed, expired, or unknown-user token — the same error for all cases,
  so the response leaks nothing about which check failed.

Definition of done: the auth tests in tests/test_api.py are un-skipped and
pass in CI.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.db import User, get_db

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the password. [US-1.1 AC3]"""
    raise NotImplementedError("E1: implement bcrypt hashing")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time check of a password against its stored hash. [US-1.2]"""
    raise NotImplementedError("E1: implement bcrypt verification")


def create_access_token(user_id: int) -> str:
    """Create a signed JWT with sub=user_id and expiry from settings. [US-1.2 AC1]"""
    raise NotImplementedError("E1: implement JWT creation")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the bearer token to a User or raise 401. [US-1.3]"""
    raise NotImplementedError("E1: implement token verification and user lookup")
