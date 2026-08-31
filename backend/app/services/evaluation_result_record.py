"""Privacy-safe foundation for provider-neutral evaluation attempt records.

The frozen normalization contract explicitly requires a future complete result
record artifact.  This module does not invent that contract.  It only composes
the attempt-state and provider-data projections whose ownership is already
frozen, while retaining restricted data behind its existing capability type.
It carries no persistence, provider, retry, network, or execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.evaluation_attempt_state import AttemptState, validate_attempt_state
from app.services.evaluation_data_handling import (
    POLICY_HASH as DATA_HANDLING_POLICY_HASH,
    POLICY_ID as DATA_HANDLING_POLICY_ID,
    POLICY_VERSION as DATA_HANDLING_POLICY_VERSION,
    ProviderDataProjections,
    RestrictedProviderDataProjection,
    SafeTransportMetadata,
)
from app.services.url_security import validate_url_security


FULL_RESULT_RECORD_BLOCKERS = (
    "future_result_record_artifact",
    "immutable_run_binding",
    "adapter_and_transport_bindings",
    "complete_stage_hash_inventory",
    "result_identity_and_timing",
    "retry_run_record",
)

_FOUNDATION_TOKEN = object()


class ResultRecordFoundationError(ValueError):
    """An already-frozen attempt/result-record boundary was violated."""


def _fail(code: str) -> ResultRecordFoundationError:
    return ResultRecordFoundationError(code)


@dataclass(frozen=True, slots=True)
class SafeValidatorState:
    validator_id: str
    applicability: str
    state: str

    def as_dict(self) -> dict[str, str]:
        return {
            "validator_id": self.validator_id,
            "applicability": self.applicability,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class OrdinaryAttemptRecordFoundation:
    workload_branch: str
    normalized_presemantic_state: str
    highest_completed_stage: str
    normalization_disposition: str
    terminal_outcome: str
    attempt_outcome: str
    validator_states: tuple[SafeValidatorState, ...]
    refusal_state: str
    failure_category: str | None
    raw_provider_response_hash: str | None
    canonical_evidence_bundle_hash_if_applicable: str | None
    final_semantic_payload_hash_if_applicable: str | None
    restricted_trace_reference_if_applicable: str | None
    url_security_classification_if_applicable: str | None
    url_security_reason_codes_if_applicable: tuple[str, ...] | None
    url_security_policy_id_if_applicable: str | None
    url_security_policy_version_if_applicable: str | None
    url_security_policy_hash_if_applicable: str | None
    public_safe_canonical_urls: tuple[str, ...]
    safe_transport_metadata: SafeTransportMetadata
    _token: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _FOUNDATION_TOKEN:
            raise _fail("ordinary_foundation_factory_required")

    def as_dict(self) -> dict[str, Any]:
        return {
            "workload_branch": self.workload_branch,
            "normalized_presemantic_state": self.normalized_presemantic_state,
            "highest_completed_stage": self.highest_completed_stage,
            "normalization_disposition": self.normalization_disposition,
            "terminal_outcome": self.terminal_outcome,
            "attempt_outcome": self.attempt_outcome,
            "validator_states": [item.as_dict() for item in self.validator_states],
            "refusal_state": self.refusal_state,
            "failure_category": self.failure_category,
            "raw_provider_response_hash": self.raw_provider_response_hash,
            "canonical_evidence_bundle_hash_if_applicable": (
                self.canonical_evidence_bundle_hash_if_applicable
            ),
            "final_semantic_payload_hash_if_applicable": (
                self.final_semantic_payload_hash_if_applicable
            ),
            "restricted_trace_reference_if_applicable": (
                self.restricted_trace_reference_if_applicable
            ),
            "url_security_classification_if_applicable": (
                self.url_security_classification_if_applicable
            ),
            "url_security_reason_codes_if_applicable": (
                list(self.url_security_reason_codes_if_applicable)
                if self.url_security_reason_codes_if_applicable is not None
                else None
            ),
            "url_security_policy_id_if_applicable": (
                self.url_security_policy_id_if_applicable
            ),
            "url_security_policy_version_if_applicable": (
                self.url_security_policy_version_if_applicable
            ),
            "url_security_policy_hash_if_applicable": (
                self.url_security_policy_hash_if_applicable
            ),
            "public_safe_canonical_urls": list(self.public_safe_canonical_urls),
            "safe_transport_metadata": self.safe_transport_metadata.as_dict(),
            "provider_data_handling_policy": {
                "policy_id": DATA_HANDLING_POLICY_ID,
                "policy_version": DATA_HANDLING_POLICY_VERSION,
                "policy_hash": DATA_HANDLING_POLICY_HASH,
            },
        }


@dataclass(frozen=True, slots=True)
class PrivacySafeAttemptRecordFoundation:
    ordinary: OrdinaryAttemptRecordFoundation
    restricted_provider_data: RestrictedProviderDataProjection = field(repr=False)
    full_result_record_blockers: tuple[str, ...]
    complete_result_record_eligible: bool
    execution_authority: bool
    _token: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _FOUNDATION_TOKEN:
            raise _fail("attempt_record_foundation_factory_required")
        if (
            self.full_result_record_blockers != FULL_RESULT_RECORD_BLOCKERS
            or self.complete_result_record_eligible is not False
            or self.execution_authority is not False
        ):
            raise _fail("attempt_record_foundation_boundary")


def _safe_url_result(
    provider_data: ProviderDataProjections,
) -> dict[str, Any] | None:
    restricted = provider_data.restricted.as_dict()
    traces = restricted["exact_url_traces"]
    reference = provider_data.ordinary.restricted_trace_reference
    if not traces:
        if reference is not None:
            raise _fail("restricted_trace_reference_without_trace")
        return None
    if len(traces) != 1:
        raise _fail("restricted_trace_cardinality")
    trace = traces[0]
    try:
        result = validate_url_security(**trace)
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise _fail("restricted_trace_revalidation") from exc
    if result.get("restricted_trace_reference") != reference:
        raise _fail("restricted_trace_reference_mismatch")
    return result


def _validate_projection_coherence(
    state: AttemptState,
    provider_data: ProviderDataProjections,
    safe_url_result: dict[str, Any] | None,
) -> None:
    ordinary = provider_data.ordinary
    restricted = provider_data.restricted
    if ordinary.raw_provider_response_hash != state.raw_provider_response_hash:
        raise _fail("raw_provider_response_hash_mismatch")
    raw = restricted.raw_provider_response
    if (raw is None) != (ordinary.raw_provider_response_hash is None):
        raise _fail("raw_provider_response_availability_mismatch")

    metadata = ordinary.safe_transport_metadata.as_dict()
    status = metadata.get("http_or_result_status")
    if status is not None and status["kind"] == "terminal_outcome":
        if status["value"] != state.terminal_outcome:
            raise _fail("terminal_outcome_metadata_mismatch")
    finish_reason = metadata.get("finish_or_stop_reason")
    if finish_reason is not None and finish_reason != state.terminal_outcome:
        raise _fail("finish_reason_metadata_mismatch")

    has_url_data = safe_url_result is not None or bool(
        ordinary.public_safe_canonical_urls
    )
    if has_url_data and state.workload_branch != "search_retrieval":
        raise _fail("url_trace_workload_branch")
    if state.terminal_outcome == "failed_url_security_validation":
        if safe_url_result is None:
            raise _fail("url_security_trace_required")
        if safe_url_result["classification"] == "public_safe":
            raise _fail("url_security_failure_classification")
        if ordinary.public_safe_canonical_urls:
            raise _fail("url_security_failure_public_url")
    if ordinary.public_safe_canonical_urls:
        if (
            state.terminal_outcome != "accepted"
            or safe_url_result is None
            or safe_url_result["classification"] != "public_safe"
        ):
            raise _fail("public_url_attempt_state")


def build_privacy_safe_attempt_record(
    *,
    attempt_state: AttemptState,
    provider_data: ProviderDataProjections,
) -> PrivacySafeAttemptRecordFoundation:
    """Compose frozen state and privacy projections without completing a run record."""
    try:
        validate_attempt_state(attempt_state)
    except (TypeError, ValueError) as exc:
        raise _fail("attempt_state_invalid") from exc
    if not isinstance(provider_data, ProviderDataProjections):
        raise _fail("provider_data_projection_required")

    safe_url_result = _safe_url_result(provider_data)
    _validate_projection_coherence(attempt_state, provider_data, safe_url_result)

    ordinary = OrdinaryAttemptRecordFoundation(
        workload_branch=attempt_state.workload_branch,
        normalized_presemantic_state=attempt_state.normalized_presemantic_state,
        highest_completed_stage=attempt_state.highest_completed_stage,
        normalization_disposition=attempt_state.normalization_disposition,
        terminal_outcome=attempt_state.terminal_outcome,
        attempt_outcome=attempt_state.attempt_outcome,
        validator_states=tuple(
            SafeValidatorState(
                validator_id=item.validator_id,
                applicability=item.applicability,
                state=item.state,
            )
            for item in attempt_state.validator_states
        ),
        refusal_state=attempt_state.refusal_state,
        failure_category=attempt_state.failure_category,
        raw_provider_response_hash=attempt_state.raw_provider_response_hash,
        canonical_evidence_bundle_hash_if_applicable=(
            attempt_state.accepted_artifact_hash
            if attempt_state.workload_branch == "search_retrieval"
            else None
        ),
        final_semantic_payload_hash_if_applicable=(
            attempt_state.accepted_artifact_hash
            if attempt_state.workload_branch != "search_retrieval"
            else None
        ),
        restricted_trace_reference_if_applicable=(
            provider_data.ordinary.restricted_trace_reference
        ),
        url_security_classification_if_applicable=(
            safe_url_result["classification"] if safe_url_result else None
        ),
        url_security_reason_codes_if_applicable=(
            tuple(safe_url_result["reason_codes"]) if safe_url_result else None
        ),
        url_security_policy_id_if_applicable=(
            safe_url_result["policy_id"] if safe_url_result else None
        ),
        url_security_policy_version_if_applicable=(
            safe_url_result["policy_version"] if safe_url_result else None
        ),
        url_security_policy_hash_if_applicable=(
            safe_url_result["policy_hash"] if safe_url_result else None
        ),
        public_safe_canonical_urls=(
            provider_data.ordinary.public_safe_canonical_urls
        ),
        safe_transport_metadata=provider_data.ordinary.safe_transport_metadata,
        _token=_FOUNDATION_TOKEN,
    )
    return PrivacySafeAttemptRecordFoundation(
        ordinary=ordinary,
        restricted_provider_data=provider_data.restricted,
        full_result_record_blockers=FULL_RESULT_RECORD_BLOCKERS,
        complete_result_record_eligible=False,
        execution_authority=False,
        _token=_FOUNDATION_TOKEN,
    )
