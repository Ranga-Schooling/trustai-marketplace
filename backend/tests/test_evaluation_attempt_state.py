"""Conformance tests for the frozen provider-neutral attempt-state core."""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path

import pytest


SPEC_PATH = (
    Path(__file__).parents[2]
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "normalization-parser.v1.json"
)
SPEC = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
MODULE_NAME = "app.services.evaluation_attempt_state"
TEST_POLICY_IDENTITY = ("test_policy_v1", "v1", "1" * 64)
TEST_ADAPTER_IDENTITY = ("test_adapter_v1", "v1", "2" * 64)


def _core():
    return importlib.import_module(MODULE_NAME)


VECTOR_SETS = (
    "highest_completed_stage_test_vectors",
    "normalization_disposition_test_vectors",
    "validator_state_test_vectors",
    "normalized_presemantic_state_test_vectors",
    "first_terminal_condition_test_vectors",
    "attempt_run_outcome_test_vectors",
    "attempt_illegal_combination_test_vectors",
    "attempt_status_compatibility_test_vectors",
)


def test_p1_6_vector_inventory_is_complete():
    expected = {
        "highest_completed_stage_test_vectors": 12,
        "normalization_disposition_test_vectors": 8,
        "validator_state_test_vectors": 6,
        "normalized_presemantic_state_test_vectors": 6,
        "first_terminal_condition_test_vectors": 8,
        "attempt_run_outcome_test_vectors": 6,
        "attempt_illegal_combination_test_vectors": 12,
        "attempt_status_compatibility_test_vectors": 24,
    }

    assert tuple(expected) == VECTOR_SETS
    assert sum(expected.values()) == 82
    for name, count in expected.items():
        vectors = SPEC[name]
        assert vectors["expected_case_count"] == count
        assert len(vectors["cases"]) == count
        assert vectors["provider_calls_required"] is False


def test_closed_vocabularies_match_the_frozen_contract():
    core = _core()
    status = SPEC["normalization_status_model"]

    assert core.HIGHEST_COMPLETED_STAGES == tuple(
        status["highest_completed_stage_total_order"]
    )
    assert core.NORMALIZATION_DISPOSITIONS == tuple(
        status["normalization_disposition_values"]
    )
    assert core.TERMINAL_OUTCOMES == tuple(status["terminal_outcome_values"])
    assert core.VALIDATOR_STATES == tuple(
        SPEC["validator_state_model"]["state_closed_enum"]
    )
    assert core.PRESEMANTIC_STATES == tuple(
        SPEC["normalized_presemantic_state"]["closed_enum"]
    )
    assert core.REFUSAL_STATES == tuple(
        SPEC["refusal_state_model"]["closed_enum"]
    )
    assert core.NORMALIZATION_ACTIONS == tuple(
        SPEC["normalization_action_vocabulary"]["closed_enum"]
    )
    assert core.EVENT_TYPES == tuple(
        SPEC["attempt_stage_event_ledger"]["event_type_closed_enum"]
    )
    assert core.EVENT_RESULTS == tuple(
        SPEC["attempt_stage_event_ledger"]["result_closed_enum"]
    )
    assert core.WORKLOAD_BRANCHES == tuple(
        SPEC["workload_validator_applicability"]["workload_branches"]
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(case, id=case["id"])
        for case in SPEC["highest_completed_stage_test_vectors"]["cases"]
    ],
)
def test_highest_completed_stage_vectors(case):
    core = _core()

    assert (
        core.derive_highest_completed_stage(case["completed_major_stages"])
        == case["expected_highest_completed_stage"]
    )


def test_highest_completed_stage_rejects_unknown_or_duplicate_stages():
    core = _core()

    with pytest.raises(core.AttemptStateError, match="unknown_major_stage"):
        core.derive_highest_completed_stage(["not-a-stage"])
    with pytest.raises(core.AttemptStateError, match="duplicate_major_stage"):
        core.derive_highest_completed_stage(
            ["raw_transport_captured", "raw_transport_captured"]
        )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(case, id=case["id"])
        for case in SPEC["normalization_disposition_test_vectors"]["cases"]
        if "action_summary" in case
    ],
)
def test_normalization_disposition_vectors(case):
    core = _core()
    records = _action_records_for_summary(core, case["action_summary"])
    actual = core.derive_normalization_disposition(records)

    if "expected_normalization_disposition" in case:
        assert actual == case["expected_normalization_disposition"]
    else:
        assert actual != "failed"


