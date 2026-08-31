"""Provider-free tests for frozen prompt-to-component manifest binding."""

from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.services.evaluation_prompt_component_binding as binding_module
from app.services.evaluation_contract_identity import (
    load_strict_contract_json,
    verify_normalization_parser_artifact,
    verify_prompt_template_artifact,
)
from app.services.evaluation_prompt_component_binding import (
    PromptComponentBindingError,
    bind_frozen_prompt_components,
)


ARTIFACT_DIRECTORY = (
    Path(__file__).parents[2] / "docs" / "testing" / "ai-evaluation"
)
PROMPT_PATH = ARTIFACT_DIRECTORY / "prompt-templates.v1.json"
SPEC_PATH = ARTIFACT_DIRECTORY / "normalization-parser.v1.json"
EXPECTED_MANIFESTS = (
    ("text_analysis", ("text_system_v1", "text_input_v1"), 17),
    ("search_retrieval", ("search_retrieval_v1",), 8),
    ("search_synthesis", ("search_synthesis_v1",), 8),
    ("visual_inspection", ("visual_system_v1", "visual_context_v1"), 10),
)


def _artifacts():
    return (
        load_strict_contract_json(PROMPT_PATH),
        load_strict_contract_json(SPEC_PATH),
    )


def _bypass_internal_identity_recomputation(monkeypatch, prompts, spec):
    prompt_identity = verify_prompt_template_artifact(prompts)
    normalization_identity = verify_normalization_parser_artifact(spec)
    monkeypatch.setattr(
        binding_module,
        "verify_prompt_template_artifact",
        lambda artifact: prompt_identity,
    )
    monkeypatch.setattr(
        binding_module,
        "verify_normalization_parser_artifact",
        lambda artifact: normalization_identity,
    )


def test_all_frozen_prompt_components_bind_to_verified_template_identities():
    prompts, spec = _artifacts()

    binding = bind_frozen_prompt_components(prompts, spec)

    assert binding.prompt_template_set_version == "v1"
    assert binding.prompt_template_set_hash == (
        "9d6c5e43acb971b3ffb2a47b69f0def142d21c971717541e007f711404603df2"
    )
    assert binding.normalization_spec_semantic_hash == (
        "8747fb7fc5ae63789e256f0268d90ea3bbce7c6481fabff41be269cf738cdd6e"
    )
    assert tuple(
        (item.manifest_name, item.ordered_template_ids, len(item.components))
        for item in binding.manifests
    ) == EXPECTED_MANIFESTS
    assert sum(len(item.components) for item in binding.manifests) == 43
    assert binding.component_binding_ready is True
    assert binding.dynamic_values_rendered is False
    assert binding.concrete_mapping_available is False
    assert binding.independently_authorizes_execution is False


def test_every_component_covers_one_exact_frozen_canonical_content_index():
    prompts, spec = _artifacts()
    binding = bind_frozen_prompt_components(prompts, spec)
    templates = {item["template_id"]: item for item in prompts["templates"]}

    bound_by_template = {}
    for manifest in binding.manifests:
        for component in manifest.components:
            bound_by_template.setdefault(component.template_id, []).append(component)
            assert component.template_sha256 == templates[component.template_id][
                "canonical_sha256"
            ]
            assert component.ordering_index >= 0

    assert tuple(bound_by_template) == tuple(prompts["template_order"])
    for template_id, components in bound_by_template.items():
        assert tuple(item.component_index for item in components) == tuple(
            range(len(templates[template_id]["canonical_content"]))
        )


def test_binding_result_is_immutable_and_detached_from_artifacts():
    prompts, spec = _artifacts()
    binding = bind_frozen_prompt_components(prompts, spec)
    original = copy.deepcopy(binding)

    prompts["templates"].clear()
    spec["provider_role_mapping_contract_v1"][
        "request_component_manifests"
    ].clear()

    assert binding == original
    with pytest.raises((AttributeError, TypeError)):
        binding.component_binding_ready = False


