"""Provider-free tests for frozen response adapters and topology preflight."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from app.services.evaluation_contract_identity import load_strict_contract_json
from app.services.evaluation_provider_adapters import (
    ProviderAdapterContractError,
    ProviderAdapterResponseError,
    adapt_provider_response,
    assess_adapter_topology,
    bind_provider_adapters,
    require_eligible_adapter_topology,
)
from app.services.evaluation_provider_role_mappings import (
    bind_provider_role_mappings,
    select_provider_role_mapping,
)
from app.services.evaluation_search_authority import bind_search_authority_v2
from app.services.evaluation_transport_capture import CanonicalRawResponseAccumulator


ARTIFACT_DIRECTORY = (
    Path(__file__).parents[2] / "docs" / "testing" / "ai-evaluation"
)
ADAPTER_PATH = ARTIFACT_DIRECTORY / "provider-adapters.v1.json"
MAPPING_PATH = ARTIFACT_DIRECTORY / "provider-role-mappings.v1.json"
SEARCH_PATH = ARTIFACT_DIRECTORY / "search-authority.v2.json"
PROMPT_PATH = ARTIFACT_DIRECTORY / "prompt-templates.v1.json"
SPEC_PATH = ARTIFACT_DIRECTORY / "normalization-parser.v1.json"
EXPECTED_ARTIFACT_HASH = (
    "7d8fe70e6f2f74d9223233c9174443e4d9849be690fcd382a45ab17e385f2bf7"
)
EXPECTED_ADAPTER_HASHES = {
    "openai_responses_adapter_v1": (
        "78cb5800877d25970d4ed7e9a34ad63a25a591b8ba3b890da098a88a5052063d"
    ),
    "gemini_interactions_adapter_v1": (
        "9b74156f6ea19b2f2b4f9107a9c7325b580e091fff4651cff4996b6641e89fa5"
    ),
    "groq_chat_completions_adapter_v1": (
        "6fe6a87605ad3729762d092c9917cc38875a516e2c10d8722fbd27e243c3b0f5"
    ),
    "groq_compound_chat_completions_adapter_v1": (
        "3ff807e50f87f60a7d031dadb2bcf96dcedfa3942dad3b9b634dd64d5f8b530a"
    ),
    "groq_vision_chat_completions_adapter_v1": (
        "835ffdf536f84b4f23c9da3f812c3833778abe55352a708b56a33a40372c33db"
    ),
}


SELECTIONS = {
    ("openai_unified_premium_v1", "text_analysis"): (
        "OpenAI",
        "gpt-5.6-sol",
        "Responses API",
        "single_call_text",
    ),
    ("openai_unified_premium_v1", "search_retrieval"): (
        "OpenAI",
        "gpt-5.6-sol",
        "Responses API",
        "two_call_search_retrieval",
    ),
    ("openai_unified_premium_v1", "search_synthesis"): (
        "OpenAI",
        "gpt-5.6-sol",
        "Responses API",
        "two_call_search_synthesis",
    ),
    ("openai_unified_premium_v1", "visual_inspection"): (
        "OpenAI",
        "gpt-5.6-sol",
        "Responses API",
        "single_call_visual",
    ),
    ("openai_unified_balanced_v1", "text_analysis"): (
        "OpenAI",
        "gpt-5.6-terra",
        "Responses API",
        "single_call_text",
    ),
    ("openai_unified_balanced_v1", "search_retrieval"): (
        "OpenAI",
        "gpt-5.6-terra",
        "Responses API",
        "two_call_search_retrieval",
    ),
    ("openai_unified_balanced_v1", "search_synthesis"): (
        "OpenAI",
        "gpt-5.6-terra",
        "Responses API",
        "two_call_search_synthesis",
    ),
    ("openai_unified_balanced_v1", "visual_inspection"): (
        "OpenAI",
        "gpt-5.6-terra",
        "Responses API",
        "single_call_visual",
    ),
    ("gemini_unified_v1", "text_analysis"): (
        "Google Gemini",
        "gemini-3.7-flash",
        "Gemini Interactions API v1beta with Api-Revision 2026-05-20",
        "single_call_text",
    ),
    ("gemini_unified_v1", "search_retrieval"): (
        "Google Gemini",
        "gemini-3.7-flash",
        "Gemini Interactions API v1beta with Api-Revision 2026-05-20",
        "two_call_search_retrieval",
    ),
    ("gemini_unified_v1", "search_synthesis"): (
        "Google Gemini",
        "gemini-3.7-flash",
        "Gemini Interactions API v1beta with Api-Revision 2026-05-20",
        "two_call_search_synthesis",
    ),
    ("gemini_unified_v1", "visual_inspection"): (
        "Google Gemini",
        "gemini-3.7-flash",
        "Gemini Interactions API v1beta with Api-Revision 2026-05-20",
        "single_call_visual",
    ),
    ("groq_split_v1", "text_analysis"): (
        "Groq",
        "openai/gpt-oss-120b",
        "Chat Completions API",
        "single_call_text",
    ),
    ("groq_split_v1", "search_retrieval"): (
        "Groq",
        "groq/compound",
        "Chat Completions API with Compound",
        "two_call_search_retrieval",
    ),
    ("groq_split_v1", "search_synthesis"): (
        "Groq",
        "openai/gpt-oss-120b",
        "Chat Completions API",
        "two_call_search_synthesis",
    ),
    ("groq_split_v1", "visual_inspection"): (
        "Groq",
        "qwen/qwen3.8-27b",
        "Chat Completions API with vision content",
        "single_call_visual",
    ),
}


def _raw_artifacts():
    return (
        load_strict_contract_json(ADAPTER_PATH),
        load_strict_contract_json(MAPPING_PATH),
        load_strict_contract_json(SEARCH_PATH),
        load_strict_contract_json(PROMPT_PATH),
        load_strict_contract_json(SPEC_PATH),
    )


def _bound():
    adapters, mappings, search, prompts, spec = _raw_artifacts()
    search_binding = bind_search_authority_v2(search, prompts, spec)
    mapping_set = bind_provider_role_mappings(mappings, search_binding)
    return bind_provider_adapters(adapters, mapping_set), mapping_set


def _selection(candidate_id: str, stage: str):
    _, mapping_set = _bound()
    provider, model, api_family, topology = SELECTIONS[(candidate_id, stage)]
    return select_provider_role_mapping(
        mapping_set,
        candidate_id=candidate_id,
        provider=provider,
        model_id=model,
        api_family=api_family,
        workload_stage=stage,
        topology_id=topology,
    )


def _capture_bytes(payload: bytes):
    accumulator = CanonicalRawResponseAccumulator("non_streaming_http")
    accumulator.append(payload)
    return accumulator.finish_response()


def _capture_json(payload):
    return _capture_bytes(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode()
    )


def _openai_payload(model="gpt-5.6-sol", text='{"risk_level":"LOW"}'):
    return {
        "id": "native-id-must-not-enter-ordinary-record",
        "model": model,
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "output": [
            {"type": "reasoning", "summary": []},
            {
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": text, "annotations": []}
                ],
            },
        ],
        "usage": {
            "input_tokens": 12,
            "output_tokens": 7,
            "output_tokens_details": {"reasoning_tokens": 3},
            "total_tokens": 19,
        },
    }


def _gemini_payload(text='{"findings":[]}'):
    return {
        "id": "native-id-must-not-enter-ordinary-record",
        "model": "gemini-3.7-flash",
        "status": "completed",
        "steps": [
            {"type": "thought", "summary": []},
            {"type": "model_output", "content": [{"type": "text", "text": text}]},
        ],
        "usage": {
            "input_tokens_by_modality": [
                {"modality": "text", "tokens": 10},
                {"modality": "image", "tokens": 258},
            ],
            "total_input_tokens": 268,
            "total_output_tokens": 20,
            "total_thought_tokens": 4,
            "total_tokens": 292,
        },
    }


def _groq_payload(model="openai/gpt-oss-120b", text='{"risk_level":"LOW"}'):
    return {
        "id": "native-id-must-not-enter-ordinary-record",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 18,
            "completion_tokens": 9,
            "total_tokens": 27,
        },
        "x_groq": {"id": "req_must_not_enter_ordinary_record"},
    }


def test_artifact_and_every_adapter_identity_are_frozen():
    adapter_set, _ = _bound()

    assert adapter_set.artifact_id == "provider_adapters_v1"
    assert adapter_set.artifact_version == "v1"
    assert adapter_set.semantic_hash == EXPECTED_ARTIFACT_HASH
    assert {item.adapter_id: item.semantic_hash for item in adapter_set.adapters} == (
        EXPECTED_ADAPTER_HASHES
    )
    assert adapter_set.provider_calls_allowed is False
    assert adapter_set.provider_calls_completed == 0
    assert adapter_set.independently_authorizes_execution is False


def test_all_six_role_mappings_bind_to_exact_frozen_adapter():
    adapter_set, mapping_set = _bound()

    for mapping in mapping_set.mappings:
        matching = [
            item
            for item in adapter_set.adapters
            if mapping.mapping_id in item.role_mapping_ids
        ]
        assert len(matching) == 1
        assert matching[0].adapter_id == mapping.adapter_id
        assert matching[0].adapter_version == mapping.adapter_version
        assert matching[0].provider == mapping.provider
        assert matching[0].api_family == mapping.api_family


def test_exact_candidate_stage_topology_matrix_is_complete():
    adapter_set, _ = _bound()
    observed = {}
    for candidate_stage in SELECTIONS:
        selection = _selection(*candidate_stage)
        assessment = assess_adapter_topology(adapter_set, selection)
        observed[candidate_stage] = assessment.eligible
        assert assessment.provider_attempt_created is False
        assert assessment.provider_call_incremented is False

    assert len(observed) == 16
    assert {key for key, value in observed.items() if not value} == {
        ("openai_unified_premium_v1", "search_retrieval"),
        ("openai_unified_balanced_v1", "search_retrieval"),
        ("gemini_unified_v1", "search_retrieval"),
        ("groq_split_v1", "search_retrieval"),
    }


@pytest.mark.parametrize(
    "candidate_id",
    (
        "openai_unified_premium_v1",
        "openai_unified_balanced_v1",
        "gemini_unified_v1",
        "groq_split_v1",
    ),
)
def test_built_in_search_topology_fails_before_attempt(candidate_id):
    adapter_set, _ = _bound()
    selection = _selection(candidate_id, "search_retrieval")
    assessment = assess_adapter_topology(adapter_set, selection)

    assert assessment.eligible is False
    assert len(assessment.blockers) == 2
    assert any("redirect context" in item for item in assessment.blockers)
    assert any("authentication context" in item for item in assessment.blockers)
    with pytest.raises(
        ProviderAdapterContractError,
        match="search_retrieval_topology_ineligible",
    ) as caught:
        require_eligible_adapter_topology(adapter_set, selection)
    assert caught.value.provider_attempt_created is False
    assert caught.value.provider_call_incremented is False


def test_openai_raw_http_envelope_extracts_one_exact_semantic_string():
    adapter_set, _ = _bound()
    selection = _selection("openai_unified_premium_v1", "text_analysis")
    text = '{"risk_level":"LOW","summary":"é"}'
    result = adapt_provider_response(
        adapter_set,
        selection,
        (capture := _capture_json(_openai_payload(text=text))),
        http_status=200,
    )

    assert result.adapter_id == "openai_responses_adapter_v1"
    assert result.semantic_content_bytes == text.encode()
    assert result.semantic_content_hash == hashlib.sha256(text.encode()).hexdigest()
    assert result.raw_provider_response_hash != result.semantic_content_hash
    assert result.content_decoded_response_bytes == capture.raw_provider_response
    assert result.provider_trace_hash == result.raw_provider_response_hash
    assert result.provider_trace_item_count == 2
    assert result.semantic_content_tag == "provider_authored_final_content"
    assert result.semantic_location == (
        "output[documented_unique_message_index].content[0].text"
    )
    assert result.usage.input_token_usage == 12
    assert result.usage.output_token_usage == 7
    assert result.usage.reasoning_usage_if_exposed == 3
    assert result.provider_request_id is None
    assert result.retrieval_trace is None
    assert text not in repr(result)


def test_openai_balanced_and_each_eligible_stage_use_same_frozen_adapter():
    adapter_set, _ = _bound()

    for stage in ("text_analysis", "search_synthesis", "visual_inspection"):
        selection = _selection("openai_unified_balanced_v1", stage)
        result = adapt_provider_response(
            adapter_set,
            selection,
            _capture_json(_openai_payload(model="gpt-5.6-terra")),
            http_status=200,
        )
        assert result.adapter_id == "openai_responses_adapter_v1"
        assert result.model == "gpt-5.6-terra"


def test_gemini_raw_http_envelope_extracts_text_and_usage_without_sdk_shortcuts():
    adapter_set, _ = _bound()
    selection = _selection("gemini_unified_v1", "visual_inspection")
    result = adapt_provider_response(
        adapter_set,
        selection,
        _capture_json(_gemini_payload()),
        http_status=200,
    )

    assert result.adapter_id == "gemini_interactions_adapter_v1"
    assert result.semantic_content_bytes == b'{"findings":[]}'
    assert result.semantic_location == (
        "steps[documented_unique_model_output_index].content[0].text"
    )
    assert result.usage.input_token_usage == 268
    assert result.usage.output_token_usage == 20
    assert result.usage.reasoning_usage_if_exposed == 4
    assert result.usage.image_usage_if_exposed == 258
    assert result.provider_request_id is None


def test_groq_text_and_vision_raw_http_envelopes_share_exact_chat_shape():
    adapter_set, _ = _bound()
    cases = (
        ("text_analysis", "openai/gpt-oss-120b", "groq_chat_completions_adapter_v1"),
        (
            "visual_inspection",
            "qwen/qwen3.8-27b",
            "groq_vision_chat_completions_adapter_v1",
        ),
    )

    for stage, model, adapter_id in cases:
        selection = _selection("groq_split_v1", stage)
        result = adapt_provider_response(
            adapter_set,
            selection,
            _capture_json(_groq_payload(model=model)),
            http_status=200,
        )
        assert result.adapter_id == adapter_id
        assert result.semantic_content_bytes == b'{"risk_level":"LOW"}'
        assert result.semantic_location == "choices[0].message.content"
        assert result.documented_finish_state == "stop"
        assert result.usage.input_token_usage == 18
        assert result.usage.output_token_usage == 9
        assert result.provider_request_id is None


def test_provider_ids_and_unknown_envelope_fields_do_not_enter_adapter_projection():
    adapter_set, _ = _bound()
    selection = _selection("groq_split_v1", "text_analysis")
    payload = _groq_payload()
    payload["future_unknown"] = {"secretish_provider_diagnostic": "not projected"}

    result = adapt_provider_response(
        adapter_set,
        selection,
        _capture_json(payload),
        http_status=200,
    )

    assert result.provider_request_id is None
    assert "native-id" not in repr(result)
    assert "req_must" not in repr(result)
    assert "secretish" not in repr(result)


def test_provider_response_cannot_select_or_mutate_adapter_identity():
    adapter_set, _ = _bound()
    selection = _selection("openai_unified_premium_v1", "text_analysis")
    payload = _openai_payload()
    payload["adapter_id"] = "groq_chat_completions_adapter_v1"
    payload["adapter_hash"] = "0" * 64

    result = adapt_provider_response(
        adapter_set,
        selection,
        _capture_json(payload),
        http_status=200,
    )

    assert result.adapter_id == "openai_responses_adapter_v1"
    assert result.adapter_hash == EXPECTED_ADAPTER_HASHES[result.adapter_id]


def test_duplicate_provider_envelope_key_fails_before_semantic_selection():
    adapter_set, _ = _bound()
    selection = _selection("openai_unified_premium_v1", "text_analysis")
    payload = (
        b'{"model":"gpt-5.6-sol","model":"gpt-5.6-terra",'
        b'"status":"completed","error":null,"incomplete_details":null,'
        b'"output":[],"usage":{}}'
    )

    with pytest.raises(ProviderAdapterResponseError, match="provider_envelope_json"):
        adapt_provider_response(
            adapter_set,
            selection,
            _capture_bytes(payload),
            http_status=200,
        )


@pytest.mark.parametrize(
    "mutation, expected",
    (
        ("wrong_model", "model_identity"),
        ("incomplete", "provider_terminal_state"),
        ("two_messages", "semantic_candidate_count"),
        ("two_content_parts", "semantic_candidate_count"),
        ("wrong_content_type", "semantic_content_type"),
        ("negative_usage", "input_tokens"),
    ),
)
def test_openai_ambiguous_or_nonterminal_envelopes_fail_closed(mutation, expected):
    adapter_set, _ = _bound()
    selection = _selection("openai_unified_premium_v1", "text_analysis")
    payload = _openai_payload()
    if mutation == "wrong_model":
        payload["model"] = "gpt-5.6-terra"
    elif mutation == "incomplete":
        payload["status"] = "incomplete"
    elif mutation == "two_messages":
        payload["output"].append(payload["output"][1].copy())
    elif mutation == "two_content_parts":
        payload["output"][1]["content"].append(
            {"type": "output_text", "text": "{}"}
        )
    elif mutation == "wrong_content_type":
        payload["output"][1]["content"][0]["type"] = "refusal"
    else:
        payload["usage"]["input_tokens"] = -1

    with pytest.raises(ProviderAdapterResponseError, match=expected):
        adapt_provider_response(
            adapter_set,
            selection,
            _capture_json(payload),
            http_status=200,
        )


def test_gemini_multiple_model_outputs_and_errors_fail_closed():
    adapter_set, _ = _bound()
    selection = _selection("gemini_unified_v1", "text_analysis")
    payload = _gemini_payload()
    payload["steps"].append(payload["steps"][1].copy())
    with pytest.raises(ProviderAdapterResponseError, match="semantic_candidate_count"):
        adapt_provider_response(
            adapter_set,
            selection,
            _capture_json(payload),
            http_status=200,
        )

    payload = _gemini_payload()
    payload["errors"] = [{"code": "provider-error", "message": "restricted"}]
    with pytest.raises(ProviderAdapterResponseError, match="provider_terminal_state"):
        adapt_provider_response(
            adapter_set,
            selection,
            _capture_json(payload),
            http_status=200,
        )


@pytest.mark.parametrize("finish", ("length", "tool_calls", None))
def test_groq_non_stop_finish_never_becomes_partial_success(finish):
    adapter_set, _ = _bound()
    selection = _selection("groq_split_v1", "text_analysis")
    payload = _groq_payload()
    payload["choices"][0]["finish_reason"] = finish

    with pytest.raises(ProviderAdapterResponseError, match="provider_terminal_state"):
        adapt_provider_response(
            adapter_set,
            selection,
            _capture_json(payload),
            http_status=200,
        )


def test_non_200_response_is_not_parsed_as_semantic_success():
    adapter_set, _ = _bound()
    selection = _selection("groq_split_v1", "text_analysis")

    with pytest.raises(ProviderAdapterResponseError, match="http_provider_error"):
        adapt_provider_response(
            adapter_set,
            selection,
            _capture_json(_groq_payload()),
            http_status=503,
        )


def test_ineligible_compound_adapter_never_consumes_a_response():
    adapter_set, _ = _bound()
    selection = _selection("groq_split_v1", "search_retrieval")

    with pytest.raises(ProviderAdapterContractError) as caught:
        adapt_provider_response(
            adapter_set,
            selection,
            _capture_json(_groq_payload(model="groq/compound")),
            http_status=200,
        )
    assert caught.value.provider_attempt_created is False
    assert caught.value.provider_call_incremented is False


def test_stale_artifact_and_child_hashes_fail_closed():
    adapters, mappings, search, prompts, spec = _raw_artifacts()
    search_binding = bind_search_authority_v2(search, prompts, spec)
    mapping_set = bind_provider_role_mappings(mappings, search_binding)
    adapters["specification_identity"]["semantic_hash"] = "0" * 64
    with pytest.raises(ProviderAdapterContractError, match="semantic_hash"):
        bind_provider_adapters(adapters, mapping_set)

    adapters, *_ = _raw_artifacts()
    adapters["adapters"][0]["semantic_hash"] = "0" * 64
    adapters["specification_identity"]["semantic_hash"] = None
    adapters["specification_identity"]["semantic_hash"] = hashlib.sha256(
        json.dumps(
            adapters,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    with pytest.raises(
        ProviderAdapterContractError,
        match="semantic_hash|adapter_shape",
    ):
        bind_provider_adapters(adapters, mapping_set)


def test_wrong_role_mapping_adapter_reference_fails_before_attempt():
    adapter_set, _ = _bound()
    selection = _selection("openai_unified_premium_v1", "text_analysis")
    wrong_mapping = replace(
        selection.mapping,
        adapter_id="groq_chat_completions_adapter_v1",
    )
    wrong_selection = replace(selection, mapping=wrong_mapping)

    with pytest.raises(ProviderAdapterContractError, match="selection"):
        assess_adapter_topology(adapter_set, wrong_selection)