def test_failed_disposition_is_incoherent_with_acceptance():
    core = _core()

    assert not core.is_state_fragment_coherent(
        terminal_outcome="accepted",
        normalization_disposition="failed",
    )


def test_normalization_action_log_derives_disposition_and_validates_ordinals():
    core = _core()
    records = (
        _action_record(core, 1, "decode_strict_utf8", "completed"),
        _action_record(core, 2, "unwrap_transport_envelope", "completed"),
    )

    assert core.summarize_normalization_actions(
        records
    ) == core.NormalizationActionSummary(
        disposition_driving_completed=1,
        disposition_driving_failed_terminally=0,
        disposition_driving_aborted=0,
        observation_validation_only_completed=1,
    )
    assert core.derive_normalization_disposition(records) == "performed"

    with pytest.raises(core.AttemptStateError, match="action_ordinal"):
        core.summarize_normalization_actions((replace(records[0], ordinal=2),))


def _action_record(core, ordinal, action, action_result):
    return core.NormalizationActionRecord(
        ordinal=ordinal,
        action=action,
        policy_id="test_policy_v1",
        policy_version="v1",
        policy_hash="1" * 64,
        adapter_id_if_applicable=None,
        adapter_version_if_applicable=None,
        adapter_hash_if_applicable=None,
        input_hash="2" * 64,
        output_hash="3" * 64 if action_result == "completed" else None,
        trace_references=(),
        deterministic_parameters=(),
        action_result=action_result,
    )


def _action_records_for_summary(core, summary):
    records = []
    driving_actions = iter(
        action
        for action in core.NORMALIZATION_ACTIONS
        if action not in {"decode_strict_utf8", "parse_strict_json_text"}
    )
    for _ in range(summary["disposition_driving_completed"]):
        records.append(
            _action_record(core, len(records) + 1, next(driving_actions), "completed")
        )
    for action in ("decode_strict_utf8", "parse_strict_json_text")[:
        summary["observation_validation_only_completed"]
    ]:
        records.append(_action_record(core, len(records) + 1, action, "completed"))
    for _ in range(summary["disposition_driving_failed_terminally"]):
        records.append(
            _action_record(core, len(records) + 1, next(driving_actions), "failed")
        )
    for _ in range(summary["disposition_driving_aborted"]):
        records.append(
            _action_record(
                core,
                len(records) + 1,
                next(driving_actions),
                "aborted_by_earlier_terminal",
            )
        )
    return tuple(records)


def test_disposition_derivation_rejects_fabricated_summary_input():
    core = _core()

    with pytest.raises(core.AttemptStateError, match="normalization_action_log"):
        core.derive_normalization_disposition(
            core.NormalizationActionSummary(disposition_driving_completed=1)
        )


def test_normalization_action_record_requires_complete_audit_identity():
    core = _core()

    with pytest.raises(TypeError):
        core.NormalizationActionRecord(
            ordinal=1,
            action="decode_strict_utf8",
            action_result="completed",
        )
    with pytest.raises(core.AttemptStateError, match="output_hash"):
        replace(
            _action_record(core, 1, "decode_strict_utf8", "completed"),
            output_hash=None,
        )


def test_normalization_action_log_rejects_success_after_terminal_failure():
    core = _core()
    records = (
        _action_record(core, 1, "unwrap_transport_envelope", "failed"),
        _action_record(core, 2, "parse_strict_json_text", "completed"),
    )

    with pytest.raises(core.AttemptStateError, match="action_after_terminal"):
        core.summarize_normalization_actions(records)


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(case, id=case["id"])
        for case in SPEC["validator_state_test_vectors"]["cases"]
        if "validator_input" in case
    ],
)
def test_validator_state_vectors(case):
    core = _core()

    assert core.derive_validator_state(**case["validator_input"]) == case.get(
        "expected_validator_state",
        "passed",
    )


def test_validator_state_incoherence_vectors():
    core = _core()

    assert not core.is_validator_state_coherent(
        workload_branch="search_retrieval",
        validator_id="url_security_validation",
        provided_state="not_applicable",
    )
    assert not core.is_validator_execution_coherent(
        applicability="applicable",
        executed=True,
        accepted=True,
        provided_state="not_run",
    )


