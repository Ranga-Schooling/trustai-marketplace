"""Pilot-minimal immutable result-record contract and implementation tests."""

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
from app.services.evaluation_contract_identity import (
    load_strict_normalization_spec,
    verify_normalization_parser_artifact,
    verify_output_schema_artifact,
    verify_prompt_template_artifact,
)
from app.services.evaluation_data_handling import (
    POLICY_HASH as DATA_POLICY_HASH,
    POLICY_ID as DATA_POLICY_ID,
    POLICY_VERSION as DATA_POLICY_VERSION,
    derive_restricted_trace_reference,
    project_provider_data,
)
from app.services.evaluation_pricing import (
    calculate_estimated_cost,
    verify_pricing_snapshot,
)
from app.services.evaluation_result_record import (
    PilotAttemptKey,
    PilotAttemptRecord,
    PilotRunBundle,
    ResultRecordFoundationError,
    build_pilot_attempt_record,
    verify_result_record_contract,
)
from app.services.evaluation_retrieval_trace import (
    RetrievalSourceObservation,
    allocate_retrieval_observations,
    validate_trace_position_inventory,
)
from app.services.evaluation_search_tool_record import (
    RawSearchToolOperation,
    build_search_tool_projections,
)


ROOT = Path(__file__).resolve().parents[2]
PARSER_PATH = (
    ROOT / "docs" / "testing" / "ai-evaluation" / "normalization-parser.v1.json"
)
RUBRIC_PATH = ROOT / "docs" / "testing" / "ai-evaluation" / "rubric.v1.json"
CONTRACT_PATH = (
    ROOT / "docs" / "testing" / "ai-evaluation" / "result-record.v1.json"
)
PROMPT_PATH = ROOT / "docs" / "testing" / "ai-evaluation" / "prompt-templates.v1.json"
SCHEMA_PATH = ROOT / "docs" / "testing" / "ai-evaluation" / "output-schemas.v1.json"
POLICY_IDENTITY = ("test_policy_v1", "v1", "1" * 64)
RAW = b"synthetic provider output retained only in restricted projection"
RAW_HASH = hashlib.sha256(RAW).hexdigest()
FINAL_HASH = "b" * 64


def _state(*, workload_branch="text_final"):
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
            stage_or_event_id="all_required_processing_and_finalization_completed",
            applicability="applicable",
            result="completed",
            policy_identity_if_applicable=POLICY_IDENTITY,
        )
    )
    return derive_attempt_state(
        workload_branch=workload_branch,
        normalized_presemantic_state="ordinary_semantic_path",
        ledger=AttemptStageEventLedger(tuple(events)),
        normalization_actions=(),
        raw_provider_response_hash=RAW_HASH,
        accepted_artifact_hash=FINAL_HASH,
    )


def _provider_data(
    *,
    attempt_number: int = 1,
    status: str = "accepted",
    provider: str = "synthetic-provider",
    model: str = "synthetic-model",
):
    return project_provider_data(
        raw_provider_response=RAW,
        restricted_url_trace=None,
        safe_transport_metadata={
            "provider": provider,
            "model": model,
            "model_version_or_snapshot": "synthetic-snapshot-v1",
            "http_or_result_status": {
                "kind": "terminal_outcome",
                "value": status,
            },
            "started_at": "2026-08-31T20:00:00.000Z",
            "completed_at": "2026-08-31T20:00:01.250Z",
            "latency_measurements": {
                "end_to_end_latency_ms": 1250,
                "provider_latency_ms": 1100,
            },
            "input_token_usage": 100,
            "output_token_usage": 50,
            "finish_or_stop_reason": status,
            "attempt_number": attempt_number,
            "retry_count": attempt_number - 1,
        },
    )


def _timeout_state():
    return derive_attempt_state(
        workload_branch="text_final",
        normalized_presemantic_state="provider_timeout",
        ledger=AttemptStageEventLedger(
            (
                StageEvent(
                    event_ordinal=1,
                    event_type="normalized_presemantic_state",
                    stage_or_event_id="provider_timeout",
                    applicability="applicable",
                    result="failed",
                    policy_identity_if_applicable=POLICY_IDENTITY,
                    adapter_identity_if_applicable=(
                        "synthetic_adapter_v1",
                        "v1",
                        "a" * 64,
                    ),
                ),
            )
        ),
        normalization_actions=(),
        raw_provider_response_hash=RAW_HASH,
        accepted_artifact_hash=None,
    )


