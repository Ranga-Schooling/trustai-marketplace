"""Bind frozen prompt identities to frozen request-component manifests.

This is a static, provider-free preflight.  It verifies only committed prompt
and normalization-contract identities plus their component correspondence.
It does not render dynamic values, inspect provider-native syntax, create a
concrete mapping, or authorize execution.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.services.evaluation_contract_identity import (
    ContractIdentityError,
    verify_normalization_parser_artifact,
    verify_prompt_template_artifact,
)


_MANIFEST_TEMPLATES = (
    ("text_analysis", ("text_system_v1", "text_input_v1")),
    ("search_retrieval", ("search_retrieval_v1",)),
    ("search_synthesis", ("search_synthesis_v1",)),
    ("visual_inspection", ("visual_system_v1", "visual_context_v1")),
)
_EXPECTED_PROMPT_SET_HASH = (
    "9d6c5e43acb971b3ffb2a47b69f0def142d21c971717541e007f711404603df2"
)
_EXPECTED_NORMALIZATION_SPEC_HASH = (
    "8747fb7fc5ae63789e256f0268d90ea3bbce7c6481fabff41be269cf738cdd6e"
)


class PromptComponentBindingError(ValueError):
    """Frozen prompt and component identities do not bind exactly."""


@dataclass(frozen=True)
class BoundPromptComponent:
    """One frozen provider-visible semantic component identity."""

    component_id: str
    template_id: str
    template_sha256: str
    component_index: int
    ordering_index: int
    authority_class: str
    content_source: str
    content_identity: str
    content_integrity_rule: str


@dataclass(frozen=True)
class BoundPromptManifest:
    """One ordered workload/stage component manifest."""

    manifest_name: str
    ordered_template_ids: tuple[str, ...]
    components: tuple[BoundPromptComponent, ...]


@dataclass(frozen=True)
class PromptComponentBinding:
    """Immutable cross-contract prompt/component binding evidence."""

    prompt_template_set_version: str
    prompt_template_set_hash: str
    normalization_spec_semantic_hash: str
    manifests: tuple[BoundPromptManifest, ...]
    component_binding_ready: bool = True
    dynamic_values_rendered: bool = False
    concrete_mapping_available: bool = False
    independently_authorizes_execution: bool = False


def _verify_contract_identities(
    prompt_artifact: Any,
    normalization_spec: Any,
):
    try:
        prompt_identity = verify_prompt_template_artifact(prompt_artifact)
        normalization_identity = verify_normalization_parser_artifact(
            normalization_spec
        )
    except (ContractIdentityError, TypeError, KeyError) as exc:
        raise PromptComponentBindingError("contract_identity") from exc
    return prompt_identity, normalization_identity


def bind_frozen_prompt_components(
    prompt_artifact: dict[str, Any],
    normalization_spec: dict[str, Any],
) -> PromptComponentBinding:
    """Verify exact prompt hashes and canonical-content component coverage."""
    prompt_identity, normalization_identity = _verify_contract_identities(
        prompt_artifact,
        normalization_spec,
    )
    try:
        contract = normalization_spec["provider_role_mapping_contract_v1"]
        role_model = contract["template_role_model"]
        manifests = contract["request_component_manifests"]
        templates = {
            template["template_id"]: template
            for template in prompt_artifact["templates"]
        }
    except (KeyError, TypeError) as exc:
        raise PromptComponentBindingError("prompt_component_binding") from exc

    prompt_hashes = dict(prompt_identity.child_hashes)
    expected_manifest_names = tuple(name for name, _ in _MANIFEST_TEMPLATES)
    role_templates = role_model.get("templates")
    if (
        prompt_identity.set_hash != _EXPECTED_PROMPT_SET_HASH
        or normalization_identity.semantic_hash
        != _EXPECTED_NORMALIZATION_SPEC_HASH
        or contract.get("policy_id") != "provider_role_mapping_contract_v1"
        or contract.get("policy_version") != "v1"
        or contract.get("status") != "frozen_common_contract"
        or contract.get("provider_neutral") is not True
        or contract.get("independently_authorizes_execution") is not False
        or role_model.get("prompt_template_set_version")
        != prompt_artifact.get("prompt_template_set_version")
        or role_model.get("prompt_template_set_hash") != prompt_identity.set_hash
        or role_model.get("canonical_template_count") != len(prompt_hashes)
        or type(role_templates) is not list
        or any(not isinstance(item, Mapping) for item in role_templates)
        or tuple(item.get("template_id") for item in role_templates)
        != tuple(prompt_artifact.get("template_order", ()))
        or not isinstance(manifests, Mapping)
        or set(manifests) != set(expected_manifest_names)
    ):
        raise PromptComponentBindingError("prompt_component_binding")

    bound_manifests: list[BoundPromptManifest] = []
    globally_bound_templates: list[str] = []
    globally_seen_components: set[str] = set()
    for manifest_name, expected_template_ids in _MANIFEST_TEMPLATES:
        manifest = manifests[manifest_name]
        if tuple(manifest.get("ordered_template_ids", ())) != expected_template_ids:
            raise PromptComponentBindingError("manifest_template_order")
        components = manifest.get("components")
        if not isinstance(components, list) or not components:
            raise PromptComponentBindingError("manifest_components")

        bound_components: list[BoundPromptComponent] = []
        encountered_templates: list[str] = []
        indices_by_template: dict[str, list[int]] = {
            template_id: [] for template_id in expected_template_ids
        }
        for expected_order, component in enumerate(components):
            if not isinstance(component, Mapping):
                raise PromptComponentBindingError("manifest_components")
            try:
                component_id = component["component_id"]
                template_id = component["template_id"]
                template_sha256 = component["template_sha256"]
                component_index = component["component_index"]
                ordering_index = component["ordering_index"]
                content_source = component["content_source"]
                content_identity = component["content_identity"]
                authority_class = component["authority_class"]
                content_integrity_rule = component["content_integrity_rule"]
            except (KeyError, TypeError) as exc:
                raise PromptComponentBindingError("manifest_components") from exc
            if (
                type(component_id) is not str
                or not component_id
                or component_id in globally_seen_components
                or type(template_id) is not str
                or template_id not in indices_by_template
                or type(template_sha256) is not str
                or type(component_index) is not int
                or component_index < 0
                or type(ordering_index) is not int
                or ordering_index != expected_order
                or type(content_source) is not str
                or type(content_identity) is not str
                or type(authority_class) is not str
                or type(content_integrity_rule) is not str
                or template_sha256 != prompt_hashes.get(template_id)
            ):
                raise PromptComponentBindingError("manifest_components")
            expected_content_identity = (
                f"{template_sha256}:canonical_content[{component_index}]"
            )
            if content_source != "frozen_static_canonical_content":
                expected_content_identity += f":{content_source}"
            if content_identity != expected_content_identity:
                raise PromptComponentBindingError("manifest_content_identity")
            if not encountered_templates or encountered_templates[-1] != template_id:
                if template_id in encountered_templates:
                    raise PromptComponentBindingError("manifest_template_order")
                encountered_templates.append(template_id)
            globally_seen_components.add(component_id)
            indices_by_template[template_id].append(component_index)
            bound_components.append(
                BoundPromptComponent(
                    component_id=component_id,
                    template_id=template_id,
                    template_sha256=template_sha256,
                    component_index=component_index,
                    ordering_index=ordering_index,
                    authority_class=authority_class,
                    content_source=content_source,
                    content_identity=content_identity,
                    content_integrity_rule=content_integrity_rule,
                )
            )

        if tuple(encountered_templates) != expected_template_ids:
            raise PromptComponentBindingError("manifest_template_order")
        for template_id in expected_template_ids:
            canonical_content = templates[template_id]["canonical_content"]
            if (
                type(canonical_content) is not list
                or any(type(item) is not str for item in canonical_content)
                or indices_by_template[template_id]
                != list(range(len(canonical_content)))
            ):
                raise PromptComponentBindingError("manifest_component_coverage")
            globally_bound_templates.append(template_id)
        bound_manifests.append(
            BoundPromptManifest(
                manifest_name=manifest_name,
                ordered_template_ids=expected_template_ids,
                components=tuple(bound_components),
            )
        )

    if tuple(globally_bound_templates) != tuple(prompt_artifact["template_order"]):
        raise PromptComponentBindingError("global_template_coverage")
    return PromptComponentBinding(
        prompt_template_set_version=prompt_artifact[
            "prompt_template_set_version"
        ],
        prompt_template_set_hash=prompt_identity.set_hash,
        normalization_spec_semantic_hash=normalization_identity.semantic_hash,
        manifests=tuple(bound_manifests),
    )
