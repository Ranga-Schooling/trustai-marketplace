"""Provider-free Search Authority V2 binding and projection.

V1 remains the immutable source of prompt components.  V2 changes only the
logical placement order: all evaluator instructions are projected into one
trusted segment before target data or retrieved evidence.  This module never
constructs a provider request, creates an attempt, or authorizes execution.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from app.services.evaluation_contract_identity import (
    ContractIdentityError,
    verify_normalization_parser_artifact,
    verify_prompt_template_artifact,
)


_EXPECTED_PROMPT_SET_HASH = (
    "9d6c5e43acb971b3ffb2a47b69f0def142d21c971717541e007f711404603df2"
)
_EXPECTED_NORMALIZATION_HASH = (
    "023ad80eeb6e08e9279c22b7955ebe5d04ec9ab3cd88626ceaccc4962c41b343"
)
_STAGE_ORDER = ("search_retrieval", "search_synthesis")
_AUTHORITY_ORDER = {
    "search_retrieval": (
        "authoritative_instruction",
        "untrusted_input",
    ),
    "search_synthesis": (
        "authoritative_instruction",
        "untrusted_input",
        "untrusted_retrieved_evidence",
    ),
}
_DESTINATIONS = {
    "authoritative_instruction": "strongest_documented_instruction_surface",
    "untrusted_input": "ordinary_untrusted_input_surface",
    "untrusted_retrieved_evidence": (
        "ordinary_untrusted_evidence_or_input_surface"
    ),
}
_EXPECTED_CANDIDATES = (
    "openai_unified_premium_v1",
    "openai_unified_balanced_v1",
    "gemini_unified_v1",
    "groq_split_v1",
)
_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class SearchAuthorityContractError(ValueError):
    """The V2 contract is malformed, stale, or authority-weakening."""

    provider_attempt_created = False
    provider_call_incremented = False


@dataclass(frozen=True)
class SearchAuthorityTrace:
    component_id: str
    stage_id: str
    v1_ordering_index: int
    v1_authority_class: str
    v2_logical_segment_id: str
    content_preserved_exactly: bool
    authority_preserved: bool
    relocated_before_untrusted_data: bool
    provider_specific_instruction_added: bool
    provider_information_changed: bool


@dataclass(frozen=True)
class SearchAuthoritySegmentBinding:
    segment_id: str
    segment_ordinal: int
    authority_class: str
    native_destination_semantics: str
    source_component_ids: tuple[str, ...]


@dataclass(frozen=True)
class SearchAuthorityStageBinding:
    stage_id: str
    source_template_id: str
    source_template_hash: str
    component_count: int
    segments: tuple[SearchAuthoritySegmentBinding, ...]


@dataclass(frozen=True)
class ProviderRepresentability:
    candidate_id: str
    provider: str
    api_family: str
    trusted_instruction_surface: str
    untrusted_input_surface: str
    retrieved_evidence_surface: str
    representable: bool
    later_trusted_instruction_injection_required: bool
    official_documentation_urls: tuple[str, ...]


@dataclass(frozen=True)
class AdversarialAuthorityVector:
    vector_id: str
    case: str
    content_surface: str
    content_authority: str
    trusted_contract_remains_authoritative: bool
    expected_conformance: str


@dataclass(frozen=True)
class SearchAuthorityBinding:
    contract_id: str
    contract_version: str
    semantic_hash: str
    source_prompt_set_hash: str
    source_normalization_hash: str
    v1_historical_status: str
    v2_execution_status: str
    stages: tuple[SearchAuthorityStageBinding, ...]
    traceability: tuple[SearchAuthorityTrace, ...]
    representability: tuple[ProviderRepresentability, ...]
    adversarial_vectors: tuple[AdversarialAuthorityVector, ...]
    component_count: int
    provider_calls_allowed: bool = False
    provider_calls_completed: int = 0
    independently_authorizes_execution: bool = False


@dataclass(frozen=True)
class ProjectedAuthoritySegment:
    segment_id: str
    segment_ordinal: int
    authority_class: str
    native_destination_semantics: str
    source_component_ids: tuple[str, ...]
    content_bytes: bytes
    provider_attempt_created: bool = False
    provider_call_incremented: bool = False
    independently_authorizes_execution: bool = False


@dataclass(frozen=True)
class SearchAuthorityProjection:
    stage_id: str
    segments: tuple[ProjectedAuthoritySegment, ...]
    source_component_count: int
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
        raise SearchAuthorityContractError("semantic_hash") from exc


def _verify_semantic_hash(artifact: Mapping[str, Any]) -> str:
    try:
        identity = artifact["specification_identity"]
        stored = identity["semantic_hash"]
        pointers = identity["semantic_hash_excluded_json_pointers"]
    except (KeyError, TypeError) as exc:
        raise SearchAuthorityContractError("semantic_hash") from exc
    if (
        type(stored) is not str
        or _LOWER_SHA256.fullmatch(stored) is None
        or pointers != ["/specification_identity/semantic_hash"]
    ):
        raise SearchAuthorityContractError("semantic_hash")
    semantic_copy = json.loads(_canonical_bytes(artifact))
    semantic_copy["specification_identity"]["semantic_hash"] = None
    computed = hashlib.sha256(_canonical_bytes(semantic_copy)).hexdigest()
    if computed != stored:
        raise SearchAuthorityContractError("semantic_hash")
    return computed


def _verify_source_identities(prompt_artifact: Any, normalization_spec: Any):
    try:
        prompt_identity = verify_prompt_template_artifact(prompt_artifact)
        parser_identity = verify_normalization_parser_artifact(normalization_spec)
    except (ContractIdentityError, KeyError, TypeError) as exc:
        raise SearchAuthorityContractError("frozen_source_identity") from exc
    if (
        prompt_identity.set_hash != _EXPECTED_PROMPT_SET_HASH
        or parser_identity.semantic_hash != _EXPECTED_NORMALIZATION_HASH
    ):
        raise SearchAuthorityContractError("frozen_source_identity")
    return prompt_identity, parser_identity


def _bind_stages(
    artifact: Mapping[str, Any],
    normalization_spec: Mapping[str, Any],
) -> tuple[tuple[SearchAuthorityStageBinding, ...], dict[str, tuple[str, int, str]]]:
    try:
        layouts = artifact["workload_layouts"]
        manifests = normalization_spec["provider_role_mapping_contract_v1"][
            "request_component_manifests"
        ]
    except (KeyError, TypeError) as exc:
        raise SearchAuthorityContractError("workload_layouts") from exc
    if not isinstance(layouts, Mapping) or tuple(layouts) != _STAGE_ORDER:
        raise SearchAuthorityContractError("workload_layouts")

    bound: list[SearchAuthorityStageBinding] = []
    source_inventory: dict[str, tuple[str, int, str]] = {}
    for stage_id in _STAGE_ORDER:
        layout = layouts[stage_id]
        source_manifest = manifests[stage_id]
        source_components = source_manifest["components"]
        if (
            not isinstance(layout, Mapping)
            or type(source_components) is not list
            or layout.get("component_count") != len(source_components)
            or layout.get("source_template_hash")
            != source_components[0].get("template_sha256")
            or layout.get("source_template_id")
            != source_components[0].get("template_id")
        ):
            raise SearchAuthorityContractError("workload_layouts")
        expected_source = {
            component["component_id"]: (
                stage_id,
                component["ordering_index"],
                component["authority_class"],
            )
            for component in source_components
        }
        source_inventory.update(expected_source)

        segments = layout.get("logical_segments")
        if type(segments) is not list or not segments:
            raise SearchAuthorityContractError("workload_layouts")
        if tuple(item.get("authority_class") for item in segments) != _AUTHORITY_ORDER[
            stage_id
        ]:
            raise SearchAuthorityContractError("trusted_before_untrusted")
        flattened: list[str] = []
        stage_bindings: list[SearchAuthoritySegmentBinding] = []
        for ordinal, segment in enumerate(segments):
            if not isinstance(segment, Mapping):
                raise SearchAuthorityContractError("workload_layouts")
            segment_id = segment.get("logical_segment_id")
            authority = segment.get("authority_class")
            destination = segment.get("native_destination_semantics")
            source_ids = segment.get("source_component_ids")
            if (
                type(segment_id) is not str
                or not segment_id
                or segment.get("logical_segment_ordinal") != ordinal
                or destination != _DESTINATIONS.get(authority)
                or type(source_ids) is not list
                or not source_ids
                or any(type(item) is not str for item in source_ids)
            ):
                raise SearchAuthorityContractError("workload_layouts")
            if any(
                item not in expected_source
                or expected_source[item][2] != authority
                for item in source_ids
            ):
                raise SearchAuthorityContractError("authority_assignment")
            source_order = [expected_source[item][1] for item in source_ids]
            if source_order != sorted(source_order):
                raise SearchAuthorityContractError("relative_order")
            flattened.extend(source_ids)
            stage_bindings.append(
                SearchAuthoritySegmentBinding(
                    segment_id=segment_id,
                    segment_ordinal=ordinal,
                    authority_class=authority,
                    native_destination_semantics=destination,
                    source_component_ids=tuple(source_ids),
                )
            )
        if len(flattened) != len(set(flattened)) or set(flattened) != set(
            expected_source
        ):
            raise SearchAuthorityContractError("component_coverage")
        bound.append(
            SearchAuthorityStageBinding(
                stage_id=stage_id,
                source_template_id=layout["source_template_id"],
                source_template_hash=layout["source_template_hash"],
                component_count=len(expected_source),
                segments=tuple(stage_bindings),
            )
        )
    return tuple(bound), source_inventory


def _bind_traceability(
    artifact: Mapping[str, Any],
    source_inventory: Mapping[str, tuple[str, int, str]],
    stages: tuple[SearchAuthorityStageBinding, ...],
) -> tuple[SearchAuthorityTrace, ...]:
    raw = artifact.get("v1_to_v2_traceability")
    if type(raw) is not list or len(raw) != len(source_inventory):
        raise SearchAuthorityContractError("traceability")
    segment_by_component = {
        component_id: segment.segment_id
        for stage in stages
        for segment in stage.segments
        for component_id in segment.source_component_ids
    }
    traces: list[SearchAuthorityTrace] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise SearchAuthorityContractError("traceability")
        component_id = item.get("component_id")
        source = source_inventory.get(component_id)
        required_true = (
            item.get("content_preserved_exactly") is True
            and item.get("authority_preserved") is True
        )
        required_false = (
            item.get("provider_specific_instruction_added") is False
            and item.get("provider_information_changed") is False
        )
        if (
            source is None
            or item.get("v1_ordering_index") != source[1]
            or item.get("v1_authority_class") != source[2]
            or item.get("v2_logical_segment_id")
            != segment_by_component.get(component_id)
            or type(item.get("relocated_before_untrusted_data")) is not bool
            or not required_true
            or not required_false
        ):
            raise SearchAuthorityContractError("traceability")
        traces.append(
            SearchAuthorityTrace(
                component_id=component_id,
                stage_id=source[0],
                v1_ordering_index=source[1],
                v1_authority_class=source[2],
                v2_logical_segment_id=item["v2_logical_segment_id"],
                content_preserved_exactly=True,
                authority_preserved=True,
                relocated_before_untrusted_data=item[
                    "relocated_before_untrusted_data"
                ],
                provider_specific_instruction_added=False,
                provider_information_changed=False,
            )
        )
    if len({item.component_id for item in traces}) != len(source_inventory):
        raise SearchAuthorityContractError("traceability")
    return tuple(traces)


def _bind_representability(
    artifact: Mapping[str, Any],
) -> tuple[ProviderRepresentability, ...]:
    raw = artifact.get("cross_provider_representability")
    if (
        type(raw) is not list
        or tuple(item.get("candidate_id") for item in raw) != _EXPECTED_CANDIDATES
    ):
        raise SearchAuthorityContractError("representability")
    result: list[ProviderRepresentability] = []
    for item in raw:
        urls = item.get("official_documentation_urls")
        required_strings = (
            "provider",
            "api_family",
            "trusted_instruction_surface",
            "untrusted_input_surface",
            "retrieved_evidence_surface",
        )
        if (
            any(type(item.get(field)) is not str or not item[field] for field in required_strings)
            or type(urls) is not list
            or not urls
            or any(type(url) is not str or not url.startswith("https://") for url in urls)
            or item.get("representable") is not True
            or item.get("later_trusted_instruction_injection_required") is not False
        ):
            raise SearchAuthorityContractError("representability")
        result.append(
            ProviderRepresentability(
                candidate_id=item["candidate_id"],
                provider=item["provider"],
                api_family=item["api_family"],
                trusted_instruction_surface=item["trusted_instruction_surface"],
                untrusted_input_surface=item["untrusted_input_surface"],
                retrieved_evidence_surface=item["retrieved_evidence_surface"],
                representable=True,
                later_trusted_instruction_injection_required=False,
                official_documentation_urls=tuple(urls),
            )
        )
    return tuple(result)


def _bind_adversarial_vectors(
    artifact: Mapping[str, Any],
) -> tuple[AdversarialAuthorityVector, ...]:
    raw = artifact.get("adversarial_conformance_vectors")
    if (
        type(raw) is not list
        or len(raw) != 11
        or tuple(item.get("vector_id") for item in raw)
        != tuple(f"A{index}" for index in range(1, 12))
    ):
        raise SearchAuthorityContractError("adversarial_vectors")
    result: list[AdversarialAuthorityVector] = []
    for item in raw:
        if (
            item.get("content_surface")
            not in {"untrusted_input", "untrusted_retrieved_evidence"}
            or item.get("content_authority") != "untrusted"
            or item.get("trusted_contract_remains_authoritative") is not True
            or item.get("expected_conformance") != "pass"
            or type(item.get("case")) is not str
        ):
            raise SearchAuthorityContractError("adversarial_vectors")
        result.append(
            AdversarialAuthorityVector(
                vector_id=item["vector_id"],
                case=item["case"],
                content_surface=item["content_surface"],
                content_authority="untrusted",
                trusted_contract_remains_authoritative=True,
                expected_conformance="pass",
            )
        )
    return tuple(result)


def _verify_execution_boundary(artifact: Mapping[str, Any]) -> None:
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
        raise SearchAuthorityContractError("execution_boundary")


def bind_search_authority_v2(
    artifact: dict[str, Any],
    prompt_artifact: dict[str, Any],
    normalization_spec: dict[str, Any],
) -> SearchAuthorityBinding:
    """Verify V2 identity, exact V1 traceability, and safe representability."""
    if not isinstance(artifact, Mapping):
        raise SearchAuthorityContractError("artifact")
    prompt_identity, parser_identity = _verify_source_identities(
        prompt_artifact,
        normalization_spec,
    )
    semantic_hash = _verify_semantic_hash(artifact)
    if (
        artifact.get("artifact_id") != "search_authority_contract_v2"
        or artifact.get("artifact_version") != "v2"
        or artifact.get("status") != "frozen_pre_execution_contract"
        or artifact.get("provider_neutral") is not True
        or artifact.get("historical_contract", {}).get("status")
        != "preserved_frozen_historical_contract"
        or artifact.get("v2_execution_contract", {}).get("status")
        != "frozen_pre_execution_contract"
        or artifact.get("frozen_sources", {}).get("prompt_template_set", {}).get(
            "semantic_hash"
        )
        != prompt_identity.set_hash
        or artifact.get("frozen_sources", {}).get("normalization_parser", {}).get(
            "semantic_hash"
        )
        != parser_identity.semantic_hash
    ):
        raise SearchAuthorityContractError("contract_identity")
    _verify_execution_boundary(artifact)
    stages, source_inventory = _bind_stages(artifact, normalization_spec)
    traceability = _bind_traceability(
        artifact,
        source_inventory,
        stages,
    )
    representability = _bind_representability(artifact)
    adversarial_vectors = _bind_adversarial_vectors(artifact)
    return SearchAuthorityBinding(
        contract_id="search_authority_contract_v2",
        contract_version="v2",
        semantic_hash=semantic_hash,
        source_prompt_set_hash=prompt_identity.set_hash,
        source_normalization_hash=parser_identity.semantic_hash,
        v1_historical_status="preserved_frozen_historical_contract",
        v2_execution_status="frozen_pre_execution_contract",
        stages=stages,
        traceability=traceability,
        representability=representability,
        adversarial_vectors=adversarial_vectors,
        component_count=len(source_inventory),
    )


def project_search_authority_v2(
    *,
    binding: SearchAuthorityBinding,
    stage_id: str,
    component_content_bytes: Mapping[str, bytes],
) -> SearchAuthorityProjection:
    """Project exact component bytes into V2 logical segments, locally only."""
    if type(binding) is not SearchAuthorityBinding:
        raise SearchAuthorityContractError("binding")
    stage = next((item for item in binding.stages if item.stage_id == stage_id), None)
    if stage is None:
        raise SearchAuthorityContractError("stage_id")
    expected_ids = tuple(
        component_id
        for segment in stage.segments
        for component_id in segment.source_component_ids
    )
    if (
        not isinstance(component_content_bytes, Mapping)
        or set(component_content_bytes) != set(expected_ids)
        or any(
            type(component_content_bytes[component_id]) is not bytes
            for component_id in expected_ids
        )
    ):
        raise SearchAuthorityContractError("component_bytes")
    segments = tuple(
        ProjectedAuthoritySegment(
            segment_id=segment.segment_id,
            segment_ordinal=segment.segment_ordinal,
            authority_class=segment.authority_class,
            native_destination_semantics=segment.native_destination_semantics,
            source_component_ids=segment.source_component_ids,
            content_bytes=b"\n".join(
                component_content_bytes[component_id]
                for component_id in segment.source_component_ids
            ),
        )
        for segment in stage.segments
    )
    return SearchAuthorityProjection(
        stage_id=stage_id,
        segments=segments,
        source_component_count=len(expected_ids),
    )
