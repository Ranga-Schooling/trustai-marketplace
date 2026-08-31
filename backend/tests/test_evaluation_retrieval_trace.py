"""Provider-free tests for frozen retrieval trace positions and identifiers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.evaluation_contract_identity import load_strict_normalization_spec
from app.services.evaluation_retrieval_trace import (
    TRACE_POSITION_FIELDS,
    RetrievalIdentifierLimitError,
    RetrievalTraceValidationError,
    evidence_observation_key,
    render_evidence_id,
    render_source_id,
    source_observation_key,
    validate_trace_ordinal_scope,
)


SPEC_PATH = (
    Path(__file__).parents[2]
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "normalization-parser.v1.json"
)
SPEC = load_strict_normalization_spec(SPEC_PATH)

EXPECTED_POSITION_FIELDS = (
    "retrieval_attempt_ordinal",
    "tool_call_ordinal",
    "result_ordinal",
    "evidence_observation_ordinal",
)


def test_trace_position_inventory_matches_the_frozen_contract():
    policy = SPEC["retrieval_trace_ordering_policy"]

    assert TRACE_POSITION_FIELDS == EXPECTED_POSITION_FIELDS
    assert tuple(policy["position_fields"]) == EXPECTED_POSITION_FIELDS
    assert tuple(policy["source_observation_key"]) == EXPECTED_POSITION_FIELDS[:3]
    assert tuple(policy["evidence_observation_key"]) == EXPECTED_POSITION_FIELDS
    assert policy["ordering"] == (
        "lexicographic ascending over the applicable canonical trace-position tuple"
    )


def test_failure_and_identifier_rules_match_the_frozen_contract():
    trace_policy = SPEC["retrieval_trace_ordering_policy"]
    source_policy = SPEC["source_id_policy"]
    evidence_policy = SPEC["evidence_id_policy"]

    assert trace_policy["common_validation"]["runtime_violation_result"] == (
        RetrievalTraceValidationError.outcome
    )
    assert source_policy["identifier_over_schema_max_length_result"] == (
        RetrievalIdentifierLimitError.outcome
    )
    assert evidence_policy["identifier_over_schema_max_length_result"] == (
        RetrievalIdentifierLimitError.outcome
    )
    assert source_policy["schema_contract"]["maxLength"] == 64
    assert source_policy["schema_contract"]["maximum_decimal_component_digits"] == 60
    assert evidence_policy["schema_contract"]["maxLength"] == 64
    assert evidence_policy["schema_contract"]["maximum_component_digit_sum"] == 60
    assert source_policy["operational_source_count_dependency"].startswith("pending ")
    assert evidence_policy["operational_source_and_evidence_limits"].startswith(
        "pending "
    )


def test_frozen_ordinal_vectors_keep_mapping_and_topology_checks_separate():
    vectors = SPEC["retrieval_trace_ordinal_invariant_test_vectors"]

    assert vectors["provider_calls_required"] is False
    assert vectors["expected_case_count"] == 9
    assert tuple(case["id"] for case in vectors["cases"]) == tuple(
        f"O{index}" for index in range(1, 10)
    )
    assert tuple(case["expected"] for case in vectors["cases"][:8]) == (
        "failed_trace_validation",
    ) * 8
    assert vectors["cases"][8]["expected"] == "topology_preflight_failure"


def test_failed_observations_consume_positions_without_receiving_ids():
    failed_observations = SPEC["retrieval_trace_ordering_policy"][
        "failed_observations"
    ]

    assert failed_observations == {
        "remain_in_retrieval_trace": True,
        "consume_actual_trace_position": True,
        "become_canonical_source": False,
        "receive_source_id": False,
        "become_canonical_evidence": False,
        "receive_evidence_id": False,
        "trace_positions_may_be_recycled_or_renumbered": False,
        "canonical_ids_remain_contiguous_over_successful_canonical_objects": True,
    }


@pytest.mark.parametrize("field", EXPECTED_POSITION_FIELDS)
def test_trace_scope_accepts_unique_contiguous_positive_integer_ordinals(field):
    ordinals = [3, 1, 2]

    assert validate_trace_ordinal_scope(field, ordinals) == (3, 1, 2)
    assert ordinals == [3, 1, 2]


@pytest.mark.parametrize("field", EXPECTED_POSITION_FIELDS)
def test_empty_trace_scope_is_vacuously_contiguous(field):
    assert validate_trace_ordinal_scope(field, []) == ()


@pytest.mark.parametrize("value", (0, -1, True, False, 1.0, "1", None))
def test_trace_scope_rejects_non_positive_or_non_integer_ordinals(value):
    with pytest.raises(
        RetrievalTraceValidationError,
        match="failed_trace_validation",
    ):
        validate_trace_ordinal_scope("result_ordinal", [value])


@pytest.mark.parametrize("ordinals", ([1, 1], [1, 3], [2], [1, 2, 4]))
def test_trace_scope_rejects_duplicate_or_gapped_ordinals(ordinals):
    with pytest.raises(
        RetrievalTraceValidationError,
        match="failed_trace_validation",
    ):
        validate_trace_ordinal_scope("result_ordinal", ordinals)


def test_trace_scope_rejects_unknown_field_or_non_sequence_shape():
    with pytest.raises(RetrievalTraceValidationError, match="failed_trace_validation"):
        validate_trace_ordinal_scope("provider_native_id", [1])
    with pytest.raises(RetrievalTraceValidationError, match="failed_trace_validation"):
        validate_trace_ordinal_scope("result_ordinal", None)


def test_source_observation_keys_are_frozen_lexicographic_tuples():
    keys = [
        source_observation_key(2, 1, 1),
        source_observation_key(1, 2, 1),
        source_observation_key(1, 1, 2),
        source_observation_key(1, 1, 1),
    ]

    assert sorted(keys) == [
        (1, 1, 1),
        (1, 1, 2),
        (1, 2, 1),
        (2, 1, 1),
    ]


def test_evidence_observation_keys_are_frozen_lexicographic_tuples():
    keys = [
        evidence_observation_key(1, 1, 1, 2),
        evidence_observation_key(1, 1, 2, 1),
        evidence_observation_key(1, 1, 1, 1),
    ]

    assert sorted(keys) == [
        (1, 1, 1, 1),
        (1, 1, 1, 2),
        (1, 1, 2, 1),
    ]


@pytest.mark.parametrize(
    ("ordinal", "expected"),
    ((1, "src-0001"), (9999, "src-9999"), (10000, "src-10000")),
)
def test_source_id_rendering_uses_minimum_width_four_without_truncation(
    ordinal,
    expected,
):
    assert render_source_id(ordinal) == expected


def test_source_id_enforces_frozen_64_character_representational_capacity():
    sixty_digit_ordinal = 10**59
    assert len(render_source_id(sixty_digit_ordinal)) == 64

    with pytest.raises(
        RetrievalIdentifierLimitError,
        match="failed_resource_limit",
    ):
        render_source_id(10**60)


@pytest.mark.parametrize(
    ("source_ordinal", "evidence_ordinal", "expected"),
    (
        (1, 1, "ev-0001-0001"),
        (10000, 1, "ev-10000-0001"),
        (10000, 10000, "ev-10000-10000"),
    ),
)
def test_evidence_id_rendering_uses_each_canonical_ordinal(
    source_ordinal,
    evidence_ordinal,
    expected,
):
    assert render_evidence_id(source_ordinal, evidence_ordinal) == expected


def test_evidence_id_enforces_frozen_combined_64_character_capacity():
    thirty_digit = 10**29
    assert len(render_evidence_id(thirty_digit, thirty_digit)) == 64

    with pytest.raises(
        RetrievalIdentifierLimitError,
        match="failed_resource_limit",
    ):
        render_evidence_id(10**30, thirty_digit)


@pytest.mark.parametrize("value", (0, -1, True, False, 1.0, "1", None))
def test_identifier_rendering_rejects_non_positive_or_non_integer_ordinals(value):
    with pytest.raises(
        RetrievalTraceValidationError,
        match="failed_trace_validation",
    ):
        render_source_id(value)
    with pytest.raises(
        RetrievalTraceValidationError,
        match="failed_trace_validation",
    ):
        render_evidence_id(1, value)


def test_representational_capacity_does_not_impose_an_operational_count_cap():
    assert render_source_id(10000) == "src-10000"
    assert render_evidence_id(10000, 10000) == "ev-10000-10000"
