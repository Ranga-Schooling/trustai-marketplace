"""Frozen provider-neutral selection of approved pilot request controls.

This module validates and selects immutable configuration metadata. It does not
construct transport requests, read credentials, or authorize provider calls.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from app.services.evaluation_provider_adapters import ProviderAdapterSet
from app.services.evaluation_provider_role_mappings import ProviderRoleMappingSet


_EXPECTED_ARTIFACT_HASH = (
    "1aaca1df3d67f51c3d9c1e5638d63b541bd947a1301aa509291cc7445e60b152"
)
_CONFIGURATION_ORDER = (
    "openai_sol_text_pilot_v1",
    "openai_sol_search_synthesis_pilot_v1",
    "openai_sol_visual_pilot_v1",
    "openai_terra_text_pilot_v1",
    "openai_terra_search_synthesis_pilot_v1",
    "openai_terra_visual_pilot_v1",
    "gemini_flash_text_pilot_v1",
    "gemini_flash_search_synthesis_pilot_v1",
    "gemini_flash_visual_pilot_v1",
    "groq_gpt_oss_text_pilot_v1",
    "groq_gpt_oss_search_synthesis_pilot_v1",
    "groq_qwen_visual_pilot_v1",
    "groq_baseline_text_pilot_v1",
)
_EXPECTED_SELECTIONS = {
    ("openai_unified_premium_v1", "text_analysis"): (
        "openai_sol_text_pilot_v1", 4096
    ),
    ("openai_unified_premium_v1", "search_synthesis"): (
        "openai_sol_search_synthesis_pilot_v1", 8192
    ),
    ("openai_unified_premium_v1", "visual_inspection"): (
        "openai_sol_visual_pilot_v1", 4096
    ),
    ("openai_unified_balanced_v1", "text_analysis"): (
        "openai_terra_text_pilot_v1", 4096
    ),
    ("openai_unified_balanced_v1", "search_synthesis"): (
        "openai_terra_search_synthesis_pilot_v1", 8192
    ),
    ("openai_unified_balanced_v1", "visual_inspection"): (
        "openai_terra_visual_pilot_v1", 4096
    ),
    ("gemini_unified_v1", "text_analysis"): (
        "gemini_flash_text_pilot_v1", 4096
    ),
    ("gemini_unified_v1", "search_synthesis"): (
        "gemini_flash_search_synthesis_pilot_v1", 8192
    ),
    ("gemini_unified_v1", "visual_inspection"): (
        "gemini_flash_visual_pilot_v1", 4096
    ),
    ("groq_split_v1", "text_analysis"): (
        "groq_gpt_oss_text_pilot_v1", 4096
    ),
    ("groq_split_v1", "search_synthesis"): (
        "groq_gpt_oss_search_synthesis_pilot_v1", 8192
    ),
    ("groq_split_v1", "visual_inspection"): (
        "groq_qwen_visual_pilot_v1", 4096
    ),
    ("baseline_current_text_v1", "text_analysis"): (
        "groq_baseline_text_pilot_v1", 4096
    ),
}
_SEARCH_RETRIEVAL_CANDIDATES = {
    "openai_unified_premium_v1",
    "openai_unified_balanced_v1",
    "gemini_unified_v1",
    "groq_split_v1",
}
_EXPECTED_PROFILE_HASHES = {
    "openai_responses_balanced_v1": "16bfa034229521474f40bfd3973ab208f6b934ae8632692d4ffc2241c2f6512b",
    "gemini_interactions_balanced_v1": "87feef957ecb197e814d1950b01ba8c9525ce5f4770550f6a82355e18e476712",
    "groq_gpt_oss_balanced_v1": "072d2e0ae03f3ad8e580923290a55c7fd331e1c690728ab2de96210e3ffaefa9",
    "groq_qwen_visual_balanced_v1": "f987de1d45e888267d8fe902f0229548302b8a78b3a592b854f0de6ea1a78ca0",
    "groq_current_text_baseline_v1": "190ed301b4bddac9e7cc24185ff9cbd157f8a1a0f4c354960fd04d6296e17afa",
}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TOP_KEYS = {
    "artifact_id", "artifact_version", "status", "purpose",
    "governance_decision", "source_contracts", "official_documentation_evidence",
    "native_profile_order", "native_profiles", "configuration_order",
    "configurations", "ineligible_search_retrieval", "execution_boundary",
    "specification_identity",
}
_CONTENT_KEYS = {
    "candidate_id", "provider", "model", "workload_stage", "topology_id",
    "profile_id", "role_mapping_id", "role_mapping_version",
    "role_mapping_hash", "adapter_id", "adapter_version", "adapter_hash",
    "output_schema_id", "output_schema_hash", "maximum_output_tokens",
    "search_and_tool_configuration",
}


class PilotRequestConfigurationError(ValueError):
    """A request configuration is stale, ambiguous, or ineligible."""

    category = "topology_preflight_failure"
    provider_attempt_created = False
    provider_call_incremented = False


@dataclass(frozen=True, slots=True)
class FrozenPilotRequestConfiguration:
    configuration_id: str
    configuration_version: str
    semantic_hash: str
    candidate_id: str
    provider: str
    model: str
    api_family: str
    endpoint_identity: str
    workload_stage: str
    topology_id: str
    role_mapping_id: str
    role_mapping_version: str
    role_mapping_hash: str
    adapter_id: str
    adapter_version: str
    adapter_hash: str
    output_schema_id: str
    output_schema_hash: str
    maximum_output_tokens: int
    reasoning: str | None
    reasoning_state: str
    temperature: float | None
    temperature_state: str
    top_p: str
    seed: str
    structured_output_mode: str
    harness_schema_validation_required: bool
    search_and_tool_configuration: str
    image_detail: str | None
    image_detail_state: str
    timeout_seconds: int
    maximum_physical_attempts: int
    streaming_enabled: bool
    storage_configuration: Mapping[str, Any]
    caching_configuration: Mapping[str, Any]

    def safe_record_projection(self) -> dict[str, Any]:
        return {
            "request_configuration_id": self.configuration_id,
            "request_configuration_version": self.configuration_version,
            "request_configuration_hash": self.semantic_hash,
            "role_mapping_id": self.role_mapping_id,
            "role_mapping_version": self.role_mapping_version,
            "role_mapping_hash": self.role_mapping_hash,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "adapter_hash": self.adapter_hash,
            "maximum_output_tokens": self.maximum_output_tokens,
            "reasoning_or_thinking_level": self.reasoning,
            "temperature_if_supported": self.temperature,
            "top_p_if_supported": self.top_p,
            "seed_if_supported": self.seed,
            "structured_output_mode": self.structured_output_mode,
            "search_and_tool_configuration": self.search_and_tool_configuration,
            "image_detail_or_resolution_configuration": self.image_detail,
            "timeout_seconds": self.timeout_seconds,
            "maximum_physical_attempts": self.maximum_physical_attempts,
            "streaming_enabled": self.streaming_enabled,
            "storage_configuration": dict(self.storage_configuration),
            "caching_configuration": dict(self.caching_configuration),
        }


@dataclass(frozen=True, slots=True)
class PilotRequestConfigurationSet:
    artifact_id: str
    artifact_version: str
    semantic_hash: str
    configurations: tuple[FrozenPilotRequestConfiguration, ...]
    ineligible_search_retrieval_candidates: tuple[str, ...]
    provider_calls_allowed: bool = False
    pilot_calls_allowed: bool = False
    scored_calls_allowed: bool = False
    provider_calls_completed: int = 0
    pilot_calls_completed: int = 0
    scored_calls_completed: int = 0
    winner_selected: bool = False
    independently_authorizes_execution: bool = False


@dataclass(frozen=True, slots=True)
class PilotRequestConfigurationSelection:
    configuration: FrozenPilotRequestConfiguration
    provider_attempt_created: bool = False
    provider_call_incremented: bool = False
    independently_authorizes_execution: bool = False


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise PilotRequestConfigurationError("semantic_hash") from exc


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _profile_hash(profile: Mapping[str, Any]) -> str:
    detached = json.loads(_canonical(profile))
    detached["semantic_hash"] = None
    return _hash(detached)


def _artifact_hash(raw: Mapping[str, Any]) -> str:
    detached = json.loads(_canonical(raw))
    detached["specification_identity"]["semantic_hash"] = None
    return _hash(detached)


def _control(profile: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = profile.get(name)
    if type(value) is not dict or set(value) != {"state", "value", "native_parameter"}:
        raise PilotRequestConfigurationError(f"profile_control:{name}")
    return value


def bind_pilot_request_configurations(
    raw: Mapping[str, Any],
    mappings: ProviderRoleMappingSet,
    adapters: ProviderAdapterSet,
) -> PilotRequestConfigurationSet:
    """Validate and bind the exact approved, non-executing pilot configuration set."""
    if type(raw) is not dict or set(raw) != _TOP_KEYS:
        raise PilotRequestConfigurationError("artifact_fields")
    if (
        raw["artifact_id"] != "pilot_request_configurations_v1"
        or raw["artifact_version"] != "v1"
        or raw["status"] != "frozen_pre_execution_contract"
    ):
        raise PilotRequestConfigurationError("artifact_header")
    identity = raw["specification_identity"]
    if (
        type(identity) is not dict
        or identity.get("semantic_hash") != _EXPECTED_ARTIFACT_HASH
        or identity.get("semantic_hash_excluded_json_pointers")
        != ["/specification_identity/semantic_hash"]
        or _artifact_hash(raw) != _EXPECTED_ARTIFACT_HASH
    ):
        raise PilotRequestConfigurationError("artifact_hash")
    decision = raw["governance_decision"]
    if (
        decision.get("text_maximum_output_tokens") != 4096
        or decision.get("search_synthesis_maximum_output_tokens") != 8192
        or decision.get("visual_maximum_output_tokens") != 4096
        or decision.get("streaming_enabled") is not False
        or decision.get("timeout_seconds_per_physical_attempt") != 120
        or decision.get("maximum_physical_attempts") != 2
        or decision.get("search_retrieval_security_contract_weakened") is not False
    ):
        raise PilotRequestConfigurationError("governance_decision")
    sources = raw["source_contracts"]
    if (
        sources.get("provider_role_mapping_artifact_hash") != mappings.semantic_hash
        or sources.get("provider_adapter_artifact_hash") != adapters.semantic_hash
        or sources.get("retry_policy_hash")
        != "a4e08ef3b92232cbbf1542aa37b30c87697da60c42bcf72d71876098d0251c4b"
        or sources.get("resource_policy_hash")
        != "9269950928ddf05e6b691623c57e6b60797c1131ee96f893e4977d5f223b2d16"
    ):
        raise PilotRequestConfigurationError("source_contract")

    profiles_raw = raw["native_profiles"]
    if type(profiles_raw) is not list or raw["native_profile_order"] != [
        item.get("profile_id") for item in profiles_raw
    ]:
        raise PilotRequestConfigurationError("profile_order")
    profiles: dict[str, Mapping[str, Any]] = {}
    for profile in profiles_raw:
        if type(profile) is not dict:
            raise PilotRequestConfigurationError("profile")
        profile_id = profile.get("profile_id")
        if profile_id in profiles or profile.get("profile_version") != "v1":
            raise PilotRequestConfigurationError("profile_identity")
        expected = _EXPECTED_PROFILE_HASHES.get(profile_id)
        if (
            expected is None
            or profile.get("semantic_hash") != expected
            or _profile_hash(profile) != expected
        ):
            raise PilotRequestConfigurationError("profile_hash")
        for name in (
            "reasoning", "temperature", "top_p", "seed", "image_detail",
            "streaming", "storage", "caching",
        ):
            _control(profile, name)
        if profile["streaming"]["value"] is not False:
            raise PilotRequestConfigurationError("streaming")
        profiles[profile_id] = profile

    mapping_index = {item.mapping_id: item for item in mappings.mappings}
    adapter_index = {item.adapter_id: item for item in adapters.adapters}
    configurations_raw = raw["configurations"]
    if (
        type(configurations_raw) is not list
        or raw["configuration_order"] != list(_CONFIGURATION_ORDER)
        or [item.get("configuration_id") for item in configurations_raw]
        != list(_CONFIGURATION_ORDER)
    ):
        raise PilotRequestConfigurationError("configuration_order")
    bound: list[FrozenPilotRequestConfiguration] = []
    seen: set[tuple[str, str]] = set()
    for entry in configurations_raw:
        if type(entry) is not dict or set(entry) != {
            "configuration_id", "configuration_version", "semantic_hash", "envelope"
        }:
            raise PilotRequestConfigurationError("configuration_fields")
        envelope = entry["envelope"]
        if (
            type(envelope) is not dict
            or set(envelope) != {
                "identity_domain", "request_configuration_id",
                "request_configuration_version", "content",
            }
            or envelope["identity_domain"]
            != "trustai.pilot_request_configuration.v1"
            or envelope["request_configuration_id"] != entry["configuration_id"]
            or envelope["request_configuration_version"] != "v1"
            or entry["configuration_version"] != "v1"
        ):
            raise PilotRequestConfigurationError("configuration_envelope")
        content = envelope["content"]
        if type(content) is not dict or set(content) != _CONTENT_KEYS:
            raise PilotRequestConfigurationError("configuration_content")
        profile = profiles.get(content["profile_id"])
        if profile is None:
            raise PilotRequestConfigurationError("profile_reference")
        computed = _hash({"envelope": envelope, "native_profile": profile})
        if (
            type(entry["semantic_hash"]) is not str
            or _SHA256.fullmatch(entry["semantic_hash"]) is None
            or entry["semantic_hash"] != computed
        ):
            raise PilotRequestConfigurationError("configuration_hash")
        key = (content["candidate_id"], content["workload_stage"])
        expected = _EXPECTED_SELECTIONS.get(key)
        if expected != (entry["configuration_id"], content["maximum_output_tokens"]):
            raise PilotRequestConfigurationError("configuration_selection")
        if key in seen:
            raise PilotRequestConfigurationError("configuration_duplicate")
        seen.add(key)
        mapping = mapping_index.get(content["role_mapping_id"])
        adapter = adapter_index.get(content["adapter_id"])
        if (
            mapping is None
            or mapping.mapping_version != content["role_mapping_version"]
            or mapping.semantic_hash != content["role_mapping_hash"]
            or content["candidate_id"] not in mapping.candidate_ids
            or content["model"] not in mapping.model_ids
            or content["workload_stage"]
            not in {item.workload_stage for item in mapping.workload_bindings}
        ):
            raise PilotRequestConfigurationError("role_mapping_binding")
        if (
            adapter is None
            or adapter.adapter_version != content["adapter_version"]
            or adapter.semantic_hash != content["adapter_hash"]
            or mapping.mapping_id not in adapter.role_mapping_ids
            or content["model"] not in adapter.model_ids
            or content["workload_stage"] not in adapter.eligible_workload_stages
        ):
            raise PilotRequestConfigurationError("adapter_binding")
        if (
            profile["provider"] != content["provider"]
            or profile["api_family"] != mapping.api_family
            or content["provider"] != mapping.provider
        ):
            raise PilotRequestConfigurationError("profile_applicability")
        reasoning = _control(profile, "reasoning")
        temperature = _control(profile, "temperature")
        image_detail = _control(profile, "image_detail")
        bound.append(FrozenPilotRequestConfiguration(
            configuration_id=entry["configuration_id"],
            configuration_version="v1",
            semantic_hash=entry["semantic_hash"],
            candidate_id=content["candidate_id"],
            provider=content["provider"],
            model=content["model"],
            api_family=profile["api_family"],
            endpoint_identity=profile["endpoint_identity"],
            workload_stage=content["workload_stage"],
            topology_id=content["topology_id"],
            role_mapping_id=mapping.mapping_id,
            role_mapping_version=mapping.mapping_version,
            role_mapping_hash=mapping.semantic_hash,
            adapter_id=adapter.adapter_id,
            adapter_version=adapter.adapter_version,
            adapter_hash=adapter.semantic_hash,
            output_schema_id=content["output_schema_id"],
            output_schema_hash=content["output_schema_hash"],
            maximum_output_tokens=content["maximum_output_tokens"],
            reasoning=reasoning["value"],
            reasoning_state=reasoning["state"],
            temperature=temperature["value"],
            temperature_state=temperature["state"],
            top_p=_control(profile, "top_p")["state"],
            seed=_control(profile, "seed")["state"],
            structured_output_mode=profile["structured_output_mode"],
            harness_schema_validation_required=profile[
                "harness_schema_validation_required"
            ],
            search_and_tool_configuration=content[
                "search_and_tool_configuration"
            ],
            image_detail=(
                image_detail["value"]
                if content["workload_stage"] == "visual_inspection"
                else None
            ),
            image_detail_state=(
                image_detail["state"]
                if content["workload_stage"] == "visual_inspection"
                else "not_applicable"
            ),
            timeout_seconds=decision["timeout_seconds_per_physical_attempt"],
            maximum_physical_attempts=decision["maximum_physical_attempts"],
            streaming_enabled=profile["streaming"]["value"],
            storage_configuration=profile["storage"],
            caching_configuration=profile["caching"],
        ))
    if seen != set(_EXPECTED_SELECTIONS):
        raise PilotRequestConfigurationError("configuration_coverage")

    ineligible = raw["ineligible_search_retrieval"]
    if (
        type(ineligible) is not list
        or {item.get("candidate_id") for item in ineligible}
        != _SEARCH_RETRIEVAL_CANDIDATES
        or any("redirect-chain" not in item.get("reason", "") for item in ineligible)
    ):
        raise PilotRequestConfigurationError("search_retrieval_ineligible_contract")
    boundary = raw["execution_boundary"]
    if (
        boundary != {
            "execution_state": "blocked_pre_execution",
            "provider_calls_allowed": False,
            "pilot_calls_allowed": False,
            "scored_calls_allowed": False,
            "provider_calls_completed": 0,
            "pilot_calls_completed": 0,
            "scored_calls_completed": 0,
            "winner_selected": False,
            "this_artifact_independently_authorizes_execution": False,
            "credentials_present": False,
        }
    ):
        raise PilotRequestConfigurationError("execution_boundary")
    return PilotRequestConfigurationSet(
        artifact_id=raw["artifact_id"],
        artifact_version=raw["artifact_version"],
        semantic_hash=identity["semantic_hash"],
        configurations=tuple(bound),
        ineligible_search_retrieval_candidates=tuple(
            item["candidate_id"] for item in ineligible
        ),
    )


def select_pilot_request_configuration(
    configurations: PilotRequestConfigurationSet,
    *,
    candidate_id: str,
    workload_stage: str,
) -> PilotRequestConfigurationSelection:
    if (
        workload_stage == "search_retrieval"
        and candidate_id in configurations.ineligible_search_retrieval_candidates
    ):
        raise PilotRequestConfigurationError("search_retrieval_ineligible")
    matches = tuple(
        item for item in configurations.configurations
        if item.candidate_id == candidate_id and item.workload_stage == workload_stage
    )
    if len(matches) != 1:
        raise PilotRequestConfigurationError("configuration_selection_missing")
    return PilotRequestConfigurationSelection(configuration=matches[0])


def validate_request_configuration_record(
    selection: PilotRequestConfigurationSelection,
    record: Mapping[str, Any],
) -> dict[str, Any]:
    expected = selection.configuration.safe_record_projection()
    if type(record) is not dict or record != expected:
        raise PilotRequestConfigurationError("record_mismatch")
    return json.loads(_canonical(record))