def _audit(state=None):
    state = state or _state()
    parser = load_strict_normalization_spec(PARSER_PATH)
    identity = verify_normalization_parser_artifact(parser)
    children = dict(identity.child_hashes)
    contract = verify_result_record_contract()
    values = {field: None for field in contract.normalization_audit_fields}
    values.update(
        {
            "normalization_spec_id": "normalization_parser_spec_v1",
            "normalization_spec_version": "v1",
            "normalization_spec_semantic_hash": identity.semantic_hash,
            "normalization_spec_file_sha256_or_immutable_run_binding_reference": hashlib.sha256(
                PARSER_PATH.read_bytes()
            ).hexdigest(),
            "canonical_parser_policy_id": "canonical_parser_policy_json_v1",
            "canonical_parser_policy_version": "v1",
            "canonical_parser_policy_hash": children[
                "canonical_parser_policy_json_v1"
            ],
            "normalization_hashing_policy_id": "normalization_hashing_policy_v1",
            "normalization_hashing_policy_version": "v1",
            "normalization_hashing_policy_hash": children[
                "normalization_hashing_policy_v1"
            ],
            "parser_implementation_id": "trustai_normalization_parser_v1",
            "parser_implementation_version": "v1",
            "parser_implementation_hash": hashlib.sha256(
                (
                    ROOT
                    / "backend"
                    / "app"
                    / "services"
                    / "normalization_parser.py"
                ).read_bytes()
            ).hexdigest(),
            "strict_json_policy_id": "strict_json_policy_v1",
            "strict_json_policy_version": "v1",
            "strict_json_policy_hash": children["strict_json_policy_v1"],
            "semantic_numeric_domain_policy_id": "semantic_numeric_domain_policy_v1",
            "semantic_numeric_domain_policy_version": "v1",
            "semantic_numeric_domain_policy_hash": children[
                "semantic_numeric_domain_policy_v1"
            ],
            "numeric_policy_execution_conformance_status": (
                "independent_reference_passed"
            ),
            "adapter_id": "synthetic_adapter_v1",
            "adapter_version": "v1",
            "adapter_hash": "a" * 64,
            "response_transport_mode": "non_streaming_http",
            "canonical_raw_byte_availability": True,
            "raw_response_unavailable_reason_if_applicable": None,
            "content_decoding_responsibility": "synthetic_adapter_v1",
            "stream_framing_policy_id_if_applicable": None,
            "stream_framing_policy_hash_if_applicable": None,
            "native_object_lossless_equivalence_evidence_if_applicable": None,
            "normalization_actions": [],
            "normalized_presemantic_state": state.normalized_presemantic_state,
            "highest_completed_stage": state.highest_completed_stage,
            "normalization_disposition": state.normalization_disposition,
            "terminal_outcome": state.terminal_outcome,
            "attempt_outcome": state.attempt_outcome,
            "validator_states": [
                {
                    "validator_id": item.validator_id,
                    "applicability": item.applicability,
                    "state": item.state,
                }
                for item in state.validator_states
            ],
            "attempt_state_coherence": "passed",
            "refusal_state": state.refusal_state,
            "failure_category": state.failure_category,
            "numeric_domain_reason_if_applicable": None,
            "stage_event_ledger_hash_or_safe_reference": "c" * 64,
            "stage_event_ledger_policy_id": "attempt_stage_event_ledger_v1",
            "stage_event_ledger_policy_version": "v1",
            "stage_event_ledger_policy_hash": children[
                "attempt_stage_event_ledger_v1"
            ],
            "compatibility_matrix_id": "attempt_state_compatibility_matrix_v1",
            "compatibility_matrix_version": "v1",
            "compatibility_matrix_hash": children[
                "attempt_state_compatibility_matrix_v1"
            ],
            "validator_applicability_policy_id": (
                "workload_validator_applicability_v1"
            ),
            "validator_applicability_policy_version": "v1",
            "validator_applicability_policy_hash": children[
                "workload_validator_applicability_v1"
            ],
            "first_terminal_condition_reducer_id": (
                "first_terminal_condition_reducer_v1"
            ),
            "first_terminal_condition_reducer_version": "v1",
            "first_terminal_condition_reducer_hash": children[
                "first_terminal_condition_reducer_v1"
            ],
            "wire_response_hash_if_available": "d" * 64,
            "raw_provider_response_hash": state.raw_provider_response_hash,
            "stream_trace_hash_if_applicable": None,
            "native_structured_object_hash_if_applicable": None,
            "transport_extracted_payload_hash": (
                "e" * 64 if state.highest_completed_stage != "none" else None
            ),
            "strict_parsed_semantic_payload_hash": (
                "f" * 64
                if HIGHEST_COMPLETED_STAGES.index(state.highest_completed_stage) >= 3
                else None
            ),
            "canonical_validation_candidate_hash": (
                "9" * 64
                if HIGHEST_COMPLETED_STAGES.index(state.highest_completed_stage) >= 4
                else None
            ),
            "provider_trace_hash_if_applicable": (
                "1" * 64 if state.workload_branch == "search_retrieval" else None
            ),
            "retrieval_trace_hash_if_applicable": (
                "2" * 64 if state.workload_branch == "search_retrieval" else None
            ),
            "canonical_evidence_bundle_hash_if_applicable": (
                state.accepted_artifact_hash
                if state.workload_branch == "search_retrieval"
                else None
            ),
            "final_semantic_payload_hash_if_applicable": (
                None
                if state.workload_branch == "search_retrieval"
                else state.accepted_artifact_hash
            ),
        }
    )
    binding_fields = (
        ("canonical_parser_policy_id", "canonical_parser_policy_version", "canonical_parser_policy_hash"),
        ("normalization_hashing_policy_id", "normalization_hashing_policy_version", "normalization_hashing_policy_hash"),
        ("strict_json_policy_id", "strict_json_policy_version", "strict_json_policy_hash"),
        ("semantic_numeric_domain_policy_id", "semantic_numeric_domain_policy_version", "semantic_numeric_domain_policy_hash"),
        ("stage_event_ledger_policy_id", "stage_event_ledger_policy_version", "stage_event_ledger_policy_hash"),
        ("compatibility_matrix_id", "compatibility_matrix_version", "compatibility_matrix_hash"),
        ("validator_applicability_policy_id", "validator_applicability_policy_version", "validator_applicability_policy_hash"),
        ("first_terminal_condition_reducer_id", "first_terminal_condition_reducer_version", "first_terminal_condition_reducer_hash"),
    )
    values["applied_policy_bindings"] = [
        {
            "policy_id": values[id_field],
            "policy_version": values[version_field],
            "policy_hash": values[hash_field],
        }
        for id_field, version_field, hash_field in binding_fields
    ] + [
        {
            "policy_id": DATA_POLICY_ID,
            "policy_version": DATA_POLICY_VERSION,
            "policy_hash": DATA_POLICY_HASH,
        }
    ]
    prompt_identity = verify_prompt_template_artifact(
        json.loads(PROMPT_PATH.read_text(encoding="utf-8"))
    )
    schema_identity = verify_output_schema_artifact(
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    )
    child_hashes = {
        **dict(prompt_identity.child_hashes),
        **dict(schema_identity.child_hashes),
    }
    binding_ids = {
        "text_final": ("text_system_v1", "text_input_v1", "text_output_schema_v1"),
        "search_retrieval": (
            "search_retrieval_v1",
            "retrieval_evidence_bundle_v1",
        ),
        "search_synthesis_final": ("search_synthesis_v1", "search_output_schema_v1"),
        "visual_final": (
            "visual_system_v1",
            "visual_context_v1",
            "visual_output_schema_v1",
        ),
    }[state.workload_branch]
    for binding_id in binding_ids:
        values["applied_policy_bindings"].append(
            {
                "policy_id": binding_id,
                "policy_version": "v1",
                "policy_hash": child_hashes[binding_id],
            }
        )
    return values


