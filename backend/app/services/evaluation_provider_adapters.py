"""Frozen provider response adapters for provider-free pilot preflight.

The adapters consume bounded, content-decoded HTTP response bytes.  They do
not own HTTP transport, credentials, request construction, retries, execution
authority, canonical schema validation, or retrieval provenance repair.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
import json
import re
from typing import Any

from app.services.evaluation_provider_role_mappings import (
    ProviderRoleMappingSelection,
    ProviderRoleMappingSet,
)
from app.services.evaluation_transport_capture import (
    ExtractedSemanticAccumulator,
    RawResponseCapture,
)
from app.services.normalization_parser import (
    DuplicateJsonKeyError,
    ExactJsonNumber,
    StrictJsonPayloadError,
    parse_strict_json_payload,
)


_ADAPTER_ORDER = (
    "openai_responses_adapter_v1",
    "gemini_interactions_adapter_v1",
    "groq_chat_completions_adapter_v1",
    "groq_compound_chat_completions_adapter_v1",
    "groq_vision_chat_completions_adapter_v1",
)
_EXPECTED_ARTIFACT_HASH = (
    "d5c98a4645c15beed550679c7c1dc1e63342dbb4142ccfe5bc905759514dc61f"
)
_EXPECTED_ADAPTER_HASHES = {
    "openai_responses_adapter_v1": (
        "78cb5800877d25970d4ed7e9a34ad63a25a591b8ba3b890da098a88a5052063d"
    ),
    "gemini_interactions_adapter_v1": (
        "9b74156f6ea19b2f2b4f9107a9c7325b580e091fff4651cff4996b6641e89fa5"
    ),
    "groq_chat_completions_adapter_v1": (
        "9af01c2b0c7267a42962e2136d650eacdd883ef6bacd76a842afcc7b95391f0a"
    ),
    "groq_compound_chat_completions_adapter_v1": (
        "3ff807e50f87f60a7d031dadb2bcf96dcedfa3942dad3b9b634dd64d5f8b530a"
    ),
    "groq_vision_chat_completions_adapter_v1": (
        "835ffdf536f84b4f23c9da3f812c3833778abe55352a708b56a33a40372c33db"
    ),
}
_EXPECTED_MAPPING_ADAPTERS = {
    "openai_responses_sol_v1": "openai_responses_adapter_v1",
    "openai_responses_terra_v1": "openai_responses_adapter_v1",
    "gemini_interactions_flash_v1": "gemini_interactions_adapter_v1",
    "groq_gpt_oss_chat_v1": "groq_chat_completions_adapter_v1",
    "groq_baseline_chat_v1": "groq_chat_completions_adapter_v1",
    "groq_compound_chat_v1": "groq_compound_chat_completions_adapter_v1",
    "groq_qwen_vision_chat_v1": "groq_vision_chat_completions_adapter_v1",
}
_EXPECTED_TOPOLOGIES = {
    ("openai_unified_premium_v1", "text_analysis"): (
        "openai_responses_adapter_v1",
        True,
    ),
    ("openai_unified_premium_v1", "search_retrieval"): (
        "openai_responses_adapter_v1",
        False,
    ),
    ("openai_unified_premium_v1", "search_synthesis"): (
        "openai_responses_adapter_v1",
        True,
    ),
    ("openai_unified_premium_v1", "visual_inspection"): (
        "openai_responses_adapter_v1",
        True,
    ),
    ("openai_unified_balanced_v1", "text_analysis"): (
        "openai_responses_adapter_v1",
        True,
    ),
    ("openai_unified_balanced_v1", "search_retrieval"): (
        "openai_responses_adapter_v1",
        False,
    ),
    ("openai_unified_balanced_v1", "search_synthesis"): (
        "openai_responses_adapter_v1",
        True,
    ),
    ("openai_unified_balanced_v1", "visual_inspection"): (
        "openai_responses_adapter_v1",
        True,
    ),
    ("gemini_unified_v1", "text_analysis"): (
        "gemini_interactions_adapter_v1",
        True,
    ),
    ("gemini_unified_v1", "search_retrieval"): (
        "gemini_interactions_adapter_v1",
        False,
    ),
    ("gemini_unified_v1", "search_synthesis"): (
        "gemini_interactions_adapter_v1",
        True,
    ),
    ("gemini_unified_v1", "visual_inspection"): (
        "gemini_interactions_adapter_v1",
        True,
    ),
    ("groq_split_v1", "text_analysis"): (
        "groq_chat_completions_adapter_v1",
        True,
    ),
    ("groq_split_v1", "search_retrieval"): (
        "groq_compound_chat_completions_adapter_v1",
        False,
    ),
    ("groq_split_v1", "search_synthesis"): (
        "groq_chat_completions_adapter_v1",
        True,
    ),
    ("groq_split_v1", "visual_inspection"): (
        "groq_vision_chat_completions_adapter_v1",
        True,
    ),
    ("baseline_current_text_v1", "text_analysis"): (
        "groq_chat_completions_adapter_v1",
        True,
    ),
}
_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_SAFE_INTEGER = 9_007_199_254_740_991


class ProviderAdapterContractError(ValueError):
    """A frozen adapter or topology is stale, ambiguous, or ineligible."""

    category = "topology_preflight_failure"
    provider_attempt_created = False
    provider_call_incremented = False


class ProviderAdapterResponseError(ValueError):
    """A started attempt's provider response cannot be extracted safely."""

    category = "failed_transport_extraction"
    provider_attempt_created = True
    provider_call_incremented = True


