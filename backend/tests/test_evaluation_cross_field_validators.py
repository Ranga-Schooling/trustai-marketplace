"""Tests for frozen deterministic post-schema evaluation validators."""

from __future__ import annotations

import copy

import pytest

from app.services.evaluation_validators import (
    DeterministicValidationError,
    validate_retrieval_status_coherence,
    validate_search_cross_references,
    validate_text_cross_fields,
    validate_visual_photo_references,
)


def _text_payload(*severities, risk_level="low", recommendation="buy"):
    return {
        "summary": "Synthetic assessment.",
        "risk_level": risk_level,
        "risk_indicators": [
            {
                "category": f"indicator_{index}",
                "severity": severity,
                "explanation": "Synthetic explanation.",
            }
            for index, severity in enumerate(severities, start=1)
        ],
        "price_assessment": "Synthetic price assessment.",
        "price_plausibility": "plausible",
        "seller_questions": ["Synthetic question?"],
        "recommendation": recommendation,
    }


@pytest.mark.parametrize(
    "payload",
    (
        _text_payload(),
        _text_payload("low", "low"),
        _text_payload("low", "medium", risk_level="medium", recommendation="caution"),
        _text_payload("medium", "high", risk_level="high", recommendation="avoid"),
    ),
)
def test_text_cross_field_validator_accepts_exact_risk_and_recommendation(payload):
    original = copy.deepcopy(payload)

    assert validate_text_cross_fields(payload) is None
    assert payload == original


@pytest.mark.parametrize(
    ("payload", "reason"),
    (
        (_text_payload("medium"), "risk_level_indicator_mismatch"),
        (
            _text_payload("high", risk_level="medium", recommendation="caution"),
            "risk_level_indicator_mismatch",
        ),
        (
            _text_payload("low", risk_level="low", recommendation="avoid"),
            "risk_recommendation_mismatch",
        ),
    ),
)
def test_text_cross_field_validator_rejects_without_repair(payload, reason):
    original = copy.deepcopy(payload)

    with pytest.raises(DeterministicValidationError, match=reason) as caught:
        validate_text_cross_fields(payload)

    assert caught.value.validator_id == "text_cross_field_validator_v1"
    assert caught.value.terminal_outcome == "failed_cross_field_validation"
    assert payload == original


def _visual_payload(*photo_number_sets):
    return {
        "findings": [
            {
                "category": "visible_detail",
                "observation": "Synthetic visible detail.",
                "photo_numbers": list(numbers),
            }
            for numbers in photo_number_sets
        ]
    }


@pytest.mark.parametrize(
    ("payload", "count"),
    (
        (_visual_payload((1,)), 1),
        (_visual_payload((1,), (1, 2), (3,)), 3),
        (_visual_payload((2,)), 2),
    ),
)
def test_visual_photo_reference_validator_accepts_supplied_photos(payload, count):
    original = copy.deepcopy(payload)

    assert validate_visual_photo_references(payload, count) is None
    assert payload == original


@pytest.mark.parametrize(
    ("payload", "count"),
    (
        (_visual_payload((2,)), 1),
        (_visual_payload((1, 3)), 2),
        (_visual_payload((3,), (1,)), 2),
    ),
)
def test_visual_photo_reference_validator_rejects_out_of_range(payload, count):
    original = copy.deepcopy(payload)

    with pytest.raises(
        DeterministicValidationError,
        match="photo_number_exceeds_supplied_count",
    ) as caught:
        validate_visual_photo_references(payload, count)

    assert caught.value.validator_id == "visual_photo_reference_validator_v1"
    assert caught.value.terminal_outcome == "failed_cross_field_validation"
    assert payload == original


@pytest.mark.parametrize("count", (0, -1, 1.0, True, 4))
def test_visual_validator_rejects_invalid_harness_photo_count(count):
    with pytest.raises(ValueError, match="supplied_image_count"):
        validate_visual_photo_references(_visual_payload((1,)), count)