def test_workload_validator_applicability_matches_frozen_table():
    core = _core()
    policy = SPEC["workload_validator_applicability"]

    for branch, states in policy["table"].items():
        assert core.validator_applicability_for_branch(branch) == states
        assert core.ordered_applicable_validators(branch) == tuple(
            policy["ordered_applicable_validators"][branch]
        )


def _signals_for(case):
    signal_text = set(case["signals"])
    return {
        "provider_connection_error": any(
            "connection" in signal.lower() for signal in signal_text
        ),
        "provider_timeout": any(
            "provider timeout" in signal.lower() for signal in signal_text
        ),
        "provider_safety_block": any(
            "safety block" in signal.lower() for signal in signal_text
        ),
        "provider_native_refusal": any(
            "provider native refusal" in signal.lower() for signal in signal_text
        ),
        "http_provider_error": any(
            signal.startswith("HTTP ") for signal in signal_text
        ),
        "terminal_tool_error": any(
            "terminal tool failure" in signal.lower() for signal in signal_text
        ),
        "terminal_tool_timeout": any(
            "terminal tool timeout" in signal.lower() for signal in signal_text
        ),
    }


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(case, id=case["id"])
        for case in SPEC["normalized_presemantic_state_test_vectors"]["cases"]
    ],
)
def test_normalized_presemantic_state_vectors(case):
    core = _core()
    signals = core.PresemanticSignals(**_signals_for(case))

    assert (
        core.derive_normalized_presemantic_state(signals)
        == case["expected_normalized_presemantic_state"]
    )


def test_connection_and_timeout_cannot_both_be_authoritative():
    core = _core()

    with pytest.raises(core.AttemptStateError, match="transport_state_conflict"):
        core.derive_normalized_presemantic_state(
            core.PresemanticSignals(
                provider_connection_error=True,
                provider_timeout=True,
            )
        )


CONDITION_EVENT_IDS = {
    "transport extraction fails": "transport_extraction_failed",
    "UTF-8 decode fails": "strict_utf8_decode_failed",
    "syntactically malformed JSON": "strict_json_syntax_failed",
    "canonical schema invalid": "canonical_schema_validation_failed",
    "retrieval trace invalid": "retrieval_trace_reference_source_membership_failed",
    "URL security validation fails": "url_security_validation_failed",
    "evidence type unsupported": "evidence_trace_coherence_failed",
}

TERMINAL_EVENT_TYPES = {
    "transport_extraction_failed": "normalization_action",
    "strict_utf8_decode_failed": "normalization_action",
    "duplicate_key_detected_in_syntactically_valid_json": "normalization_action",
    "strict_json_syntax_failed": "normalization_action",
    "resource_limit_failed": "resource_limit",
    "objective_support_state_invalid": "internal_invariant",
    "attempt_state_coherence_failed": "internal_invariant",
    "other_application_owned_invariant_failed": "internal_invariant",
    "all_required_processing_and_finalization_completed": "acceptance_finalization",
}


def _terminal_events_for_conditions(core, conditions):
    events = []
    for condition in conditions:
        event_id = CONDITION_EVENT_IDS.get(condition)
        if event_id is not None:
            events.append(
                core.StageEvent(
                    event_ordinal=len(events) + 1,
                    event_type=TERMINAL_EVENT_TYPES.get(event_id, "validator"),
                    stage_or_event_id=event_id,
                    applicability="applicable",
                    result="failed",
                    policy_identity_if_applicable=TEST_POLICY_IDENTITY,
                )
            )
    return core.AttemptStageEventLedger(tuple(events))


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(case, id=case["id"])
        for case in SPEC["first_terminal_condition_test_vectors"]["cases"]
    ],
)
def test_first_terminal_condition_vectors(case):
    core = _core()
    if case["id"] == "P8":
        presemantic = "provider_native_refusal"
        ledger = core.AttemptStageEventLedger(
            (
                core.StageEvent(
                    event_ordinal=1,
                    event_type="normalized_presemantic_state",
                    stage_or_event_id=presemantic,
                    applicability="applicable",
                    result="failed",
                    policy_identity_if_applicable=TEST_POLICY_IDENTITY,
                    adapter_identity_if_applicable=TEST_ADAPTER_IDENTITY,
                ),
            )
        )
    else:
        presemantic = "ordinary_semantic_path"
        ledger = _terminal_events_for_conditions(core, case["ordered_conditions"])

    assert (
        core.reduce_first_terminal_condition(presemantic, ledger)
        == case["expected_terminal_outcome"]
    )