@dataclass(frozen=True, slots=True)
class UsageMetadata:
    input_token_usage: int
    output_token_usage: int
    reasoning_usage_if_exposed: int | None
    image_usage_if_exposed: int | None


@dataclass(frozen=True, slots=True)
class FrozenProviderAdapter:
    adapter_id: str
    adapter_version: str
    semantic_hash: str
    provider: str
    api_family: str
    role_mapping_ids: tuple[str, ...]
    model_ids: tuple[str, ...]
    eligible_workload_stages: tuple[str, ...]
    ineligible_workload_stages: tuple[tuple[str, tuple[str, ...]], ...]
    official_evidence_refs: tuple[str, ...]
    response_transport_mode: str = "non_streaming_http"
    provider_request_id_ordinary_projection: None = None
    independently_authorizes_execution: bool = False


@dataclass(frozen=True, slots=True)
class ProviderAdapterSet:
    artifact_id: str
    artifact_version: str
    semantic_hash: str
    adapters: tuple[FrozenProviderAdapter, ...]
    provider_calls_allowed: bool = False
    provider_calls_completed: int = 0
    independently_authorizes_execution: bool = False


@dataclass(frozen=True, slots=True)
class AdapterTopologyAssessment:
    adapter_id: str
    adapter_version: str
    adapter_hash: str
    candidate_id: str
    workload_stage: str
    eligible: bool
    blockers: tuple[str, ...]
    provider_attempt_created: bool = False
    provider_call_incremented: bool = False
    independently_authorizes_execution: bool = False


@dataclass(frozen=True, slots=True)
class AdaptedProviderResponse:
    adapter_id: str
    adapter_version: str
    adapter_hash: str
    response_transport_mode: str
    raw_provider_response_hash: str
    canonical_raw_byte_availability: bool
    content_decoded_response_bytes: bytes = field(repr=False)
    content_decoding_responsibility: str
    provider_trace_hash: str
    provider_trace_item_count: int
    semantic_content_tag: str
    semantic_location: str
    semantic_content_bytes: bytes = field(repr=False)
    semantic_content_hash: str
    provider: str
    model: str
    http_status: int
    documented_finish_state: str
    usage: UsageMetadata
    provider_request_id: None = None
    retrieval_trace: None = None
    provider_attempt_created: bool = True
    provider_call_incremented: bool = True
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
        raise ProviderAdapterContractError("semantic_hash") from exc


