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
    GeminiProvider,
    GPTProvider,
    GroqProvider,
    MockProvider,
    get_provider,
)

VALID_RESULT_JSON = """
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


class FakeResponse:
    """OpenAI-compatible shape -- shared by Groq and GPT (both subclass
    OpenAICompatibleProvider, same request/response format)."""

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "content": VALID_RESULT_JSON,
                    }
                }
            ]
        }


class FakeGeminiResponse:
    """Gemini's generateContent shape -- candidates/content/parts, not
    OpenAI's choices/message."""

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": VALID_RESULT_JSON}],
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


def test_groq_provider_requires_api_key(monkeypatch):
    monkeypatch.setattr("app.services.ai.settings.groq_api_key", "")

    with pytest.raises(AnalysisFailure):
        GroqProvider()


# ---------- GPTProvider (Card #20) ----------
# Same OpenAI-compatible request/response shape as Groq -- shares
# OpenAICompatibleProvider, so these tests mirror the Groq ones above.


def test_gpt_provider_success(monkeypatch):
    monkeypatch.setattr("app.services.ai.httpx.post", lambda *a, **kw: FakeResponse())
    monkeypatch.setattr("app.services.ai.settings.openai_api_key", "test-key")

    provider = GPTProvider()
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
    assert raw_json == VALID_RESULT_JSON


def test_gpt_provider_raises_analysis_failure_after_two_failures(monkeypatch):
    def fake_post(*args, **kwargs):
        raise httpx.ConnectError("Simulated connection failure")

    monkeypatch.setattr("app.services.ai.httpx.post", fake_post)
    monkeypatch.setattr("app.services.ai.settings.openai_api_key", "test-key")

    provider = GPTProvider()
    listing = ListingIn(
        title="IKEA Billy bookcase, white",
        price=450.0,
        currency="ZAR",
        source="Facebook Marketplace",
        description="Used bookcase in good condition, collection in Randburg.",
    )

    with pytest.raises(AnalysisFailure):
        provider.analyze(listing)


def test_gpt_provider_requires_api_key(monkeypatch):
    monkeypatch.setattr("app.services.ai.settings.openai_api_key", "")

    with pytest.raises(AnalysisFailure):
        GPTProvider()


def test_get_provider_returns_gpt_provider(monkeypatch):
    monkeypatch.setattr("app.services.ai.settings.ai_provider", "gpt")
    monkeypatch.setattr("app.services.ai.settings.openai_api_key", "test-key")

    provider = get_provider()

    assert isinstance(provider, GPTProvider)


# ---------- GeminiProvider (Card #20) ----------
# Distinct request/response shape (contents/parts, not messages/choices) --
# does not share OpenAICompatibleProvider, so this exercises its own
# success/retry/failure paths rather than relying on the shared base.


def test_gemini_provider_success(monkeypatch):
    monkeypatch.setattr("app.services.ai.httpx.post", lambda *a, **kw: FakeGeminiResponse())
    monkeypatch.setattr("app.services.ai.settings.gemini_api_key", "test-key")

    provider = GeminiProvider()
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
    assert raw_json == VALID_RESULT_JSON


def test_gemini_provider_retries_once_then_succeeds(monkeypatch):
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("Simulated connection failure")
        return FakeGeminiResponse()

    monkeypatch.setattr("app.services.ai.httpx.post", fake_post)
    monkeypatch.setattr("app.services.ai.settings.gemini_api_key", "test-key")

    provider = GeminiProvider()
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
    assert raw_json == VALID_RESULT_JSON


def test_gemini_provider_raises_analysis_failure_after_two_failures(monkeypatch):
    def fake_post(*args, **kwargs):
        raise httpx.ConnectError("Simulated connection failure")

    monkeypatch.setattr("app.services.ai.httpx.post", fake_post)
    monkeypatch.setattr("app.services.ai.settings.gemini_api_key", "test-key")

    provider = GeminiProvider()
    listing = ListingIn(
        title="IKEA Billy bookcase, white",
        price=450.0,
        currency="ZAR",
        source="Facebook Marketplace",
        description="Used bookcase in good condition, collection in Randburg.",
    )

    with pytest.raises(AnalysisFailure):
        provider.analyze(listing)


def test_gemini_provider_requires_api_key(monkeypatch):
    monkeypatch.setattr("app.services.ai.settings.gemini_api_key", "")

    with pytest.raises(AnalysisFailure):
        GeminiProvider()


def test_get_provider_returns_gemini_provider(monkeypatch):
    monkeypatch.setattr("app.services.ai.settings.ai_provider", "gemini")
    monkeypatch.setattr("app.services.ai.settings.gemini_api_key", "test-key")

    provider = get_provider()

    assert isinstance(provider, GeminiProvider)
