"""Provider-neutral mechanical enforcement for evaluation data handling.

The frozen policy owns classification and projection boundaries only.  This
module deliberately does not persist evidence, load credentials, choose a
provider, access a network, or authorize evaluation execution.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from app.services.evaluation_attempt_state import TERMINAL_OUTCOMES
from app.services.evaluation_contract_identity import load_strict_contract_json
from app.services.evaluation_retrieval_trace import PublicSafeDeduplicationKey
from app.services.url_security import validate_url_security


POLICY_ID = "provider_data_handling_review_v1"
POLICY_VERSION = "v1"
POLICY_HASH = "e3c909e117177208eac123986318d5ba448479ef4d68d226c00d656b7e3e47a5"

_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+\-]{0,127}\Z")
_UTC_MILLISECOND = re.compile(
    r"(?:19|20)[0-9]{2}-(?:0[1-9]|1[0-2])-"
    r"(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\."
    r"[0-9]{3}Z\Z"
)
_TRACE_REFERENCE = re.compile(r"rtr-v1-[0-9a-f]{32}\Z")

_SAFE_METADATA_FIELDS = (
    "provider",
    "model",
    "model_version_or_snapshot",
    "provider_request_id",
    "http_or_result_status",
    "started_at",
    "completed_at",
    "latency_measurements",
    "input_token_usage",
    "output_token_usage",
    "reasoning_usage_if_exposed",
    "image_usage_if_exposed",
    "finish_or_stop_reason",
    "attempt_number",
    "retry_count",
)
_CURRENTLY_ACCEPTED_SAFE_METADATA_FIELDS = frozenset(_SAFE_METADATA_FIELDS) - {
    "provider_request_id"
}
_LATENCY_FIELDS = frozenset(
    {
        "end_to_end_latency_ms",
        "provider_latency_ms",
        "time_to_first_result_ms_if_available",
        "search_latency_ms",
        "image_normalization_latency_ms",
        "visual_latency_ms",
    }
)
_PUBLIC_URL_DOWNSTREAM_CONTRACTS = frozenset(
    {"retrieval_evidence_bundle_v1", "safe_search_tool_record_v1"}
)
_STATUS_KINDS = frozenset({"http_status", "terminal_outcome"})
_URL_CLASSIFIER_INPUT_KEYS = frozenset(
    {
        "exact_url",
        "url_role",
        "retrieval_auth_context",
        "redirect_context",
        "origin_rule",
        "restricted_trace_reference",
    }
)
_REDIRECT_CONTEXT_KEYS = frozenset(
    {
        "capture_status",
        "current_position",
        "requested_position",
        "final_position",
        "members",
    }
)
_REDIRECT_MEMBER_KEYS = frozenset(
    {
        "position",
        "url_role",
        "exact_url",
        "retrieval_auth_context",
        "origin_rule",
        "restricted_trace_reference",
    }
)
_URL_CLASSIFIER_OUTPUT_KEYS = frozenset(
    {
        "classification",
        "reason_codes",
        "url_role",
        "restricted_trace_reference",
        "policy_id",
        "policy_version",
        "policy_hash",
    }
)
_LIFECYCLE_MEMBERS = frozenset(
    {
        "raw_provider_response",
        "exact_url_traces",
        "restricted_transport_metadata",
        "restricted_linkage_material",
        "raw_search_queries",
        "raw_tool_arguments",
    }
)
_DATA_HANDLING_ARTIFACT_REQUIRED_KEYS = frozenset(
    {
        "artifact_id",
        "artifact_kind",
        "artifact_version",
        "authority",
        "access_policy",
        "credential_boundary",
        "cross_contract_compatibility",
        "data_classes",
        "deletion_lifecycle",
        "exact_url_policy",
        "execution_boundary",
        "explicitly_forbidden_ordinary_metadata",
        "fail_closed_policy",
        "final_invariants",
        "hash_and_linkage_classification",
        "implementation_contract",
        "ordinary_projection",
        "provider_calls_completed",
        "provider_neutral",
        "purpose",
        "raw_provider_response_policy",
        "regional_binding",
        "restricted_projection",
        "restricted_trace_reference",
        "restricted_transport_metadata",
        "retention_policy",
        "safe_transport_metadata",
        "specification_identity",
        "specification_only",
        "status",
    }
)
_PROJECTION_TOKEN = object()


class DataHandlingPolicyError(ValueError):
    """A provider-evaluation datum violated the frozen privacy boundary."""


def _fail(code: str) -> DataHandlingPolicyError:
    return DataHandlingPolicyError(code)


@dataclass(frozen=True, slots=True)
class _FrozenList:
    items: tuple[Any, ...]


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
        raise _fail("policy_identity_canonicalization") from exc


def _pointer_segments(pointer: Any) -> tuple[str, ...]:
    if type(pointer) is not str or not pointer.startswith("/"):
        raise _fail("policy_identity_pointer")
    result: list[str] = []
    for raw in pointer[1:].split("/"):
        decoded: list[str] = []
        index = 0
        while index < len(raw):
            if raw[index] != "~":
                decoded.append(raw[index])
                index += 1
                continue
            if index + 1 >= len(raw) or raw[index + 1] not in {"0", "1"}:
                raise _fail("policy_identity_pointer")
            decoded.append("~" if raw[index + 1] == "0" else "/")
            index += 2
        result.append("".join(decoded))
    return tuple(result)


def _delete_pointer(document: Any, pointer: Any) -> None:
    segments = _pointer_segments(pointer)
    if not segments:
        raise _fail("policy_identity_pointer")
    parent = document
    for segment in segments[:-1]:
        if type(parent) is not dict or segment not in parent:
            raise _fail("policy_identity_pointer")
        parent = parent[segment]
    if type(parent) is not dict or segments[-1] not in parent:
        raise _fail("policy_identity_pointer")
    del parent[segments[-1]]


def _validate_policy_structure(artifact: dict[str, Any]) -> None:
    if frozenset(artifact) != _DATA_HANDLING_ARTIFACT_REQUIRED_KEYS:
        raise _fail("policy_artifact_keys")
    if (
        artifact.get("artifact_id") != POLICY_ID
        or artifact.get("artifact_version") != POLICY_VERSION
        or artifact.get("status") != "frozen"
        or artifact.get("provider_neutral") is not True
        or artifact.get("provider_calls_completed") != 0
    ):
        raise _fail("policy_artifact_identity")
    execution = artifact.get("execution_boundary")
    if execution != {
        "authoritative_execution_gate": "experiment.v1.json execution_gate",
        "execution_state": "blocked_pre_execution",
        "provider_calls_allowed": False,
        "pilot_calls_allowed": False,
        "scored_calls_allowed": False,
        "this_artifact_independently_authorizes_execution": False,
    }:
        raise _fail("policy_execution_boundary")
    retention = artifact.get("retention_policy")
    if not isinstance(retention, dict) or (
        retention.get("restricted_retention_days") != 30
        or retention.get("clock_starts_at")
        != "final_model_selection_decision_at"
    ):
        raise _fail("policy_retention")
    fields = artifact.get("safe_transport_metadata", {}).get("field_definitions")
    if not isinstance(fields, dict) or tuple(fields) != _SAFE_METADATA_FIELDS:
        raise _fail("policy_safe_metadata_inventory")
    if fields["provider_request_id"].get("runtime_acceptance") != (
        "blocked_until_provider_specific_non_secret_verifier_is_frozen"
    ):
        raise _fail("policy_provider_request_id_boundary")


def verify_provider_data_handling_artifact(path: str | Path) -> dict[str, Any]:
    """Strictly parse, structurally validate, and recompute the policy identity."""
    artifact = load_strict_contract_json(path)
    _validate_policy_structure(artifact)
    try:
        identity = artifact["specification_identity"]
        semantic = identity["semantic_identity"]
        exclusions = semantic["semantic_excluded_json_pointers"]
        stored_hash = identity["derived_hash_cache"]["policy_semantic_hash"]
    except (KeyError, TypeError) as exc:
        raise _fail("policy_identity_shape") from exc
    if (
        identity.get("policy_id") != POLICY_ID
        or identity.get("policy_version") != POLICY_VERSION
        or semantic.get("identity_domain")
        != "trustai.provider_data_handling_review.v1"
        or type(exclusions) is not list
        or len(exclusions) != len(set(exclusions))
        or _LOWER_SHA256.fullmatch(stored_hash or "") is None
    ):
        raise _fail("policy_identity_shape")
    content = copy.deepcopy(artifact)
    for pointer in exclusions:
        _delete_pointer(content, pointer)
    envelope = {
        "identity_domain": semantic["identity_domain"],
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "content": content,
    }
    computed = hashlib.sha256(_canonical_bytes(envelope)).hexdigest()
    if computed != stored_hash or computed != POLICY_HASH:
        raise _fail("policy_identity_mismatch")
    return artifact


def _freeze_value(value: Any) -> Any:
    if value is None or type(value) in {str, int, bool, bytes}:
        return value
    if type(value) is tuple:
        return tuple(_freeze_value(item) for item in value)
    if type(value) is list:
        return _FrozenList(tuple(_freeze_value(item) for item in value))
    if type(value) is dict:
        return tuple((key, _freeze_value(item)) for key, item in value.items())
    raise _fail("projection_value_type")


def _thaw_value(value: Any) -> Any:
    if isinstance(value, _FrozenList):
        return [_thaw_value(item) for item in value.items]
    if type(value) is tuple:
        if all(
            type(item) is tuple and len(item) == 2 and type(item[0]) is str
            for item in value
        ):
            return {key: _thaw_value(item) for key, item in value}
        return tuple(_thaw_value(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class SafeTransportMetadata:
    values: tuple[tuple[str, Any], ...]
    _token: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _PROJECTION_TOKEN:
            raise _fail("safe_transport_metadata_factory_required")

    def as_dict(self) -> dict[str, Any]:
        return {key: _thaw_value(value) for key, value in self.values}


class RestrictedTraceReference:
    __slots__ = ("_value",)

    def __init__(self, value: str, *, _token: object | None = None) -> None:
        if _token is not _TRACE_REFERENCE_TOKEN:
            raise _fail("restricted_trace_reference_factory_required")
        if _TRACE_REFERENCE.fullmatch(value) is None:
            raise _fail("restricted_trace_reference_format")
        object.__setattr__(self, "_value", value)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("restricted_trace_reference_is_immutable")

    @property
    def value(self) -> str:
        return self._value


_TRACE_REFERENCE_TOKEN = object()


def derive_restricted_trace_reference(random_bytes: bytes) -> RestrictedTraceReference:
    """Render caller-supplied independent random bytes without any URL input."""
    if type(random_bytes) is not bytes or len(random_bytes) != 16:
        raise _fail("restricted_trace_entropy")
    return RestrictedTraceReference(
        f"rtr-v1-{random_bytes.hex()}",
        _token=_TRACE_REFERENCE_TOKEN,
    )


@dataclass(frozen=True, slots=True)
class RestrictedUrlTrace:
    """One complete frozen URL-classifier input retained only as evidence."""

    restricted_input: tuple[tuple[str, Any], ...] = field(repr=False)
    safe_classifier_result: tuple[tuple[str, Any], ...]
    _token: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _PROJECTION_TOKEN:
            raise _fail("restricted_url_trace_factory_required")

    def as_restricted_dict(self) -> dict[str, Any]:
        return {
            key: _thaw_value(value)
            for key, value in self.restricted_input
        }

    def as_safe_result_dict(self) -> dict[str, Any]:
        return {
            key: _thaw_value(value)
            for key, value in self.safe_classifier_result
        }


def capture_restricted_url_trace(
    classifier_input: Mapping[str, Any],
    *,
    reference_capabilities: Mapping[int, RestrictedTraceReference],
) -> RestrictedUrlTrace:
    """Validate and freeze one complete exact URL/redirect classifier input."""
    if type(classifier_input) is not dict or set(classifier_input) != (
        _URL_CLASSIFIER_INPUT_KEYS
    ):
        raise _fail("classifier_input_keys")
    if type(reference_capabilities) is not dict:
        raise _fail("reference_inventory")
    try:
        captured = copy.deepcopy(classifier_input)
    except (TypeError, ValueError, RecursionError) as exc:
        raise _fail("restricted_url_trace_copy") from exc
    redirect = captured.get("redirect_context")
    if type(redirect) is not dict or set(redirect) != _REDIRECT_CONTEXT_KEYS:
        raise _fail("redirect_context_keys")
    members = redirect.get("members")
    if type(members) is not list or not members:
        raise _fail("redirect_member_inventory")
    positions: list[int] = []
    for member in members:
        if type(member) is not dict or set(member) != _REDIRECT_MEMBER_KEYS:
            raise _fail("redirect_member_keys")
        position = member.get("position")
        if type(position) is not int or position < 0:
            raise _fail("redirect_member_position")
        positions.append(position)
    if set(reference_capabilities) != set(positions) or len(positions) != len(
        set(positions)
    ):
        raise _fail("reference_inventory")
    for member in members:
        position = member["position"]
        capability = reference_capabilities[position]
        if not isinstance(capability, RestrictedTraceReference):
            raise _fail("reference_capability")
        if member["restricted_trace_reference"] != capability.value:
            raise _fail("reference_mismatch")
    current_position = redirect.get("current_position")
    if (
        type(current_position) is not int
        or current_position < 0
        or current_position >= len(members)
    ):
        raise _fail("redirect_current_position")
    current = members[current_position]
    outer = {
        key: captured[key]
        for key in _REDIRECT_MEMBER_KEYS
        if key != "position"
    }
    current_without_position = {
        key: current[key]
        for key in _REDIRECT_MEMBER_KEYS
        if key != "position"
    }
    if outer != current_without_position:
        raise _fail("classifier_current_member_mismatch")
    try:
        safe_result = validate_url_security(**captured)
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise _fail("restricted_url_trace_validation") from exc
    if type(safe_result) is not dict or set(safe_result) != (
        _URL_CLASSIFIER_OUTPUT_KEYS
    ):
        raise _fail("url_classifier_output_keys")
    if (
        safe_result.get("restricted_trace_reference")
        != current["restricted_trace_reference"]
    ):
        raise _fail("url_classifier_reference_mismatch")
    return RestrictedUrlTrace(
        restricted_input=tuple(
            (key, _freeze_value(value)) for key, value in captured.items()
        ),
        safe_classifier_result=tuple(
            (key, _freeze_value(value)) for key, value in safe_result.items()
        ),
        _token=_PROJECTION_TOKEN,
    )


class PublicSafeUrlDisclosure:
    __slots__ = ("_canonical_url", "_downstream_contract_id", "_policy_identity")

    def __init__(
        self,
        *,
        canonical_url: str,
        downstream_contract_id: str,
        policy_identity: tuple[str, str, str],
        _token: object | None = None,
    ) -> None:
        if _token is not _PUBLIC_URL_DISCLOSURE_TOKEN:
            raise _fail("public_url_disclosure_factory_required")
        object.__setattr__(self, "_canonical_url", canonical_url)
        object.__setattr__(self, "_downstream_contract_id", downstream_contract_id)
        object.__setattr__(self, "_policy_identity", policy_identity)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("public_url_disclosure_is_immutable")

    @property
    def canonical_url(self) -> str:
        return self._canonical_url

    @property
    def downstream_contract_id(self) -> str:
        return self._downstream_contract_id

    @property
    def policy_identity(self) -> tuple[str, str, str]:
        return self._policy_identity


_PUBLIC_URL_DISCLOSURE_TOKEN = object()


def authorize_public_safe_url(
    key: PublicSafeDeduplicationKey,
    *,
    downstream_contract_id: str,
) -> PublicSafeUrlDisclosure:
    """Bind an application-validated public-safe URL to an allowed consumer."""
    if not isinstance(key, PublicSafeDeduplicationKey):
        raise _fail("public_safe_url_capability_required")
    if downstream_contract_id not in _PUBLIC_URL_DOWNSTREAM_CONTRACTS:
        raise _fail("downstream_url_disclosure_not_permitted")
    if (
        key.policy_identity[0] != "url_security_policy_v1"
        or key.policy_identity[1] != "v1"
        or _LOWER_SHA256.fullmatch(key.policy_identity[2]) is None
        or not key.safe_canonical_url
    ):
        raise _fail("public_safe_url_capability_invalid")
    return PublicSafeUrlDisclosure(
        canonical_url=key.safe_canonical_url,
        downstream_contract_id=downstream_contract_id,
        policy_identity=key.policy_identity,
        _token=_PUBLIC_URL_DISCLOSURE_TOKEN,
    )


def _require_safe_identifier(field: str, value: Any) -> str:
    if type(value) is not str or _SAFE_IDENTIFIER.fullmatch(value) is None:
        raise _fail(f"metadata_type:{field}")
    return value


def _require_non_negative_integer(field: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise _fail(f"metadata_type:{field}")
    return value


def _validate_timestamp(field: str, value: Any) -> str:
    if type(value) is not str or _UTC_MILLISECOND.fullmatch(value) is None:
        raise _fail(f"metadata_type:{field}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _fail(f"metadata_type:{field}") from exc
    if parsed.tzinfo != UTC:
        raise _fail(f"metadata_type:{field}")
    return value


def _validate_status(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {"kind", "value"}:
        raise _fail("metadata_type:http_or_result_status")
    kind = value["kind"]
    status = value["value"]
    if kind not in _STATUS_KINDS:
        raise _fail("metadata_type:http_or_result_status")
    if kind == "http_status":
        if type(status) is not int or not 100 <= status <= 599:
            raise _fail("metadata_type:http_or_result_status")
    elif type(status) is not str or status not in TERMINAL_OUTCOMES:
        raise _fail("metadata_type:http_or_result_status")
    return {"kind": kind, "value": status}


def _validate_latency(value: Any) -> dict[str, int]:
    if type(value) is not dict:
        raise _fail("metadata_type:latency_measurements")
    if not set(value) <= _LATENCY_FIELDS:
        raise _fail("metadata_field_not_allowed")
    result: dict[str, int] = {}
    for key, item in value.items():
        result[key] = _require_non_negative_integer(key, item)
    return result


def sanitize_transport_metadata(metadata: Mapping[str, Any]) -> SafeTransportMetadata:
    """Copy and validate only the exact closed ordinary metadata surface."""
    if type(metadata) is not dict:
        raise _fail("metadata_container_type")
    for key in metadata:
        if type(key) is not str or key not in _SAFE_METADATA_FIELDS:
            raise _fail("metadata_field_not_allowed")
        if key not in _CURRENTLY_ACCEPTED_SAFE_METADATA_FIELDS:
            raise _fail("provider_request_id_verifier_not_frozen")

    validated: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in {"provider", "model", "model_version_or_snapshot"}:
            validated[key] = _require_safe_identifier(key, value)
        elif key in {"started_at", "completed_at"}:
            validated[key] = _validate_timestamp(key, value)
        elif key == "http_or_result_status":
            validated[key] = _validate_status(value)
        elif key == "latency_measurements":
            validated[key] = _validate_latency(value)
        elif key in {
            "input_token_usage",
            "output_token_usage",
            "reasoning_usage_if_exposed",
            "image_usage_if_exposed",
            "retry_count",
        }:
            validated[key] = _require_non_negative_integer(key, value)
        elif key == "attempt_number":
            validated[key] = _require_non_negative_integer(key, value)
            if value < 1:
                raise _fail("metadata_type:attempt_number")
        elif key == "finish_or_stop_reason":
            if type(value) is not str or value not in TERMINAL_OUTCOMES:
                raise _fail("metadata_type:finish_or_stop_reason")
            validated[key] = value
        else:  # pragma: no cover - closed inventory guarded above
            raise _fail("metadata_field_not_allowed")
    frozen = tuple((key, _freeze_value(validated[key])) for key in metadata)
    return SafeTransportMetadata(frozen, _token=_PROJECTION_TOKEN)


@dataclass(frozen=True, slots=True)
class OrdinaryProviderDataProjection:
    raw_provider_response_hash: str | None
    restricted_trace_reference: str | None
    public_safe_canonical_urls: tuple[str, ...]
    safe_transport_metadata: SafeTransportMetadata
    _token: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _PROJECTION_TOKEN:
            raise _fail("ordinary_projection_factory_required")

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_provider_response_hash": self.raw_provider_response_hash,
            "restricted_trace_reference": self.restricted_trace_reference,
            "public_safe_canonical_urls": self.public_safe_canonical_urls,
            "safe_transport_metadata": self.safe_transport_metadata.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class RestrictedProviderDataProjection:
    raw_provider_response: bytes | None = field(repr=False)
    exact_url_traces: tuple[tuple[tuple[str, Any], ...], ...] = field(repr=False)
    restricted_url_hashes: tuple[str, ...] = field(repr=False)
    restricted_transport_metadata: tuple[tuple[str, Any], ...] = field(repr=False)
    _token: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _PROJECTION_TOKEN:
            raise _fail("restricted_projection_factory_required")

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_provider_response": self.raw_provider_response,
            "exact_url_traces": _thaw_value(self.exact_url_traces),
            "restricted_url_hashes": self.restricted_url_hashes,
            "restricted_transport_metadata": {
                key: _thaw_value(value)
                for key, value in self.restricted_transport_metadata
            },
        }


@dataclass(frozen=True, slots=True)
class ProviderDataProjections:
    ordinary: OrdinaryProviderDataProjection
    restricted: RestrictedProviderDataProjection = field(repr=False)
    _token: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _PROJECTION_TOKEN:
            raise _fail("provider_data_projections_factory_required")


def project_provider_data(
    *,
    raw_provider_response: bytes | None,
    restricted_url_trace: RestrictedUrlTrace | None,
    safe_transport_metadata: Mapping[str, Any],
    public_safe_url_disclosures: Sequence[PublicSafeUrlDisclosure] = (),
    ordinary_hashes: Mapping[str, str] | None = None,
    restricted_url_hashes: Sequence[str] = (),
    restricted_transport_metadata: Mapping[str, Any] | None = None,
    credential_material: Any = None,
) -> ProviderDataProjections:
    """Build disjoint immutable projections without semantic repair."""
    if credential_material is not None:
        raise _fail("credential_material_forbidden")
    if raw_provider_response is not None and type(raw_provider_response) is not bytes:
        raise _fail("raw_provider_response_type")
    if restricted_url_trace is not None and not isinstance(
        restricted_url_trace, RestrictedUrlTrace
    ):
        raise _fail("restricted_url_trace_capability")
    if ordinary_hashes is not None:
        if type(ordinary_hashes) is not dict:
            raise _fail("ordinary_hash_container")
        for name, value in ordinary_hashes.items():
            if name != "raw_provider_response_hash":
                if "url" in str(name).lower():
                    raise _fail("restricted_url_hash_forbidden")
                raise _fail("ordinary_hash_not_allowed")
            if _LOWER_SHA256.fullmatch(value or "") is None:
                raise _fail("ordinary_hash_invalid")
    if restricted_transport_metadata:
        raise _fail("restricted_metadata_binding_not_frozen")
    if restricted_transport_metadata is not None and type(
        restricted_transport_metadata
    ) is not dict:
        raise _fail("restricted_metadata_container")
    if type(restricted_url_hashes) not in {tuple, list}:
        raise _fail("restricted_url_hash_container")
    restricted_hashes = tuple(restricted_url_hashes)
    if any(_LOWER_SHA256.fullmatch(value or "") is None for value in restricted_hashes):
        raise _fail("restricted_url_hash_invalid")
    if type(public_safe_url_disclosures) not in {tuple, list}:
        raise _fail("public_url_disclosure_container")
    disclosures = tuple(public_safe_url_disclosures)
    if any(not isinstance(value, PublicSafeUrlDisclosure) for value in disclosures):
        raise _fail("public_safe_url_capability_required")

    raw_hash = (
        hashlib.sha256(raw_provider_response).hexdigest()
        if raw_provider_response is not None
        else None
    )
    if ordinary_hashes and ordinary_hashes.get("raw_provider_response_hash") != raw_hash:
        raise _fail("raw_provider_response_hash_mismatch")
    safe_metadata = sanitize_transport_metadata(dict(safe_transport_metadata))
    safe_url_result = (
        restricted_url_trace.as_safe_result_dict()
        if restricted_url_trace is not None
        else None
    )
    if disclosures:
        if restricted_url_trace is None or safe_url_result is None:
            raise _fail("public_url_trace_binding")
        restricted_url_input = restricted_url_trace.as_restricted_dict()
        safe_policy_identity = (
            safe_url_result["policy_id"],
            safe_url_result["policy_version"],
            safe_url_result["policy_hash"],
        )
        if (
            len(disclosures) != 1
            or safe_url_result["classification"] != "public_safe"
            or safe_url_result["url_role"] != "final_url"
            or disclosures[0].canonical_url != restricted_url_input["exact_url"]
            or disclosures[0].policy_identity != safe_policy_identity
        ):
            raise _fail("public_url_trace_binding")

    ordinary = OrdinaryProviderDataProjection(
        raw_provider_response_hash=raw_hash,
        restricted_trace_reference=(
            safe_url_result["restricted_trace_reference"]
            if safe_url_result is not None
            else None
        ),
        public_safe_canonical_urls=tuple(
            disclosure.canonical_url for disclosure in disclosures
        ),
        safe_transport_metadata=safe_metadata,
        _token=_PROJECTION_TOKEN,
    )
    restricted = RestrictedProviderDataProjection(
        raw_provider_response=(
            bytes(raw_provider_response) if raw_provider_response is not None else None
        ),
        exact_url_traces=(
            (restricted_url_trace.restricted_input,)
            if restricted_url_trace is not None
            else ()
        ),
        restricted_url_hashes=restricted_hashes,
        restricted_transport_metadata=(),
        _token=_PROJECTION_TOKEN,
    )
    return ProviderDataProjections(
        ordinary=ordinary,
        restricted=restricted,
        _token=_PROJECTION_TOKEN,
    )


@dataclass(frozen=True, slots=True)
class RestrictedRetentionAssessment:
    state: str
    expires_at: datetime | None
    deletion_schedule_resolved: bool
    deletion_required: bool


def _require_utc_datetime(label: str, value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo != UTC:
        raise _fail(f"{label}_must_be_utc")
    return value


def evaluate_restricted_retention(
    *,
    final_model_selection_decision_at: datetime | None,
    observed_at: datetime,
    lifecycle_member_deletion_states: Mapping[str, str] | None = None,
) -> RestrictedRetentionAssessment:
    """Evaluate the pure 30-day lifecycle without performing deletion."""
    observed = _require_utc_datetime("observed_at", observed_at)
    states = lifecycle_member_deletion_states or {}
    if type(states) is not dict or not set(states) <= _LIFECYCLE_MEMBERS:
        raise _fail("lifecycle_deletion_state")
    if states and set(states) != _LIFECYCLE_MEMBERS:
        raise _fail("lifecycle_member_inventory")
    if any(value not in {"retained", "deleted"} for value in states.values()):
        raise _fail("lifecycle_deletion_state")
    if states and len(set(states.values())) != 1:
        raise _fail("partial_lifecycle_deletion")
    if states and next(iter(states.values())) == "deleted":
        return RestrictedRetentionAssessment("deleted", None, True, False)
    if final_model_selection_decision_at is None:
        return RestrictedRetentionAssessment(
            "blocked_pending_final_model_selection_decision",
            None,
            False,
            False,
        )
    decision = _require_utc_datetime(
        "final_model_selection_decision_at",
        final_model_selection_decision_at,
    )
    if observed < decision:
        raise _fail("observed_before_final_decision")
    expires_at = decision + timedelta(days=30)
    if observed < expires_at:
        state = "retained"
    elif observed == expires_at:
        state = "deletion_due"
    else:
        state = "deletion_overdue"
    return RestrictedRetentionAssessment(
        state,
        expires_at,
        True,
        state in {"deletion_due", "deletion_overdue"},
    )


@dataclass(frozen=True, slots=True)
class RegionBindingAssessment:
    state: str
    pre_execution_ready: bool


def evaluate_region_binding(
    *,
    approved_execution_region: str | None,
    restricted_storage_region: str | None,
) -> RegionBindingAssessment:
    """Fail closed until one approved region exactly matches restricted storage."""
    if approved_execution_region is None or restricted_storage_region is None:
        return RegionBindingAssessment("blocked_pending_region_binding", False)
    if (
        type(approved_execution_region) is not str
        or type(restricted_storage_region) is not str
        or not approved_execution_region
        or not restricted_storage_region
    ):
        raise _fail("region_binding_type")
    if approved_execution_region != restricted_storage_region:
        return RegionBindingAssessment("blocked_region_mismatch", False)
    return RegionBindingAssessment("ready", True)
