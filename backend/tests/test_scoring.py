"""Unit tests for the deterministic risk-scoring formula (D-09, Card #27).

Pure function, no HTTP, no DB -- same (risk_level, indicators) in must
always produce the same score out, and scores must never contradict the
tier they were derived from (a "medium" can never outscore a "high").
"""
import pytest

from app.schemas.schemas import RiskIndicatorOut, RiskLevel
from app.services.scoring import TIER_RANGES, compute_risk_score

LOW = RiskIndicatorOut(category="x", severity=RiskLevel.low, explanation="x")
MEDIUM = RiskIndicatorOut(category="x", severity=RiskLevel.medium, explanation="x")
HIGH = RiskIndicatorOut(category="x", severity=RiskLevel.high, explanation="x")


def test_no_indicators_scores_the_floor_of_its_tier():
    assert compute_risk_score(RiskLevel.low, []) == TIER_RANGES[RiskLevel.low][0]


def test_score_is_deterministic():
    indicators = [MEDIUM, HIGH]
    first = compute_risk_score(RiskLevel.high, indicators)
    second = compute_risk_score(RiskLevel.high, indicators)
    assert first == second


@pytest.mark.parametrize(
    "risk_level,indicators",
    [
        (RiskLevel.low, []),
        (RiskLevel.low, [LOW]),
        (RiskLevel.medium, [MEDIUM]),
        (RiskLevel.medium, [MEDIUM, MEDIUM]),
        (RiskLevel.high, [HIGH]),
        (RiskLevel.high, [HIGH, MEDIUM, MEDIUM, MEDIUM]),
    ],
)
def test_score_stays_within_its_tier_range(risk_level, indicators):
    low, high = TIER_RANGES[risk_level]
    score = compute_risk_score(risk_level, indicators)
    assert low <= score <= high


def test_tiers_never_overlap_regardless_of_indicator_count():
    # A "high" with the single weakest possible signal must still outscore
    # a "medium" saturated with the strongest possible signal.
    weakest_high = compute_risk_score(RiskLevel.high, [HIGH])
    saturated_medium = compute_risk_score(RiskLevel.medium, [HIGH] * 10)
    assert weakest_high > saturated_medium

    weakest_medium = compute_risk_score(RiskLevel.medium, [MEDIUM])
    saturated_low = compute_risk_score(RiskLevel.low, [LOW] * 10)
    assert weakest_medium > saturated_low


def test_more_severe_indicators_score_higher_within_the_same_tier():
    one_medium = compute_risk_score(RiskLevel.medium, [MEDIUM])
    two_medium = compute_risk_score(RiskLevel.medium, [MEDIUM, MEDIUM])
    assert two_medium > one_medium


def test_score_never_exceeds_100_with_many_indicators():
    assert compute_risk_score(RiskLevel.high, [HIGH] * 10) == 100