def _key(
    *,
    attempt_number: int = 1,
    provider: str = "synthetic-provider",
    model: str = "synthetic-model",
    fixture_id: str = "PT1",
    workload: str = "text_risk_analysis",
):
    return PilotAttemptKey(
        evaluation_id="capstone-evaluation-v1",
        fixture_id=fixture_id,
        candidate_id="synthetic-candidate-v1",
        provider=provider,
        model=model,
        component_topology="unified",
        workload=workload,
        run_number=1,
        attempt_number=attempt_number,
    )


def _envelope(
    state=None,
    *,
    attempt_number: int = 1,
    provider: str = "synthetic-provider",
    model: str = "synthetic-model",
    fixture_id: str = "PT1",
    workload: str = "text_risk_analysis",
    search_tool_data=None,
):
    state = state or _state()
    audit = _audit(state)
    metadata = _provider_data(
        attempt_number=attempt_number,
        status=state.terminal_outcome,
        provider=provider,
        model=model,
    ).ordinary.safe_transport_metadata.as_dict()
    contract = verify_result_record_contract()
    values = {field: None for field in contract.pilot_envelope_fields}
    values.update(
        {
            "evaluation_id": "capstone-evaluation-v1",
            "experiment_version": "v1",
            "experiment_phase": "pilot",
            "repository_harness_commit_sha": "b230881287a48fe83e722bd7b1c2c841de08f372",
            "harness_version": "v1",
            "fixture_manifest_version": "v1",
            "fixture_id": fixture_id,
            "fixture_version": "v1",
            "rubric_version": "v1",
            "scoring_rule_version": "v1",
            "truth_sheet_version": None,
            "visual_asset_set_version": None,
            "provider": provider,
            "model": model,
            "model_version_or_snapshot": "synthetic-snapshot-v1",
            "provider_request_id": None,
            "api_endpoint": "synthetic-endpoint-v1",
            "api_version": "v1",
            "component_topology": "unified",
            "workload": workload,
            "prompt_template_version": "v1",
            "prompt_hash": "8" * 64,
            "output_schema_version": "v1",
            "request_configuration": None,
            "run_number": 1,
            "attempt_number": attempt_number,
            "retry_reason": (
                None if attempt_number == 1 else "provider_attempt_timeout"
            ),
            "input_hashes": {"rendered_prompt": "7" * 64},
            "started_at": metadata["started_at"],
            "completed_at": metadata["completed_at"],
            "http_or_result_status": metadata["http_or_result_status"],
            "finish_or_stop_reason": metadata["finish_or_stop_reason"],
            "refusal_state": state.refusal_state,
            "latency_measurements": metadata["latency_measurements"],
            "schema_pass": next(
                item.state == "passed"
                for item in state.validator_states
                if item.validator_id == "canonical_schema_validation"
            ),
            "raw_response_hash": audit["raw_provider_response_hash"],
            "normalized_output_hash": audit[
                "final_semantic_payload_hash_if_applicable"
            ],
            "normalization_parser_version": audit["parser_implementation_version"],
            "normalization_performed": False,
            "normalization_actions": audit["normalization_actions"],
            "search_query_list": None,
            "search_and_tool_calls": None,
            "source_urls": None,
            "source_retrieval_timestamps": None,
            "claim_to_source_mapping": None,
            "visual_asset_hashes": None,
            "input_token_usage": metadata["input_token_usage"],
            "output_token_usage": metadata["output_token_usage"],
            "reasoning_usage_if_exposed": None,
            "image_usage_if_exposed": None,
            "rate_limit_and_service_metadata_if_exposed": None,
            "estimated_cost": None,
            "retry_count": attempt_number - 1,
            "safe_failure_code": state.failure_category,
            "notes_and_anomalies": [],
        }
    )
    if search_tool_data is not None:
        safe = search_tool_data.ordinary.as_dict()
        values.update(
            {
                "search_query_list": [
                    item["query_id"]
                    for item in safe["operations"]
                    if item["query_id"] is not None
                ],
                "search_and_tool_calls": safe,
                "source_urls": [
                    item["public_safe_canonical_url"] for item in safe["sources"]
                ],
                "source_retrieval_timestamps": [
                    {
                        "source_id": item["source_id"],
                        "retrieved_at": item["retrieved_at"],
                    }
                    for item in safe["sources"]
                ],
                "claim_to_source_mapping": safe["claim_evidence_source_links"],
            }
        )
    return values


