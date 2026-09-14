"""Provider-free integration tests for the minimal Capstone pilot runner."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
import json
from pathlib import Path

import pytest

from app.services.evaluation_pilot_budget import (
    empty_pilot_budget_ledger,
    reconcile_pending_attempt_cost,
)
from app.services.evaluation_pilot_runner import (
    CREDENTIAL_VARIABLE_BY_PROVIDER,
    PILOT_RUNNER_STATUS,
    CredentialReference,
    LiveGateBinding,
    PilotRunnerError,
    SyntheticCredentialResolver,
    SyntheticPilotTransport,
    TransportResponse,
    _synthetic_provider_envelope,
    build_provider_free_pilot_runner,
)


ROOT = Path(__file__).resolve().parents[2]
CANARY = "synthetic-secret-canary-MUST-NEVER-LEAK"


@pytest.fixture(scope="module")
def runner():
    return build_provider_free_pilot_runner(
        repository_root=ROOT,
        repository_harness_commit_sha="a9a986e8a36952f9c12c7438f605d658fce17a73",
    )


def _gate(runner):
    return LiveGateBinding.synthetic_for_tests(
        evaluation_id=runner.evaluation_id,
        experiment_version=runner.experiment_version,
        request_configuration_set_hash=runner.request_configuration_set_hash,
        budget_control_hash=runner.budget_control_hash,
        region_binding_hash=runner.region_binding_hash,
        valid_on_date="2026-08-31",
        credential_references=runner.credential_references,
    )


def _resolver():
    return SyntheticCredentialResolver(
        {
            "OPENAI_API_KEY": CANARY,
            "GEMINI_API_KEY": CANARY,
            "GROQ_API_KEY": CANARY,
        }
    )


def _live_gate(runner):
    return LiveGateBinding._verified_live(
        evaluation_id=runner.evaluation_id,
        experiment_version=runner.experiment_version,
        request_configuration_set_hash=runner.request_configuration_set_hash,
        budget_control_hash=runner.budget_control_hash,
        region_binding_hash=runner.region_binding_hash,
        valid_on_date="2026-09-01",
        credential_references=tuple(
            CredentialReference(
                provider,
                variable,
                "externally_confirmed_for_live_pilot",
            )
            for provider, variable in CREDENTIAL_VARIABLE_BY_PROVIDER.items()
        ),
        repository_harness_commit_sha=runner.repository_harness_commit_sha,
        same_day_certification_hash="a" * 64,
        pilot_authorization_hash="b" * 64,
        authorized_call_ids=tuple(call.call_id for call in runner.plan.provider_calls),
        authorization_scope="full_authorized_pilot",
    )


class _UsageCompletingTransport:
    def __init__(self, **synthetic_options):
        self.inner = SyntheticPilotTransport(**synthetic_options)

    @property
    def invocation_count(self):
        return self.inner.invocation_count

    def invoke(self, request, credential, deadline):
        response = self.inner.invoke(request, credential, deadline)
        if response.status_code != 200 or not response.response_bytes:
            return response
        value = json.loads(response.response_bytes.decode("utf-8"))
        if request.call.provider == "OpenAI":
            value["usage"]["input_tokens_details"] = {
                "cached_tokens": 0,
                "cache_write_tokens": 0,
            }
        elif request.call.provider == "Google Gemini":
            value["usage"]["total_cached_tokens"] = 0
        elif request.call.model == "openai/gpt-oss-120b":
            value["usage"]["prompt_tokens_details"] = {"cached_tokens": 0}
        return TransportResponse(
            status_code=response.status_code,
            response_bytes=json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
            elapsed_seconds=response.elapsed_seconds,
            failure_signal=response.failure_signal,
            safe_response_metadata=response.safe_response_metadata,
        )


def test_plan_is_derived_from_frozen_eligible_matrix_and_pf1_stays_no_call(runner):
    plan = runner.plan

    assert PILOT_RUNNER_STATUS == "pilot_runner_ready_awaiting_live_gates"
    assert len(plan.logical_runs) == 21
    assert len(plan.provider_calls) == 22
    assert plan.maximum_real_physical_attempts == 44
    assert plan.pf1_no_call_count == 1
    assert plan.breakdown_by_workload == {
        "text_analysis": 10,
        "visual_inspection": 8,
        "openai_url_discovery": 2,
        "openai_search_synthesis": 2,
    }
    assert plan.breakdown_by_provider == {
        "OpenAI": 12,
        "Google Gemini": 4,
        "Groq": 6,
    }
    assert {
        (call.candidate_id, call.workload_stage)
        for call in plan.provider_calls
        if call.workload_stage == "provider_native_url_discovery"
    } == {
        ("openai_unified_premium_v1", "provider_native_url_discovery"),
        ("openai_unified_balanced_v1", "provider_native_url_discovery"),
    }
    assert all(
        call.workload_stage != "provider_native_url_discovery"
        for call in plan.provider_calls
        if call.provider != "OpenAI"
    )


def test_every_planned_call_has_complete_immutable_authoritative_bindings(runner):
    required = {
        "evaluation_id",
        "experiment_version",
        "fixture_id",
        "candidate_id",
        "provider",
        "model",
        "api_family",
        "workload_stage",
        "topology_id",
        "request_configuration_id",
        "request_configuration_hash",
        "prompt_ids",
        "prompt_hashes",
        "schema_id",
        "schema_hash",
        "role_mapping_id",
        "role_mapping_hash",
        "adapter_id",
        "adapter_hash",
        "retry_policy_id",
        "retry_policy_hash",
        "resource_policy_id",
        "resource_policy_hash",
        "privacy_policy_id",
        "privacy_policy_hash",
        "budget_policy_id",
        "budget_policy_hash",
        "region_binding_id",
        "region_binding_hash",
        "result_record_policy_id",
        "result_record_policy_hash",
        "run_number",
    }
    for call in runner.plan.provider_calls:
        projection = call.safe_projection()
        assert set(projection) == required
        assert call.maximum_physical_attempts == 2
        assert call.timeout_seconds == 120
        with pytest.raises(FrozenInstanceError):
            call.model = "application-default-must-not-win"


def test_request_payloads_match_all_nine_eligible_provider_topologies(runner):
    snapshots = runner.request_payload_snapshots()

    assert tuple(snapshots) == (
        "openai_text",
        "openai_visual",
        "openai_url_discovery",
        "openai_search_synthesis",
        "gemini_text",
        "gemini_visual",
        "groq_gpt_oss_text",
        "groq_qwen_visual",
        "groq_baseline_text",
    )
    assert snapshots["openai_text"]["native_surfaces"] == (
        "instructions",
        "input user message input_text",
    )
    assert snapshots["openai_visual"]["media_surface"] == "input_image"
    assert snapshots["openai_url_discovery"]["tool_type"] == "web_search"
    assert snapshots["openai_search_synthesis"]["segment_authorities"] == (
        "authoritative_instruction",
        "untrusted_input",
        "untrusted_retrieved_evidence",
    )
    assert snapshots["gemini_text"]["native_surfaces"][0] == "system_instruction"
    assert snapshots["gemini_visual"]["media_surface"] == "image"
    assert snapshots["groq_gpt_oss_text"]["structured_output"] == "json_schema_strict"
    assert snapshots["groq_qwen_visual"]["structured_output"] == "json_schema_best_effort"
    assert snapshots["groq_baseline_text"]["structured_output"] == "json_object"
    serialized = json.dumps(snapshots, sort_keys=True)
    assert CANARY not in serialized
    assert "Authorization" not in serialized
    assert "OPENAI_MODEL" not in serialized
    assert "GEMINI_MODEL" not in serialized
    assert "GROQ_MODEL" not in serialized


def test_frozen_models_not_application_defaults_are_selected(runner):
    models = {(call.candidate_id, call.model) for call in runner.plan.provider_calls}

    assert ("openai_unified_premium_v1", "gpt-5.6-sol") in models
    assert ("openai_unified_balanced_v1", "gpt-5.6-terra") in models
    assert ("gemini_unified_v1", "gemini-3.7-flash") in models
    assert ("groq_split_v1", "openai/gpt-oss-120b") in models
    assert ("groq_split_v1", "qwen/qwen3.8-27b") in models
    module_source = (
        ROOT / "backend/app/services/evaluation_pilot_runner.py"
    ).read_text(encoding="utf-8")
    assert "AI_PROVIDER" not in module_source
    assert "OPENAI_MODEL" not in module_source
    assert "GEMINI_MODEL" not in module_source
    assert "GROQ_MODEL" not in module_source


@pytest.mark.parametrize(
    "mutation",
    (
        {"common_preflight_status": "blocked"},
        {"same_day_certification_status": "pending"},
        {"credential_authorization_status": "pending"},
        {"explicit_pilot_authorization_status": "pending"},
        {"evaluation_id": "wrong-evaluation"},
        {"experiment_version": "wrong-version"},
        {"valid_on_date": "2026-08-30"},
        {"request_configuration_set_hash": "0" * 64},
        {"budget_control_hash": "0" * 64},
        {"region_binding_hash": "0" * 64},
    ),
)
def test_missing_forged_or_stale_live_gate_blocks_before_credential_and_transport(
    runner, mutation
):
    resolver = _resolver()
    transport = SyntheticPilotTransport()

    with pytest.raises(PilotRunnerError, match="live_gate_factory_required"):
        replace(_gate(runner), **mutation)

    assert resolver.resolution_count == 0
    assert transport.invocation_count == 0


def test_budget_is_reserved_before_credential_resolution_or_transport(runner):
    resolver = _resolver()
    transport = SyntheticPilotTransport()

    with pytest.raises(PilotRunnerError, match="pilot_budget_ceiling_exhausted"):
        runner.execute_one(
            runner.plan.provider_calls[0],
            gate=_gate(runner),
            credential_resolver=resolver,
            transport=transport,
            budget_ledger=empty_pilot_budget_ledger(),
            conservative_reservation_usd="5.01",
            synthetic_today="2026-08-31",
        )

    assert resolver.resolution_count == 0
    assert transport.invocation_count == 0


@pytest.mark.parametrize("invalid", (None, "unknown", "NaN", "Infinity", "-1"))
def test_unknown_or_malformed_reservation_fails_closed_before_transport(runner, invalid):
    resolver = _resolver()
    transport = SyntheticPilotTransport()

    with pytest.raises(PilotRunnerError, match="budget_reservation"):
        runner.execute_one(
            runner.plan.provider_calls[0],
            gate=_gate(runner),
            credential_resolver=resolver,
            transport=transport,
            budget_ledger=empty_pilot_budget_ledger(),
            conservative_reservation_usd=invalid,
            synthetic_today="2026-08-31",
        )

    assert resolver.resolution_count == 0
    assert transport.invocation_count == 0


def test_credential_reference_names_are_exact_and_values_are_never_serialized(runner):
    assert CREDENTIAL_VARIABLE_BY_PROVIDER == {
        "OpenAI": "OPENAI_API_KEY",
        "Google Gemini": "GEMINI_API_KEY",
        "Groq": "GROQ_API_KEY",
    }
    resolver = _resolver()
    transport = SyntheticPilotTransport()
    outcome = runner.execute_one(
        runner.plan.provider_calls[0],
        gate=_gate(runner),
        credential_resolver=resolver,
        transport=transport,
        budget_ledger=empty_pilot_budget_ledger(),
        conservative_reservation_usd="0.01",
        synthetic_today="2026-08-31",
    )

    exposed = json.dumps(outcome.safe_projection(), sort_keys=True)
    restricted = repr(outcome.record.restricted_provider_data.as_dict())
    assert resolver.requested_environment_variable_names == ("OPENAI_API_KEY",)
    assert transport.credential_boundary_matches == (True,)
    for surface in (exposed, restricted, repr(outcome), repr(resolver), repr(transport)):
        assert CANARY not in surface
    assert "OPENAI_API_KEY" in exposed
    assert outcome.real_provider_calls == 0
    assert outcome.synthetic_provider_attempts == 1


def test_response_cannot_replace_frozen_pre_attempt_selection(runner):
    call = runner.plan.provider_calls[0]
    transport = SyntheticPilotTransport(
        semantic_overrides={
            call.call_id: {
                "model": "attacker-selected-model",
                "request_configuration_hash": "0" * 64,
            }
        }
    )
    resolver = _resolver()

    outcome = runner.execute_one(
        call,
        gate=_gate(runner),
        credential_resolver=resolver,
        transport=transport,
        budget_ledger=empty_pilot_budget_ledger(),
        conservative_reservation_usd="0.01",
        synthetic_today="2026-08-31",
    )

    assert outcome.accepted is False
    assert outcome.safe_failure_code == "failed_canonical_validation"
    assert outcome.call.model == call.model
    assert outcome.call.request_configuration_hash == call.request_configuration_hash


@pytest.mark.parametrize(
    "field",
    (
        "provider",
        "model",
        "api_family",
        "request_configuration_hash",
        "adapter_hash",
        "role_mapping_hash",
        "prompt_hashes",
        "schema_hash",
        "resource_policy_hash",
        "privacy_policy_hash",
        "retry_policy_hash",
        "budget_policy_hash",
        "fixture_version",
        "topology_id",
        "region_binding_hash",
    ),
)
def test_any_pre_attempt_identity_mutation_blocks_before_credential_or_transport(
    runner, field
):
    call = runner.plan.provider_calls[0]
    replacement = ("0" * 64,) if field == "prompt_hashes" else "mutated"
    if field.endswith("_hash"):
        replacement = "0" * 64
    mutated = replace(call, **{field: replacement})
    resolver = _resolver()
    transport = SyntheticPilotTransport()

    with pytest.raises(PilotRunnerError, match="pre_attempt_identity"):
        runner.execute_one(
            mutated,
            gate=_gate(runner),
            credential_resolver=resolver,
            transport=transport,
            budget_ledger=empty_pilot_budget_ledger(),
            conservative_reservation_usd="0.01",
            synthetic_today="2026-08-31",
        )

    assert resolver.resolution_count == 0
    assert transport.invocation_count == 0


def test_third_physical_attempt_is_impossible_before_any_side_effect(runner):
    resolver = _resolver()
    transport = SyntheticPilotTransport()

    with pytest.raises(PilotRunnerError, match="attempt_number"):
        runner.execute_one(
            runner.plan.provider_calls[0],
            gate=_gate(runner),
            credential_resolver=resolver,
            transport=transport,
            budget_ledger=empty_pilot_budget_ledger(),
            conservative_reservation_usd="0.01",
            synthetic_today="2026-08-31",
            attempt_number=3,
            retry_reason="provider_attempt_timeout",
        )

    assert resolver.resolution_count == 0
    assert transport.invocation_count == 0


def test_timeout_ignores_late_result_and_retries_once_with_new_record_and_budget(runner):
    call = runner.plan.provider_calls[0]
    transport = SyntheticPilotTransport(timeout_once_call_ids={call.call_id})
    result = runner.execute_logical_run(
        runner.logical_run_for_call(call.call_id),
        gate=_gate(runner),
        credential_resolver=_resolver(),
        transport=transport,
        budget_ledger=empty_pilot_budget_ledger(),
        conservative_reservation_usd="0.01",
        synthetic_today="2026-08-31",
    )

    assert result.accepted is True
    assert [item.safe_failure_code for item in result.attempts] == [
        "provider_timeout",
        None,
    ]
    assert [item.record.key.attempt_number for item in result.attempts] == [1, 2]
    assert result.attempts[1].record.as_dict()["pilot_envelope"]["retry_reason"] == (
        "provider_attempt_timeout"
    )
    assert len(result.budget_ledger.completed_attempts) == 2
    assert transport.invocation_count == 2


@pytest.mark.parametrize(
    ("signal", "expected_failure", "retryable"),
    (
        ("connection", "provider_connection_error", True),
        ("timeout", "provider_timeout", True),
        ("rate_limit", "http_provider_error", True),
        ("service_unavailable", "http_provider_error", True),
        ("http_failure", "http_provider_error", False),
        ("malformed", "failed_transport_extraction", False),
        ("schema_failure", "failed_canonical_validation", False),
    ),
)
def test_closed_transport_failure_mapping_and_retry_scope(
    runner, signal, expected_failure, retryable
):
    call = runner.plan.provider_calls[0]
    transport = SyntheticPilotTransport(failure_once={call.call_id: signal})
    result = runner.execute_logical_run(
        runner.logical_run_for_call(call.call_id),
        gate=_gate(runner),
        credential_resolver=_resolver(),
        transport=transport,
        budget_ledger=empty_pilot_budget_ledger(),
        conservative_reservation_usd="0.01",
        synthetic_today="2026-08-31",
    )

    assert result.attempts[0].safe_failure_code == expected_failure
    assert len(result.attempts) == (2 if retryable else 1)
    assert transport.invocation_count == (2 if retryable else 1)


@pytest.mark.parametrize(
    ("signal", "failure_code"),
    (
        ("connection", "provider_connection_error"),
        ("timeout", "provider_timeout"),
        ("rate_limit", "http_provider_error"),
        ("service_unavailable", "http_provider_error"),
        ("http_failure", "http_provider_error"),
    ),
)
def test_live_invocation_without_authoritative_usage_is_pending_not_zero_and_no_retry(
    runner, signal, failure_code
):
    call = runner.plan.provider_calls[0]
    transport = SyntheticPilotTransport(failure_once={call.call_id: signal})
    result = runner.execute_logical_run(
        runner.logical_run_for_call(call.call_id),
        gate=_live_gate(runner),
        credential_resolver=_resolver(),
        transport=transport,
        budget_ledger=empty_pilot_budget_ledger(),
        conservative_reservation_usd="0.50",
        synthetic_today="2026-09-01",
    )

    assert result.accepted is False
    assert len(result.attempts) == 1
    assert transport.invocation_count == 1
    attempt = result.attempts[0]
    assert attempt.safe_failure_code == failure_code
    assert attempt.billing_state == "pending_cost_reconciliation"
    assert attempt.budget_ledger.committed_cost_usd == Decimal("0.00")
    assert attempt.budget_ledger.pending_encumbered_cost_usd == Decimal("0.50")
    assert attempt.budget_ledger.provider_calls_completed == 1
    assert attempt.budget_ledger.pending_attempts[0].actual_cost_usd is None
    envelope = attempt.record.as_dict()["pilot_envelope"]
    assert envelope["estimated_cost"] is None
    assert envelope["notes_and_anomalies"] == ["pending_cost_reconciliation"]
    assert attempt.record.as_dict()["normalization_audit"]["terminal_outcome"] == (
        failure_code
    )


@pytest.mark.parametrize(
    ("failure_once", "semantic_overrides", "expected_failure"),
    (
        ({"SIGNAL": "schema_failure"}, None, "failed_canonical_validation"),
        (None, {"recommendation": "avoid"}, "failed_cross_field_validation"),
    ),
)
def test_live_exact_usage_survives_later_schema_or_semantic_failure(
    runner, failure_once, semantic_overrides, expected_failure
):
    call = runner.plan.provider_calls[0]
    options = {}
    if failure_once:
        options["failure_once"] = {call.call_id: failure_once["SIGNAL"]}
    if semantic_overrides:
        options["semantic_overrides"] = {call.call_id: semantic_overrides}
    transport = _UsageCompletingTransport(**options)

    outcome = runner.execute_one(
        call,
        gate=_live_gate(runner),
        credential_resolver=_resolver(),
        transport=transport,
        budget_ledger=empty_pilot_budget_ledger(),
        conservative_reservation_usd="0.50",
        synthetic_today="2026-09-01",
    )

    assert outcome.accepted is False
    assert outcome.safe_failure_code == expected_failure
    assert outcome.billing_state == "exact_actual_cost_committed"
    assert outcome.budget_ledger.pending_attempts == ()
    assert outcome.budget_ledger.committed_cost_usd > Decimal("0.00")
    exact = outcome.record.as_dict()["pilot_envelope"]["estimated_cost"]
    assert exact is not None
    assert Decimal(exact["total_usd"]) == outcome.budget_ledger.committed_cost_usd


def test_pending_cost_blocks_another_candidate_before_credential_or_transport(runner):
    first = runner.plan.provider_calls[0]
    failed = runner.execute_one(
        first,
        gate=_live_gate(runner),
        credential_resolver=_resolver(),
        transport=SyntheticPilotTransport(
            failure_once={first.call_id: "connection"}
        ),
        budget_ledger=empty_pilot_budget_ledger(),
        conservative_reservation_usd="0.50",
        synthetic_today="2026-09-01",
    )
    other = next(
        call for call in runner.plan.provider_calls
        if call.candidate_id != first.candidate_id
    )
    resolver = _resolver()
    transport = SyntheticPilotTransport()

    with pytest.raises(PilotRunnerError, match="pending_cost_reconciliation"):
        runner.execute_one(
            other,
            gate=_live_gate(runner),
            credential_resolver=resolver,
            transport=transport,
            budget_ledger=failed.budget_ledger,
            conservative_reservation_usd="0.01",
            synthetic_today="2026-09-01",
        )

    assert resolver.resolution_count == 0
    assert transport.invocation_count == 0


def test_authoritative_reconciliation_can_unblock_existing_retry_policy(runner):
    call = runner.plan.provider_calls[0]
    first = runner.execute_one(
        call,
        gate=_live_gate(runner),
        credential_resolver=_resolver(),
        transport=SyntheticPilotTransport(
            failure_once={call.call_id: "connection"}
        ),
        budget_ledger=empty_pilot_budget_ledger(),
        conservative_reservation_usd="0.50",
        synthetic_today="2026-09-01",
    )
    pending_attempt_id = first.budget_ledger.unresolved_pending_attempt_ids[0]
    reconciled = reconcile_pending_attempt_cost(
        first.budget_ledger,
        reconciliation_id="reconciliation-0001",
        attempt_id=pending_attempt_id,
        actual_cost_usd="0.01",
        authoritative_evidence_type="provider_billing_record",
        authoritative_evidence_reference="c" * 64,
        reconciled_at="2026-09-01T20:00:00Z",
    )

    retry = runner.execute_one(
        call,
        gate=_live_gate(runner),
        credential_resolver=_resolver(),
        transport=_UsageCompletingTransport(),
        budget_ledger=reconciled,
        conservative_reservation_usd="0.50",
        synthetic_today="2026-09-01",
        attempt_number=2,
        retry_reason=first.retry_reason,
    )

    assert retry.accepted is True
    assert retry.billing_state == "exact_actual_cost_committed"
    assert retry.budget_ledger.unresolved_pending_attempt_ids == ()
    assert retry.budget_ledger.provider_calls_completed == 2
    assert retry.budget_ledger.committed_cost_usd > Decimal("0.01")


def test_full_live_mock_stops_globally_after_first_pending_cost(runner):
    first = runner.plan.provider_calls[0]
    transport = SyntheticPilotTransport(
        failure_once={first.call_id: "connection"}
    )

    summary = runner.run_complete_synthetic_pilot(
        gate=_live_gate(runner),
        credential_resolver=_resolver(),
        transport=transport,
        conservative_reservation_usd="0.50",
        synthetic_today="2026-09-01",
    )

    assert summary.status == "blocked_pending_cost_reconciliation"
    assert summary.completed_logical_runs == 0
    assert summary.failed_logical_runs == 1
    assert summary.blocked_logical_runs == 20
    assert summary.synthetic_physical_attempts == 1
    assert transport.invocation_count == 1
    assert summary.budget_ledger.pending_encumbered_cost_usd == Decimal("0.50")
    assert summary.budget_ledger.provider_calls_completed == 1


def test_pending_safe_projection_contains_only_safe_reference_not_diagnostics(runner):
    call = runner.plan.provider_calls[0]
    outcome = runner.execute_one(
        call,
        gate=_live_gate(runner),
        credential_resolver=_resolver(),
        transport=SyntheticPilotTransport(
            failure_once={call.call_id: "service_unavailable"}
        ),
        budget_ledger=empty_pilot_budget_ledger(),
        conservative_reservation_usd="0.50",
        synthetic_today="2026-09-01",
    )
    exposed = json.dumps(outcome.safe_projection(), sort_keys=True)

    assert outcome.billing_state == "pending_cost_reconciliation"
    assert len(outcome.pending_cost_reference) == 64
    assert outcome.pending_cost_reference in exposed
    assert "provider diagnostic prose" not in exposed
    assert "raw_response" not in exposed
    assert CANARY not in exposed


def test_text_refusal_and_malformed_output_are_safe_nonaccepted_records(runner):
    text_call = next(
        call for call in runner.plan.provider_calls
        if call.workload_stage == "text_analysis"
    )
    for signal, expected in (
        ("refusal", "provider_native_refusal"),
        ("malformed", "failed_transport_extraction"),
    ):
        outcome = runner.execute_one(
            text_call,
            gate=_gate(runner),
            credential_resolver=_resolver(),
            transport=SyntheticPilotTransport(
                failure_once={text_call.call_id: signal}
            ),
            budget_ledger=empty_pilot_budget_ledger(),
            conservative_reservation_usd="0.01",
            synthetic_today="2026-08-31",
        )
        assert outcome.accepted is False
        assert outcome.safe_failure_code == expected
        assert outcome.record.as_dict()["ordinary_projection"]["failure_category"] == expected


@pytest.mark.parametrize(
    "urls",
    (
        (),
        ("https://private.example.test/account?token=secret",),
        (
            "https://www.logitech.com/en-us/shop/p/mx-master-3s.910-006557",
            "https://example.test/second-result",
        ),
    ),
)
def test_ps1_discovery_failures_stop_before_synthesis_without_fabricating_evidence(
    runner, urls
):
    discovery = next(
        call
        for call in runner.plan.provider_calls
        if call.workload_stage == "provider_native_url_discovery"
    )
    logical = runner.logical_run_for_call(discovery.call_id)
    transport = SyntheticPilotTransport(
        discovery_urls_by_call={discovery.call_id: urls}
    )

    result = runner.execute_logical_run(
        logical,
        gate=_gate(runner),
        credential_resolver=_resolver(),
        transport=transport,
        budget_ledger=empty_pilot_budget_ledger(),
        conservative_reservation_usd="0.01",
        synthetic_today="2026-08-31",
    )

    assert result.accepted is False
    assert len(result.attempts) == 1
    assert result.attempts[0].safe_failure_code == "failed_transport_extraction"
    record = result.attempts[0].record.as_dict()
    assert record["normalization_audit"][
        "canonical_evidence_bundle_hash_if_applicable"
    ] is None
    assert record["pilot_envelope"]["search_and_tool_calls"] is None
    assert transport.invocation_count == 1


def test_duplicate_ps1_url_is_deterministically_deduplicated_and_bound(runner):
    discovery = next(
        call
        for call in runner.plan.provider_calls
        if call.workload_stage == "provider_native_url_discovery"
    )
    logical = runner.logical_run_for_call(discovery.call_id)
    transport = SyntheticPilotTransport(
        discovery_urls_by_call={
            discovery.call_id: (
                "https://www.logitech.com/en-us/shop/p/mx-master-3s.910-006557",
                "https://www.logitech.com/en-us/shop/p/mx-master-3s.910-006557",
            )
        }
    )

    result = runner.execute_logical_run(
        logical,
        gate=_gate(runner),
        credential_resolver=_resolver(),
        transport=transport,
        budget_ledger=empty_pilot_budget_ledger(),
        conservative_reservation_usd="0.01",
        synthetic_today="2026-08-31",
    )

    assert result.accepted is True
    assert len(result.attempts) == 2
    assert transport.invocation_count == 2


def test_complete_synthetic_pilot_exercises_real_pipeline_without_live_execution(runner):
    retry_call = next(
        call for call in runner.plan.provider_calls
        if call.fixture_id == "PT2" and call.candidate_id == "openai_unified_premium_v1"
    )
    resolver = _resolver()
    transport = SyntheticPilotTransport(timeout_once_call_ids={retry_call.call_id})

    summary = runner.run_complete_synthetic_pilot(
        gate=_gate(runner),
        credential_resolver=resolver,
        transport=transport,
        conservative_reservation_usd="0.01",
        synthetic_today="2026-08-31",
    )

    assert summary.status == "synthetic_pilot_complete"
    assert summary.logical_runs == 21
    assert summary.completed_logical_runs == 21
    assert summary.failed_logical_runs == 0
    assert summary.blocked_logical_runs == 0
    assert summary.synthetic_physical_attempts == 23
    assert summary.real_provider_calls == 0
    assert summary.pilot_calls_completed == 0
    assert summary.scored_calls_completed == 0
    assert summary.pf1_no_call_executions == 1
    assert summary.application_refetches == 2
    assert summary.text_attempts == 11
    assert summary.visual_attempts == 8
    assert summary.discovery_attempts == 2
    assert summary.search_synthesis_attempts == 2
    assert len(summary.run_bundle.attempts) == 23
    assert len(summary.budget_ledger.completed_attempts) == 23
    assert summary.budget_ledger.committed_cost_usd == Decimal("0")
    assert summary.budget_ledger.remaining_unreserved_usd == Decimal("5.00")
    assert resolver.resolution_count == 23
    assert transport.invocation_count == 23
    assert summary.all_records_validate is True
    assert summary.all_stage_identities_bound is True
    assert summary.privacy_checks_passed is True
    assert summary.network_calls == 0
    assert summary.real_credentials_used is False
    assert summary.winner_selected is False
    assert summary.execution_state == "blocked_pre_execution"
    assert summary.synthetic_mode is True


def test_full_dry_run_contains_accepted_text_visual_and_complete_ps1_records(runner):
    summary = runner.run_complete_synthetic_pilot(
        gate=_gate(runner),
        credential_resolver=_resolver(),
        transport=SyntheticPilotTransport(),
        conservative_reservation_usd="0.01",
        synthetic_today="2026-08-31",
    )
    records = [record.as_dict() for record in summary.run_bundle.attempts]

    assert any(
        item["attempt_key"]["workload"] == "text_risk_analysis"
        and item["normalization_audit"]["terminal_outcome"] == "accepted"
        for item in records
    )
    assert any(
        item["attempt_key"]["workload"] == "visual_inspection"
        and item["pilot_envelope"]["visual_asset_hashes"]
        for item in records
    )
    ps1 = [
        item for item in records
        if item["attempt_key"]["workload"] == "grounded_product_price_research"
    ]
    assert len(ps1) == 4
    assert all(item["pilot_envelope"]["search_and_tool_calls"] for item in ps1)
    assert all(item["pilot_envelope"]["source_urls"] for item in ps1)
    assert all(
        item["normalization_audit"]["canonical_evidence_bundle_hash_if_applicable"]
        or item["normalization_audit"]["final_semantic_payload_hash_if_applicable"]
        for item in ps1
    )


def test_pf1_never_resolves_credentials_reserves_budget_or_invokes_transport(runner):
    resolver = _resolver()
    transport = SyntheticPilotTransport()
    result = runner.execute_pf1()

    assert result.fixture_id == "PF1"
    assert result.status == "provider_free_safe_failure_captured"
    assert result.external_provider_call_required is False
    assert result.synthetic_physical_attempts == 0
    assert result.cost_usd == Decimal("0")
    assert resolver.resolution_count == 0
    assert transport.invocation_count == 0


def test_default_runner_never_self_authorizes_and_readiness_stays_live_gate_blocked(runner):
    readiness = runner.readiness_projection()

    assert readiness == {
        "status": "pilot_runner_ready_awaiting_live_gates",
        "common_preflight": "ready",
        "same_day_certification": "pending",
        "credential_provisioning_and_authorization": "pending",
        "explicit_pilot_authorization": "pending",
        "provider_calls_allowed": False,
        "pilot_calls_allowed": False,
        "scored_calls_allowed": False,
        "provider_calls_completed": 0,
        "pilot_calls_completed": 0,
        "scored_calls_completed": 0,
        "winner_selected": False,
    }
    with pytest.raises(TypeError):
        runner.execute_one(runner.plan.provider_calls[0])


def test_runner_and_all_artifacts_are_credential_free(runner):
    summary = runner.run_complete_synthetic_pilot(
        gate=_gate(runner),
        credential_resolver=_resolver(),
        transport=SyntheticPilotTransport(),
        conservative_reservation_usd="0.01",
        synthetic_today="2026-08-31",
    )
    serialized = json.dumps(summary.safe_projection(), sort_keys=True)
    serialized_records = json.dumps(
        [record.as_dict() for record in summary.run_bundle.attempts], sort_keys=True
    )

    assert CANARY not in serialized
    assert CANARY not in serialized_records
    assert "Authorization" not in serialized_records
    assert "Bearer" not in serialized_records
    assert not any(
        CANARY.encode() in record.ordinary_json
        or CANARY.encode() in (record.restricted_provider_data.raw_provider_response or b"")
        for record in summary.run_bundle.attempts
    )
