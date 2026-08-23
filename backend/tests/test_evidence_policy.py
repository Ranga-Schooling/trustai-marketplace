import pytest

from app.schemas.schemas import (
    AIAnalysisResult,
    PricePlausibility,
    Recommendation,
    RiskIndicatorOut,
    RiskLevel,
)
from app.services.evidence_policy import (
    EvidencePolicyViolation,
    validate_evidence_policy,
)


def _result_with_prose(
    *,
    summary: str = "No obvious risk indicators were found.",
    risk_indicators: list[RiskIndicatorOut] | None = None,
    price_assessment: str = "Current pricing was not verified.",
) -> AIAnalysisResult:
    return AIAnalysisResult(
        summary=summary,
        risk_level=RiskLevel.low,
        risk_indicators=risk_indicators if risk_indicators is not None else [],
        price_assessment=price_assessment,
        price_plausibility=PricePlausibility.plausible,
        seller_questions=["Can I inspect the item before making payment?"],
        recommendation=Recommendation.buy,
    )


def test_captured_production_result_is_rejected():
    result = AIAnalysisResult(
        summary=(
            "The product name is unusual, and the supplied information raises "
            "several concerns."
        ),
        risk_level=RiskLevel.medium,
        risk_indicators=[
            RiskIndicatorOut(
                category="Product description accuracy",
                severity=RiskLevel.medium,
                explanation=(
                    "The model name is not recognized in the official Nintendo "
                    "lineup, which may indicate misrepresentation or a counterfeit."
                ),
            ),
            RiskIndicatorOut(
                category="Missing visual evidence",
                severity=RiskLevel.medium,
                explanation=(
                    "No images are provided in the supplied text, limiting the "
                    "ability to verify the item's condition and authenticity."
                ),
            ),
            RiskIndicatorOut(
                category="Platform risk",
                severity=RiskLevel.medium,
                explanation=(
                    "Facebook Marketplace is a platform where scams occur with "
                    "some frequency."
                ),
            ),
            RiskIndicatorOut(
                category="Payment method flexibility",
                severity=RiskLevel.medium,
                explanation=(
                    "Marketplace or in-person payment does not provide escrow or "
                    "buyer-protection mechanisms."
                ),
            ),
        ],
        price_assessment=(
            "The asking price is within the range commonly seen for a new or "
            "like-new console with accessories."
        ),
        price_plausibility=PricePlausibility.plausible,
        seller_questions=["Can I inspect the item before making payment?"],
        recommendation=Recommendation.caution,
    )

    with pytest.raises(EvidencePolicyViolation):
        validate_evidence_policy(result)


def test_compliant_uncertainty_language_is_allowed():
    result = AIAnalysisResult(
        summary=(
            "No obvious risk indicators were found, but this does not guarantee "
            "that the listing is safe."
        ),
        risk_level=RiskLevel.low,
        risk_indicators=[],
        price_assessment="Current pricing was not verified.",
        price_plausibility=PricePlausibility.plausible,
        seller_questions=["Can I inspect the item before making payment?"],
        recommendation=Recommendation.buy,
    )

    validate_evidence_policy(result)


def test_summary_surface_rejects_forbidden_evidence():
    result = _result_with_prose(
        summary=(
            "This model is not recognized in the official product lineup and "
            "may be counterfeit."
        )
    )

    with pytest.raises(EvidencePolicyViolation):
        validate_evidence_policy(result)


def test_indicator_explanation_surface_rejects_forbidden_evidence():
    result = _result_with_prose(
        risk_indicators=[
            RiskIndicatorOut(
                category="Listing detail",
                severity=RiskLevel.low,
                explanation="This marketplace is known for scams.",
            )
        ]
    )

    with pytest.raises(EvidencePolicyViolation):
        validate_evidence_policy(result)


def test_price_assessment_surface_rejects_forbidden_evidence():
    result = _result_with_prose(
        price_assessment="The asking price is within the current market range."
    )

    with pytest.raises(EvidencePolicyViolation):
        validate_evidence_policy(result)


@pytest.mark.parametrize(
    "summary",
    [
        (
            "This model is not recognized in the official product lineup and "
            "may be counterfeit."
        ),
        "The product is unrecognized and could be fake.",
        "This is an unknown model, which raises a fraud concern.",
        "The variant does not appear to exist and may be a scam.",
    ],
)
def test_product_nonrecognition_used_as_evidence_is_rejected(summary):
    with pytest.raises(EvidencePolicyViolation):
        validate_evidence_policy(_result_with_prose(summary=summary))


