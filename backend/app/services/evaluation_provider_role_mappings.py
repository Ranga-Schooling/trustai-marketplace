"""Frozen concrete provider-role mapping selection and conformance.

Mappings are selected from exact candidate/provider/model/API/workload/topology
facts before an attempt exists.  The response cannot select or mutate them.
This module contains no credentials, transport client, or execution authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from app.services.evaluation_role_mapping_identity import (
    ProviderRoleMappingIdentityError,
    verify_provider_role_mapping_hash,
)
from app.services.evaluation_search_authority import (
    SearchAuthorityBinding,
)


_MAPPING_ORDER = (
    "openai_responses_sol_v1",
    "openai_responses_terra_v1",
    "gemini_interactions_flash_v1",
    "groq_gpt_oss_chat_v1",
    "groq_compound_chat_v1",
    "groq_qwen_vision_chat_v1",
)
_EXPECTED_ARTIFACT_HASH = (
    "ba246ab6e9ecdcd7bee09b40364508e880596c97bbffd856052f0c4b64b01766"
)
_EXPECTED_MAPPING_HASHES = {
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
    "groq_compound_chat_v1": (
        "7301d3def1841bbce445fd5f0565adbe74c9628fe257feda47c2003a9e565667"
    ),
    "groq_qwen_vision_chat_v1": (
        "2969a59036227fa88497b83f0a2053627b23ae8e98bf9c164cbadd1c18bae322"
    ),
}
_EXPECTED_COVERAGE = {
    "openai_unified_premium_v1": {
        "text_analysis": ("gpt-5.6-sol", "single_call_text"),
        "search_retrieval": ("gpt-5.6-sol", "two_call_search_retrieval"),
        "search_synthesis": ("gpt-5.6-sol", "two_call_search_synthesis"),
        "visual_inspection": ("gpt-5.6-sol", "single_call_visual"),
    },
    "openai_unified_balanced_v1": {
        "text_analysis": ("gpt-5.6-terra", "single_call_text"),
        "search_retrieval": ("gpt-5.6-terra", "two_call_search_retrieval"),
        "search_synthesis": ("gpt-5.6-terra", "two_call_search_synthesis"),
        "visual_inspection": ("gpt-5.6-terra", "single_call_visual"),
    },
    "gemini_unified_v1": {
        "text_analysis": ("gemini-3.7-flash", "single_call_text"),
        "search_retrieval": (
            "gemini-3.7-flash",
            "two_call_search_retrieval",
        ),
        "search_synthesis": (
            "gemini-3.7-flash",
            "two_call_search_synthesis",
        ),
        "visual_inspection": ("gemini-3.7-flash", "single_call_visual"),
    },
    "groq_split_v1": {
        "text_analysis": ("openai/gpt-oss-120b", "single_call_text"),
        "search_retrieval": ("groq/compound", "two_call_search_retrieval"),
        "search_synthesis": (
            "openai/gpt-oss-120b",
            "two_call_search_synthesis",
        ),
        "visual_inspection": ("qwen/qwen3.8-27b", "single_call_visual"),
    },
}
_AUTHORITY_CLASSES = {
    "authoritative_instruction",
    "untrusted_input",
    "untrusted_context",
    "untrusted_retrieved_evidence",
    "visual_media",
}
_EXPECTED_SEGMENTS = {
    "text_analysis": (
        (
            "authoritative_instruction components in exact manifest order",
            "authoritative_instruction",
        ),
        (
            "untrusted_input components in exact manifest order",
            "untrusted_input",
        ),
    ),
    "search_retrieval": (
        (
            "search_retrieval_v2_trusted_instructions",
            "authoritative_instruction",
        ),
        ("search_retrieval_v2_untrusted_target", "untrusted_input"),
    ),
    "search_synthesis": (
        (
            "search_synthesis_v2_trusted_instructions",
            "authoritative_instruction",
        ),
        ("search_synthesis_v2_untrusted_target", "untrusted_input"),
        (
            "search_synthesis_v2_untrusted_evidence",
            "untrusted_retrieved_evidence",
        ),
    ),
    "visual_inspection": (
        (
            "authoritative_instruction components in exact manifest order",
            "authoritative_instruction",
        ),
        (
            "untrusted_context components in exact manifest order",
            "untrusted_context",
        ),
        ("frozen local normalized image bytes", "visual_media"),
    ),
}
_EXPECTED_SCHEMA = {
    "text_analysis": "text_output_schema_v1",
    "search_synthesis": "search_output_schema_v1",
    "visual_inspection": "visual_output_schema_v1",
}
_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ConcreteProviderRoleMappingError(ValueError):
    """A mapping artifact, selection, or request placement fails closed."""

    provider_attempt_created = False
    provider_call_incremented = False


@dataclass(frozen=True)
class NativeSegmentBinding:
    ordinal: int
    source: str
    authority_class: str
    native_surface: str


@dataclass(frozen=True)
class WorkloadRoleBinding:
    workload_stage: str
    topology_id: str
    authority_contract_ref: str
    segments: tuple[NativeSegmentBinding, ...]
    schema_placement: str
    visual_media_placement: str | None
    search_tool_placement: str | None


@dataclass(frozen=True)
class FrozenProviderRoleMapping:
    mapping_id: str
    mapping_version: str
    semantic_hash: str
    adapter_id: str
    adapter_version: str
    provider: str
    api_family: str
    candidate_ids: tuple[str, ...]
    model_ids: tuple[str, ...]
    workload_bindings: tuple[WorkloadRoleBinding, ...]
    official_evidence_refs: tuple[str, ...]
    response_mutation_allowed: bool = False
    independently_authorizes_execution: bool = False


@dataclass(frozen=True)
class ProviderRoleMappingSet:
    artifact_id: str
    artifact_version: str
    semantic_hash: str
    mappings: tuple[FrozenProviderRoleMapping, ...]
    provider_calls_allowed: bool = False
    provider_calls_completed: int = 0
    independently_authorizes_execution: bool = False


@dataclass(frozen=True)
class ProviderRoleMappingSelection:
    mapping: FrozenProviderRoleMapping
    workload_binding: WorkloadRoleBinding
    candidate_id: str
    model_id: str
    provider_attempt_created: bool = False
    provider_call_incremented: bool = False
    independently_authorizes_execution: bool = False


@dataclass(frozen=True)
class ProviderRequestPlanAssessment:
    conformant: bool
    mapping_id: str
    mapping_version: str
    mapping_hash: str
    workload_stage: str
    topology_id: str
    segment_count: int
    provider_attempt_created: bool = False
    provider_call_incremented: bool = False
    independently_authorizes_execution: bool = False


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ConcreteProviderRoleMappingError("semantic_hash") from exc


def _verify_artifact_hash(artifact: Mapping[str, Any]) -> str:
    try:
        identity = artifact["specification_identity"]
        stored = identity["semantic_hash"]
    except (KeyError, TypeError) as exc:
        raise ConcreteProviderRoleMappingError("semantic_hash") from exc
    if (
        type(stored) is not str
        or _LOWER_SHA256.fullmatch(stored) is None
        or identity.get("semantic_hash_excluded_json_pointers")
        != ["/specification_identity/semantic_hash"]
    ):
        raise ConcreteProviderRoleMappingError("semantic_hash")
    semantic_copy = json.loads(_canonical_bytes(artifact))
    semantic_copy["specification_identity"]["semantic_hash"] = None
    computed = hashlib.sha256(_canonical_bytes(semantic_copy)).hexdigest()
    if computed != stored or computed != _EXPECTED_ARTIFACT_HASH:
        raise ConcreteProviderRoleMappingError("semantic_hash")
    return computed


def _validate_execution_boundary(artifact: Mapping[str, Any]) -> None:
    boundary = artifact.get("execution_boundary")
    expected = {
        "execution_state": "blocked_pre_execution",
        "provider_calls_allowed": False,
        "pilot_calls_allowed": False,
        "scored_calls_allowed": False,
        "provider_calls_completed": 0,
        "pilot_calls_completed": 0,
        "scored_calls_completed": 0,
        "winner_selected": False,
        "independently_authorizes_execution": False,
    }
    if not isinstance(boundary, Mapping) or any(
        boundary.get(key) != value for key, value in expected.items()
    ):
        raise ConcreteProviderRoleMappingError("execution_boundary")


def _bind_segments(raw: Any) -> tuple[NativeSegmentBinding, ...]:
    if type(raw) is not list or not raw:
        raise ConcreteProviderRoleMappingError("native_segments")
    result: list[NativeSegmentBinding] = []
    for ordinal, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ConcreteProviderRoleMappingError("native_segments")
        source = item.get("source")
        authority = item.get("authority_class")
        surface = item.get("native_surface")
        if (
            item.get("ordinal") != ordinal
            or type(source) is not str
            or not source
            or authority not in _AUTHORITY_CLASSES
            or type(surface) is not str
            or not surface
        ):
            raise ConcreteProviderRoleMappingError("native_segments")
        result.append(
            NativeSegmentBinding(
                ordinal=ordinal,
                source=source,
                authority_class=authority,
                native_surface=surface,
            )
        )
    if result[0].authority_class != "authoritative_instruction":
        raise ConcreteProviderRoleMappingError("trusted_segment")
    if any(
        item.authority_class != "authoritative_instruction"
        and ("system" in item.native_surface or item.native_surface == "instructions")
        for item in result
    ):
        raise ConcreteProviderRoleMappingError("untrusted_promoted")
    return tuple(result)


def _validate_stage_binding(
    raw: Mapping[str, Any],
    search_authority: SearchAuthorityBinding,
) -> WorkloadRoleBinding:
    try:
        stage = raw["workload_stage"]
        topology = raw["topology_id"]
        contract_ref = raw["authority_contract_ref"]
        schema = raw["schema_placement"]
        visual = raw["visual_media_placement"]
        search = raw["search_tool_placement"]
    except (KeyError, TypeError) as exc:
        raise ConcreteProviderRoleMappingError("workload_binding") from exc
    if stage not in {
        "text_analysis",
        "search_retrieval",
        "search_synthesis",
        "visual_inspection",
    }:
        raise ConcreteProviderRoleMappingError("workload_binding")
    segments = _bind_segments(raw.get("ordered_native_segments"))
    if tuple(
        (item.source, item.authority_class) for item in segments
    ) != _EXPECTED_SEGMENTS[stage]:
        raise ConcreteProviderRoleMappingError("authority_or_order")
    if stage.startswith("search_"):
        expected_ref = f"search_authority_contract_v2.workload_layouts.{stage}"
        if (
            contract_ref != expected_ref
            or search_authority.contract_version != "v2"
            or search_authority.v2_execution_status
            != "frozen_pre_execution_contract"
        ):
            raise ConcreteProviderRoleMappingError("search_authority_binding")
    elif contract_ref != (
        "provider_role_mapping_contract_v1.request_component_manifests."
        f"{stage}"
    ):
        raise ConcreteProviderRoleMappingError("v1_authority_binding")
    if stage == "search_retrieval":
        if schema != "none_harness_assembles_retrieval_evidence_bundle_v1":
            raise ConcreteProviderRoleMappingError("schema_placement")
        if type(search) is not str or "search" not in search:
            raise ConcreteProviderRoleMappingError("search_placement")
    else:
        expected_schema = _EXPECTED_SCHEMA[stage]
        if type(schema) is not str or expected_schema not in schema:
            raise ConcreteProviderRoleMappingError("schema_placement")
        if search is not None:
            raise ConcreteProviderRoleMappingError("search_placement")
    if stage == "visual_inspection":
        if type(visual) is not str or not visual:
            raise ConcreteProviderRoleMappingError("visual_placement")
    elif visual is not None:
        raise ConcreteProviderRoleMappingError("visual_placement")
    return WorkloadRoleBinding(
        workload_stage=stage,
        topology_id=topology,
        authority_contract_ref=contract_ref,
        segments=segments,
        schema_placement=schema,
        visual_media_placement=visual,
        search_tool_placement=search,
    )


def _bind_mapping(
    raw: Mapping[str, Any],
    evidence_ids: set[str],
    search_authority: SearchAuthorityBinding,
) -> FrozenProviderRoleMapping:
    try:
        mapping_id = raw["mapping_id"]
        mapping_version = raw["mapping_version"]
        stored_hash = raw["semantic_hash"]
        envelope = raw["envelope"]
        evidence_refs = raw["official_evidence_refs"]
        envelope_bytes = _canonical_bytes(envelope)
        identity = verify_provider_role_mapping_hash(envelope_bytes, stored_hash)
        content = envelope["content"]
        adapter = content["applicable_adapter"]
        workload_bindings = content["workload_bindings"]
    except (
        KeyError,
        TypeError,
        ProviderRoleMappingIdentityError,
    ) as exc:
        raise ConcreteProviderRoleMappingError("mapping_identity") from exc
    if (
        identity.mapping_id != mapping_id
        or identity.mapping_version != mapping_version
        or stored_hash != _EXPECTED_MAPPING_HASHES.get(mapping_id)
        or type(evidence_refs) is not list
        or not evidence_refs
        or any(ref not in evidence_ids for ref in evidence_refs)
        or content.get("selection_time") != "before physical attempt creation"
        or content.get("response_mutation_allowed") is not False
        or type(content.get("candidate_ids")) is not list
        or not content["candidate_ids"]
        or type(content.get("model_ids")) is not list
        or not content["model_ids"]
        or type(workload_bindings) is not list
        or not workload_bindings
    ):
        raise ConcreteProviderRoleMappingError("mapping_identity")
    bindings = tuple(
        _validate_stage_binding(item, search_authority)
        for item in workload_bindings
    )
    if len({item.workload_stage for item in bindings}) != len(bindings):
        raise ConcreteProviderRoleMappingError("duplicate_workload_binding")
    return FrozenProviderRoleMapping(
        mapping_id=mapping_id,
        mapping_version=mapping_version,
        semantic_hash=stored_hash,
        adapter_id=adapter["adapter_id"],
        adapter_version=adapter["adapter_version"],
        provider=content["provider"],
        api_family=content["api_family"],
        candidate_ids=tuple(content["candidate_ids"]),
        model_ids=tuple(content["model_ids"]),
        workload_bindings=bindings,
        official_evidence_refs=tuple(evidence_refs),
    )


def _verify_complete_coverage(mappings: tuple[FrozenProviderRoleMapping, ...]) -> None:
    actual: dict[str, dict[str, list[tuple[str, str]]]] = {}
    for mapping in mappings:
        for candidate_id in mapping.candidate_ids:
            for binding in mapping.workload_bindings:
                actual.setdefault(candidate_id, {}).setdefault(
                    binding.workload_stage,
                    [],
                ).append((mapping.model_ids[0], binding.topology_id))
    if set(actual) != set(_EXPECTED_COVERAGE):
        raise ConcreteProviderRoleMappingError("candidate_coverage")
    for candidate_id, expected_stages in _EXPECTED_COVERAGE.items():
        if set(actual[candidate_id]) != set(expected_stages):
            raise ConcreteProviderRoleMappingError("candidate_coverage")
        for stage, expected in expected_stages.items():
            if actual[candidate_id][stage] != [expected]:
                raise ConcreteProviderRoleMappingError("candidate_coverage")


def bind_provider_role_mappings(
    artifact: dict[str, Any],
    search_authority: SearchAuthorityBinding,
) -> ProviderRoleMappingSet:
    """Verify exact concrete mappings, evidence references, and coverage."""
    if not isinstance(artifact, Mapping) or type(search_authority) is not SearchAuthorityBinding:
        raise ConcreteProviderRoleMappingError("artifact")
    semantic_hash = _verify_artifact_hash(artifact)
    if (
        artifact.get("artifact_id") != "provider_role_mappings_v1"
        or artifact.get("artifact_version") != "v1"
        or artifact.get("status") != "frozen_pre_execution_contract"
        or artifact.get("provider_neutral_common_contract")
        != "normalization-parser.v1.json#/provider_role_mapping_contract_v1"
        or artifact.get("search_authority_contract")
        != "search-authority.v2.json@v2"
        or tuple(artifact.get("mapping_order", ())) != _MAPPING_ORDER
    ):
        raise ConcreteProviderRoleMappingError("artifact")
    _validate_execution_boundary(artifact)
    evidence = artifact.get("official_documentation_evidence")
    if (
        type(evidence) is not list
        or len(evidence) != 3
        or any(
            not isinstance(item, Mapping)
            or item.get("observed_on") != "2026-08-31"
            or type(item.get("source")) is not str
            or not item["source"].startswith("https://")
            for item in evidence
        )
    ):
        raise ConcreteProviderRoleMappingError("official_evidence")
    evidence_ids = {item["evidence_id"] for item in evidence}
    raw_mappings = artifact.get("mappings")
    if (
        type(raw_mappings) is not list
        or tuple(item.get("mapping_id") for item in raw_mappings) != _MAPPING_ORDER
    ):
        raise ConcreteProviderRoleMappingError("mapping_inventory")
    mappings = tuple(
        _bind_mapping(item, evidence_ids, search_authority)
        for item in raw_mappings
    )
    _verify_complete_coverage(mappings)
    return ProviderRoleMappingSet(
        artifact_id="provider_role_mappings_v1",
        artifact_version="v1",
        semantic_hash=semantic_hash,
        mappings=mappings,
    )


def select_provider_role_mapping(
    mapping_set: ProviderRoleMappingSet,
    *,
    candidate_id: str,
    provider: str,
    model_id: str,
    api_family: str,
    workload_stage: str,
    topology_id: str,
) -> ProviderRoleMappingSelection:
    """Select exactly one pre-attempt mapping or fail closed."""
    if type(mapping_set) is not ProviderRoleMappingSet:
        raise ConcreteProviderRoleMappingError("mapping_set")
    matches: list[tuple[FrozenProviderRoleMapping, WorkloadRoleBinding]] = []
    for mapping in mapping_set.mappings:
        if (
            candidate_id not in mapping.candidate_ids
            or provider != mapping.provider
            or model_id not in mapping.model_ids
            or api_family != mapping.api_family
        ):
            continue
        for binding in mapping.workload_bindings:
            if (
                binding.workload_stage == workload_stage
                and binding.topology_id == topology_id
            ):
                matches.append((mapping, binding))
    if len(matches) != 1:
        raise ConcreteProviderRoleMappingError("mapping_selection")
    mapping, workload_binding = matches[0]
    return ProviderRoleMappingSelection(
        mapping=mapping,
        workload_binding=workload_binding,
        candidate_id=candidate_id,
        model_id=model_id,
    )


def expected_provider_request_plan(
    selection: ProviderRoleMappingSelection,
) -> dict[str, Any]:
    """Return the exact immutable-semantic placement plan, with no content."""
    if type(selection) is not ProviderRoleMappingSelection:
        raise ConcreteProviderRoleMappingError("selection")
    binding = selection.workload_binding
    mapping = selection.mapping
    return {
        "mapping_id": mapping.mapping_id,
        "mapping_version": mapping.mapping_version,
        "mapping_hash": mapping.semantic_hash,
        "candidate_id": selection.candidate_id,
        "provider": mapping.provider,
        "model_id": selection.model_id,
        "api_family": mapping.api_family,
        "adapter_id": mapping.adapter_id,
        "adapter_version": mapping.adapter_version,
        "workload_stage": binding.workload_stage,
        "topology_id": binding.topology_id,
        "authority_contract_ref": binding.authority_contract_ref,
        "ordered_native_segments": [
            {
                "ordinal": segment.ordinal,
                "source": segment.source,
                "authority_class": segment.authority_class,
                "native_surface": segment.native_surface,
            }
            for segment in binding.segments
        ],
        "schema_placement": binding.schema_placement,
        "visual_media_placement": binding.visual_media_placement,
        "search_tool_placement": binding.search_tool_placement,
    }


def validate_provider_request_plan(
    selection: ProviderRoleMappingSelection,
    observed_plan: Mapping[str, Any],
) -> ProviderRequestPlanAssessment:
    """Require exact preselected placement; no response-dependent repair."""
    expected = expected_provider_request_plan(selection)
    if not isinstance(observed_plan, Mapping):
        raise ConcreteProviderRoleMappingError("request_plan")
    try:
        matches = _canonical_bytes(observed_plan) == _canonical_bytes(expected)
    except ConcreteProviderRoleMappingError:
        raise
    if not matches:
        raise ConcreteProviderRoleMappingError("request_plan")
    binding = selection.workload_binding
    return ProviderRequestPlanAssessment(
        conformant=True,
        mapping_id=selection.mapping.mapping_id,
        mapping_version=selection.mapping.mapping_version,
        mapping_hash=selection.mapping.semantic_hash,
        workload_stage=binding.workload_stage,
        topology_id=binding.topology_id,
        segment_count=len(binding.segments),
    )
