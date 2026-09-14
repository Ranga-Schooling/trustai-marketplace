"""Provider-neutral state reduction for evaluation normalization attempts.

This module implements the closed P1 #6 state model frozen in
``normalization-parser.v1.json``.  It deliberately contains no provider,
network, persistence, retry, or execution behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Sequence


HIGHEST_COMPLETED_STAGES = (
    "none",
    "raw_transport_captured",
    "semantic_representation_extracted",
    "strict_semantic_payload_parsed",
    "canonical_candidate_constructed",
    "canonical_schema_validated",
    "deterministic_validators_passed",
    "accepted",
)

NORMALIZATION_DISPOSITIONS = ("not_required", "performed", "failed")

TERMINAL_OUTCOMES = (
    "accepted",
    "http_provider_error",
    "provider_connection_error",
    "provider_timeout",
    "provider_safety_block",
    "provider_native_refusal",
    "tool_error",
    "tool_timeout",
    "failed_transport_extraction",
    "failed_resource_limit",
    "failed_utf8_decode",
    "failed_duplicate_key",
    "failed_strict_parse",
    "failed_canonical_validation",
    "failed_cross_field_validation",
    "failed_evidence_trace_coherence",
    "failed_trace_validation",
    "failed_url_security_validation",
    "failed_retrieval_coherence",
    "failed_evidence_policy",
    "internal_harness_error",
)

FAILURE_CODES = TERMINAL_OUTCOMES[1:]
VALIDATOR_STATES = ("passed", "failed", "not_run", "not_applicable")
PRESEMANTIC_STATES = (
    "ordinary_semantic_path",
    "provider_connection_error",
    "provider_timeout",
    "provider_safety_block",
    "provider_native_refusal",
    "http_provider_error",
    "terminal_tool_error",
    "terminal_tool_timeout",
)
REFUSAL_STATES = ("none", "provider_native_refusal", "provider_safety_block")

NORMALIZATION_ACTIONS = (
    "unwrap_transport_envelope",
    "select_designated_semantic_content",
    "assemble_documented_semantic_chunks",
    "extract_native_structured_object",
    "decode_strict_utf8",
    "parse_strict_json_text",
    "map_provider_reference_to_retrieval_trace",
    "deduplicate_canonical_source_by_url_key",
    "generate_canonical_source_id",
    "generate_canonical_evidence_id",
    "attach_trace_url",
    "attach_trace_retrieved_at",
    "attach_classified_source_type",
    "map_provider_reference_to_canonical_source_id",
    "canonicalize_json_representation",
)

EVENT_TYPES = (
    "normalized_presemantic_state",
    "major_stage",
    "normalization_action",
    "validator",
    "tool_event",
    "resource_limit",
    "internal_invariant",
    "acceptance_finalization",
)
EVENT_RESULTS = (
    "completed",
    "failed",
    "observed_nonterminal",
    "aborted_by_earlier_terminal",
    "not_applicable",
)
WORKLOAD_BRANCHES = (
    "text_final",
    "search_retrieval",
    "search_synthesis_final",
    "visual_final",
)

KNOWN_VALIDATORS = (
    "canonical_schema_validation",
    "text_cross_field_validator_v1",
    "search_cross_reference_validator_v1",
    "visual_photo_reference_validator_v1",
    "url_security_validation",
    "retrieval_trace_reference_source_membership_validation",
    "source_classification_validation",
    "evidence_trace_coherence_validator_v1",
    "objective_support_validator_v1",
    "retrieval_status_coherence_validator_v1",
    "evidence_policy_validation",
    "attempt_state_coherence_validator_v1",
)

_VALIDATOR_APPLICABILITY = {
    "text_final": {
        "canonical_schema_validation": "applicable",
        "text_cross_field_validator_v1": "applicable",
        "search_cross_reference_validator_v1": "not_applicable",
        "visual_photo_reference_validator_v1": "not_applicable",
        "url_security_validation": "not_applicable",
        "retrieval_trace_reference_source_membership_validation": "not_applicable",
        "source_classification_validation": "not_applicable",
        "evidence_trace_coherence_validator_v1": "not_applicable",
        "objective_support_validator_v1": "not_applicable",
        "retrieval_status_coherence_validator_v1": "not_applicable",
        "evidence_policy_validation": "applicable",
        "attempt_state_coherence_validator_v1": "applicable",
    },
    "search_retrieval": {
        "canonical_schema_validation": "applicable",
        "text_cross_field_validator_v1": "not_applicable",
        "search_cross_reference_validator_v1": "not_applicable",
        "visual_photo_reference_validator_v1": "not_applicable",
        "url_security_validation": "applicable",
        "retrieval_trace_reference_source_membership_validation": "applicable",
        "source_classification_validation": "applicable",
        "evidence_trace_coherence_validator_v1": "applicable",
        "objective_support_validator_v1": "applicable",
        "retrieval_status_coherence_validator_v1": "applicable",
        "evidence_policy_validation": "not_applicable",
        "attempt_state_coherence_validator_v1": "applicable",
    },
    "search_synthesis_final": {
        "canonical_schema_validation": "applicable",
        "text_cross_field_validator_v1": "not_applicable",
        "search_cross_reference_validator_v1": "applicable",
        "visual_photo_reference_validator_v1": "not_applicable",
        "url_security_validation": "not_applicable",
        "retrieval_trace_reference_source_membership_validation": "not_applicable",
        "source_classification_validation": "not_applicable",
        "evidence_trace_coherence_validator_v1": "not_applicable",
        "objective_support_validator_v1": "not_applicable",
        "retrieval_status_coherence_validator_v1": "not_applicable",
        "evidence_policy_validation": "applicable",
        "attempt_state_coherence_validator_v1": "applicable",
    },
    "visual_final": {
        "canonical_schema_validation": "applicable",
        "text_cross_field_validator_v1": "not_applicable",
        "search_cross_reference_validator_v1": "not_applicable",
        "visual_photo_reference_validator_v1": "applicable",
        "url_security_validation": "not_applicable",
        "retrieval_trace_reference_source_membership_validation": "not_applicable",
        "source_classification_validation": "not_applicable",
        "evidence_trace_coherence_validator_v1": "not_applicable",
        "objective_support_validator_v1": "not_applicable",
        "retrieval_status_coherence_validator_v1": "not_applicable",
        "evidence_policy_validation": "applicable",
        "attempt_state_coherence_validator_v1": "applicable",
    },
}

_ORDERED_APPLICABLE_VALIDATORS = {
    "text_final": (
        "canonical_schema_validation",
        "text_cross_field_validator_v1",
        "evidence_policy_validation",
        "attempt_state_coherence_validator_v1",
    ),
    "search_retrieval": (
        "url_security_validation",
        "canonical_schema_validation",
        "retrieval_trace_reference_source_membership_validation",
        "source_classification_validation",
        "evidence_trace_coherence_validator_v1",
        "objective_support_validator_v1",
        "retrieval_status_coherence_validator_v1",
        "attempt_state_coherence_validator_v1",
    ),
    "search_synthesis_final": (
        "canonical_schema_validation",
        "search_cross_reference_validator_v1",
        "evidence_policy_validation",
        "attempt_state_coherence_validator_v1",
    ),
    "visual_final": (
        "canonical_schema_validation",
        "visual_photo_reference_validator_v1",
        "evidence_policy_validation",
        "attempt_state_coherence_validator_v1",
    ),
}

_ACTION_CLASSIFICATION = {
    action: (
        "observation_validation_only"
        if action in {"decode_strict_utf8", "parse_strict_json_text"}
        else "disposition_driving"
    )
    for action in NORMALIZATION_ACTIONS
}
_ACTION_RESULTS = ("completed", "failed", "aborted_by_earlier_terminal")

_PRESEMANTIC_TERMINAL = {
    "provider_connection_error": "provider_connection_error",
    "provider_timeout": "provider_timeout",
    "provider_safety_block": "provider_safety_block",
    "provider_native_refusal": "provider_native_refusal",
    "http_provider_error": "http_provider_error",
    "terminal_tool_error": "tool_error",
    "terminal_tool_timeout": "tool_timeout",
}

_TERMINAL_EVENT_MAPPING = {
    "transport_extraction_failed": "failed_transport_extraction",
    "resource_limit_failed": "failed_resource_limit",
    "strict_utf8_decode_failed": "failed_utf8_decode",
    "duplicate_key_detected_in_syntactically_valid_json": "failed_duplicate_key",
    "strict_json_syntax_failed": "failed_strict_parse",
    "canonical_schema_validation_failed": "failed_canonical_validation",
    "text_cross_field_validator_failed": "failed_cross_field_validation",
    "visual_photo_reference_validator_failed": "failed_cross_field_validation",
    "retrieval_trace_reference_source_membership_failed": "failed_trace_validation",
    "search_cross_reference_validator_failed": "failed_trace_validation",
    "source_classification_validation_failed": "failed_trace_validation",
    "url_security_validation_failed": "failed_url_security_validation",
    "evidence_trace_coherence_failed": "failed_evidence_trace_coherence",
    "retrieval_status_coherence_failed": "failed_retrieval_coherence",
    "evidence_policy_validation_failed": "failed_evidence_policy",
    "objective_support_state_invalid": "internal_harness_error",
    "attempt_state_coherence_failed": "internal_harness_error",
    "other_application_owned_invariant_failed": "internal_harness_error",
    "all_required_processing_and_finalization_completed": "accepted",
}

_TRIGGER_TO_VALIDATOR = {
    "canonical_schema_validation_failed": "canonical_schema_validation",
    "text_cross_field_validator_failed": "text_cross_field_validator_v1",
    "search_cross_reference_validator_failed": "search_cross_reference_validator_v1",
    "visual_photo_reference_validator_failed": "visual_photo_reference_validator_v1",
    "url_security_validation_failed": "url_security_validation",
    "retrieval_trace_reference_source_membership_failed": (
        "retrieval_trace_reference_source_membership_validation"
    ),
    "source_classification_validation_failed": "source_classification_validation",
    "evidence_trace_coherence_failed": "evidence_trace_coherence_validator_v1",
    "objective_support_state_invalid": "objective_support_validator_v1",
    "retrieval_status_coherence_failed": "retrieval_status_coherence_validator_v1",
    "evidence_policy_validation_failed": "evidence_policy_validation",
    "attempt_state_coherence_failed": "attempt_state_coherence_validator_v1",
}

_TERMINAL_EVENT_TYPES = {
    "transport_extraction_failed": "normalization_action",
    "resource_limit_failed": "resource_limit",
    "strict_utf8_decode_failed": "normalization_action",
    "duplicate_key_detected_in_syntactically_valid_json": "normalization_action",
    "strict_json_syntax_failed": "normalization_action",
    "canonical_schema_validation_failed": "validator",
    "text_cross_field_validator_failed": "validator",
    "visual_photo_reference_validator_failed": "validator",
    "retrieval_trace_reference_source_membership_failed": "validator",
    "search_cross_reference_validator_failed": "validator",
    "source_classification_validation_failed": "validator",
    "url_security_validation_failed": "validator",
    "evidence_trace_coherence_failed": "validator",
    "retrieval_status_coherence_failed": "validator",
    "evidence_policy_validation_failed": "validator",
    "objective_support_state_invalid": "internal_invariant",
    "attempt_state_coherence_failed": "internal_invariant",
    "other_application_owned_invariant_failed": "internal_invariant",
    "all_required_processing_and_finalization_completed": "acceptance_finalization",
}

_EVENT_IDS_BY_TYPE = {
    "normalized_presemantic_state": PRESEMANTIC_STATES,
    "major_stage": HIGHEST_COMPLETED_STAGES[1:],
    "normalization_action": NORMALIZATION_ACTIONS
    + tuple(
        event_id
        for event_id, event_type in _TERMINAL_EVENT_TYPES.items()
        if event_type == "normalization_action"
    ),
    "validator": KNOWN_VALIDATORS
    + tuple(
        event_id
        for event_id, event_type in _TERMINAL_EVENT_TYPES.items()
        if event_type == "validator"
    ),
    "tool_event": (),
    "resource_limit": tuple(
        event_id
        for event_id, event_type in _TERMINAL_EVENT_TYPES.items()
        if event_type == "resource_limit"
    ),
    "internal_invariant": tuple(
        event_id
        for event_id, event_type in _TERMINAL_EVENT_TYPES.items()
        if event_type == "internal_invariant"
    ),
    "acceptance_finalization": tuple(
        event_id
        for event_id, event_type in _TERMINAL_EVENT_TYPES.items()
        if event_type == "acceptance_finalization"
    ),
}

_POLICY_IDENTITY_REQUIRED_EVENT_TYPES = frozenset(EVENT_TYPES) - {"major_stage"}
_ADAPTER_IDENTITY_ALLOWED_EVENT_TYPES = frozenset(
    {"normalized_presemantic_state", "normalization_action"}
)

_STAGE_RULES = {
    "accepted": ("exact", "accepted"),
    "provider_connection_error": ("exact", "none"),
    "provider_timeout": ("maximum", "deterministic_validators_passed"),
    "http_provider_error": ("allowed", ("none", "raw_transport_captured")),
    "provider_safety_block": ("allowed", ("none", "raw_transport_captured")),
    "provider_native_refusal": ("allowed", ("none", "raw_transport_captured")),
    "tool_error": ("maximum", "deterministic_validators_passed"),
    "tool_timeout": ("maximum", "deterministic_validators_passed"),
    "failed_transport_extraction": ("maximum", "raw_transport_captured"),
    "failed_resource_limit": ("maximum", "deterministic_validators_passed"),
    "failed_utf8_decode": ("exact", "semantic_representation_extracted"),
    "failed_duplicate_key": ("exact", "semantic_representation_extracted"),
    "failed_strict_parse": ("exact", "semantic_representation_extracted"),
    "failed_canonical_validation": ("exact", "canonical_candidate_constructed"),
    "failed_cross_field_validation": ("exact", "canonical_schema_validated"),
    "failed_evidence_trace_coherence": ("exact", "canonical_schema_validated"),
    "failed_trace_validation": ("exact", "canonical_schema_validated"),
    "failed_url_security_validation": (
        "maximum",
        "semantic_representation_extracted",
    ),
    "failed_retrieval_coherence": ("exact", "canonical_schema_validated"),
    "failed_evidence_policy": ("exact", "canonical_schema_validated"),
    "internal_harness_error": ("maximum", "deterministic_validators_passed"),
}

_PRESEMANTIC_ALLOWED_BY_OUTCOME = {
    "accepted": ("ordinary_semantic_path",),
    "http_provider_error": ("http_provider_error",),
    "provider_connection_error": ("provider_connection_error",),
    "provider_timeout": ("provider_timeout",),
    "provider_safety_block": ("provider_safety_block",),
    "provider_native_refusal": ("provider_native_refusal",),
    "tool_error": ("terminal_tool_error",),
    "tool_timeout": ("terminal_tool_timeout",),
    **{outcome: ("ordinary_semantic_path",) for outcome in FAILURE_CODES[7:-1]},
    "internal_harness_error": PRESEMANTIC_STATES,
}

_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_V1_ID = re.compile(r"[a-z][a-z0-9_]*_v1\Z")


class AttemptStateError(ValueError):
    """Invalid input to the frozen attempt-state reducer."""


class AttemptStateCoherenceError(AttemptStateError):
    """A provisional attempt record violates the compatibility matrix."""


@dataclass(frozen=True)
class NormalizationActionSummary:
    disposition_driving_completed: int = 0
    disposition_driving_failed_terminally: int = 0
    disposition_driving_aborted: int = 0
    observation_validation_only_completed: int = 0

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if type(value) is not int or value < 0:
                raise AttemptStateError(f"invalid_action_summary:{name}")


@dataclass(frozen=True)
class NormalizationActionRecord:
    ordinal: int
    action: str
    policy_id: str
    policy_version: str
    policy_hash: str
    adapter_id_if_applicable: str | None
    adapter_version_if_applicable: str | None
    adapter_hash_if_applicable: str | None
    input_hash: str
    output_hash: str | None
    trace_references: tuple[str, ...]
    deterministic_parameters: tuple[tuple[str, str], ...]
    action_result: str

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or self.ordinal < 1:
            raise AttemptStateError("action_ordinal")
        _require_member("normalization_action", self.action, NORMALIZATION_ACTIONS)
        _require_member(
            "normalization_action_result",
            self.action_result,
            _ACTION_RESULTS,
        )
        if not self.policy_id or not self.policy_version:
            raise AttemptStateError("action_policy_identity")
        _validate_hash("policy_hash", self.policy_hash)
        _validate_hash("input_hash", self.input_hash)
        _validate_optional_hash("adapter_hash", self.adapter_hash_if_applicable)
        _validate_optional_hash("output_hash", self.output_hash)
        adapter_identity = (
            self.adapter_id_if_applicable,
            self.adapter_version_if_applicable,
            self.adapter_hash_if_applicable,
        )
        if any(value is not None for value in adapter_identity) and not all(
            value is not None for value in adapter_identity
        ):
            raise AttemptStateError("action_adapter_identity")
        if self.action_result == "completed" and self.output_hash is None:
            raise AttemptStateError("output_hash")
        if not isinstance(self.trace_references, tuple) or not all(
            isinstance(value, str) and value for value in self.trace_references
        ):
            raise AttemptStateError("action_trace_references")
        if not isinstance(self.deterministic_parameters, tuple) or not all(
            isinstance(item, tuple)
            and len(item) == 2
            and all(isinstance(value, str) for value in item)
            for item in self.deterministic_parameters
        ):
            raise AttemptStateError("action_deterministic_parameters")


@dataclass(frozen=True)
class PresemanticSignals:
    provider_connection_error: bool = False
    provider_timeout: bool = False
    provider_safety_block: bool = False
    provider_native_refusal: bool = False
    http_provider_error: bool = False
    terminal_tool_error: bool = False
    terminal_tool_timeout: bool = False

    def __post_init__(self) -> None:
        if any(type(value) is not bool for value in vars(self).values()):
            raise AttemptStateError("invalid_presemantic_signal")


@dataclass(frozen=True)
class StageEvent:
    event_ordinal: int
    event_type: str
    stage_or_event_id: str
    applicability: str
    result: str
    safe_input_hash_references_if_applicable: tuple[str, ...] = ()
    safe_output_hash_references_if_applicable: tuple[str, ...] = ()
    policy_identity_if_applicable: tuple[str, str, str] | None = None
    adapter_identity_if_applicable: tuple[str, str, str] | None = None

    def __post_init__(self) -> None:
        if type(self.event_ordinal) is not int or self.event_ordinal < 1:
            raise AttemptStateError("event_ordinal")
        _require_member("event_type", self.event_type, EVENT_TYPES)
        _require_member(
            "event_applicability",
            self.applicability,
            ("applicable", "not_applicable"),
        )
        _require_member("event_result", self.result, EVENT_RESULTS)
        if self.applicability == "not_applicable" and self.result != "not_applicable":
            raise AttemptStateError("event_applicability_result")
        if self.applicability == "applicable" and self.result == "not_applicable":
            raise AttemptStateError("event_applicability_result")
        _require_member(
            "stage_or_event_id",
            self.stage_or_event_id,
            _EVENT_IDS_BY_TYPE[self.event_type],
        )
        if self.stage_or_event_id in _TERMINAL_EVENT_MAPPING:
            expected_result = (
                "completed"
                if self.stage_or_event_id
                == "all_required_processing_and_finalization_completed"
                else "failed"
            )
            if self.result not in {expected_result, "aborted_by_earlier_terminal"}:
                raise AttemptStateError("terminal_event_result")
        elif self.event_type == "normalized_presemantic_state":
            expected_result = (
                "completed"
                if self.stage_or_event_id == "ordinary_semantic_path"
                else "failed"
            )
            if self.result not in {expected_result, "aborted_by_earlier_terminal"}:
                raise AttemptStateError("presemantic_event_result")
        elif self.result == "failed":
            raise AttemptStateError("terminal_event_id_required")

        _validate_event_identity(
            "event_policy_identity",
            self.policy_identity_if_applicable,
            required=self.event_type in _POLICY_IDENTITY_REQUIRED_EVENT_TYPES,
        )
        _validate_event_identity(
            "event_adapter_identity",
            self.adapter_identity_if_applicable,
            required=self.event_type == "normalized_presemantic_state",
        )
        if (
            self.adapter_identity_if_applicable is not None
            and self.event_type not in _ADAPTER_IDENTITY_ALLOWED_EVENT_TYPES
        ):
            raise AttemptStateError("unexpected_event_identity")
        if self.event_type == "major_stage" and (
            self.policy_identity_if_applicable is not None
            or self.adapter_identity_if_applicable is not None
        ):
            raise AttemptStateError("unexpected_event_identity")
        for field_name, references in (
            (
                "safe_input_hash_references_if_applicable",
                self.safe_input_hash_references_if_applicable,
            ),
            (
                "safe_output_hash_references_if_applicable",
                self.safe_output_hash_references_if_applicable,
            ),
        ):
            if not isinstance(references, tuple):
                raise AttemptStateError(f"invalid_{field_name}")
            for value in references:
                _validate_hash(field_name, value)


@dataclass(frozen=True)
class AttemptStageEventLedger:
    events: tuple[StageEvent, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.events, tuple):
            raise AttemptStateError("event_ledger_not_immutable")
        expected = tuple(range(1, len(self.events) + 1))
        actual = tuple(event.event_ordinal for event in self.events)
        if actual != expected:
            raise AttemptStateError("event_ordinal")


@dataclass(frozen=True)
class ValidatorStateRecord:
    validator_id: str
    applicability: str
    state: str

    def __post_init__(self) -> None:
        _require_member("validator_id", self.validator_id, KNOWN_VALIDATORS)
        _require_member(
            "validator_applicability",
            self.applicability,
            ("applicable", "not_applicable"),
        )
        _require_member("validator_state", self.state, VALIDATOR_STATES)


@dataclass(frozen=True)
class AttemptState:
    workload_branch: str
    normalized_presemantic_state: str
    ledger: AttemptStageEventLedger
    normalization_action_summary: NormalizationActionSummary
    validator_states: tuple[ValidatorStateRecord, ...]
    highest_completed_stage: str
    normalization_disposition: str
    terminal_outcome: str
    attempt_outcome: str
    refusal_state: str
    failure_category: str | None
    raw_provider_response_hash: str | None
    accepted_artifact_hash: str | None


@dataclass(frozen=True)
class AttemptRun:
    attempt_outcomes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.attempt_outcomes, tuple):
            raise AttemptStateError("attempt_records_not_immutable")
        for outcome in self.attempt_outcomes:
            _require_member("terminal_outcome", outcome, TERMINAL_OUTCOMES)

    def record(self, outcome: str, *, preflight_passed: bool = True) -> AttemptRun:
        if type(preflight_passed) is not bool:
            raise AttemptStateError("invalid_preflight_state")
        _require_member("terminal_outcome", outcome, TERMINAL_OUTCOMES)
        if not preflight_passed:
            return self
        return AttemptRun(self.attempt_outcomes + (outcome,))


def _require_member(label: str, value: str, allowed: Iterable[str]) -> None:
    if value not in allowed:
        raise AttemptStateError(f"unknown_{label}")


def _validate_hash(label: str, value: str) -> None:
    if not isinstance(value, str) or _LOWER_SHA256.fullmatch(value) is None:
        raise AttemptStateError(f"invalid_{label}")


def _validate_optional_hash(label: str, value: str | None) -> None:
    if value is not None:
        _validate_hash(label, value)


def _validate_event_identity(
    label: str,
    identity: tuple[str, str, str] | None,
    *,
    required: bool,
) -> None:
    if identity is None:
        if required:
            raise AttemptStateError(label)
        return
    if (
        not isinstance(identity, tuple)
        or len(identity) != 3
        or not isinstance(identity[0], str)
        or _V1_ID.fullmatch(identity[0]) is None
        or not isinstance(identity[1], str)
        or identity[1] != "v1"
    ):
        raise AttemptStateError(label)
    try:
        _validate_hash(label, identity[2])
    except AttemptStateError as exc:
        raise AttemptStateError(label) from exc


def derive_highest_completed_stage(completed_major_stages: Iterable[str]) -> str:
    stages = tuple(completed_major_stages)
    for stage in stages:
        _require_member("major_stage", stage, HIGHEST_COMPLETED_STAGES[1:])
    if len(set(stages)) != len(stages):
        raise AttemptStateError("duplicate_major_stage")
    if not stages:
        return "none"
    indexes = tuple(HIGHEST_COMPLETED_STAGES.index(stage) for stage in stages)
    if tuple(sorted(indexes)) != indexes:
        raise AttemptStateError("major_stage_order")
    if indexes != tuple(range(1, max(indexes) + 1)):
        raise AttemptStateError("major_stage_progression")
    return HIGHEST_COMPLETED_STAGES[max(indexes)]


def summarize_normalization_actions(
    records: Sequence[NormalizationActionRecord],
) -> NormalizationActionSummary:
    if not isinstance(records, tuple):
        raise AttemptStateError("normalization_action_log")
    expected = tuple(range(1, len(records) + 1))
    actual = tuple(record.ordinal for record in records)
    if actual != expected:
        raise AttemptStateError("action_ordinal")

    driving_completed = 0
    driving_failed = 0
    driving_aborted = 0
    observation_completed = 0
    terminal_seen = False
    for record in records:
        classification = _ACTION_CLASSIFICATION[record.action]
        if terminal_seen and record.action_result != "aborted_by_earlier_terminal":
            raise AttemptStateError("action_after_terminal")
        if classification == "disposition_driving":
            if record.action_result == "completed":
                driving_completed += 1
            elif record.action_result == "failed":
                driving_failed += 1
                terminal_seen = True
            else:
                driving_aborted += 1
        elif record.action_result == "completed":
            observation_completed += 1
        elif record.action_result == "failed":
            terminal_seen = True

    return NormalizationActionSummary(
        disposition_driving_completed=driving_completed,
        disposition_driving_failed_terminally=driving_failed,
        disposition_driving_aborted=driving_aborted,
        observation_validation_only_completed=observation_completed,
    )


def _derive_normalization_disposition_from_summary(
    summary: NormalizationActionSummary,
) -> str:
    if summary.disposition_driving_failed_terminally:
        return "failed"
    if summary.disposition_driving_completed:
        return "performed"
    return "not_required"


def derive_normalization_disposition(
    records: tuple[NormalizationActionRecord, ...],
) -> str:
    return _derive_normalization_disposition_from_summary(
        summarize_normalization_actions(records)
    )


def is_state_fragment_coherent(
    *,
    terminal_outcome: str,
    normalization_disposition: str | None = None,
    attempt_outcome: str | None = None,
) -> bool:
    if terminal_outcome not in TERMINAL_OUTCOMES:
        return False
    if normalization_disposition is not None:
        if normalization_disposition not in NORMALIZATION_DISPOSITIONS:
            return False
        if terminal_outcome == "accepted" and normalization_disposition == "failed":
            return False
        if (
            terminal_outcome == "failed_transport_extraction"
            and normalization_disposition != "failed"
        ):
            return False
    return attempt_outcome is None or attempt_outcome == terminal_outcome


def derive_validator_state(
    *,
    applicability: str,
    executed: bool,
    accepted: bool | None,
    blocked_by_earlier_terminal: bool = False,
) -> str:
    _require_member(
        "validator_applicability",
        applicability,
        ("applicable", "not_applicable"),
    )
    if type(executed) is not bool or type(blocked_by_earlier_terminal) is not bool:
        raise AttemptStateError("invalid_validator_execution")
    if accepted is not None and type(accepted) is not bool:
        raise AttemptStateError("invalid_validator_acceptance")
    if applicability == "not_applicable":
        if executed or accepted is not None or blocked_by_earlier_terminal:
            raise AttemptStateError("validator_execution_incoherent")
        return "not_applicable"
    if executed:
        if blocked_by_earlier_terminal or accepted is None:
            raise AttemptStateError("validator_execution_incoherent")
        return "passed" if accepted else "failed"
    if not blocked_by_earlier_terminal or accepted is not None:
        raise AttemptStateError("validator_execution_incoherent")
    return "not_run"


def is_validator_execution_coherent(
    *,
    applicability: str,
    executed: bool,
    accepted: bool | None,
    provided_state: str,
    blocked_by_earlier_terminal: bool = False,
) -> bool:
    try:
        return derive_validator_state(
            applicability=applicability,
            executed=executed,
            accepted=accepted,
            blocked_by_earlier_terminal=blocked_by_earlier_terminal,
        ) == provided_state
    except AttemptStateError:
        return False


def validator_applicability_for_branch(branch: str) -> dict[str, str]:
    _require_member("workload_branch", branch, WORKLOAD_BRANCHES)
    return dict(_VALIDATOR_APPLICABILITY[branch])


def ordered_applicable_validators(branch: str) -> tuple[str, ...]:
    _require_member("workload_branch", branch, WORKLOAD_BRANCHES)
    return _ORDERED_APPLICABLE_VALIDATORS[branch]


def is_validator_state_coherent(
    *, workload_branch: str, validator_id: str, provided_state: str
) -> bool:
    try:
        applicability = validator_applicability_for_branch(workload_branch)[
            validator_id
        ]
    except (AttemptStateError, KeyError):
        return False
    return (
        provided_state in VALIDATOR_STATES
        and (applicability == "applicable")
        == (provided_state != "not_applicable")
    )


def derive_normalized_presemantic_state(signals: PresemanticSignals) -> str:
    if signals.provider_connection_error and signals.provider_timeout:
        raise AttemptStateError("transport_state_conflict")
    if signals.terminal_tool_error and signals.terminal_tool_timeout:
        raise AttemptStateError("tool_state_conflict")
    if signals.provider_connection_error:
        return "provider_connection_error"
    if signals.provider_timeout:
        return "provider_timeout"
    if signals.provider_safety_block:
        return "provider_safety_block"
    if signals.provider_native_refusal:
        return "provider_native_refusal"
    if signals.http_provider_error:
        return "http_provider_error"
    if signals.terminal_tool_error:
        return "terminal_tool_error"
    if signals.terminal_tool_timeout:
        return "terminal_tool_timeout"
    return "ordinary_semantic_path"


def reduce_first_terminal_condition(
    normalized_presemantic_state: str,
    ledger: AttemptStageEventLedger,
) -> str:
    _require_member(
        "presemantic_state",
        normalized_presemantic_state,
        PRESEMANTIC_STATES,
    )
    terminal_outcome, _ = _derive_terminal_from_ledger(
        normalized_presemantic_state,
        ledger,
    )
    return terminal_outcome


def _derive_terminal_from_ledger(
    normalized_presemantic_state: str,
    ledger: AttemptStageEventLedger,
) -> tuple[str, int]:
    if normalized_presemantic_state != "ordinary_semantic_path":
        matching = tuple(
            index
            for index, event in enumerate(ledger.events)
            if event.event_type == "normalized_presemantic_state"
            and event.stage_or_event_id == normalized_presemantic_state
            and event.result == "failed"
        )
        if len(matching) != 1:
            raise AttemptStateCoherenceError("presemantic_terminal_event")
        presemantic_index = matching[0]
        for event in ledger.events[:presemantic_index]:
            if event.result == "failed" or (
                event.stage_or_event_id
                == "all_required_processing_and_finalization_completed"
                and event.result == "completed"
            ):
                raise AttemptStateCoherenceError(
                    "event_before_presemantic_terminal"
                )

        internal_index = None
        for index, event in enumerate(
            ledger.events[presemantic_index + 1 :],
            start=presemantic_index + 1,
        ):
            if (
                internal_index is None
                and event.event_type == "internal_invariant"
                and event.result == "failed"
            ):
                internal_index = index
            elif event.result != "aborted_by_earlier_terminal":
                raise AttemptStateCoherenceError(
                    "event_after_presemantic_terminal"
                )
        if internal_index is not None:
            return "internal_harness_error", internal_index
        return _PRESEMANTIC_TERMINAL[normalized_presemantic_state], presemantic_index

    for index, event in enumerate(ledger.events):
        if event.event_type == "normalized_presemantic_state" and (
            event.stage_or_event_id != "ordinary_semantic_path"
            or event.result != "completed"
        ):
            raise AttemptStateCoherenceError("presemantic_event_mismatch")
        if event.result == "failed":
            return _TERMINAL_EVENT_MAPPING[event.stage_or_event_id], index
        if (
            event.stage_or_event_id
            == "all_required_processing_and_finalization_completed"
            and event.result == "completed"
        ):
            return "accepted", index
    raise AttemptStateError("missing_terminal_condition")


def derive_refusal_state(
    terminal_outcome: str,
    normalized_presemantic_state: str,
) -> str:
    _require_member("terminal_outcome", terminal_outcome, TERMINAL_OUTCOMES)
    _require_member(
        "presemantic_state",
        normalized_presemantic_state,
        PRESEMANTIC_STATES,
    )
    if terminal_outcome == "provider_native_refusal":
        if normalized_presemantic_state != "provider_native_refusal":
            raise AttemptStateError("refusal_state_context")
        return "provider_native_refusal"
    if terminal_outcome == "provider_safety_block":
        if normalized_presemantic_state != "provider_safety_block":
            raise AttemptStateError("refusal_state_context")
        return "provider_safety_block"
    if terminal_outcome == "internal_harness_error":
        if normalized_presemantic_state == "provider_native_refusal":
            return "provider_native_refusal"
        if normalized_presemantic_state == "provider_safety_block":
            return "provider_safety_block"
    return "none"


def _derive_validator_records(
    branch: str,
    terminal_outcome: str,
    ledger: AttemptStageEventLedger,
) -> tuple[ValidatorStateRecord, ...]:
    applicability = _VALIDATOR_APPLICABILITY[branch]
    ordered = _ORDERED_APPLICABLE_VALIDATORS[branch]
    passed_validators = []
    failed_validator = None
    for event in ledger.events:
        if (
            event.event_type == "validator"
            and event.stage_or_event_id in KNOWN_VALIDATORS
            and event.result == "completed"
        ):
            passed_validators.append(event.stage_or_event_id)
        if event.result == "failed":
            failed_validator = _TRIGGER_TO_VALIDATOR.get(event.stage_or_event_id)
            break

    if len(set(passed_validators)) != len(passed_validators):
        raise AttemptStateCoherenceError("duplicate_validator_event")
    if tuple(passed_validators) != ordered[: len(passed_validators)]:
        raise AttemptStateCoherenceError("validator_event_order")

    states: dict[str, str] = {
        validator_id: "not_applicable"
        for validator_id in KNOWN_VALIDATORS
        if applicability[validator_id] == "not_applicable"
    }
    states.update({validator_id: "passed" for validator_id in passed_validators})
    if terminal_outcome == "accepted":
        states.update({validator_id: "passed" for validator_id in ordered})
    elif failed_validator is not None:
        if failed_validator not in ordered:
            raise AttemptStateCoherenceError("failed_validator_not_applicable")
        failed_index = ordered.index(failed_validator)
        for index, validator_id in enumerate(ordered):
            if index < failed_index:
                states[validator_id] = "passed"
            elif index == failed_index:
                states[validator_id] = "failed"
            else:
                states[validator_id] = "not_run"
    else:
        states.update(
            {
                validator_id: "not_run"
                for validator_id in ordered
                if validator_id not in passed_validators
            }
        )

    return tuple(
        ValidatorStateRecord(
            validator_id=validator_id,
            applicability=applicability[validator_id],
            state=states[validator_id],
        )
        for validator_id in KNOWN_VALIDATORS
    )


def derive_attempt_state(
    *,
    workload_branch: str,
    normalized_presemantic_state: str,
    ledger: AttemptStageEventLedger,
    normalization_actions: tuple[NormalizationActionRecord, ...],
    raw_provider_response_hash: str | None,
    accepted_artifact_hash: str | None,
) -> AttemptState:
    _require_member("workload_branch", workload_branch, WORKLOAD_BRANCHES)
    _require_member(
        "presemantic_state",
        normalized_presemantic_state,
        PRESEMANTIC_STATES,
    )
    summary = summarize_normalization_actions(normalization_actions)
    terminal_outcome = reduce_first_terminal_condition(
        normalized_presemantic_state,
        ledger,
    )
    completed_stages = tuple(
        event.stage_or_event_id
        for event in ledger.events
        if event.event_type == "major_stage" and event.result == "completed"
    )
    state = AttemptState(
        workload_branch=workload_branch,
        normalized_presemantic_state=normalized_presemantic_state,
        ledger=ledger,
        normalization_action_summary=summary,
        validator_states=_derive_validator_records(
            workload_branch,
            terminal_outcome,
            ledger,
        ),
        highest_completed_stage=derive_highest_completed_stage(completed_stages),
        normalization_disposition=(
            _derive_normalization_disposition_from_summary(summary)
        ),
        terminal_outcome=terminal_outcome,
        attempt_outcome=terminal_outcome,
        refusal_state=derive_refusal_state(
            terminal_outcome,
            normalized_presemantic_state,
        ),
        failure_category=(None if terminal_outcome == "accepted" else terminal_outcome),
        raw_provider_response_hash=raw_provider_response_hash,
        accepted_artifact_hash=accepted_artifact_hash,
    )
    validate_attempt_state(state)
    return state


def _validate_stage_rule(state: AttemptState) -> None:
    mode, rule_value = _STAGE_RULES[state.terminal_outcome]
    actual_index = HIGHEST_COMPLETED_STAGES.index(state.highest_completed_stage)
    if mode == "exact" and state.highest_completed_stage != rule_value:
        raise AttemptStateCoherenceError("highest_completed_stage")
    if mode == "allowed" and state.highest_completed_stage not in rule_value:
        raise AttemptStateCoherenceError("highest_completed_stage")
    if mode == "maximum":
        maximum_index = HIGHEST_COMPLETED_STAGES.index(rule_value)
        if actual_index > maximum_index:
            raise AttemptStateCoherenceError("highest_completed_stage")


def _validate_validator_inventory(state: AttemptState) -> None:
    if not isinstance(state.validator_states, tuple):
        raise AttemptStateCoherenceError("validator_inventory")
    identifiers = tuple(record.validator_id for record in state.validator_states)
    if identifiers != KNOWN_VALIDATORS:
        raise AttemptStateCoherenceError("validator_inventory")
    expected_applicability = _VALIDATOR_APPLICABILITY[state.workload_branch]
    for record in state.validator_states:
        if record.applicability != expected_applicability[record.validator_id]:
            raise AttemptStateCoherenceError("validator_applicability")
        if not is_validator_state_coherent(
            workload_branch=state.workload_branch,
            validator_id=record.validator_id,
            provided_state=record.state,
        ):
            raise AttemptStateCoherenceError("validator_applicability")

    expected = _derive_validator_records(
        state.workload_branch,
        state.terminal_outcome,
        state.ledger,
    )
    if state.validator_states != expected:
        raise AttemptStateCoherenceError("validator_states")


def _validate_hash_rules(state: AttemptState) -> None:
    _validate_optional_hash(
        "raw_provider_response_hash",
        state.raw_provider_response_hash,
    )
    _validate_optional_hash("accepted_artifact_hash", state.accepted_artifact_hash)
    if state.terminal_outcome == "accepted":
        if state.raw_provider_response_hash is None:
            raise AttemptStateCoherenceError("raw_provider_response_hash")
        if state.accepted_artifact_hash is None:
            raise AttemptStateCoherenceError("accepted_artifact_hash")
    elif state.accepted_artifact_hash is not None:
        raise AttemptStateCoherenceError("accepted_artifact_hash")
    if (
        state.terminal_outcome == "provider_connection_error"
        and state.raw_provider_response_hash is not None
    ):
        raise AttemptStateCoherenceError("raw_provider_response_hash")
    if state.terminal_outcome in {
        "failed_utf8_decode",
        "failed_duplicate_key",
        "failed_strict_parse",
        "failed_canonical_validation",
        "failed_cross_field_validation",
        "failed_evidence_trace_coherence",
        "failed_trace_validation",
        "failed_url_security_validation",
        "failed_retrieval_coherence",
        "failed_evidence_policy",
    } and state.raw_provider_response_hash is None:
        raise AttemptStateCoherenceError("raw_provider_response_hash")


def validate_attempt_state(state: AttemptState) -> None:
    if not isinstance(state, AttemptState):
        raise AttemptStateCoherenceError("attempt_state_type")
    _require_member("workload_branch", state.workload_branch, WORKLOAD_BRANCHES)
    _require_member(
        "presemantic_state",
        state.normalized_presemantic_state,
        PRESEMANTIC_STATES,
    )
    _require_member(
        "major_stage",
        state.highest_completed_stage,
        HIGHEST_COMPLETED_STAGES,
    )
    _require_member(
        "normalization_disposition",
        state.normalization_disposition,
        NORMALIZATION_DISPOSITIONS,
    )
    _require_member("terminal_outcome", state.terminal_outcome, TERMINAL_OUTCOMES)
    _require_member("terminal_outcome", state.attempt_outcome, TERMINAL_OUTCOMES)
    _require_member("refusal_state", state.refusal_state, REFUSAL_STATES)

    if state.normalized_presemantic_state not in _PRESEMANTIC_ALLOWED_BY_OUTCOME[
        state.terminal_outcome
    ]:
        raise AttemptStateCoherenceError("presemantic_terminal_compatibility")
    if state.attempt_outcome != state.terminal_outcome:
        raise AttemptStateCoherenceError("attempt_outcome")
    if state.failure_category != (
        None if state.terminal_outcome == "accepted" else state.terminal_outcome
    ):
        raise AttemptStateCoherenceError("failure_category")
    if state.refusal_state != derive_refusal_state(
        state.terminal_outcome,
        state.normalized_presemantic_state,
    ):
        raise AttemptStateCoherenceError("refusal_state")
    if state.normalization_disposition != (
        _derive_normalization_disposition_from_summary(
            state.normalization_action_summary
        )
    ):
        raise AttemptStateCoherenceError("normalization_disposition")
    if not is_state_fragment_coherent(
        terminal_outcome=state.terminal_outcome,
        normalization_disposition=state.normalization_disposition,
        attempt_outcome=state.attempt_outcome,
    ):
        raise AttemptStateCoherenceError("state_fragment")

    completed_stages = tuple(
        event.stage_or_event_id
        for event in state.ledger.events
        if event.event_type == "major_stage" and event.result == "completed"
    )
    if (
        derive_highest_completed_stage(completed_stages)
        != state.highest_completed_stage
    ):
        raise AttemptStateCoherenceError("highest_completed_stage_ledger")
    derived_terminal, terminal_index = _derive_terminal_from_ledger(
        state.normalized_presemantic_state,
        state.ledger,
    )
    if derived_terminal != state.terminal_outcome:
        raise AttemptStateCoherenceError("first_terminal_condition")
    if any(
        event.result != "aborted_by_earlier_terminal"
        for event in state.ledger.events[terminal_index + 1 :]
    ):
        raise AttemptStateCoherenceError("event_after_terminal")

    _validate_stage_rule(state)
    _validate_validator_inventory(state)
    _validate_hash_rules(state)
