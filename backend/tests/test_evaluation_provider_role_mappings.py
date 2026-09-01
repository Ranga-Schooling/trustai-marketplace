"""Provider-free tests for frozen concrete provider-role mappings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.services.evaluation_provider_role_mappings as mapping_module
from app.services.evaluation_contract_identity import load_strict_contract_json
from app.services.evaluation_provider_role_mappings import (
    ConcreteProviderRoleMappingError,
    bind_provider_role_mappings,
    expected_provider_request_plan,
    select_provider_role_mapping,
    validate_provider_request_plan,
)
from app.services.evaluation_role_mapping_identity import (
    compute_provider_role_mapping_identity,
)
from app.services.evaluation_search_authority import bind_search_authority_v2


ARTIFACT_DIRECTORY = (
    Path(__file__).parents[2] / "docs" / "testing" / "ai-evaluation"
)
MAPPING_PATH = ARTIFACT_DIRECTORY / "provider-role-mappings.v1.json"
SEARCH_AUTHORITY_PATH = ARTIFACT_DIRECTORY / "search-authority.v2.json"
PROMPT_PATH = ARTIFACT_DIRECTORY / "prompt-templates.v1.json"
SPEC_PATH = ARTIFACT_DIRECTORY / "normalization-parser.v1.json"
EXPECTED_ARTIFACT_HASH = (
    "feb8921abaac76b43d81d65f250b4081793a8ed5eff9b14527ff73ced389bdf9"
)
EXPECTED_MAPPING_HASHES = {
    "openai_responses_sol_v1": (
        "8378af7ef40c05640fda77f153637b10aa196ed7dcf507b7e2637463e4e42fc0"
    ),
    "openai_responses_terra_v1": (
        "1726614cdf2959edd4125be6cb7c5098c712631a13f13820edec87681e51685d"
    ),
    "gemini_interactions_flash_v1": (
        "8900ae8cb50d6095d56b3c283c5e7d486ed6d94b4e8bc876d5e9253eaac83c2e"
    ),
    "groq_gpt_oss_chat_v1": (
        "83dc83749e17901043cb2026d0c6adacaa9a6601610fb501b9c50c97a8a3f6d6"
    ),
    "groq_baseline_chat_v1": (
        "f9034ce72afd00be0e60ae7e5a3c4dad713fac0d45e5ec97efb177721f164ce1"
    ),
    "groq_compound_chat_v1": (
        "7301d3def1841bbce445fd5f0565adbe74c9628fe257feda47c2003a9e565667"
    ),
    "groq_qwen_vision_chat_v1": (
        "2969a59036227fa88497b83f0a2053627b23ae8e98bf9c164cbadd1c18bae322"
    ),
}
SELECTIONS = (
    (
        "openai_unified_premium_v1",
        "OpenAI",
        "gpt-5.6-sol",
        "Responses API",
        "text_analysis",
        "single_call_text",
        "openai_responses_sol_v1",
    ),
    (
        "openai_unified_premium_v1",
        "OpenAI",
        "gpt-5.6-sol",
        "Responses API",
        "search_retrieval",
        "two_call_search_retrieval",
        "openai_responses_sol_v1",
    ),
    (
        "openai_unified_premium_v1",
        "OpenAI",
        "gpt-5.6-sol",
        "Responses API",
        "search_synthesis",
        "two_call_search_synthesis",
        "openai_responses_sol_v1",
    ),
    (
        "openai_unified_premium_v1",
        "OpenAI",
        "gpt-5.6-sol",
        "Responses API",
        "visual_inspection",
        "single_call_visual",
        "openai_responses_sol_v1",
    ),
    (
        "openai_unified_balanced_v1",
        "OpenAI",
        "gpt-5.6-terra",
        "Responses API",
        "text_analysis",
        "single_call_text",
        "openai_responses_terra_v1",
    ),
    (
        "openai_unified_balanced_v1",
        "OpenAI",
        "gpt-5.6-terra",
        "Responses API",
        "search_retrieval",
        "two_call_search_retrieval",
        "openai_responses_terra_v1",
    ),
    (
        "openai_unified_balanced_v1",
        "OpenAI",
        "gpt-5.6-terra",
        "Responses API",
        "search_synthesis",
        "two_call_search_synthesis",
        "openai_responses_terra_v1",
    ),
    (
        "openai_unified_balanced_v1",
        "OpenAI",
        "gpt-5.6-terra",
        "Responses API",
        "visual_inspection",
        "single_call_visual",
        "openai_responses_terra_v1",
    ),
    (
        "gemini_unified_v1",
        "Google Gemini",
        "gemini-3.7-flash",
        "Gemini Interactions API v1beta with Api-Revision 2026-05-20",
        "text_analysis",
        "single_call_text",
        "gemini_interactions_flash_v1",
    ),
    (
        "gemini_unified_v1",
        "Google Gemini",
        "gemini-3.7-flash",
        "Gemini Interactions API v1beta with Api-Revision 2026-05-20",
        "search_retrieval",
        "two_call_search_retrieval",
        "gemini_interactions_flash_v1",
    ),
    (
        "gemini_unified_v1",
        "Google Gemini",
        "gemini-3.7-flash",
        "Gemini Interactions API v1beta with Api-Revision 2026-05-20",
        "search_synthesis",
        "two_call_search_synthesis",
        "gemini_interactions_flash_v1",
    ),
    (
        "gemini_unified_v1",
        "Google Gemini",
        "gemini-3.7-flash",
        "Gemini Interactions API v1beta with Api-Revision 2026-05-20",
        "visual_inspection",
        "single_call_visual",
        "gemini_interactions_flash_v1",
    ),
    (
        "groq_split_v1",
        "Groq",
        "openai/gpt-oss-120b",
        "Chat Completions API",
        "text_analysis",
        "single_call_text",
        "groq_gpt_oss_chat_v1",
    ),
    (
        "groq_split_v1",
        "Groq",
        "groq/compound",
        "Chat Completions API with Compound",
        "search_retrieval",
        "two_call_search_retrieval",
        "groq_compound_chat_v1",
    ),
    (
        "groq_split_v1",
        "Groq",
        "openai/gpt-oss-120b",
        "Chat Completions API",
        "search_synthesis",
        "two_call_search_synthesis",
        "groq_gpt_oss_chat_v1",
    ),
    (
        "groq_split_v1",
        "Groq",
        "qwen/qwen3.8-27b",
        "Chat Completions API with vision content",
        "visual_inspection",
        "single_call_visual",
        "groq_qwen_vision_chat_v1",
    ),
    (
        "baseline_current_text_v1",
        "Groq",
        "openai/gpt-oss-120b",
        "Chat Completions API",
        "text_analysis",
        "single_call_text",
        "groq_baseline_chat_v1",
    ),
)


def _raw_artifacts():
    return (
        load_strict_contract_json(MAPPING_PATH),
        load_strict_contract_json(SEARCH_AUTHORITY_PATH),
        load_strict_contract_json(PROMPT_PATH),
        load_strict_contract_json(SPEC_PATH),
    )


def _bound_set():
    mappings, search, prompts, spec = _raw_artifacts()
    authority = bind_search_authority_v2(search, prompts, spec)
    return bind_provider_role_mappings(mappings, authority)


def _rehash_mapping(raw_mapping):
    envelope_bytes = json.dumps(
        raw_mapping["envelope"],
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    raw_mapping["semantic_hash"] = compute_provider_role_mapping_identity(
        envelope_bytes
    ).semantic_hash


def test_artifact_binds_exact_current_candidate_and_mapping_inventory():
    mapping_set = _bound_set()

    assert mapping_set.artifact_id == "provider_role_mappings_v1"
    assert mapping_set.artifact_version == "v1"
    assert mapping_set.semantic_hash == EXPECTED_ARTIFACT_HASH
    assert tuple(item.mapping_id for item in mapping_set.mappings) == tuple(
        EXPECTED_MAPPING_HASHES
    )
    assert {
        item.mapping_id: item.semantic_hash for item in mapping_set.mappings
    } == EXPECTED_MAPPING_HASHES
    assert mapping_set.provider_calls_allowed is False
    assert mapping_set.provider_calls_completed == 0
    assert mapping_set.independently_authorizes_execution is False


def test_every_mapping_identity_is_independently_recomputed():
    raw, *_ = _raw_artifacts()

    for mapping in raw["mappings"]:
        envelope_bytes = json.dumps(
            mapping["envelope"],
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        identity = compute_provider_role_mapping_identity(envelope_bytes)
        assert identity.mapping_id == mapping["mapping_id"]
        assert identity.mapping_version == mapping["mapping_version"]
        assert identity.semantic_hash == mapping["semantic_hash"]


@pytest.mark.parametrize(
    (
        "candidate_id",
        "provider",
        "model_id",
        "api_family",
        "workload_stage",
        "topology_id",
        "mapping_id",
    ),
    SELECTIONS,
)
def test_exact_candidate_model_api_workload_and_topology_select_one_mapping(
    candidate_id,
    provider,
    model_id,
    api_family,
    workload_stage,
    topology_id,
    mapping_id,
):
    selection = select_provider_role_mapping(
        _bound_set(),
        candidate_id=candidate_id,
        provider=provider,
        model_id=model_id,
        api_family=api_family,
        workload_stage=workload_stage,
        topology_id=topology_id,
    )

    assert selection.mapping.mapping_id == mapping_id
    assert selection.provider_attempt_created is False
    assert selection.provider_call_incremented is False
    assert selection.independently_authorizes_execution is False
    plan = expected_provider_request_plan(selection)
    assessment = validate_provider_request_plan(selection, plan)
    assert assessment.conformant is True
    assert assessment.mapping_hash == EXPECTED_MAPPING_HASHES[mapping_id]
    assert assessment.provider_attempt_created is False
    assert assessment.provider_call_incremented is False


@pytest.mark.parametrize(
    ("index", "replacement"),
    (
        (0, "wrong_candidate"),
        (1, "wrong_provider"),
        (2, "wrong_model"),
        (3, "wrong_api"),
        (4, "wrong_workload"),
        (5, "wrong_topology"),
    ),
)
def test_selection_fails_closed_for_every_mismatched_dimension(index, replacement):
    values = list(SELECTIONS[0][:-1])
    values[index] = replacement

    with pytest.raises(ConcreteProviderRoleMappingError, match="mapping_selection"):
        select_provider_role_mapping(
            _bound_set(),
            candidate_id=values[0],
            provider=values[1],
            model_id=values[2],
            api_family=values[3],
            workload_stage=values[4],
            topology_id=values[5],
        )


def test_current_baseline_mapping_is_text_only():
    with pytest.raises(ConcreteProviderRoleMappingError, match="mapping_selection"):
        select_provider_role_mapping(
            _bound_set(),
            candidate_id="baseline_current_text_v1",
            provider="Groq",
            model_id="openai/gpt-oss-120b",
            api_family="Chat Completions API",
            workload_stage="search_synthesis",
            topology_id="two_call_search_synthesis",
        )


def test_current_baseline_preserves_json_object_response_mode():
    values = SELECTIONS[-1][:-1]
    selection = select_provider_role_mapping(
        _bound_set(),
        candidate_id=values[0],
        provider=values[1],
        model_id=values[2],
        api_family=values[3],
        workload_stage=values[4],
        topology_id=values[5],
    )

    assert selection.workload_binding.schema_placement == (
        "response_format json_object; harness validates text_output_schema_v1"
    )


@pytest.mark.parametrize(
    "mutation",
    (
        lambda plan: plan.__setitem__("mapping_hash", "0" * 64),
        lambda plan: plan.__setitem__("model_id", "other"),
        lambda plan: plan["ordered_native_segments"].reverse(),
        lambda plan: plan["ordered_native_segments"].pop(0),
        lambda plan: plan["ordered_native_segments"][1].__setitem__(
            "authority_class", "authoritative_instruction"
        ),
        lambda plan: plan.__setitem__("schema_placement", "other"),
        lambda plan: plan.__setitem__("search_tool_placement", "other"),
        lambda plan: plan.__setitem__("runtime_response", "provider-controlled"),
    ),
)
def test_request_plan_is_exact_and_response_cannot_mutate_it(mutation):
    values = SELECTIONS[1][:-1]
    selection = select_provider_role_mapping(
        _bound_set(),
        candidate_id=values[0],
        provider=values[1],
        model_id=values[2],
        api_family=values[3],
        workload_stage=values[4],
        topology_id=values[5],
    )
    plan = expected_provider_request_plan(selection)
    mutation(plan)

    with pytest.raises(ConcreteProviderRoleMappingError, match="request_plan"):
        validate_provider_request_plan(selection, plan)


@pytest.mark.parametrize(
    ("mutator", "error"),
    (
        (
            lambda artifact: artifact["mappings"][0]["envelope"]["content"][
                "workload_bindings"
            ][0]["ordered_native_segments"][1].__setitem__(
                "authority_class", "authoritative_instruction"
            ),
            "authority_or_order",
        ),
        (
            lambda artifact: artifact["mappings"][0]["envelope"]["content"][
                "workload_bindings"
            ][1]["ordered_native_segments"][0].__setitem__(
                "source", "search_retrieval_v2_untrusted_target"
            ),
            "authority_or_order",
        ),
        (
            lambda artifact: artifact["mappings"][0]["envelope"]["content"][
                "workload_bindings"
            ][1].__setitem__("search_tool_placement", None),
            "search_placement",
        ),
        (
            lambda artifact: artifact["mappings"][0]["envelope"]["content"][
                "workload_bindings"
            ][3].__setitem__("visual_media_placement", None),
            "visual_placement",
        ),
        (
            lambda artifact: artifact["mappings"][0]["envelope"]["content"][
                "workload_bindings"
            ][0].__setitem__("schema_placement", "other"),
            "schema_placement",
        ),
    ),
)
def test_authority_schema_media_and_search_weakening_fail_closed(
    monkeypatch,
    mutator,
    error,
):
    raw, search, prompts, spec = _raw_artifacts()
    mutator(raw)
    _rehash_mapping(raw["mappings"][0])
    monkeypatch.setattr(
        mapping_module,
        "_verify_artifact_hash",
        lambda artifact: EXPECTED_ARTIFACT_HASH,
    )
    expected_hashes = dict(mapping_module._EXPECTED_MAPPING_HASHES)
    expected_hashes[raw["mappings"][0]["mapping_id"]] = raw["mappings"][0][
        "semantic_hash"
    ]
    monkeypatch.setattr(
        mapping_module,
        "_EXPECTED_MAPPING_HASHES",
        expected_hashes,
    )
    authority = bind_search_authority_v2(search, prompts, spec)

    with pytest.raises(ConcreteProviderRoleMappingError, match=error):
        bind_provider_role_mappings(raw, authority)


def test_official_evidence_and_execution_boundary_are_exact(monkeypatch):
    raw, search, prompts, spec = _raw_artifacts()
    authority = bind_search_authority_v2(search, prompts, spec)
    assert [item["evidence_id"] for item in raw["official_documentation_evidence"]] == [
        "openai_responses_2026_08_31",
        "gemini_interactions_2026_08_31",
        "groq_chat_compound_2026_08_31",
    ]
    assert all(
        item["source"].startswith("https://")
        for item in raw["official_documentation_evidence"]
    )

    raw["execution_boundary"]["provider_calls_allowed"] = True
    monkeypatch.setattr(
        mapping_module,
        "_verify_artifact_hash",
        lambda artifact: EXPECTED_ARTIFACT_HASH,
    )
    with pytest.raises(
        ConcreteProviderRoleMappingError,
        match="execution_boundary",
    ):
        bind_provider_role_mappings(raw, authority)


def test_stored_artifact_and_mapping_hashes_are_mandatory(monkeypatch):
    raw, search, prompts, spec = _raw_artifacts()
    authority = bind_search_authority_v2(search, prompts, spec)
    raw["specification_identity"]["semantic_hash"] = "0" * 64
    with pytest.raises(ConcreteProviderRoleMappingError, match="semantic_hash"):
        bind_provider_role_mappings(raw, authority)

    raw, *_ = _raw_artifacts()
    raw["mappings"][0]["semantic_hash"] = "0" * 64
    monkeypatch.setattr(
        mapping_module,
        "_verify_artifact_hash",
        lambda artifact: EXPECTED_ARTIFACT_HASH,
    )
    with pytest.raises(
        ConcreteProviderRoleMappingError,
        match="mapping_identity",
    ):
        bind_provider_role_mappings(raw, authority)
