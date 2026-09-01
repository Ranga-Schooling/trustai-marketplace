"""Verify the exact provider-free pilot cost envelope.

This module records exact known charge components and preserves unknown billing
quantities as unknown.  It does not access credentials, inspect billing state,
authorize spend, or perform a provider/network operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from app.services.evaluation_contract_identity import load_strict_contract_json


_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_ARTIFACT = (
    _ROOT / "docs" / "testing" / "ai-evaluation" / "pilot-cost-envelope.v1.json"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_EXPECTED_HASH = "7223f8fad4774b8fe431d90475b5aebe53456a509af69bb54daefd1e10636398"
_EXPECTED_UNKNOWN = (
    "provider_reported_input_and_cached_input_tokens_for_configured_model_calls",
    "provider_native_url_discovery_request_input_and_output_usage_without_an_approved_request_configuration",
    "openai_web_search_tool_call_count_and_content_tokens_billed_at_model_rates",
    "gemini_billable_search_query_count_and_shared_free_allowance_state",
    "groq_compound_internal_model_and_tool_usage_with_incomplete_official_pricing",
)
_EXPECTED_COMPONENTS = (
    (
        "openai_sol_configured_maximum_output_conservative_long_context_rate",
        24576,
        "0.00003",
        "0.73728000",
    ),
    (
        "openai_terra_configured_maximum_output_conservative_long_context_rate",
        24576,
        "0.000018",
        "0.44236800",
    ),
    (
        "gemini_flash_configured_maximum_output_including_thinking",
        24576,
        "0.00000375",
        "0.09216000",
    ),
    (
        "groq_gpt_oss_configured_candidate_maximum_output",
        16384,
        "0.0000006",
        "0.00983040",
    ),
    (
        "groq_qwen_configured_visual_maximum_output",
        8192,
        "0.000004",
        "0.03276800",
    ),
    (
        "groq_gpt_oss_baseline_maximum_output",
        8192,
        "0.0000006",
        "0.00491520",
    ),
    (
        "groq_qwen_two_fixed_visual_image_inputs",
        4096,
        "0.0000008",
        "0.00327680",
    ),
)
_TOP_KEYS = {
    "artifact_id",
    "artifact_version",
    "status",
    "purpose",
    "source_bindings",
    "call_plan",
    "region_pricing_binding",
    "known_charge_components_one_attempt",
    "cost_summary",
    "remaining_unknown_cost_components",
    "discovery_configuration_boundary",
    "candidate_cost_readiness",
    "budget_recommendation",
    "same_day_requirement",
    "execution_boundary",
    "provider_calls_completed",
    "pilot_calls_completed",
    "scored_calls_completed",
    "winner_selected",
    "specification_identity",
}


class PilotCostEnvelopeError(ValueError):
    """The pilot cost envelope is stale, ambiguous, or unsafe."""


def _fail(code: str) -> PilotCostEnvelopeError:
    return PilotCostEnvelopeError(code)


@dataclass(frozen=True, slots=True)
class PilotCostEnvelope:
    artifact_id: str
    artifact_version: str
    semantic_hash: str
    pricing_snapshot_hash: str
    request_configuration_hash: str
    region_binding_hash: str
    configured_model_calls: int
    provider_native_url_discovery_calls: int
    nominal_physical_calls: int
    maximum_physical_attempts: int
    regional_uplift_multiplier: Decimal
    conditional_short_context_output_charge_one_attempt: Decimal
    conditional_short_context_output_charge_two_attempts: Decimal
    conservative_output_charge_one_attempt: Decimal
    conservative_output_charge_two_attempts: Decimal
    qwen_fixed_image_charge_one_attempt: Decimal
    qwen_fixed_image_charge_two_attempts: Decimal
    openai_search_tool_charge_one_attempt: Decimal | None
    openai_search_tool_charge_two_attempts: Decimal | None
    known_charge_subtotal_one_attempt: Decimal
    known_charge_subtotal_two_attempts: Decimal
    nominal_total_cost_usd: Decimal | None
    conservative_maximum_total_cost_usd: Decimal | None
    remaining_unknown_cost_components: tuple[str, ...]
    all_planned_calls_cost_finalized: bool
    groq_compound_discovery_cost_finalized: bool
    recommended_budget_ceiling_usd: Decimal
    budget_headroom_over_known_two_attempt_subtotal_usd: Decimal
    budget_authorization_status: str
    recommendation_is_spend_authority: bool
    provider_calls_allowed: bool
    pilot_calls_allowed: bool
    scored_calls_allowed: bool
    provider_calls_completed: int
    winner_selected: bool


def _canonical_without_hash(raw: dict[str, Any]) -> bytes:
    detached = json.loads(json.dumps(raw))
    detached["specification_identity"]["semantic_hash"] = None
    return json.dumps(
        detached,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _decimal(name: str, value: Any) -> Decimal:
    if type(value) is not str:
        raise _fail(f"decimal:{name}")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise _fail(f"decimal:{name}") from None
    if not result.is_finite() or format(result, "f") != value:
        raise _fail(f"decimal:{name}")
    return result


def _exact(name: str, actual: Any, expected: Any) -> None:
    if actual != expected or type(actual) is not type(expected):
        raise _fail(name)


def verify_pilot_cost_envelope(
    path: str | Path = _DEFAULT_ARTIFACT,
) -> PilotCostEnvelope:
    """Verify the immutable cost envelope without inferring unknown usage."""
    try:
        raw = load_strict_contract_json(Path(path))
    except (OSError, TypeError, ValueError) as exc:
        raise _fail("parse") from exc
    if type(raw) is not dict or set(raw) != _TOP_KEYS:
        raise _fail("fields")
    if (
        raw["artifact_id"] != "pilot_cost_envelope_v1"
        or raw["artifact_version"] != "v1"
        or raw["status"] != "provider_free_complete_with_explicit_unknowns"
    ):
        raise _fail("header")

    identity = raw["specification_identity"]
    if (
        type(identity) is not dict
        or set(identity) != {"hash_algorithm", "hash_input", "semantic_hash"}
        or identity["hash_algorithm"] != "SHA-256"
        or identity["hash_input"]
        != "canonical_compact_utf8_json_with_semantic_hash_replaced_by_null"
        or type(identity["semantic_hash"]) is not str
        or _SHA256.fullmatch(identity["semantic_hash"]) is None
    ):
        raise _fail("semantic_hash")
    computed_hash = hashlib.sha256(_canonical_without_hash(raw)).hexdigest()
    if identity["semantic_hash"] != computed_hash or computed_hash != _EXPECTED_HASH:
        raise _fail("semantic_hash")

    sources = raw["source_bindings"]
    if type(sources) is not dict:
        raise _fail("source_bindings")
    expected_sources = {
        "pricing_snapshot_id": "pricing_snapshot_v1",
        "pricing_snapshot_version": "v1",
        "pricing_snapshot_hash": "0467643eafbe55e6e2215c9ad0e0576dac2d0d157a94418eef23382b0ec09282",
        "pricing_observed_on": "2026-08-31",
        "request_configuration_id": "pilot_request_configurations_v1",
        "request_configuration_version": "v1",
        "request_configuration_hash": "1aaca1df3d67f51c3d9c1e5638d63b541bd947a1301aa509291cc7445e60b152",
        "region_binding_id": "pilot_region_binding_v1",
        "region_binding_version": "v1",
        "region_binding_hash": "0c79df332d87bfdf1c902df26df9701bf531100f691650286eb7d5dd38627555",
        "retry_policy_id": "retry_policy_v1",
        "retry_policy_version": "v1",
        "retry_policy_hash": "a4e08ef3b92232cbbf1542aa37b30c87697da60c42bcf72d71876098d0251c4b",
    }
    _exact("source_bindings", sources, expected_sources)

    call_plan = raw["call_plan"]
    expected_call_plan = {
        "configured_non_search_synthesis_model_calls": 18,
        "configured_search_synthesis_model_calls": 4,
        "configured_model_calls": 22,
        "provider_native_url_discovery_calls": 4,
        "nominal_physical_calls": 26,
        "maximum_physical_attempts_per_run": 2,
        "maximum_physical_attempts": 52,
        "application_owned_refetches_are_provider_model_calls": False,
        "provider_native_search_prose_or_snippets_are_canonical_evidence": False,
    }
    _exact("call_plan", call_plan, expected_call_plan)

    region = raw["region_pricing_binding"]
    if region != {
        "provider_service_mode": "standard_global",
        "regional_uplift_multiplier": "1",
        "regional_uplift_applied": False,
        "provider_internal_processing_location_asserted": False,
    }:
        raise _fail("region_pricing_binding")

    components = raw["known_charge_components_one_attempt"]
    if type(components) is not list or len(components) != len(_EXPECTED_COMPONENTS):
        raise _fail("components")
    computed_components: list[tuple[str, Decimal]] = []
    for item, expected in zip(components, _EXPECTED_COMPONENTS, strict=True):
        if type(item) is not dict or set(item) != {
            "component_id",
            "unit_count",
            "usd_per_unit",
            "total_usd",
        }:
            raise _fail("component_fields")
        component_id, unit_count, rate, total = expected
        if item != {
            "component_id": component_id,
            "unit_count": unit_count,
            "usd_per_unit": rate,
            "total_usd": total,
        }:
            raise _fail(f"component:{component_id}")
        calculated = Decimal(unit_count) * _decimal("rate", rate)
        if calculated != _decimal("total", total):
            raise _fail(f"component_arithmetic:{component_id}")
        computed_components.append((component_id, calculated))

    output_ids = {item[0] for item in _EXPECTED_COMPONENTS[:6]}
    conservative_output_one = sum(
        (value for component_id, value in computed_components if component_id in output_ids),
        Decimal(0),
    )
    image_one = computed_components[6][1]
    known_one = sum((value for _, value in computed_components), Decimal(0))
    short_context_output_one = Decimal("0.92610560")

    summary = raw["cost_summary"]
    if type(summary) is not dict:
        raise _fail("cost_summary")
    expected_summary = {
        "currency": "USD",
        "conditional_short_context_output_charge_one_attempt_usd": "0.92610560",
        "conditional_short_context_output_charge_two_attempts_usd": "1.85221120",
        "conservative_output_charge_one_attempt_usd": "1.31932160",
        "conservative_output_charge_two_attempts_usd": "2.63864320",
        "qwen_fixed_image_charge_one_attempt_usd": "0.00327680",
        "qwen_fixed_image_charge_two_attempts_usd": "0.00655360",
        "openai_search_tool_charge_one_attempt_usd": None,
        "openai_search_tool_charge_two_attempts_usd": None,
        "known_charge_subtotal_one_attempt_usd": "1.32259840",
        "known_charge_subtotal_two_attempts_usd": "2.64519680",
        "nominal_total_cost_usd": None,
        "conservative_maximum_total_cost_usd": None,
        "all_planned_calls_cost_finalized": False,
        "rounding": "none_exact_decimal_arithmetic",
    }
    _exact("cost_summary", summary, expected_summary)
    if (
        short_context_output_one
        != _decimal(
            "short_context_output_one",
            summary["conditional_short_context_output_charge_one_attempt_usd"],
        )
        or short_context_output_one * 2
        != _decimal(
            "short_context_output_two",
            summary["conditional_short_context_output_charge_two_attempts_usd"],
        )
        or conservative_output_one
        != _decimal(
            "conservative_output_one",
            summary["conservative_output_charge_one_attempt_usd"],
        )
        or conservative_output_one * 2
        != _decimal(
            "conservative_output_two",
            summary["conservative_output_charge_two_attempts_usd"],
        )
        or image_one
        != _decimal("image_one", summary["qwen_fixed_image_charge_one_attempt_usd"])
        or known_one
        != _decimal("known_one", summary["known_charge_subtotal_one_attempt_usd"])
        or known_one * 2
        != _decimal("known_two", summary["known_charge_subtotal_two_attempts_usd"])
    ):
        raise _fail("cost_arithmetic")

    unknown = raw["remaining_unknown_cost_components"]
    if type(unknown) is not list or tuple(unknown) != _EXPECTED_UNKNOWN:
        raise _fail("unknown_cost_components")
    discovery = raw["discovery_configuration_boundary"]
    if (
        type(discovery) is not dict
        or discovery.get("approved_discovery_maximum_output_tokens") is not None
        or discovery.get("approved_discovery_request_configuration_count") != 0
        or discovery.get("search_synthesis_8192_token_limit_may_be_reused_for_discovery")
        is not False
        or not all(
            type(discovery.get(name)) is str
            and discovery[name].startswith("blocked_")
            for name in (
                "openai_discovery_status",
                "gemini_discovery_status",
                "groq_compound_discovery_status",
            )
        )
    ):
        raise _fail("discovery_configuration_boundary")

    candidates = raw["candidate_cost_readiness"]
    if (
        type(candidates) is not list
        or [item.get("candidate_id") for item in candidates]
        != [
            "openai_unified_premium_v1",
            "openai_unified_balanced_v1",
            "gemini_unified_v1",
            "groq_split_v1",
            "baseline_current_text_v1",
        ]
        or any(
            item.get("complete_candidate_cost_envelope") is not False
            for item in candidates
        )
    ):
        raise _fail("candidate_cost_readiness")

    budget = raw["budget_recommendation"]
    recommendation = _decimal("recommended_ceiling", budget.get("recommended_ceiling_usd"))
    headroom = _decimal("headroom", budget.get("headroom_over_known_two_attempt_subtotal_usd"))
    if (
        recommendation != Decimal("5.00")
        or headroom != recommendation - known_one * 2
        or budget.get("approval_status") != "pending_human_approval"
        or budget.get("recommendation_is_spend_authority") is not False
    ):
        raise _fail("budget_recommendation")

    same_day = raw["same_day_requirement"]
    if (
        same_day.get("pricing_recheck_required") is not True
        or same_day.get("lifecycle_recheck_required") is not True
        or not str(same_day.get("price_or_lifecycle_change_result", "")).startswith("block_")
    ):
        raise _fail("same_day_requirement")
    boundary = raw["execution_boundary"]
    if boundary != {
        "authoritative_execution_gate": "experiment.v1.json execution_gate",
        "execution_state": "blocked_pre_execution",
        "provider_calls_allowed": False,
        "pilot_calls_allowed": False,
        "scored_calls_allowed": False,
        "this_artifact_independently_authorizes_execution": False,
    } or (
        raw["provider_calls_completed"] != 0
        or raw["pilot_calls_completed"] != 0
        or raw["scored_calls_completed"] != 0
        or raw["winner_selected"] is not False
    ):
        raise _fail("execution_boundary")

    return PilotCostEnvelope(
        artifact_id=raw["artifact_id"],
        artifact_version=raw["artifact_version"],
        semantic_hash=identity["semantic_hash"],
        pricing_snapshot_hash=sources["pricing_snapshot_hash"],
        request_configuration_hash=sources["request_configuration_hash"],
        region_binding_hash=sources["region_binding_hash"],
        configured_model_calls=call_plan["configured_model_calls"],
        provider_native_url_discovery_calls=call_plan["provider_native_url_discovery_calls"],
        nominal_physical_calls=call_plan["nominal_physical_calls"],
        maximum_physical_attempts=call_plan["maximum_physical_attempts"],
        regional_uplift_multiplier=_decimal(
            "regional_uplift", region["regional_uplift_multiplier"]
        ),
        conditional_short_context_output_charge_one_attempt=short_context_output_one,
        conditional_short_context_output_charge_two_attempts=short_context_output_one * 2,
        conservative_output_charge_one_attempt=conservative_output_one,
        conservative_output_charge_two_attempts=conservative_output_one * 2,
        qwen_fixed_image_charge_one_attempt=image_one,
        qwen_fixed_image_charge_two_attempts=image_one * 2,
        openai_search_tool_charge_one_attempt=None,
        openai_search_tool_charge_two_attempts=None,
        known_charge_subtotal_one_attempt=known_one,
        known_charge_subtotal_two_attempts=known_one * 2,
        nominal_total_cost_usd=None,
        conservative_maximum_total_cost_usd=None,
        remaining_unknown_cost_components=tuple(unknown),
        all_planned_calls_cost_finalized=False,
        groq_compound_discovery_cost_finalized=False,
        recommended_budget_ceiling_usd=recommendation,
        budget_headroom_over_known_two_attempt_subtotal_usd=headroom,
        budget_authorization_status=budget["approval_status"],
        recommendation_is_spend_authority=budget["recommendation_is_spend_authority"],
        provider_calls_allowed=boundary["provider_calls_allowed"],
        pilot_calls_allowed=boundary["pilot_calls_allowed"],
        scored_calls_allowed=boundary["scored_calls_allowed"],
        provider_calls_completed=raw["provider_calls_completed"],
        winner_selected=raw["winner_selected"],
    )
