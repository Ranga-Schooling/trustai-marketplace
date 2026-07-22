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
- GroqProvider: OpenAI-compatible chat completions, JSON mode
  (response_format={"type": "json_object"}), temperature ~0.2, 30s timeout,
  ONE retry on invalid output, then raise AnalysisFailure.
- MockProvider: deterministic keyword/price heuristics, no network — this is
  what tests and CI run against, and it doubles as the documented list of
  fraud signals the product targets (urgency language, off-platform payment,
  off-platform contact, suspiciously low price...).

TODO(E3): write the system prompt. It must instruct the model to reply with
ONLY a JSON object matching AIAnalysisResult, to keep risk_level consistent
with the listed indicators, to map risk to recommendation deterministically,
and to be honest about uncertainty (no scam-detection guarantees).
"""
from typing import Protocol

from app.core.config import get_settings
from app.schemas.schemas import AIAnalysisResult, ListingIn

settings = get_settings()

SYSTEM_PROMPT = """TODO(E3/US-3.1): write the analyst prompt per the notes above."""


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
        from app.schemas.schemas import Recommendation, RiskIndicatorOut, RiskLevel

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

        if listing.price < 50:
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
            if listing.price < 50
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


class GroqProvider:
    """Groq chat completions (OpenAI-compatible) with JSON mode."""

    ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self) -> None:
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        self.model_name = settings.groq_model

    def analyze(self, listing: ListingIn) -> tuple[AIAnalysisResult, str]:
        raise NotImplementedError(
            "E3/US-3.1: call the endpoint in JSON mode, validate with "
            "AIAnalysisResult.model_validate_json, retry once, then raise "
            "AnalysisFailure"
        )


def get_provider() -> AIProvider:
    if settings.ai_provider == "groq":
        return GroqProvider()
    return MockProvider()