def _artifact_hash(artifact: Mapping[str, Any]) -> str:
    try:
        identity = artifact["specification_identity"]
        stored = identity["semantic_hash"]
    except (KeyError, TypeError) as exc:
        raise ProviderAdapterContractError("semantic_hash") from exc
    if (
        type(stored) is not str
        or _LOWER_SHA256.fullmatch(stored) is None
        or identity.get("semantic_hash_excluded_json_pointers")
        != ["/specification_identity/semantic_hash"]
    ):
        raise ProviderAdapterContractError("semantic_hash")
    detached = json.loads(_canonical_bytes(artifact))
    detached["specification_identity"]["semantic_hash"] = None
    computed = hashlib.sha256(_canonical_bytes(detached)).hexdigest()
    if computed != stored or computed != _EXPECTED_ARTIFACT_HASH:
        raise ProviderAdapterContractError("semantic_hash")
    return computed


def _adapter_hash(raw: Mapping[str, Any]) -> str:
    detached = {key: value for key, value in raw.items() if key != "semantic_hash"}
    return hashlib.sha256(_canonical_bytes(detached)).hexdigest()


def _execution_boundary(artifact: Mapping[str, Any]) -> None:
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
    boundary = artifact.get("execution_boundary")
    if not isinstance(boundary, Mapping) or any(
        boundary.get(key) != value for key, value in expected.items()
    ):
        raise ProviderAdapterContractError("execution_boundary")


def _bind_adapter(
    raw: Mapping[str, Any],
    *,
    evidence_ids: set[str],
) -> FrozenProviderAdapter:
    try:
        adapter_id = raw["adapter_id"]
        adapter_version = raw["adapter_version"]
        stored_hash = raw["semantic_hash"]
        evidence_refs = raw["official_evidence_refs"]
        content = raw["content"]
        ineligible = content["ineligible_workload_stages"]
    except (KeyError, TypeError) as exc:
        raise ProviderAdapterContractError("adapter_shape") from exc
    if (
        adapter_version != "v1"
        or stored_hash != _EXPECTED_ADAPTER_HASHES.get(adapter_id)
        or _adapter_hash(raw) != stored_hash
        or type(evidence_refs) is not list
        or not evidence_refs
        or any(ref not in evidence_ids for ref in evidence_refs)
        or type(content.get("role_mapping_ids")) is not list
        or not content["role_mapping_ids"]
        or type(content.get("model_ids")) is not list
        or not content["model_ids"]
        or type(content.get("eligible_workload_stages")) is not list
        or not isinstance(ineligible, Mapping)
        or set(content["eligible_workload_stages"]) & set(ineligible)
    ):
        raise ProviderAdapterContractError("adapter_shape")
    blockers: list[tuple[str, tuple[str, ...]]] = []
    for stage, reasons in ineligible.items():
        if type(stage) is not str or type(reasons) is not list or not reasons:
            raise ProviderAdapterContractError("adapter_ineligibility")
        if any(type(reason) is not str or not reason for reason in reasons):
            raise ProviderAdapterContractError("adapter_ineligibility")
        blockers.append((stage, tuple(reasons)))
    return FrozenProviderAdapter(
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        semantic_hash=stored_hash,
        provider=content["provider"],
        api_family=content["api_family"],
        role_mapping_ids=tuple(content["role_mapping_ids"]),
        model_ids=tuple(content["model_ids"]),
        eligible_workload_stages=tuple(content["eligible_workload_stages"]),
        ineligible_workload_stages=tuple(blockers),
        official_evidence_refs=tuple(evidence_refs),
    )


