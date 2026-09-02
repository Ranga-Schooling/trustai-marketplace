"""Private Visual Inspection result and evidence-policy contract tests.

These tests deliberately target a module that does not exist yet.  The first
RED state establishes the request-scoped, advisory result boundary before any
provider, route, persistence, or frontend integration is introduced.
"""

import pytest
from pydantic import ValidationError

from app.services.visual_inspection import (
    VisualEvidencePolicyViolation,
    VisualInspectionResult,
    validate_visual_evidence_policy,
)


MAX_OBSERVATION_CHARS = 500
MAX_FINDINGS = 8


def _finding(
    observation: str,
    *,
    category: str = "visible_detail",
    photo_numbers: list[int] | None = None,
) -> dict:
    return {
        "category": category,
        "observation": observation,
        "photo_numbers": [1] if photo_numbers is None else photo_numbers,
    }


def _result(*findings: dict, **extra_fields) -> VisualInspectionResult:
    payload = {"findings": list(findings)}
    payload.update(extra_fields)
    return VisualInspectionResult.model_validate(payload)


def test_private_result_accepts_a_directly_visible_photo_indexed_finding():
    result = _result(
        _finding(
            "Photo 1 visibly shows a scratch on the upper-right corner.",
            category="visible_damage",
        )
    )

    assert result.findings[0].category == "visible_damage"
    assert result.findings[0].photo_numbers == [1]


def test_private_result_accepts_exactly_eight_findings():
    result = _result(
        *[
            _finding(f"Photo 1 visibly shows detail {number}.")
            for number in range(1, MAX_FINDINGS + 1)
        ]
    )

    assert len(result.findings) == MAX_FINDINGS


def test_private_result_rejects_nine_findings():
    with pytest.raises(ValidationError):
        _result(
            *[
                _finding(f"Photo 1 visibly shows detail {number}.")
                for number in range(1, MAX_FINDINGS + 2)
            ]
        )


def test_private_result_schema_caps_findings_at_eight():
    findings_schema = VisualInspectionResult.model_json_schema()["properties"][
        "findings"
    ]

    assert findings_schema["minItems"] == 1
    assert findings_schema["maxItems"] == MAX_FINDINGS


@pytest.mark.parametrize("photo_number", [0, 4])
def test_private_result_rejects_photo_numbers_outside_v1_bounds(photo_number):
    with pytest.raises(ValidationError):
        _result(_finding("A visible surface mark is present.", photo_numbers=[photo_number]))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("risk_score", 70),
        ("risk_level", "high"),
        ("recommendation", "avoid"),
        ("price_plausibility", "suspicious"),
    ],
)
def test_private_result_forbids_trust_decision_fields(field, value):
    with pytest.raises(ValidationError):
        _result(_finding("Photo 1 visibly shows a scratch."), **{field: value})


@pytest.mark.parametrize(
    "finding",
    [
        _finding("A visible detail is present.", category="unsupported_category"),
        _finding(""),
        _finding(" "),
        _finding("x" * (MAX_OBSERVATION_CHARS + 1)),
        _finding("A visible detail is present.", photo_numbers=[]),
    ],
)
def test_private_result_enforces_category_and_field_length_constraints(finding):
    with pytest.raises(ValidationError):
        _result(finding)


def test_policy_allows_visible_uncertainty_and_quality_limitations():
    result = _result(
        _finding(
            "Photo 1 is too blurred to establish the label text.",
            category="image_quality",
        ),
        _finding(
            "The accessory is not visible in the supplied photo.",
            category="visibility_limitation",
            photo_numbers=[2],
        ),
    )

    assert validate_visual_evidence_policy(result) is None


@pytest.mark.parametrize(
    ("observation", "category"),
    [
        (
            "Photo 1 does not establish whether the item is authentic.",
            "visibility_limitation",
        ),
        (
            "Authenticity cannot be determined from the supplied photo.",
            "visibility_limitation",
        ),
        (
            "The photo does not verify whether the item is genuine.",
            "visibility_limitation",
        ),
        (
            "Photo 1 does not establish whether the device is fully functional.",
            "visibility_limitation",
        ),
        (
            "Internal condition cannot be determined from the supplied photos.",
            "visibility_limitation",
        ),
        (
            "The photos do not verify whether the device works.",
            "visibility_limitation",
        ),
        (
            "The supplied photos do not establish ownership.",
            "visibility_limitation",
        ),
        (
            "Ownership cannot be verified from the image.",
            "visibility_limitation",
        ),
        (
            "The photos do not establish the current market price.",
            "visibility_limitation",
        ),
        (
            "Current market value cannot be determined from the supplied photos.",
            "visibility_limitation",
        ),
        (
            "Photo 1 contains the printed words 'current market price'.",
            "visible_text",
        ),
        (
            "The visible label includes the word 'genuine'.",
            "visible_text",
        ),
        (
            "The package visibly contains the text 'authentic product'.",
            "visible_text",
        ),
    ],
)
def test_policy_allows_limitations_uncertainty_and_visible_text(
    observation, category
):
    result = _result(_finding(observation, category=category))
    before = result.model_dump(mode="json")

    assert validate_visual_evidence_policy(result) is None
    assert result.model_dump(mode="json") == before


