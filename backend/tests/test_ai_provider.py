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
                            "price_plausibility": "plausible",
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


@pytest.mark.parametrize("listing_kwargs", [
    # Clean listing: no risk indicators triggered.
    {},
    # Multi-signal listing: urgency + off-platform payment + off-platform
    # contact + low price all fire, so this also proves determinism isn't
    # trivial just because the indicator list happens to be empty.
    {
        "price": 15.0,
        "currency": "USD",
        "description": (
            "URGENT sale today only!! Payment by gift card or wire transfer "
            "only, contact me on WhatsApp."
        ),
    },
])
def test_mock_provider_is_deterministic(listing_kwargs):
    """US-3.3: MockProvider must be a pure function of its input -- no
    randomness, no hidden state -- so CI results are reproducible and
    testing costs nothing. Two independent providers analyzing the same
    listing must produce byte-identical results."""
    base_listing = {
        "title": "IKEA Billy bookcase, white",
        "price": 450.0,
        "currency": "ZAR",
        "source": "Facebook Marketplace",
        "description": "Used bookcase in good condition, collection in Randburg.",
    }
    listing = ListingIn(**{**base_listing, **listing_kwargs})

    result_1, raw_1 = MockProvider().analyze(listing)
    result_2, raw_2 = MockProvider().analyze(listing)

    assert result_1 == result_2
    assert raw_1 == raw_2


def test_get_provider_returns_groq_provider(monkeypatch):
    monkeypatch.setattr("app.services.ai.settings.ai_provider", "groq")
    monkeypatch.setattr("app.services.ai.settings.groq_api_key", "test-key")

    provider = get_provider()

    assert isinstance(provider, GroqProvider)
