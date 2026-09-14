"""Provider-free tests for the frozen resource-limit contract boundary."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from app.services.evaluation_contract_identity import load_strict_normalization_spec
from app.services.evaluation_resource_limits import (
    COUNTING_CONVENTIONS,
    ENFORCEMENT_STATUS,
    RESOURCE_LIMIT_NAMES,
    RESOURCE_LIMIT_PRECEDENCE,
    RESOURCE_LIMIT_VALUES,
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

EXPECTED_LIMITS = {
    "maximum_raw_response_bytes": 2_097_152,
    "maximum_extracted_semantic_bytes": 1_048_576,
    "maximum_json_nesting_depth": 32,
    "maximum_object_members": 64,
    "maximum_total_object_members": 16_384,
    "maximum_array_elements": 1_024,
    "maximum_total_array_elements": 4_096,
    "maximum_single_string_bytes": 131_072,
    "maximum_total_string_bytes": 524_288,
    "maximum_canonical_payload_bytes": 2_097_152,
    "maximum_numeric_lexeme_length": 16_384,
    "maximum_numeric_significand_or_coefficient_digits": 8_192,
    "maximum_absolute_decimal_exponent_magnitude": 32_768,
}


def _policy():
    return load_strict_normalization_spec(SPEC_PATH)["resource_limit_policy"]


def test_resource_limit_inventory_and_values_match_the_governance_freeze():
    policy = _policy()

    assert RESOURCE_LIMIT_NAMES == tuple(EXPECTED_LIMITS)
    assert dict(RESOURCE_LIMIT_VALUES) == EXPECTED_LIMITS
    assert tuple(policy["required_limits"]) == RESOURCE_LIMIT_NAMES
    assert policy["required_limits"] == EXPECTED_LIMITS


def test_frozen_policy_is_ready_without_authorizing_provider_execution():
    assessment = assess_resource_limit_policy(_policy())

    assert assessment.policy_id == "normalization_parser_resource_limits_v1"
    assert assessment.status == "frozen"
    assert assessment.ready is True
    assert assessment.provider_calls_blocked is False
    assert assessment.failure_terminal == "failed_resource_limit"
    assert assessment.missing_limits == ()
    assert tuple(item.name for item in assessment.requirements) == RESOURCE_LIMIT_NAMES
    assert tuple(item.value for item in assessment.requirements) == tuple(
        EXPECTED_LIMITS.values()
    )
    assert all(item.frozen is True for item in assessment.requirements)
    assert require_resource_limits_ready(assessment) is None


def test_counting_conventions_and_precedence_are_exact():
    policy = _policy()

    assert policy["counting_conventions"] == COUNTING_CONVENTIONS
    assert policy["deterministic_limit_precedence"] == RESOURCE_LIMIT_PRECEDENCE
    assert policy["enforcement_status"] == ENFORCEMENT_STATUS
    assert policy["counting_conventions"]["limits_are_inclusive"] is True
    assert policy["counting_conventions"]["json_nesting_depth"] == {
        "root_object_or_array_depth": 1,
        "scalar_root_depth": 0,
    }


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("policy_id", "other", "resource_limit_policy_id"),
        ("status", "pending_numeric_freeze", "unsupported_resource_limit_status"),
        ("provider_calls_blocked_while_pending", False, "pending_provider_call_boundary"),
        ("provider_calls_blocked_while_pending", 1, "pending_provider_call_boundary"),
        ("numeric_limit_thresholds_frozen_here", False, "frozen_threshold_authority"),
        ("numeric_limit_thresholds_frozen_here", 1, "frozen_threshold_authority"),
        ("numeric_limit_failure_terminal", "internal_harness_error", "resource_limit_terminal"),
        ("limit_exceeded_result", "accepted", "resource_limit_terminal"),
        ("counting_conventions", {}, "resource_limit_counting_conventions"),
        ("deterministic_limit_precedence", [], "resource_limit_precedence"),
        ("enforcement_status", {}, "resource_limit_enforcement_status"),
    ),
)
def test_resource_limit_policy_identity_and_readiness_are_exact(field, value, error):
    policy = _policy()
    policy[field] = copy.deepcopy(value)

    with pytest.raises(ResourceLimitPolicyError, match=error):
        assess_resource_limit_policy(policy)


@pytest.mark.parametrize("limit_name", tuple(EXPECTED_LIMITS))
@pytest.mark.parametrize("mutation", (-1, 1, None, True, 1.0, "1"))
def test_every_frozen_limit_rejects_wrong_value_or_type(limit_name, mutation):
    policy = _policy()
    expected = EXPECTED_LIMITS[limit_name]
    policy["required_limits"][limit_name] = (
        expected + mutation
        if isinstance(mutation, int) and not isinstance(mutation, bool)
        else mutation
    )

    with pytest.raises(ResourceLimitPolicyError, match=f"resource_limit_value:{limit_name}"):
        assess_resource_limit_policy(policy)


def test_limit_inventory_rejects_missing_or_extra_members():
    policy = _policy()
    policy["required_limits"].pop(RESOURCE_LIMIT_NAMES[-1])
    with pytest.raises(ResourceLimitPolicyError, match="resource_limit_inventory"):
        assess_resource_limit_policy(policy)

    policy = _policy()
    policy["required_limits"]["invented_limit"] = 1
    with pytest.raises(ResourceLimitPolicyError, match="resource_limit_inventory"):
        assess_resource_limit_policy(policy)



def test_object_member_order_is_nonsemantic_but_reporting_order_is_frozen():
    policy = _policy()
    policy = {key: policy[key] for key in reversed(tuple(policy))}
    policy["required_limits"] = {
        key: policy["required_limits"][key] for key in reversed(RESOURCE_LIMIT_NAMES)
    }
    policy["counting_conventions"] = {
        key: policy["counting_conventions"][key]
        for key in reversed(tuple(policy["counting_conventions"]))
    }

    assessment = assess_resource_limit_policy(policy)

    assert tuple(item.name for item in assessment.requirements) == RESOURCE_LIMIT_NAMES


@pytest.mark.parametrize("value", (None, [], (), "frozen", 0, False))
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

    policy["required_limits"][RESOURCE_LIMIT_NAMES[0]] = 1
    policy["status"] = "changed"

    assert assessment == original
    assert isinstance(assessment.requirements, tuple)
    assert isinstance(assessment.missing_limits, tuple)


def test_unknown_fields_cannot_create_provider_execution_authority():
    policy = _policy()
    policy["provider_calls_allowed"] = True
    with pytest.raises(ResourceLimitPolicyError, match="resource_limit_policy_inventory"):
        assess_resource_limit_policy(policy)