def _search_tool_data():
    inventory = validate_trace_position_inventory(
        retrieval_attempt_ordinals=[1],
        tool_call_ordinals_by_attempt={1: [1]},
        result_ordinals_by_tool_call={(1, 1): [1]},
        evidence_ordinals_by_result={(1, 1, 1): []},
    )
    plan = allocate_retrieval_observations(
        inventory,
        (
            RetrievalSourceObservation(1, 1, 1, False, None, None, None),
        ),
        (),
    )
    operation = RawSearchToolOperation(
        retrieval_attempt_ordinal=1,
        tool_call_ordinal=1,
        operation_type="search",
        raw_search_query="synthetic pilot product query",
        raw_tool_arguments={"query": "synthetic pilot product query"},
        outcome="completed",
        safe_failure_code=None,
        started_at="2026-08-31T20:00:00.000Z",
        completed_at="2026-08-31T20:00:00.250Z",
        latency_ms=250,
        restricted_trace_reference=derive_restricted_trace_reference(b"q" * 16),
        restricted_url_traces=(),
    )
    return build_search_tool_projections(
        operations=(operation,),
        trace_inventory=inventory,
        allocation_plan=plan,
        claim_evidence_links=(),
    )


def _record(*, attempt_number: int = 1):
    state = _state()
    return build_pilot_attempt_record(
        attempt_key=_key(attempt_number=attempt_number),
        attempt_state=state,
        provider_data=_provider_data(attempt_number=attempt_number),
        normalization_audit=_audit(state),
        pilot_envelope=_envelope(state, attempt_number=attempt_number),
        provider_attempt_started=True,
    )


