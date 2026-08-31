"""Privacy-safe provider-neutral attempt-record foundation tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path

import pytest

from app.services.evaluation_attempt_state import (
    HIGHEST_COMPLETED_STAGES,
    AttemptStageEventLedger,
    StageEvent,
    derive_attempt_state,
)
from app.services.evaluation_data_handling import (
    DataHandlingPolicyError,
    capture_restricted_url_trace,
    derive_restricted_trace_reference,
    project_provider_data,
)
from app.services.evaluation_result_record import (
    FULL_RESULT_RECORD_BLOCKERS,
    PrivacySafeAttemptRecordFoundation,
    ResultRecordFoundationError,
    build_privacy_safe_attempt_record,
)


ROOT = Path(__file__).resolve().parents[2]
URL_POLICY = json.loads(
    (
        ROOT
        / "docs"
        / "testing"
        / "ai-evaluation"
        / "url-security-policy.v1.json"
    ).read_text(encoding="utf-8")
)
TEST_POLICY_IDENTITY = ("test_policy_v1", "v1", "1" * 64)


def _attempt_state(
    *,
    raw: bytes,
    workload_branch: str = "text_final",
    terminal_outcome: str = "accepted",
):
    if terminal_outcome == "accepted":
        events = [
            StageEvent(
                event_ordinal=index,
                event_type="major_stage",
                stage_or_event_id=stage,
                applicability="applicable",
                result="completed",
            )
            for index, stage in enumerate(HIGHEST_COMPLETED_STAGES[1:], start=1)
        ]
        events.append(
            StageEvent(
                event_ordinal=len(events) + 1,
                event_type="acceptance_finalization",
                stage_or_event_id=(
                    "all_required_processing_and_finalization_completed"
                ),
                applicability="applicable",
                result="completed",
                policy_identity_if_applicable=TEST_POLICY_IDENTITY,
            )
        )
        accepted_hash = "b" * 64
    elif terminal_outcome == "failed_url_security_validation":
        events = [
            StageEvent(
                event_ordinal=index,
                event_type="major_stage",
                stage_or_event_id=stage,
                applicability="applicable",
                result="completed",
            )
            for index, stage in enumerate(
                (
                    "raw_transport_captured",
                    "semantic_representation_extracted",
                ),
                start=1,
            )
        ]
        events.append(
            StageEvent(
                event_ordinal=len(events) + 1,
                event_type="validator",
                stage_or_event_id="url_security_validation_failed",
                applicability="applicable",
                result="failed",
                policy_identity_if_applicable=TEST_POLICY_IDENTITY,
            )
        )
        accepted_hash = None
    else:  # pragma: no cover - local test helper is intentionally closed
        raise AssertionError(terminal_outcome)
    return derive_attempt_state(
        workload_branch=workload_branch,
        normalized_presemantic_state="ordinary_semantic_path",
        ledger=AttemptStageEventLedger(tuple(events)),
        normalization_actions=(),
        raw_provider_response_hash=hashlib.sha256(raw).hexdigest(),
        accepted_artifact_hash=accepted_hash,
    )


def _classifier_case(vector_id: str):
    vector = next(
        vector
        for group_name in (
            "existing_direct",
            "existing_redirect",
            "existing_propagation_and_privacy",
            "existing_positive_proof",
            "adversarial",
        )
        for vector in URL_POLICY["test_vectors"][group_name]
        if vector["id"] == vector_id
    )
    classifier_input = deepcopy(vector["classifier_input"])
    capabilities = {}
    for member in classifier_input["redirect_context"]["members"]:
        position = member["position"]
        capability = derive_restricted_trace_reference(
            position.to_bytes(2, "big") * 8
        )
        member["restricted_trace_reference"] = capability.value
        capabilities[position] = capability
    current = classifier_input["redirect_context"]["current_position"]
    classifier_input["restricted_trace_reference"] = capabilities[current].value
    return classifier_input, capabilities


def _projections(
    raw: bytes,
    *,
    status: str = "accepted",
    vector_id: str | None = None,
):
    trace = None
    if vector_id is not None:
        classifier_input, capabilities = _classifier_case(vector_id)
        trace = capture_restricted_url_trace(
            classifier_input,
            reference_capabilities=capabilities,
        )
    return project_provider_data(
        raw_provider_response=raw,
        restricted_url_trace=trace,
        safe_transport_metadata={
            "provider": "synthetic-provider",
            "model": "synthetic-model",
            "http_or_result_status": {
                "kind": "terminal_outcome",
                "value": status,
            },
            "finish_or_stop_reason": status,
            "attempt_number": 1,
            "retry_count": 0,
        },
    )


def test_accepted_attempt_builds_only_the_already_owned_ordinary_foundation():
    raw = b"synthetic provider response"
    state = _attempt_state(raw=raw)
    record = build_privacy_safe_attempt_record(
        attempt_state=state,
        provider_data=_projections(raw),
    )

    ordinary = record.ordinary.as_dict()
    assert ordinary == {
        "workload_branch": "text_final",
        "normalized_presemantic_state": "ordinary_semantic_path",
        "highest_completed_stage": "accepted",
        "normalization_disposition": "not_required",
        "terminal_outcome": "accepted",
        "attempt_outcome": "accepted",
        "validator_states": [
            {
                "validator_id": item.validator_id,
                "applicability": item.applicability,
                "state": item.state,
            }
            for item in state.validator_states
        ],
        "refusal_state": "none",
        "failure_category": None,
        "raw_provider_response_hash": hashlib.sha256(raw).hexdigest(),
        "canonical_evidence_bundle_hash_if_applicable": None,
        "final_semantic_payload_hash_if_applicable": "b" * 64,
        "restricted_trace_reference_if_applicable": None,
        "url_security_classification_if_applicable": None,
        "url_security_reason_codes_if_applicable": None,
        "url_security_policy_id_if_applicable": None,
        "url_security_policy_version_if_applicable": None,
        "url_security_policy_hash_if_applicable": None,
        "public_safe_canonical_urls": [],
        "safe_transport_metadata": _projections(raw).ordinary.safe_transport_metadata.as_dict(),
        "provider_data_handling_policy": {
            "policy_id": "provider_data_handling_review_v1",
            "policy_version": "v1",
            "policy_hash": (
                "9f58a7d84698f0d77ea1af58eee72c3b512e1204a760409eb08520cda7529d52"
            ),
        },
    }
    assert record.complete_result_record_eligible is False
    assert record.execution_authority is False
    assert record.full_result_record_blockers == FULL_RESULT_RECORD_BLOCKERS
    assert record.restricted_provider_data.raw_provider_response == raw


def test_search_retrieval_acceptance_maps_the_owned_hash_to_the_evidence_bundle():
    raw = b"synthetic retrieval response"
    state = _attempt_state(raw=raw, workload_branch="search_retrieval")
    ordinary = build_privacy_safe_attempt_record(
        attempt_state=state,
        provider_data=_projections(raw),
    ).ordinary.as_dict()

    assert ordinary["canonical_evidence_bundle_hash_if_applicable"] == "b" * 64
    assert ordinary["final_semantic_payload_hash_if_applicable"] is None


def test_raw_response_hash_and_terminal_metadata_must_match_attempt_state():
    raw = b"one response"
    state = _attempt_state(raw=raw)

    with pytest.raises(
        ResultRecordFoundationError,
        match="raw_provider_response_hash_mismatch",
    ):
        build_privacy_safe_attempt_record(
            attempt_state=state,
            provider_data=_projections(b"different response"),
        )

    with pytest.raises(
        ResultRecordFoundationError,
        match="terminal_outcome_metadata_mismatch",
    ):
        build_privacy_safe_attempt_record(
            attempt_state=state,
            provider_data=_projections(raw, status="provider_timeout"),
        )


def test_failed_url_security_record_recomputes_only_the_safe_trace_projection():
    raw = b"synthetic failed URL response"
    state = _attempt_state(
        raw=raw,
        workload_branch="search_retrieval",
        terminal_outcome="failed_url_security_validation",
    )
    projections = _projections(
        raw,
        status="failed_url_security_validation",
        vector_id="R2",
    )
    record = build_privacy_safe_attempt_record(
        attempt_state=state,
        provider_data=projections,
    )

    ordinary = record.ordinary.as_dict()
    assert ordinary["url_security_classification_if_applicable"] == "sensitive"
    assert ordinary["url_security_reason_codes_if_applicable"]
    assert ordinary["url_security_policy_id_if_applicable"] == (
        "url_security_policy_v1"
    )
    assert ordinary["restricted_trace_reference_if_applicable"]
    assert ordinary["public_safe_canonical_urls"] == []
    serialized = json.dumps(ordinary, sort_keys=True)
    restricted = projections.restricted.as_dict()
    assert restricted["raw_provider_response"].decode() not in serialized
    for trace in restricted["exact_url_traces"]:
        assert trace["exact_url"] not in serialized
        for member in trace["redirect_context"]["members"]:
            assert member["exact_url"] not in serialized


def test_url_security_failure_requires_the_same_restricted_trace():
    raw = b"synthetic failed URL response"
    state = _attempt_state(
        raw=raw,
        workload_branch="search_retrieval",
        terminal_outcome="failed_url_security_validation",
    )

    with pytest.raises(
        ResultRecordFoundationError,
        match="url_security_trace_required",
    ):
        build_privacy_safe_attempt_record(
            attempt_state=state,
            provider_data=_projections(
                raw,
                status="failed_url_security_validation",
            ),
        )


def test_restricted_trace_is_rejected_for_non_retrieval_attempt():
    raw = b"synthetic response"
    state = _attempt_state(raw=raw)

    with pytest.raises(
        ResultRecordFoundationError,
        match="url_trace_workload_branch",
    ):
        build_privacy_safe_attempt_record(
            attempt_state=state,
            provider_data=_projections(raw, vector_id="D7"),
        )


def test_foundation_and_ordinary_projection_require_the_validating_factory():
    with pytest.raises(ResultRecordFoundationError, match="factory_required"):
        PrivacySafeAttemptRecordFoundation(
            ordinary=None,
            restricted_provider_data=None,
            full_result_record_blockers=(),
            complete_result_record_eligible=False,
            execution_authority=False,
        )


def test_foundation_is_immutable_and_returned_dicts_are_detached():
    raw = b"synthetic provider response"
    record = build_privacy_safe_attempt_record(
        attempt_state=_attempt_state(raw=raw),
        provider_data=_projections(raw),
    )
    exposed = record.ordinary.as_dict()
    exposed["safe_transport_metadata"]["provider"] = "mutated"
    exposed["validator_states"].clear()

    assert record.ordinary.as_dict()["safe_transport_metadata"]["provider"] == (
        "synthetic-provider"
    )
    assert record.ordinary.as_dict()["validator_states"]
    assert raw.decode() not in repr(record)
    with pytest.raises(FrozenInstanceError):
        record.execution_authority = True


def test_data_handling_factory_boundary_remains_required():
    raw = b"synthetic provider response"
    state = _attempt_state(raw=raw)

    with pytest.raises((DataHandlingPolicyError, ResultRecordFoundationError)):
        build_privacy_safe_attempt_record(
            attempt_state=state,
            provider_data=object(),
        )


def test_foundation_declares_the_full_contract_dependencies_it_does_not_invent():
    assert FULL_RESULT_RECORD_BLOCKERS == (
        "pilot_result_record_builder_required",
        "immutable_run_binding",
        "adapter_and_transport_bindings",
        "complete_stage_hash_inventory",
        "result_identity_and_timing",
        "retry_run_record",
    )
