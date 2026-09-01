"""Provider-free aggregation tests for the pilot preflight checkpoint."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.services.evaluation_pilot_preflight import (
    PilotPreflightError,
    assess_provider_neutral_pilot_preflight,
)


def test_preflight_reports_exact_resolved_scope_and_remaining_decisions():
    result = assess_provider_neutral_pilot_preflight()

    assert result.status == "provider_neutral_ready_awaiting_decisions"
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
        "dated_official_pricing_schedules",
    )
    assert result.remaining_decision_packages == (
        "ps1_trace_conforming_retrieval_architecture",
        "execution_and_restricted_storage_region",
        "pilot_budget_ceiling",
        "credential_authorization_handling_and_scope",
        "explicit_pilot_authorization",
    )
    assert result.same_day_lifecycle_recheck_required is True
    assert result.provider_calls_allowed is False
    assert result.pilot_calls_allowed is False
    assert result.provider_calls_completed == 0
    assert result.pilot_calls_completed == 0
    assert result.scored_calls_completed == 0
    assert result.winner_selected is False


def test_preflight_stage_matrix_and_call_counts_are_exact():
    result = assess_provider_neutral_pilot_preflight()

    assert result.eligible_stage_matrix == (
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
    assert result.ineligible_stage_matrix == (
        ("openai_unified_premium_v1", "search_retrieval"),
        ("openai_unified_balanced_v1", "search_retrieval"),
        ("gemini_unified_v1", "search_retrieval"),
        ("groq_split_v1", "search_retrieval"),
    )
    assert result.provider_calls_in_currently_configured_non_search_scope == 18
    assert result.planned_provider_calls_after_ps1_resolution == 26
    assert result.maximum_physical_attempts_after_ps1_resolution == 52


def test_ps1_blockers_preserve_the_frozen_security_and_evidence_boundaries():
    result = assess_provider_neutral_pilot_preflight()

    assert result.ps1_provider_free_blockers == (
        "source_classification_policy_v1",
        "url_security_operational_origin_rule_registry_v1",
        "retrieval_objective_support_policy_v1_and_PS1_objective_manifest",
        "deterministic_trace_backed_evidence_extractor_and_matcher_v1",
    )
    assert result.ps1_reusable_primitives == (
        "bounded_ssrf_safe_fetch_transport",
        "strict_url_security_and_redirect_auth_classification",
        "deterministic_retrieval_ordinals_source_ids_and_evidence_ids",
        "restricted_exact_trace_and_safe_ordinary_projection",
        "safe_search_tool_result_record",
    )
    assert result.ps1_built_in_search_evidence_eligible is False
    assert result.ps1_security_contract_weakened is False


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