def bind_provider_adapters(
    artifact: dict[str, Any],
    role_mappings: ProviderRoleMappingSet,
) -> ProviderAdapterSet:
    """Verify exact adapter identity, role mappings, and topology outcomes."""
    if (
        not isinstance(artifact, Mapping)
        or type(role_mappings) is not ProviderRoleMappingSet
    ):
        raise ProviderAdapterContractError("artifact")
    semantic_hash = _artifact_hash(artifact)
    if (
        artifact.get("artifact_id") != "provider_adapters_v1"
        or artifact.get("artifact_version") != "v1"
        or artifact.get("status") != "frozen_pre_execution_contract"
        or tuple(artifact.get("adapter_order", ())) != _ADAPTER_ORDER
        or artifact.get("provider_neutral_contract")
        != "normalization-parser.v1.json#/provider_adapter_interface"
        or artifact.get("role_mapping_contract")
        != "provider-role-mappings.v1.json@v1"
    ):
        raise ProviderAdapterContractError("artifact")
    _execution_boundary(artifact)
    common = artifact.get("common_transport_policy")
    if (
        not isinstance(common, Mapping)
        or common.get("response_transport_mode") != "non_streaming_http"
        or common.get("streaming_enabled") is not False
        or common.get("sdk_native_structured_mode_allowed") is not False
        or common.get("canonical_raw_surface")
        != "content_decoded_response_bytes"
        or common.get("successful_http_status") != 200
        or common.get("provider_request_id_ordinary_projection") is not None
    ):
        raise ProviderAdapterContractError("transport_policy")
    preflight = artifact.get("search_topology_preflight")
    if (
        not isinstance(preflight, Mapping)
        or preflight.get("affected_workload_stage") != "search_retrieval"
        or preflight.get("all_current_built_in_search_topologies_eligible")
        is not False
        or preflight.get("failure_result") != "topology_preflight_failure"
        or preflight.get("attempt_created_on_failure") is not False
        or preflight.get("provider_call_incremented_on_failure") is not False
    ):
        raise ProviderAdapterContractError("search_topology_preflight")
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
        raise ProviderAdapterContractError("official_evidence")
    evidence_ids = {item["evidence_id"] for item in evidence}
    raw_adapters = artifact.get("adapters")
    if (
        type(raw_adapters) is not list
        or tuple(item.get("adapter_id") for item in raw_adapters)
        != _ADAPTER_ORDER
    ):
        raise ProviderAdapterContractError("adapter_inventory")
    adapters = tuple(
        _bind_adapter(item, evidence_ids=evidence_ids) for item in raw_adapters
    )
    by_id = {adapter.adapter_id: adapter for adapter in adapters}
    if len(by_id) != len(adapters):
        raise ProviderAdapterContractError("adapter_inventory")
    for mapping in role_mappings.mappings:
        expected_adapter = _EXPECTED_MAPPING_ADAPTERS.get(mapping.mapping_id)
        if (
            expected_adapter is None
            or mapping.adapter_id != expected_adapter
            or mapping.adapter_version != "v1"
            or mapping.mapping_id not in by_id[expected_adapter].role_mapping_ids
            or mapping.provider != by_id[expected_adapter].provider
            or mapping.api_family != by_id[expected_adapter].api_family
            or any(
                model not in by_id[expected_adapter].model_ids
                for model in mapping.model_ids
            )
        ):
            raise ProviderAdapterContractError("role_mapping_binding")
    matrix = artifact.get("topology_matrix")
    if type(matrix) is not list:
        raise ProviderAdapterContractError("topology_matrix")
    observed: dict[tuple[str, str], tuple[str, bool]] = {}
    for row in matrix:
        if not isinstance(row, Mapping):
            raise ProviderAdapterContractError("topology_matrix")
        key = (row.get("candidate_id"), row.get("workload_stage"))
        value = (row.get("adapter_id"), row.get("eligible"))
        if key in observed:
            raise ProviderAdapterContractError("topology_matrix")
        observed[key] = value
    if observed != _EXPECTED_TOPOLOGIES:
        raise ProviderAdapterContractError("topology_matrix")
    for (candidate_id, stage), (adapter_id, eligible) in observed.items():
        adapter = by_id[adapter_id]
        ineligible = dict(adapter.ineligible_workload_stages)
        if eligible != (stage in adapter.eligible_workload_stages):
            raise ProviderAdapterContractError("topology_matrix")
        if not eligible and stage not in ineligible:
            raise ProviderAdapterContractError("topology_matrix")
        if not any(
            candidate_id in mapping.candidate_ids
            for mapping in role_mappings.mappings
        ):
            raise ProviderAdapterContractError("topology_matrix")
    return ProviderAdapterSet(
        artifact_id="provider_adapters_v1",
        artifact_version="v1",
        semantic_hash=semantic_hash,
        adapters=adapters,
    )


