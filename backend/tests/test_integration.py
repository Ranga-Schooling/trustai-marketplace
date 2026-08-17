"""Integration tests: chained journeys across auth -> listing -> analysis.

Workstream: E6 Testing & QA. Unlike test_api.py (one acceptance criterion
per test, story-by-story), these drive a single simulated user session
through several endpoints in sequence and assert the system holds together
end to end -- a login token keeps authorizing later calls, a submitted
listing's analysis is retrievable from history in the same session, and
two users' full sessions never leak into each other. Runs entirely against
MockProvider (AI_PROVIDER=mock, set in conftest.py) -- no network, no API
key, matching CLAUDE.md's CI constraint.
"""
import pytest

from app.schemas.schemas import RiskLevel
from conftest import SAFE_LISTING, SCAM_LISTING

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("fresh_db")]


def register(client, email, name="Journey User", password="s3curepass"):
    r = client.post("/api/auth/register", json={
        "email": email, "name": name, "password": password,
    })
    assert r.status_code == 201
    return r.json()


def login(client, email, password="s3curepass") -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_full_journey_register_login_submit_view_history(client):
    register(client, "journey@example.com")
    headers = login(client, "journey@example.com")

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "journey@example.com"

    safe = client.post("/api/analyses", json=SAFE_LISTING, headers=headers)
    assert safe.status_code == 201
    assert safe.json()["risk_level"] == RiskLevel.low.value

    scam = client.post("/api/analyses", json=SCAM_LISTING, headers=headers)
    assert scam.status_code == 201
    assert scam.json()["risk_level"] == RiskLevel.high.value

    history = client.get("/api/analyses", headers=headers)
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [scam.json()["id"], safe.json()["id"]]

    detail = client.get(f"/api/analyses/{safe.json()['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["listing_title"] == SAFE_LISTING["title"]
    assert detail.json()["risk_score"] == safe.json()["risk_score"]


def test_journey_survives_profile_edit_mid_session(client):
    register(client, "edit@example.com")
    headers = login(client, "edit@example.com")

    client.post("/api/analyses", json=SAFE_LISTING, headers=headers)

    patch = client.patch(
        "/api/auth/me",
        json={"name": "New Name", "email": "edited@example.com"},
        headers=headers,
    )
    assert patch.status_code == 200

    # The bearer token is keyed on user id, not email -- it must keep
    # authorizing requests after the user changes their own email.
    history = client.get("/api/analyses", headers=headers)
    assert history.status_code == 200
    assert len(history.json()) == 1

    me = client.get("/api/auth/me", headers=headers)
    assert me.json()["email"] == "edited@example.com"


def test_two_users_full_sessions_stay_isolated(client):
    register(client, "alice@example.com")
    alice = login(client, "alice@example.com")
    register(client, "bob@example.com")
    bob = login(client, "bob@example.com")

    alice_analysis = client.post("/api/analyses", json=SAFE_LISTING, headers=alice).json()
    bob_analysis = client.post("/api/analyses", json=SCAM_LISTING, headers=bob).json()

    assert len(client.get("/api/analyses", headers=alice).json()) == 1
    assert len(client.get("/api/analyses", headers=bob).json()) == 1

    assert client.get(f"/api/analyses/{bob_analysis['id']}", headers=alice).status_code == 404
    assert client.get(f"/api/analyses/{alice_analysis['id']}", headers=bob).status_code == 404


def test_ai_outage_mid_session_does_not_break_subsequent_analyses(client, monkeypatch):
    """A provider outage on one submission saves the listing and returns
    502; the same session recovers immediately on the next submission
    once the provider is healthy again."""
    register(client, "outage@example.com")
    headers = login(client, "outage@example.com")

    from app.api import routes
    from app.services import ai as ai_module

    class BrokenProvider:
        model_name = "broken"

        def analyze(self, listing):
            raise ai_module.AnalysisFailure("simulated outage")

    monkeypatch.setattr(routes, "get_provider", lambda: BrokenProvider())
    failed = client.post("/api/analyses", json=SAFE_LISTING, headers=headers)
    assert failed.status_code == 502

    monkeypatch.undo()
    recovered = client.post("/api/analyses", json=SAFE_LISTING, headers=headers)
    assert recovered.status_code == 201

    # The failed submission left a Listing row with no Analysis, so it
    # never surfaces in history -- only the recovered analysis does.
    history = client.get("/api/analyses", headers=headers).json()
    assert len(history) == 1
    assert history[0]["id"] == recovered.json()["id"]
