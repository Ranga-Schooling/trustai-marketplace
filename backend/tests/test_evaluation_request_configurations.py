"""Provider-free tests for frozen pilot request configurations."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.services.evaluation_contract_identity import load_strict_contract_json
from app.services.evaluation_provider_adapters import bind_provider_adapters
from app.services.evaluation_provider_role_mappings import (
    bind_provider_role_mappings,
)
from app.services.evaluation_request_configurations import (
    PilotRequestConfigurationError,
    bind_pilot_request_configurations,
    select_pilot_request_configuration,
    validate_request_configuration_record,
)
from app.services.evaluation_search_authority import bind_search_authority_v2


ROOT = Path(__file__).parents[2]
ARTIFACTS = ROOT / "docs" / "testing" / "ai-evaluation"
REQUEST_PATH = ARTIFACTS / "request-configurations.v1.json"
MAPPING_PATH = ARTIFACTS / "provider-role-mappings.v1.json"
ADAPTER_PATH = ARTIFACTS / "provider-adapters.v1.json"
SEARCH_PATH = ARTIFACTS / "search-authority.v2.json"
PROMPT_PATH = ARTIFACTS / "prompt-templates.v1.json"
SPEC_PATH = ARTIFACTS / "normalization-parser.v1.json"

EXPECTED_SELECTIONS = {
    ("openai_unified_premium_v1", "text_analysis"): (
        "openai_sol_text_pilot_v1",
        4096,
    ),
    ("openai_unified_premium_v1", "search_synthesis"): (
        "openai_sol_search_synthesis_pilot_v1",
        8192,
    ),
    ("openai_unified_premium_v1", "visual_inspection"): (
        "openai_sol_visual_pilot_v1",
        4096,
    ),
    ("openai_unified_balanced_v1", "text_analysis"): (
        "openai_terra_text_pilot_v1",
        4096,
    ),
    ("openai_unified_balanced_v1", "search_synthesis"): (
        "openai_terra_search_synthesis_pilot_v1",
        8192,
    ),
    ("openai_unified_balanced_v1", "visual_inspection"): (
        "openai_terra_visual_pilot_v1",
        4096,
    ),
    ("gemini_unified_v1", "text_analysis"): (
        "gemini_flash_text_pilot_v1",
        4096,
    ),
    ("gemini_unified_v1", "search_synthesis"): (
        "gemini_flash_search_synthesis_pilot_v1",
        8192,
    ),
    ("gemini_unified_v1", "visual_inspection"): (
        "gemini_flash_visual_pilot_v1",
        4096,
    ),
    ("groq_split_v1", "text_analysis"): (
        "groq_gpt_oss_text_pilot_v1",
        4096,
    ),
    ("groq_split_v1", "search_synthesis"): (
        "groq_gpt_oss_search_synthesis_pilot_v1",
        8192,
    ),
    ("groq_split_v1", "visual_inspection"): (
        "groq_qwen_visual_pilot_v1",
        4096,
    ),
    ("baseline_current_text_v1", "text_analysis"): (
        "groq_baseline_text_pilot_v1",
        4096,
    ),
}


def _raw():
    request = load_strict_contract_json(REQUEST_PATH)
    mappings = load_strict_contract_json(MAPPING_PATH)
    adapters = load_strict_contract_json(ADAPTER_PATH)
    search = load_strict_contract_json(SEARCH_PATH)
    prompts = load_strict_contract_json(PROMPT_PATH)
    spec = load_strict_contract_json(SPEC_PATH)
    authority = bind_search_authority_v2(search, prompts, spec)
    mapping_set = bind_provider_role_mappings(mappings, authority)
    adapter_set = bind_provider_adapters(adapters, mapping_set)
    return request, mapping_set, adapter_set


def _bound():
    request, mappings, adapters = _raw()
    return bind_pilot_request_configurations(request, mappings, adapters)


def test_approved_configuration_inventory_and_execution_boundary_are_exact():
    bound = _bound()

    assert len(bound.configurations) == 13
    assert {
        (item.candidate_id, item.workload_stage): (
            item.configuration_id,
            item.maximum_output_tokens,
        )
        for item in bound.configurations
    } == EXPECTED_SELECTIONS
    assert bound.provider_calls_allowed is False
    assert bound.pilot_calls_allowed is False
    assert bound.scored_calls_allowed is False
    assert bound.provider_calls_completed == 0
    assert bound.pilot_calls_completed == 0
    assert bound.scored_calls_completed == 0
    assert bound.winner_selected is False
    assert bound.independently_authorizes_execution is False


def test_balanced_parameters_are_frozen_without_cross_provider_approximation():
    bound = _bound()
    by_id = {item.configuration_id: item for item in bound.configurations}

    for item in bound.configurations:
        assert item.top_p == "deliberately_unset"
        assert item.streaming_enabled is False
        assert item.timeout_seconds == 120
        assert item.maximum_physical_attempts == 2
    assert by_id["openai_sol_text_pilot_v1"].reasoning == "medium"
    assert by_id["openai_sol_text_pilot_v1"].temperature == 1.0
    assert by_id["openai_sol_visual_pilot_v1"].image_detail == "auto"
    assert by_id["gemini_flash_text_pilot_v1"].reasoning == "medium"
    assert by_id["gemini_flash_text_pilot_v1"].temperature is None
    assert by_id["gemini_flash_text_pilot_v1"].temperature_state == "unsupported_or_unavailable"
    assert by_id["gemini_flash_visual_pilot_v1"].image_detail is None
    assert by_id["groq_gpt_oss_text_pilot_v1"].reasoning == "medium"
    assert by_id["groq_gpt_oss_text_pilot_v1"].temperature == 1.0
    qwen = by_id["groq_qwen_visual_pilot_v1"]
    assert qwen.structured_output_mode == "json_schema_best_effort"
    assert qwen.harness_schema_validation_required is True
    assert qwen.image_detail is None
    baseline = by_id["groq_baseline_text_pilot_v1"]
    assert baseline.temperature == 0.2
    assert baseline.reasoning is None
    assert baseline.structured_output_mode == "json_object"
    assert baseline.harness_schema_validation_required is True


@pytest.mark.parametrize("candidate_id", (
    "openai_unified_premium_v1",
    "openai_unified_balanced_v1",
    "gemini_unified_v1",
    "groq_split_v1",
))
def test_search_retrieval_remains_explicitly_ineligible(candidate_id):
    bound = _bound()

    with pytest.raises(
        PilotRequestConfigurationError,
        match="search_retrieval_ineligible",
    ):
        select_pilot_request_configuration(
            bound,
            candidate_id=candidate_id,
            workload_stage="search_retrieval",
        )


@pytest.mark.parametrize(("candidate_id", "workload_stage"), EXPECTED_SELECTIONS)
def test_selection_is_exact_and_pre_attempt(candidate_id, workload_stage):
    bound = _bound()

    selected = select_pilot_request_configuration(
        bound,
        candidate_id=candidate_id,
        workload_stage=workload_stage,
    )

    expected_id, expected_tokens = EXPECTED_SELECTIONS[(candidate_id, workload_stage)]
    assert selected.configuration.configuration_id == expected_id
    assert selected.configuration.maximum_output_tokens == expected_tokens
    assert selected.provider_attempt_created is False
    assert selected.provider_call_incremented is False
    assert selected.independently_authorizes_execution is False


def test_safe_result_record_projection_is_exact_and_validated():
    selection = select_pilot_request_configuration(
        _bound(),
        candidate_id="openai_unified_balanced_v1",
        workload_stage="visual_inspection",
    )
    record = selection.configuration.safe_record_projection()

    validated = validate_request_configuration_record(selection, record)

    assert validated == record
    assert set(record) == {
        "request_configuration_id",
        "request_configuration_version",
        "request_configuration_hash",
        "role_mapping_id",
        "role_mapping_version",
        "role_mapping_hash",
        "adapter_id",
        "adapter_version",
        "adapter_hash",
        "maximum_output_tokens",
        "reasoning_or_thinking_level",
        "temperature_if_supported",
        "top_p_if_supported",
        "seed_if_supported",
        "structured_output_mode",
        "search_and_tool_configuration",
        "image_detail_or_resolution_configuration",
        "timeout_seconds",
        "maximum_physical_attempts",
        "streaming_enabled",
        "storage_configuration",
        "caching_configuration",
    }


@pytest.mark.parametrize("mutation", (
    lambda record: record.__setitem__("maximum_output_tokens", 8192),
    lambda record: record.__setitem__("temperature_if_supported", 0.2),
    lambda record: record.__setitem__("request_configuration_hash", "0" * 64),
    lambda record: record.__setitem__("streaming_enabled", True),
    lambda record: record.__setitem__("extra", True),
))
def test_result_record_projection_mutations_fail_closed(mutation):
    selection = select_pilot_request_configuration(
        _bound(),
        candidate_id="openai_unified_balanced_v1",
        workload_stage="text_analysis",
    )
    record = selection.configuration.safe_record_projection()
    mutation(record)

    with pytest.raises(PilotRequestConfigurationError, match="record"):
        validate_request_configuration_record(selection, record)


@pytest.mark.parametrize("mutation", (
    lambda raw: raw["configurations"][0]["envelope"]["content"].__setitem__(
        "maximum_output_tokens", 8192
    ),
    lambda raw: raw["configurations"][0]["envelope"]["content"].__setitem__(
        "streaming_enabled", True
    ),
    lambda raw: raw["configurations"][0]["envelope"]["content"].__setitem__(
        "role_mapping_hash", "0" * 64
    ),
    lambda raw: raw["configurations"][0]["envelope"]["content"].__setitem__(
        "adapter_hash", "0" * 64
    ),
))
def test_semantic_or_binding_mutations_fail_closed(mutation):
    raw, mappings, adapters = _raw()
    mutation(raw)

    with pytest.raises(PilotRequestConfigurationError):
        bind_pilot_request_configurations(raw, mappings, adapters)


def test_binding_does_not_mutate_any_input_artifact():
    raw, mappings, adapters = _raw()
    original = copy.deepcopy(raw)

    bind_pilot_request_configurations(raw, mappings, adapters)

    assert raw == original


def test_artifact_is_strict_json_without_duplicate_keys_or_nonfinite_values():
    payload = REQUEST_PATH.read_bytes()

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate")
            result[key] = value
        return result

    parsed = json.loads(
        payload,
        object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )
    assert parsed["artifact_id"] == "pilot_request_configurations_v1"
    payload.decode("utf-8", errors="strict")