def _adapter_for_selection(
    adapter_set: ProviderAdapterSet,
    selection: ProviderRoleMappingSelection,
) -> FrozenProviderAdapter:
    if (
        type(adapter_set) is not ProviderAdapterSet
        or type(selection) is not ProviderRoleMappingSelection
    ):
        raise ProviderAdapterContractError("selection")
    matches = tuple(
        adapter
        for adapter in adapter_set.adapters
        if adapter.adapter_id == selection.mapping.adapter_id
        and adapter.adapter_version == selection.mapping.adapter_version
        and selection.mapping.mapping_id in adapter.role_mapping_ids
        and selection.mapping.provider == adapter.provider
        and selection.mapping.api_family == adapter.api_family
        and selection.model_id in adapter.model_ids
    )
    if len(matches) != 1:
        raise ProviderAdapterContractError("selection")
    return matches[0]


def assess_adapter_topology(
    adapter_set: ProviderAdapterSet,
    selection: ProviderRoleMappingSelection,
) -> AdapterTopologyAssessment:
    """Return the frozen provider-free topology outcome before any attempt."""
    adapter = _adapter_for_selection(adapter_set, selection)
    stage = selection.workload_binding.workload_stage
    ineligible = dict(adapter.ineligible_workload_stages)
    eligible = stage in adapter.eligible_workload_stages
    blockers = () if eligible else ineligible.get(stage, ())
    if not eligible and not blockers:
        raise ProviderAdapterContractError("unclassified_topology")
    expected = _EXPECTED_TOPOLOGIES.get((selection.candidate_id, stage))
    if expected != (adapter.adapter_id, eligible):
        raise ProviderAdapterContractError("topology_selection")
    return AdapterTopologyAssessment(
        adapter_id=adapter.adapter_id,
        adapter_version=adapter.adapter_version,
        adapter_hash=adapter.semantic_hash,
        candidate_id=selection.candidate_id,
        workload_stage=stage,
        eligible=eligible,
        blockers=blockers,
    )


def require_eligible_adapter_topology(
    adapter_set: ProviderAdapterSet,
    selection: ProviderRoleMappingSelection,
) -> AdapterTopologyAssessment:
    """Fail closed before attempt creation for an ineligible topology."""
    assessment = assess_adapter_topology(adapter_set, selection)
    if not assessment.eligible:
        raise ProviderAdapterContractError("search_retrieval_topology_ineligible")
    return assessment


def _required_object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ProviderAdapterResponseError(label)
    return value


def _required_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise ProviderAdapterResponseError(label)
    return value


def _nonnegative_integer(value: Any, label: str) -> int:
    if type(value) is not ExactJsonNumber:
        raise ProviderAdapterResponseError(label)
    exact: Decimal = value.exact_decimal
    if (
        exact != exact.to_integral_value()
        or exact < 0
        or exact > _MAX_SAFE_INTEGER
    ):
        raise ProviderAdapterResponseError(label)
    return int(exact)