def _retrieval_bundle():
    return {
        "retrieval_status": "completed",
        "sources": [
            {
                "source_id": "src-1",
                "name": "Synthetic source",
                "url": "https://example.invalid/product",
                "source_type": "manufacturer",
                "retrieved_at": "2026-08-30T00:00:00.000Z",
                "evidence_items": [
                    {
                        "evidence_id": "ev-1",
                        "evidence_type": "identity",
                        "content": "Synthetic identity evidence.",
                    }
                ],
            },
            {
                "source_id": "src-2",
                "name": "Second synthetic source",
                "url": "https://example.invalid/product-2",
                "source_type": "authorized_retailer",
                "retrieved_at": "2026-08-30T00:00:01.000Z",
                "evidence_items": [
                    {
                        "evidence_id": "ev-2",
                        "evidence_type": "status",
                        "content": "Synthetic status evidence.",
                    }
                ],
            },
        ],
    }


def _source_projection(source):
    return {
        key: source[key]
        for key in ("source_id", "name", "url", "source_type", "retrieved_at")
    }


def _search_payload():
    bundle = _retrieval_bundle()
    return {
        "identity_resolution": {
            "status": "resolved",
            "current_status": "current",
            "resolved_product_identity": "Synthetic Product",
            "source_ids": ["src-1"],
        },
        "comparison_status": "established",
        "claims": [
            {
                "claim_id": "claim-1",
                "claim_type": "specification",
                "statement": "Synthetic supported claim.",
                "source_ids": ["src-1"],
            }
        ],
        "price_evidence": [],
        "sources": [_source_projection(bundle["sources"][0])],
        "uncertainties": [],
        "conflicts": [],
    }


def test_search_cross_reference_validator_accepts_unchanged_source_projection():
    payload = _search_payload()
    bundle = _retrieval_bundle()
    original_payload = copy.deepcopy(payload)
    original_bundle = copy.deepcopy(bundle)

    assert validate_search_cross_references(payload, bundle) is None
    assert payload == original_payload
    assert bundle == original_bundle


@pytest.mark.parametrize(
    ("mutator", "reason"),
    (
        (
            lambda payload: payload["claims"][0].update(source_ids=["missing"]),
            "unknown_source_reference",
        ),
        (
            lambda payload: payload["sources"][0].update(name="Rewritten name"),
            "source_projection_mismatch",
        ),
        (
            lambda payload: payload["claims"].append(
                {**payload["claims"][0], "statement": "Duplicate ID."}
            ),
            "duplicate_claim_id",
        ),
        (
            lambda payload: payload["price_evidence"].append(
                {
                    "price_evidence_id": "price-1",
                    "source_id": "missing",
                    "price_value": {"kind": "exact", "amount": 10},
                    "currency": "USD",
                    "price_type": "msrp_or_list",
                    "region": "US",
                    "condition": "new",
                    "availability": "in_stock",
                    "seller_type": "manufacturer",
                    "tax_inclusion": "unknown",
                    "import_status": "domestic",
                }
            ),
            "unknown_source_reference",
        ),
    ),
)
def test_search_cross_reference_validator_rejects_identity_and_reference_mutations(
    mutator, reason
):
    payload = _search_payload()
    mutator(payload)

    with pytest.raises(DeterministicValidationError, match=reason) as caught:
        validate_search_cross_references(payload, _retrieval_bundle())

    assert caught.value.validator_id == "search_cross_reference_validator_v1"
    assert caught.value.terminal_outcome == "failed_trace_validation"


def test_search_validator_rejects_inverted_price_range():
    payload = _search_payload()
    payload["price_evidence"] = [
        {
            "price_evidence_id": "price-1",
            "source_id": "src-1",
            "price_value": {"kind": "range", "minimum": 20, "maximum": 10},
            "currency": "USD",
            "price_type": "msrp_or_list",
            "region": "US",
            "condition": "new",
            "availability": "in_stock",
            "seller_type": "manufacturer",
            "tax_inclusion": "unknown",
            "import_status": "domestic",
        }
    ]

    with pytest.raises(DeterministicValidationError, match="inverted_price_range"):
        validate_search_cross_references(payload, _retrieval_bundle())


@pytest.mark.parametrize("identity_status", ("unresolved", "conflicting"))
def test_search_validator_forbids_resolved_fields_for_unresolved_identity(
    identity_status,
):
    payload = _search_payload()
    payload["identity_resolution"]["status"] = identity_status

    with pytest.raises(
        DeterministicValidationError,
        match="resolved_identity_field_forbidden",
    ):
        validate_search_cross_references(payload, _retrieval_bundle())


