"""Provider-neutral exact pricing snapshot and calculation tests."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext
import json
from pathlib import Path

import pytest

from app.services.evaluation_pricing import (
    PricingSnapshot,
    PricingContractError,
    calculate_estimated_cost,
    verify_estimated_cost_record,
    verify_pricing_snapshot,
)


ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = (
    ROOT / "docs" / "testing" / "ai-evaluation" / "pricing-snapshot.v1.json"
)
MODULE_PATH = (
    ROOT / "backend" / "app" / "services" / "evaluation_pricing.py"
)


def _snapshot():
    return verify_pricing_snapshot(SNAPSHOT_PATH)


def _zero_usage(schedule_id: str) -> dict[str, int]:
    snapshot = _snapshot()
    schedule = next(
        item for item in snapshot.schedules if item.schedule_id == schedule_id
    )
    return {component: 0 for component, _ in schedule.rates}


def test_snapshot_is_dated_official_evidence_without_execution_authority():
    snapshot = _snapshot()

    assert snapshot.artifact_id == "pricing_snapshot_v1"
    assert snapshot.artifact_version == "v1"
    assert snapshot.observed_on == "2026-08-31"
    assert snapshot.currency == "USD"
    assert snapshot.status == "blocked_incomplete_candidate_binding"
    assert snapshot.provider_calls_allowed is False
    assert snapshot.provider_calls_completed == 0
    assert snapshot.pilot_calls_allowed is False
    assert snapshot.scored_calls_allowed is False
    assert snapshot.winner_selected is False

    raw = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert {source["provider"] for source in raw["official_sources"]} == {
        "OpenAI",
        "Google Gemini",
        "Groq",
    }
    assert all(
        source["url"].startswith(
            ("https://developers.openai.com/", "https://ai.google.dev/", "https://console.groq.com/")
        )
        for source in raw["official_sources"]
    )


def test_snapshot_covers_every_enabled_candidate_and_baseline_without_selecting_them():
    raw = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    bindings = {
        item["candidate_id"]: item for item in raw["candidate_bindings"]
    }
    assert set(bindings) == {
        "openai_unified_premium_v1",
        "openai_unified_balanced_v1",
        "gemini_unified_v1",
        "groq_split_v1",
        "baseline_current_text_v1",
    }
    assert all(
        item["selection_rule_status"].startswith("blocked_")
        for item in bindings.values()
    )
    assert all(item["status"].startswith("blocked_") for item in bindings.values())
    assert raw["winner_selected"] is False


def test_openai_cost_is_exact_decimal_and_includes_web_search_calls():
    usage = _zero_usage("openai_gpt_5_6_sol_standard_short_context_v1")
    usage.update(
        {
            "uncached_input_tokens": 1_000,
            "cached_input_tokens": 500,
            "cache_write_tokens": 0,
            "output_tokens": 200,
            "web_search_calls": 2,
        }
    )

    record = calculate_estimated_cost(
        _snapshot(),
        schedule_id="openai_gpt_5_6_sol_standard_short_context_v1",
        usage=usage,
    )

    assert record.total_usd == "0.0282"
    assert record.component_costs == (
        ("uncached_input_tokens", "0.004"),
        ("cached_input_tokens", "0.0002"),
        ("cache_write_tokens", "0"),
        ("output_tokens", "0.004"),
        ("web_search_calls", "0.02"),
    )
    assert Decimal(record.total_usd) == Decimal("0.0282")
    with pytest.raises(FrozenInstanceError):
        record.total_usd = "0"  # type: ignore[misc]


def test_gemini_cost_requires_explicit_billable_search_query_count():
    usage = _zero_usage("gemini_3_7_flash_paid_standard_2026_v1")
    usage.update(
        {
            "input_tokens": 1_000,
            "output_including_thinking_tokens": 200,
            "billable_google_search_queries": 3,
        }
    )

    record = calculate_estimated_cost(
        _snapshot(),
        schedule_id="gemini_3_7_flash_paid_standard_2026_v1",
        usage=usage,
    )

    assert record.total_usd == "0.0435"


def test_groq_visual_cost_can_use_the_official_per_image_token_quantity():
    usage = _zero_usage("groq_qwen_3_8_27b_on_demand_v1")
    usage.update({"input_tokens": 2_048, "output_tokens": 100})

    record = calculate_estimated_cost(
        _snapshot(),
        schedule_id="groq_qwen_3_8_27b_on_demand_v1",
        usage=usage,
    )

    assert record.total_usd == "0.0020384"


def test_incomplete_compound_schedule_fails_closed():
    usage = _zero_usage("groq_compound_official_incomplete_v1")
    with pytest.raises(PricingContractError, match="pricing_schedule_incomplete"):
        calculate_estimated_cost(
            _snapshot(),
            schedule_id="groq_compound_official_incomplete_v1",
            usage=usage,
        )


@pytest.mark.parametrize(
    "mutator, error",
    [
        (lambda usage: usage.__setitem__("input_tokens", True), "usage_unit_type"),
        (lambda usage: usage.__setitem__("input_tokens", 1.5), "usage_unit_type"),
        (lambda usage: usage.__setitem__("input_tokens", -1), "usage_unit_negative"),
        (lambda usage: usage.__setitem__("unknown_charge", 1), "usage_component_set"),
        (lambda usage: usage.pop("input_tokens"), "usage_component_set"),
    ],
)
def test_usage_is_closed_non_negative_integer_inventory(mutator, error):
    usage = _zero_usage("groq_gpt_oss_120b_on_demand_v1")
    mutator(usage)
    with pytest.raises(PricingContractError, match=error):
        calculate_estimated_cost(
            _snapshot(),
            schedule_id="groq_gpt_oss_120b_on_demand_v1",
            usage=usage,
        )


def test_snapshot_identity_and_rates_fail_closed_on_tampering(tmp_path):
    raw = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    raw["schedules"][0]["rates"][0]["usd_per_unit"] = "0.0000000001"
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(PricingContractError, match="pricing_snapshot_identity"):
        verify_pricing_snapshot(path)


def test_estimated_cost_record_is_self_contained_and_recomputed_fail_closed():
    usage = _zero_usage("openai_gpt_5_6_terra_standard_short_context_v1")
    usage.update({"uncached_input_tokens": 100, "output_tokens": 10})
    record = calculate_estimated_cost(
        _snapshot(),
        schedule_id="openai_gpt_5_6_terra_standard_short_context_v1",
        usage=usage,
    )

    exposed = record.as_dict()
    assert exposed["provider"] == "OpenAI"
    assert exposed["model"] == "gpt-5.6-terra"
    assert verify_estimated_cost_record(exposed) == record

    exposed["total_usd"] = "0"
    with pytest.raises(PricingContractError, match="estimated_cost_recalculation"):
        verify_estimated_cost_record(exposed)


def test_calculator_rejects_a_manually_forged_snapshot():
    with pytest.raises(PricingContractError, match="pricing_snapshot_factory_required"):
        PricingSnapshot(
            artifact_id="pricing_snapshot_v1",
            artifact_version="v1",
            status="blocked_incomplete_candidate_binding",
            currency="USD",
            observed_on="2026-08-31",
            semantic_hash="0" * 64,
            schedules=(),
            provider_calls_allowed=False,
            pilot_calls_allowed=False,
            scored_calls_allowed=False,
            provider_calls_completed=0,
            winner_selected=False,
        )


def test_cost_is_exact_independent_of_decimal_context_precision():
    usage = _zero_usage("groq_gpt_oss_120b_on_demand_v1")
    usage["input_tokens"] = 10**100
    with localcontext() as context:
        context.prec = 2
        record = calculate_estimated_cost(
            _snapshot(),
            schedule_id="groq_gpt_oss_120b_on_demand_v1",
            usage=usage,
        )

    assert record.total_usd == "15" + ("0" * 92)


def test_pricing_module_has_no_network_provider_or_floating_point_surface():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert imported_roots.isdisjoint(
        {"httpx", "requests", "openai", "groq", "google", "socket"}
    )
    assert not any(
        isinstance(node, ast.Constant) and isinstance(node.value, float)
        for node in ast.walk(tree)
    )