def _optional_nonnegative_integer(value: Any, label: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_integer(value, label)


def _extract_semantic_bytes(text: Any) -> tuple[bytes, str]:
    if type(text) is not str:
        raise ProviderAdapterResponseError("semantic_content")
    try:
        fragment = text.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ProviderAdapterResponseError("semantic_content") from exc
    accumulator = ExtractedSemanticAccumulator()
    accumulator.append(fragment)
    content = accumulator.finish()
    return content, hashlib.sha256(content).hexdigest()


def _extract_openai(
    root: dict[str, Any],
    expected_model: str,
) -> tuple[str, str, UsageMetadata, str, int]:
    if root.get("model") != expected_model:
        raise ProviderAdapterResponseError("model_identity")
    if root.get("status") != "completed":
        raise ProviderAdapterResponseError("provider_terminal_state")
    if (
        "error" not in root
        or "incomplete_details" not in root
        or root["error"] is not None
        or root["incomplete_details"] is not None
    ):
        raise ProviderAdapterResponseError("provider_terminal_state")
    messages = []
    for item in _required_list(root.get("output"), "output"):
        item = _required_object(item, "output_item")
        if item.get("type") == "message":
            messages.append(item)
    if len(messages) != 1:
        raise ProviderAdapterResponseError("semantic_candidate_count")
    message = messages[0]
    if message.get("role") != "assistant" or message.get("status") != "completed":
        raise ProviderAdapterResponseError("semantic_message")
    content = _required_list(message.get("content"), "message_content")
    if len(content) != 1:
        raise ProviderAdapterResponseError("semantic_candidate_count")
    part = _required_object(content[0], "message_content")
    if part.get("type") != "output_text":
        raise ProviderAdapterResponseError("semantic_content_type")
    usage = _required_object(root.get("usage"), "usage")
    details = usage.get("output_tokens_details")
    reasoning = None
    if details is not None:
        details = _required_object(details, "output_tokens_details")
        reasoning = _optional_nonnegative_integer(
            details.get("reasoning_tokens"),
            "reasoning_tokens",
        )
    return (
        part.get("text"),
        "output[documented_unique_message_index].content[0].text",
        UsageMetadata(
            input_token_usage=_nonnegative_integer(
                usage.get("input_tokens"), "input_tokens"
            ),
            output_token_usage=_nonnegative_integer(
                usage.get("output_tokens"), "output_tokens"
            ),
            reasoning_usage_if_exposed=reasoning,
            image_usage_if_exposed=None,
        ),
        "completed",
        len(_required_list(root.get("output"), "output")),
    )


def _extract_gemini(
    root: dict[str, Any],
    expected_model: str,
) -> tuple[str, str, UsageMetadata, str, int]:
    if root.get("model") != expected_model:
        raise ProviderAdapterResponseError("model_identity")
    if root.get("status") != "completed":
        raise ProviderAdapterResponseError("provider_terminal_state")
    if root.get("errors") not in (None, []):
        raise ProviderAdapterResponseError("provider_terminal_state")
    model_outputs = []
    for step in _required_list(root.get("steps"), "steps"):
        step = _required_object(step, "step")
        if step.get("type") == "model_output":
            model_outputs.append(step)
    if len(model_outputs) != 1:
        raise ProviderAdapterResponseError("semantic_candidate_count")
    content = _required_list(model_outputs[0].get("content"), "model_output_content")
    if len(content) != 1:
        raise ProviderAdapterResponseError("semantic_candidate_count")
    part = _required_object(content[0], "model_output_content")
    if part.get("type") != "text":
        raise ProviderAdapterResponseError("semantic_content_type")
    usage = _required_object(root.get("usage"), "usage")
    image_usage = None
    modalities = usage.get("input_tokens_by_modality")
    if modalities is not None:
        image_total = 0
        image_seen = False
        for item in _required_list(modalities, "input_tokens_by_modality"):
            item = _required_object(item, "modality_usage")
            if item.get("modality") == "image":
                image_seen = True
                image_total += _nonnegative_integer(item.get("tokens"), "image_tokens")
        if image_seen:
            image_usage = image_total
    return (
        part.get("text"),
        "steps[documented_unique_model_output_index].content[0].text",
        UsageMetadata(
            input_token_usage=_nonnegative_integer(
                usage.get("total_input_tokens"), "total_input_tokens"
            ),
            output_token_usage=_nonnegative_integer(
                usage.get("total_output_tokens"), "total_output_tokens"
            ),
            reasoning_usage_if_exposed=_optional_nonnegative_integer(
                usage.get("total_thought_tokens"), "total_thought_tokens"
            ),
            image_usage_if_exposed=image_usage,
        ),
        "completed",
        len(_required_list(root.get("steps"), "steps")),
    )


def _extract_groq(
    root: dict[str, Any],
    expected_model: str,
) -> tuple[str, str, UsageMetadata, str, int]:
    if root.get("model") != expected_model:
        raise ProviderAdapterResponseError("model_identity")
    choices = _required_list(root.get("choices"), "choices")
    if len(choices) != 1:
        raise ProviderAdapterResponseError("semantic_candidate_count")
    choice = _required_object(choices[0], "choice")
    if _nonnegative_integer(choice.get("index"), "choice_index") != 0:
        raise ProviderAdapterResponseError("choice_index")
    finish = choice.get("finish_reason")
    if finish != "stop":
        raise ProviderAdapterResponseError("provider_terminal_state")
    message = _required_object(choice.get("message"), "message")
    if message.get("role") != "assistant":
        raise ProviderAdapterResponseError("semantic_message")
    usage = _required_object(root.get("usage"), "usage")
    return (
        message.get("content"),
        "choices[0].message.content",
        UsageMetadata(
            input_token_usage=_nonnegative_integer(
                usage.get("prompt_tokens"), "prompt_tokens"
            ),
            output_token_usage=_nonnegative_integer(
                usage.get("completion_tokens"), "completion_tokens"
            ),
            reasoning_usage_if_exposed=None,
            image_usage_if_exposed=None,
        ),
        finish,
        1,
    )


def adapt_provider_response(
    adapter_set: ProviderAdapterSet,
    selection: ProviderRoleMappingSelection,
    capture: RawResponseCapture,
    *,
    http_status: int,
) -> AdaptedProviderResponse:
    """Extract one documented semantic string from bounded raw HTTP bytes."""
    assessment = require_eligible_adapter_topology(adapter_set, selection)
    adapter = _adapter_for_selection(adapter_set, selection)
    if (
        type(capture) is not RawResponseCapture
        or capture.response_transport_mode != "non_streaming_http"
        or capture.canonical_raw_byte_availability is not True
        or type(capture.raw_provider_response) is not bytes
        or type(capture.raw_provider_response_hash) is not str
    ):
        raise ProviderAdapterResponseError("raw_capture")
    if type(http_status) is not int or isinstance(http_status, bool):
        raise TypeError("http_status must be an integer")
    if http_status != 200:
        raise ProviderAdapterResponseError("http_provider_error")
    try:
        parsed = parse_strict_json_payload(capture.raw_provider_response)
    except (StrictJsonPayloadError, DuplicateJsonKeyError) as exc:
        raise ProviderAdapterResponseError("provider_envelope_json") from exc
    root = _required_object(parsed.value, "provider_envelope")
    if adapter.adapter_id == "openai_responses_adapter_v1":
        text, location, usage, finish, trace_count = _extract_openai(
            root, selection.model_id
        )
    elif adapter.adapter_id == "gemini_interactions_adapter_v1":
        text, location, usage, finish, trace_count = _extract_gemini(
            root, selection.model_id
        )
    elif adapter.adapter_id in {
        "groq_chat_completions_adapter_v1",
        "groq_vision_chat_completions_adapter_v1",
    }:
        text, location, usage, finish, trace_count = _extract_groq(
            root, selection.model_id
        )
    else:
        raise ProviderAdapterContractError("adapter_not_execution_eligible")
    semantic, semantic_hash = _extract_semantic_bytes(text)
    return AdaptedProviderResponse(
        adapter_id=assessment.adapter_id,
        adapter_version=assessment.adapter_version,
        adapter_hash=assessment.adapter_hash,
        response_transport_mode="non_streaming_http",
        raw_provider_response_hash=capture.raw_provider_response_hash,
        canonical_raw_byte_availability=True,
        content_decoded_response_bytes=capture.raw_provider_response,
        content_decoding_responsibility="HTTP transport before raw capture",
        provider_trace_hash=capture.raw_provider_response_hash,
        provider_trace_item_count=trace_count,
        semantic_content_tag="provider_authored_final_content",
        semantic_location=location,
        semantic_content_bytes=semantic,
        semantic_content_hash=semantic_hash,
        provider=adapter.provider,
        model=selection.model_id,
        http_status=http_status,
        documented_finish_state=finish,
        usage=usage,
    )
