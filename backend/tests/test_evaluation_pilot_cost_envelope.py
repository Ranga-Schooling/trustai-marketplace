"""Exact provider-free pilot cost-envelope contract tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
import json
from pathlib import Path

import pytest

from app.services.evaluation_pilot_cost_envelope import (
    PilotCostEnvelopeError,
    verify_pilot_cost_envelope,
)


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = (
    ROOT
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "pilot-cost-envelope.v1.json"
)


def test_cost_envelope_binds_exact_frozen_inputs_and_call_plan():
    envelope = verify_pilot_cost_envelope()

    assert envelope.artifact_id == "pilot_cost_envelope_v1"
    assert envelope.artifact_version == "v1"
    assert envelope.pricing_snapshot_hash == (
        "0467643eafbe55e6e2215c9ad0e0576dac2d0d157a94418eef23382b0ec09282"
    )
    assert envelope.request_configuration_hash == (
        "1aaca1df3d67f51c3d9c1e5638d63b541bd947a1301aa509291cc7445e60b152"
    )
    assert envelope.region_binding_hash == (
        "0c79df332d87bfdf1c902df26df9701bf531100f691650286eb7d5dd38627555"
    )
    assert envelope.configured_model_calls == 22
    assert envelope.provider_native_url_discovery_calls == 4
    assert envelope.nominal_physical_calls == 26
    assert envelope.maximum_physical_attempts == 52


def test_cost_envelope_exact_known_charges_and_no_regional_uplift():
    envelope = verify_pilot_cost_envelope()

    assert envelope.regional_uplift_multiplier == Decimal("1")
    assert envelope.conditional_short_context_output_charge_one_attempt == Decimal(
        "0.92610560"
    )
    assert envelope.conditional_short_context_output_charge_two_attempts == Decimal(
        "1.85221120"
    )
    assert envelope.conservative_output_charge_one_attempt == Decimal("1.31932160")
    assert envelope.conservative_output_charge_two_attempts == Decimal("2.63864320")
    assert envelope.qwen_fixed_image_charge_one_attempt == Decimal("0.00327680")
    assert envelope.qwen_fixed_image_charge_two_attempts == Decimal("0.00655360")
    assert envelope.openai_search_tool_charge_one_attempt is None
    assert envelope.openai_search_tool_charge_two_attempts is None
    assert envelope.known_charge_subtotal_one_attempt == Decimal("1.32259840")
    assert envelope.known_charge_subtotal_two_attempts == Decimal("2.64519680")


def test_cost_envelope_never_misrepresents_unknowns_as_an_exact_total():
    envelope = verify_pilot_cost_envelope()

    assert envelope.nominal_total_cost_usd is None
    assert envelope.conservative_maximum_total_cost_usd is None
    assert envelope.remaining_unknown_cost_components == (
        "provider_reported_input_and_cached_input_tokens_for_configured_model_calls",
        "provider_native_url_discovery_request_input_and_output_usage_without_an_approved_request_configuration",
        "openai_web_search_tool_call_count_and_content_tokens_billed_at_model_rates",
        "gemini_billable_search_query_count_and_shared_free_allowance_state",
        "groq_compound_internal_model_and_tool_usage_with_incomplete_official_pricing",
    )
    assert envelope.all_planned_calls_cost_finalized is False
    assert envelope.groq_compound_discovery_cost_finalized is False


def test_cost_envelope_recommends_but_does_not_authorize_five_dollars():
    envelope = verify_pilot_cost_envelope()

    assert envelope.recommended_budget_ceiling_usd == Decimal("5.00")
    assert envelope.budget_headroom_over_known_two_attempt_subtotal_usd == Decimal(
        "2.35480320"
    )
    assert envelope.budget_authorization_status == "pending_human_approval"
    assert envelope.recommendation_is_spend_authority is False
    assert envelope.provider_calls_allowed is False
    assert envelope.pilot_calls_allowed is False
    assert envelope.provider_calls_completed == 0
    assert envelope.winner_selected is False

    with pytest.raises(FrozenInstanceError):
        envelope.provider_calls_allowed = True  # type: ignore[misc]


def test_cost_envelope_rejects_mutation_or_invented_exact_total(tmp_path):
    raw = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    raw["cost_summary"]["conservative_maximum_total_cost_usd"] = "1.89876480"
    path = tmp_path / "cost.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(PilotCostEnvelopeError, match="semantic_hash"):
        verify_pilot_cost_envelope(path)


def test_cost_envelope_module_is_provider_free_and_has_no_floating_point_surface():
    source = (
        ROOT
        / "backend"
        / "app"
        / "services"
        / "evaluation_pilot_cost_envelope.py"
    ).read_text(encoding="utf-8")

    assert "requests" not in source
    assert "httpx" not in source
    assert "urllib" not in source
    assert "os.environ" not in source
    assert "float(" not in source