@pytest.mark.parametrize(
    "observation",
    [
        "The photo shows a serial-number label, but authenticity cannot be verified.",
        "Packaging is visible, but the photos do not establish ownership.",
        "The screen is visible, but this does not establish whether the device works.",
        "A printed price is visible, but current market value cannot be determined.",
    ],
)
def test_policy_allows_bounded_cross_context_limitations(observation):
    result = _result(_finding(observation, category="visibility_limitation"))
    before = result.model_dump(mode="json")

    assert validate_visual_evidence_policy(result) is None
    assert result.model_dump(mode="json") == before


@pytest.mark.parametrize(
    ("observation", "expected_code"),
    [
        (
            "Authenticity cannot be fully verified, but this appears to be a "
            "genuine product.",
            "authenticity_claim",
        ),
        (
            "The photos cannot establish ownership, but this item is owned by "
            "the seller.",
            "ownership_claim",
        ),
    ],
)
def test_policy_rejects_a_conclusion_despite_a_separate_limitation(
    observation, expected_code
):
    result = _result(_finding(observation))

    with pytest.raises(VisualEvidencePolicyViolation) as exc_info:
        validate_visual_evidence_policy(result)

    assert expected_code in exc_info.value.codes


def test_policy_rejects_a_conclusion_after_visible_text_attribution():
    result = _result(
        _finding(
            "The visible label says 'genuine', therefore the item is authentic.",
            category="visible_text",
        )
    )

    with pytest.raises(VisualEvidencePolicyViolation) as exc_info:
        validate_visual_evidence_policy(result)

    assert exc_info.value.codes == ("authenticity_claim",)


@pytest.mark.parametrize(
    "observation",
    [
        "The item is authentic.",
        "The product is genuine.",
        "This product is counterfeit.",
        "The item is fake.",
    ],
)
def test_policy_rejects_definitive_authenticity_claims(observation):
    result = _result(_finding(observation))

    with pytest.raises(VisualEvidencePolicyViolation) as exc_info:
        validate_visual_evidence_policy(result)

    assert "authenticity_claim" in exc_info.value.codes


@pytest.mark.parametrize(
    "observation",
    [
        "The item is owned by the seller.",
        "The item is stolen.",
        "The item was obtained through theft.",
    ],
)
def test_policy_rejects_ownership_and_stolen_property_claims(observation):
    result = _result(_finding(observation))

    with pytest.raises(VisualEvidencePolicyViolation) as exc_info:
        validate_visual_evidence_policy(result)

    assert "ownership_claim" in exc_info.value.codes


@pytest.mark.parametrize(
    "observation",
    [
        "The battery health is excellent.",
        "The internal components are original.",
        "The device works perfectly.",
        "The item is fully functional.",
    ],
)
def test_policy_rejects_unseen_internal_condition_claims(observation):
    result = _result(_finding(observation))

    with pytest.raises(VisualEvidencePolicyViolation) as exc_info:
        validate_visual_evidence_policy(result)

    assert "internal_condition_claim" in exc_info.value.codes


@pytest.mark.parametrize(
    "observation",
    [
        "The current market value is 900 USD.",
        "The live market price is 850 USD.",
    ],
)
def test_policy_rejects_current_market_price_claims(observation):
    result = _result(_finding(observation))

    with pytest.raises(VisualEvidencePolicyViolation) as exc_info:
        validate_visual_evidence_policy(result)

    assert "current_market_price_claim" in exc_info.value.codes


def test_policy_allows_neutral_visible_price_text():
    result = _result(
        _finding(
            "Photo 1 visibly shows a printed price label reading 399.",
            category="visible_text",
        )
    )

    assert validate_visual_evidence_policy(result) is None


def test_policy_violation_exposes_safe_codes_without_provider_prose():
    offending_prose = "The photographed item is definitely counterfeit."
    result = _result(_finding(offending_prose))

    with pytest.raises(VisualEvidencePolicyViolation) as exc_info:
        validate_visual_evidence_policy(result)

    assert exc_info.value.codes == ("authenticity_claim",)
    assert offending_prose not in str(exc_info.value)
    assert offending_prose not in repr(exc_info.value)
    assert all(offending_prose not in str(arg) for arg in exc_info.value.args)


def test_policy_validation_does_not_mutate_an_accepted_result():
    result = _result(
        _finding(
            "Photo 1 visibly shows light surface wear.",
            category="visible_condition",
        )
    )
    before = result.model_dump(mode="json")

    assert validate_visual_evidence_policy(result) is None

    assert result.model_dump(mode="json") == before