def _timeout_record():
    state = _timeout_state()
    return build_pilot_attempt_record(
        attempt_key=_key(),
        attempt_state=state,
        provider_data=_provider_data(status="provider_timeout"),
        normalization_audit=_audit(state),
        pilot_envelope=_envelope(state),
        provider_attempt_started=True,
    )


def test_contract_exactly_partitions_frozen_normalization_and_rubric_fields():
    contract = verify_result_record_contract()
    parser = json.loads(PARSER_PATH.read_text(encoding="utf-8"))
    rubric = json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))

    assert len(contract.normalization_audit_fields) == 66
    assert list(contract.normalization_audit_fields) == parser[
        "result_record_integration"
    ]["required_fields"]
    assert len(contract.pilot_envelope_fields) == 55
    assert len(contract.scored_only_fields) == 21
    assert set(contract.pilot_envelope_fields).isdisjoint(contract.scored_only_fields)
    assert set(contract.pilot_envelope_fields) | set(contract.scored_only_fields) == set(
        rubric["experimental_protocol"]["result_record_fields"]
    )


def test_complete_pilot_attempt_is_immutable_hashed_and_privacy_safe():
    record = _record()
    exposed = record.as_dict()

    assert tuple(exposed) == (
        "attempt_key",
        "normalization_audit",
        "ordinary_projection",
        "pilot_envelope",
        "record_contract",
        "record_hash",
        "record_type",
    )
    unhashed = deepcopy(exposed)
    record_hash = unhashed.pop("record_hash")
    expected = hashlib.sha256(
        json.dumps(
            unhashed,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert record_hash == expected
    serialized = json.dumps(exposed, sort_keys=True)
    assert RAW.decode() not in serialized
    assert record.restricted_provider_data.raw_provider_response == RAW
    exposed["attempt_key"]["fixture_id"] = "mutated"
    assert record.as_dict()["attempt_key"]["fixture_id"] == "PT1"
    with pytest.raises(FrozenInstanceError):
        record.ordinary_json = b"mutated"


def test_grounded_search_attempt_binds_exact_safe_projection_and_restricted_inputs():
    state = _state(workload_branch="search_retrieval")
    search_tool_data = _search_tool_data()
    key = _key(
        fixture_id="PS1",
        workload="grounded_product_price_research",
    )
    envelope = _envelope(
        state,
        fixture_id="PS1",
        workload="grounded_product_price_research",
        search_tool_data=search_tool_data,
    )

    record = build_pilot_attempt_record(
        attempt_key=key,
        attempt_state=state,
        provider_data=_provider_data(),
        normalization_audit=_audit(state),
        pilot_envelope=envelope,
        provider_attempt_started=True,
        search_tool_data=search_tool_data,
    )
    exposed = record.as_dict()["pilot_envelope"]
    serialized = json.dumps(record.as_dict(), sort_keys=True)

    assert exposed["search_query_list"] == ["qry-0001-0001"]
    assert exposed["search_and_tool_calls"] == search_tool_data.ordinary.as_dict()
    assert exposed["source_urls"] == []
    assert exposed["source_retrieval_timestamps"] == []
    assert exposed["claim_to_source_mapping"] == []
    assert "synthetic pilot product query" not in serialized
    assert record.restricted_search_tool_data is not None
    assert record.restricted_search_tool_data.as_dict()["operations"][0][
        "raw_search_query"
    ] == "synthetic pilot product query"
    assert "synthetic pilot product query" not in repr(record)


def test_grounded_search_attempt_rejects_missing_or_tampered_safe_projection():
    state = _state(workload_branch="search_retrieval")
    search_tool_data = _search_tool_data()
    key = _key(
        fixture_id="PS1",
        workload="grounded_product_price_research",
    )
    envelope = _envelope(
        state,
        fixture_id="PS1",
        workload="grounded_product_price_research",
        search_tool_data=search_tool_data,
    )

    with pytest.raises(ResultRecordFoundationError, match="safe_search_tool_data"):
        build_pilot_attempt_record(
            attempt_key=key,
            attempt_state=state,
            provider_data=_provider_data(),
            normalization_audit=_audit(state),
            pilot_envelope=envelope,
            provider_attempt_started=True,
        )

    tampered = deepcopy(envelope)
    tampered["search_query_list"] = ["literal query must not be accepted"]
    with pytest.raises(
        ResultRecordFoundationError,
        match="safe_search_tool_alias:search_query_list",
    ):
        build_pilot_attempt_record(
            attempt_key=key,
            attempt_state=state,
            provider_data=_provider_data(),
            normalization_audit=_audit(state),
            pilot_envelope=tampered,
            provider_attempt_started=True,
            search_tool_data=search_tool_data,
        )


def test_non_search_attempt_rejects_search_tool_projection():
    with pytest.raises(
        ResultRecordFoundationError,
        match="search_tool_data_not_applicable",
    ):
        build_pilot_attempt_record(
            attempt_key=_key(),
            attempt_state=_state(),
            provider_data=_provider_data(),
            normalization_audit=_audit(),
            pilot_envelope=_envelope(),
            provider_attempt_started=True,
            search_tool_data=_search_tool_data(),
        )


def test_preflight_failure_never_creates_a_fake_attempt_or_increments_bundle():
    bundle = PilotRunBundle()
    assert bundle.record_preflight_failure() is bundle
    with pytest.raises(
        ResultRecordFoundationError,
        match="preflight_failure_is_not_provider_attempt",
    ):
        build_pilot_attempt_record(
            attempt_key=_key(),
            attempt_state=_state(),
            provider_data=_provider_data(),
            normalization_audit=_audit(),
            pilot_envelope=_envelope(),
            provider_attempt_started=False,
        )


def test_exact_pricing_record_can_bind_to_its_physical_attempt():
    provider = "OpenAI"
    model = "gpt-5.6-sol"
    schedule_id = "openai_gpt_5_6_sol_standard_short_context_v1"
    snapshot = verify_pricing_snapshot()
    schedule = next(item for item in snapshot.schedules if item.schedule_id == schedule_id)
    usage = {component: 0 for component, _ in schedule.rates}
    usage.update({"uncached_input_tokens": 100, "output_tokens": 10})
    estimated_cost = calculate_estimated_cost(
        snapshot,
        schedule_id=schedule_id,
        usage=usage,
    ).as_dict()
    state = _state()
    envelope = _envelope(state, provider=provider, model=model)
    envelope["estimated_cost"] = estimated_cost

    record = build_pilot_attempt_record(
        attempt_key=_key(provider=provider, model=model),
        attempt_state=state,
        provider_data=_provider_data(provider=provider, model=model),
        normalization_audit=_audit(state),
        pilot_envelope=envelope,
        provider_attempt_started=True,
    )

    assert record.as_dict()["pilot_envelope"]["estimated_cost"] == estimated_cost

    envelope["estimated_cost"]["total_usd"] = "0"
    with pytest.raises(ResultRecordFoundationError, match="estimated_cost_contract"):
        build_pilot_attempt_record(
            attempt_key=_key(provider=provider, model=model),
            attempt_state=state,
            provider_data=_provider_data(provider=provider, model=model),
            normalization_audit=_audit(state),
            pilot_envelope=envelope,
            provider_attempt_started=True,
        )


def test_failed_or_earlier_attempts_are_never_replaced_by_a_later_retry():
    first = _timeout_record()
    second = _record(attempt_number=2)
    bundle = PilotRunBundle().append_attempt(first).append_attempt(second)

    assert bundle.attempts == (first, second)
    assert bundle.attempts[0].as_dict()["pilot_envelope"]["safe_failure_code"] == (
        "provider_timeout"
    )
    assert bundle.attempts[1].as_dict()["pilot_envelope"]["safe_failure_code"] is None
    assert bundle.attempts[0].record_hash == first.record_hash
    with pytest.raises(ResultRecordFoundationError, match="duplicate_attempt_key"):
        bundle.append_attempt(first)


def test_retry_bundle_rejects_attempts_outside_the_frozen_budget():
    with pytest.raises(ResultRecordFoundationError, match="attempt_key:attempt_number"):
        _key(attempt_number=3)


def test_retry_bundle_requires_a_contiguous_retryable_predecessor():
    with pytest.raises(ResultRecordFoundationError, match="retry_policy:missing_previous_attempt"):
        PilotRunBundle().append_attempt(_record(attempt_number=2))

    first = _record()
    second = _record(attempt_number=2)
    with pytest.raises(
        ResultRecordFoundationError,
        match="retry_policy:previous_attempt_nonretryable",
    ):
        PilotRunBundle().append_attempt(first).append_attempt(second)


def test_retry_bundle_requires_the_exact_safe_reason_mapped_from_attempt_one():
    state = _state()
    envelope = _envelope(state, attempt_number=2)
    envelope["retry_reason"] = "transient_provider_connection_error"
    second = build_pilot_attempt_record(
        attempt_key=_key(attempt_number=2),
        attempt_state=state,
        provider_data=_provider_data(attempt_number=2),
        normalization_audit=_audit(state),
        pilot_envelope=envelope,
        provider_attempt_started=True,
    )

    with pytest.raises(ResultRecordFoundationError, match="retry_policy:retry_reason"):
        PilotRunBundle().append_attempt(_timeout_record()).append_attempt(second)


def test_attempt_record_rejects_retry_reason_outside_the_closed_vocabulary():
    state = _state()
    envelope = _envelope(state, attempt_number=2)
    envelope["retry_reason"] = "provider said please retry later"

    with pytest.raises(ResultRecordFoundationError, match="retry_reason"):
        build_pilot_attempt_record(
            attempt_key=_key(attempt_number=2),
            attempt_state=state,
            provider_data=_provider_data(attempt_number=2),
            normalization_audit=_audit(state),
            pilot_envelope=envelope,
            provider_attempt_started=True,
        )


def test_json_object_member_order_is_not_semantic_but_record_hash_is_stable():
    state = _state()
    audit = _audit(state)
    envelope = _envelope(state)
    reordered_audit = dict(reversed(tuple(audit.items())))
    reordered_envelope = dict(reversed(tuple(envelope.items())))

    reordered = build_pilot_attempt_record(
        attempt_key=_key(),
        attempt_state=state,
        provider_data=_provider_data(),
        normalization_audit=reordered_audit,
        pilot_envelope=reordered_envelope,
        provider_attempt_started=True,
    )

    assert reordered.record_hash == _record().record_hash


def test_completed_stage_requires_its_owned_hash_inventory():
    state = _state()
    audit = _audit(state)
    audit["canonical_validation_candidate_hash"] = None

    with pytest.raises(
        ResultRecordFoundationError,
        match="stage_hash_required:canonical_validation_candidate_hash",
    ):
        build_pilot_attempt_record(
            attempt_key=_key(),
            attempt_state=state,
            provider_data=_provider_data(),
            normalization_audit=audit,
            pilot_envelope=_envelope(state),
            provider_attempt_started=True,
        )


def test_normalization_action_records_are_closed_safe_and_state_coherent():
    state = _state()
    audit = _audit(state)
    audit["normalization_actions"] = [
        {
            "ordinal": 1,
            "action": "unwrap_transport_envelope",
            "policy_id": "synthetic_policy_v1",
            "policy_version": "v1",
            "policy_hash": "1" * 64,
            "adapter_id_if_applicable": None,
            "adapter_version_if_applicable": None,
            "adapter_hash_if_applicable": None,
            "input_hash": "2" * 64,
            "output_hash": "3" * 64,
            "trace_references": [],
            "deterministic_parameters": [["mode", "safe"]],
            "action_result": "completed",
        }
    ]

    with pytest.raises(
        ResultRecordFoundationError,
        match="normalization_action_summary_mismatch",
    ):
        build_pilot_attempt_record(
            attempt_key=_key(),
            attempt_state=state,
            provider_data=_provider_data(),
            normalization_audit=audit,
            pilot_envelope=_envelope(state),
            provider_attempt_started=True,
        )

    audit["normalization_actions"][0]["raw_provider_response"] = RAW.decode()
    with pytest.raises(
        ResultRecordFoundationError,
        match="normalization_action_fields",
    ):
        build_pilot_attempt_record(
            attempt_key=_key(),
            attempt_state=state,
            provider_data=_provider_data(),
            normalization_audit=audit,
            pilot_envelope=_envelope(state),
            provider_attempt_started=True,
        )


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (lambda audit, envelope: audit.pop("adapter_hash"), "normalization_audit_fields"),
        (
            lambda audit, envelope: audit.__setitem__("attempt_outcome", "provider_timeout"),
            "attempt_state_alias:attempt_outcome",
        ),
        (
            lambda audit, envelope: envelope.__setitem__("raw_response_hash", "0" * 64),
            "pilot_alias:raw_response_hash",
        ),
        (
            lambda audit, envelope: envelope.__setitem__("quality_scores", {}),
            "pilot_envelope_fields",
        ),
        (
            lambda audit, envelope: envelope.__setitem__("provider_request_id", "opaque"),
            "provider_request_id_verifier_pending",
        ),
    ],
)
def test_attempt_record_fails_closed_on_missing_alias_scored_or_unverified_data(
    mutation,
    error,
):
    state = _state()
    audit = _audit(state)
    envelope = _envelope(state)
    mutation(audit, envelope)

    with pytest.raises(ResultRecordFoundationError, match=error):
        build_pilot_attempt_record(
            attempt_key=_key(),
            attempt_state=state,
            provider_data=_provider_data(),
            normalization_audit=audit,
            pilot_envelope=envelope,
            provider_attempt_started=True,
        )


def test_contract_identity_and_source_inventory_fail_closed(tmp_path):
    artifact = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    artifact["normalization_audit_fields"].pop()
    path = tmp_path / "result-record.v1.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(ResultRecordFoundationError, match="normalization_audit_inventory"):
        verify_result_record_contract(path)


def test_direct_construction_of_a_pilot_attempt_record_is_forbidden():
    with pytest.raises(ResultRecordFoundationError, match="factory_required"):
        PilotAttemptRecord(
            key=_key(),
            ordinary_json=b"{}",
            restricted_provider_data=_provider_data().restricted,
        )