def test_first_terminal_condition_is_immutable_and_ordinal():
    core = _core()
    first = core.StageEvent(
        event_ordinal=1,
        event_type="validator",
        stage_or_event_id="canonical_schema_validation_failed",
        applicability="applicable",
        result="failed",
        policy_identity_if_applicable=TEST_POLICY_IDENTITY,
    )
    later = core.StageEvent(
        event_ordinal=2,
        event_type="validator",
        stage_or_event_id="text_cross_field_validator_failed",
        applicability="applicable",
        result="failed",
        policy_identity_if_applicable=TEST_POLICY_IDENTITY,
    )
    ledger = core.AttemptStageEventLedger((first, later))

    assert (
        core.reduce_first_terminal_condition("ordinary_semantic_path", ledger)
        == "failed_canonical_validation"
    )
    with pytest.raises(core.AttemptStateError, match="event_ordinal"):
        core.AttemptStageEventLedger((replace(first, event_ordinal=2),))


def test_major_stage_ledger_rejects_gaps_and_acceptance_before_later_work():
    core = _core()

    with pytest.raises(core.AttemptStateError, match="major_stage_progression"):
        core.derive_highest_completed_stage(
            ["raw_transport_captured", "canonical_candidate_constructed"]
        )

    state = _coherent_state(core)
    later = core.StageEvent(
        event_ordinal=len(state.ledger.events) + 1,
        event_type="validator",
        stage_or_event_id="text_cross_field_validator_failed",
        applicability="applicable",
        result="failed",
        policy_identity_if_applicable=TEST_POLICY_IDENTITY,
    )
    invalid = replace(
        state,
        ledger=core.AttemptStageEventLedger(state.ledger.events + (later,)),
    )
    with pytest.raises(core.AttemptStateCoherenceError, match="event_after_terminal"):
        core.validate_attempt_state(invalid)


def test_terminal_event_ids_require_their_frozen_event_types():
    core = _core()

    with pytest.raises(core.AttemptStateError, match="stage_or_event_id"):
        core.StageEvent(
            event_ordinal=1,
            event_type="validator",
            stage_or_event_id="all_required_processing_and_finalization_completed",
            applicability="applicable",
            result="completed",
            policy_identity_if_applicable=TEST_POLICY_IDENTITY,
        )


@pytest.mark.parametrize(
    ("event_type", "event_id", "result"),
    (
        ("validator", "provider_custom_validator", "completed"),
        ("validator", "provider_custom_validator", "failed"),
        ("normalization_action", "provider_custom_action", "completed"),
        ("tool_event", "provider_custom_tool_event", "failed"),
    ),
)
def test_stage_event_ids_are_closed(event_type, event_id, result):
    core = _core()

    with pytest.raises(core.AttemptStateError, match="stage_or_event_id"):
        core.StageEvent(
            event_ordinal=1,
            event_type=event_type,
            stage_or_event_id=event_id,
            applicability="applicable",
            result=result,
            policy_identity_if_applicable=TEST_POLICY_IDENTITY,
        )


@pytest.mark.parametrize(
    "identity",
    (
        None,
        ("", "v1", "1" * 64),
        ("wrong_policy", "v1", "1" * 64),
        ("test_policy_v1", "", "1" * 64),
        ("test_policy_v1", "v2", "1" * 64),
        ("test_policy_v1", "v1", "not-a-hash"),
        ("test_policy_v1", "v1"),
    ),
)
def test_stage_event_requires_complete_policy_identity(identity):
    core = _core()

    with pytest.raises(core.AttemptStateError, match="event_policy_identity"):
        core.StageEvent(
            event_ordinal=1,
            event_type="validator",
            stage_or_event_id="canonical_schema_validation",
            applicability="applicable",
            result="completed",
            policy_identity_if_applicable=identity,
        )


