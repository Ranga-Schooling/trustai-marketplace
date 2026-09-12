"""Per-user daily quota on provider-consuming routes (D-22).

Workstream: E6 Testing & QA. The deployed API is publicly reachable and
every analysis spends a real provider call, so `POST /api/analyses` and
`POST /api/listings/{id}/retry` are capped per user per rolling 24 hours.
These tests pin the three properties that make the cap worth having: it
refuses once spent, failures count toward it (a broken provider can't be
driven for free), and retry can't be used to step around it.

Runs against MockProvider (AI_PROVIDER=mock, set in conftest.py) -- no
network, no API key, matching CLAUDE.md's CI constraint. The cap itself is
monkeypatched down rather than exercised at its real value so the suite
doesn't have to make fifty provider calls to prove one branch.
"""
import pytest

from app.api import routes
from app.core.config import Settings
from app.services import ai as ai_module
from conftest import SAFE_LISTING

pytestmark = pytest.mark.usefixtures("fresh_db")


def register_and_login(client, email="quota@example.com", password="s3curepass") -> dict:
    client.post("/api/auth/register", json={
        "email": email, "name": "Quota User", "password": password,
    })
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class BrokenProvider:
    model_name = "broken"

    def analyze(self, listing):
        raise ai_module.AnalysisFailure("simulated outage")


def test_requests_below_the_cap_are_unaffected(client, monkeypatch):
    monkeypatch.setattr(routes.settings, "max_analyses_per_day", 2)
    headers = register_and_login(client)

    assert client.post("/api/analyses", json=SAFE_LISTING, headers=headers).status_code == 201
    assert client.post("/api/analyses", json=SAFE_LISTING, headers=headers).status_code == 201


def test_the_request_past_the_cap_is_refused_with_429(client, monkeypatch):
    monkeypatch.setattr(routes.settings, "max_analyses_per_day", 1)
    headers = register_and_login(client)

    assert client.post("/api/analyses", json=SAFE_LISTING, headers=headers).status_code == 201

    refused = client.post("/api/analyses", json=SAFE_LISTING, headers=headers)
    assert refused.status_code == 429
    assert "Daily analysis limit reached" in refused.json()["detail"]


def test_a_refused_request_writes_no_listing(client, monkeypatch):
    """The quota is checked before the Listing row is committed, so a
    rejected submission leaves nothing behind for the owner to find."""
    monkeypatch.setattr(routes.settings, "max_analyses_per_day", 1)
    headers = register_and_login(client)

    client.post("/api/analyses", json=SAFE_LISTING, headers=headers)
    client.post("/api/analyses", json=SAFE_LISTING, headers=headers)

    assert len(client.get("/api/analyses", headers=headers).json()) == 1
    assert client.get("/api/listings/failed", headers=headers).json() == []


def test_failed_attempts_count_toward_the_cap(client, monkeypatch):
    """A provider outage still spends the call, so it still spends quota --
    otherwise a broken provider could be hammered without limit."""
    monkeypatch.setattr(routes.settings, "max_analyses_per_day", 1)
    monkeypatch.setattr(routes, "get_provider", lambda: BrokenProvider(), raising=False)
    headers = register_and_login(client)

    assert client.post("/api/analyses", json=SAFE_LISTING, headers=headers).status_code == 502

    monkeypatch.setattr(routes, "get_provider", ai_module.get_provider, raising=False)
    assert client.post("/api/analyses", json=SAFE_LISTING, headers=headers).status_code == 429


def test_retry_is_subject_to_the_same_cap(client, monkeypatch):
    monkeypatch.setattr(routes.settings, "max_analyses_per_day", 2)
    monkeypatch.setattr(routes, "get_provider", lambda: BrokenProvider(), raising=False)
    headers = register_and_login(client)

    assert client.post("/api/analyses", json=SAFE_LISTING, headers=headers).status_code == 502
    failed = client.get("/api/listings/failed", headers=headers).json()
    assert len(failed) == 1
    listing_id = failed[0]["id"]

    # Second failure spends the remaining allowance; the third attempt is refused
    # before the provider is reached.
    assert client.post(f"/api/listings/{listing_id}/retry", headers=headers).status_code == 502
    assert client.post(f"/api/listings/{listing_id}/retry", headers=headers).status_code == 429


def test_the_cap_is_scoped_per_user(client, monkeypatch):
    monkeypatch.setattr(routes.settings, "max_analyses_per_day", 1)
    first = register_and_login(client, email="first@example.com")
    second = register_and_login(client, email="second@example.com")

    assert client.post("/api/analyses", json=SAFE_LISTING, headers=first).status_code == 201
    assert client.post("/api/analyses", json=SAFE_LISTING, headers=first).status_code == 429
    assert client.post("/api/analyses", json=SAFE_LISTING, headers=second).status_code == 201


def test_cors_origins_parse_from_a_comma_separated_setting():
    settings = Settings(cors_allow_origins="https://a.example , https://b.example")
    assert settings.cors_origin_list == ["https://a.example", "https://b.example"]


def test_cors_origins_ignore_blank_entries():
    assert Settings(cors_allow_origins="https://a.example,,").cors_origin_list == [
        "https://a.example"
    ]
