import httpx
import pytest

from app.schemas.schemas import (
    AIAnalysisResult,
    ListingIn,
    Recommendation,
    RiskLevel,
)
from app.services.ai import (
    AnalysisFailure,
    GroqProvider,
    MockProvider,
    get_provider,
)


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "content": """
                        {
                            "summary": "No obvious risk indicators were found.",
                            "risk_level": "low",
                            "risk_indicators": [],
                            "price_assessment": "The price requires independent verification.",
                            "seller_questions": [
                                "Can I inspect the item before paying?"
                            ],
                            "recommendation": "buy"
                        }
                        """
                    }
                }
            ]
        }


def test_groq_provider_success(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai.httpx.post",
        lambda *args, **kwargs: FakeResponse(),
    )
    monkeypatch.setattr("app.services.ai.settings.groq_api_key", "test-key")

    provider = GroqProvider()
    listing = ListingIn(
        title="IKEA Billy bookcase, white",
        price=450.0,
        currency="ZAR",
        source="Facebook Marketplace",
        description="Used bookcase in good condition, collection in Randburg.",
    )

    result, raw_json = provider.analyze(listing)

    assert isinstance(result, AIAnalysisResult)
    assert result.risk_level is RiskLevel.low
    assert result.recommendation is Recommendation.buy
    assert raw_json == FakeResponse().json()["choices"][0]["message"]["content"]


def test_groq_provider_retries_once_then_succeeds(monkeypatch):
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("Simulated connection failure")
        return FakeResponse()

    monkeypatch.setattr("app.services.ai.httpx.post", fake_post)
    monkeypatch.setattr("app.services.ai.settings.groq_api_key", "test-key")

    provider = GroqProvider()
    listing = ListingIn(
        title="IKEA Billy bookcase, white",
        price=450.0,
        currency="ZAR",
        source="Facebook Marketplace",
        description="Used bookcase in good condition, collection in Randburg.",
    )

    result, raw_json = provider.analyze(listing)

    assert calls == 2
    assert isinstance(result, AIAnalysisResult)
    assert result.summary == "No obvious risk indicators were found."
    assert result.recommendation is Recommendation.buy
    assert raw_json == FakeResponse().json()["choices"][0]["message"]["content"]


def test_groq_provider_raises_analysis_failure_after_two_failures(monkeypatch):
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("Simulated connection failure")

    monkeypatch.setattr("app.services.ai.httpx.post", fake_post)
    monkeypatch.setattr("app.services.ai.settings.groq_api_key", "test-key")

    provider = GroqProvider()
    listing = ListingIn(
        title="IKEA Billy bookcase, white",
        price=450.0,
        currency="ZAR",
        source="Facebook Marketplace",
        description="Used bookcase in good condition, collection in Randburg.",
    )

    with pytest.raises(AnalysisFailure):
        provider.analyze(listing)

    assert calls == 2


def test_get_provider_returns_mock_provider(monkeypatch):
    monkeypatch.setattr("app.services.ai.settings.ai_provider", "mock")

    provider = get_provider()

    assert isinstance(provider, MockProvider)


def test_get_provider_returns_groq_provider(monkeypatch):
    monkeypatch.setattr("app.services.ai.settings.ai_provider", "groq")
    monkeypatch.setattr("app.services.ai.settings.groq_api_key", "test-key")

    provider = get_provider()

    assert isinstance(provider, GroqProvider)