def test_stage_event_validates_adapter_identity_and_forbids_major_stage_identity():
    core = _core()

    with pytest.raises(core.AttemptStateError, match="event_adapter_identity"):
        core.StageEvent(
            event_ordinal=1,
            event_type="normalization_action",
            stage_or_event_id="unwrap_transport_envelope",
            applicability="applicable",
            result="completed",
            policy_identity_if_applicable=TEST_POLICY_IDENTITY,
            adapter_identity_if_applicable=("adapter", "v1", "bad-hash"),
        )
    with pytest.raises(core.AttemptStateError, match="unexpected_event_identity"):
        core.StageEvent(
            event_ordinal=1,
            event_type="major_stage",
            stage_or_event_id="raw_transport_captured",
            applicability="applicable",
            result="completed",
            policy_identity_if_applicable=TEST_POLICY_IDENTITY,
        )


def test_refusal_state_is_derived_from_outcome_and_frozen_presemantic_state():
    core = _core()

    assert core.derive_refusal_state(
        "provider_native_refusal", "provider_native_refusal"
    ) == (
        "provider_native_refusal"
    )
    assert core.derive_refusal_state(
        "provider_safety_block", "provider_safety_block"
    ) == (
        "provider_safety_block"
    )
    assert core.derive_refusal_state(
        "internal_harness_error", "provider_native_refusal"
    ) == "provider_native_refusal"
    assert core.derive_refusal_state(
        "internal_harness_error", "provider_safety_block"
    ) == "provider_safety_block"
    assert core.derive_refusal_state(
        "internal_harness_error", "ordinary_semantic_path"
    ) == "none"
    assert core.derive_refusal_state(
        "failed_strict_parse", "ordinary_semantic_path"
    ) == "none"

    with pytest.raises(core.AttemptStateError, match="refusal_state_context"):
        core.derive_refusal_state(
            "provider_native_refusal", "ordinary_semantic_path"
        )


def test_attempt_run_records_are_immutable_and_preflight_does_not_create_attempts():
    core = _core()
    run = core.AttemptRun()
    unchanged = run.record("provider_timeout", preflight_passed=False)
    first = run.record("failed_strict_parse")
    second = first.record("accepted")

    assert unchanged is run
    assert run.attempt_outcomes == ()
    assert first.attempt_outcomes == ("failed_strict_parse",)
    assert second.attempt_outcomes == ("failed_strict_parse", "accepted")
    assert first.attempt_outcomes == ("failed_strict_parse",)


def test_attempt_run_vectors():
    core = _core()
    vectors = SPEC["attempt_run_outcome_test_vectors"]["cases"]

    for case in vectors:
        if "attempt_outcomes" in case:
            run = core.AttemptRun()
            for outcome in case["attempt_outcomes"]:
                run = run.record(outcome)
            expected = case.get(
                "expected_immutable_attempt_record_count",
                len(case["attempt_outcomes"]),
            )
            assert len(run.attempt_outcomes) == expected
        elif case["id"] == "R4":
            run = core.AttemptRun().record("accepted", preflight_passed=False)
            assert len(run.attempt_outcomes) == 0
        elif case["id"] == "R5":
            timeout_run = core.AttemptRun().record("provider_timeout")
            assert len(timeout_run.attempt_outcomes) == 1
        elif case["id"] == "R6":
            assert not core.is_state_fragment_coherent(
                terminal_outcome="accepted",
                attempt_outcome="failed_strict_parse",
            )


TRIGGER_TO_STAGE = {
    "all_required_processing_and_finalization_completed": "accepted",
    "transport_extraction_failed": "raw_transport_captured",
    "strict_utf8_decode_failed": "semantic_representation_extracted",
    "duplicate_key_detected_in_syntactically_valid_json": (
        "semantic_representation_extracted"
    ),
    "strict_json_syntax_failed": "semantic_representation_extracted",
    "canonical_schema_validation_failed": "canonical_candidate_constructed",
    "text_cross_field_validator_failed": "canonical_schema_validated",
    "visual_photo_reference_validator_failed": "canonical_schema_validated",
    "retrieval_trace_reference_source_membership_failed": (
        "canonical_schema_validated"
    ),
    "search_cross_reference_validator_failed": "canonical_schema_validated",
    "source_classification_validation_failed": "canonical_schema_validated",
    "url_security_validation_failed": "semantic_representation_extracted",
    "evidence_trace_coherence_failed": "canonical_schema_validated",
    "retrieval_status_coherence_failed": "canonical_schema_validated",
    "evidence_policy_validation_failed": "canonical_schema_validated",
    "other_application_owned_invariant_failed": "canonical_schema_validated",
}

