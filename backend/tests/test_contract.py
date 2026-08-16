"""Contract tests: the frozen surfaces named in CLAUDE.md's SCHEMA-0 freeze.

Workstream: E6 Testing & QA. These don't map to a single user story --
they pin down structural guarantees other code depends on:
  - every AIProvider satisfies the `AIProvider` Protocol and its output
    round-trips cleanly through the `AIAnalysisResult` validator
  - `AIAnalysisResult` structurally has no numeric field (D-05), so a
    future PR can't quietly reintroduce a "confidence score" -- this pins
    the schema shape itself, not just current provider behavior
  - a hand-authored, Groq-shaped chat-completion payload still parses
    through that same validator (this is NOT a captured real Groq
    response -- see the note on GROQ_SHAPED_CONTENT below; the
    "replaying recorded Groq responses" item in docs/testing/README.md's
    planned coverage is still open)
  - malformed/out-of-contract LLM output is rejected or silently excluded
    by the validator, never entering the domain (the anti-corruption
    layer the schemas.py docstring describes)
  - the frozen HTTP surface (paths, status codes, response field shape)
    behaves as routes.py's contract docstring documents

No network calls, no API key -- runs on MockProvider like every other
suite here (CLAUDE.md: "CI runs on the MockProvider only").
"""
import inspect
import typing

import pydantic
import pytest
from pydantic import ValidationError

from app.schemas.schemas import (
    AIAnalysisResult,
    AnalysisOut,
    ListingIn,
    Recommendation,
    RiskLevel,
)
from app.services.ai import GroqProvider, MockProvider
from conftest import SAFE_LISTING

pytestmark = [pytest.mark.contract, pytest.mark.usefixtures("fresh_db")]

SAMPLE_LISTING = ListingIn(**SAFE_LISTING)


# ---------- AIAnalysisResult schema contract (D-05) ----------

def _contains_numeric_type(annotation, _seen: frozenset = frozenset()) -> bool:
    """True if `annotation` is int/float, or int/float appears anywhere in
    it once Optional/Union/list/dict wrappers AND nested Pydantic models
    are unwrapped -- so `int | None`, `list[int]`, and a numeric field
    added to a nested model like `RiskIndicatorOut` are all caught, not
    just a bare `int` on the top-level model."""
    if annotation in (int, float):
        return True
    if isinstance(annotation, type) and issubclass(annotation, pydantic.BaseModel):
        if annotation in _seen:
            return False
        _seen = _seen | {annotation}
        return any(
            _contains_numeric_type(field.annotation, _seen)
            for field in annotation.model_fields.values()
        )
    return any(_contains_numeric_type(arg, _seen) for arg in typing.get_args(annotation))


def test_ai_analysis_result_has_no_numeric_field():
    """No AIProvider is ever asked for or returns a score (D-05). Checking
    the schema shape, not just current provider output, catches a future
    accidental numeric field -- including one hidden behind `| None` or a
    container type -- even before any provider tries to fill it."""
    for name, field in AIAnalysisResult.model_fields.items():
        assert not _contains_numeric_type(field.annotation), (
            f"AIAnalysisResult.{name} is (or contains) a numeric type -- "
            "risk must stay categorical (D-05)"
        )


def test_llm_extra_numeric_field_never_enters_the_domain():
    """Even if an LLM bolts a numeric field onto otherwise-valid JSON, it's
    not part of AIAnalysisResult and never reaches the domain."""
    content = (
        '{"summary": "x", "risk_level": "low", "risk_indicators": [], '
        '"price_assessment": "x", "seller_questions": ["x"], '
        '"recommendation": "buy", "confidence_score": 87}'
    )

    result = AIAnalysisResult.model_validate_json(content)

    assert not hasattr(result, "confidence_score")
    assert "confidence_score" not in result.model_dump()


@pytest.mark.parametrize("broken_content", [
    # Free-text risk_level instead of the RiskLevel enum.
    '{"summary": "x", "risk_level": "kinda risky", "risk_indicators": [], '
    '"price_assessment": "x", "seller_questions": ["x"], "recommendation": "buy"}',
    # Missing a required field (summary).
    '{"risk_level": "low", "risk_indicators": [], '
    '"price_assessment": "x", "seller_questions": ["x"], "recommendation": "buy"}',
    # seller_questions violates min_length=1.
    '{"summary": "x", "risk_level": "low", "risk_indicators": [], '
    '"price_assessment": "x", "seller_questions": [], "recommendation": "buy"}',
])
def test_malformed_llm_output_is_rejected_by_the_validator(broken_content):
    with pytest.raises(ValidationError):
        AIAnalysisResult.model_validate_json(broken_content)


# ---------- AIProvider protocol contract ----------