def test_conflicting_identity_and_status_require_matching_conflict_records():
    payload = _search_payload()
    identity = payload["identity_resolution"]
    identity["status"] = "conflicting"
    identity["current_status"] = "conflicting"
    identity.pop("resolved_product_identity")
    identity["source_ids"] = ["src-1", "src-2"]
    payload["sources"].append(_source_projection(_retrieval_bundle()["sources"][1]))
    payload["comparison_status"] = "partially_established"
    payload["uncertainties"] = [
        {
            "uncertainty_id": "uncertainty-1",
            "uncertainty_type": "unresolved_identity",
            "statement": "Synthetic uncertainty.",
            "source_ids": ["src-1", "src-2"],
        }
    ]

    with pytest.raises(DeterministicValidationError, match="identity_conflict_missing"):
        validate_search_cross_references(payload, _retrieval_bundle())

    payload["conflicts"] = [
        {
            "conflict_id": "conflict-1",
            "conflict_type": "identity",
            "statement": "Synthetic identity conflict.",
            "source_ids": ["src-1", "src-2"],
        }
    ]
    with pytest.raises(DeterministicValidationError, match="status_conflict_missing"):
        validate_search_cross_references(payload, _retrieval_bundle())


def test_not_established_requires_frozen_uncertainty_type():
    payload = _search_payload()
    payload["comparison_status"] = "not_established"
    payload["identity_resolution"] = {
        "status": "unresolved",
        "current_status": "not_established",
        "source_ids": [],
    }
    payload["claims"] = []
    payload["sources"] = []
    payload["uncertainties"] = [
        {
            "uncertainty_id": "uncertainty-1",
            "uncertainty_type": "availability_unknown",
            "statement": "Synthetic uncertainty.",
            "source_ids": [],
        }
    ]

    with pytest.raises(
        DeterministicValidationError,
        match="not_established_uncertainty_missing",
    ):
        validate_search_cross_references(payload, _retrieval_bundle())


@pytest.mark.parametrize(
    ("status", "support", "source_count"),
    (
        ("completed", ("sufficient",), 1),
        ("completed", ("sufficient", "sufficient"), 2),
        ("partial", ("sufficient", "insufficient"), 1),
        ("partial", ("conflicting", "sufficient"), 3),
        ("no_reliable_evidence", ("insufficient",), 0),
        ("no_reliable_evidence", ("conflicting", "insufficient"), 2),
    ),
)
def test_retrieval_status_coherence_accepts_exact_frozen_formula(
    status, support, source_count
):
    assert validate_retrieval_status_coherence(status, support, source_count) is None


@pytest.mark.parametrize(
    ("status", "support", "source_count"),
    (
        ("partial", ("sufficient", "sufficient"), 1),
        ("completed", ("sufficient", "insufficient"), 1),
        ("no_reliable_evidence", ("sufficient", "conflicting"), 2),
        ("partial", ("insufficient", "conflicting"), 2),
        ("completed", ("sufficient",), 0),
        ("partial", ("sufficient", "insufficient"), 0),
    ),
)
def test_retrieval_status_coherence_rejects_without_replacing_provider_status(
    status, support, source_count
):
    with pytest.raises(
        DeterministicValidationError,
        match="retrieval_status_mismatch",
    ) as caught:
        validate_retrieval_status_coherence(status, support, source_count)

    assert caught.value.validator_id == "retrieval_status_coherence_validator_v1"
    assert caught.value.terminal_outcome == "failed_retrieval_coherence"


@pytest.mark.parametrize(
    ("status", "support", "source_count"),
    (
        ("unknown", ("sufficient",), 1),
        ("completed", (), 1),
        ("completed", ("not_applicable",), 1),
        ("completed", ("provider_error",), 1),
        ("completed", ("sufficient",), True),
        ("completed", ("sufficient",), -1),
    ),
)
def test_retrieval_status_validator_rejects_invalid_prevalidated_inputs(
    status, support, source_count
):
    with pytest.raises(ValueError, match="retrieval_status_coherence input"):
        validate_retrieval_status_coherence(status, support, source_count)
