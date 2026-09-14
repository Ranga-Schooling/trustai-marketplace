"""Provider-free conformance tests for Search Authority V2."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

import app.services.evaluation_search_authority as authority_module
from app.services.evaluation_contract_identity import load_strict_contract_json
from app.services.evaluation_search_authority import (
    SearchAuthorityContractError,
    bind_search_authority_v2,
    project_search_authority_v2,
)


ARTIFACT_DIRECTORY = (
    Path(__file__).parents[2] / "docs" / "testing" / "ai-evaluation"
)
AUTHORITY_PATH = ARTIFACT_DIRECTORY / "search-authority.v2.json"
PROMPT_PATH = ARTIFACT_DIRECTORY / "prompt-templates.v1.json"
SPEC_PATH = ARTIFACT_DIRECTORY / "normalization-parser.v1.json"
EXPECTED_AUTHORITY_HASH = (
    "c682f3b3bcd7fb9e6f316a3e02a8b931576ee56f1296c462f5302acfa836f3e8"
)


def _artifacts():
    return (
        load_strict_contract_json(AUTHORITY_PATH),
        load_strict_contract_json(PROMPT_PATH),
        load_strict_contract_json(SPEC_PATH),
    )


def _component_bytes(manifest):
    return {
        item["component_id"]: f'<{item["component_id"]}>'.encode()
        for item in manifest["components"]
    }


def test_v2_binds_exact_frozen_v1_search_components_without_mutating_v1():
    authority, prompts, spec = _artifacts()

    binding = bind_search_authority_v2(authority, prompts, spec)

    assert binding.contract_id == "search_authority_contract_v2"
    assert binding.contract_version == "v2"
    assert binding.semantic_hash == EXPECTED_AUTHORITY_HASH
    assert binding.source_prompt_set_hash == (
        "9d6c5e43acb971b3ffb2a47b69f0def142d21c971717541e007f711404603df2"
    )
    assert binding.source_normalization_hash == (
        "023ad80eeb6e08e9279c22b7955ebe5d04ec9ab3cd88626ceaccc4962c41b343"
    )
    assert binding.v1_historical_status == "preserved_frozen_historical_contract"
    assert binding.v2_execution_status == "frozen_pre_execution_contract"
    assert binding.provider_calls_allowed is False
    assert binding.provider_calls_completed == 0
    assert binding.independently_authorizes_execution is False
    assert tuple((item.stage_id, item.component_count) for item in binding.stages) == (
        ("search_retrieval", 8),
        ("search_synthesis", 8),
    )


def test_v2_projects_all_trusted_instructions_before_untrusted_material():
    authority, prompts, spec = _artifacts()
    binding = bind_search_authority_v2(authority, prompts, spec)
    manifests = spec["provider_role_mapping_contract_v1"][
        "request_component_manifests"
    ]

    retrieval = project_search_authority_v2(
        binding=binding,
        stage_id="search_retrieval",
        component_content_bytes=_component_bytes(manifests["search_retrieval"]),
    )
    assert tuple(segment.authority_class for segment in retrieval.segments) == (
        "authoritative_instruction",
        "untrusted_input",
    )
    assert retrieval.segments[0].source_component_ids == (
        "search_retrieval_v1_component_0",
        "search_retrieval_v1_component_1",
        "search_retrieval_v1_component_3",
        "search_retrieval_v1_component_4",
        "search_retrieval_v1_component_5",
        "search_retrieval_v1_component_6",
        "search_retrieval_v1_component_7",
    )
    assert retrieval.segments[1].source_component_ids == (
        "search_retrieval_v1_component_2",
    )

    synthesis = project_search_authority_v2(
        binding=binding,
        stage_id="search_synthesis",
        component_content_bytes=_component_bytes(manifests["search_synthesis"]),
    )
    assert tuple(segment.authority_class for segment in synthesis.segments) == (
        "authoritative_instruction",
        "untrusted_input",
        "untrusted_retrieved_evidence",
    )
    assert synthesis.segments[0].source_component_ids == (
        "search_synthesis_v1_component_0",
        "search_synthesis_v1_component_1",
        "search_synthesis_v1_component_3",
        "search_synthesis_v1_component_5",
        "search_synthesis_v1_component_6",
        "search_synthesis_v1_component_7",
    )
    assert synthesis.segments[1].source_component_ids == (
        "search_synthesis_v1_component_2",
    )
    assert synthesis.segments[2].source_component_ids == (
        "search_synthesis_v1_component_4",
    )
    assert all(
        segment.provider_attempt_created is False
        and segment.provider_call_incremented is False
        for segment in synthesis.segments
    )


def test_v1_to_v2_traceability_is_exact_complete_and_semantically_continuous():
    authority, prompts, spec = _artifacts()
    binding = bind_search_authority_v2(authority, prompts, spec)

    assert binding.component_count == 16
    assert len({item.component_id for item in binding.traceability}) == 16
    assert all(item.content_preserved_exactly for item in binding.traceability)
    assert all(item.authority_preserved for item in binding.traceability)
    assert all(not item.provider_specific_instruction_added for item in binding.traceability)
    assert all(not item.provider_information_changed for item in binding.traceability)
    assert sum(item.relocated_before_untrusted_data for item in binding.traceability) == 9


def test_all_candidates_have_officially_evidenced_v2_representability():
    authority, prompts, spec = _artifacts()
    binding = bind_search_authority_v2(authority, prompts, spec)

    assert tuple(item.candidate_id for item in binding.representability) == (
        "openai_unified_premium_v1",
        "openai_unified_balanced_v1",
        "gemini_unified_v1",
        "groq_split_v1",
    )
    assert all(item.representable is True for item in binding.representability)
    assert all(item.later_trusted_instruction_injection_required is False for item in binding.representability)
    assert all(item.official_documentation_urls for item in binding.representability)


def test_adversarial_inventory_keeps_all_attack_content_untrusted():
    authority, prompts, spec = _artifacts()
    binding = bind_search_authority_v2(authority, prompts, spec)

    assert tuple(item.vector_id for item in binding.adversarial_vectors) == tuple(
        f"A{index}" for index in range(1, 12)
    )
    assert all(item.content_authority == "untrusted" for item in binding.adversarial_vectors)
    assert all(item.trusted_contract_remains_authoritative for item in binding.adversarial_vectors)
    assert all(item.expected_conformance == "pass" for item in binding.adversarial_vectors)


@pytest.mark.parametrize(
    ("mutation", "error"),
    (
        (
            lambda value: value["workload_layouts"]["search_synthesis"][
                "logical_segments"
            ][0]["source_component_ids"].pop(),
            "component_coverage",
        ),
        (
            lambda value: value["workload_layouts"]["search_synthesis"][
                "logical_segments"
            ][2].__setitem__("authority_class", "authoritative_instruction"),
            "trusted_before_untrusted",
        ),
        (
            lambda value: value["workload_layouts"]["search_retrieval"][
                "logical_segments"
            ].reverse(),
            "trusted_before_untrusted",
        ),
        (
            lambda value: value["v1_to_v2_traceability"][0].__setitem__(
                "content_preserved_exactly", False
            ),
            "traceability",
        ),
        (
            lambda value: value["cross_provider_representability"][0].__setitem__(
                "representable", False
            ),
            "representability",
        ),
    ),
)
def test_semantic_or_security_weakening_fails_closed(monkeypatch, mutation, error):
    authority, prompts, spec = _artifacts()
    mutation(authority)
    monkeypatch.setattr(
        authority_module,
        "_verify_semantic_hash",
        lambda artifact: EXPECTED_AUTHORITY_HASH,
    )

    with pytest.raises(SearchAuthorityContractError, match=error):
        bind_search_authority_v2(authority, prompts, spec)


def test_runtime_projection_rejects_missing_extra_nonbytes_or_wrong_stage():
    authority, prompts, spec = _artifacts()
    binding = bind_search_authority_v2(authority, prompts, spec)
    manifest = spec["provider_role_mapping_contract_v1"][
        "request_component_manifests"
    ]["search_synthesis"]
    values = _component_bytes(manifest)

    for mutation in (
        lambda item: item.pop(next(iter(item))),
        lambda item: item.__setitem__("extra", b"extra"),
        lambda item: item.__setitem__(next(iter(item)), "not-bytes"),
    ):
        mutated = copy.deepcopy(values)
        mutation(mutated)
        with pytest.raises(SearchAuthorityContractError, match="component_bytes"):
            project_search_authority_v2(
                binding=binding,
                stage_id="search_synthesis",
                component_content_bytes=mutated,
            )

    with pytest.raises(SearchAuthorityContractError, match="stage_id"):
        project_search_authority_v2(
            binding=binding,
            stage_id="other",
            component_content_bytes=values,
        )


def test_stored_semantic_hash_is_verified_and_runtime_cannot_authorize_execution(
    monkeypatch,
):
    authority, prompts, spec = _artifacts()
    authority["specification_identity"]["semantic_hash"] = "0" * 64

    with pytest.raises(SearchAuthorityContractError, match="semantic_hash"):
        bind_search_authority_v2(authority, prompts, spec)

    authority, prompts, spec = _artifacts()
    authority["execution_boundary"]["provider_calls_allowed"] = True
    monkeypatch.setattr(
        authority_module,
        "_verify_semantic_hash",
        lambda artifact: EXPECTED_AUTHORITY_HASH,
    )
    with pytest.raises(SearchAuthorityContractError, match="execution_boundary"):
        bind_search_authority_v2(authority, prompts, spec)
