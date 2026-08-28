"""Admin RBAC + analytics (D-15, issue #42)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.db import (
    Analysis,
    AnalysisFailureLog,
    Base,
    Listing,
    SessionLocal,
    User,
    engine,
)
from app.schemas.schemas import UserRole
from scripts.promote_admin import promote

from tests.test_api import SAFE_LISTING, register_and_login


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _promote(email: str) -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email.lower()).first()
        user.role = UserRole.admin.value
        db.commit()
    finally:
        db.close()


def test_admin_analytics_rejects_unauthenticated(client):
    r = client.get("/api/admin/analytics")
    assert r.status_code == 401


def test_admin_analytics_rejects_non_admin(client):
    headers = register_and_login(client)
    r = client.get("/api/admin/analytics", headers=headers)
    assert r.status_code == 403
    assert r.json()["detail"] == "Admin access required"


def test_admin_analytics_allows_admin_with_empty_db(client):
    headers = register_and_login(client, email="admin@example.com")
    _promote("admin@example.com")

    r = client.get("/api/admin/analytics", headers=headers)

    assert r.status_code == 200
    body = r.json()
    assert body["total_listings"] == 0
    assert body["total_analyses"] == 0
    assert body["listings_per_day"] == {}
    assert body["risk_level_distribution"] == {}
    assert body["provider_failure_counts"] == {}


def test_admin_analytics_aggregates_across_all_users(client):
    admin_headers = register_and_login(client, email="admin@example.com")
    _promote("admin@example.com")
    other_headers = register_and_login(client, email="bob@example.com")

    # A second user's submission must still be counted -- this is the one
    # route in the API deliberately not scoped to the caller.
    r = client.post("/api/analyses", json=SAFE_LISTING, headers=other_headers)
    assert r.status_code == 201
    analysis = r.json()

    body = client.get("/api/admin/analytics", headers=admin_headers).json()

    assert body["total_listings"] == 1
    assert body["total_analyses"] == 1
    assert sum(body["listings_per_day"].values()) == 1
    assert body["risk_level_distribution"] == {analysis["risk_level"]: 1}
    assert body["recommendation_distribution"] == {analysis["recommendation"]: 1}
    assert body["price_plausibility_distribution"] == {
        analysis["price_plausibility"]: 1
    }
    assert body["model_used_distribution"] == {analysis["model_used"]: 1}


def test_admin_analytics_includes_provider_failure_counts(client, monkeypatch):
    admin_headers = register_and_login(client, email="admin@example.com")
    _promote("admin@example.com")
    other_headers = register_and_login(client, email="bob@example.com")

    from app.services import ai as ai_module
    from app.api import routes

    class BrokenProvider:
        model_name = "broken"

        def analyze(self, listing):
            raise ai_module.AnalysisFailure("simulated outage")

    monkeypatch.setattr(routes, "get_provider", lambda: BrokenProvider())

    r = client.post("/api/analyses", json=SAFE_LISTING, headers=other_headers)
    assert r.status_code == 502

    body = client.get("/api/admin/analytics", headers=admin_headers).json()

    assert body["provider_failure_counts"] == {"mock": 1}
    assert body["total_listings"] == 1
    assert body["total_analyses"] == 0


def test_analysis_failure_persists_failure_log(client, monkeypatch):
    headers = register_and_login(client)

    from app.services import ai as ai_module
    from app.api import routes

    class BrokenProvider:
        model_name = "broken"

        def analyze(self, listing):
            raise ai_module.AnalysisFailure("simulated outage")

    monkeypatch.setattr(routes, "get_provider", lambda: BrokenProvider())

    client.post("/api/analyses", json=SAFE_LISTING, headers=headers)

    db = SessionLocal()
    try:
        logs = db.query(AnalysisFailureLog).all()
        assert len(logs) == 1
        assert logs[0].provider == "mock"
        assert logs[0].failure_type == "AnalysisFailure"
        assert logs[0].cause_type == "none"
        listing = db.query(Listing).one()
        assert logs[0].listing_id == listing.id
    finally:
        db.close()


def test_deleting_account_cascades_failure_logs(client, monkeypatch):
    headers = register_and_login(client)

    from app.services import ai as ai_module
    from app.api import routes

    class BrokenProvider:
        model_name = "broken"

        def analyze(self, listing):
            raise ai_module.AnalysisFailure("simulated outage")

    monkeypatch.setattr(routes, "get_provider", lambda: BrokenProvider())
    client.post("/api/analyses", json=SAFE_LISTING, headers=headers)

    client.delete("/api/auth/me", headers=headers)

    db = SessionLocal()
    try:
        assert db.query(AnalysisFailureLog).count() == 0
        assert db.query(Listing).count() == 0
    finally:
        db.close()


def test_promote_admin_sets_role(client):
    register_and_login(client, email="future-admin@example.com")

    promote("future-admin@example.com")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "future-admin@example.com").first()
        assert user.role == UserRole.admin.value
    finally:
        db.close()


def test_promote_admin_is_idempotent(client, capsys):
    register_and_login(client, email="future-admin@example.com")
    promote("future-admin@example.com")

    promote("future-admin@example.com")

    assert "already an admin" in capsys.readouterr().out


def test_promote_admin_missing_user_exits(client):
    with pytest.raises(SystemExit):
        promote("nobody@example.com")
