"""Risk analysis context — AI providers behind one interface.

Workstream: E3 AI Analysis & Risk Scoring (owner: Ahmed)
Stories: US-3.1 (structured analysis), US-3.2 (auditable output),
US-3.3 (provider-independent testing)

The Protocol, exception and provider selection below are the agreed
contract — keep them. The two providers are the owner's work.

Design decisions already agreed (docs/DESIGN_NOTES.md):
- Every provider returns (AIAnalysisResult, raw_response_text). The schema
  in app/schemas/schemas.py is the anti-corruption layer: nothing the LLM
  says enters the domain until it validates.
- Risk is categorical, derived from indicator severities:
  any high indicator -> high/avoid; any medium -> medium/caution;
  otherwise low/buy. No LLM-invented numeric scores.
- GroqProvider/GPTProvider: OpenAI-compatible chat completions, JSON mode
  (response_format={"type": "json_object"}), temperature ~0.2, 30s timeout,
  ONE retry on invalid output, then raise AnalysisFailure. Share
  OpenAICompatibleProvider (D-10) since both speak the same request/
  response shape.
- GeminiProvider: same external contract (validate, one retry, then
  AnalysisFailure) but Google's generateContent API isn't OpenAI-shaped,
  so it doesn't subclass OpenAICompatibleProvider (D-10).
- MockProvider: deterministic keyword/price heuristics, no network — this is
  what tests and CI run against, and it doubles as the documented list of
  fraud signals the product targets (urgency language, off-platform payment,
  off-platform contact, suspiciously low price...).

"""
import json
from typing import Protocol

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.schemas import (
    AIAnalysisResult,
    ListingIn,
    Recommendation,
    RiskIndicatorOut,
    RiskLevel,
)

settings = get_settings()

# Fixed currency thresholds keep MockProvider deterministic for tests.
# This mock intentionally does not perform live exchange-rate conversion.
PRICE_THRESHOLDS = {
    "USD": 50,
    "CAD": 65,
    "EUR": 45,
    "GBP": 40,
}
DEFAULT_PRICE_THRESHOLD = 50

SYSTEM_PROMPT = """You are a marketplace listing risk analyst. Assess only the
information supplied in the listing and do not invent facts or market data.

Return ONLY one valid JSON object with exactly this AIAnalysisResult structure:
{
  "summary": "string",
  "risk_level": "low | medium | high",
  "risk_indicators": [
    {
      "category": "string",
      "severity": "low | medium | high",
      "explanation": "string"
    }
  ],
  "price_assessment": "string",
  "seller_questions": ["string"],
  "recommendation": "buy | caution | avoid"
}

Do not include Markdown, code fences, commentary, or fields outside the JSON.
Return no more than 10 risk indicators and between 1 and 8 seller questions.

Derive risk_level from the risk indicator severities: if any indicator is high,
risk_level must be high; otherwise, if any indicator is medium, risk_level must
be medium; otherwise risk_level must be low. Derive recommendation only from
risk_level: high means avoid, medium means caution, and low means buy. Never
invent or return a numeric risk score.

Clearly acknowledge uncertainty. Explain that the assessment is based only on
the supplied listing, may miss scams or flag legitimate listings, and does not
guarantee that the listing or seller is safe."""


class AnalysisFailure(Exception):
    """Raised when a provider cannot produce a valid structured result."""


class AIProvider(Protocol):
    model_name: str

    def analyze(self, listing: ListingIn) -> tuple[AIAnalysisResult, str]:
        """Return (validated result, raw response text)."""
        ...


class MockProvider:
    """Deterministic heuristic analyzer — no network, stable for tests."""

    model_name = "mock-heuristics-v1"

    def analyze(self, listing: ListingIn) -> tuple[AIAnalysisResult, str]:
        text = f"{listing.title} {listing.description}".lower()
        indicators: list[RiskIndicatorOut] = []

        if any(term in text for term in ("urgent", "today only", "act now")):
            indicators.append(
                RiskIndicatorOut(
                    category="Urgency language",
                    severity=RiskLevel.medium,
                    explanation="The listing pressures the buyer to act quickly.",
                )
            )

        if any(
            term in text
            for term in ("gift card", "wire transfer", "bitcoin", "cryptocurrency")
        ):
            indicators.append(
                RiskIndicatorOut(
                    category="Off-platform payment",
                    severity=RiskLevel.high,
                    explanation="The seller requests a difficult-to-recover payment method.",
                )
            )

        if any(term in text for term in ("whatsapp", "telegram", "text me")):
            indicators.append(
                RiskIndicatorOut(
                    category="Off-platform contact",
                    severity=RiskLevel.medium,
                    explanation=(
                        "The seller asks to move communication away from the marketplace."
                    ),
                )
            )

        threshold = PRICE_THRESHOLDS.get(
            listing.currency,
            DEFAULT_PRICE_THRESHOLD,
        )
        if listing.price < threshold:
            indicators.append(
                RiskIndicatorOut(
                    category="Suspiciously low price",
                    severity=RiskLevel.medium,
                    explanation="The asking price is unusually low and should be verified.",
                )
            )

        severities = {indicator.severity for indicator in indicators}
        if RiskLevel.high in severities:
            risk_level = RiskLevel.high
            recommendation = Recommendation.avoid
        elif RiskLevel.medium in severities:
            risk_level = RiskLevel.medium
            recommendation = Recommendation.caution
        else:
            risk_level = RiskLevel.low
            recommendation = Recommendation.buy

        if indicators:
            summary = (
                f"The listing contains {len(indicators)} potential risk indicator(s). "
                "Verify the seller and item before proceeding."
            )
        else:
            summary = (
                "No obvious risk indicators were found, but this does not guarantee "
                "that the listing is safe."
            )

        price_assessment = (
            "The asking price appears unusually low and needs independent verification."
            if listing.price < threshold
            else "The asking price cannot be verified without comparable market data."
        )

        result = AIAnalysisResult(
            summary=summary,
            risk_level=risk_level,
            risk_indicators=indicators,
            price_assessment=price_assessment,
            seller_questions=[
                "Can you provide proof of ownership or purchase?",
                "Can I inspect the item before making payment?",
                "Will you accept payment through the marketplace's protected method?",
            ],
            recommendation=recommendation,
        )
        return result, result.model_dump_json()


