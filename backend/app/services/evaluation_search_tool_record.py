"""Pilot-minimal safe search/tool observations with restricted raw inputs.

This module is provider-neutral and performs no persistence, credential access,
network operation, provider call, scoring, or execution authorization.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from app.services.evaluation_attempt_state import FAILURE_CODES
from app.services.evaluation_contract_identity import (
    ContractIdentityError,
    load_strict_contract_json,
)
from app.services.evaluation_data_handling import (
    RestrictedTraceReference,
    RestrictedUrlTrace,
)
from app.services.evaluation_resource_limits import (
    RESOURCE_LIMIT_VALUES,
    NativeResourceTopologyError,
    ResourceLimitExceededError,
    enforce_native_json_resource_limits,
)
from app.services.evaluation_retrieval_trace import (
    PublicSafeDeduplicationKey,
    RetrievalAllocationPlan,
    ValidatedTracePositionInventory,
    derive_public_safe_deduplication_key,
    render_evidence_id,
    render_source_id,
)


POLICY_ID = "safe_search_tool_record_v1"
POLICY_VERSION = "v1"
POLICY_HASH = "a1b6325f6619c7fb3067f7add52adb6f53a9806ff1b9e72432c7cf528e4f35cb"

_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CONTRACT = (
    _ROOT
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "safe-search-tool-record.v1.json"
)
_TOKEN = object()
_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_UTC_MILLISECOND = re.compile(
    r"(?:19|20)[0-9]{2}-(?:0[1-9]|1[0-2])-"
    r"(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\."
    r"[0-9]{3}Z\Z"
)
_OPERATION_TYPES = (
    "search",
    "query",
    "page_fetch",
    "page_visit",
    "grounded_retrieval",
)
_OPERATION_OUTCOMES = ("completed", "failed")
_ORDINARY_FIELDS = (
    "contract",
    "operations",
    "sources",
    "evidence",
    "claim_evidence_source_links",
)
_OPERATION_FIELDS = (
    "operation_id",
    "phase_id",
    "retrieval_attempt_ordinal",
    "tool_call_ordinal",
    "operation_type",
    "query_id",
    "outcome",
    "safe_failure_code",
    "result_count",
    "source_count",
    "evidence_count",
    "started_at",
    "completed_at",
    "latency_ms",
    "restricted_trace_reference",
    "url_security_results",
)
_SOURCE_FIELDS = (
    "source_id",
    "public_safe_canonical_url",
    "retrieved_at",
    "retrieval_observations",
    "restricted_trace_reference",
    "url_security_policy_id",
    "url_security_policy_version",
    "url_security_policy_hash",
)
_EVIDENCE_FIELDS = ("evidence_id", "source_id", "retrieval_observation")
_LINK_FIELDS = ("claim_id", "evidence_id", "source_id", "retrieval_observation")
_SOURCE_POSITION_FIELDS = (
    "retrieval_attempt_ordinal",
    "tool_call_ordinal",
    "result_ordinal",
)
_POSITION_FIELDS = (
    "retrieval_attempt_ordinal",
    "tool_call_ordinal",
    "result_ordinal",
    "evidence_observation_ordinal",
)
_RESTRICTED_FIELDS = ("contract", "operations")
_RESTRICTED_OPERATION_FIELDS = (
    "operation_id",
    "restricted_trace_reference",
    "raw_search_query",
    "raw_tool_arguments",
    "exact_url_traces",
)
_URL_RESULT_FIELDS = {
    "classification",
    "reason_codes",
    "url_role",
    "restricted_trace_reference",
    "policy_id",
    "policy_version",
    "policy_hash",
}
_CONTRACT_FIELDS = {
    "artifact_id",
    "artifact_version",
    "status",
    "purpose",
    "provider_neutral",
    "authority",
    "source_contracts",
    "ordinary_projection",
    "restricted_projection",
    "operation_contract",
    "query_identity",
    "tool_identity",
    "ordering",
    "provenance_linkage",
    "url_policy",
    "privacy",
    "retention_and_region",
    "validation",
    "result_record_compatibility",
    "execution_boundary",
    "specification_identity",
}
_FORBIDDEN_CREDENTIAL_FIELDS = {
    "authorization",
    "proxyauthorization",
    "cookie",
    "setcookie",
    "apikey",
    "accesstoken",
    "refreshtoken",
    "idtoken",
    "clientsecret",
    "password",
    "passwd",
    "secret",
    "sessionid",
    "sessiontoken",
    "privatekey",
}
_CREDENTIAL_STRING = re.compile(
    r"(?i)(?:"
    r"\bauthorization\s*[:=]\s*\S+|"
    r"\bbearer\s+\S+|"
    r"\b(?:api[_. -]*key|access[_. -]*token|refresh[_. -]*token|"
    r"id[_. -]*token|client[_. -]*secret|password|passwd|"
    r"session[_. -]*token|private[_. -]*key)\s*[:=]\s*\S+|"
    r"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY-----"
    r")"
)


class SearchToolRecordError(ValueError):
    """A search/tool observation violated the frozen safe record contract."""


def _fail(code: str) -> SearchToolRecordError:
    return SearchToolRecordError(code)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise _fail("restricted_json_shape") from exc


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(_canonical_bytes(value).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:  # pragma: no cover
        raise _fail("restricted_json_shape") from exc


def _semantic_hash(artifact: dict[str, Any]) -> str:
    detached = _json_copy(artifact)
    try:
        del detached["specification_identity"]["semantic_hash"]
    except (KeyError, TypeError) as exc:
        raise _fail("contract_identity") from exc
    return hashlib.sha256(_canonical_bytes(detached)).hexdigest()


@dataclass(frozen=True, slots=True)
class SafeSearchToolRecordContract:
    policy_id: str
    policy_version: str
    policy_hash: str


def verify_safe_search_tool_record_contract(
    path: str | Path = _DEFAULT_CONTRACT,
) -> SafeSearchToolRecordContract:
    """Verify the exact frozen contract and recompute its semantic identity."""
    try:
        artifact = load_strict_contract_json(path)
    except ContractIdentityError as exc:
        raise _fail("contract_identity") from exc
    if (
        set(artifact) != _CONTRACT_FIELDS
        or artifact.get("artifact_id") != POLICY_ID
        or artifact.get("artifact_version") != POLICY_VERSION
        or artifact.get("status") != "frozen"
        or artifact.get("provider_neutral") is not True
        or artifact.get("ordinary_projection", {}).get("exact_fields")
        != list(_ORDINARY_FIELDS)
        or artifact["ordinary_projection"].get("operation_exact_fields")
        != list(_OPERATION_FIELDS)
        or artifact["ordinary_projection"].get("source_exact_fields")
        != list(_SOURCE_FIELDS)
        or artifact["ordinary_projection"].get("evidence_exact_fields")
        != list(_EVIDENCE_FIELDS)
        or artifact["ordinary_projection"].get("source_observation_exact_fields")
        != list(_SOURCE_POSITION_FIELDS)
        or artifact["ordinary_projection"].get("claim_link_exact_fields")
        != list(_LINK_FIELDS)
        or artifact["ordinary_projection"].get(
            "retrieval_observation_exact_fields"
        )
        != list(_POSITION_FIELDS)
        or artifact.get("restricted_projection", {}).get("exact_fields")
        != list(_RESTRICTED_FIELDS)
        or artifact["restricted_projection"].get("operation_exact_fields")
        != list(_RESTRICTED_OPERATION_FIELDS)
        or artifact.get("operation_contract", {}).get("operation_types")
        != list(_OPERATION_TYPES)
        or artifact["operation_contract"].get("outcomes")
        != list(_OPERATION_OUTCOMES)
    ):
        raise _fail("contract_shape")
    privacy = artifact.get("privacy", {})
    credential = privacy.get("credential_detection", {})
    if (
        privacy.get("raw_search_query_in_ordinary_allowed") is not False
        or privacy.get("raw_tool_arguments_in_ordinary_allowed") is not False
        or privacy.get("credential_material_allowed_in_ordinary") is not False
        or privacy.get("credential_material_allowed_in_restricted") is not False
        or set(credential.get("forbidden_normalized_field_names", ()))
        != _FORBIDDEN_CREDENTIAL_FIELDS
        or artifact.get("execution_boundary")
        != {
            "authoritative_execution_gate": "experiment.v1.json execution_gate",
            "execution_state": "blocked_pre_execution",
            "provider_calls_allowed": False,
            "pilot_calls_allowed": False,
            "scored_calls_allowed": False,
            "provider_calls_completed": 0,
            "this_artifact_independently_authorizes_execution": False,
        }
    ):
        raise _fail("contract_privacy_or_execution")
    identity = artifact.get("specification_identity", {})
    stored_hash = identity.get("semantic_hash")
    if (
        identity.get("semantic_hash_excluded_json_pointers")
        != ["/specification_identity/semantic_hash"]
        or type(stored_hash) is not str
        or _LOWER_SHA256.fullmatch(stored_hash) is None
        or _semantic_hash(artifact) != stored_hash
        or stored_hash != POLICY_HASH
    ):
        raise _fail("contract_identity")
    return SafeSearchToolRecordContract(POLICY_ID, POLICY_VERSION, stored_hash)


@dataclass(frozen=True, slots=True, repr=False)
class RawSearchToolOperation:
    """Transient restricted input captured before privacy projection."""

    retrieval_attempt_ordinal: Any
    tool_call_ordinal: Any
    operation_type: Any
    raw_search_query: Any
    raw_tool_arguments: Any
    outcome: Any
    safe_failure_code: Any
    started_at: Any
    completed_at: Any
    latency_ms: Any
    restricted_trace_reference: Any
    restricted_url_traces: Any = ()

    def __repr__(self) -> str:
        return "RawSearchToolOperation(<restricted>)"


@dataclass(frozen=True, slots=True)
class OrdinarySearchToolProjection:
    _json: bytes = field(repr=False)
    _token: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _TOKEN:
            raise _fail("ordinary_projection_factory_required")

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._json.decode("utf-8"))


@dataclass(frozen=True, slots=True)
class RestrictedSearchToolProjection:
    _json: bytes = field(repr=False)
    _token: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _TOKEN:
            raise _fail("restricted_projection_factory_required")

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._json.decode("utf-8"))


@dataclass(frozen=True, slots=True)
class SearchToolProjections:
    ordinary: OrdinarySearchToolProjection
    restricted: RestrictedSearchToolProjection = field(repr=False)
    _token: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _TOKEN:
            raise _fail("projection_factory_required")


def _format_position(prefix: str, attempt: int, tool_call: int) -> str:
    return f"{prefix}-{attempt:04d}-{tool_call:04d}"


def _require_timestamp(value: Any) -> datetime:
    if type(value) is not str or _UTC_MILLISECOND.fullmatch(value) is None:
        raise _fail("operation_timing")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _fail("operation_timing") from exc
    if parsed.tzinfo != UTC:
        raise _fail("operation_timing")
    return parsed


def _normalized_credential_field(value: str) -> str:
    return "".join(
        character
        for character in value.lower()
        if character not in "-_. \t\r\n"
    )


def _contains_credential_marker(value: Any) -> bool:
    if type(value) is str:
        return _CREDENTIAL_STRING.search(value) is not None
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                return True
            if _normalized_credential_field(key) in _FORBIDDEN_CREDENTIAL_FIELDS:
                return True
            if _contains_credential_marker(child):
                return True
        return False
    if type(value) is list:
        return any(_contains_credential_marker(child) for child in value)
    return False


def _validate_allocation_plan(
    inventory: ValidatedTracePositionInventory,
    plan: RetrievalAllocationPlan,
) -> None:
    if not isinstance(inventory, ValidatedTracePositionInventory):
        raise _fail("trace_inventory")
    if not isinstance(plan, RetrievalAllocationPlan):
        raise _fail("allocation_plan")
    source_ids = tuple(source.source_id for source in plan.sources)
    if source_ids != tuple(render_source_id(index) for index in range(1, len(plan.sources) + 1)):
        raise _fail("allocation_plan")
    source_by_id = {source.source_id: source for source in plan.sources}
    seen_source_positions: set[tuple[int, int, int]] = set()
    for source in plan.sources:
        if (
            source.source_ordinal < 1
            or source.source_id != render_source_id(source.source_ordinal)
            or not source.observation_keys
            or tuple(sorted(source.observation_keys)) != source.observation_keys
            or min(source.observation_keys) != source.earliest_observation_key
            or any(key not in inventory.source_positions for key in source.observation_keys)
            or seen_source_positions.intersection(source.observation_keys)
        ):
            raise _fail("allocation_plan")
        seen_source_positions.update(source.observation_keys)
        _require_timestamp(source.retrieved_at)
    expected_evidence_ids: list[str] = []
    counts: dict[str, int] = {source_id: 0 for source_id in source_ids}
    for evidence in plan.evidence:
        source = source_by_id.get(evidence.source_id)
        if source is None or evidence.source_ordinal != source.source_ordinal:
            raise _fail("allocation_plan")
        counts[evidence.source_id] += 1
        expected = render_evidence_id(source.source_ordinal, counts[evidence.source_id])
        expected_evidence_ids.append(expected)
        if (
            evidence.evidence_id != expected
            or evidence.evidence_ordinal != counts[evidence.source_id]
            or evidence.observation_key not in inventory.evidence_positions
            or evidence.observation_key[:3] not in source.observation_keys
        ):
            raise _fail("allocation_plan")
    if tuple(item.evidence_id for item in plan.evidence) != tuple(expected_evidence_ids):
        raise _fail("allocation_plan")


def _position_dict(position: tuple[int, int, int, int]) -> dict[str, int]:
    return dict(zip(_POSITION_FIELDS, position, strict=True))


def build_search_tool_projections(
    *,
    operations: Sequence[RawSearchToolOperation],
    trace_inventory: ValidatedTracePositionInventory,
    allocation_plan: RetrievalAllocationPlan,
    claim_evidence_links: Sequence[Mapping[str, Any]],
    credential_material: Any = None,
    contract_path: str | Path = _DEFAULT_CONTRACT,
) -> SearchToolProjections:
    """Build disjoint immutable pilot projections without semantic repair."""
    contract = verify_safe_search_tool_record_contract(contract_path)
    if credential_material is not None:
        raise _fail("credential_material")
    if isinstance(operations, (str, bytes, bytearray)) or type(operations) not in {
        tuple,
        list,
    }:
        raise _fail("operation_inventory")
    operation_items = tuple(operations)
    if (
        not operation_items
        or len(operation_items) > RESOURCE_LIMIT_VALUES["maximum_array_elements"]
        or any(not isinstance(item, RawSearchToolOperation) for item in operation_items)
    ):
        raise _fail("operation_inventory")
    if isinstance(claim_evidence_links, (str, bytes, bytearray)) or type(
        claim_evidence_links
    ) not in {tuple, list}:
        raise _fail("claim_link_inventory")
    claim_inputs = tuple(claim_evidence_links)
    if len(claim_inputs) > RESOURCE_LIMIT_VALUES["maximum_array_elements"]:
        raise _fail("claim_link_inventory")
    _validate_allocation_plan(trace_inventory, allocation_plan)

    trace_operation_keys = tuple(sorted(trace_inventory.tool_positions))
    supplied_keys = tuple(
        (item.retrieval_attempt_ordinal, item.tool_call_ordinal)
        for item in operation_items
    )
    if supplied_keys != trace_operation_keys:
        raise _fail("operation_order")

    source_by_id = {source.source_id: source for source in allocation_plan.sources}
    evidence_by_id = {
        evidence.evidence_id: evidence for evidence in allocation_plan.evidence
    }
    source_positions_by_operation = {
        key: tuple(
            source
            for source in allocation_plan.sources
            if any(position[:2] == key for position in source.observation_keys)
        )
        for key in trace_operation_keys
    }
    evidence_by_operation = {
        key: tuple(
            evidence
            for evidence in allocation_plan.evidence
            if evidence.observation_key[:2] == key
        )
        for key in trace_operation_keys
    }

    ordinary_operations: list[dict[str, Any]] = []
    restricted_operations: list[dict[str, Any]] = []
    public_trace_inputs_by_reference: dict[str, dict[str, Any]] = {}
    total_url_traces = 0
    for item in operation_items:
        key = (item.retrieval_attempt_ordinal, item.tool_call_ordinal)
        if (
            any(type(value) is not int or value < 1 for value in key)
            or item.operation_type not in _OPERATION_TYPES
            or item.outcome not in _OPERATION_OUTCOMES
            or not isinstance(item.restricted_trace_reference, RestrictedTraceReference)
        ):
            raise _fail("operation_fields")
        if item.outcome == "completed":
            if item.safe_failure_code is not None:
                raise _fail("operation_failure")
        elif type(item.safe_failure_code) is not str or item.safe_failure_code not in FAILURE_CODES:
            raise _fail("operation_failure")
        started = _require_timestamp(item.started_at)
        completed = _require_timestamp(item.completed_at)
        if (
            completed < started
            or type(item.latency_ms) is not int
            or item.latency_ms < 0
            or int((completed - started).total_seconds() * 1000) != item.latency_ms
        ):
            raise _fail("operation_timing")
        if item.raw_search_query is not None and type(item.raw_search_query) is not str:
            raise _fail("raw_search_query_type")
        if item.raw_tool_arguments is not None and type(item.raw_tool_arguments) is not dict:
            raise _fail("raw_tool_arguments_type")
        try:
            enforce_native_json_resource_limits(
                {
                    "raw_search_query": item.raw_search_query,
                    "raw_tool_arguments": item.raw_tool_arguments,
                }
            )
        except (ResourceLimitExceededError, NativeResourceTopologyError) as exc:
            raise _fail("record_resource_limit") from exc
        raw_arguments = (
            None if item.raw_tool_arguments is None else _json_copy(item.raw_tool_arguments)
        )
        if _contains_credential_marker(item.raw_search_query) or _contains_credential_marker(raw_arguments):
            raise _fail("credential_material")
        if type(item.restricted_url_traces) not in {tuple, list}:
            raise _fail("url_trace_inventory")
        traces = tuple(item.restricted_url_traces)
        if any(not isinstance(trace, RestrictedUrlTrace) for trace in traces):
            raise _fail("url_trace_inventory")
        total_url_traces += len(traces)
        if len(traces) > RESOURCE_LIMIT_VALUES["maximum_array_elements"]:
            raise _fail("url_trace_inventory")
        safe_results: list[dict[str, Any]] = []
        restricted_trace_inputs: list[dict[str, Any]] = []
        has_non_public_trace = False
        for trace in traces:
            safe = trace.as_safe_result_dict()
            restricted_input = trace.as_restricted_dict()
            if set(safe) != _URL_RESULT_FIELDS:
                raise _fail("url_trace_result")
            if _contains_credential_marker(restricted_input):
                raise _fail("credential_material")
            safe_results.append(_json_copy(safe))
            restricted_trace_inputs.append(_json_copy(restricted_input))
            if safe["classification"] == "public_safe":
                reference = safe["restricted_trace_reference"]
                if reference in public_trace_inputs_by_reference:
                    raise _fail("url_trace_reference_duplicate")
                public_trace_inputs_by_reference[reference] = restricted_input
            else:
                has_non_public_trace = True
        if has_non_public_trace and (
            item.outcome == "completed" or source_positions_by_operation[key]
        ):
            raise _fail("url_security_trace_outcome")
        operation_id = _format_position("op", key[0], key[1])
        query_id = (
            _format_position("qry", key[0], key[1])
            if item.raw_search_query is not None
            else None
        )
        result_count = sum(
            1 for position in trace_inventory.source_positions if position[:2] == key
        )
        sources_for_operation = source_positions_by_operation[key]
        evidence_for_operation = evidence_by_operation[key]
        ordinary_operations.append(
            {
                "operation_id": operation_id,
                "phase_id": "search_retrieval",
                "retrieval_attempt_ordinal": key[0],
                "tool_call_ordinal": key[1],
                "operation_type": item.operation_type,
                "query_id": query_id,
                "outcome": item.outcome,
                "safe_failure_code": item.safe_failure_code,
                "result_count": result_count,
                "source_count": len(sources_for_operation),
                "evidence_count": len(evidence_for_operation),
                "started_at": item.started_at,
                "completed_at": item.completed_at,
                "latency_ms": item.latency_ms,
                "restricted_trace_reference": item.restricted_trace_reference.value,
                "url_security_results": safe_results,
            }
        )
        restricted_operations.append(
            {
                "operation_id": operation_id,
                "restricted_trace_reference": item.restricted_trace_reference.value,
                "raw_search_query": item.raw_search_query,
                "raw_tool_arguments": raw_arguments,
                "exact_url_traces": restricted_trace_inputs,
            }
        )

    ordinary_sources: list[dict[str, Any]] = []
    for source in allocation_plan.sources:
        restricted_input = public_trace_inputs_by_reference.get(
            source.url_trace_reference
        )
        if restricted_input is None:
            raise _fail("public_safe_source_trace")
        try:
            key = derive_public_safe_deduplication_key(**restricted_input)
        except (TypeError, ValueError) as exc:
            raise _fail("public_safe_source_trace") from exc
        if (
            not isinstance(key, PublicSafeDeduplicationKey)
            or key.safe_canonical_url != source.safe_canonical_url
            or key.value != source.deduplication_url_key
            or key.restricted_trace_reference != source.url_trace_reference
            or key.policy_identity != source.url_security_policy_identity
        ):
            raise _fail("public_safe_source_trace")
        ordinary_sources.append(
            {
                "source_id": source.source_id,
                "public_safe_canonical_url": source.safe_canonical_url,
                "retrieved_at": source.retrieved_at,
                "retrieval_observations": [
                    dict(zip(_SOURCE_POSITION_FIELDS, position, strict=True))
                    for position in source.observation_keys
                ],
                "restricted_trace_reference": source.url_trace_reference,
                "url_security_policy_id": source.url_security_policy_identity[0],
                "url_security_policy_version": source.url_security_policy_identity[1],
                "url_security_policy_hash": source.url_security_policy_identity[2],
            }
        )

    ordinary_evidence = [
        {
            "evidence_id": evidence.evidence_id,
            "source_id": evidence.source_id,
            "retrieval_observation": _position_dict(evidence.observation_key),
        }
        for evidence in allocation_plan.evidence
    ]
    ordinary_links: list[dict[str, Any]] = []
    seen_claim_evidence: set[tuple[str, str]] = set()
    for link in claim_inputs:
        if type(link) is not dict or set(link) != {"claim_id", "evidence_id"}:
            raise _fail("claim_link_fields")
        claim_id = link["claim_id"]
        evidence_id = link["evidence_id"]
        if (
            type(claim_id) is not str
            or _SAFE_IDENTIFIER.fullmatch(claim_id) is None
            or type(evidence_id) is not str
            or evidence_id not in evidence_by_id
            or (claim_id, evidence_id) in seen_claim_evidence
        ):
            raise _fail("claim_link_identity")
        seen_claim_evidence.add((claim_id, evidence_id))
        evidence = evidence_by_id[evidence_id]
        source = source_by_id[evidence.source_id]
        ordinary_links.append(
            {
                "claim_id": claim_id,
                "evidence_id": evidence.evidence_id,
                "source_id": source.source_id,
                "retrieval_observation": _position_dict(evidence.observation_key),
            }
        )

    combined_elements = (
        len(operation_items)
        + len(allocation_plan.sources)
        + len(allocation_plan.evidence)
        + len(claim_inputs)
        + total_url_traces
    )
    if combined_elements > RESOURCE_LIMIT_VALUES["maximum_total_array_elements"]:
        raise _fail("record_resource_limit")
    identity = {
        "policy_id": contract.policy_id,
        "policy_version": contract.policy_version,
        "policy_hash": contract.policy_hash,
    }
    ordinary = {
        "contract": identity,
        "operations": ordinary_operations,
        "sources": ordinary_sources,
        "evidence": ordinary_evidence,
        "claim_evidence_source_links": ordinary_links,
    }
    restricted = {
        "contract": identity,
        "operations": restricted_operations,
    }
    return SearchToolProjections(
        ordinary=OrdinarySearchToolProjection(
            _canonical_bytes(ordinary),
            _token=_TOKEN,
        ),
        restricted=RestrictedSearchToolProjection(
            _canonical_bytes(restricted),
            _token=_TOKEN,
        ),
        _token=_TOKEN,
    )