@pytest.mark.parametrize(
    "summary",
    [
        "Current product information was not independently verified.",
        "The model's release status is unknown.",
        "Product recognition was not used as evidence.",
        "The analysis does not verify whether this model is current.",
    ],
)
def test_product_uncertainty_without_adverse_inference_is_allowed(summary):
    validate_evidence_policy(_result_with_prose(summary=summary))


def test_product_uncertainty_with_unrelated_fraud_signal_is_allowed():
    result = _result_with_prose(
        summary=(
            "The product model release status is unknown. Separately, a "
            "gift-card request raises a fraud concern."
        )
    )

    validate_evidence_policy(result)


def test_image_disclosure_with_unrelated_risk_signal_is_allowed():
    result = _result_with_prose(
        summary=(
            "Images were not analyzed. Separately, urgent gift-card payment "
            "is a risk concern."
        )
    )

    validate_evidence_policy(result)


def test_platform_source_with_unrelated_scam_signal_is_allowed():
    result = _result_with_prose(
        summary=(
            "Source platform: Facebook Marketplace. Separately, gift-card "
            "requests are a common scam signal."
        )
    )

    validate_evidence_policy(result)


def test_negated_product_risk_conclusion_is_allowed():
    result = _result_with_prose(
        summary="The model is unknown, but this is not a fraud concern."
    )

    validate_evidence_policy(result)


@pytest.mark.parametrize(
    "summary",
    [
        "No images were analyzed, so authenticity cannot be verified.",
        (
            "Photos were not provided, limiting the ability to verify physical "
            "condition."
        ),
        (
            "No listing images are available, which raises a concern about "
            "authenticity."
        ),
    ],
)
def test_unavailable_images_used_as_adverse_evidence_are_rejected(summary):
    with pytest.raises(EvidencePolicyViolation):
        validate_evidence_policy(_result_with_prose(summary=summary))


@pytest.mark.parametrize(
    "summary",
    [
        "Images were not analyzed.",
        (
            "No visual evidence was inspected; this does not mean the listing "
            "lacks images."
        ),
        "Ask the seller for current photos.",
        "The analysis is text-only.",
    ],
)
def test_neutral_image_limitations_are_allowed(summary):
    validate_evidence_policy(_result_with_prose(summary=summary))


@pytest.mark.parametrize(
    "summary",
    [
        "This marketplace is known for scams.",
        "The platform has frequent fraud.",
        "Scams occur commonly on this marketplace.",
    ],
)
def test_generic_platform_reputation_used_as_risk_is_rejected(summary):
    with pytest.raises(EvidencePolicyViolation):
        validate_evidence_policy(_result_with_prose(summary=summary))


@pytest.mark.parametrize(
    "summary",
    [
        "Source: Facebook Marketplace.",
        "The listing was posted on a marketplace.",
        "Keep communication within the marketplace.",
        "Ask what buyer protections apply on the platform.",
    ],
)
def test_neutral_platform_references_are_allowed(summary):
    validate_evidence_policy(_result_with_prose(summary=summary))


@pytest.mark.parametrize(
    "summary",
    [
        "This payment method does not provide buyer protection.",
        "There is no escrow.",
        "The payment lacks buyer-protection mechanisms.",
        "Buyer protection is unavailable.",
    ],
)
def test_inferred_payment_protection_properties_are_rejected(summary):
    with pytest.raises(EvidencePolicyViolation):
        validate_evidence_policy(_result_with_prose(summary=summary))


@pytest.mark.parametrize(
    "summary",
    [
        "Ask what buyer protections apply.",
        "Confirm whether escrow is available.",
        "The listing does not specify buyer-protection terms.",
        "Buyer protection was not verified.",
    ],
)
def test_payment_protection_questions_and_uncertainty_are_allowed(summary):
    validate_evidence_policy(_result_with_prose(summary=summary))


@pytest.mark.parametrize(
    "price_assessment",
    [
        "The price is within the range commonly seen.",
        "This is a typical retail price.",
        "The item generally sells for around this amount.",
        "The asking price is within the current market range.",
        "Comparable products commonly cost this amount.",
    ],
)
def test_unsupported_current_market_comparisons_are_rejected(price_assessment):
    with pytest.raises(EvidencePolicyViolation):
        validate_evidence_policy(
            _result_with_prose(price_assessment=price_assessment)
        )


@pytest.mark.parametrize(
    "price_assessment",
    [
        "Current pricing was not verified.",
        "No current market comparison was performed.",
        "The listing states an asking price of $399.",
        "Price plausibility could not be independently verified.",
    ],
)
def test_price_uncertainty_without_market_comparison_is_allowed(price_assessment):
    validate_evidence_policy(_result_with_prose(price_assessment=price_assessment))
