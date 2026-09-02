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
from app.models.db import Analysis, Base, Listing, RiskIndicator, SessionLocal, engine
from app.schemas.schemas import PricePlausibility, Recommendation, RiskLevel

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

MODERATELY_LOW_PRICE_LISTING = {
    "title": "Samsung Galaxy S22, lightly used",
    "price": 35.0,
    "currency": "USD",
    "source": "OLX",
    "description": "Selling my phone, works perfectly, minor scratches on the back.",
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


def test_url_preview_requires_auth(client):
    r = client.post("/api/listings/preview", json={"url": "https://example.com/item/1"})
    assert r.status_code == 401


def test_url_preview_returns_suggested_fields(client, monkeypatch):
    headers = register_and_login(client)

    from app.api import routes
    from app.schemas.schemas import ListingPreviewOut

    def fake_fetch(url):
        return ListingPreviewOut(
            url=url,
            title="IKEA Billy bookcase, white",
            description="Used bookcase in good condition.",
            source="example.com",
        )

    monkeypatch.setattr(routes, "fetch_listing_preview", fake_fetch)

    r = client.post(
        "/api/listings/preview",
        json={"url": "https://example.com/item/1"},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "IKEA Billy bookcase, white"
    assert body["source"] == "example.com"


def test_url_preview_rejects_private_address(client):
    headers = register_and_login(client)
    r = client.post(
        "/api/listings/preview",
        json={"url": "http://127.0.0.1:8000/whatever"},
        headers=headers,
    )
    assert r.status_code == 422
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


def test_delete_account_requires_auth(client):
    assert client.delete("/api/auth/me").status_code == 401


def test_delete_account_removes_user_and_owned_data(client):
    headers = register_and_login(client, "alice@example.com")
    analysis = client.post("/api/analyses", json=SAFE_LISTING, headers=headers).json()

    assert client.delete("/api/auth/me", headers=headers).status_code == 204

    # the token used to authenticate no longer works
    assert client.get("/api/auth/me", headers=headers).status_code == 401

    # the email is free again -- proves the user row is actually gone, not
    # just inaccessible
    again = client.post("/api/auth/register", json={
        "email": "alice@example.com", "name": "Alice", "password": "s3curepass",
    })
    assert again.status_code == 201

    db = SessionLocal()
    try:
        assert db.query(Listing).filter(Listing.id == analysis["listing_id"]).first() is None
        assert db.query(Analysis).filter(Analysis.id == analysis["id"]).first() is None
    finally:
        db.close()


def test_delete_account_does_not_affect_other_users(client):
    alice = register_and_login(client, "alice@example.com")
    bob = register_and_login(client, "bob@example.com")
    bob_analysis = client.post("/api/analyses", json=SAFE_LISTING, headers=bob).json()

    assert client.delete("/api/auth/me", headers=alice).status_code == 204

    assert client.get("/api/auth/me", headers=bob).status_code == 200
    assert client.get(f"/api/analyses/{bob_analysis['id']}", headers=bob).status_code == 200


def test_low_risk_listing_gets_buy(client):
    headers = register_and_login(client)
    r = client.post("/api/analyses", json=SAFE_LISTING, headers=headers)
    assert r.status_code == 201
    body = r.json()
    assert body["risk_level"] == RiskLevel.low.value
    assert body["recommendation"] == Recommendation.buy.value
    assert body["price_plausibility"] == PricePlausibility.plausible.value
    assert 0 <= body["risk_score"] <= 33
    assert len(body["seller_questions"]) >= 1


def test_high_risk_listing_gets_avoid(client):
    headers = register_and_login(client)
    r = client.post("/api/analyses", json=SCAM_LISTING, headers=headers)
    assert r.status_code == 201
    body = r.json()
    assert body["risk_level"] == RiskLevel.high.value
    assert body["recommendation"] == Recommendation.avoid.value
    assert body["price_plausibility"] == PricePlausibility.too_good_to_be_true.value
    assert 67 <= body["risk_score"] <= 100
    categories = {i["category"] for i in body["risk_indicators"]}
    assert "Off-platform payment" in categories


def test_moderately_low_price_gets_suspicious_plausibility(client):
    headers = register_and_login(client)
    r = client.post("/api/analyses", json=MODERATELY_LOW_PRICE_LISTING, headers=headers)
    assert r.status_code == 201
    body = r.json()
    assert body["price_plausibility"] == PricePlausibility.suspicious.value
    assert body["risk_level"] == RiskLevel.medium.value
    assert body["recommendation"] == Recommendation.caution.value


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


def test_history_is_per_user(client):
    alice = register_and_login(client, "alice@example.com")
    bob = register_and_login(client, "bob@example.com")
    client.post("/api/analyses", json=SAFE_LISTING, headers=alice)
    assert len(client.get("/api/analyses", headers=alice).json()) == 1
    assert len(client.get("/api/analyses", headers=bob).json()) == 0
    aid = client.get("/api/analyses", headers=alice).json()[0]["id"]
    assert client.get(f"/api/analyses/{aid}", headers=bob).status_code == 404


def test_list_analyses_newest_first(client):
    headers = register_and_login(client)
    first = client.post("/api/analyses", json=SAFE_LISTING, headers=headers).json()
    second = client.post("/api/analyses", json=SCAM_LISTING, headers=headers).json()

    body = client.get("/api/analyses", headers=headers).json()

    assert [item["id"] for item in body] == [second["id"], first["id"]]
    assert body[0]["listing_title"] == SCAM_LISTING["title"]
    assert body[0]["listing_price"] == SCAM_LISTING["price"]
    assert body[0]["listing_currency"] == SCAM_LISTING["currency"].upper()


def test_get_analysis_returns_full_detail(client):
    headers = register_and_login(client)
    created = client.post("/api/analyses", json=SCAM_LISTING, headers=headers).json()

    r = client.get(f"/api/analyses/{created['id']}", headers=headers)

    assert r.status_code == 200
    body = r.json()
    assert body["listing_title"] == SCAM_LISTING["title"]
    assert len(body["risk_indicators"]) > 0
    assert body["risk_score"] == created["risk_score"]


def test_get_analysis_unknown_id_returns_404(client):
    headers = register_and_login(client)
    assert client.get("/api/analyses/999999", headers=headers).status_code == 404


def test_ai_failure_returns_502_and_saves_listing(client, monkeypatch, caplog):
    headers = register_and_login(client)

    from app.services import ai as ai_module

    class BrokenProvider:
        model_name = "broken"

        def analyze(self, listing):
            raise ai_module.AnalysisFailure("simulated outage")

    from app.api import routes
    monkeypatch.setattr(routes, "get_provider", lambda: BrokenProvider(), raising=False)

    with caplog.at_level("ERROR", logger="app.api.routes"):
        r = client.post("/api/analyses", json=SAFE_LISTING, headers=headers)

    assert r.status_code == 502
    assert "saved" in r.json()["detail"]
    assert "AI analysis failed listing_id=" in caplog.text
    assert "provider=mock" in caplog.text
    assert "failure_type=AnalysisFailure" in caplog.text
    assert "cause_type=none" in caplog.text
    assert "simulated outage" not in caplog.text


class BrokenProvider:
    """Shared by the failed-listing/retry tests below (D-20, issue #80)."""

    model_name = "broken"

    def analyze(self, listing):
        from app.services.ai import AnalysisFailure

        raise AnalysisFailure("simulated outage")


def test_failed_listing_appears_in_failed_listings(client, monkeypatch):
    headers = register_and_login(client)

    from app.api import routes
    monkeypatch.setattr(routes, "get_provider", lambda: BrokenProvider(), raising=False)
    client.post("/api/analyses", json=SAFE_LISTING, headers=headers)

    body = client.get("/api/listings/failed", headers=headers).json()

    assert len(body) == 1
    assert body[0]["title"] == SAFE_LISTING["title"]
    assert body[0]["price"] == SAFE_LISTING["price"]


def test_successful_listing_not_in_failed_listings(client):
    headers = register_and_login(client)
    client.post("/api/analyses", json=SAFE_LISTING, headers=headers)

    assert client.get("/api/listings/failed", headers=headers).json() == []


def test_failed_listings_scoped_per_user(client, monkeypatch):
    alice = register_and_login(client, "alice@example.com")
    bob = register_and_login(client, "bob@example.com")

    from app.api import routes
    monkeypatch.setattr(routes, "get_provider", lambda: BrokenProvider(), raising=False)
    client.post("/api/analyses", json=SAFE_LISTING, headers=alice)

    assert len(client.get("/api/listings/failed", headers=alice).json()) == 1
    assert client.get("/api/listings/failed", headers=bob).json() == []


def test_retry_analysis_succeeds_and_clears_failed_list(client, monkeypatch):
    headers = register_and_login(client)

    from app.api import routes
    real_get_provider = routes.get_provider

    monkeypatch.setattr(routes, "get_provider", lambda: BrokenProvider(), raising=False)
    create = client.post("/api/analyses", json=SAFE_LISTING, headers=headers)
    assert create.status_code == 502

    failed = client.get("/api/listings/failed", headers=headers).json()
    assert len(failed) == 1
    listing_id = failed[0]["id"]

    monkeypatch.setattr(routes, "get_provider", real_get_provider, raising=False)
    retry = client.post(f"/api/listings/{listing_id}/retry", headers=headers)

    assert retry.status_code == 201
    assert retry.json()["risk_level"] == RiskLevel.low.value
    assert client.get("/api/listings/failed", headers=headers).json() == []
    assert len(client.get("/api/analyses", headers=headers).json()) == 1


def test_retry_still_failing_provider_returns_502_with_listing_id(client, monkeypatch):
    headers = register_and_login(client)

    from app.api import routes
    monkeypatch.setattr(routes, "get_provider", lambda: BrokenProvider(), raising=False)
    create = client.post("/api/analyses", json=SAFE_LISTING, headers=headers)
    listing_id = create.json()["detail"].split("id ")[1].split(")")[0]

    retry = client.post(f"/api/listings/{listing_id}/retry", headers=headers)

    assert retry.status_code == 502
    assert f"id {listing_id}" in retry.json()["detail"]
    # still unretrieved -- a second failed retry doesn't hide it or duplicate it.
    assert len(client.get("/api/listings/failed", headers=headers).json()) == 1


def test_retry_unknown_listing_returns_404(client):
    headers = register_and_login(client)
    assert client.post("/api/listings/999999/retry", headers=headers).status_code == 404


def test_retry_listing_not_owned_returns_404(client, monkeypatch):
    alice = register_and_login(client, "alice@example.com")
    bob = register_and_login(client, "bob@example.com")

    from app.api import routes
    monkeypatch.setattr(routes, "get_provider", lambda: BrokenProvider(), raising=False)
    client.post("/api/analyses", json=SAFE_LISTING, headers=alice)
    listing_id = client.get("/api/listings/failed", headers=alice).json()[0]["id"]

    assert client.post(f"/api/listings/{listing_id}/retry", headers=bob).status_code == 404


def test_evidence_policy_exhaustion_persists_only_listing(client, monkeypatch):
    headers = register_and_login(client)
    user_id = client.get("/api/auth/me", headers=headers).json()["id"]

    from app.api import routes
    from app.services.ai import AnalysisFailure
    from app.services.evidence_policy import EvidencePolicyViolation

    class PolicyExhaustedProvider:
        model_name = "policy-test"

        def analyze(self, listing):
            violation = EvidencePolicyViolation(("product_nonrecognition",))
            raise AnalysisFailure("evidence policy rejected both attempts") from violation

    monkeypatch.setattr(routes, "get_provider", lambda: PolicyExhaustedProvider())

    response = client.post("/api/analyses", json=SAFE_LISTING, headers=headers)

    assert response.status_code == 502
    # D-20/#80: message now names the listing id and points at retry, not
    # just "the listing was saved" with no way to act on it.
    assert response.json() == {
        "detail": (
            "AI analysis failed; the listing was saved (id 1). "
            "Find it under Failed listings to retry without re-entering it."
        ),
    }

    db = SessionLocal()
    try:
        listing = (
            db.query(Listing)
            .filter(
                Listing.user_id == user_id,
                Listing.title == SAFE_LISTING["title"],
            )
            .one()
        )
        assert listing.price == SAFE_LISTING["price"]
        assert listing.currency == SAFE_LISTING["currency"].upper()
        assert listing.source == SAFE_LISTING["source"]
        assert listing.description == SAFE_LISTING["description"]
        assert listing.url is None

        assert db.query(Analysis).filter(Analysis.listing_id == listing.id).count() == 0
        assert (
            db.query(RiskIndicator)
            .join(Analysis)
            .filter(Analysis.listing_id == listing.id)
            .count()
            == 0
        )
    finally:
        db.close()
