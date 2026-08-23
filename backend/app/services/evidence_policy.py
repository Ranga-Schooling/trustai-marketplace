"""Deterministic checks for known unsupported AI evidence patterns."""

import re

from app.schemas.schemas import AIAnalysisResult


class EvidencePolicyViolation(ValueError):
    """Raised when generated analysis prose violates a known evidence rule."""

    def __init__(self, codes: tuple[str, ...]) -> None:
        self.codes = codes
        super().__init__(f"Evidence policy violation: {', '.join(codes)}")


_PRODUCT_NOT_RECOGNIZED_IN_LINEUP = re.compile(
    r"\b(?:product|model|variant)(?: name)?\b.{0,60}\bnot recognized\b"
    r".{0,80}\b(?:lineup|catalog|product|model|variant)\b"
    r"|\bnot recognized\b.{0,80}\b(?:lineup|catalog|product|model|variant)\b"
)
_UNKNOWN_PRODUCT = re.compile(
    r"\b(?:unknown|unrecognized)\b.{0,60}\b(?:product|model|variant)\b"
    r"|\b(?:product|model|variant)(?: name)?\b.{0,60}"
    r"\b(?:unknown|unrecognized)\b"
)
_PRODUCT_EXISTENCE_DOUBT = re.compile(
    r"\b(?:product|model|variant)\b.{0,60}"
    r"\b(?:does not|doesn't) appear to exist\b"
)
_PRODUCT_RISK_CONCLUSION = re.compile(
    r"\b(?:fake|counterfeit|nonexistent|does not exist|fraud(?:ulent)?|scam|"
    r"misrepresent(?:ation|ed)?|risky?|risk|concern)\b"
)
_NEGATED_PRODUCT_RISK_CONCLUSION = re.compile(
    r"\bnot\s+(?:an?\s+)?(?:fake|counterfeit|nonexistent|fraud(?:ulent)?|"
    r"scam|misrepresent(?:ation|ed)?|risky?|risk|concern)\b"
    r"(?:\s+concern\b)?"
)

_IMAGE_EVIDENCE_UNAVAILABLE = re.compile(
    r"\bno (?:listing )?(?:images?|photos?) (?:are |were )?"
    r"(?:supplied|provided|analyzed|available)\b"
    r"|\b(?:images?|photos?) (?:are |were )?not "
    r"(?:supplied|provided|analyzed|available)\b"
)
_IMAGE_RISK_CONCLUSION = re.compile(
    r"\b(?:cannot|can't|unable to|limits? the ability to|limiting the ability to|"
    r"prevents?)\b.{0,60}\bverif(?:y|ication)\b"
    r"|\b(?:authenticity|physical condition)\b"
    r"|\b(?:risky?|risk|concern)\b"
)

_PLATFORM_REFERENCE = re.compile(r"\b(?:marketplace|platform)\b")
_PLATFORM_RISK = re.compile(r"\b(?:scams?|fraud(?:ulent)?|risky?|risk)\b")
_PLATFORM_GENERALIZATION = re.compile(
    r"\b(?:occur(?:s|red)?|common(?:ly)?|frequen(?:t|cy|tly)|prevalent|known for)\b"
)

_EVIDENCE_CLAUSE_BOUNDARY = re.compile(
    r"(?:[.!?;]+|\bseparately\b)[,\s]*"
)

_INFERRED_PAYMENT_PROTECTION = (
    re.compile(
        r"\b(?:does not|doesn't|do not|don't) "
        r"(?:offer|provide|include|have)\b.{0,60}"
        r"\b(?:escrow|buyer[- ]protection)\b"
    ),
    re.compile(r"\bno (?:escrow|buyer[- ]protection)\b"),
    re.compile(r"\black(?:s|ing)?\b.{0,40}\b(?:escrow|buyer[- ]protection)\b"),
    re.compile(
        r"\b(?:escrow|buyer[- ]protection)\b.{0,40}"
        r"\b(?:not available|unavailable)\b"
    ),
)

_UNSUPPORTED_PRICE_COMPARISONS = (
    re.compile(r"\bwithin (?:the )?range commonly seen\b"),
    re.compile(r"\btypical (?:retail|market|current market) (?:price|range)\b"),
    re.compile(r"\bcurrent market range\b"),
    re.compile(r"\bgenerally sells for\b"),
    re.compile(r"\bcommonly costs?\b"),
)


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def _evidence_clauses(text: str) -> tuple[str, ...]:
    return tuple(
        clause
        for clause in _EVIDENCE_CLAUSE_BOUNDARY.split(text)
        if clause
    )


def _uses_product_nonrecognition(text: str) -> bool:
    return any(
        (
            _PRODUCT_NOT_RECOGNIZED_IN_LINEUP.search(clause)
            or _UNKNOWN_PRODUCT.search(clause)
            or _PRODUCT_EXISTENCE_DOUBT.search(clause)
        )
        and _PRODUCT_RISK_CONCLUSION.search(
            _NEGATED_PRODUCT_RISK_CONCLUSION.sub("", clause)
        )
        for clause in _evidence_clauses(text)
    )


def _uses_unavailable_images_as_risk(text: str) -> bool:
    return any(
        _IMAGE_EVIDENCE_UNAVAILABLE.search(clause)
        and _IMAGE_RISK_CONCLUSION.search(clause)
        for clause in _evidence_clauses(text)
    )


def _uses_generic_platform_reputation(text: str) -> bool:
    return any(
        _PLATFORM_REFERENCE.search(clause)
        and _PLATFORM_RISK.search(clause)
        and _PLATFORM_GENERALIZATION.search(clause)
        for clause in _evidence_clauses(text)
    )


def _infers_payment_protection(text: str) -> bool:
    return any(pattern.search(text) for pattern in _INFERRED_PAYMENT_PROTECTION)


def _uses_unsupported_price_comparison(text: str) -> bool:
    return any(pattern.search(text) for pattern in _UNSUPPORTED_PRICE_COMPARISONS)


_PUBLIC_PROSE_RULES = (
    ("product_nonrecognition", _uses_product_nonrecognition),
    ("unavailable_images_as_risk", _uses_unavailable_images_as_risk),
    ("generic_platform_reputation", _uses_generic_platform_reputation),
    ("inferred_payment_protection", _infers_payment_protection),
)


def validate_evidence_policy(result: AIAnalysisResult) -> None:
    """Reject a complete result when its public prose uses forbidden evidence."""

    public_prose = [
        _normalize(result.summary),
        *(_normalize(indicator.explanation) for indicator in result.risk_indicators),
        _normalize(result.price_assessment),
    ]
    violation_codes = [
        code
        for code, violates in _PUBLIC_PROSE_RULES
        if any(violates(text) for text in public_prose)
    ]

    if _uses_unsupported_price_comparison(_normalize(result.price_assessment)):
        violation_codes.append("unsupported_price_comparison")

    if violation_codes:
        raise EvidencePolicyViolation(tuple(violation_codes))
