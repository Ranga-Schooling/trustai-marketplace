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
        raise NotImplementedError(
            "E3/US-3.3: implement keyword/price heuristics returning a valid "
            "AIAnalysisResult (see fraud-signal list in the module docstring)"
        )


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