def _listing_prompt(listing: ListingIn) -> str:
    return (
        "Analyze this marketplace listing:\n"
        f"Title: {listing.title}\n"
        f"Price: {listing.price} {listing.currency}\n"
        f"Source: {listing.source}\n"
        f"Description:\n{listing.description}\n"
        f"URL: {listing.url or 'Not provided'}"
    )


class OpenAICompatibleProvider:
    """Base for chat-completions APIs that speak the OpenAI request/response
    shape (messages/choices, JSON mode) -- Groq and OpenAI's own API both do
    (Card #20: GroqProvider was the whole implementation before this split;
    GPTProvider is now a ~5-line subclass, not a second copy of this logic).

    Subclasses set ENDPOINT and pass their own api_key/model_name/label.
    """

    ENDPOINT: str

    def __init__(self, api_key: str, model_name: str, provider_label: str) -> None:
        if not api_key:
            raise AnalysisFailure(f"{provider_label} API key is not configured")
        self.api_key = api_key
        self.model_name = model_name
        self._provider_label = provider_label

    def analyze(self, listing: ListingIn) -> tuple[AIAnalysisResult, str]:
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _listing_prompt(listing)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(2):
            try:
                response = httpx.post(
                    self.ENDPOINT,
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()

                raw_json = response.json()["choices"][0]["message"]["content"]
                result = AIAnalysisResult.model_validate_json(raw_json)
                return result, raw_json
            except (
                httpx.HTTPError,
                json.JSONDecodeError,
                ValidationError,
                KeyError,
                IndexError,
                TypeError,
            ) as exc:
                if attempt == 1:
                    raise AnalysisFailure(
                        f"{self._provider_label} could not produce a valid analysis "
                        "after two attempts"
                    ) from exc
                # Let the loop naturally advance to the second (and final) retry.


class GroqProvider(OpenAICompatibleProvider):
    """Groq chat completions (OpenAI-compatible) with JSON mode."""

    ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self) -> None:
        super().__init__(settings.groq_api_key, settings.groq_model, "Groq")


class GPTProvider(OpenAICompatibleProvider):
    """OpenAI chat completions with JSON mode (Card #20)."""

    ENDPOINT = "https://api.openai.com/v1/chat/completions"

    def __init__(self) -> None:
        super().__init__(settings.openai_api_key, settings.openai_model, "OpenAI")


class GeminiProvider:
    """Google Gemini generateContent, JSON mode (Card #20).

    Gemini's request/response shape isn't OpenAI-compatible (contents/parts,
    not messages/choices), so unlike GPTProvider this can't reuse
    OpenAICompatibleProvider -- but the external contract (validate into
    AIAnalysisResult, one retry, then AnalysisFailure) is identical.
    """

    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise AnalysisFailure("Gemini API key is not configured")
        self.model_name = settings.gemini_model

    @property
    def _endpoint(self) -> str:
        return (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_name}:generateContent"
        )

    def analyze(self, listing: ListingIn) -> tuple[AIAnalysisResult, str]:
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": _listing_prompt(listing)}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        headers = {
            "x-goog-api-key": settings.gemini_api_key,
            "Content-Type": "application/json",
        }

        for attempt in range(2):
            try:
                response = httpx.post(
                    self._endpoint,
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()

                raw_json = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                result = AIAnalysisResult.model_validate_json(raw_json)
                return result, raw_json
            except (
                httpx.HTTPError,
                json.JSONDecodeError,
                ValidationError,
                KeyError,
                IndexError,
                TypeError,
            ) as exc:
                if attempt == 1:
                    raise AnalysisFailure(
                        "Gemini could not produce a valid analysis after two attempts"
                    ) from exc
                # Let the loop naturally advance to the second (and final) retry.


def get_provider() -> AIProvider:
    if settings.ai_provider == "groq":
        return GroqProvider()
    if settings.ai_provider == "gpt":
        return GPTProvider()
    if settings.ai_provider == "gemini":
        return GeminiProvider()
    return MockProvider()