@pytest.mark.parametrize(
    ("target", "mutation"),
    (
        (
            "prompt",
            lambda value: value["templates"][0].__setitem__(
                "canonical_content",
                ["mutated"],
            ),
        ),
        (
            "prompt",
            lambda value: value.__setitem__("prompt_template_set_hash", "0" * 64),
        ),
        (
            "spec",
            lambda value: value["provider_role_mapping_contract_v1"][
                "request_component_manifests"
            ]["search_retrieval"]["components"][0].__setitem__(
                "template_sha256",
                "0" * 64,
            ),
        ),
        (
            "spec",
            lambda value: value["provider_role_mapping_contract_v1"][
                "template_role_model"
            ].__setitem__("prompt_template_set_hash", "0" * 64),
        ),
    ),
)
def test_any_prompt_or_manifest_identity_mutation_fails_closed(target, mutation):
    prompts, spec = _artifacts()
    mutation(prompts if target == "prompt" else spec)

    with pytest.raises(PromptComponentBindingError, match="contract_identity"):
        bind_frozen_prompt_components(prompts, spec)


@pytest.mark.parametrize(
    ("prompts", "spec"),
    (
        (None, {}),
        ([], {}),
        ({}, None),
        ({}, []),
    ),
)
def test_artifact_inputs_require_exact_object_shapes(prompts, spec):
    with pytest.raises(PromptComponentBindingError, match="contract_identity"):
        bind_frozen_prompt_components(prompts, spec)


def test_binding_preserves_the_pending_concrete_mapping_execution_boundary():
    prompts, spec = _artifacts()
    binding = bind_frozen_prompt_components(prompts, spec)
    contract = spec["provider_role_mapping_contract_v1"]

    assert contract["future_external_dependency"]["status"] == "pending_creation"
    assert contract["independently_authorizes_execution"] is False
    assert binding.concrete_mapping_available is False
    assert binding.independently_authorizes_execution is False
    assert spec["provider_calls_completed"] == 0
    assert spec["execution_boundary"]["provider_calls_allowed"] is False


def test_external_frozen_hash_pins_reject_self_consistent_replacement(monkeypatch):
    prompts, spec = _artifacts()
    prompt_identity = verify_prompt_template_artifact(prompts)
    normalization_identity = verify_normalization_parser_artifact(spec)
    monkeypatch.setattr(
        binding_module,
        "verify_prompt_template_artifact",
        lambda artifact: SimpleNamespace(
            child_hashes=prompt_identity.child_hashes,
            set_hash="0" * 64,
        ),
    )
    monkeypatch.setattr(
        binding_module,
        "verify_normalization_parser_artifact",
        lambda artifact: normalization_identity,
    )

    with pytest.raises(PromptComponentBindingError, match="prompt_component_binding"):
        bind_frozen_prompt_components(prompts, spec)