PRESEMANTIC_INPUT_STAGES = {
    "provider_connection_error": "none",
    "provider_timeout": "none",
    "provider_safety_block": "none",
    "provider_native_refusal": "none",
    "http_provider_error": "raw_transport_captured",
    "terminal_tool_error": "none",
    "terminal_tool_timeout": "none",
}

PERFORMED_ACTION_CASES = {"S2", "S22"}
FAILED_ACTION_CASES = {"S9"}


def _stage_prefix(core, highest):
    if highest is None or highest == "none":
        return []
    index = core.HIGHEST_COMPLETED_STAGES.index(highest)
    return list(core.HIGHEST_COMPLETED_STAGES[1 : index + 1])


def _ledger_for_status_vector(core, case):
    trigger = case["terminal_trigger"]
    if trigger == "normalized_presemantic_state":
        input_stage = PRESEMANTIC_INPUT_STAGES[case["normalized_presemantic_state"]]
    else:
        input_stage = TRIGGER_TO_STAGE[trigger]
    stages = _stage_prefix(core, input_stage)
    events = [
        core.StageEvent(
            event_ordinal=index,
            event_type="major_stage",
            stage_or_event_id=stage,
            applicability="applicable",
            result="completed",
        )
        for index, stage in enumerate(stages, start=1)
    ]
    if trigger == "normalized_presemantic_state":
        events.append(
            core.StageEvent(
                event_ordinal=len(events) + 1,
                event_type="normalized_presemantic_state",
                stage_or_event_id=case["normalized_presemantic_state"],
                applicability="applicable",
                result="failed",
                policy_identity_if_applicable=TEST_POLICY_IDENTITY,
                adapter_identity_if_applicable=TEST_ADAPTER_IDENTITY,
            )
        )
    else:
        events.append(
            core.StageEvent(
                event_ordinal=len(events) + 1,
                event_type=TERMINAL_EVENT_TYPES.get(trigger, "validator"),
                stage_or_event_id=trigger,
                applicability="applicable",
                result=(
                    "completed"
                    if trigger == "all_required_processing_and_finalization_completed"
                    else "failed"
                ),
                policy_identity_if_applicable=TEST_POLICY_IDENTITY,
            )
        )
    return core.AttemptStageEventLedger(tuple(events))


def _actions_for_status_vector(core, case):
    if case["id"] in PERFORMED_ACTION_CASES:
        return (_action_record(core, 1, "unwrap_transport_envelope", "completed"),)
    if case["id"] in FAILED_ACTION_CASES:
        return (_action_record(core, 1, "unwrap_transport_envelope", "failed"),)
    return ()


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(case, id=case["id"])
        for case in SPEC["attempt_status_compatibility_test_vectors"]["cases"]
        if "terminal_trigger" in case
    ],
)
def test_attempt_status_compatibility_vectors(case):
    core = _core()
    ledger = _ledger_for_status_vector(core, case)
    state = core.derive_attempt_state(
        workload_branch=case.get("workload_branch", "text_final"),
        normalized_presemantic_state=case["normalized_presemantic_state"],
        ledger=ledger,
        normalization_actions=_actions_for_status_vector(core, case),
        raw_provider_response_hash=(
            None
            if case["normalized_presemantic_state"]
            in {"provider_connection_error", "provider_timeout"}
            else "a" * 64
        ),
        accepted_artifact_hash=(
            "b" * 64 if case["expected_terminal_outcome"] == "accepted" else None
        ),
    )

    assert state.terminal_outcome == case["expected_terminal_outcome"]
    if "expected_highest_completed_stage" in case:
        assert state.highest_completed_stage == case[
            "expected_highest_completed_stage"
        ]
    if "expected_normalization_disposition" in case:
        assert state.normalization_disposition == case[
            "expected_normalization_disposition"
        ]
    if "expected_refusal_state" in case:
        assert state.refusal_state == case["expected_refusal_state"]
    if "expected_failed_validator" in case:
        records = {record.validator_id: record for record in state.validator_states}
        assert records[case["expected_failed_validator"]].state == "failed"
    assert core.validate_attempt_state(state) is None


