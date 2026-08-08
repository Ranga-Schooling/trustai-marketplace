"""Executable acceptance criteria.

Workstream: E6 Testing & QA (owner: Samar) maintains this suite; each
context owner un-skips the tests for their stories as they implement.
A story's Definition of Done includes its tests passing here and in CI.

Every test below is currently skipped. The skip reason names the story.
Do NOT weaken assertions to make tests pass — change the implementation.

Test env vars (DATABASE_URL, AI_PROVIDER, JWT_SECRET) are set in
conftest.py, not here -- see that file for why it has to happen there.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.db import Base, engine
from app.schemas.schemas import Recommendation, RiskLevel

pytestmark = []


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def register_and_login(client, email="alice@example.com") -> dict:
    client.post("/api/auth/register", json={
        "email": email, "name": "Alice", "password": "s3curepass",
    })
    token = client.post("/api/auth/login", json={
        "email": email, "password": "s3curepass",
    }).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


SAFE_LISTING = {
    "title": "IKEA Billy bookcase, white",
    "price": 450.0,
    "currency": "zar",
    "source": "Facebook Marketplace",
    "description": "Used bookcase in good condition, collection in Randburg.",
}

SCAM_LISTING = {
    "title": "iPhone 15 Pro brand new sealed",
    "price": 15.0,
    "currency": "USD",
    "source": "Gumtree",
    "description": "URGENT sale today only!! Payment by gift card or wire "
                   "transfer only, contact me on WhatsApp.",
}


def test_health(client):
    """Sprint 0: deploy skeleton exposes a liveness endpoint."""
    assert client.get("/api/health").json() == {"status": "ok"}


def test_register_login_me(client):
    headers = register_and_login(client)
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"


def test_duplicate_registration_rejected(client):
    register_and_login(client)
    r = client.post("/api/auth/register", json={
        "email": "alice@example.com", "name": "A", "password": "s3curepass",
    })
    assert r.status_code == 409


def test_bad_credentials_rejected(client):
    register_and_login(client)
    r = client.post("/api/auth/login", json={
        "email": "alice@example.com", "password": "wrongpass1",
    })
    assert r.status_code == 401


def test_analyses_requires_auth(client):
    assert client.post("/api/analyses", json=SAFE_LISTING).status_code == 401
    assert client.get("/api/analyses").status_code == 401


def test_update_profile_requires_auth(client):
    r = client.patch("/api/auth/me", json={"name": "New Name"})
    assert r.status_code == 401


def test_update_profile_name(client):
    headers = register_and_login(client)
    r = client.patch("/api/auth/me", json={"name": "Alice Updated"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Alice Updated"

    me = client.get("/api/auth/me", headers=headers)
    assert me.json()["name"] == "Alice Updated"


def test_update_profile_email(client):
    headers = register_and_login(client)
    r = client.patch("/api/auth/me", json={"email": "alice2@example.com"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "alice2@example.com"


def test_update_profile_duplicate_email_rejected(client):
    register_and_login(client, "alice@example.com")
    headers = register_and_login(client, "bob@example.com")
    r = client.patch("/api/auth/me", json={"email": "alice@example.com"}, headers=headers)
    assert r.status_code == 409


def test_update_profile_requires_a_field(client):
    headers = register_and_login(client)
    r = client.patch("/api/auth/me", json={}, headers=headers)
    assert r.status_code == 400


def test_low_risk_listing_gets_buy(client):
    headers = register_and_login(client)
    r = client.post("/api/analyses", json=SAFE_LISTING, headers=headers)
    assert r.status_code == 201
    body = r.json()
    assert body["risk_level"] == RiskLevel.low.value
    assert body["recommendation"] == Recommendation.buy.value
    assert 0 <= body["risk_score"] <= 33
    assert len(body["seller_questions"]) >= 1


def test_high_risk_listing_gets_avoid(client):
    headers = register_and_login(client)
    r = client.post("/api/analyses", json=SCAM_LISTING, headers=headers)
    assert r.status_code == 201
    body = r.json()
    assert body["risk_level"] == RiskLevel.high.value
    assert body["recommendation"] == Recommendation.avoid.value
    assert 67 <= body["risk_score"] <= 100
    categories = {i["category"] for i in body["risk_indicators"]}
    assert "Off-platform payment" in categories


def test_risk_score_never_contradicts_risk_level(client):
    headers = register_and_login(client)
    safe = client.post("/api/analyses", json=SAFE_LISTING, headers=headers).json()
    scam = client.post("/api/analyses", json=SCAM_LISTING, headers=headers).json()
    assert safe["risk_score"] < scam["risk_score"]


def test_invalid_listing_rejected(client):
    headers = register_and_login(client)
    bad = {**SAFE_LISTING, "price": -5}
    assert client.post("/api/analyses", json=bad, headers=headers).status_code == 422
    bad = {**SAFE_LISTING, "currency": "RANDS"}
    assert client.post("/api/analyses", json=bad, headers=headers).status_code == 422


def test_preview_listing_from_text(client):
    headers = register_and_login(client)
    body = {
        "text": "Awesome sofa, firm price $250. Contact me on WhatsApp."
    }
    r = client.post("/api/listings/preview", json=body, headers=headers)
    assert r.status_code == 200
    response = r.json()
    assert response["title"] == "Awesome sofa, firm price $250. Contact me on WhatsApp."
    assert response["price"] == 250.0
    assert response["currency"] == "USD"
    assert "WhatsApp" in response["seller_details"]


def test_preview_listing_from_url(client, monkeypatch):
    headers = register_and_login(client)

    from app.services.listing_parser import _fetch_html

    def fake_fetch_html(url: str) -> str:
        return (
            "<html><head><title>Vintage guitar</title>"
            "<meta name='description' content='1960s guitar in good shape.'>"
            "</head><body>Price: $1,800</body></html>"
        )

    monkeypatch.setattr("app.services.listing_parser._fetch_html", fake_fetch_html)
    r = client.post(
        "/api/listings/preview",
        json={"url": "https://example.com/listing/123"},
        headers=headers,
    )
    assert r.status_code == 200
    response = r.json()
    assert response["title"] == "Vintage guitar"
    assert response["description"] == "1960s guitar in good shape."
    assert response["price"] == 1800.0
    assert response["currency"] == "USD"


@pytest.mark.skip(reason="US-1.3 AC2 + US-4.1: per-user history isolation (E1+E2)")
def test_history_is_per_user(client):
    alice = register_and_login(client, "alice@example.com")
    bob = register_and_login(client, "bob@example.com")
    client.post("/api/analyses", json=SAFE_LISTING, headers=alice)
    assert len(client.get("/api/analyses", headers=alice).json()) == 1
    assert len(client.get("/api/analyses", headers=bob).json()) == 0
    aid = client.get("/api/analyses", headers=alice).json()[0]["id"]
    assert client.get(f"/api/analyses/{aid}", headers=bob).status_code == 404


def test_ai_failure_returns_502_and_saves_listing(client, monkeypatch):
    headers = register_and_login(client)

    from app.services import ai as ai_module

    class BrokenProvider:
        model_name = "broken"

        def analyze(self, listing):
            raise ai_module.AnalysisFailure("simulated outage")

    from app.api import routes
    monkeypatch.setattr(routes, "get_provider", lambda: BrokenProvider(), raising=False)

    r = client.post("/api/analyses", json=SAFE_LISTING, headers=headers)
    assert r.status_code == 502
    assert "saved" in r.json()["detail"]
