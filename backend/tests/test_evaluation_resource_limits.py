"""Provider-free tests for the frozen resource-limit readiness boundary."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from app.services.evaluation_contract_identity import load_strict_normalization_spec
from app.services.evaluation_resource_limits import (
    RESOURCE_LIMIT_NAMES,
    ResourceLimitPolicyError,
    assess_resource_limit_policy,
    require_resource_limits_ready,
)


SPEC_PATH = (
    Path(__file__).parents[2]
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "normalization-parser.v1.json"
)

EXPECTED_LIMIT_NAMES = (
    "maximum_raw_response_bytes",
    "maximum_extracted_semantic_bytes",
    "maximum_json_nesting_depth",
    "maximum_object_members",
    "maximum_total_object_members",
    "maximum_array_elements",
    "maximum_total_array_elements",
    "maximum_single_string_bytes",
    "maximum_total_string_bytes",
    "maximum_canonical_payload_bytes",
    "maximum_numeric_lexeme_length",
    "maximum_numeric_significand_or_coefficient_digits",
    "maximum_absolute_decimal_exponent_magnitude",
)


def _policy():
    return load_strict_normalization_spec(SPEC_PATH)["resource_limit_policy"]


def test_resource_limit_inventory_matches_the_frozen_contract():
    policy = _policy()

    assert RESOURCE_LIMIT_NAMES == EXPECTED_LIMIT_NAMES
    assert tuple(policy["required_limits"]) == EXPECTED_LIMIT_NAMES


def test_current_pending_policy_is_deterministically_blocking():
    assessment = assess_resource_limit_policy(_policy())

    assert assessment.policy_id == "normalization_parser_resource_limits_v1"
    assert assessment.status == "pending_numeric_freeze"
    assert assessment.ready is False
    assert assessment.provider_calls_blocked is True
    assert assessment.failure_terminal == "failed_resource_limit"
    assert assessment.missing_limits == EXPECTED_LIMIT_NAMES
    assert tuple(item.name for item in assessment.requirements) == (
        EXPECTED_LIMIT_NAMES
    )
    assert all(item.value is None for item in assessment.requirements)
    assert all(item.frozen is False for item in assessment.requirements)


def test_pending_policy_cannot_be_promoted_to_ready_by_the_assessor():
    assessment = assess_resource_limit_policy(_policy())

    with pytest.raises(ResourceLimitPolicyError, match="resource_limits_pending"):
        require_resource_limits_ready(assessment)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("policy_id", "other", "resource_limit_policy_id"),
        ("status", "frozen", "unsupported_resource_limit_status"),
        (
            "provider_calls_blocked_while_pending",
            False,
            "pending_provider_call_boundary",
        ),
        (
            "provider_calls_blocked_while_pending",
            1,
            "pending_provider_call_boundary",
        ),
        (
            "numeric_limit_thresholds_frozen_here",
            True,
            "pending_threshold_authority",
        ),
        (
            "numeric_limit_thresholds_frozen_here",
            0,
            "pending_threshold_authority",
        ),
        (
            "numeric_limit_failure_terminal",
            "internal_harness_error",
            "resource_limit_terminal",
        ),
        (
            "limit_exceeded_result",
            "accepted",
            "resource_limit_terminal",
        ),
    ),
)
def test_resource_limit_policy_identity_and_pending_boundary_are_exact(
    field,
    value,
    error,
):
    policy = _policy()
    policy[field] = value

    with pytest.raises(ResourceLimitPolicyError, match=error):
        assess_resource_limit_policy(policy)


@pytest.mark.parametrize(
    "value",
    (
        False,
        True,
        0,
        1,
        0.0,
        1.0,
        "",
        "0",
        [],
        {},
        {"value": 1},
    ),
)
@pytest.mark.parametrize("limit_name", EXPECTED_LIMIT_NAMES)
def test_pending_limit_values_cannot_smuggle_thresholds(limit_name, value):
    policy = _policy()
    policy["required_limits"][limit_name] = copy.deepcopy(value)

    with pytest.raises(ResourceLimitPolicyError, match="pending_limit_value"):
        assess_resource_limit_policy(policy)


def test_limit_inventory_rejects_missing_or_extra_members():
    policy = _policy()
    policy["required_limits"].pop(EXPECTED_LIMIT_NAMES[-1])
    with pytest.raises(ResourceLimitPolicyError, match="resource_limit_inventory"):
        assess_resource_limit_policy(policy)

    policy = _policy()
    policy["required_limits"]["invented_limit"] = None
    with pytest.raises(ResourceLimitPolicyError, match="resource_limit_inventory"):
        assess_resource_limit_policy(policy)


def test_limit_object_member_order_is_nonsemantic_and_reporting_is_frozen():
    policy = _policy()
    policy["required_limits"] = {
        key: policy["required_limits"][key]
        for key in reversed(EXPECTED_LIMIT_NAMES)
    }

    assessment = assess_resource_limit_policy(policy)

    assert assessment.missing_limits == EXPECTED_LIMIT_NAMES


@pytest.mark.parametrize("value", (None, [], (), "pending", 0, False))
def test_policy_and_limit_inventory_require_exact_mapping_shapes(value):
    with pytest.raises(ResourceLimitPolicyError, match="resource_limit_policy"):
        assess_resource_limit_policy(value)

    policy = _policy()
    policy["required_limits"] = value
    with pytest.raises(ResourceLimitPolicyError, match="resource_limit_inventory"):
        assess_resource_limit_policy(policy)


def test_assessment_is_immutable_and_detached_from_caller_state():
    policy = _policy()
    assessment = assess_resource_limit_policy(policy)
    original = copy.deepcopy(assessment)

    policy["required_limits"][EXPECTED_LIMIT_NAMES[0]] = 1
    policy["status"] = "changed"

    assert assessment == original
    assert isinstance(assessment.requirements, tuple)
    assert isinstance(assessment.missing_limits, tuple)


def test_unknown_policy_fields_do_not_create_readiness_authority():
    policy = _policy()
    policy["ready"] = True
    policy["provider_calls_allowed"] = True

    assessment = assess_resource_limit_policy(policy)

    assert assessment.ready is False
    assert assessment.provider_calls_blocked is True