def _coherent_state(core, branch="text_final"):
    case = {
        "terminal_trigger": "all_required_processing_and_finalization_completed",
        "normalized_presemantic_state": "ordinary_semantic_path",
        "expected_terminal_outcome": "accepted",
        "expected_highest_completed_stage": "accepted",
    }
    return core.derive_attempt_state(
        workload_branch=branch,
        normalized_presemantic_state="ordinary_semantic_path",
        ledger=_ledger_for_status_vector(core, case),
        normalization_actions=(),
        raw_provider_response_hash="a" * 64,
        accepted_artifact_hash="b" * 64,
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(case, id=case["id"])
        for case in SPEC["attempt_illegal_combination_test_vectors"]["cases"]
    ],
)
def test_illegal_attempt_combinations_are_rejected(case):
    core = _core()
    provided = case["provided_state"]
    branch = provided.get("workload_branch", "text_final")
    state = _coherent_state(core, branch)

    updates = {}
    for field in (
        "terminal_outcome",
        "highest_completed_stage",
        "normalization_disposition",
    ):
        if field in provided:
            updates[field] = provided[field]
    if "validator_states" in provided:
        replacements = provided["validator_states"]
        updates["validator_states"] = tuple(
            replace(record, state=replacements.get(record.validator_id, record.state))
            for record in state.validator_states
        )
    if case["id"] == "I5":
        failed_parse = core.StageEvent(
            event_ordinal=len(state.ledger.events) + 1,
            event_type="normalization_action",
            stage_or_event_id="strict_json_syntax_failed",
            applicability="applicable",
            result="failed",
            policy_identity_if_applicable=TEST_POLICY_IDENTITY,
        )
        updates["normalized_presemantic_state"] = "provider_native_refusal"
        updates["terminal_outcome"] = "provider_native_refusal"
        updates["attempt_outcome"] = "provider_native_refusal"
        updates["refusal_state"] = "provider_native_refusal"
        updates["failure_category"] = "provider_native_refusal"
        updates["accepted_artifact_hash"] = None
        updates["ledger"] = core.AttemptStageEventLedger(
            state.ledger.events + (failed_parse,)
        )
    if "terminal_outcome" in updates and "attempt_outcome" not in updates:
        updates["attempt_outcome"] = updates["terminal_outcome"]
        updates["failure_category"] = (
            None
            if updates["terminal_outcome"] == "accepted"
            else updates["terminal_outcome"]
        )
        if updates["terminal_outcome"] != "accepted":
            updates["accepted_artifact_hash"] = None
    invalid = replace(state, **updates)

    with pytest.raises(core.AttemptStateCoherenceError):
        core.validate_attempt_state(invalid)


def test_unknown_values_and_incomplete_validator_sets_fail_closed():
    core = _core()

    with pytest.raises(core.AttemptStateError, match="unknown_terminal_outcome"):
        core.AttemptRun().record("provider_extension_failure")
    with pytest.raises(core.AttemptStateError, match="unknown_workload_branch"):
        core.validator_applicability_for_branch("provider_custom")

    state = _coherent_state(core)
    with pytest.raises(core.AttemptStateCoherenceError, match="validator_inventory"):
        core.validate_attempt_state(
            replace(state, validator_states=state.validator_states[:-1])
        )


def test_derive_attempt_state_rejects_fabricated_action_summary():
    core = _core()
    case = {
        "id": "local-accepted",
        "terminal_trigger": "all_required_processing_and_finalization_completed",
        "normalized_presemantic_state": "ordinary_semantic_path",
    }

    with pytest.raises(core.AttemptStateError, match="normalization_action_log"):
        core.derive_attempt_state(
            workload_branch="text_final",
            normalized_presemantic_state="ordinary_semantic_path",
            ledger=_ledger_for_status_vector(core, case),
            normalization_actions=core.NormalizationActionSummary(),
            raw_provider_response_hash="a" * 64,
            accepted_artifact_hash="b" * 64,
        )


