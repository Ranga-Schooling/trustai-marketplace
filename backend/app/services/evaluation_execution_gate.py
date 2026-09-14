"""Pure fail-closed assessment of the frozen evaluation execution gate.

This module validates declared experiment state only.  It cannot authorize a
phase transition, mutate the experiment, access credentials, or call a
provider.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping


class ExecutionGateError(ValueError):
    """The declared execution gate is malformed or internally incoherent."""


_FROZEN_PHASE_STATES = {
    "pre_execution": {
        "provider_calls_allowed": False,
        "pilot_calls_allowed": False,
        "scored_calls_allowed": False,
    },
    "pilot_authorized": {
        "provider_calls_allowed": True,
        "pilot_calls_allowed": True,
        "scored_calls_allowed": False,
    },
    "scored_authorized": {
        "provider_calls_allowed": True,
        "pilot_calls_allowed": False,
        "scored_calls_allowed": True,
        "pilot_calls_note": (
            "Pilot calls remain false unless separately reauthorized under "
            "change control."
        ),
    },
}

_FROZEN_PREREQUISITE_CONTRACTS = {
    "universal_provider_call_prerequisites": (
        (
            "candidate_lifecycle_preflight_complete",
            "complete_and_current",
            "lifecycle_preflight.status",
        ),
        (
            "exact_candidate_endpoints_and_models_frozen",
            "frozen",
            "parameter_protocol.status",
        ),
        (
            "credential_use_explicitly_authorized",
            "approved",
            "execution_gate.credential_authorization_status",
        ),
        (
            "credential_handling_configured_outside_git_and_artifacts",
            "approved",
            "execution_gate.credential_governance."
            "source_and_handling_policy_status",
        ),
        (
            "credential_scope_and_least_privilege_decision_complete",
            "approved",
            "execution_gate.credential_governance."
            "least_privilege_project_or_account_scope_decision_status",
        ),
        (
            "official_pricing_freeze_complete",
            "frozen",
            "pricing_source_protocol.status",
        ),
        (
            "pilot_cost_ceiling_frozen",
            "frozen_non_null",
            "cost_controls.pilot_cost_ceiling_usd",
        ),
        (
            "provider_neutral_pilot_prompts_frozen",
            "frozen",
            "execution_gate.readiness_statuses.pilot_prompt_set",
        ),
        (
            "pilot_output_schemas_frozen",
            "frozen",
            "execution_gate.readiness_statuses.pilot_output_schema_set",
        ),
        (
            "pilot_harness_implementation_and_version_frozen",
            "frozen_non_null",
            "pending_versioned_artifacts.harness_version.value",
        ),
        (
            "normalization_parser_implementation_and_version_frozen",
            "frozen",
            "execution_gate.readiness_statuses."
            "normalization_parser_implementation_and_version",
        ),
        (
            "pilot_fixtures_frozen",
            "frozen_non_null",
            "pending_versioned_artifacts.pilot_fixture_set_version.value",
        ),
        (
            "pilot_request_configurations_frozen",
            "frozen",
            "execution_gate.readiness_statuses.pilot_request_configurations",
        ),
        (
            "pilot_timeout_and_retry_behavior_frozen",
            "frozen",
            "execution_gate.readiness_statuses.pilot_timeout_and_retry_policy",
        ),
        (
            "logging_and_result_record_mechanism_ready",
            "ready",
            "execution_gate.readiness_statuses."
            "logging_and_result_record_mechanism",
        ),
        (
            "pilot_privacy_and_data_handling_eligibility_reviewed",
            "approved",
            "execution_gate.readiness_statuses."
            "pilot_privacy_and_data_handling_review",
        ),
        (
            "no_unresolved_execution_blocking_prerequisite",
            "none",
            "execution_gate.readiness_statuses.universal_execution_blockers",
        ),
    ),
    "pilot_specific_prerequisites": (
        ("all_universal_provider_call_prerequisites_pass", "all_pass", None),
        (
            "dedicated_pilot_fixture_set_frozen",
            "frozen_non_null",
            "pending_versioned_artifacts.pilot_fixture_set_version.value",
        ),
        (
            "explicit_pilot_authorization_recorded",
            "approved",
            "execution_gate.pilot_authorization_status",
        ),
    ),
    "scored_call_prerequisites": (
        ("all_universal_provider_call_prerequisites_pass", "all_pass", None),
        (
            "successful_pilot_completed",
            "successful",
            "execution_gate.readiness_statuses.pilot_completion",
        ),
        (
            "pilot_findings_reviewed",
            "complete",
            "execution_gate.readiness_statuses.pilot_findings_review",
        ),
        (
            "no_unresolved_pilot_blocking_defect",
            "none",
            "execution_gate.readiness_statuses.pilot_blocking_defects",
        ),
        (
            "scored_provider_neutral_prompts_frozen",
            "frozen",
            "pending_versioned_artifacts.prompt_template_versions.status",
        ),
        (
            "scored_output_schemas_frozen",
            "frozen",
            "pending_versioned_artifacts.output_schema_versions.status",
        ),
        (
            "P1_through_P8_truth_sheets_frozen",
            "frozen_non_null",
            "pending_versioned_artifacts.truth_sheet_version.value",
        ),
        (
            "visual_assets_frozen",
            "frozen_non_null",
            "pending_versioned_artifacts.visual_asset_set_version.value",
        ),
        (
            "visual_truth_records_frozen",
            "frozen",
            "execution_gate.readiness_statuses.visual_truth_records",
        ),
        (
            "grading_anchor_set_frozen",
            "frozen_non_null",
            "pending_versioned_artifacts.grading_anchor_set_version.value",
        ),
        (
            "grader_calibration_completed",
            "complete",
            "execution_gate.readiness_statuses.grader_calibration",
        ),
        (
            "OA7_operational_anchors_frozen",
            "frozen_non_null",
            "pending_versioned_artifacts."
            "operational_maturity_anchor_set_version.value",
        ),
        (
            "OA8_latency_bands_frozen",
            "frozen_non_null",
            "pending_versioned_artifacts."
            "latency_normalization_bands_version.value",
        ),
        (
            "OA9_cost_bands_frozen",
            "frozen_non_null",
            "pending_versioned_artifacts.cost_normalization_bands_version.value",
        ),
        (
            "scored_cost_ceiling_frozen",
            "frozen_non_null",
            "cost_controls.scored_experiment_cost_ceiling_usd",
        ),
        (
            "execution_seed_frozen",
            "frozen_non_null",
            "execution_order_policy.execution_seed",
        ),
        (
            "randomized_interleaved_run_order_generated_and_frozen",
            True,
            "execution_order_policy.actual_order_generated",
        ),
        (
            "exact_scored_request_configurations_frozen",
            "frozen",
            "execution_gate.readiness_statuses."
            "exact_scored_request_configurations",
        ),
        (
            "all_candidate_lifecycle_checks_still_current",
            "complete_and_current",
            "lifecycle_preflight.status",
        ),
        (
            "common_preflight_successful",
            "successful",
            "execution_gate.readiness_statuses.common_preflight",
        ),
        (
            "explicit_scored_experiment_authorization_recorded",
            "approved",
            "execution_gate.scored_authorization_status",
        ),
    ),
}

_FROZEN_NON_NULL_VERSION_SOURCES = frozenset(
    {
        "pending_versioned_artifacts.harness_version.value",
        "pending_versioned_artifacts.pilot_fixture_set_version.value",
        "pending_versioned_artifacts.truth_sheet_version.value",
        "pending_versioned_artifacts.visual_asset_set_version.value",
        "pending_versioned_artifacts.grading_anchor_set_version.value",
        (
            "pending_versioned_artifacts."
            "operational_maturity_anchor_set_version.value"
        ),
        (
            "pending_versioned_artifacts."
            "latency_normalization_bands_version.value"
        ),
        (
            "pending_versioned_artifacts."
            "cost_normalization_bands_version.value"
        ),
    }
)
_FROZEN_NON_NULL_POSITIVE_COST_SOURCES = frozenset(
    {
        "cost_controls.pilot_cost_ceiling_usd",
        "cost_controls.scored_experiment_cost_ceiling_usd",
    }
)
_FROZEN_NON_NULL_NONNEGATIVE_INTEGER_SOURCES = frozenset(
    {"execution_order_policy.execution_seed"}
)


@dataclass(frozen=True)
class PrerequisiteBlocker:
    prerequisite_id: str
    required_state: str | bool
    actual_state: Any
    status_source: str | None


@dataclass(frozen=True)
class FrozenDiagnosticState:
    """Deeply immutable evidence for one malformed JSON-semantic value."""

    json_type: str
    value: tuple[Any, ...]


@dataclass(frozen=True)
class ExecutionGateAssessment:
    phase: str
    overall_status: str
    provider_calls_allowed: bool
    pilot_calls_allowed: bool
    scored_calls_allowed: bool
    provider_calls_completed: int
    scored_provider_calls_completed: int
    winner_selected: bool
    universal_blockers: tuple[PrerequisiteBlocker, ...]
    pilot_blockers: tuple[PrerequisiteBlocker, ...]
    scored_blockers: tuple[PrerequisiteBlocker, ...]


def _require_mapping(label: str, value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExecutionGateError(label)
    return value


def _require_bool(label: str, value: Any) -> bool:
    if type(value) is not bool:
        raise ExecutionGateError(label)
    return value


def _require_counter(label: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ExecutionGateError(label)
    return value


def _matches_exact_json(actual: Any, expected: Any) -> bool:
    if isinstance(expected, Mapping):
        return (
            isinstance(actual, Mapping)
            and set(actual) == set(expected)
            and all(
                _matches_exact_json(actual[key], expected[key])
                for key in expected
            )
        )
    if isinstance(expected, list):
        return (
            type(actual) is list
            and len(actual) == len(expected)
            and all(
                _matches_exact_json(actual_item, expected_item)
                for actual_item, expected_item in zip(actual, expected)
            )
        )
    return type(actual) is type(expected) and actual == expected


def _resolve_status_source(document: Mapping[str, Any], path: str) -> Any:
    if not isinstance(path, str) or not path or path.startswith("."):
        raise ExecutionGateError("status_source")
    current: Any = document
    for segment in path.split("."):
        if not segment or not isinstance(current, Mapping) or segment not in current:
            raise ExecutionGateError("status_source")
        current = current[segment]
    return current


def _matches_frozen_non_null_source(source: str | None, actual: Any) -> bool:
    if source in _FROZEN_NON_NULL_VERSION_SOURCES:
        return type(actual) is str and bool(actual.strip())
    if source in _FROZEN_NON_NULL_POSITIVE_COST_SOURCES:
        if type(actual) is int:
            return actual > 0
        return type(actual) is float and math.isfinite(actual) and actual > 0
    if source in _FROZEN_NON_NULL_NONNEGATIVE_INTEGER_SOURCES:
        return type(actual) is int and actual >= 0
    return False


def _snapshot_blocker_state(
    value: Any,
) -> Any:
    if type(value) in {type(None), bool, int, float, str}:
        return value
    if type(value) is list:
        return FrozenDiagnosticState(json_type="array", value=())
    if type(value) is dict:
        return FrozenDiagnosticState(json_type="object", value=())
    return FrozenDiagnosticState(
        json_type=f"unsupported:{type(value).__module__}.{type(value).__qualname__}",
        value=(),
    )


def _state_matches(
    required: str | bool,
    actual: Any,
    *,
    status_source: str | None,
) -> bool:
    if required == "frozen_non_null":
        return _matches_frozen_non_null_source(status_source, actual)
    if required == "all_pass":
        return actual is True
    if type(required) is bool:
        return type(actual) is bool and actual is required
    return (
        type(required) is str
        and type(actual) is str
        and actual == required
    )


def _evaluate_prerequisites(
    document: Mapping[str, Any],
    records: Any,
    *,
    contract_name: str,
    universal_passed: bool | None = None,
) -> tuple[PrerequisiteBlocker, ...]:
    if not isinstance(records, list):
        raise ExecutionGateError("prerequisite_inventory")
    identifiers = tuple(
        record.get("id") if isinstance(record, Mapping) else None
        for record in records
    )
    if (
        any(
            not isinstance(identifier, str) or not identifier
            for identifier in identifiers
        )
        or len(set(identifiers)) != len(identifiers)
    ):
        raise ExecutionGateError("prerequisite_inventory")
    declared_contract = tuple(
        (
            record.get("id"),
            record.get("required_state"),
            record.get("status_source"),
        )
        for record in records
    )
    if declared_contract != _FROZEN_PREREQUISITE_CONTRACTS[contract_name]:
        raise ExecutionGateError("prerequisite_contract")

    blockers = []
    for record in records:
        allowed_fields = {"id", "required_state", "status_source"}
        if set(record) - allowed_fields or "required_state" not in record:
            raise ExecutionGateError("prerequisite_shape")
        required = record["required_state"]
        if type(required) is not bool and not isinstance(required, str):
            raise ExecutionGateError("prerequisite_required_state")
        source = record.get("status_source")
        if required == "all_pass":
            if source is not None or universal_passed is None:
                raise ExecutionGateError("prerequisite_aggregate")
            actual = universal_passed
        else:
            if source is None:
                raise ExecutionGateError("status_source")
            actual = _resolve_status_source(document, source)
        if not _state_matches(required, actual, status_source=source):
            blockers.append(
                PrerequisiteBlocker(
                    prerequisite_id=record["id"],
                    required_state=required,
                    actual_state=_snapshot_blocker_state(actual),
                    status_source=source,
                )
            )
    return tuple(blockers)


def assess_execution_gate(
    experiment: Mapping[str, Any],
) -> ExecutionGateAssessment:
    """Validate and report one frozen experiment execution-gate declaration."""
    document = _require_mapping("experiment", experiment)
    gate = _require_mapping("execution_gate", document.get("execution_gate"))
    if gate.get("authoritative_for_all_provider_execution") is not True:
        raise ExecutionGateError("execution_gate_authority")

    phase = document.get("status")
    overall_status = gate.get("overall_status")
    if not isinstance(phase, str) or not isinstance(overall_status, str):
        raise ExecutionGateError("execution_phase")

    provider_allowed = _require_bool(
        "provider_calls_allowed",
        gate.get("provider_calls_allowed"),
    )
    pilot_allowed = _require_bool(
        "pilot_calls_allowed",
        gate.get("pilot_calls_allowed"),
    )
    scored_allowed = _require_bool(
        "scored_calls_allowed",
        gate.get("scored_calls_allowed"),
    )
    provider_completed = _require_counter(
        "provider_calls_completed",
        document.get("provider_calls_completed"),
    )
    scored_completed = _require_counter(
        "scored_provider_calls_completed",
        document.get("scored_provider_calls_completed"),
    )
    winner_selected = _require_bool(
        "winner_selected",
        document.get("winner_selected"),
    )

    phase_states = _require_mapping("phase_states", gate.get("phase_states"))
    if not _matches_exact_json(phase_states, _FROZEN_PHASE_STATES):
        raise ExecutionGateError("phase_contract")
    if phase not in phase_states:
        raise ExecutionGateError("execution_phase")
    declared_phase = _require_mapping("phase_state", phase_states[phase])
    expected_flags = (
        declared_phase.get("provider_calls_allowed"),
        declared_phase.get("pilot_calls_allowed"),
        declared_phase.get("scored_calls_allowed"),
    )
    if any(type(value) is not bool for value in expected_flags) or expected_flags != (
        provider_allowed,
        pilot_allowed,
        scored_allowed,
    ):
        raise ExecutionGateError("phase_flags")

    universal_blockers = _evaluate_prerequisites(
        document,
        gate.get("universal_provider_call_prerequisites"),
        contract_name="universal_provider_call_prerequisites",
    )
    pilot_blockers = _evaluate_prerequisites(
        document,
        gate.get("pilot_specific_prerequisites"),
        contract_name="pilot_specific_prerequisites",
        universal_passed=not universal_blockers,
    )
    scored_blockers = _evaluate_prerequisites(
        document,
        gate.get("scored_call_prerequisites"),
        contract_name="scored_call_prerequisites",
        universal_passed=not universal_blockers,
    )

    if pilot_allowed and (universal_blockers or pilot_blockers):
        raise ExecutionGateError("pilot_prerequisites")
    if scored_allowed and (universal_blockers or scored_blockers):
        raise ExecutionGateError("scored_prerequisites")
    if (pilot_allowed or scored_allowed) and not provider_allowed:
        raise ExecutionGateError("provider_authorization")

    if phase == "pre_execution":
        if overall_status != "blocked_pre_execution":
            raise ExecutionGateError("pre_execution_status")
        if provider_completed or scored_completed or winner_selected:
            raise ExecutionGateError("pre_execution_state")

    return ExecutionGateAssessment(
        phase=phase,
        overall_status=overall_status,
        provider_calls_allowed=provider_allowed,
        pilot_calls_allowed=pilot_allowed,
        scored_calls_allowed=scored_allowed,
        provider_calls_completed=provider_completed,
        scored_provider_calls_completed=scored_completed,
        winner_selected=winner_selected,
        universal_blockers=universal_blockers,
        pilot_blockers=pilot_blockers,
        scored_blockers=scored_blockers,
    )
