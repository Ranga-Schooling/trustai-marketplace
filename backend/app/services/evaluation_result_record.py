"""Privacy-safe foundation for provider-neutral evaluation attempt records.

The frozen normalization contract explicitly requires a future complete result
record artifact.  This module does not invent that contract.  It only composes
the attempt-state and provider-data projections whose ownership is already
frozen, while retaining restricted data behind its existing capability type.
It performs no persistence, provider call, network operation, retry, or other
execution action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from app.services.evaluation_attempt_state import (
    HIGHEST_COMPLETED_STAGES,
    NORMALIZATION_ACTIONS,
    NormalizationActionRecord,
    AttemptState,
    summarize_normalization_actions,
    validate_attempt_state,
)
from app.services.evaluation_contract_identity import (
    ContractIdentityError,
    load_strict_contract_json,
    load_strict_normalization_spec,
    verify_normalization_parser_artifact,
    verify_output_schema_artifact,
    verify_prompt_template_artifact,
)
from app.services.evaluation_data_handling import (
    POLICY_HASH as DATA_HANDLING_POLICY_HASH,
    POLICY_ID as DATA_HANDLING_POLICY_ID,
    POLICY_VERSION as DATA_HANDLING_POLICY_VERSION,
    ProviderDataProjections,
    RestrictedProviderDataProjection,
    SafeTransportMetadata,
)
from app.services.evaluation_pricing import (
    PricingContractError,
    verify_estimated_cost_record,
)
from app.services.evaluation_ps1 import (
    EVIDENCE_EXTRACTOR_POLICY_HASH,
    OBJECTIVE_SUPPORT_POLICY_HASH,
    ORIGIN_RULE_REGISTRY_HASH,
    SOURCE_CLASSIFICATION_POLICY_HASH,
    Ps1AssemblyResult,
)
from app.services.evaluation_retry_policy import (
    MAXIMUM_PHYSICAL_ATTEMPTS,
    SAFE_RETRY_REASONS,
    RetryPolicyError,
    validate_retry_linkage,
)
from app.services.evaluation_request_configurations import (
    PilotRequestConfigurationError,
    PilotRequestConfigurationSelection,
    validate_request_configuration_record,
)
from app.services.evaluation_search_tool_record import (
    RestrictedSearchToolProjection,
    SearchToolRecordError,
    SearchToolProjections,
    verify_safe_search_tool_record_contract,
)
from app.services.url_security import validate_url_security


FULL_RESULT_RECORD_BLOCKERS = (
    "pilot_result_record_builder_required",
    "immutable_run_binding",
    "adapter_and_transport_bindings",
    "complete_stage_hash_inventory",
    "result_identity_and_timing",
    "retry_run_record",
)

_FOUNDATION_TOKEN = object()
_PILOT_RECORD_TOKEN = object()
_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CONTRACT = (
    _ROOT / "docs" / "testing" / "ai-evaluation" / "result-record.v1.json"
)
_NORMALIZATION_CONTRACT = (
    _ROOT
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "normalization-parser.v1.json"
)
_NORMALIZATION_IMPLEMENTATION = (
    _ROOT / "backend" / "app" / "services" / "normalization_parser.py"
)
_RUBRIC_CONTRACT = (
    _ROOT / "docs" / "testing" / "ai-evaluation" / "rubric.v1.json"
)
_PROMPT_CONTRACT = (
    _ROOT / "docs" / "testing" / "ai-evaluation" / "prompt-templates.v1.json"
)
_SCHEMA_CONTRACT = (
    _ROOT / "docs" / "testing" / "ai-evaluation" / "output-schemas.v1.json"
)
_SAFE_SEARCH_TOOL_CONTRACT = (
    _ROOT
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "safe-search-tool-record.v1.json"
)
_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+@\-]{0,255}\Z")
_FROZEN_PROVIDER_DISPLAY_NAMES = frozenset({"Google Gemini"})
_UTC_MILLISECOND = re.compile(
    r"(?:19|20)[0-9]{2}-(?:0[1-9]|1[0-2])-"
    r"(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\."
    r"[0-9]{3}Z\Z"
)
_ATTEMPT_KEY_FIELDS = (
    "evaluation_id",
    "fixture_id",
    "candidate_id",
    "provider",
    "model",
    "component_topology",
    "workload",
    "run_number",
    "attempt_number",
)
_TRANSPORT_MODES = (
    "non_streaming_http",
    "streaming",
    "sdk_native_structured",
)
_WORKLOAD_BY_BRANCH = {
    "text_final": "text_risk_analysis",
    "search_retrieval": "grounded_product_price_research",
    "search_synthesis_final": "grounded_product_price_research",
    "visual_final": "visual_inspection",
}
_PROMPT_SCHEMA_IDS_BY_BRANCH = {
    "text_final": (
        "text_system_v1",
        "text_input_v1",
        "text_output_schema_v1",
    ),
    "search_retrieval": (
        "search_retrieval_v1",
        "retrieval_evidence_bundle_v1",
    ),
    "search_synthesis_final": (
        "search_synthesis_v1",
        "search_output_schema_v1",
    ),
    "visual_final": (
        "visual_system_v1",
        "visual_context_v1",
        "visual_output_schema_v1",
    ),
}
_NORMALIZATION_ACTION_FIELDS = {
    "ordinal",
    "action",
    "policy_id",
    "policy_version",
    "policy_hash",
    "adapter_id_if_applicable",
    "adapter_version_if_applicable",
    "adapter_hash_if_applicable",
    "input_hash",
    "output_hash",
    "trace_references",
    "deterministic_parameters",
    "action_result",
}
_RESULT_RECORD_ARTIFACT_KEYS = {
    "artifact_id",
    "artifact_version",
    "status",
    "purpose",
    "provider_neutral",
    "source_contracts",
    "record_model",
    "attempt_key",
    "normalization_audit_fields",
    "pilot_envelope_fields",
    "scored_only_fields",
    "rubric_aliases",
    "retry_linkage",
    "validation_rules",
    "privacy",
    "deferred",
    "execution_boundary",
    "specification_identity",
}


class ResultRecordFoundationError(ValueError):
    """An already-frozen attempt/result-record boundary was violated."""


def _fail(code: str) -> ResultRecordFoundationError:
    return ResultRecordFoundationError(code)


@dataclass(frozen=True, slots=True)
class SafeValidatorState:
    validator_id: str
    applicability: str
    state: str

    def as_dict(self) -> dict[str, str]:
        return {
            "validator_id": self.validator_id,
            "applicability": self.applicability,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class OrdinaryAttemptRecordFoundation:
    workload_branch: str
    normalized_presemantic_state: str
    highest_completed_stage: str
    normalization_disposition: str
    terminal_outcome: str
    attempt_outcome: str
    validator_states: tuple[SafeValidatorState, ...]
    refusal_state: str
    failure_category: str | None
    raw_provider_response_hash: str | None
    canonical_evidence_bundle_hash_if_applicable: str | None
    final_semantic_payload_hash_if_applicable: str | None
    restricted_trace_reference_if_applicable: str | None
    url_security_classification_if_applicable: str | None
    url_security_reason_codes_if_applicable: tuple[str, ...] | None
    url_security_policy_id_if_applicable: str | None
    url_security_policy_version_if_applicable: str | None
    url_security_policy_hash_if_applicable: str | None
    public_safe_canonical_urls: tuple[str, ...]
    safe_transport_metadata: SafeTransportMetadata
    _token: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _FOUNDATION_TOKEN:
            raise _fail("ordinary_foundation_factory_required")

    def as_dict(self) -> dict[str, Any]:
        return {
            "workload_branch": self.workload_branch,
            "normalized_presemantic_state": self.normalized_presemantic_state,
            "highest_completed_stage": self.highest_completed_stage,
            "normalization_disposition": self.normalization_disposition,
            "terminal_outcome": self.terminal_outcome,
            "attempt_outcome": self.attempt_outcome,
            "validator_states": [item.as_dict() for item in self.validator_states],
            "refusal_state": self.refusal_state,
            "failure_category": self.failure_category,
            "raw_provider_response_hash": self.raw_provider_response_hash,
            "canonical_evidence_bundle_hash_if_applicable": (
                self.canonical_evidence_bundle_hash_if_applicable
            ),
            "final_semantic_payload_hash_if_applicable": (
                self.final_semantic_payload_hash_if_applicable
            ),
            "restricted_trace_reference_if_applicable": (
                self.restricted_trace_reference_if_applicable
            ),
            "url_security_classification_if_applicable": (
                self.url_security_classification_if_applicable
            ),
            "url_security_reason_codes_if_applicable": (
                list(self.url_security_reason_codes_if_applicable)
                if self.url_security_reason_codes_if_applicable is not None
                else None
            ),
            "url_security_policy_id_if_applicable": (
                self.url_security_policy_id_if_applicable
            ),
            "url_security_policy_version_if_applicable": (
                self.url_security_policy_version_if_applicable
            ),
            "url_security_policy_hash_if_applicable": (
                self.url_security_policy_hash_if_applicable
            ),
            "public_safe_canonical_urls": list(self.public_safe_canonical_urls),
            "safe_transport_metadata": self.safe_transport_metadata.as_dict(),
            "provider_data_handling_policy": {
                "policy_id": DATA_HANDLING_POLICY_ID,
                "policy_version": DATA_HANDLING_POLICY_VERSION,
                "policy_hash": DATA_HANDLING_POLICY_HASH,
            },
        }


@dataclass(frozen=True, slots=True)
class PrivacySafeAttemptRecordFoundation:
    ordinary: OrdinaryAttemptRecordFoundation
    restricted_provider_data: RestrictedProviderDataProjection = field(repr=False)
    full_result_record_blockers: tuple[str, ...]
    complete_result_record_eligible: bool
    execution_authority: bool
    _token: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _FOUNDATION_TOKEN:
            raise _fail("attempt_record_foundation_factory_required")
        if (
            self.full_result_record_blockers != FULL_RESULT_RECORD_BLOCKERS
            or self.complete_result_record_eligible is not False
            or self.execution_authority is not False
        ):
            raise _fail("attempt_record_foundation_boundary")


def _safe_url_result(
    provider_data: ProviderDataProjections,
) -> dict[str, Any] | None:
    restricted = provider_data.restricted.as_dict()
    traces = restricted["exact_url_traces"]
    reference = provider_data.ordinary.restricted_trace_reference
    if not traces:
        if reference is not None:
            raise _fail("restricted_trace_reference_without_trace")
        return None
    if len(traces) != 1:
        raise _fail("restricted_trace_cardinality")
    trace = traces[0]
    try:
        result = validate_url_security(**trace)
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise _fail("restricted_trace_revalidation") from exc
    if result.get("restricted_trace_reference") != reference:
        raise _fail("restricted_trace_reference_mismatch")
    return result


def _validate_projection_coherence(
    state: AttemptState,
    provider_data: ProviderDataProjections,
    safe_url_result: dict[str, Any] | None,
) -> None:
    ordinary = provider_data.ordinary
    restricted = provider_data.restricted
    if ordinary.raw_provider_response_hash != state.raw_provider_response_hash:
        raise _fail("raw_provider_response_hash_mismatch")
    raw = restricted.raw_provider_response
    if (raw is None) != (ordinary.raw_provider_response_hash is None):
        raise _fail("raw_provider_response_availability_mismatch")

    metadata = ordinary.safe_transport_metadata.as_dict()
    status = metadata.get("http_or_result_status")
    if status is not None and status["kind"] == "terminal_outcome":
        if status["value"] != state.terminal_outcome:
            raise _fail("terminal_outcome_metadata_mismatch")
    finish_reason = metadata.get("finish_or_stop_reason")
    if finish_reason is not None and finish_reason != state.terminal_outcome:
        raise _fail("finish_reason_metadata_mismatch")

    has_url_data = safe_url_result is not None or bool(
        ordinary.public_safe_canonical_urls
    )
    if has_url_data and state.workload_branch != "search_retrieval":
        raise _fail("url_trace_workload_branch")
    if state.terminal_outcome == "failed_url_security_validation":
        if safe_url_result is None:
            raise _fail("url_security_trace_required")
        if safe_url_result["classification"] == "public_safe":
            raise _fail("url_security_failure_classification")
        if ordinary.public_safe_canonical_urls:
            raise _fail("url_security_failure_public_url")
    if ordinary.public_safe_canonical_urls:
        if (
            state.terminal_outcome != "accepted"
            or safe_url_result is None
            or safe_url_result["classification"] != "public_safe"
        ):
            raise _fail("public_url_attempt_state")


def build_privacy_safe_attempt_record(
    *,
    attempt_state: AttemptState,
    provider_data: ProviderDataProjections,
) -> PrivacySafeAttemptRecordFoundation:
    """Compose frozen state and privacy projections without completing a run record."""
    try:
        validate_attempt_state(attempt_state)
    except (TypeError, ValueError) as exc:
        raise _fail("attempt_state_invalid") from exc
    if not isinstance(provider_data, ProviderDataProjections):
        raise _fail("provider_data_projection_required")

    safe_url_result = _safe_url_result(provider_data)
    _validate_projection_coherence(attempt_state, provider_data, safe_url_result)

    ordinary = OrdinaryAttemptRecordFoundation(
        workload_branch=attempt_state.workload_branch,
        normalized_presemantic_state=attempt_state.normalized_presemantic_state,
        highest_completed_stage=attempt_state.highest_completed_stage,
        normalization_disposition=attempt_state.normalization_disposition,
        terminal_outcome=attempt_state.terminal_outcome,
        attempt_outcome=attempt_state.attempt_outcome,
        validator_states=tuple(
            SafeValidatorState(
                validator_id=item.validator_id,
                applicability=item.applicability,
                state=item.state,
            )
            for item in attempt_state.validator_states
        ),
        refusal_state=attempt_state.refusal_state,
        failure_category=attempt_state.failure_category,
        raw_provider_response_hash=attempt_state.raw_provider_response_hash,
        canonical_evidence_bundle_hash_if_applicable=(
            attempt_state.accepted_artifact_hash
            if attempt_state.workload_branch == "search_retrieval"
            else None
        ),
        final_semantic_payload_hash_if_applicable=(
            attempt_state.accepted_artifact_hash
            if attempt_state.workload_branch != "search_retrieval"
            else None
        ),
        restricted_trace_reference_if_applicable=(
            provider_data.ordinary.restricted_trace_reference
        ),
        url_security_classification_if_applicable=(
            safe_url_result["classification"] if safe_url_result else None
        ),
        url_security_reason_codes_if_applicable=(
            tuple(safe_url_result["reason_codes"]) if safe_url_result else None
        ),
        url_security_policy_id_if_applicable=(
            safe_url_result["policy_id"] if safe_url_result else None
        ),
        url_security_policy_version_if_applicable=(
            safe_url_result["policy_version"] if safe_url_result else None
        ),
        url_security_policy_hash_if_applicable=(
            safe_url_result["policy_hash"] if safe_url_result else None
        ),
        public_safe_canonical_urls=(
            provider_data.ordinary.public_safe_canonical_urls
        ),
        safe_transport_metadata=provider_data.ordinary.safe_transport_metadata,
        _token=_FOUNDATION_TOKEN,
    )
    return PrivacySafeAttemptRecordFoundation(
        ordinary=ordinary,
        restricted_provider_data=provider_data.restricted,
        full_result_record_blockers=FULL_RESULT_RECORD_BLOCKERS,
        complete_result_record_eligible=False,
        execution_authority=False,
        _token=_FOUNDATION_TOKEN,
    )


@dataclass(frozen=True, slots=True)
class ResultRecordContract:
    policy_id: str
    policy_version: str
    policy_hash: str
    normalization_audit_fields: tuple[str, ...]
    pilot_envelope_fields: tuple[str, ...]
    scored_only_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PilotAttemptKey:
    evaluation_id: str
    fixture_id: str
    candidate_id: str
    provider: str
    model: str
    component_topology: str
    workload: str
    run_number: int
    attempt_number: int

    def __post_init__(self) -> None:
        for name in _ATTEMPT_KEY_FIELDS[:-2]:
            value = getattr(self, name)
            if type(value) is not str or (
                _SAFE_IDENTIFIER.fullmatch(value) is None
                and not (
                    name == "provider" and value in _FROZEN_PROVIDER_DISPLAY_NAMES
                )
            ):
                raise _fail(f"attempt_key:{name}")
        if type(self.run_number) is not int or self.run_number < 1:
            raise _fail("attempt_key:run_number")
        if (
            type(self.attempt_number) is not int
            or not 1 <= self.attempt_number <= MAXIMUM_PHYSICAL_ATTEMPTS
        ):
            raise _fail("attempt_key:attempt_number")

    def as_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in _ATTEMPT_KEY_FIELDS}

    @property
    def identity(self) -> tuple[Any, ...]:
        return tuple(getattr(self, name) for name in _ATTEMPT_KEY_FIELDS)


@dataclass(frozen=True, slots=True)
class PilotAttemptRecord:
    key: PilotAttemptKey
    ordinary_json: bytes = field(repr=False)
    restricted_provider_data: RestrictedProviderDataProjection = field(repr=False)
    restricted_search_tool_data: RestrictedSearchToolProjection | None = field(
        default=None,
        repr=False,
    )
    _token: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _PILOT_RECORD_TOKEN:
            raise _fail("pilot_attempt_record_factory_required")

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self.ordinary_json.decode("utf-8"))

    @property
    def record_hash(self) -> str:
        return self.as_dict()["record_hash"]


@dataclass(frozen=True, slots=True)
class PilotRunBundle:
    """Immutable local bundle; it grants no persistence or execution authority."""

    attempts: tuple[PilotAttemptRecord, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.attempts, tuple):
            raise _fail("run_bundle_not_immutable")
        identities = tuple(record.key.identity for record in self.attempts)
        if len(identities) != len(set(identities)):
            raise _fail("duplicate_attempt_key")
        if len({record.key.evaluation_id for record in self.attempts}) > 1:
            raise _fail("mixed_evaluation_run_bundle")

    def record_preflight_failure(self) -> PilotRunBundle:
        """Preflight failures are not physical provider attempts."""
        return self

    def append_attempt(self, record: PilotAttemptRecord) -> PilotRunBundle:
        if not isinstance(record, PilotAttemptRecord):
            raise _fail("physical_attempt_record_required")
        if record.key.identity in {item.key.identity for item in self.attempts}:
            raise _fail("duplicate_attempt_key")
        series_identity = record.key.identity[:-1]
        series_attempts = tuple(
            item for item in self.attempts if item.key.identity[:-1] == series_identity
        )
        if record.key.attempt_number != len(series_attempts) + 1:
            raise _fail("retry_policy:missing_previous_attempt")
        previous_outcome = (
            series_attempts[-1].as_dict()["normalization_audit"]["attempt_outcome"]
            if series_attempts
            else None
        )
        retry_reason = record.as_dict()["pilot_envelope"]["retry_reason"]
        try:
            validate_retry_linkage(
                previous_attempt_outcome=previous_outcome,
                attempt_number=record.key.attempt_number,
                retry_reason=retry_reason,
            )
        except RetryPolicyError as exc:
            raise _fail(f"retry_policy:{exc}") from exc
        return PilotRunBundle(self.attempts + (record,))


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
        raise _fail("record_canonicalization") from exc


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_hash(label: str, value: Any, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if type(value) is not str or _LOWER_SHA256.fullmatch(value) is None:
        raise _fail(label)


def _require_identifier(label: str, value: Any, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if type(value) is not str or _SAFE_IDENTIFIER.fullmatch(value) is None:
        raise _fail(label)


def _without_semantic_hash(artifact: dict[str, Any]) -> dict[str, Any]:
    detached = json.loads(json.dumps(artifact))
    try:
        del detached["specification_identity"]["semantic_hash"]
    except (KeyError, TypeError) as exc:
        raise _fail("result_record_contract_identity") from exc
    return detached


def verify_result_record_contract(
    path: str | Path = _DEFAULT_CONTRACT,
) -> ResultRecordContract:
    """Verify the pilot record contract against both frozen field inventories."""
    try:
        artifact = load_strict_contract_json(path)
        parser = load_strict_normalization_spec(_NORMALIZATION_CONTRACT)
        rubric = load_strict_contract_json(_RUBRIC_CONTRACT)
        parser_identity = verify_normalization_parser_artifact(parser)
        verify_safe_search_tool_record_contract(_SAFE_SEARCH_TOOL_CONTRACT)
    except (ContractIdentityError, SearchToolRecordError) as exc:
        raise _fail("result_record_contract_source") from exc

    if set(artifact) != _RESULT_RECORD_ARTIFACT_KEYS or (
        artifact.get("artifact_id") != "pilot_result_record_v1"
        or artifact.get("artifact_version") != "v1"
        or artifact.get("status") != "frozen"
        or artifact.get("provider_neutral") is not True
    ):
        raise _fail("result_record_contract_header")
    normalization_fields = tuple(artifact.get("normalization_audit_fields", ()))
    expected_normalization = tuple(parser["result_record_integration"]["required_fields"])
    if normalization_fields != expected_normalization or len(normalization_fields) != 66:
        raise _fail("normalization_audit_inventory")
    pilot_fields = tuple(artifact.get("pilot_envelope_fields", ()))
    scored_fields = tuple(artifact.get("scored_only_fields", ()))
    rubric_fields = tuple(rubric["experimental_protocol"]["result_record_fields"])
    if (
        len(pilot_fields) != 55
        or len(scored_fields) != 21
        or len(set(pilot_fields)) != len(pilot_fields)
        or len(set(scored_fields)) != len(scored_fields)
        or set(pilot_fields).intersection(scored_fields)
        or set(pilot_fields).union(scored_fields) != set(rubric_fields)
    ):
        raise _fail("rubric_field_partition")
    if tuple(artifact["attempt_key"]["fields_in_order"]) != _ATTEMPT_KEY_FIELDS:
        raise _fail("attempt_key_inventory")
    if artifact.get("source_contracts", {}).get("safe_search_tool_record") != (
        "safe-search-tool-record.v1.json"
    ):
        raise _fail("safe_search_tool_contract_source")
    if artifact["execution_boundary"] != {
        "execution_state": "blocked_pre_execution",
        "provider_calls_allowed": False,
        "pilot_calls_allowed": False,
        "scored_calls_allowed": False,
        "provider_calls_completed": 0,
        "this_artifact_independently_authorizes_execution": False,
    }:
        raise _fail("result_record_execution_boundary")
    identity = artifact.get("specification_identity", {})
    if identity.get("semantic_hash_excluded_json_pointers") != [
        "/specification_identity/semantic_hash"
    ]:
        raise _fail("result_record_contract_identity")
    stored_hash = identity.get("semantic_hash")
    _require_hash("result_record_contract_hash", stored_hash)
    if _canonical_hash(_without_semantic_hash(artifact)) != stored_hash:
        raise _fail("result_record_contract_hash")
    if parser_identity.semantic_hash != parser["specification_identity"][
        "derived_hash_cache"
    ]["normalization_spec_semantic_hash"]:
        raise _fail("normalization_spec_identity")
    return ResultRecordContract(
        policy_id=artifact["artifact_id"],
        policy_version=artifact["artifact_version"],
        policy_hash=stored_hash,
        normalization_audit_fields=normalization_fields,
        pilot_envelope_fields=pilot_fields,
        scored_only_fields=scored_fields,
    )


def _validate_normalization_identities(audit: dict[str, Any]) -> None:
    try:
        parser = load_strict_normalization_spec(_NORMALIZATION_CONTRACT)
        identity = verify_normalization_parser_artifact(parser)
    except ContractIdentityError as exc:
        raise _fail("normalization_spec_identity") from exc
    child_hashes = dict(identity.child_hashes)
    expected = {
        "normalization_spec_id": parser["specification_identity"][
            "normalization_spec_id"
        ],
        "normalization_spec_version": parser["specification_identity"][
            "normalization_spec_version"
        ],
        "normalization_spec_semantic_hash": identity.semantic_hash,
        "canonical_parser_policy_id": "canonical_parser_policy_json_v1",
        "canonical_parser_policy_version": "v1",
        "canonical_parser_policy_hash": child_hashes[
            "canonical_parser_policy_json_v1"
        ],
        "normalization_hashing_policy_id": "normalization_hashing_policy_v1",
        "normalization_hashing_policy_version": "v1",
        "normalization_hashing_policy_hash": child_hashes[
            "normalization_hashing_policy_v1"
        ],
        "strict_json_policy_id": "strict_json_policy_v1",
        "strict_json_policy_version": "v1",
        "strict_json_policy_hash": child_hashes["strict_json_policy_v1"],
        "semantic_numeric_domain_policy_id": "semantic_numeric_domain_policy_v1",
        "semantic_numeric_domain_policy_version": "v1",
        "semantic_numeric_domain_policy_hash": child_hashes[
            "semantic_numeric_domain_policy_v1"
        ],
        "stage_event_ledger_policy_id": "attempt_stage_event_ledger_v1",
        "stage_event_ledger_policy_version": "v1",
        "stage_event_ledger_policy_hash": child_hashes[
            "attempt_stage_event_ledger_v1"
        ],
        "compatibility_matrix_id": "attempt_state_compatibility_matrix_v1",
        "compatibility_matrix_version": "v1",
        "compatibility_matrix_hash": child_hashes[
            "attempt_state_compatibility_matrix_v1"
        ],
        "validator_applicability_policy_id": "workload_validator_applicability_v1",
        "validator_applicability_policy_version": "v1",
        "validator_applicability_policy_hash": child_hashes[
            "workload_validator_applicability_v1"
        ],
        "first_terminal_condition_reducer_id": "first_terminal_condition_reducer_v1",
        "first_terminal_condition_reducer_version": "v1",
        "first_terminal_condition_reducer_hash": child_hashes[
            "first_terminal_condition_reducer_v1"
        ],
    }
    for field_name, expected_value in expected.items():
        if audit[field_name] != expected_value:
            raise _fail(f"normalization_identity:{field_name}")


def _validate_attempt_audit(
    audit: dict[str, Any],
    state: AttemptState,
    contract: ResultRecordContract,
) -> None:
    if (
        type(audit) is not dict
        or len(audit) != len(contract.normalization_audit_fields)
        or set(audit) != set(contract.normalization_audit_fields)
    ):
        raise _fail("normalization_audit_fields")
    _validate_normalization_identities(audit)
    _require_hash("adapter_hash", audit["adapter_hash"])
    ledger_link = audit["stage_event_ledger_hash_or_safe_reference"]
    if not (
        type(ledger_link) is str
        and (
            _LOWER_SHA256.fullmatch(ledger_link) is not None
            or _SAFE_IDENTIFIER.fullmatch(ledger_link) is not None
        )
    ):
        raise _fail("stage_event_ledger_hash_or_safe_reference")
    expected_spec_file_hash = hashlib.sha256(_NORMALIZATION_CONTRACT.read_bytes()).hexdigest()
    if audit["normalization_spec_file_sha256_or_immutable_run_binding_reference"] != (
        expected_spec_file_hash
    ):
        raise _fail("normalization_spec_file_binding")
    expected_implementation_hash = hashlib.sha256(
        _NORMALIZATION_IMPLEMENTATION.read_bytes()
    ).hexdigest()
    if audit["parser_implementation_hash"] != expected_implementation_hash:
        raise _fail("parser_implementation_hash")
    for name in (
        "wire_response_hash_if_available",
        "raw_provider_response_hash",
        "stream_trace_hash_if_applicable",
        "native_structured_object_hash_if_applicable",
        "transport_extracted_payload_hash",
        "strict_parsed_semantic_payload_hash",
        "canonical_validation_candidate_hash",
        "provider_trace_hash_if_applicable",
        "retrieval_trace_hash_if_applicable",
        "canonical_evidence_bundle_hash_if_applicable",
        "final_semantic_payload_hash_if_applicable",
    ):
        _require_hash(name, audit[name], nullable=True)
    for name in (
        "parser_implementation_id",
        "parser_implementation_version",
        "adapter_id",
        "adapter_version",
        "content_decoding_responsibility",
        "numeric_policy_execution_conformance_status",
    ):
        _require_identifier(name, audit[name])
    if audit["response_transport_mode"] not in _TRANSPORT_MODES:
        raise _fail("response_transport_mode")
    if type(audit["canonical_raw_byte_availability"]) is not bool:
        raise _fail("canonical_raw_byte_availability")
    if (
        audit["canonical_raw_byte_availability"]
        and audit["raw_response_unavailable_reason_if_applicable"] is not None
    ):
        raise _fail("raw_response_availability")
    if not audit["canonical_raw_byte_availability"]:
        _require_identifier(
            "raw_response_unavailable_reason_if_applicable",
            audit["raw_response_unavailable_reason_if_applicable"],
        )
    stream_identity = (
        audit["stream_framing_policy_id_if_applicable"],
        audit["stream_framing_policy_hash_if_applicable"],
    )
    if audit["response_transport_mode"] == "streaming":
        _require_identifier("stream_framing_policy_id_if_applicable", stream_identity[0])
        _require_hash("stream_framing_policy_hash_if_applicable", stream_identity[1])
    elif any(value is not None for value in stream_identity):
        raise _fail("stream_framing_policy_not_applicable")
    native_evidence = audit[
        "native_object_lossless_equivalence_evidence_if_applicable"
    ]
    if audit["response_transport_mode"] == "sdk_native_structured":
        _require_hash("native_object_lossless_equivalence_evidence", native_evidence)
    elif native_evidence is not None:
        raise _fail("native_equivalence_not_applicable")
    if type(audit["normalization_actions"]) is not list:
        raise _fail("normalization_actions")
    validated_actions: list[NormalizationActionRecord] = []
    for ordinal, action in enumerate(audit["normalization_actions"], start=1):
        if type(action) is not dict or set(action) != _NORMALIZATION_ACTION_FIELDS:
            raise _fail("normalization_action_fields")
        if action["ordinal"] != ordinal or action["action"] not in NORMALIZATION_ACTIONS:
            raise _fail("normalization_action_identity")
        for name in ("policy_id", "policy_version"):
            _require_identifier(f"normalization_action:{name}", action[name])
        _require_hash("normalization_action:policy_hash", action["policy_hash"])
        _require_hash("normalization_action:input_hash", action["input_hash"])
        _require_hash(
            "normalization_action:output_hash",
            action["output_hash"],
            nullable=action["action_result"] != "completed",
        )
        adapter_values = (
            action["adapter_id_if_applicable"],
            action["adapter_version_if_applicable"],
            action["adapter_hash_if_applicable"],
        )
        if any(value is not None for value in adapter_values):
            if not all(value is not None for value in adapter_values):
                raise _fail("normalization_action:adapter_identity")
            _require_identifier("normalization_action:adapter_id", adapter_values[0])
            _require_identifier("normalization_action:adapter_version", adapter_values[1])
            _require_hash("normalization_action:adapter_hash", adapter_values[2])
        if type(action["trace_references"]) is not list:
            raise _fail("normalization_action:trace_references")
        for reference in action["trace_references"]:
            _require_identifier("normalization_action:trace_reference", reference)
        if type(action["deterministic_parameters"]) is not list:
            raise _fail("normalization_action:deterministic_parameters")
        for parameter in action["deterministic_parameters"]:
            if (
                type(parameter) is not list
                or len(parameter) != 2
            ):
                raise _fail("normalization_action:deterministic_parameter")
            _require_identifier(
                "normalization_action:parameter_name", parameter[0]
            )
            _require_identifier(
                "normalization_action:parameter_value", parameter[1]
            )
        if action["action_result"] not in {
            "completed",
            "failed",
            "aborted_by_earlier_terminal",
        }:
            raise _fail("normalization_action:result")
        try:
            validated_actions.append(
                NormalizationActionRecord(
                    ordinal=action["ordinal"],
                    action=action["action"],
                    policy_id=action["policy_id"],
                    policy_version=action["policy_version"],
                    policy_hash=action["policy_hash"],
                    adapter_id_if_applicable=action[
                        "adapter_id_if_applicable"
                    ],
                    adapter_version_if_applicable=action[
                        "adapter_version_if_applicable"
                    ],
                    adapter_hash_if_applicable=action[
                        "adapter_hash_if_applicable"
                    ],
                    input_hash=action["input_hash"],
                    output_hash=action["output_hash"],
                    trace_references=tuple(action["trace_references"]),
                    deterministic_parameters=tuple(
                        (item[0], item[1])
                        for item in action["deterministic_parameters"]
                    ),
                    action_result=action["action_result"],
                )
            )
        except (TypeError, ValueError) as exc:
            raise _fail("normalization_action_invalid") from exc
    try:
        action_summary = summarize_normalization_actions(tuple(validated_actions))
    except (TypeError, ValueError) as exc:
        raise _fail("normalization_action_invalid") from exc
    if action_summary != state.normalization_action_summary:
        raise _fail("normalization_action_summary_mismatch")
    numeric_reason = audit["numeric_domain_reason_if_applicable"]
    if numeric_reason not in {None, "negative_zero", "binary64_overflow_nonfinite"}:
        raise _fail("numeric_domain_reason_if_applicable")
    bindings = audit["applied_policy_bindings"]
    if type(bindings) is not list or not bindings:
        raise _fail("applied_policy_bindings")
    seen: set[tuple[str, str]] = set()
    binding_hashes: dict[tuple[str, str], str] = {}
    for binding in bindings:
        if type(binding) is not dict or set(binding) != {
            "policy_id",
            "policy_version",
            "policy_hash",
        }:
            raise _fail("applied_policy_bindings")
        _require_identifier("applied_policy_id", binding["policy_id"])
        _require_identifier("applied_policy_version", binding["policy_version"])
        _require_hash("applied_policy_hash", binding["policy_hash"])
        key = (binding["policy_id"], binding["policy_version"])
        if key in seen:
            raise _fail("applied_policy_binding_duplicate")
        seen.add(key)
        binding_hashes[key] = binding["policy_hash"]
    required_bindings = {
        (
            audit["canonical_parser_policy_id"],
            audit["canonical_parser_policy_version"],
        ): audit["canonical_parser_policy_hash"],
        (
            audit["normalization_hashing_policy_id"],
            audit["normalization_hashing_policy_version"],
        ): audit["normalization_hashing_policy_hash"],
        (
            audit["strict_json_policy_id"],
            audit["strict_json_policy_version"],
        ): audit["strict_json_policy_hash"],
        (
            audit["semantic_numeric_domain_policy_id"],
            audit["semantic_numeric_domain_policy_version"],
        ): audit["semantic_numeric_domain_policy_hash"],
        (
            audit["stage_event_ledger_policy_id"],
            audit["stage_event_ledger_policy_version"],
        ): audit["stage_event_ledger_policy_hash"],
        (
            audit["compatibility_matrix_id"],
            audit["compatibility_matrix_version"],
        ): audit["compatibility_matrix_hash"],
        (
            audit["validator_applicability_policy_id"],
            audit["validator_applicability_policy_version"],
        ): audit["validator_applicability_policy_hash"],
        (
            audit["first_terminal_condition_reducer_id"],
            audit["first_terminal_condition_reducer_version"],
        ): audit["first_terminal_condition_reducer_hash"],
        (DATA_HANDLING_POLICY_ID, DATA_HANDLING_POLICY_VERSION): (
            DATA_HANDLING_POLICY_HASH
        ),
    }
    try:
        prompt_identity = verify_prompt_template_artifact(
            load_strict_contract_json(_PROMPT_CONTRACT)
        )
        schema_identity = verify_output_schema_artifact(
            load_strict_contract_json(_SCHEMA_CONTRACT)
        )
    except ContractIdentityError as exc:
        raise _fail("prompt_schema_identity") from exc
    prompt_schema_hashes = {
        **dict(prompt_identity.child_hashes),
        **dict(schema_identity.child_hashes),
    }
    for binding_id in _PROMPT_SCHEMA_IDS_BY_BRANCH[state.workload_branch]:
        required_bindings[(binding_id, "v1")] = prompt_schema_hashes[binding_id]
    if any(binding_hashes.get(key) != value for key, value in required_bindings.items()):
        raise _fail("applied_policy_binding_incomplete")
    state_fields = {
        "normalized_presemantic_state": state.normalized_presemantic_state,
        "highest_completed_stage": state.highest_completed_stage,
        "normalization_disposition": state.normalization_disposition,
        "terminal_outcome": state.terminal_outcome,
        "attempt_outcome": state.attempt_outcome,
        "refusal_state": state.refusal_state,
        "failure_category": state.failure_category,
        "raw_provider_response_hash": state.raw_provider_response_hash,
        "final_semantic_payload_hash_if_applicable": (
            state.accepted_artifact_hash
            if state.workload_branch != "search_retrieval"
            else None
        ),
    }
    if state.workload_branch != "search_synthesis_final":
        state_fields["canonical_evidence_bundle_hash_if_applicable"] = (
            state.accepted_artifact_hash
            if state.workload_branch == "search_retrieval"
            else None
        )
    for field_name, expected in state_fields.items():
        if audit[field_name] != expected:
            raise _fail(f"attempt_state_alias:{field_name}")
    expected_validators = [
        {
            "validator_id": item.validator_id,
            "applicability": item.applicability,
            "state": item.state,
        }
        for item in state.validator_states
    ]
    if audit["validator_states"] != expected_validators:
        raise _fail("attempt_state_alias:validator_states")
    if audit["attempt_state_coherence"] != "passed":
        raise _fail("attempt_state_coherence")
    stage_index = HIGHEST_COMPLETED_STAGES.index(state.highest_completed_stage)
    required_by_stage = (
        (2, "transport_extracted_payload_hash"),
        (3, "strict_parsed_semantic_payload_hash"),
        (4, "canonical_validation_candidate_hash"),
    )
    for minimum_stage, field_name in required_by_stage:
        if stage_index >= minimum_stage and audit[field_name] is None:
            raise _fail(f"stage_hash_required:{field_name}")
        if stage_index < minimum_stage and audit[field_name] is not None:
            raise _fail(f"stage_hash_not_available:{field_name}")
    if audit["response_transport_mode"] == "streaming":
        if audit["stream_trace_hash_if_applicable"] is None:
            raise _fail("stream_trace_hash_required")
    elif audit["stream_trace_hash_if_applicable"] is not None:
        raise _fail("stream_trace_hash_not_applicable")
    if audit["response_transport_mode"] == "sdk_native_structured":
        if (
            audit["native_structured_object_hash_if_applicable"] is None
            or audit["native_object_lossless_equivalence_evidence_if_applicable"]
            is None
        ):
            raise _fail("native_object_evidence_required")
    elif audit["native_structured_object_hash_if_applicable"] is not None:
        raise _fail("native_object_hash_not_applicable")
    if state.terminal_outcome == "accepted":
        if state.workload_branch == "search_retrieval":
            for field_name in (
                "provider_trace_hash_if_applicable",
                "retrieval_trace_hash_if_applicable",
                "canonical_evidence_bundle_hash_if_applicable",
            ):
                if audit[field_name] is None:
                    raise _fail(f"retrieval_hash_required:{field_name}")
            if audit["final_semantic_payload_hash_if_applicable"] is not None:
                raise _fail("retrieval_final_semantic_hash_not_applicable")
        elif audit["final_semantic_payload_hash_if_applicable"] is None:
            raise _fail("final_semantic_payload_hash_required")


def _validate_pilot_envelope(
    envelope: dict[str, Any],
    key: PilotAttemptKey,
    audit: dict[str, Any],
    state: AttemptState,
    foundation: PrivacySafeAttemptRecordFoundation,
    contract: ResultRecordContract,
    search_tool_data: SearchToolProjections | None,
    ps1_evidence: Ps1AssemblyResult | None,
    request_configuration_selection: PilotRequestConfigurationSelection | None,
) -> None:
    if (
        type(envelope) is not dict
        or len(envelope) != len(contract.pilot_envelope_fields)
        or set(envelope) != set(contract.pilot_envelope_fields)
    ):
        raise _fail("pilot_envelope_fields")
    aliases = {
        "evaluation_id": key.evaluation_id,
        "fixture_id": key.fixture_id,
        "provider": key.provider,
        "model": key.model,
        "component_topology": key.component_topology,
        "workload": key.workload,
        "run_number": key.run_number,
        "attempt_number": key.attempt_number,
        "refusal_state": state.refusal_state,
        "raw_response_hash": audit["raw_provider_response_hash"],
        "normalized_output_hash": audit["final_semantic_payload_hash_if_applicable"],
        "normalization_parser_version": audit["parser_implementation_version"],
        "normalization_performed": audit["normalization_disposition"] == "performed",
        "normalization_actions": audit["normalization_actions"],
        "safe_failure_code": state.failure_category,
    }
    for field_name, expected in aliases.items():
        if envelope[field_name] != expected:
            raise _fail(f"pilot_alias:{field_name}")
    if envelope["experiment_phase"] != "pilot":
        raise _fail("pilot_experiment_phase")
    if key.workload != _WORKLOAD_BY_BRANCH[state.workload_branch]:
        raise _fail("pilot_workload_branch")
    for name in (
        "experiment_version",
        "harness_version",
        "fixture_manifest_version",
        "fixture_version",
        "rubric_version",
        "scoring_rule_version",
        "api_endpoint",
        "api_version",
        "prompt_template_version",
        "output_schema_version",
    ):
        _require_identifier(name, envelope[name])
    _require_identifier(
        "model_version_or_snapshot",
        envelope["model_version_or_snapshot"],
        nullable=True,
    )
    if (
        type(envelope["repository_harness_commit_sha"]) is not str
        or _GIT_SHA.fullmatch(envelope["repository_harness_commit_sha"]) is None
    ):
        raise _fail("repository_harness_commit_sha")
    _require_hash("prompt_hash", envelope["prompt_hash"])
    if envelope["provider_request_id"] is not None:
        raise _fail("provider_request_id_verifier_pending")
    for timestamp in ("started_at", "completed_at"):
        value = envelope[timestamp]
        if type(value) is not str or _UTC_MILLISECOND.fullmatch(value) is None:
            raise _fail(timestamp)
    try:
        started = datetime.fromisoformat(
            envelope["started_at"].replace("Z", "+00:00")
        )
        completed = datetime.fromisoformat(
            envelope["completed_at"].replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise _fail("attempt_timestamp") from exc
    if completed < started:
        raise _fail("attempt_timing_order")
    safe_metadata = foundation.ordinary.safe_transport_metadata.as_dict()
    for name in (
        "provider",
        "model",
        "model_version_or_snapshot",
        "started_at",
        "completed_at",
        "http_or_result_status",
        "finish_or_stop_reason",
        "latency_measurements",
        "input_token_usage",
        "output_token_usage",
        "reasoning_usage_if_exposed",
        "image_usage_if_exposed",
        "attempt_number",
        "retry_count",
    ):
        if envelope[name] != safe_metadata.get(name):
            raise _fail(f"transport_alias:{name}")
    expected_schema_pass = next(
        item.state == "passed"
        for item in state.validator_states
        if item.validator_id == "canonical_schema_validation"
    )
    if envelope["schema_pass"] is not expected_schema_pass:
        raise _fail("schema_pass")
    if type(envelope["input_hashes"]) is not dict or not envelope["input_hashes"]:
        raise _fail("input_hashes")
    for name, value in envelope["input_hashes"].items():
        _require_identifier("input_hash_name", name)
        _require_hash("input_hash", value)
    if request_configuration_selection is None:
        if envelope["request_configuration"] is not None:
            raise _fail("request_configuration_selection_required")
    else:
        configuration = request_configuration_selection.configuration
        expected_stage = {
            "text_final": "text_analysis",
            "search_synthesis_final": "search_synthesis",
            "visual_final": "visual_inspection",
        }.get(state.workload_branch)
        if (
            expected_stage is None
            or configuration.workload_stage != expected_stage
            or configuration.candidate_id != key.candidate_id
            or configuration.provider != key.provider
            or configuration.model != key.model
            or configuration.adapter_id != audit["adapter_id"]
            or configuration.adapter_version != audit["adapter_version"]
            or configuration.adapter_hash != audit["adapter_hash"]
        ):
            raise _fail("request_configuration_binding")
        try:
            validate_request_configuration_record(
                request_configuration_selection,
                envelope["request_configuration"],
            )
        except PilotRequestConfigurationError as exc:
            raise _fail("request_configuration_record") from exc
    if key.attempt_number == 1:
        if envelope["retry_count"] != 0 or envelope["retry_reason"] is not None:
            raise _fail("first_attempt_retry_linkage")
    else:
        if envelope["retry_count"] != key.attempt_number - 1:
            raise _fail("retry_count_linkage")
        if envelope["retry_reason"] not in SAFE_RETRY_REASONS:
            raise _fail("retry_reason")
    if envelope["rate_limit_and_service_metadata_if_exposed"] is not None:
        raise _fail("rate_limit_and_service_metadata_if_exposed_contract_pending")
    if envelope["estimated_cost"] is not None:
        try:
            cost = verify_estimated_cost_record(envelope["estimated_cost"])
        except PricingContractError as exc:
            raise _fail("estimated_cost_contract") from exc
        if cost.provider != key.provider or cost.model != key.model:
            raise _fail("estimated_cost_attempt_binding")
    if key.workload != "grounded_product_price_research":
        if search_tool_data is not None:
            raise _fail("search_tool_data_not_applicable")
        if ps1_evidence is not None:
            raise _fail("ps1_evidence_not_applicable")
        for field_name in (
            "search_query_list",
            "search_and_tool_calls",
            "source_urls",
            "source_retrieval_timestamps",
            "claim_to_source_mapping",
        ):
            if envelope[field_name] not in (None, []):
                raise _fail(f"{field_name}_not_applicable")
    else:
        if (
            state.terminal_outcome != "accepted"
            and search_tool_data is None
            and ps1_evidence is None
        ):
            if audit["canonical_evidence_bundle_hash_if_applicable"] is not None:
                raise _fail("ps1_evidence_hash_binding")
            for field_name in (
                "search_query_list",
                "search_and_tool_calls",
                "source_urls",
                "source_retrieval_timestamps",
                "claim_to_source_mapping",
            ):
                if envelope[field_name] not in (None, []):
                    raise _fail(f"{field_name}_without_evidence")
            if envelope["visual_asset_hashes"] not in (None, []):
                raise _fail("visual_asset_hashes_not_applicable")
            if type(envelope["notes_and_anomalies"]) is not list:
                raise _fail("notes_and_anomalies")
            for value in envelope["notes_and_anomalies"]:
                _require_identifier("notes_and_anomalies", value)
            return
        if not isinstance(search_tool_data, SearchToolProjections):
            raise _fail("safe_search_tool_data_required")
        if not isinstance(ps1_evidence, Ps1AssemblyResult):
            raise _fail("ps1_evidence_required")
        if (
            audit["canonical_evidence_bundle_hash_if_applicable"]
            != ps1_evidence.canonical_evidence_bundle_hash
        ):
            raise _fail("ps1_evidence_hash_binding")
        expected_ps1_bindings = {
            ("source_classification_policy_v1", "v1"): (
                SOURCE_CLASSIFICATION_POLICY_HASH
            ),
            ("url_security_operational_origin_rule_registry_v1", "v1"): (
                ORIGIN_RULE_REGISTRY_HASH
            ),
            ("retrieval_objective_support_policy_v1", "v1"): (
                OBJECTIVE_SUPPORT_POLICY_HASH
            ),
            (
                "deterministic_trace_backed_evidence_extractor_and_matcher_v1",
                "v1",
            ): EVIDENCE_EXTRACTOR_POLICY_HASH,
        }
        actual_bindings = {
            (item["policy_id"], item["policy_version"]): item["policy_hash"]
            for item in audit["applied_policy_bindings"]
        }
        if any(
            actual_bindings.get(identity) != policy_hash
            for identity, policy_hash in expected_ps1_bindings.items()
        ):
            raise _fail("ps1_policy_binding")
        ordinary_search = search_tool_data.ordinary.as_dict()
        canonical_sources = ps1_evidence.canonical_bundle["sources"]
        expected_sources = {
            source["source_id"]: {
                "url": source["url"],
                "retrieved_at": source["retrieved_at"],
            }
            for source in canonical_sources
        }
        observed_sources = {
            source["source_id"]: {
                "url": source["public_safe_canonical_url"],
                "retrieved_at": source["retrieved_at"],
            }
            for source in ordinary_search["sources"]
        }
        expected_evidence = {
            evidence["evidence_id"]: source["source_id"]
            for source in canonical_sources
            for evidence in source["evidence_items"]
        }
        observed_evidence = {
            evidence["evidence_id"]: evidence["source_id"]
            for evidence in ordinary_search["evidence"]
        }
        if (
            observed_sources != expected_sources
            or observed_evidence != expected_evidence
        ):
            raise _fail("ps1_safe_projection_binding")
        expected_aliases = {
            "search_and_tool_calls": ordinary_search,
            "search_query_list": [
                operation["query_id"]
                for operation in ordinary_search["operations"]
                if operation["query_id"] is not None
            ],
            "source_urls": [
                source["public_safe_canonical_url"]
                for source in ordinary_search["sources"]
            ],
            "source_retrieval_timestamps": [
                {
                    "source_id": source["source_id"],
                    "retrieved_at": source["retrieved_at"],
                }
                for source in ordinary_search["sources"]
            ],
            "claim_to_source_mapping": ordinary_search[
                "claim_evidence_source_links"
            ],
        }
        for field_name, expected in expected_aliases.items():
            if envelope[field_name] != expected:
                raise _fail(f"safe_search_tool_alias:{field_name}")
    if key.workload == "visual_inspection":
        if type(envelope["visual_asset_hashes"]) is not list:
            raise _fail("visual_asset_hashes")
        for value in envelope["visual_asset_hashes"]:
            _require_hash("visual_asset_hash", value)
    elif envelope["visual_asset_hashes"] not in (None, []):
        raise _fail("visual_asset_hashes_not_applicable")
    if type(envelope["notes_and_anomalies"]) is not list:
        raise _fail("notes_and_anomalies")
    for value in envelope["notes_and_anomalies"]:
        _require_identifier("notes_and_anomalies", value)


def build_pilot_attempt_record(
    *,
    attempt_key: PilotAttemptKey,
    attempt_state: AttemptState,
    provider_data: ProviderDataProjections,
    normalization_audit: dict[str, Any],
    pilot_envelope: dict[str, Any],
    provider_attempt_started: bool,
    search_tool_data: SearchToolProjections | None = None,
    ps1_evidence: Ps1AssemblyResult | None = None,
    request_configuration_selection: PilotRequestConfigurationSelection | None = None,
    contract_path: str | Path = _DEFAULT_CONTRACT,
) -> PilotAttemptRecord:
    """Build one immutable pilot attempt without granting execution authority."""
    if provider_attempt_started is not True:
        raise _fail("preflight_failure_is_not_provider_attempt")
    if not isinstance(attempt_key, PilotAttemptKey):
        raise _fail("attempt_key_required")
    foundation = build_privacy_safe_attempt_record(
        attempt_state=attempt_state,
        provider_data=provider_data,
    )
    contract = verify_result_record_contract(contract_path)
    _validate_attempt_audit(normalization_audit, attempt_state, contract)
    _validate_pilot_envelope(
        pilot_envelope,
        attempt_key,
        normalization_audit,
        attempt_state,
        foundation,
        contract,
        search_tool_data,
        ps1_evidence,
        request_configuration_selection,
    )
    record = {
        "record_type": "pilot_physical_attempt_v1",
        "record_contract": {
            "policy_id": contract.policy_id,
            "policy_version": contract.policy_version,
            "policy_hash": contract.policy_hash,
        },
        "attempt_key": attempt_key.as_dict(),
        "pilot_envelope": pilot_envelope,
        "normalization_audit": normalization_audit,
        "ordinary_projection": foundation.ordinary.as_dict(),
    }
    record["record_hash"] = _canonical_hash(record)
    return PilotAttemptRecord(
        key=attempt_key,
        ordinary_json=_canonical_bytes(record),
        restricted_provider_data=foundation.restricted_provider_data,
        restricted_search_tool_data=(
            search_tool_data.restricted if search_tool_data is not None else None
        ),
        _token=_PILOT_RECORD_TOKEN,
    )