@pytest.mark.parametrize(
    ("event_type", "event_id"),
    (
        ("validator", "canonical_schema_validation"),
        ("normalization_action", "decode_strict_utf8"),
        ("major_stage", "raw_transport_captured"),
        (
            "acceptance_finalization",
            "all_required_processing_and_finalization_completed",
        ),
    ),
)
def test_processing_cannot_complete_after_presemantic_terminal(event_type, event_id):
    core = _core()
    terminal = core.StageEvent(
        event_ordinal=1,
        event_type="normalized_presemantic_state",
        stage_or_event_id="provider_safety_block",
        applicability="applicable",
        result="failed",
        policy_identity_if_applicable=TEST_POLICY_IDENTITY,
        adapter_identity_if_applicable=TEST_ADAPTER_IDENTITY,
    )
    later = core.StageEvent(
        event_ordinal=2,
        event_type=event_type,
        stage_or_event_id=event_id,
        applicability="applicable",
        result="completed",
        policy_identity_if_applicable=(
            None if event_type == "major_stage" else TEST_POLICY_IDENTITY
        ),
    )
    ledger = core.AttemptStageEventLedger((terminal, later))

    with pytest.raises(core.AttemptStateCoherenceError, match="event_after"):
        core.derive_attempt_state(
            workload_branch="text_final",
            normalized_presemantic_state="provider_safety_block",
            ledger=ledger,
            normalization_actions=(),
            raw_provider_response_hash=None,
            accepted_artifact_hash=None,
        )


def test_internal_failure_preserves_proven_validator_states():
    core = _core()
    stage_events = tuple(
        core.StageEvent(
            event_ordinal=index,
            event_type="major_stage",
            stage_or_event_id=stage,
            applicability="applicable",
            result="completed",
        )
        for index, stage in enumerate(
            core.HIGHEST_COMPLETED_STAGES[1:6],
            start=1,
        )
    )
    passed_schema = core.StageEvent(
        event_ordinal=6,
        event_type="validator",
        stage_or_event_id="canonical_schema_validation",
        applicability="applicable",
        result="completed",
        policy_identity_if_applicable=TEST_POLICY_IDENTITY,
    )
    passed_cross_field = core.StageEvent(
        event_ordinal=7,
        event_type="validator",
        stage_or_event_id="text_cross_field_validator_v1",
        applicability="applicable",
        result="completed",
        policy_identity_if_applicable=TEST_POLICY_IDENTITY,
    )
    internal_failure = core.StageEvent(
        event_ordinal=8,
        event_type="internal_invariant",
        stage_or_event_id="other_application_owned_invariant_failed",
        applicability="applicable",
        result="failed",
        policy_identity_if_applicable=TEST_POLICY_IDENTITY,
    )
    ledger = core.AttemptStageEventLedger(
        stage_events + (passed_schema, passed_cross_field, internal_failure)
    )
    state = core.derive_attempt_state(
        workload_branch="text_final",
        normalized_presemantic_state="ordinary_semantic_path",
        ledger=ledger,
        normalization_actions=(),
        raw_provider_response_hash="a" * 64,
        accepted_artifact_hash=None,
    )
    records = {record.validator_id: record.state for record in state.validator_states}

    assert records["canonical_schema_validation"] == "passed"
    assert records["text_cross_field_validator_v1"] == "passed"
    assert records["evidence_policy_validation"] == "not_run"


@pytest.mark.parametrize(
    ("presemantic_state", "expected_refusal"),
    (
        ("provider_safety_block", "provider_safety_block"),
        ("provider_native_refusal", "provider_native_refusal"),
    ),
)
def test_internal_finalization_failure_preserves_authoritative_refusal(
    presemantic_state, expected_refusal
):
    core = _core()
    terminal = core.StageEvent(
        event_ordinal=1,
        event_type="normalized_presemantic_state",
        stage_or_event_id=presemantic_state,
        applicability="applicable",
        result="failed",
        policy_identity_if_applicable=TEST_POLICY_IDENTITY,
        adapter_identity_if_applicable=TEST_ADAPTER_IDENTITY,
    )
    internal_failure = core.StageEvent(
        event_ordinal=2,
        event_type="internal_invariant",
        stage_or_event_id="attempt_state_coherence_failed",
        applicability="applicable",
        result="failed",
        policy_identity_if_applicable=TEST_POLICY_IDENTITY,
    )

    state = core.derive_attempt_state(
        workload_branch="text_final",
        normalized_presemantic_state=presemantic_state,
        ledger=core.AttemptStageEventLedger((terminal, internal_failure)),
        normalization_actions=(),
        raw_provider_response_hash=None,
        accepted_artifact_hash=None,
    )

    assert state.terminal_outcome == "internal_harness_error"
    assert state.refusal_state == expected_refusal
