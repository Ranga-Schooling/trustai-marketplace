"""Rule-based risk scoring — the deterministic half of Card #27.

Card #27: "As a buyer, I see a 0-100 risk score combining rule-based and
AI signals." D-05 (docs/DESIGN_NOTES.md) forbids an LLM-invented numeric
score, deliberately: an LLM asked for a number directly isn't calibrated
(a re-run can drift 20 points with no substantive change). This module is
the "rule-based" half of the card's own wording: it takes the AI-produced
signals (risk_level, risk_indicators -- both already validated,
categorical/structured per AIAnalysisResult) and combines them into a
score with a fixed, documented, unit-tested formula. Same inputs always
produce the same score. No AIProvider ever returns a score; this is
computed server-side, after the provider call, only for AnalysisOut.

See docs/DESIGN_NOTES.md D-09 for the full rationale.
"""
from app.schemas.schemas import RiskIndicatorOut, RiskLevel

# Each tier owns a disjoint slice of 0-100, so a "high" analysis always
# outscores every "medium", which always outscores every "low" -- the
# score can never contradict the categorical risk_level it's derived from.
TIER_RANGES: dict[RiskLevel, tuple[int, int]] = {
    RiskLevel.low: (0, 33),
    RiskLevel.medium: (34, 66),
    RiskLevel.high: (67, 100),
}

# How much each indicator severity contributes toward "maxing out" a tier.
SEVERITY_WEIGHT: dict[RiskLevel, int] = {
    RiskLevel.low: 1,
    RiskLevel.medium: 2,
    RiskLevel.high: 3,
}

# Weighted-signal total at which a tier is considered fully saturated
# (score lands at the top of its range). Calibrated against MockProvider's
# own signal table: a bare-minimum "high" (one high-severity indicator,
# weight 3) should score well above the tier floor but not automatically
# cap at 100 -- only a listing with several/severe indicators should.
MAX_WEIGHTED_SIGNAL = 8


def compute_risk_score(risk_level: RiskLevel, indicators: list[RiskIndicatorOut]) -> int:
    """Deterministic 0-100 score. Same (risk_level, indicators) in -> same
    score out, always -- this is a pure function, not a model call."""
    low, high = TIER_RANGES[risk_level]
    weighted_signal = sum(SEVERITY_WEIGHT[indicator.severity] for indicator in indicators)
    fraction = min(weighted_signal / MAX_WEIGHTED_SIGNAL, 1.0)
    return round(low + fraction * (high - low))
