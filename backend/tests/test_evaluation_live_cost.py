"""Exact live success-cost binding tests; no provider or billing endpoint exists here."""

from __future__ import annotations

import json

import pytest

from app.services.evaluation_live_cost import (
    LiveCostBindingError,
    calculate_live_success_cost,
)


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


@pytest.mark.parametrize(
    ("provider", "model", "stage", "body", "schedule_id", "total"),
    (
        (
            "OpenAI",
            "gpt-5.6-sol",
            "text_analysis",
            {
                "output": [{"type": "message"}],
                "usage": {
                    "input_tokens": 12,
                    "input_tokens_details": {
                        "cached_tokens": 2,
                        "cache_write_tokens": 1,
                    },
                    "output_tokens": 7,
                },
            },
            "openai_gpt_5_6_sol_standard_short_context_v1",
            "0.0001818",
        ),
        (
            "Google Gemini",
            "gemini-3.7-flash",
            "visual_inspection",
            {
                "usage": {
                    "total_cached_tokens": 0,
                    "total_input_tokens": 268,
                    "total_output_tokens": 20,
                    "total_thought_tokens": 4,
                }
            },
            "gemini_3_7_flash_paid_standard_2026_v1",
            "0.000291",
        ),
        (
            "Groq",
            "openai/gpt-oss-120b",
            "text_analysis",
            {
                "usage": {
                    "prompt_tokens": 18,
                    "prompt_tokens_details": {"cached_tokens": 4},
                    "completion_tokens": 9,
                }
            },
            "groq_gpt_oss_120b_on_demand_v1",
            "0.0000078",
        ),
        (
            "Groq",
            "qwen/qwen3.8-27b",
            "visual_inspection",
            {
                "usage": {"prompt_tokens": 18, "completion_tokens": 9}
            },
            "groq_qwen_3_8_27b_on_demand_v1",
            "0.0000504",
        ),
        (
            "OpenAI",
            "gpt-5.6-sol",
            "provider_native_url_discovery",
            {
                "output": [{"type": "web_search_call"}],
                "usage": {
                    "input_tokens": 10,
                    "input_tokens_details": {
                        "cached_tokens": 0,
                        "cache_write_tokens": 0,
                    },
                    "output_tokens": 5,
                },
            },
            "openai_gpt_5_6_sol_standard_short_context_v1",
            "0.01014",
        ),
    ),
)
def test_exact_live_success_cost_uses_frozen_provider_chargeable_units(
    provider, model, stage, body, schedule_id, total
):
    result = calculate_live_success_cost(
        provider=provider,
        model=model,
        workload_stage=stage,
        response_bytes=_bytes(body),
    )

    assert result.schedule_id == schedule_id
    assert result.total_usd == total


@pytest.mark.parametrize(
    "body",
    (
        {"output": [], "usage": {"input_tokens": 1, "output_tokens": 1}},
        {
            "output": [],
            "usage": {
                "input_tokens": 1,
                "input_tokens_details": {
                    "cached_tokens": 2,
                    "cache_write_tokens": 0,
                },
                "output_tokens": 1,
            },
        },
        {
            "output": [{"type": "web_search_call"}, {"type": "web_search_call"}],
            "usage": {
                "input_tokens": 1,
                "input_tokens_details": {
                    "cached_tokens": 0,
                    "cache_write_tokens": 0,
                },
                "output_tokens": 1,
            },
        },
    ),
)
def test_openai_incomplete_incoherent_or_unbounded_usage_fails_closed(body):
    with pytest.raises(LiveCostBindingError):
        calculate_live_success_cost(
            provider="OpenAI",
            model="gpt-5.6-sol",
            workload_stage="provider_native_url_discovery",
            response_bytes=_bytes(body),
        )


def test_gemini_automatic_or_explicit_cached_input_is_not_silently_mispriced():
    body = {
        "usage": {
            "total_cached_tokens": 1,
            "total_input_tokens": 10,
            "total_output_tokens": 2,
            "total_thought_tokens": 3,
        }
    }

    with pytest.raises(LiveCostBindingError, match="gemini_cached_input"):
        calculate_live_success_cost(
            provider="Google Gemini",
            model="gemini-3.7-flash",
            workload_stage="text_analysis",
            response_bytes=_bytes(body),
        )


def test_groq_gpt_oss_requires_cached_token_breakdown_because_caching_is_automatic():
    body = {
        "usage": {"prompt_tokens": 10, "completion_tokens": 2}
    }

    with pytest.raises(LiveCostBindingError, match="groq_cached_input"):
        calculate_live_success_cost(
            provider="Groq",
            model="openai/gpt-oss-120b",
            workload_stage="text_analysis",
            response_bytes=_bytes(body),
        )
