"""Typed integration tests for non-final post-schema validation."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import app.services.evaluation_schema_validation as schema_validation
from app.services.evaluation_schema_validation import (
    CanonicalOutputSchemaRegistry,
    SchemaContractError,
    SchemaValidatedCandidate,
)
from app.services.evaluation_post_schema_validation import (
    validate_text_post_schema_candidate,
    validate_visual_post_schema_candidate,
)
from app.services.evaluation_validators import DeterministicValidationError
from app.services.normalization_parser import AdmittedJsonNumber, normalize_semantic_json


ARTIFACT_PATH = (
    Path(__file__).parents[2]
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "output-schemas.v1.json"
)
MODULE_PATH = (
    Path(__file__).parents[1]
    / "app"
    / "services"
    / "evaluation_post_schema_validation.py"
)


def _registry():
    return CanonicalOutputSchemaRegistry.from_path(ARTIFACT_PATH)


def _candidate(schema_id, value):
    semantic = normalize_semantic_json(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    )
    return _registry().validate(schema_id, semantic)


def _text(*severities, risk_level="low", recommendation="buy"):
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


def _visual(*photo_number_sets):
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


def _identity(candidate):
    canonical = candidate.canonical_semantic_json
    return (
        candidate.schema_id,
        canonical.canonical_bytes,
        canonical.strict_parsed_semantic_payload_hash,
    )


@pytest.mark.parametrize(
    "payload",
    (
        _text(),
        _text("medium", risk_level="medium", recommendation="caution"),
        _text("high", risk_level="high", recommendation="avoid"),
    ),
)
def test_text_wrapper_runs_only_the_frozen_post_schema_validator(payload):
    candidate = _candidate("text_output_schema_v1", payload)
    before = _identity(candidate)

    assert (
        validate_text_post_schema_candidate(candidate, schema_registry=_registry())
        is None
    )
    assert _identity(candidate) == before


@pytest.mark.parametrize(
    ("payload", "reason"),
    (
        (_text("medium"), "risk_level_indicator_mismatch"),
        (
            _text("low", recommendation="avoid"),
            "risk_recommendation_mismatch",
        ),
    ),
)
def test_text_wrapper_preserves_exact_validator_failure(payload, reason):
    candidate = _candidate("text_output_schema_v1", payload)
    before = _identity(candidate)

    with pytest.raises(DeterministicValidationError, match=reason) as caught:
        validate_text_post_schema_candidate(candidate, schema_registry=_registry())

    assert caught.value.validator_id == "text_cross_field_validator_v1"
    assert caught.value.terminal_outcome == "failed_cross_field_validation"
    assert caught.value.reason == reason
    assert _identity(candidate) == before


@pytest.mark.parametrize(
    ("payload", "supplied_image_count"),
    (
        (_visual((1,)), 1),
        (_visual((1,), (1, 2)), 2),
        (_visual((1, 2, 3)), 3),
    ),
)
def test_visual_wrapper_validates_admitted_integer_references(
    payload,
    supplied_image_count,
):
    candidate = _candidate("visual_output_schema_v1", payload)
    before = _identity(candidate)
    photo_number = candidate.canonical_semantic_json.admitted.value["findings"][0][
        "photo_numbers"
    ][0]
    assert isinstance(photo_number, AdmittedJsonNumber)

    assert (
        validate_visual_post_schema_candidate(
            candidate,
            schema_registry=_registry(),
            supplied_image_count=supplied_image_count,
        )
        is None
    )
    assert _identity(candidate) == before


def test_visual_wrapper_preserves_exact_validator_failure():
    candidate = _candidate("visual_output_schema_v1", _visual((1, 3)))
    before = _identity(candidate)

    with pytest.raises(
        DeterministicValidationError,
        match="photo_number_exceeds_supplied_count",
    ) as caught:
        validate_visual_post_schema_candidate(
            candidate,
            schema_registry=_registry(),
            supplied_image_count=2,
        )

    assert caught.value.validator_id == "visual_photo_reference_validator_v1"
    assert caught.value.terminal_outcome == "failed_cross_field_validation"
    assert caught.value.reason == "photo_number_exceeds_supplied_count"
    assert _identity(candidate) == before


@pytest.mark.parametrize("count", (None, True, 0, 4, 1.0))
def test_visual_wrapper_rejects_invalid_harness_photo_count(count):
    candidate = _candidate("visual_output_schema_v1", _visual((1,)))

    with pytest.raises(
        ValueError,
        match="supplied_image_count must be an integer from 1 to 3",
    ):
        validate_visual_post_schema_candidate(
            candidate,
            schema_registry=_registry(),
            supplied_image_count=count,
        )


def test_wrappers_reject_untyped_and_cross_schema_candidates_before_field_access():
    text = _candidate("text_output_schema_v1", _text())
    visual = _candidate("visual_output_schema_v1", _visual((1,)))

    with pytest.raises(TypeError, match="SchemaValidatedCandidate"):
        validate_text_post_schema_candidate(
            _text(),
            schema_registry=_registry(),
        )
    for invocation in (
        lambda: validate_text_post_schema_candidate(
            visual,
            schema_registry=_registry(),
        ),
        lambda: validate_visual_post_schema_candidate(
            text,
            schema_registry=_registry(),
            supplied_image_count=1,
        ),
    ):
        with pytest.raises(
            SchemaContractError,
            match="post_schema_candidate_binding",
        ) as caught:
            invocation()
        assert caught.value.terminal_outcome == "internal_harness_error"


def test_wrapper_rejects_fabricated_schema_candidate_subclass():
    legitimate = _candidate("text_output_schema_v1", _text())

    class FabricatedSchemaCandidate(SchemaValidatedCandidate):
        schema_id = "text_output_schema_v1"
        canonical_semantic_json = legitimate.canonical_semantic_json

        def __init__(self):
            pass

    with pytest.raises(TypeError, match="SchemaValidatedCandidate"):
        validate_text_post_schema_candidate(
            FabricatedSchemaCandidate(),
            schema_registry=_registry(),
        )


def test_wrapper_revalidates_exact_type_candidate_before_cross_field_checks():
    legitimate = _candidate("text_output_schema_v1", _text())
    invalid = normalize_semantic_json(
        b'{"recommendation":"buy","risk_indicators":[],"risk_level":"low"}'
    )
    fabricated = SchemaValidatedCandidate(
        schema_id="text_output_schema_v1",
        schema_sha256=legitimate.schema_sha256,
        schema_set_sha256=legitimate.schema_set_sha256,
        canonical_semantic_json=invalid,
        _validation_token=schema_validation._SCHEMA_VALIDATION_TOKEN,
    )

    with pytest.raises(
        SchemaContractError,
        match="post_schema_candidate_validation",
    ) as caught:
        validate_text_post_schema_candidate(
            fabricated,
            schema_registry=_registry(),
        )
    assert caught.value.terminal_outcome == "internal_harness_error"


def test_wrapper_rejects_fabricated_schema_identity_even_for_valid_payload():
    canonical = normalize_semantic_json(
        json.dumps(_text(), separators=(",", ":")).encode()
    )
    fabricated = SchemaValidatedCandidate(
        schema_id="text_output_schema_v1",
        schema_sha256="0" * 64,
        schema_set_sha256="0" * 64,
        canonical_semantic_json=canonical,
        _validation_token=schema_validation._SCHEMA_VALIDATION_TOKEN,
    )

    with pytest.raises(
        SchemaContractError,
        match="post_schema_candidate_binding",
    ):
        validate_text_post_schema_candidate(
            fabricated,
            schema_registry=_registry(),
        )


def test_wrapper_rejects_tampered_admitted_snapshot():
    candidate = _candidate("text_output_schema_v1", _text())
    object.__setattr__(candidate, "_admitted_value", _text("medium"))

    with pytest.raises(
        SchemaContractError,
        match="canonical_semantic_json_identity",
    ):
        validate_text_post_schema_candidate(
            candidate,
            schema_registry=_registry(),
        )


def test_detached_payload_mutation_cannot_change_later_validation():
    candidate = _candidate("text_output_schema_v1", _text())
    detached = candidate.canonical_semantic_json.admitted.value
    detached["risk_level"] = "high"

    assert (
        validate_text_post_schema_candidate(candidate, schema_registry=_registry())
        is None
    )
    assert candidate.canonical_semantic_json.admitted.value["risk_level"] == "low"


def test_wrapper_module_cannot_promote_results_or_reach_other_phases():
    tree = ast.parse(MODULE_PATH.read_text())
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    public_functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }

    assert public_functions == {
        "validate_text_post_schema_candidate",
        "validate_visual_post_schema_candidate",
    }
    assert imports <= {
        "Any",
        "CanonicalOutputSchemaRegistry",
        "CanonicalSchemaValidationError",
        "SchemaContractError",
        "SchemaValidatedCandidate",
        "annotations",
        "validate_text_cross_fields",
        "validate_visual_photo_references",
    }
    source = MODULE_PATH.read_text()
    for forbidden in (
        "accepted",
        "attempt_state",
        "evidence_policy",
        "execution_gate",
        "provider",
        "result_record",
        "retrieval",
        "search",
    ):
        assert forbidden not in source.lower()