def test_mock_provider_satisfies_ai_provider_protocol():
    provider = MockProvider()
    assert isinstance(provider.model_name, str) and provider.model_name
    assert list(inspect.signature(provider.analyze).parameters) == ["listing"]


def test_groq_provider_satisfies_ai_provider_protocol(monkeypatch):
    monkeypatch.setattr("app.services.ai.settings.groq_api_key", "test-key")

    provider = GroqProvider()

    assert isinstance(provider.model_name, str) and provider.model_name
    assert list(inspect.signature(provider.analyze).parameters) == ["listing"]


@pytest.mark.parametrize("description", [
    "Used bookcase in good condition, collection in Randburg.",
    "URGENT sale today only!! Payment by gift card, contact me on WhatsApp.",
])
def test_mock_provider_output_round_trips_through_ai_analysis_result(description):
    listing = ListingIn(**{**SAMPLE_LISTING.model_dump(), "description": description})

    result, raw_json = MockProvider().analyze(listing)

    assert isinstance(result, AIAnalysisResult)
    assert AIAnalysisResult.model_validate_json(raw_json) == result


# ---------- Groq-shaped response replay ----------

# NOT a captured real Groq response -- hand-authored to match the shape
# GroqProvider.analyze expects, same as test_ai_provider.py's synthetic
# fakes. A real captured-response replay (with actual Groq quirks: key
# ordering, whitespace, occasional extra fields) is still the open item
# in docs/testing/README.md's planned coverage, not this test.
GROQ_SHAPED_CONTENT = """{
  "summary": "The listing shows one urgency signal that should be verified with the seller.",
  "risk_level": "medium",
  "risk_indicators": [
    {
      "category": "Urgency language",
      "severity": "medium",
      "explanation": "The listing pressures the buyer to act quickly."
    }
  ],
  "price_assessment": "The asking price cannot be verified without comparable market data.",
  "seller_questions": [
    "Can you provide proof of ownership or purchase?",
    "Can I inspect the item before making payment?"
  ],
  "recommendation": "caution"
}"""


def test_groq_shaped_response_replays_through_the_validator():
    """A hand-authored, Groq-shaped chat-completion payload, replayed
    through the same AIAnalysisResult validator GroqProvider.analyze uses
    -- no live Groq call, so this stays in CI without a network call or an
    API key (CLAUDE.md)."""
    result = AIAnalysisResult.model_validate_json(GROQ_SHAPED_CONTENT)

    assert result.risk_level is RiskLevel.medium
    assert result.recommendation is Recommendation.caution
    assert result.risk_indicators[0].severity is RiskLevel.medium


# ---------- Frozen HTTP surface (SCHEMA-0) ----------

def test_frozen_route_surface_matches_the_documented_contract(client):
    """Hit each documented endpoint at the HTTP level and pin its status
    code -- black-box, so it doesn't depend on FastAPI/Starlette's
    internal route representation."""
    assert client.get("/api/health").status_code == 200

    register = client.post("/api/auth/register", json={
        "email": "contract@example.com", "name": "Contract", "password": "s3curepass",
    })
    assert register.status_code == 201

    login = client.post("/api/auth/login", json={
        "email": "contract@example.com", "password": "s3curepass",
    })
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.patch("/api/auth/me", json={"name": "New"}, headers=headers).status_code == 200

    created = client.post(
        "/api/analyses",
        json=SAMPLE_LISTING.model_dump(mode="json"),
        headers=headers,
    )
    assert created.status_code == 201
    assert client.get("/api/analyses", headers=headers).status_code == 200
    assert client.get(f"/api/analyses/{created.json()['id']}", headers=headers).status_code == 200


def test_analysis_response_matches_the_documented_field_contract(client):
    """AnalysisOut's field set is what the frontend builds against -- pin
    it exactly, and confirm risk_score (D-09) is the one bounded numeric
    exception, computed server-side, not an LLM-invented value."""
    register_resp = client.post("/api/auth/register", json={
        "email": "fields@example.com", "name": "Fields", "password": "s3curepass",
    })
    assert register_resp.status_code == 201
    login_resp = client.post("/api/auth/login", json={
        "email": "fields@example.com", "password": "s3curepass",
    })
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    body = client.post(
        "/api/analyses",
        json=SAMPLE_LISTING.model_dump(mode="json"),
        headers=headers,
    ).json()

    assert set(body.keys()) == set(AnalysisOut.model_fields.keys())
    assert isinstance(body["risk_score"], int)
    assert 0 <= body["risk_score"] <= 100
    assert body["risk_level"] in {level.value for level in RiskLevel}
    assert body["recommendation"] in {rec.value for rec in Recommendation}