def test_binding_shape_and_component_failures_are_domain_errors(monkeypatch):
    prompts, spec = _artifacts()
    _bypass_internal_identity_recomputation(monkeypatch, prompts, spec)
    spec.pop("provider_role_mapping_contract_v1")
    with pytest.raises(PromptComponentBindingError, match="prompt_component_binding"):
        bind_frozen_prompt_components(prompts, spec)

    prompts, spec = _artifacts()
    _bypass_internal_identity_recomputation(monkeypatch, prompts, spec)
    manifest = spec["provider_role_mapping_contract_v1"][
        "request_component_manifests"
    ]["search_retrieval"]
    manifest["ordered_template_ids"] = ["other"]
    with pytest.raises(PromptComponentBindingError, match="manifest_template_order"):
        bind_frozen_prompt_components(prompts, spec)

    prompts, spec = _artifacts()
    _bypass_internal_identity_recomputation(monkeypatch, prompts, spec)
    manifest = spec["provider_role_mapping_contract_v1"][
        "request_component_manifests"
    ]["search_retrieval"]
    manifest["components"] = None
    with pytest.raises(PromptComponentBindingError, match="manifest_components"):
        bind_frozen_prompt_components(prompts, spec)

    prompts, spec = _artifacts()
    _bypass_internal_identity_recomputation(monkeypatch, prompts, spec)
    manifest = spec["provider_role_mapping_contract_v1"][
        "request_component_manifests"
    ]["search_retrieval"]
    manifest["components"][0] = None
    with pytest.raises(PromptComponentBindingError, match="manifest_components"):
        bind_frozen_prompt_components(prompts, spec)

    prompts, spec = _artifacts()
    _bypass_internal_identity_recomputation(monkeypatch, prompts, spec)
    component = spec["provider_role_mapping_contract_v1"][
        "request_component_manifests"
    ]["search_retrieval"]["components"][0]
    component.pop("content_identity")
    with pytest.raises(PromptComponentBindingError, match="manifest_components"):
        bind_frozen_prompt_components(prompts, spec)

    prompts, spec = _artifacts()
    _bypass_internal_identity_recomputation(monkeypatch, prompts, spec)
    component = spec["provider_role_mapping_contract_v1"][
        "request_component_manifests"
    ]["search_retrieval"]["components"][0]
    component["component_id"] = False
    with pytest.raises(PromptComponentBindingError, match="manifest_components"):
        bind_frozen_prompt_components(prompts, spec)

    prompts, spec = _artifacts()
    _bypass_internal_identity_recomputation(monkeypatch, prompts, spec)
    component = spec["provider_role_mapping_contract_v1"][
        "request_component_manifests"
    ]["search_retrieval"]["components"][0]
    component["content_identity"] = "other"
    with pytest.raises(
        PromptComponentBindingError,
        match="manifest_content_identity",
    ):
        bind_frozen_prompt_components(prompts, spec)


def test_template_block_coverage_and_global_order_fail_closed(monkeypatch):
    prompts, spec = _artifacts()
    _bypass_internal_identity_recomputation(monkeypatch, prompts, spec)
    manifest = spec["provider_role_mapping_contract_v1"][
        "request_component_manifests"
    ]["text_analysis"]
    manifest["components"] = manifest["components"][:14]
    with pytest.raises(PromptComponentBindingError, match="manifest_template_order"):
        bind_frozen_prompt_components(prompts, spec)

    prompts, spec = _artifacts()
    _bypass_internal_identity_recomputation(monkeypatch, prompts, spec)
    manifest = spec["provider_role_mapping_contract_v1"][
        "request_component_manifests"
    ]["text_analysis"]
    system_hash = manifest["components"][0]["template_sha256"]
    final = manifest["components"][-1]
    final["template_id"] = "text_system_v1"
    final["template_sha256"] = system_hash
    final["component_index"] = 14
    final["content_identity"] = f"{system_hash}:canonical_content[14]"
    with pytest.raises(PromptComponentBindingError, match="manifest_template_order"):
        bind_frozen_prompt_components(prompts, spec)

    prompts, spec = _artifacts()
    _bypass_internal_identity_recomputation(monkeypatch, prompts, spec)
    prompts["templates"][0]["canonical_content"] = "not-an-array"
    with pytest.raises(
        PromptComponentBindingError,
        match="manifest_component_coverage",
    ):
        bind_frozen_prompt_components(prompts, spec)

    prompts, spec = _artifacts()
    _bypass_internal_identity_recomputation(monkeypatch, prompts, spec)
    prompts["template_order"].reverse()
    role_templates = spec["provider_role_mapping_contract_v1"][
        "template_role_model"
    ]["templates"]
    role_templates.reverse()
    with pytest.raises(PromptComponentBindingError, match="global_template_coverage"):
        bind_frozen_prompt_components(prompts, spec)
