"""Provider-free aggregation tests for the pilot preflight checkpoint."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.services.evaluation_pilot_preflight import (
    PilotPreflightError,
    assess_provider_neutral_pilot_preflight,
)


def test_preflight_reports_exact_resolved_scope_and_remaining_gates():
    result = assess_provider_neutral_pilot_preflight()

    assert result.status == "pilot_preflight_ready_awaiting_live_gates"
    assert result.provider_free_common_preflight_ready is True
    assert result.ready_awaiting_only_human_and_live_gates is True
    assert result.resolved_components == (
        "frozen_methodology_and_fixtures",
        "prompt_and_output_contracts",
        "normalization_and_validation",
        "resource_limits",
        "retry_policy",
        "privacy_and_restricted_trace_handling",
        "provider_role_mappings_and_response_adapters",
        "pilot_request_configurations",
        "pilot_visual_assets_truth_and_context",
        "immutable_result_record_with_request_configuration_binding",
        "dated_official_pricing_schedules_and_explicit_cost_unknowns",
        "ps1_discovery_refetch_classification_extraction_and_support",
        "approved_us_operation_and_restricted_local_storage_binding",
        "same_day_lifecycle_and_pricing_checklist_prepared",
        "provider_native_url_discovery_and_application_refetch_linkage",
        "approved_five_dollar_budget_and_pre_attempt_reservation_enforcement",
    )
    assert result.provider_free_technical_blockers == ()
    assert result.pending_human_gates == (
        "pilot_credential_authorization_and_provisioning",
        "explicit_pilot_authorization",
    )
    assert result.pending_live_gates == (
        "same_day_provider_lifecycle_and_pricing_certification",
    )
    assert result.same_day_lifecycle_recheck_required is True
    assert result.provider_calls_allowed is False
    assert result.pilot_calls_allowed is False
    assert result.provider_calls_completed == 0
    assert result.pilot_calls_completed == 0
    assert result.scored_calls_completed == 0
    assert result.winner_selected is False


def test_preflight_separates_planned_discovery_from_configured_eligible_calls():
    result = assess_provider_neutral_pilot_preflight()

    assert result.configured_stage_matrix == (
        ("openai_unified_premium_v1", "text_analysis", 2),
        ("openai_unified_premium_v1", "search_synthesis", 1),
        ("openai_unified_premium_v1", "visual_inspection", 2),
        ("openai_unified_balanced_v1", "text_analysis", 2),
        ("openai_unified_balanced_v1", "search_synthesis", 1),
        ("openai_unified_balanced_v1", "visual_inspection", 2),
        ("gemini_unified_v1", "text_analysis", 2),
        ("gemini_unified_v1", "search_synthesis", 1),
        ("gemini_unified_v1", "visual_inspection", 2),
        ("groq_split_v1", "text_analysis", 2),
        ("groq_split_v1", "search_synthesis", 1),
        ("groq_split_v1", "visual_inspection", 2),
        ("baseline_current_text_v1", "text_analysis", 2),
    )
    assert result.planned_discovery_matrix == (
        ("openai_unified_premium_v1", "provider_native_url_discovery", 1),
        ("openai_unified_balanced_v1", "provider_native_url_discovery", 1),
        ("gemini_unified_v1", "provider_native_url_discovery", 1),
        ("groq_split_v1", "provider_native_url_discovery", 1),
    )
    assert result.eligible_discovery_matrix == (
        ("openai_unified_premium_v1", "provider_native_url_discovery", 1),
        ("openai_unified_balanced_v1", "provider_native_url_discovery", 1),
    )
    assert result.ineligible_stage_matrix == (
        ("gemini_unified_v1", "search_retrieval"),
        ("groq_split_v1", "search_retrieval"),
    )
    assert result.provider_calls_in_currently_configured_non_search_scope == 18
    assert result.configured_provider_calls == 22
    assert result.planned_provider_calls == 26
    assert result.maximum_configured_physical_attempts == 44
    assert result.maximum_planned_physical_attempts == 52
    assert result.currently_eligible_provider_calls == 22
    assert result.maximum_currently_eligible_physical_attempts == 44


def test_ps1_blockers_preserve_the_frozen_security_and_evidence_boundaries():
    result = assess_provider_neutral_pilot_preflight()

    assert result.ps1_provider_free_blockers == ()
    assert result.ps1_reusable_primitives == (
        "bounded_ssrf_safe_fetch_transport",
        "strict_url_security_and_redirect_auth_classification",
        "deterministic_retrieval_ordinals_source_ids_and_evidence_ids",
        "restricted_exact_trace_and_safe_ordinary_projection",
        "safe_search_tool_result_record",
    )
    assert result.ps1_built_in_search_evidence_eligible is False
    assert result.ps1_provider_native_url_discovery_capability_approved is True
    assert result.ps1_provider_native_url_discovery_configured_eligible is True
    assert result.ps1_trace_backed_application_evidence_ready is True
    assert result.ps1_security_contract_weakened is False


def test_preflight_binds_the_approved_region_without_claiming_provider_residency():
    result = assess_provider_neutral_pilot_preflight()

    assert result.operation_country_code == "US"
    assert result.provider_service_mode == "standard_global"
    assert result.restricted_storage_country_code == "US"
    assert result.cross_region_replication_allowed is False


def test_preflight_binds_exact_cost_envelope_without_fabricating_a_total():
    result = assess_provider_neutral_pilot_preflight()

    assert result.cost_envelope_hash == (
        "40899a9b6a8b94928bb52947da1f040699cbee7f7f13be0902c17a7db25b2942"
    )
    assert result.budget_control_hash == (
        "2a6d8fdfdd39efcf8ddc027734988a557d222885f736ddc60d8162dd059b7b23"
    )
    assert result.known_two_attempt_cost_subtotal_usd == "2.73434880"
    assert result.nominal_total_cost_usd is None
    assert result.conservative_maximum_total_cost_usd is None
    assert result.approved_budget_ceiling_usd == "5.00"
    assert result.budget_authorization_status == "approved_operator_ceiling"
    assert result.attempt_specific_budget_reservation_required is True
    assert result.budget_ceiling_is_execution_authority is False


def test_preflight_cross_checks_exact_candidate_models_and_pilot_fixtures():
    result = assess_provider_neutral_pilot_preflight()

    assert result.candidate_model_matrix == (
        ("openai_unified_premium_v1", ("gpt-5.6-sol",)),
        ("openai_unified_balanced_v1", ("gpt-5.6-terra",)),
        ("gemini_unified_v1", ("gemini-3.7-flash",)),
        (
            "groq_split_v1",
            ("openai/gpt-oss-120b", "groq/compound", "qwen/qwen3.8-27b"),
        ),
        ("baseline_current_text_v1", ("openai/gpt-oss-120b",)),
    )
    assert result.pilot_fixture_ids == ("PT1", "PT2", "PS1", "PV1", "PV2", "PF1")
    assert result.fixture_readiness == (
        ("PT1", "ready_awaiting_live_gates"),
        ("PT2", "ready_awaiting_live_gates"),
        ("PS1", "ready_for_openai_candidates_awaiting_live_gates"),
        ("PV1", "ready_awaiting_live_gates"),
        ("PV2", "ready_awaiting_live_gates"),
        ("PF1", "provider_free_ready_no_call"),
    )


def test_preflight_has_the_exact_same_day_operational_checklist():
    result = assess_provider_neutral_pilot_preflight()

    assert result.same_day_checklist == (
        "current_model_or_snapshot_availability_and_lifecycle",
        "api_endpoint_version_and_required_tool_availability",
        "announced_deprecation_or_shutdown_status",
        "required_schema_search_image_and_tool_combination_support",
        "official_pricing_schedule_and_current_rate_binding",
        "frozen_request_configuration_validity",
        "approved_standard_global_region_mode_compatibility",
        "attempt_specific_conservative_budget_reservation_and_remaining_ceiling",
        "provider_project_spend_limit_where_supported",
    )
    assert result.same_day_evidence_required_fields == (
        "candidate_id",
        "workload_stage_or_component",
        "model_or_snapshot",
        "endpoint_or_api_version",
        "request_configuration_id",
        "request_configuration_hash",
        "official_source_ids",
        "official_source_urls",
        "observed_at_utc",
        "lifecycle_status",
        "pricing_status",
        "request_configuration_status",
        "budget_control_id",
        "budget_control_hash",
        "conservative_attempt_reservation_usd",
        "remaining_unreserved_budget_usd",
        "blockers",
    )
    assert result.same_day_lifecycle_recheck_required is True


def test_preflight_scopes_candidate_specific_discovery_blockers():
    result = assess_provider_neutral_pilot_preflight()

    assert result.candidate_specific_blockers == (
        (
            "openai_unified_premium_v1",
            (),
        ),
        (
            "openai_unified_balanced_v1",
            (),
        ),
        (
            "gemini_unified_v1",
            (
                "billable_search_query_count_and_shared_allowance_state",
            ),
        ),
        (
            "groq_split_v1",
            (
                "compound_official_pricing_and_internal_topology",
                "qwen_preview_same_day_lifecycle",
            ),
        ),
    )


def test_preflight_preserves_the_authoritative_experiment_execution_gate():
    result = assess_provider_neutral_pilot_preflight()

    assert result.authoritative_execution_state == "blocked_pre_execution"
    assert result.provider_calls_allowed is False
    assert result.pilot_calls_allowed is False
    assert result.scored_calls_allowed is False
    assert result.provider_calls_completed == 0
    assert result.pilot_calls_completed == 0
    assert result.scored_calls_completed == 0
    assert result.winner_selected is False


def test_preflight_is_immutable_and_never_authorizes_execution():
    result = assess_provider_neutral_pilot_preflight()

    with pytest.raises(FrozenInstanceError):
        result.provider_calls_allowed = True  # type: ignore[misc]
    assert result.independently_authorizes_execution is False


def test_preflight_fails_closed_when_a_required_identity_is_wrong(monkeypatch):
    monkeypatch.setattr(
        "app.services.evaluation_pilot_preflight.REQUEST_CONFIGURATION_HASH",
        "0" * 64,
    )

    with pytest.raises(PilotPreflightError, match="request_configuration_identity"):
        assess_provider_neutral_pilot_preflight()


def test_preflight_fails_closed_when_the_cost_envelope_identity_is_wrong(monkeypatch):
    monkeypatch.setattr(
        "app.services.evaluation_pilot_preflight.COST_ENVELOPE_HASH",
        "0" * 64,
    )

    with pytest.raises(PilotPreflightError, match="cost_envelope_identity"):
        assess_provider_neutral_pilot_preflight()


def test_preflight_fails_closed_when_discovery_or_budget_identity_is_wrong(monkeypatch):
    monkeypatch.setattr(
        "app.services.evaluation_pilot_preflight.URL_DISCOVERY_HASH",
        "0" * 64,
    )
    with pytest.raises(PilotPreflightError, match="url_discovery_identity"):
        assess_provider_neutral_pilot_preflight()

    monkeypatch.undo()
    monkeypatch.setattr(
        "app.services.evaluation_pilot_preflight.PILOT_BUDGET_HASH",
        "0" * 64,
    )
    with pytest.raises(PilotPreflightError, match="pilot_budget_identity"):
        assess_provider_neutral_pilot_preflight()
