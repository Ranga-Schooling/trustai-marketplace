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
- Price plausibility is likewise categorical (plausible/suspicious/
  too_good_to_be_true, D-08) -- never a numeric or factual market-value
  claim; price_assessment stays qualitative prose explaining the tier.
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
import logging
from collections.abc import Callable
from typing import Protocol

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.schemas import (
    AIAnalysisResult,
    ListingIn,
    PricePlausibility,
    Recommendation,
    RiskIndicatorOut,
    RiskLevel,
)

settings = get_settings()
logger = logging.getLogger(__name__)

KNOWN_PROVIDERS = {"mock", "groq", "gpt", "gemini"}

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
  "price_plausibility": "plausible | suspicious | too_good_to_be_true",
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

Derive price_plausibility from how the asking price compares to what's
generally plausible for the kind of item described, using only common-sense
reasoning about the listing itself -- not a claimed market value, not a
citation to any pricing data or source. Use too_good_to_be_true when the
price is so far below what such an item would reasonably cost that it is
itself a red flag; suspicious when the price is somewhat low or otherwise
questionable; plausible otherwise. price_assessment must stay a qualitative
explanation of that judgment and must never state a specific figure, range,
or source as if it were verified market data.

No image evidence is supplied to or analyzed by this model. The listing URL
is provided only as text and is not opened by the model. Do not state or imply
that the original marketplace listing has no photos or images. Unless they are
explicitly described in the supplied text, image presence, quality, and
authenticity are unknown; even then, treat the description as an unverified
claim rather than inspected visual evidence.

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

        # Two-tier split below the existing "suspiciously low" threshold: a
        # price under half that threshold is a red flag in its own right,
        # not just "worth verifying" -- distinct wording, same no-market-
        # data honesty as the single-tier version this replaces.
        if listing.price < threshold / 2:
            price_plausibility = PricePlausibility.too_good_to_be_true
            price_assessment = (
                "The asking price is far below what would be plausible for an item "
                "like this, which is itself a strong warning sign — treat it as too "
                "good to be true until the seller proves otherwise."
            )
        elif listing.price < threshold:
            price_plausibility = PricePlausibility.suspicious
            price_assessment = (
                "The asking price appears unusually low and needs independent verification."
            )
        else:
            price_plausibility = PricePlausibility.plausible
            price_assessment = (
                "The asking price cannot be verified without comparable market data, "
                "but nothing here suggests it is implausible."
            )

        result = AIAnalysisResult(
            summary=summary,
            risk_level=risk_level,
            risk_indicators=indicators,
            price_assessment=price_assessment,
            price_plausibility=price_plausibility,
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
        f"URL: {listing.url or 'Not provided'}\n"
        "Visual evidence: No images were analyzed; this does not mean the "
        "source listing lacks images."
    )


def _post_and_validate(
    endpoint: str,
    headers: dict[str, str],
    payload: dict,
    extract_raw_json: Callable[[dict], str],
    provider_label: str,
    model_name: str,
) -> tuple[AIAnalysisResult, str]:
    """Shared two-attempt retry-then-AnalysisFailure control flow (D-10).

    OpenAICompatibleProvider and GeminiProvider POST a different-shaped
    request and pull the embedded JSON text out of a different-shaped
    response (`extract_raw_json`), but the retry/validate/fail contract
    itself was identical, duplicated almost verbatim between the two.
    Factored here so a future change to that contract (a third attempt,
    a different backoff, ...) only needs to be made once (PR #46 review,
    maintainability nit).
    """
    for attempt in range(2):
        try:
            response = httpx.post(endpoint, headers=headers, json=payload, timeout=30.0)
            response.raise_for_status()

            raw_json = extract_raw_json(response.json())
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
            http_status = (
                exc.response.status_code
                if isinstance(exc, httpx.HTTPStatusError)
                else None
            )
            logger.warning(
                "AI provider attempt failed provider=%s model=%s "
                "attempt=%d/2 error_type=%s http_status=%s",
                provider_label.lower(),
                model_name,
                attempt + 1,
                type(exc).__name__,
                http_status if http_status is not None else "none",
            )
            if attempt == 1:
                raise AnalysisFailure(
                    f"{provider_label} could not produce a valid analysis after two attempts"
                ) from exc
            # Let the loop naturally advance to the second (and final) retry.


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
            logger.error(
                "AI provider configuration invalid provider=%s missing_setting=%s_API_KEY",
                provider_label.lower(),
                provider_label.upper(),
            )
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
        return _post_and_validate(
            self.ENDPOINT,
            headers,
            payload,
            lambda body: body["choices"][0]["message"]["content"],
            self._provider_label,
            self.model_name,
        )


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
    AIAnalysisResult, one retry, then AnalysisFailure) is identical, and
    analyze() shares that retry/validate/fail control flow with
    OpenAICompatibleProvider via _post_and_validate.
    """

    def __init__(self) -> None:
        if not settings.gemini_api_key:
            logger.error(
                "AI provider configuration invalid provider=gemini "
                "missing_setting=GEMINI_API_KEY"
            )
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
        return _post_and_validate(
            self._endpoint,
            headers,
            payload,
            lambda body: body["candidates"][0]["content"]["parts"][0]["text"],
            "Gemini",
            self.model_name,
        )


def get_provider() -> AIProvider:
    if settings.ai_provider == "groq":
        return GroqProvider()
    if settings.ai_provider == "gpt":
        return GPTProvider()
    if settings.ai_provider == "gemini":
        return GeminiProvider()
    if settings.ai_provider not in KNOWN_PROVIDERS:
        # An unrecognized AI_PROVIDER value (typo, stale config) used to fall
        # through to MockProvider with no signal at all -- confusing when
        # you've set a real key and can't tell why analyses still look
        # heuristic. Log it; still fail open to mock rather than crash the
        # request path over a config typo.
        logger.warning(
            "Unknown AI_PROVIDER=%r; falling back to MockProvider. Expected one of %s.",
            settings.ai_provider,
            sorted(KNOWN_PROVIDERS),
        )
    return MockProvider()
