"""Unit tests for the auth service (app/core/security.py).

Workstream: E6 Testing & QA. Unlike test_api.py, these call the security
functions directly -- no TestClient, no HTTP round trip -- so they stay
fast and isolate failures to the auth service itself.
"""
import datetime as dt
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_trustai_security.db")
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("JWT_SECRET", "test-secret")

import jwt
import pytest
from fastapi import HTTPException

from app.core import security
from app.core.config import get_settings
from app.models.db import Base, SessionLocal, User, engine

settings = get_settings()


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_hash_password_is_not_plaintext_and_is_bcrypt():
    password_hash = security.hash_password("s3curepass")
    assert password_hash != "s3curepass"
    assert password_hash.startswith("$2")  # bcrypt identifier


def test_hash_password_is_salted_per_call():
    assert security.hash_password("s3curepass") != security.hash_password("s3curepass")


def test_verify_password_round_trip():
    password_hash = security.hash_password("s3curepass")
    assert security.verify_password("s3curepass", password_hash) is True
    assert security.verify_password("wrongpass", password_hash) is False


def test_create_access_token_contains_expected_claims():
    token = security.create_access_token(user_id=42)
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])

    assert payload["sub"] == "42"
    expire = dt.datetime.fromtimestamp(payload["exp"], tz=dt.timezone.utc)
    now = dt.datetime.now(dt.timezone.utc)
    assert now < expire <= now + dt.timedelta(minutes=settings.jwt_expiry_minutes, seconds=5)


def test_get_current_user_rejects_missing_credentials(db):
    with pytest.raises(HTTPException) as exc_info:
        security.get_current_user(credentials=None, db=db)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_malformed_token(db):
    class FakeCredentials:
        credentials = "not-a-real-jwt"

    with pytest.raises(HTTPException) as exc_info:
        security.get_current_user(credentials=FakeCredentials(), db=db)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_expired_token(db):
    expired_payload = {
        "sub": "1",
        "exp": dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1),
    }
    expired_token = jwt.encode(expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    class FakeCredentials:
        credentials = expired_token

    with pytest.raises(HTTPException) as exc_info:
        security.get_current_user(credentials=FakeCredentials(), db=db)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_unknown_user_id(db):
    token = security.create_access_token(user_id=999999)

    class FakeCredentials:
        credentials = token

    with pytest.raises(HTTPException) as exc_info:
        security.get_current_user(credentials=FakeCredentials(), db=db)
    assert exc_info.value.status_code == 401


def test_get_current_user_returns_user_for_valid_token(db):
    user = User(
        email="unit@example.com",
        name="Unit Test",
        password_hash=security.hash_password("s3curepass"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = security.create_access_token(user_id=user.id)

    class FakeCredentials:
        credentials = token

    resolved = security.get_current_user(credentials=FakeCredentials(), db=db)
    assert resolved.id == user.id
    assert resolved.email == "unit@example.com"
