"""Fail-closed readiness checks for frozen evaluation resource limits.

This module does not define, infer, or enforce numeric thresholds.  It only
validates the currently frozen pending-policy shape and exposes an immutable
assessment that keeps provider execution blocked until a later, separately
reviewed contract freezes those thresholds.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


RESOURCE_LIMIT_NAMES = (
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


class ResourceLimitPolicyError(ValueError):
    """The frozen resource-limit policy is malformed or is not executable."""


@dataclass(frozen=True)
class ResourceLimitRequirement:
    """One immutable requirement from the frozen resource-limit inventory."""

    name: str
    value: None
    frozen: bool


@dataclass(frozen=True)
class ResourceLimitAssessment:
    """Immutable fail-closed assessment of the pending resource-limit policy."""

    policy_id: str
    status: str
    ready: bool
    provider_calls_blocked: bool
    failure_terminal: str
    requirements: tuple[ResourceLimitRequirement, ...]
    missing_limits: tuple[str, ...]


def _require_exact_field(
    policy: Mapping[str, Any],
    field: str,
    expected: Any,
    error: str,
) -> None:
    actual = policy.get(field)
    if type(actual) is not type(expected) or actual != expected:
        raise ResourceLimitPolicyError(error)


def assess_resource_limit_policy(
    policy: Mapping[str, Any],
) -> ResourceLimitAssessment:
    """Validate the frozen pending policy without inventing future semantics."""
    if not isinstance(policy, Mapping):
        raise ResourceLimitPolicyError("resource_limit_policy")

    _require_exact_field(
        policy,
        "policy_id",
        "normalization_parser_resource_limits_v1",
        "resource_limit_policy_id",
    )
    _require_exact_field(
        policy,
        "status",
        "pending_numeric_freeze",
        "unsupported_resource_limit_status",
    )
    _require_exact_field(
        policy,
        "provider_calls_blocked_while_pending",
        True,
        "pending_provider_call_boundary",
    )
    _require_exact_field(
        policy,
        "numeric_limit_thresholds_frozen_here",
        False,
        "pending_threshold_authority",
    )
    _require_exact_field(
        policy,
        "numeric_limit_failure_terminal",
        "failed_resource_limit",
        "resource_limit_terminal",
    )
    _require_exact_field(
        policy,
        "limit_exceeded_result",
        "failed_resource_limit",
        "resource_limit_terminal",
    )

    required_limits = policy.get("required_limits")
    if not isinstance(required_limits, Mapping):
        raise ResourceLimitPolicyError("resource_limit_inventory")
    if set(required_limits) != set(RESOURCE_LIMIT_NAMES):
        raise ResourceLimitPolicyError("resource_limit_inventory")
    if any(required_limits[name] is not None for name in RESOURCE_LIMIT_NAMES):
        raise ResourceLimitPolicyError("pending_limit_value")

    requirements = tuple(
        ResourceLimitRequirement(name=name, value=None, frozen=False)
        for name in RESOURCE_LIMIT_NAMES
    )
    return ResourceLimitAssessment(
        policy_id="normalization_parser_resource_limits_v1",
        status="pending_numeric_freeze",
        ready=False,
        provider_calls_blocked=True,
        failure_terminal="failed_resource_limit",
        requirements=requirements,
        missing_limits=RESOURCE_LIMIT_NAMES,
    )


def require_resource_limits_ready(
    assessment: ResourceLimitAssessment,
) -> None:
    """Refuse execution because no executable threshold contract exists yet."""
    if not isinstance(assessment, ResourceLimitAssessment):
        raise ResourceLimitPolicyError("resource_limit_assessment")
    raise ResourceLimitPolicyError("resource_limits_pending")
