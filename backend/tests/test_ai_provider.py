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


TINY_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAA"


def test_groq_provider_sends_plain_text_content_without_images(monkeypatch):
    """No images (the common case) -- message content is unchanged (a plain
    string), not the multi-part shape, so this doesn't regress the existing
    text-only request format (US-2.4/D-12)."""
    captured = {}

    def fake_post(*args, **kwargs):
        captured["payload"] = kwargs["json"]
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
    provider.analyze(listing)

    user_content = captured["payload"]["messages"][1]["content"]
    assert isinstance(user_content, str)


def test_groq_provider_sends_image_parts_when_images_present(monkeypatch):
    """US-2.4/D-12 AC3: images present -> OpenAI-shaped multi-part content
    (text part + one image_url part per image), same request shape a
    vision-capable model expects. MockProvider is unaffected -- this only
    covers the real-provider payload construction, no network call."""
    captured = {}

    def fake_post(*args, **kwargs):
        captured["payload"] = kwargs["json"]
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
        images=[TINY_PNG],
    )
    provider.analyze(listing)

    user_content = captured["payload"]["messages"][1]["content"]
    assert isinstance(user_content, list)
    assert user_content[0] == {"type": "text", "text": user_content[0]["text"]}
    assert user_content[1] == {"type": "image_url", "image_url": {"url": TINY_PNG}}
