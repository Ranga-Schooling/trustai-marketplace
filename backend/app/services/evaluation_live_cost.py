"""Exact live-success billing-unit binding for the frozen pilot schedules.

This module neither reserves money nor queries provider billing systems.  It
accepts only a successful bounded provider envelope whose documented usage
fields are complete enough to calculate one exact frozen estimated-cost record.
"""

from __future__ import annotations

from typing import Any

from app.services.evaluation_pricing import (
    EstimatedCostRecord,
    calculate_estimated_cost,
    verify_pricing_snapshot,
)
from app.services.normalization_parser import (
    DuplicateJsonKeyError,
    ExactJsonNumber,
    StrictJsonPayloadError,
    parse_strict_json_payload,
)


_MAX_SAFE_INTEGER = 9_007_199_254_740_991


class LiveCostBindingError(ValueError):
    """Provider usage cannot be bound exactly to one frozen price schedule."""


def _fail(code: str) -> LiveCostBindingError:
    return LiveCostBindingError(code)


def _object(value: Any, code: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise _fail(code)
    return value


def _integer(value: Any, code: str) -> int:
    if type(value) is not ExactJsonNumber:
        raise _fail(code)
    exact = value.exact_decimal
    if exact != exact.to_integral_value() or not 0 <= exact <= _MAX_SAFE_INTEGER:
        raise _fail(code)
    return int(exact)


def _root(response_bytes: bytes) -> dict[str, Any]:
    if type(response_bytes) is not bytes:
        raise _fail("response_bytes")
    try:
        parsed = parse_strict_json_payload(response_bytes)
    except (DuplicateJsonKeyError, StrictJsonPayloadError) as exc:
        raise _fail("provider_usage_json") from exc
    return _object(parsed.value, "provider_usage_root")


def _openai_usage(
    root: dict[str, Any],
    *,
    model: str,
    workload_stage: str,
) -> tuple[str, dict[str, int]]:
    usage = _object(root.get("usage"), "openai_usage")
    details = _object(usage.get("input_tokens_details"), "openai_input_details")
    total_input = _integer(usage.get("input_tokens"), "openai_input_tokens")
    cached = _integer(details.get("cached_tokens"), "openai_cached_tokens")
    cache_write = _integer(
        details.get("cache_write_tokens"),
        "openai_cache_write_tokens",
    )
    if cached + cache_write > total_input:
        raise _fail("openai_input_partition")
    output = _integer(usage.get("output_tokens"), "openai_output_tokens")
    output_items = root.get("output")
    if type(output_items) is not list or any(type(item) is not dict for item in output_items):
        raise _fail("openai_output_items")
    web_search_calls = sum(item.get("type") == "web_search_call" for item in output_items)
    if (
        workload_stage == "provider_native_url_discovery"
        and web_search_calls != 1
    ) or (
        workload_stage != "provider_native_url_discovery"
        and web_search_calls != 0
    ):
        raise _fail("openai_web_search_call_count")
    model_part = {
        "gpt-5.6-sol": "openai_gpt_5_6_sol",
        "gpt-5.6-terra": "openai_gpt_5_6_terra",
    }.get(model)
    if model_part is None:
        raise _fail("openai_model")
    regime = "standard_short_context_v1" if total_input <= 272_000 else "standard_long_context_v1"
    return (
        f"{model_part}_{regime}",
        {
            "uncached_input_tokens": total_input - cached - cache_write,
            "cached_input_tokens": cached,
            "cache_write_tokens": cache_write,
            "output_tokens": output,
            "web_search_calls": web_search_calls,
        },
    )


def _gemini_usage(root: dict[str, Any]) -> tuple[str, dict[str, int]]:
    usage = _object(root.get("usage"), "gemini_usage")
    cached = _integer(usage.get("total_cached_tokens"), "gemini_cached_tokens")
    if cached != 0:
        # The frozen paid-Standard request configurations do not bind context
        # caching or its separate price component.
        raise _fail("gemini_cached_input")
    input_tokens = _integer(usage.get("total_input_tokens"), "gemini_input_tokens")
    output_tokens = _integer(
        usage.get("total_output_tokens"),
        "gemini_output_tokens",
    )
    thought_tokens = _integer(
        usage.get("total_thought_tokens"),
        "gemini_thought_tokens",
    )
    return (
        "gemini_3_7_flash_paid_standard_2026_v1",
        {
            "input_tokens": input_tokens,
            "output_including_thinking_tokens": output_tokens + thought_tokens,
            "billable_google_search_queries": 0,
        },
    )


def _groq_usage(root: dict[str, Any], *, model: str) -> tuple[str, dict[str, int]]:
    usage = _object(root.get("usage"), "groq_usage")
    prompt = _integer(usage.get("prompt_tokens"), "groq_prompt_tokens")
    output = _integer(usage.get("completion_tokens"), "groq_completion_tokens")
    if model == "openai/gpt-oss-120b":
        details = _object(
            usage.get("prompt_tokens_details"),
            "groq_cached_input",
        )
        cached = _integer(details.get("cached_tokens"), "groq_cached_input")
        if cached > prompt:
            raise _fail("groq_input_partition")
        return (
            "groq_gpt_oss_120b_on_demand_v1",
            {
                "input_tokens": prompt - cached,
                "cached_input_tokens": cached,
                "output_tokens": output,
            },
        )
    if model == "qwen/qwen3.8-27b":
        details = usage.get("prompt_tokens_details")
        if details is not None:
            cached = _integer(
                _object(details, "groq_qwen_input_details").get("cached_tokens"),
                "groq_qwen_cached_input",
            )
            if cached != 0:
                raise _fail("groq_qwen_cached_input")
        return (
            "groq_qwen_3_8_27b_on_demand_v1",
            {"input_tokens": prompt, "output_tokens": output},
        )
    raise _fail("groq_model")


def calculate_live_success_cost(
    *,
    provider: str,
    model: str,
    workload_stage: str,
    response_bytes: bytes,
) -> EstimatedCostRecord:
    """Bind one successful response's exact usage to one frozen schedule."""
    root = _root(response_bytes)
    if provider == "OpenAI":
        schedule_id, usage = _openai_usage(
            root,
            model=model,
            workload_stage=workload_stage,
        )
    elif provider == "Google Gemini" and model == "gemini-3.7-flash":
        schedule_id, usage = _gemini_usage(root)
    elif provider == "Groq":
        schedule_id, usage = _groq_usage(root, model=model)
    else:
        raise _fail("provider_model")
    try:
        return calculate_estimated_cost(
            verify_pricing_snapshot(),
            schedule_id=schedule_id,
            usage=usage,
        )
    except (TypeError, ValueError) as exc:
        raise _fail("pricing_binding") from exc
