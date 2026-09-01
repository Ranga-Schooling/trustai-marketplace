"""Minimal provider-free orchestration for the frozen Capstone pilot.

The module composes existing frozen contracts.  It deliberately provides no
network transport, environment-variable reader, credential store, scheduler,
or execution authority.  Tests inject the only concrete transport and secret
resolver implemented here; both are deterministic and synthetic.
"""

from __future__ import annotations

from base64 import b64encode
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from app.services.evaluation_attempt_state import (
    HIGHEST_COMPLETED_STAGES,
    AttemptStageEventLedger,
    NormalizationActionRecord,
    StageEvent,
    derive_attempt_state,
)
from app.services.evaluation_contract_identity import (
    load_strict_contract_json,
    load_strict_normalization_spec,
    verify_normalization_parser_artifact,
    verify_output_schema_artifact,
    verify_prompt_template_artifact,
)
from app.services.evaluation_data_handling import (
    POLICY_HASH as PRIVACY_POLICY_HASH,
    POLICY_ID as PRIVACY_POLICY_ID,
    POLICY_VERSION as PRIVACY_POLICY_VERSION,
    derive_restricted_trace_reference,
    project_provider_data,
)
from app.services.evaluation_pilot_budget import (
    PilotBudgetError,
    PilotBudgetLedger,
    commit_provider_attempt_cost,
    empty_pilot_budget_ledger,
    reserve_provider_attempt,
    verify_pilot_budget_control,
)
from app.services.evaluation_pilot_preflight import (
    assess_provider_neutral_pilot_preflight,
)
from app.services.evaluation_pilot_visual_assets import (
    FrozenPilotVisualAssets,
    verify_pilot_visual_assets,
)
from app.services.evaluation_post_schema_validation import (
    validate_text_post_schema_candidate,
    validate_visual_post_schema_candidate,
)
from app.services.evaluation_provider_adapters import (
    AdaptedProviderResponse,
    ProviderAdapterResponseError,
    ProviderAdapterSet,
    adapt_provider_response,
    bind_provider_adapters,
)
from app.services.evaluation_provider_role_mappings import (
    ProviderRoleMappingSelection,
    ProviderRoleMappingSet,
    expected_provider_request_plan,
    bind_provider_role_mappings,
    select_provider_role_mapping,
    validate_provider_request_plan,
)
from app.services.evaluation_ps1 import (
    EVIDENCE_EXTRACTOR_POLICY_HASH,
    OBJECTIVE_SUPPORT_POLICY_HASH,
    ORIGIN_RULE_REGISTRY_HASH,
    SOURCE_CLASSIFICATION_POLICY_HASH,
    Ps1AssemblyResult,
    Ps1EvidenceCandidate,
    Ps1RefetchObservation,
    assemble_ps1_evidence_bundle,
    build_ps1_classifier_input,
    record_ps1_discovery_url,
)
from app.services.evaluation_region_binding import (
    POLICY_HASH as REGION_BINDING_HASH,
    verify_pilot_region_binding,
)
from app.services.evaluation_request_configurations import (
    PilotRequestConfigurationSelection,
    PilotRequestConfigurationSet,
    bind_pilot_request_configurations,
    select_pilot_request_configuration,
)
from app.services.evaluation_result_record import (
    PilotAttemptKey,
    PilotAttemptRecord,
    PilotRunBundle,
    build_pilot_attempt_record,
    verify_result_record_contract,
)
from app.services.evaluation_retry_policy import (
    AttemptDeadline,
    RetryPolicy,
    decide_retry,
    load_retry_policy,
)
from app.services.evaluation_schema_validation import (
    CanonicalOutputSchemaRegistry,
    CanonicalSchemaValidationError,
)
from app.services.evaluation_search_authority import bind_search_authority_v2
from app.services.evaluation_search_tool_record import (
    RawSearchToolOperation,
    SearchToolProjections,
    build_search_tool_projections,
)
from app.services.evaluation_transport_capture import (
    CanonicalRawResponseAccumulator,
    RawResponseCapture,
    TransportCaptureStateError,
)
from app.services.evaluation_url_discovery import (
    UrlDiscoveryError,
    bind_url_discovery_to_ps1_refetch,
    build_openai_url_discovery_request,
    extract_openai_url_discovery,
    select_url_discovery_configuration,
    verify_url_discovery_contract,
)
from app.services.evaluation_validators import (
    DeterministicValidationError,
    validate_search_cross_references,
)
from app.services.evaluation_visual_context import (
    FrozenVisualContextContract,
    bind_visual_context_contract,
    render_pilot_visual_context,
)
from app.services.normalization_parser import (
    DuplicateJsonKeyError,
    StrictJsonPayloadError,
    normalize_semantic_json,
)


PILOT_RUNNER_STATUS = "pilot_runner_ready_awaiting_live_gates"
CREDENTIAL_VARIABLE_BY_PROVIDER = MappingProxyType(
    {
        "OpenAI": "OPENAI_API_KEY",
        "Google Gemini": "GEMINI_API_KEY",
        "Groq": "GROQ_API_KEY",
    }
)
_EVALUATION_ID = "trustai_capstone_evaluation_v1"
_EXPERIMENT_VERSION = "v1"
_RESOURCE_POLICY_ID = "normalization_parser_resource_limits_v1"
_RESOURCE_POLICY_HASH = (
    "9269950928ddf05e6b691623c57e6b60797c1131ee96f893e4977d5f223b2d16"
)
_RETRY_POLICY_HASH = (
    "a4e08ef3b92232cbbf1542aa37b30c87697da60c42bcf72d71876098d0251c4b"
)
_TRANSPORT_SECRET_TOKEN = object()
_ATTEMPT_POLICY_IDENTITY = (
    "failure_taxonomy_v1",
    "v1",
    "f14c419e3176a61747eb427a94e77ab045da242fcffa20be2f4db362c6f34f06",
)
_PS1_URL = "https://www.logitech.com/en-us/shop/p/mx-master-3s.910-006557"
_FIXED_STARTED = "2026-08-31T20:00:00.000Z"
_FIXED_COMPLETED = "2026-08-31T20:00:01.000Z"


class PilotRunnerError(ValueError):
    """A safe application-owned runner boundary failed closed."""

    provider_attempt_created = False
    provider_call_incremented = False

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> PilotRunnerError:
    return PilotRunnerError(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise _fail("canonicalization") from exc


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _json_copy(value: Any) -> Any:
    return json.loads(_canonical(value).decode("utf-8"))


def _provider_segment_text(value: Any) -> str:
    """Render one already-authorized provider-visible segment deterministically."""
    if isinstance(value, str):
        return value
    return _canonical(value).decode("utf-8")


@dataclass(frozen=True, slots=True)
class CredentialReference:
    provider: str
    environment_variable_name: str
    readiness_state: str = "externally_confirmed_for_synthetic_test"

    def __post_init__(self) -> None:
        expected = CREDENTIAL_VARIABLE_BY_PROVIDER.get(self.provider)
        if expected is None or self.environment_variable_name != expected:
            raise _fail("credential_reference")
        if self.readiness_state not in {
            "pending_external_presence_check",
            "externally_confirmed_for_synthetic_test",
            "externally_confirmed_for_live_pilot",
        }:
            raise _fail("credential_reference")


class _ResolvedCredential:
    __slots__ = ("provider", "environment_variable_name", "_secret")

    def __init__(
        self,
        reference: CredentialReference,
        secret: str,
        *,
        _token: object,
    ) -> None:
        if _token is not _TRANSPORT_SECRET_TOKEN or type(secret) is not str or not secret:
            raise _fail("credential_resolution")
        self.provider = reference.provider
        self.environment_variable_name = reference.environment_variable_name
        self._secret = secret

    def _transport_value(self, token: object) -> str:
        if token is not _TRANSPORT_SECRET_TOKEN:
            raise _fail("credential_boundary")
        return self._secret

    def __repr__(self) -> str:
        return (
            "ResolvedCredential("
            f"provider={self.provider!r}, "
            f"environment_variable_name={self.environment_variable_name!r}, "
            "value=<redacted>)"
        )


class CredentialResolver(Protocol):
    def resolve(self, reference: CredentialReference) -> _ResolvedCredential: ...


class SyntheticCredentialResolver:
    """Test-only resolver; it never reads process environment or files."""

    __slots__ = ("_synthetic_values", "_requested")

    def __init__(self, synthetic_values_by_name: Mapping[str, str]) -> None:
        if type(synthetic_values_by_name) is not dict:
            raise _fail("synthetic_credential_inventory")
        if set(synthetic_values_by_name) != set(CREDENTIAL_VARIABLE_BY_PROVIDER.values()):
            raise _fail("synthetic_credential_inventory")
        if any(type(value) is not str or not value for value in synthetic_values_by_name.values()):
            raise _fail("synthetic_credential_inventory")
        self._synthetic_values = dict(synthetic_values_by_name)
        self._requested: list[str] = []

    def resolve(self, reference: CredentialReference) -> _ResolvedCredential:
        if not isinstance(reference, CredentialReference):
            raise _fail("credential_reference")
        value = self._synthetic_values.get(reference.environment_variable_name)
        if value is None:
            raise _fail("credential_unavailable")
        self._requested.append(reference.environment_variable_name)
        return _ResolvedCredential(
            reference,
            value,
            _token=_TRANSPORT_SECRET_TOKEN,
        )

    @property
    def resolution_count(self) -> int:
        return len(self._requested)

    @property
    def requested_environment_variable_names(self) -> tuple[str, ...]:
        return tuple(self._requested)

    def __repr__(self) -> str:
        return (
            "SyntheticCredentialResolver("
            f"requested_environment_variable_names={tuple(self._requested)!r}, "
            "values=<redacted>)"
        )


@dataclass(frozen=True, slots=True)
class LiveGateBinding:
    evaluation_id: str
    experiment_version: str
    common_preflight_status: str
    same_day_certification_status: str
    credential_authorization_status: str
    explicit_pilot_authorization_status: str
    request_configuration_set_hash: str
    budget_control_hash: str
    region_binding_hash: str
    valid_on_date: str
    credential_references: tuple[CredentialReference, ...]
    binding_mode: str

    @classmethod
    def synthetic_for_tests(
        cls,
        *,
        evaluation_id: str,
        experiment_version: str,
        request_configuration_set_hash: str,
        budget_control_hash: str,
        region_binding_hash: str,
        valid_on_date: str,
        credential_references: tuple[CredentialReference, ...],
    ) -> LiveGateBinding:
        return cls(
            evaluation_id=evaluation_id,
            experiment_version=experiment_version,
            common_preflight_status="ready",
            same_day_certification_status="synthetic_certified_for_tests",
            credential_authorization_status="synthetic_authorized_for_tests",
            explicit_pilot_authorization_status="synthetic_authorized_for_tests",
            request_configuration_set_hash=request_configuration_set_hash,
            budget_control_hash=budget_control_hash,
            region_binding_hash=region_binding_hash,
            valid_on_date=valid_on_date,
            credential_references=credential_references,
            binding_mode="synthetic_provider_free",
        )


@dataclass(frozen=True, slots=True)
class PlannedProviderCall:
    call_id: str
    logical_run_id: str
    evaluation_id: str
    experiment_version: str
    fixture_id: str
    fixture_version: str
    candidate_id: str
    provider: str
    model: str
    api_family: str
    workload_stage: str
    topology_id: str
    request_configuration_id: str | None
    request_configuration_hash: str | None
    prompt_ids: tuple[str, ...]
    prompt_hashes: tuple[str, ...]
    schema_id: str | None
    schema_hash: str | None
    role_mapping_id: str
    role_mapping_hash: str
    adapter_id: str
    adapter_hash: str
    retry_policy_id: str
    retry_policy_hash: str
    resource_policy_id: str
    resource_policy_hash: str
    privacy_policy_id: str
    privacy_policy_hash: str
    budget_policy_id: str
    budget_policy_hash: str
    region_binding_id: str
    region_binding_hash: str
    result_record_policy_id: str
    result_record_policy_hash: str
    run_number: int
    timeout_seconds: int
    maximum_physical_attempts: int

    def safe_projection(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "experiment_version": self.experiment_version,
            "fixture_id": self.fixture_id,
            "candidate_id": self.candidate_id,
            "provider": self.provider,
            "model": self.model,
            "api_family": self.api_family,
            "workload_stage": self.workload_stage,
            "topology_id": self.topology_id,
            "request_configuration_id": self.request_configuration_id,
            "request_configuration_hash": self.request_configuration_hash,
            "prompt_ids": list(self.prompt_ids),
            "prompt_hashes": list(self.prompt_hashes),
            "schema_id": self.schema_id,
            "schema_hash": self.schema_hash,
            "role_mapping_id": self.role_mapping_id,
            "role_mapping_hash": self.role_mapping_hash,
            "adapter_id": self.adapter_id,
            "adapter_hash": self.adapter_hash,
            "retry_policy_id": self.retry_policy_id,
            "retry_policy_hash": self.retry_policy_hash,
            "resource_policy_id": self.resource_policy_id,
            "resource_policy_hash": self.resource_policy_hash,
            "privacy_policy_id": self.privacy_policy_id,
            "privacy_policy_hash": self.privacy_policy_hash,
            "budget_policy_id": self.budget_policy_id,
            "budget_policy_hash": self.budget_policy_hash,
            "region_binding_id": self.region_binding_id,
            "region_binding_hash": self.region_binding_hash,
            "result_record_policy_id": self.result_record_policy_id,
            "result_record_policy_hash": self.result_record_policy_hash,
            "run_number": self.run_number,
        }


@dataclass(frozen=True, slots=True)
class PlannedLogicalRun:
    logical_run_id: str
    fixture_id: str
    candidate_id: str | None
    calls: tuple[PlannedProviderCall, ...]
    provider_free_no_call: bool = False


@dataclass(frozen=True, slots=True)
class PilotPlan:
    logical_runs: tuple[PlannedLogicalRun, ...]
    provider_calls: tuple[PlannedProviderCall, ...]
    maximum_real_physical_attempts: int
    pf1_no_call_count: int
    breakdown_by_workload: Mapping[str, int]
    breakdown_by_provider: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class NativeProviderRequest:
    call: PlannedProviderCall
    role_selection: ProviderRoleMappingSelection
    request_configuration_selection: PilotRequestConfigurationSelection | None
    payload_json: bytes = field(repr=False)
    payload_hash: str
    synthetic_semantic_json: bytes = field(repr=False)
    ps1_evidence: Ps1AssemblyResult | None = field(default=None, repr=False)
    search_tool_data: SearchToolProjections | None = field(default=None, repr=False)
    visual_asset_hashes: tuple[str, ...] = ()

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self.payload_json.decode("utf-8"))


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status_code: int
    response_bytes: bytes
    elapsed_seconds: float
    failure_signal: str | None = None


class PilotTransport(Protocol):
    def invoke(
        self,
        request: NativeProviderRequest,
        credential: _ResolvedCredential,
        deadline: AttemptDeadline,
    ) -> TransportResponse: ...


class SyntheticPilotTransport:
    """Deterministic local transport used only for provider-free tests."""

    __slots__ = (
        "_semantic_overrides",
        "_failure_once",
        "_timeout_once_call_ids",
        "_discovery_urls_by_call",
        "_seen",
        "_credential_matches",
    )

    def __init__(
        self,
        *,
        semantic_overrides: Mapping[str, Mapping[str, Any]] | None = None,
        failure_once: Mapping[str, str] | None = None,
        timeout_once_call_ids: set[str] | None = None,
        discovery_urls_by_call: Mapping[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._semantic_overrides = {
            key: dict(value) for key, value in (semantic_overrides or {}).items()
        }
        self._failure_once = dict(failure_once or {})
        self._timeout_once_call_ids = set(timeout_once_call_ids or ())
        self._discovery_urls_by_call = {
            key: tuple(value) for key, value in (discovery_urls_by_call or {}).items()
        }
        self._seen: list[str] = []
        self._credential_matches: list[bool] = []

    @property
    def invocation_count(self) -> int:
        return len(self._seen)

    @property
    def credential_boundary_matches(self) -> tuple[bool, ...]:
        return tuple(self._credential_matches)

    def invoke(
        self,
        request: NativeProviderRequest,
        credential: _ResolvedCredential,
        deadline: AttemptDeadline,
    ) -> TransportResponse:
        if not isinstance(request, NativeProviderRequest):
            raise _fail("transport_request")
        if not isinstance(deadline, AttemptDeadline):
            raise _fail("transport_deadline")
        secret = credential._transport_value(_TRANSPORT_SECRET_TOKEN)
        self._credential_matches.append(
            bool(secret)
            and credential.provider == request.call.provider
            and credential.environment_variable_name
            == CREDENTIAL_VARIABLE_BY_PROVIDER[request.call.provider]
        )
        occurrence = self._seen.count(request.call.call_id)
        self._seen.append(request.call.call_id)
        signal = self._failure_once.get(request.call.call_id) if occurrence == 0 else None
        if request.call.call_id in self._timeout_once_call_ids and occurrence == 0:
            return TransportResponse(
                status_code=200,
                response_bytes=_synthetic_provider_envelope(request),
                elapsed_seconds=121.0,
            )
        if signal == "connection":
            return TransportResponse(0, b"", 1.0, "connection")
        if signal == "timeout":
            return TransportResponse(200, _synthetic_provider_envelope(request), 121.0)
        if signal == "rate_limit":
            return TransportResponse(429, b"{}", 1.0, "rate_limit")
        if signal == "service_unavailable":
            return TransportResponse(503, b"{}", 1.0, "service_unavailable")
        if signal == "http_failure":
            return TransportResponse(400, b"{}", 1.0, "http_failure")
        if signal == "malformed":
            return TransportResponse(200, b"not-json", 1.0, "malformed")
        if signal == "refusal":
            return TransportResponse(200, b"{}", 1.0, "refusal")
        semantic = json.loads(request.synthetic_semantic_json.decode("utf-8"))
        override = self._semantic_overrides.get(request.call.call_id)
        if override:
            semantic.update(_json_copy(override))
        if signal == "schema_failure":
            semantic["unexpected_field"] = True
        overridden_request = NativeProviderRequest(
            call=request.call,
            role_selection=request.role_selection,
            request_configuration_selection=request.request_configuration_selection,
            payload_json=request.payload_json,
            payload_hash=request.payload_hash,
            synthetic_semantic_json=_canonical(semantic),
            ps1_evidence=request.ps1_evidence,
            search_tool_data=request.search_tool_data,
            visual_asset_hashes=request.visual_asset_hashes,
        )
        if request.call.workload_stage == "provider_native_url_discovery":
            return TransportResponse(
                status_code=200,
                response_bytes=_synthetic_discovery_envelope(
                    self._discovery_urls_by_call.get(request.call.call_id, (_PS1_URL,))
                ),
                elapsed_seconds=1.0,
            )
        return TransportResponse(
            status_code=200,
            response_bytes=_synthetic_provider_envelope(overridden_request),
            elapsed_seconds=1.0,
        )

    def __repr__(self) -> str:
        return (
            "SyntheticPilotTransport("
            f"invocation_count={self.invocation_count}, "
            f"credential_boundary_matches={tuple(self._credential_matches)!r})"
        )


@dataclass(frozen=True, slots=True)
class PilotAttemptOutcome:
    call: PlannedProviderCall
    record: PilotAttemptRecord
    budget_ledger: PilotBudgetLedger
    accepted: bool
    safe_failure_code: str | None
    retry_reason: str | None
    synthetic_provider_attempts: int = 1
    real_provider_calls: int = 0

    def safe_projection(self) -> dict[str, Any]:
        return {
            "call": self.call.safe_projection(),
            "credential_reference": {
                "provider": self.call.provider,
                "environment_variable_name": CREDENTIAL_VARIABLE_BY_PROVIDER[
                    self.call.provider
                ],
            },
            "record_hash": self.record.record_hash,
            "accepted": self.accepted,
            "safe_failure_code": self.safe_failure_code,
            "retry_reason": self.retry_reason,
            "synthetic_provider_attempts": self.synthetic_provider_attempts,
            "real_provider_calls": self.real_provider_calls,
        }


@dataclass(frozen=True, slots=True)
class LogicalRunOutcome:
    logical_run: PlannedLogicalRun
    attempts: tuple[PilotAttemptOutcome, ...]
    budget_ledger: PilotBudgetLedger
    accepted: bool


@dataclass(frozen=True, slots=True)
class Pf1Outcome:
    fixture_id: str = "PF1"
    status: str = "provider_free_safe_failure_captured"
    external_provider_call_required: bool = False
    synthetic_physical_attempts: int = 0
    cost_usd: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class SyntheticPilotSummary:
    status: str
    logical_runs: int
    completed_logical_runs: int
    failed_logical_runs: int
    blocked_logical_runs: int
    synthetic_physical_attempts: int
    real_provider_calls: int
    pilot_calls_completed: int
    scored_calls_completed: int
    pf1_no_call_executions: int
    application_refetches: int
    text_attempts: int
    visual_attempts: int
    discovery_attempts: int
    search_synthesis_attempts: int
    run_bundle: PilotRunBundle = field(repr=False)
    budget_ledger: PilotBudgetLedger
    all_records_validate: bool
    all_stage_identities_bound: bool
    privacy_checks_passed: bool
    network_calls: int
    real_credentials_used: bool
    winner_selected: bool
    execution_state: str
    synthetic_mode: bool

    def safe_projection(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "logical_runs": self.logical_runs,
            "completed_logical_runs": self.completed_logical_runs,
            "failed_logical_runs": self.failed_logical_runs,
            "blocked_logical_runs": self.blocked_logical_runs,
            "synthetic_physical_attempts": self.synthetic_physical_attempts,
            "real_provider_calls": self.real_provider_calls,
            "pilot_calls_completed": self.pilot_calls_completed,
            "scored_calls_completed": self.scored_calls_completed,
            "pf1_no_call_executions": self.pf1_no_call_executions,
            "application_refetches": self.application_refetches,
            "budget_committed_usd": str(self.budget_ledger.committed_cost_usd),
            "budget_remaining_usd": str(self.budget_ledger.remaining_unreserved_usd),
            "all_records_validate": self.all_records_validate,
            "all_stage_identities_bound": self.all_stage_identities_bound,
            "privacy_checks_passed": self.privacy_checks_passed,
            "network_calls": self.network_calls,
            "real_credentials_used": self.real_credentials_used,
            "winner_selected": self.winner_selected,
            "execution_state": self.execution_state,
            "synthetic_mode": self.synthetic_mode,
        }


class ProviderFreePilotRunner:
    """One immutable composition root for the frozen pilot contracts."""

    __slots__ = (
        "repository_root",
        "repository_harness_commit_sha",
        "evaluation_id",
        "experiment_version",
        "request_configuration_set_hash",
        "budget_control_hash",
        "region_binding_hash",
        "credential_references",
        "plan",
        "_artifacts",
        "_mappings",
        "_adapters",
        "_configurations",
        "_schema_registry",
        "_retry_policy",
        "_visual_context",
        "_visual_assets",
        "_prompt_hashes",
        "_schema_hashes",
        "_parser_identity",
        "_result_contract",
    )

    def __init__(
        self,
        *,
        repository_root: Path,
        repository_harness_commit_sha: str,
        artifacts: Mapping[str, Any],
        mappings: ProviderRoleMappingSet,
        adapters: ProviderAdapterSet,
        configurations: PilotRequestConfigurationSet,
        schema_registry: CanonicalOutputSchemaRegistry,
        retry_policy: RetryPolicy,
        visual_context: FrozenVisualContextContract,
        visual_assets: FrozenPilotVisualAssets,
        prompt_hashes: Mapping[str, str],
        schema_hashes: Mapping[str, str],
        parser_identity: Any,
        result_contract: Any,
        plan: PilotPlan,
        budget_control_hash: str,
    ) -> None:
        self.repository_root = repository_root
        self.repository_harness_commit_sha = repository_harness_commit_sha
        self.evaluation_id = _EVALUATION_ID
        self.experiment_version = _EXPERIMENT_VERSION
        self.request_configuration_set_hash = configurations.semantic_hash
        self.budget_control_hash = budget_control_hash
        self.region_binding_hash = REGION_BINDING_HASH
        self.credential_references = tuple(
            CredentialReference(provider, variable)
            for provider, variable in CREDENTIAL_VARIABLE_BY_PROVIDER.items()
        )
        self.plan = plan
        self._artifacts = MappingProxyType(dict(artifacts))
        self._mappings = mappings
        self._adapters = adapters
        self._configurations = configurations
        self._schema_registry = schema_registry
        self._retry_policy = retry_policy
        self._visual_context = visual_context
        self._visual_assets = visual_assets
        self._prompt_hashes = MappingProxyType(dict(prompt_hashes))
        self._schema_hashes = MappingProxyType(dict(schema_hashes))
        self._parser_identity = parser_identity
        self._result_contract = result_contract

    def logical_run_for_call(self, call_id: str) -> PlannedLogicalRun:
        matches = tuple(
            run for run in self.plan.logical_runs
            if any(call.call_id == call_id for call in run.calls)
        )
        if len(matches) != 1:
            raise _fail("logical_run_selection")
        return matches[0]

    def readiness_projection(self) -> dict[str, Any]:
        return {
            "status": PILOT_RUNNER_STATUS,
            "common_preflight": "ready",
            "same_day_certification": "pending",
            "credential_provisioning_and_authorization": "pending",
            "explicit_pilot_authorization": "pending",
            "provider_calls_allowed": False,
            "pilot_calls_allowed": False,
            "scored_calls_allowed": False,
            "provider_calls_completed": 0,
            "pilot_calls_completed": 0,
            "scored_calls_completed": 0,
            "winner_selected": False,
        }

    def request_payload_snapshots(self) -> dict[str, dict[str, Any]]:
        keys = (
            "openai_text",
            "openai_visual",
            "openai_url_discovery",
            "openai_search_synthesis",
            "gemini_text",
            "gemini_visual",
            "groq_gpt_oss_text",
            "groq_qwen_visual",
            "groq_baseline_text",
        )
        selectors = {
            "openai_text": lambda c: c.provider == "OpenAI" and c.workload_stage == "text_analysis",
            "openai_visual": lambda c: (
                c.provider == "OpenAI" and c.workload_stage == "visual_inspection"
            ),
            "openai_url_discovery": lambda c: c.workload_stage == "provider_native_url_discovery",
            "openai_search_synthesis": lambda c: (
                c.provider == "OpenAI" and c.workload_stage == "search_synthesis"
            ),
            "gemini_text": lambda c: (
                c.provider == "Google Gemini" and c.workload_stage == "text_analysis"
            ),
            "gemini_visual": lambda c: (
                c.provider == "Google Gemini"
                and c.workload_stage == "visual_inspection"
            ),
            "groq_gpt_oss_text": lambda c: (
                c.candidate_id == "groq_split_v1"
                and c.workload_stage == "text_analysis"
            ),
            "groq_qwen_visual": lambda c: (
                c.candidate_id == "groq_split_v1"
                and c.workload_stage == "visual_inspection"
            ),
            "groq_baseline_text": lambda c: c.candidate_id == "baseline_current_text_v1",
        }
        snapshots: dict[str, dict[str, Any]] = {}
        for key in keys:
            call = next(call for call in self.plan.provider_calls if selectors[key](call))
            request = self._build_native_request(call)
            payload = request.payload
            plan = expected_provider_request_plan(request.role_selection)
            native_surfaces = tuple(
                item["native_surface"] for item in plan["ordered_native_segments"]
            )
            snapshot = {
                "provider": call.provider,
                "model": call.model,
                "api_family": call.api_family,
                "workload_stage": call.workload_stage,
                "topology_id": call.topology_id,
                "native_surfaces": native_surfaces,
                "segment_authorities": tuple(
                    item["authority_class"]
                    for item in plan["ordered_native_segments"]
                ),
                "schema_placement": plan["schema_placement"],
                "structured_output": (
                    request.request_configuration_selection.configuration.structured_output_mode
                    if request.request_configuration_selection is not None
                    else "provider_native_structured_url_extraction"
                ),
                "streaming": payload.get("stream", False),
                "payload_hash": request.payload_hash,
            }
            if call.workload_stage == "provider_native_url_discovery":
                snapshot["tool_type"] = payload["tools"][0]["type"]
            if call.workload_stage == "visual_inspection":
                snapshot["media_surface"] = {
                    "OpenAI": "input_image",
                    "Google Gemini": "image",
                    "Groq": "image_url",
                }[call.provider]
            snapshots[key] = snapshot
        return snapshots

    def execute_pf1(self) -> Pf1Outcome:
        fixture = self._fixture("PF1")
        if (
            fixture.get("external_provider_call_required") is not False
            or fixture.get("provider_visible_input") is not None
        ):
            raise _fail("pf1_contract")
        return Pf1Outcome()

    def execute_one(
        self,
        call: PlannedProviderCall,
        *,
        gate: LiveGateBinding,
        credential_resolver: CredentialResolver,
        transport: PilotTransport,
        budget_ledger: PilotBudgetLedger,
        conservative_reservation_usd: Any,
        synthetic_today: str,
        attempt_number: int = 1,
        retry_reason: str | None = None,
        ps1_evidence: Ps1AssemblyResult | None = None,
        search_tool_data: SearchToolProjections | None = None,
    ) -> PilotAttemptOutcome:
        self._validate_live_gate(gate, synthetic_today=synthetic_today)
        authoritative = self._authoritative_call(call.call_id)
        if call != authoritative:
            raise _fail("pre_attempt_identity")
        if type(attempt_number) is not int or not 1 <= attempt_number <= 2:
            raise _fail("attempt_number")
        if attempt_number == 1 and retry_reason is not None:
            raise _fail("retry_linkage")
        if attempt_number == 2 and retry_reason is None:
            raise _fail("retry_linkage")

        request = self._build_native_request(
            call,
            ps1_evidence=ps1_evidence,
            search_tool_data=search_tool_data,
        )
        reservation = self._reservation_value(conservative_reservation_usd)
        attempt_id = f"pa-{self.plan.provider_calls.index(call) + 1:04d}-{attempt_number}"
        try:
            reserved = reserve_provider_attempt(
                budget_ledger,
                attempt_id=attempt_id,
                conservative_upper_bound_usd=reservation,
            )
        except PilotBudgetError as exc:
            raise _fail(str(exc)) from exc

        credential_reference = self._credential_reference(call.provider, gate)
        credential = credential_resolver.resolve(credential_reference)
        deadline = AttemptDeadline(started_monotonic=0.0)
        response = transport.invoke(request, credential, deadline)
        del credential

        mapped = _map_transport_result(response, deadline)
        if mapped is not None:
            failure_code, transient_reason = mapped
            outcome = self._failure_outcome(
                request=request,
                response=response,
                attempt_number=attempt_number,
                retry_reason=retry_reason,
                failure_code=failure_code,
                budget_ledger=reserved,
                attempt_id=attempt_id,
                transient_retry_reason=transient_reason,
            )
            return outcome

        try:
            return self._successful_or_semantic_failure_outcome(
                request=request,
                response=response,
                attempt_number=attempt_number,
                retry_reason=retry_reason,
                budget_ledger=reserved,
                attempt_id=attempt_id,
            )
        except CanonicalSchemaValidationError:
            return self._failure_outcome(
                request=request,
                response=response,
                attempt_number=attempt_number,
                retry_reason=retry_reason,
                failure_code="failed_canonical_validation",
                budget_ledger=reserved,
                attempt_id=attempt_id,
            )
        except (ProviderAdapterResponseError, TransportCaptureStateError):
            return self._failure_outcome(
                request=request,
                response=response,
                attempt_number=attempt_number,
                retry_reason=retry_reason,
                failure_code="failed_transport_extraction",
                budget_ledger=reserved,
                attempt_id=attempt_id,
            )
        except UrlDiscoveryError:
            return self._failure_outcome(
                request=request,
                response=response,
                attempt_number=attempt_number,
                retry_reason=retry_reason,
                failure_code="failed_transport_extraction",
                budget_ledger=reserved,
                attempt_id=attempt_id,
            )
        except (DuplicateJsonKeyError, StrictJsonPayloadError):
            return self._failure_outcome(
                request=request,
                response=response,
                attempt_number=attempt_number,
                retry_reason=retry_reason,
                failure_code="failed_strict_parse",
                budget_ledger=reserved,
                attempt_id=attempt_id,
            )
        except DeterministicValidationError as exc:
            failure = {
                "text_cross_field_validator_v1": "failed_cross_field_validation",
                "visual_photo_reference_validator_v1": "failed_cross_field_validation",
                "search_cross_reference_validator_v1": "failed_trace_validation",
            }.get(exc.validator_id, "failed_evidence_policy")
            return self._failure_outcome(
                request=request,
                response=response,
                attempt_number=attempt_number,
                retry_reason=retry_reason,
                failure_code=failure,
                budget_ledger=reserved,
                attempt_id=attempt_id,
            )

    def execute_logical_run(
        self,
        logical_run: PlannedLogicalRun,
        *,
        gate: LiveGateBinding,
        credential_resolver: CredentialResolver,
        transport: PilotTransport,
        budget_ledger: PilotBudgetLedger,
        conservative_reservation_usd: Any,
        synthetic_today: str,
    ) -> LogicalRunOutcome:
        if logical_run.provider_free_no_call:
            self.execute_pf1()
            return LogicalRunOutcome(logical_run, (), budget_ledger, True)
        ledger = budget_ledger
        outcomes: list[PilotAttemptOutcome] = []
        ps1_evidence = None
        search_tool_data = None
        for call in logical_run.calls:
            attempt_number = 1
            retry_reason = None
            while True:
                outcome = self.execute_one(
                    call,
                    gate=gate,
                    credential_resolver=credential_resolver,
                    transport=transport,
                    budget_ledger=ledger,
                    conservative_reservation_usd=conservative_reservation_usd,
                    synthetic_today=synthetic_today,
                    attempt_number=attempt_number,
                    retry_reason=retry_reason,
                    ps1_evidence=ps1_evidence,
                    search_tool_data=search_tool_data,
                )
                outcomes.append(outcome)
                ledger = outcome.budget_ledger
                if outcome.accepted:
                    if call.workload_stage == "provider_native_url_discovery":
                        ps1_evidence, search_tool_data = self._synthetic_ps1_material(call)
                    break
                retry_decision = decide_retry(
                    attempt_number=attempt_number,
                    attempt_outcome=outcome.safe_failure_code,
                    transient_retry_reason=outcome.retry_reason,
                )
                if not retry_decision.retry_allowed:
                    return LogicalRunOutcome(
                        logical_run,
                        tuple(outcomes),
                        ledger,
                        False,
                    )
                attempt_number = retry_decision.next_attempt_number
                retry_reason = retry_decision.retry_reason
        return LogicalRunOutcome(logical_run, tuple(outcomes), ledger, True)

    def run_complete_synthetic_pilot(
        self,
        *,
        gate: LiveGateBinding,
        credential_resolver: CredentialResolver,
        transport: PilotTransport,
        conservative_reservation_usd: Any,
        synthetic_today: str,
    ) -> SyntheticPilotSummary:
        ledger = empty_pilot_budget_ledger()
        bundle = PilotRunBundle()
        completed = 0
        failed = 0
        physical: list[PilotAttemptOutcome] = []
        pf1_count = 0
        for logical_run in self.plan.logical_runs:
            if logical_run.provider_free_no_call:
                self.execute_pf1()
                pf1_count += 1
                completed += 1
                continue
            result = self.execute_logical_run(
                logical_run,
                gate=gate,
                credential_resolver=credential_resolver,
                transport=transport,
                budget_ledger=ledger,
                conservative_reservation_usd=conservative_reservation_usd,
                synthetic_today=synthetic_today,
            )
            ledger = result.budget_ledger
            physical.extend(result.attempts)
            if result.accepted:
                completed += 1
            else:
                failed += 1
            for attempt in result.attempts:
                bundle = bundle.append_attempt(attempt.record)
        serialized_records = _canonical([record.as_dict() for record in bundle.attempts])
        privacy_passed = not any(
            marker in serialized_records
            for marker in (b"synthetic-secret", b"Authorization", b"Bearer ")
        )
        return SyntheticPilotSummary(
            status=("synthetic_pilot_complete" if failed == 0 else "synthetic_pilot_failed"),
            logical_runs=len(self.plan.logical_runs),
            completed_logical_runs=completed,
            failed_logical_runs=failed,
            blocked_logical_runs=0,
            synthetic_physical_attempts=len(physical),
            real_provider_calls=0,
            pilot_calls_completed=0,
            scored_calls_completed=0,
            pf1_no_call_executions=pf1_count,
            application_refetches=sum(
                item.call.workload_stage == "provider_native_url_discovery"
                and item.accepted
                for item in physical
            ),
            text_attempts=sum(item.call.workload_stage == "text_analysis" for item in physical),
            visual_attempts=sum(
                item.call.workload_stage == "visual_inspection" for item in physical
            ),
            discovery_attempts=sum(
                item.call.workload_stage == "provider_native_url_discovery"
                for item in physical
            ),
            search_synthesis_attempts=sum(
                item.call.workload_stage == "search_synthesis" for item in physical
            ),
            run_bundle=bundle,
            budget_ledger=ledger,
            all_records_validate=all(record.record_hash for record in bundle.attempts),
            all_stage_identities_bound=all(
                record.as_dict()["normalization_audit"]["attempt_state_coherence"]
                == "passed"
                for record in bundle.attempts
            ),
            privacy_checks_passed=privacy_passed,
            network_calls=0,
            real_credentials_used=False,
            winner_selected=False,
            execution_state="blocked_pre_execution",
            synthetic_mode=True,
        )

    def _fixture(self, fixture_id: str) -> dict[str, Any]:
        fixtures = self._artifacts["pilot_fixtures"]["pilot_fixtures"]
        matches = tuple(item for item in fixtures if item.get("id") == fixture_id)
        if len(matches) != 1:
            raise _fail("fixture_identity")
        return _json_copy(matches[0])

    def _authoritative_call(self, call_id: str) -> PlannedProviderCall:
        matches = tuple(call for call in self.plan.provider_calls if call.call_id == call_id)
        if len(matches) != 1:
            raise _fail("call_identity")
        return matches[0]

    def _credential_reference(
        self,
        provider: str,
        gate: LiveGateBinding,
    ) -> CredentialReference:
        matches = tuple(item for item in gate.credential_references if item.provider == provider)
        if len(matches) != 1:
            raise _fail("live_gate:credential_reference")
        return matches[0]

    def _reservation_value(self, value: Any) -> str:
        if type(value) is not str:
            raise _fail("budget_reservation")
        try:
            parsed = Decimal(value)
        except InvalidOperation as exc:
            raise _fail("budget_reservation") from exc
        if not parsed.is_finite() or parsed <= 0:
            raise _fail("budget_reservation")
        return value

    def _validate_live_gate(self, gate: LiveGateBinding, *, synthetic_today: str) -> None:
        expected_references = self.credential_references
        if (
            not isinstance(gate, LiveGateBinding)
            or gate.binding_mode != "synthetic_provider_free"
            or gate.evaluation_id != self.evaluation_id
            or gate.experiment_version != self.experiment_version
            or gate.common_preflight_status != "ready"
            or gate.same_day_certification_status != "synthetic_certified_for_tests"
            or gate.credential_authorization_status != "synthetic_authorized_for_tests"
            or gate.explicit_pilot_authorization_status != "synthetic_authorized_for_tests"
            or gate.request_configuration_set_hash != self.request_configuration_set_hash
            or gate.budget_control_hash != self.budget_control_hash
            or gate.region_binding_hash != self.region_binding_hash
            or gate.valid_on_date != synthetic_today
            or gate.credential_references != expected_references
        ):
            raise _fail("live_gate")

    def _build_native_request(
        self,
        call: PlannedProviderCall,
        *,
        ps1_evidence: Ps1AssemblyResult | None = None,
        search_tool_data: SearchToolProjections | None = None,
    ) -> NativeProviderRequest:
        fixture = self._fixture(call.fixture_id)
        if call.workload_stage == "provider_native_url_discovery":
            configuration = select_url_discovery_configuration(call.candidate_id)
            if (
                configuration.configuration_id != call.request_configuration_id
                or configuration.semantic_hash != call.request_configuration_hash
                or configuration.model != call.model
                or configuration.adapter_id != call.adapter_id
                or configuration.role_mapping_id != call.role_mapping_id
            ):
                raise _fail("pre_attempt_identity")
            role_selection = select_provider_role_mapping(
                self._mappings,
                candidate_id=call.candidate_id,
                provider=call.provider,
                model_id=call.model,
                api_family=call.api_family,
                workload_stage="search_retrieval",
                topology_id="two_call_search_retrieval",
            )
            plan = expected_provider_request_plan(role_selection)
            validate_provider_request_plan(role_selection, plan)
            query = _render_search_target(fixture)
            payload = build_openai_url_discovery_request(
                configuration=configuration,
                raw_query=query,
            )
            semantic = {
                "retrieval_status": "partial",
                "sources": [],
            }
            return NativeProviderRequest(
                call=call,
                role_selection=role_selection,
                request_configuration_selection=None,
                payload_json=_canonical(payload),
                payload_hash=_hash(payload),
                synthetic_semantic_json=_canonical(semantic),
            )

        selection = select_pilot_request_configuration(
            self._configurations,
            candidate_id=call.candidate_id,
            workload_stage=call.workload_stage,
        )
        configuration = selection.configuration
        if (
            configuration.configuration_id != call.request_configuration_id
            or configuration.semantic_hash != call.request_configuration_hash
            or configuration.provider != call.provider
            or configuration.model != call.model
            or configuration.api_family != call.api_family
            or configuration.topology_id != call.topology_id
            or configuration.adapter_id != call.adapter_id
            or configuration.adapter_hash != call.adapter_hash
            or configuration.role_mapping_id != call.role_mapping_id
            or configuration.role_mapping_hash != call.role_mapping_hash
            or configuration.output_schema_id != call.schema_id
            or configuration.output_schema_hash != call.schema_hash
        ):
            raise _fail("pre_attempt_identity")
        role_selection = select_provider_role_mapping(
            self._mappings,
            candidate_id=call.candidate_id,
            provider=call.provider,
            model_id=call.model,
            api_family=call.api_family,
            workload_stage=call.workload_stage,
            topology_id=call.topology_id,
        )
        plan = expected_provider_request_plan(role_selection)
        validate_provider_request_plan(role_selection, plan)

        if call.workload_stage == "text_analysis":
            instruction = _template_text(self._artifacts["prompts"], "text_system_v1")
            user_text = _render_template(
                self._artifacts["prompts"],
                "text_input_v1",
                {
                    key: fixture[key]
                    for key in (
                        "title",
                        "description",
                        "asking_price",
                        "currency",
                        "marketplace_source",
                        "region",
                    )
                },
            )
            semantic = _synthetic_text_semantic(fixture)
            payload, visual_hashes = self._provider_payload(
                configuration,
                instruction=instruction,
                untrusted_segments=(user_text,),
                image=None,
            )
        elif call.workload_stage == "visual_inspection":
            instruction = _template_text(self._artifacts["prompts"], "visual_system_v1")
            rendered = render_pilot_visual_context(
                self._visual_context,
                fixture_id=call.fixture_id,
            )
            image = self._visual_image(call.fixture_id)
            semantic = _synthetic_visual_semantic(fixture)
            payload, visual_hashes = self._provider_payload(
                configuration,
                instruction=instruction,
                untrusted_segments=(rendered.provider_visible_context,),
                image=image,
            )
        elif call.workload_stage == "search_synthesis":
            if ps1_evidence is None or search_tool_data is None:
                ps1_evidence, search_tool_data = self._synthetic_ps1_material(call)
            target = {
                "product_identity": fixture["product_identity"],
                "exact_variant_or_sku": fixture["exact_variant"],
                "region": fixture["region"],
                "currency": fixture["currency"],
                "retrieved_evidence_bundle": ps1_evidence.canonical_bundle,
            }
            rendered = _render_template(
                self._artifacts["prompts"],
                "search_synthesis_v1",
                target,
            )
            lines = rendered.split("\n")
            instruction = lines[0]
            untrusted = "\n".join(lines[1:])
            semantic = _synthetic_search_semantic(ps1_evidence)
            payload, visual_hashes = self._provider_payload(
                configuration,
                instruction=instruction,
                untrusted_segments=(untrusted,),
                image=None,
            )
        else:
            raise _fail("workload_stage")
        return NativeProviderRequest(
            call=call,
            role_selection=role_selection,
            request_configuration_selection=selection,
            payload_json=_canonical(payload),
            payload_hash=_hash(payload),
            synthetic_semantic_json=_canonical(semantic),
            ps1_evidence=ps1_evidence,
            search_tool_data=search_tool_data,
            visual_asset_hashes=visual_hashes,
        )

    def _provider_payload(
        self,
        configuration: Any,
        *,
        instruction: str,
        untrusted_segments: tuple[str, ...],
        image: tuple[bytes, str, str] | None,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        schema = _schema_document(self._artifacts["schemas"], configuration.output_schema_id)
        rendered_segments = tuple(_provider_segment_text(item) for item in untrusted_segments)
        visual_hashes: tuple[str, ...] = ()
        if image is not None:
            image_bytes, mime_type, image_hash = image
            data_url = f"data:{mime_type};base64,{b64encode(image_bytes).decode('ascii')}"
            visual_hashes = (image_hash,)
        if configuration.provider == "OpenAI":
            content: list[dict[str, Any]] = [
                {"type": "input_text", "text": text} for text in rendered_segments
            ]
            if image is not None:
                content.append(
                    {
                        "type": "input_image",
                        "image_url": data_url,
                        "detail": configuration.image_detail,
                    }
                )
            payload = {
                "model": configuration.model,
                "instructions": instruction,
                "input": [{"role": "user", "content": content}],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": configuration.output_schema_id,
                        "schema": schema,
                        "strict": True,
                    }
                },
                "reasoning": {"effort": configuration.reasoning},
                "temperature": configuration.temperature,
                "max_output_tokens": configuration.maximum_output_tokens,
                "stream": configuration.streaming_enabled,
                "store": configuration.storage_configuration["value"],
            }
        elif configuration.provider == "Google Gemini":
            content = [{"type": "text", "text": text} for text in rendered_segments]
            if image is not None:
                content.append(
                    {
                        "type": "image",
                        "inline_data": {"mime_type": mime_type, "data": data_url},
                    }
                )
            payload = {
                "model": configuration.model,
                "system_instruction": instruction,
                "input": [{"role": "user", "content": content}],
                "response_format": {
                    "mime_type": "application/json",
                    "json_schema": schema,
                },
                "generation_config": {
                    "max_output_tokens": configuration.maximum_output_tokens,
                    "thinking_level": configuration.reasoning,
                },
                "stream": configuration.streaming_enabled,
                "store": configuration.storage_configuration["value"],
            }
        elif configuration.provider == "Groq":
            if image is None:
                user_content: Any = "\n".join(rendered_segments)
            else:
                user_content = [
                    {"type": "text", "text": "\n".join(rendered_segments)},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]
            if configuration.structured_output_mode == "json_object":
                response_format = {"type": "json_object"}
            else:
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": configuration.output_schema_id,
                        "schema": schema,
                        "strict": configuration.structured_output_mode
                        == "json_schema_strict",
                    },
                }
            payload = {
                "model": configuration.model,
                "messages": [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": user_content},
                ],
                "response_format": response_format,
                "max_completion_tokens": configuration.maximum_output_tokens,
                "temperature": configuration.temperature,
                "stream": configuration.streaming_enabled,
            }
            if configuration.reasoning is not None:
                payload["reasoning_effort"] = configuration.reasoning
        else:
            raise _fail("provider")
        return payload, visual_hashes

    def _visual_image(self, fixture_id: str) -> tuple[bytes, str, str]:
        matches = tuple(
            image for image in self._visual_assets.images if image.fixture_id == fixture_id
        )
        if len(matches) != 1:
            raise _fail("visual_asset_identity")
        image = matches[0]
        path = self.repository_root / image.path
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != image.sha256:
            raise _fail("visual_asset_hash")
        return payload, image.mime_type, image.sha256

    def _synthetic_ps1_material(
        self,
        call: PlannedProviderCall,
    ) -> tuple[Ps1AssemblyResult, SearchToolProjections]:
        discovery = _synthetic_discovery_url(call)
        capabilities = {0: derive_restricted_trace_reference(b"p" * 16)}
        classifier_input = build_ps1_classifier_input(
            exact_urls=(_PS1_URL,),
            retrieval_auth_contexts=("public_unauthenticated",),
            reference_capabilities=capabilities,
        )
        refetch = Ps1RefetchObservation(
            discovery=discovery,
            retrieval_attempt_ordinal=1,
            tool_call_ordinal=1,
            result_ordinal=1,
            classifier_input=classifier_input,
            reference_capabilities=capabilities,
            status_code=200,
            captured_at=datetime(2026, 8, 31, 20, 0, tzinfo=UTC),
            display_name="Logitech MX Master 3S",
            decoded_body=(
                "MX Master 3S Graphite standard right-handed mouse. "
                "Includes Logi Bolt USB receiver."
            ),
            evidence_candidates=(
                Ps1EvidenceCandidate(
                    "identity",
                    "MX Master 3S Graphite standard right-handed mouse.",
                ),
                Ps1EvidenceCandidate("bundle", "Includes Logi Bolt USB receiver."),
            ),
        )
        evidence = assemble_ps1_evidence_bundle(
            retrieval_status="partial",
            discoveries=(discovery,),
            refetch_observations=(refetch,),
        )
        operation = RawSearchToolOperation(
            retrieval_attempt_ordinal=1,
            tool_call_ordinal=1,
            operation_type="search",
            raw_search_query="Logitech MX Master 3S Graphite US Logi Bolt receiver",
            raw_tool_arguments={"query": "Logitech MX Master 3S Graphite US"},
            outcome="completed",
            safe_failure_code=None,
            started_at=_FIXED_STARTED,
            completed_at="2026-08-31T20:00:00.250Z",
            latency_ms=250,
            restricted_trace_reference=derive_restricted_trace_reference(b"q" * 16),
            restricted_url_traces=evidence.restricted_traces,
        )
        search_tool = build_search_tool_projections(
            operations=(operation,),
            trace_inventory=evidence.trace_inventory,
            allocation_plan=evidence.allocation_plan,
            claim_evidence_links=(),
        )
        return evidence, search_tool

    def _successful_or_semantic_failure_outcome(
        self,
        *,
        request: NativeProviderRequest,
        response: TransportResponse,
        attempt_number: int,
        retry_reason: str | None,
        budget_ledger: PilotBudgetLedger,
        attempt_id: str,
    ) -> PilotAttemptOutcome:
        call = request.call
        if call.workload_stage == "provider_native_url_discovery":
            evidence, search_tool_data = self._synthetic_ps1_material(call)
            configuration = select_url_discovery_configuration(call.candidate_id)
            projection = extract_openai_url_discovery(
                response_bytes=response.response_bytes,
                raw_query=_render_search_target(self._fixture("PS1")),
                raw_tool_arguments={"query": "Logitech MX Master 3S Graphite US"},
                evaluation_id=self.evaluation_id,
                fixture_id="PS1",
                run_number=call.run_number,
                attempt_number=attempt_number,
                operation_id=f"discovery-{call.run_number:04d}",
                candidate_id=call.candidate_id,
                provider=call.provider,
                model=call.model,
                configuration_id=call.request_configuration_id,
                configuration_hash=call.request_configuration_hash,
                mapping_id=call.role_mapping_id,
                mapping_hash=call.role_mapping_hash,
                adapter_id=call.adapter_id,
                adapter_hash=call.adapter_hash,
                started_at=_FIXED_STARTED,
                completed_at="2026-08-31T20:00:01.000Z",
                latency_ms=1000,
                restricted_trace_references=(
                    derive_restricted_trace_reference(b"p" * 16),
                ),
            )
            bind_url_discovery_to_ps1_refetch(
                discovery=projection,
                ps1_evidence=evidence,
            )
            raw_hash = hashlib.sha256(response.response_bytes).hexdigest()
            state = _accepted_state(
                "search_retrieval",
                raw_hash=raw_hash,
                accepted_hash=evidence.canonical_evidence_bundle_hash,
            )
            record = self._build_record(
                request=request,
                state=state,
                raw_response=response.response_bytes,
                semantic_hash=evidence.canonical_evidence_bundle_hash,
                attempt_number=attempt_number,
                retry_reason=retry_reason,
                ps1_evidence=evidence,
                search_tool_data=search_tool_data,
                adapted=None,
            )
        else:
            capture = _capture(response.response_bytes)
            adapted = adapt_provider_response(
                self._adapters,
                request.role_selection,
                capture,
                http_status=response.status_code,
            )
            normalized = normalize_semantic_json(adapted.semantic_content_bytes)
            validated = self._schema_registry.validate(
                call.schema_id,
                normalized,
            )
            if call.workload_stage == "text_analysis":
                validate_text_post_schema_candidate(
                    validated,
                    schema_registry=self._schema_registry,
                )
                branch = "text_final"
            elif call.workload_stage == "visual_inspection":
                validate_visual_post_schema_candidate(
                    validated,
                    schema_registry=self._schema_registry,
                    supplied_image_count=len(request.visual_asset_hashes),
                )
                branch = "visual_final"
            elif call.workload_stage == "search_synthesis":
                if request.ps1_evidence is None:
                    raise _fail("ps1_evidence_required")
                validate_search_cross_references(
                    validated.canonical_semantic_json.admitted.value,
                    request.ps1_evidence.canonical_bundle,
                )
                branch = "search_synthesis_final"
            else:
                raise _fail("workload_stage")
            semantic_hash = normalized.strict_parsed_semantic_payload_hash
            state = _accepted_state(
                branch,
                raw_hash=capture.raw_provider_response_hash,
                accepted_hash=semantic_hash,
            )
            record = self._build_record(
                request=request,
                state=state,
                raw_response=response.response_bytes,
                semantic_hash=semantic_hash,
                attempt_number=attempt_number,
                retry_reason=retry_reason,
                ps1_evidence=request.ps1_evidence,
                search_tool_data=request.search_tool_data,
                adapted=adapted,
            )
        committed = commit_provider_attempt_cost(
            budget_ledger,
            attempt_id=attempt_id,
            actual_cost_usd="0.00",
            outcome="succeeded",
        )
        return PilotAttemptOutcome(
            call=call,
            record=record,
            budget_ledger=committed,
            accepted=True,
            safe_failure_code=None,
            retry_reason=None,
        )

    def _failure_outcome(
        self,
        *,
        request: NativeProviderRequest,
        response: TransportResponse,
        attempt_number: int,
        retry_reason: str | None,
        failure_code: str,
        budget_ledger: PilotBudgetLedger,
        attempt_id: str,
        transient_retry_reason: str | None = None,
    ) -> PilotAttemptOutcome:
        branch = _branch_for_call(request.call)
        raw = response.response_bytes or None
        raw_hash = hashlib.sha256(raw).hexdigest() if raw is not None else None
        semantic_hash = None
        adapted = None
        if raw is not None and failure_code in {
            "failed_canonical_validation",
            "failed_cross_field_validation",
            "failed_trace_validation",
            "failed_evidence_policy",
        }:
            capture = _capture(raw)
            adapted = adapt_provider_response(
                self._adapters,
                request.role_selection,
                capture,
                http_status=response.status_code,
            )
            normalized = normalize_semantic_json(adapted.semantic_content_bytes)
            semantic_hash = normalized.strict_parsed_semantic_payload_hash
        state, normalization_actions = _failure_state(
            branch,
            failure_code=failure_code,
            raw_hash=raw_hash,
            adapter_identity=(
                request.call.adapter_id,
                "v1",
                request.call.adapter_hash,
            ),
        )
        ps1_evidence = request.ps1_evidence
        search_tool_data = request.search_tool_data
        record = self._build_record(
            request=request,
            state=state,
            raw_response=raw,
            semantic_hash=semantic_hash,
            attempt_number=attempt_number,
            retry_reason=retry_reason,
            ps1_evidence=ps1_evidence,
            search_tool_data=search_tool_data,
            adapted=adapted,
            normalization_actions=normalization_actions,
        )
        transient = failure_code in {
            "provider_connection_error",
            "provider_timeout",
        } or response.failure_signal in {"rate_limit", "service_unavailable"}
        committed = commit_provider_attempt_cost(
            budget_ledger,
            attempt_id=attempt_id,
            actual_cost_usd="0.00",
            outcome="failed_retryable" if transient else "failed_nonretryable",
        )
        return PilotAttemptOutcome(
            call=request.call,
            record=record,
            budget_ledger=committed,
            accepted=False,
            safe_failure_code=failure_code,
            retry_reason=transient_retry_reason,
        )

    def _build_record(
        self,
        *,
        request: NativeProviderRequest,
        state: Any,
        raw_response: bytes | None,
        semantic_hash: str | None,
        attempt_number: int,
        retry_reason: str | None,
        ps1_evidence: Ps1AssemblyResult | None,
        search_tool_data: SearchToolProjections | None,
        adapted: AdaptedProviderResponse | None,
        normalization_actions: tuple[NormalizationActionRecord, ...] = (),
    ) -> PilotAttemptRecord:
        call = request.call
        provider_data = project_provider_data(
            raw_provider_response=raw_response,
            restricted_url_trace=None,
            safe_transport_metadata=_safe_transport_metadata(
                call,
                state=state,
                attempt_number=attempt_number,
                adapted=adapted,
            ),
        )
        audit = self._normalization_audit(
            request=request,
            state=state,
            semantic_hash=semantic_hash,
            adapted=adapted,
            raw_response=raw_response,
            ps1_evidence=ps1_evidence,
            normalization_actions=normalization_actions,
        )
        key = PilotAttemptKey(
            evaluation_id=self.evaluation_id,
            fixture_id=call.fixture_id,
            candidate_id=call.candidate_id,
            provider=call.provider,
            model=call.model,
            component_topology=call.topology_id,
            workload={
                "text_analysis": "text_risk_analysis",
                "visual_inspection": "visual_inspection",
                "provider_native_url_discovery": "grounded_product_price_research",
                "search_synthesis": "grounded_product_price_research",
            }[call.workload_stage],
            run_number=call.run_number,
            attempt_number=attempt_number,
        )
        envelope = self._pilot_envelope(
            request=request,
            key=key,
            state=state,
            audit=audit,
            provider_data=provider_data,
            attempt_number=attempt_number,
            retry_reason=retry_reason,
            search_tool_data=search_tool_data,
        )
        return build_pilot_attempt_record(
            attempt_key=key,
            attempt_state=state,
            provider_data=provider_data,
            normalization_audit=audit,
            pilot_envelope=envelope,
            provider_attempt_started=True,
            search_tool_data=search_tool_data,
            ps1_evidence=ps1_evidence,
            request_configuration_selection=request.request_configuration_selection,
        )

    def _normalization_audit(
        self,
        *,
        request: NativeProviderRequest,
        state: Any,
        semantic_hash: str | None,
        adapted: AdaptedProviderResponse | None,
        raw_response: bytes | None,
        ps1_evidence: Ps1AssemblyResult | None,
        normalization_actions: tuple[NormalizationActionRecord, ...],
    ) -> dict[str, Any]:
        parser = self._artifacts["parser"]
        children = dict(self._parser_identity.child_hashes)
        values = {field: None for field in self._result_contract.normalization_audit_fields}
        stage_index = HIGHEST_COMPLETED_STAGES.index(state.highest_completed_stage)
        raw_hash = hashlib.sha256(raw_response).hexdigest() if raw_response is not None else None
        adapter_hash = request.call.adapter_hash
        values.update(
            {
                "normalization_spec_id": "normalization_parser_spec_v1",
                "normalization_spec_version": "v1",
                "normalization_spec_semantic_hash": self._parser_identity.semantic_hash,
                "normalization_spec_file_sha256_or_immutable_run_binding_reference": hashlib.sha256(
                    (
                        self.repository_root
                        / "docs/testing/ai-evaluation/normalization-parser.v1.json"
                    ).read_bytes()
                ).hexdigest(),
                "canonical_parser_policy_id": "canonical_parser_policy_json_v1",
                "canonical_parser_policy_version": "v1",
                "canonical_parser_policy_hash": children["canonical_parser_policy_json_v1"],
                "normalization_hashing_policy_id": "normalization_hashing_policy_v1",
                "normalization_hashing_policy_version": "v1",
                "normalization_hashing_policy_hash": children["normalization_hashing_policy_v1"],
                "parser_implementation_id": "trustai_normalization_parser_v1",
                "parser_implementation_version": "v1",
                "parser_implementation_hash": hashlib.sha256(
                    (
                        self.repository_root
                        / "backend/app/services/normalization_parser.py"
                    ).read_bytes()
                ).hexdigest(),
                "strict_json_policy_id": "strict_json_policy_v1",
                "strict_json_policy_version": "v1",
                "strict_json_policy_hash": children["strict_json_policy_v1"],
                "semantic_numeric_domain_policy_id": "semantic_numeric_domain_policy_v1",
                "semantic_numeric_domain_policy_version": "v1",
                "semantic_numeric_domain_policy_hash": children[
                    "semantic_numeric_domain_policy_v1"
                ],
                "numeric_policy_execution_conformance_status": "independent_reference_passed",
                "adapter_id": request.call.adapter_id,
                "adapter_version": "v1",
                "adapter_hash": adapter_hash,
                "response_transport_mode": "non_streaming_http",
                "canonical_raw_byte_availability": raw_response is not None,
                "raw_response_unavailable_reason_if_applicable": (
                    None if raw_response is not None else "transport_bytes_unavailable"
                ),
                "content_decoding_responsibility": "http_transport_before_raw_capture",
                "stream_framing_policy_id_if_applicable": None,
                "stream_framing_policy_hash_if_applicable": None,
                "native_object_lossless_equivalence_evidence_if_applicable": None,
                "normalization_actions": [
                    {
                        "ordinal": action.ordinal,
                        "action": action.action,
                        "policy_id": action.policy_id,
                        "policy_version": action.policy_version,
                        "policy_hash": action.policy_hash,
                        "adapter_id_if_applicable": action.adapter_id_if_applicable,
                        "adapter_version_if_applicable": action.adapter_version_if_applicable,
                        "adapter_hash_if_applicable": action.adapter_hash_if_applicable,
                        "input_hash": action.input_hash,
                        "output_hash": action.output_hash,
                        "trace_references": list(action.trace_references),
                        "deterministic_parameters": [
                            list(item) for item in action.deterministic_parameters
                        ],
                        "action_result": action.action_result,
                    }
                    for action in normalization_actions
                ],
                "normalized_presemantic_state": state.normalized_presemantic_state,
                "highest_completed_stage": state.highest_completed_stage,
                "normalization_disposition": state.normalization_disposition,
                "terminal_outcome": state.terminal_outcome,
                "attempt_outcome": state.attempt_outcome,
                "validator_states": [
                    {
                        "validator_id": item.validator_id,
                        "applicability": item.applicability,
                        "state": item.state,
                    }
                    for item in state.validator_states
                ],
                "attempt_state_coherence": "passed",
                "refusal_state": state.refusal_state,
                "failure_category": state.failure_category,
                "numeric_domain_reason_if_applicable": None,
                "stage_event_ledger_hash_or_safe_reference": _hash(
                    [
                        {
                            "ordinal": item.event_ordinal,
                            "type": item.event_type,
                            "id": item.stage_or_event_id,
                            "result": item.result,
                        }
                        for item in state.ledger.events
                    ]
                ),
                "stage_event_ledger_policy_id": "attempt_stage_event_ledger_v1",
                "stage_event_ledger_policy_version": "v1",
                "stage_event_ledger_policy_hash": children["attempt_stage_event_ledger_v1"],
                "compatibility_matrix_id": "attempt_state_compatibility_matrix_v1",
                "compatibility_matrix_version": "v1",
                "compatibility_matrix_hash": children["attempt_state_compatibility_matrix_v1"],
                "validator_applicability_policy_id": "workload_validator_applicability_v1",
                "validator_applicability_policy_version": "v1",
                "validator_applicability_policy_hash": children[
                    "workload_validator_applicability_v1"
                ],
                "first_terminal_condition_reducer_id": "first_terminal_condition_reducer_v1",
                "first_terminal_condition_reducer_version": "v1",
                "first_terminal_condition_reducer_hash": children[
                    "first_terminal_condition_reducer_v1"
                ],
                "wire_response_hash_if_available": raw_hash,
                "raw_provider_response_hash": state.raw_provider_response_hash,
                "stream_trace_hash_if_applicable": None,
                "native_structured_object_hash_if_applicable": None,
                "transport_extracted_payload_hash": (
                    adapted.semantic_content_hash if adapted is not None and stage_index >= 2
                    else semantic_hash if stage_index >= 2
                    else None
                ),
                "strict_parsed_semantic_payload_hash": semantic_hash if stage_index >= 3 else None,
                "canonical_validation_candidate_hash": semantic_hash if stage_index >= 4 else None,
                "provider_trace_hash_if_applicable": (
                    raw_hash if state.workload_branch == "search_retrieval" else None
                ),
                "retrieval_trace_hash_if_applicable": (
                    ps1_evidence.canonical_evidence_bundle_hash
                    if state.workload_branch == "search_retrieval" and ps1_evidence is not None
                    else None
                ),
                "canonical_evidence_bundle_hash_if_applicable": (
                    ps1_evidence.canonical_evidence_bundle_hash
                    if ps1_evidence is not None
                    else None
                ),
                "final_semantic_payload_hash_if_applicable": (
                    state.accepted_artifact_hash
                    if state.workload_branch != "search_retrieval"
                    else None
                ),
            }
        )
        bindings = [
            {"policy_id": i, "policy_version": "v1", "policy_hash": children[i]}
            for i in (
                "canonical_parser_policy_json_v1",
                "normalization_hashing_policy_v1",
                "strict_json_policy_v1",
                "semantic_numeric_domain_policy_v1",
                "attempt_stage_event_ledger_v1",
                "attempt_state_compatibility_matrix_v1",
                "workload_validator_applicability_v1",
                "first_terminal_condition_reducer_v1",
            )
        ]
        bindings.append(
            {
                "policy_id": PRIVACY_POLICY_ID,
                "policy_version": PRIVACY_POLICY_VERSION,
                "policy_hash": PRIVACY_POLICY_HASH,
            }
        )
        for policy_id in _prompt_schema_ids(state.workload_branch):
            bindings.append(
                {
                    "policy_id": policy_id,
                    "policy_version": "v1",
                    "policy_hash": self._prompt_hashes.get(policy_id)
                    or self._schema_hashes[policy_id],
                }
            )
        if request.call.fixture_id == "PS1":
            bindings.extend(
                (
                    {
                        "policy_id": "source_classification_policy_v1",
                        "policy_version": "v1",
                        "policy_hash": SOURCE_CLASSIFICATION_POLICY_HASH,
                    },
                    {
                        "policy_id": (
                            "url_security_operational_origin_rule_registry_v1"
                        ),
                        "policy_version": "v1",
                        "policy_hash": ORIGIN_RULE_REGISTRY_HASH,
                    },
                    {
                        "policy_id": "retrieval_objective_support_policy_v1",
                        "policy_version": "v1",
                        "policy_hash": OBJECTIVE_SUPPORT_POLICY_HASH,
                    },
                    {
                        "policy_id": (
                            "deterministic_trace_backed_evidence_extractor_and_matcher_v1"
                        ),
                        "policy_version": "v1",
                        "policy_hash": EVIDENCE_EXTRACTOR_POLICY_HASH,
                    },
                )
            )
        values["applied_policy_bindings"] = bindings
        return values

    def _pilot_envelope(
        self,
        *,
        request: NativeProviderRequest,
        key: PilotAttemptKey,
        state: Any,
        audit: Mapping[str, Any],
        provider_data: Any,
        attempt_number: int,
        retry_reason: str | None,
        search_tool_data: SearchToolProjections | None,
    ) -> dict[str, Any]:
        call = request.call
        metadata = provider_data.ordinary.safe_transport_metadata.as_dict()
        values = {field: None for field in self._result_contract.pilot_envelope_fields}
        values.update(
            {
                "evaluation_id": key.evaluation_id,
                "experiment_version": self.experiment_version,
                "experiment_phase": "pilot",
                "repository_harness_commit_sha": self.repository_harness_commit_sha,
                "harness_version": "v1",
                "fixture_manifest_version": "v1",
                "fixture_id": key.fixture_id,
                "fixture_version": "v1",
                "rubric_version": "v1",
                "scoring_rule_version": "v1",
                "truth_sheet_version": None,
                "visual_asset_set_version": (
                    self._visual_assets.asset_set_version
                    if call.workload_stage == "visual_inspection"
                    else None
                ),
                "provider": key.provider,
                "model": key.model,
                "model_version_or_snapshot": key.model,
                "provider_request_id": None,
                "api_endpoint": call.api_family.replace(" ", "_"),
                "api_version": "v1",
                "component_topology": key.component_topology,
                "workload": key.workload,
                "prompt_template_version": "v1",
                "prompt_hash": _hash(list(call.prompt_hashes)),
                "output_schema_version": "v1",
                "request_configuration": (
                    request.request_configuration_selection.configuration.safe_record_projection()
                    if request.request_configuration_selection is not None
                    else None
                ),
                "run_number": key.run_number,
                "attempt_number": attempt_number,
                "retry_reason": retry_reason,
                "input_hashes": {"provider_native_request": request.payload_hash},
                "started_at": metadata["started_at"],
                "completed_at": metadata["completed_at"],
                "http_or_result_status": metadata["http_or_result_status"],
                "finish_or_stop_reason": metadata["finish_or_stop_reason"],
                "refusal_state": state.refusal_state,
                "latency_measurements": metadata["latency_measurements"],
                "schema_pass": next(
                    item.state == "passed"
                    for item in state.validator_states
                    if item.validator_id == "canonical_schema_validation"
                ),
                "raw_response_hash": audit["raw_provider_response_hash"],
                "normalized_output_hash": audit["final_semantic_payload_hash_if_applicable"],
                "normalization_parser_version": audit["parser_implementation_version"],
                "normalization_performed": False,
                "normalization_actions": audit["normalization_actions"],
                "search_query_list": None,
                "search_and_tool_calls": None,
                "source_urls": None,
                "source_retrieval_timestamps": None,
                "claim_to_source_mapping": None,
                "visual_asset_hashes": (
                    list(request.visual_asset_hashes)
                    if call.workload_stage == "visual_inspection"
                    else None
                ),
                "input_token_usage": metadata.get("input_token_usage"),
                "output_token_usage": metadata.get("output_token_usage"),
                "reasoning_usage_if_exposed": metadata.get("reasoning_usage_if_exposed"),
                "image_usage_if_exposed": metadata.get("image_usage_if_exposed"),
                "rate_limit_and_service_metadata_if_exposed": None,
                "estimated_cost": None,
                "retry_count": attempt_number - 1,
                "safe_failure_code": state.failure_category,
                "notes_and_anomalies": [],
            }
        )
        if search_tool_data is not None:
            safe = search_tool_data.ordinary.as_dict()
            values.update(
                {
                    "search_query_list": [
                        item["query_id"]
                        for item in safe["operations"]
                        if item["query_id"] is not None
                    ],
                    "search_and_tool_calls": safe,
                    "source_urls": [
                        item["public_safe_canonical_url"] for item in safe["sources"]
                    ],
                    "source_retrieval_timestamps": [
                        {
                            "source_id": item["source_id"],
                            "retrieved_at": item["retrieved_at"],
                        }
                        for item in safe["sources"]
                    ],
                    "claim_to_source_mapping": safe["claim_evidence_source_links"],
                }
            )
        return values


def build_provider_free_pilot_runner(
    *,
    repository_root: str | Path,
    repository_harness_commit_sha: str,
) -> ProviderFreePilotRunner:
    """Bind the frozen provider-free contracts without reading credentials."""
    root = Path(repository_root).resolve()
    artifacts_root = root / "docs" / "testing" / "ai-evaluation"
    if (
        type(repository_harness_commit_sha) is not str
        or len(repository_harness_commit_sha) != 40
        or any(character not in "0123456789abcdef" for character in repository_harness_commit_sha)
    ):
        raise _fail("repository_harness_commit_sha")
    artifact_names = {
        "experiment": "experiment.v1.json",
        "pilot_fixtures": "pilot-fixtures.v1.json",
        "prompts": "prompt-templates.v1.json",
        "schemas": "output-schemas.v1.json",
        "parser": "normalization-parser.v1.json",
        "mappings": "provider-role-mappings.v1.json",
        "adapters": "provider-adapters.v1.json",
        "request_configurations": "request-configurations.v1.json",
        "search_authority": "search-authority.v2.json",
        "visual_context": "visual-context.v1.json",
    }
    artifacts = {
        key: load_strict_contract_json(artifacts_root / filename)
        for key, filename in artifact_names.items()
    }
    parser = load_strict_normalization_spec(artifacts_root / "normalization-parser.v1.json")
    artifacts["parser"] = parser
    prompt_identity = verify_prompt_template_artifact(artifacts["prompts"])
    schema_identity = verify_output_schema_artifact(artifacts["schemas"])
    parser_identity = verify_normalization_parser_artifact(parser)
    authority = bind_search_authority_v2(
        artifacts["search_authority"],
        artifacts["prompts"],
        parser,
    )
    mappings = bind_provider_role_mappings(artifacts["mappings"], authority)
    adapters = bind_provider_adapters(artifacts["adapters"], mappings)
    configurations = bind_pilot_request_configurations(
        artifacts["request_configurations"],
        mappings,
        adapters,
    )
    schema_registry = CanonicalOutputSchemaRegistry.from_artifact(artifacts["schemas"])
    retry_policy = load_retry_policy()
    budget = verify_pilot_budget_control()
    region = verify_pilot_region_binding()
    result_contract = verify_result_record_contract()
    visual_context = bind_visual_context_contract(
        artifacts["visual_context"],
        artifacts["pilot_fixtures"],
        artifacts["prompts"],
    )
    visual_assets = verify_pilot_visual_assets()
    verify_url_discovery_contract()
    preflight = assess_provider_neutral_pilot_preflight()
    if (
        preflight.status != "pilot_preflight_ready_awaiting_live_gates"
        or not preflight.provider_free_common_preflight_ready
        or preflight.provider_free_technical_blockers
        or preflight.authoritative_execution_state != "blocked_pre_execution"
        or preflight.currently_eligible_provider_calls != 22
        or preflight.maximum_currently_eligible_physical_attempts != 44
        or budget.approved_ceiling_usd != Decimal("5.00")
        or region.policy_hash != REGION_BINDING_HASH
        or retry_policy.semantic_hash != _RETRY_POLICY_HASH
    ):
        raise _fail("provider_neutral_preflight")
    plan = _build_plan(
        configurations=configurations,
        mappings=mappings,
        prompt_hashes=dict(prompt_identity.child_hashes),
        schema_hashes=dict(schema_identity.child_hashes),
        result_policy_id=result_contract.policy_id,
        result_policy_hash=result_contract.policy_hash,
        budget_policy_id=budget.artifact_id,
        budget_policy_hash=budget.semantic_hash,
    )
    return ProviderFreePilotRunner(
        repository_root=root,
        repository_harness_commit_sha=repository_harness_commit_sha,
        artifacts=artifacts,
        mappings=mappings,
        adapters=adapters,
        configurations=configurations,
        schema_registry=schema_registry,
        retry_policy=retry_policy,
        visual_context=visual_context,
        visual_assets=visual_assets,
        prompt_hashes=dict(prompt_identity.child_hashes),
        schema_hashes=dict(schema_identity.child_hashes),
        parser_identity=parser_identity,
        result_contract=result_contract,
        plan=plan,
        budget_control_hash=budget.semantic_hash,
    )


def _build_plan(
    *,
    configurations: PilotRequestConfigurationSet,
    mappings: ProviderRoleMappingSet,
    prompt_hashes: Mapping[str, str],
    schema_hashes: Mapping[str, str],
    result_policy_id: str,
    result_policy_hash: str,
    budget_policy_id: str,
    budget_policy_hash: str,
) -> PilotPlan:
    logical_runs: list[PlannedLogicalRun] = []
    calls: list[PlannedProviderCall] = []

    def add_call(
        *,
        candidate_id: str,
        fixture_id: str,
        stage: str,
        logical_run_id: str,
    ) -> PlannedProviderCall:
        if stage == "provider_native_url_discovery":
            discovery = select_url_discovery_configuration(candidate_id)
            provider = discovery.provider
            model = discovery.model
            api_family = discovery.api_family
            topology = "two_call_search_retrieval"
            config_id = discovery.configuration_id
            config_hash = discovery.semantic_hash
            prompt_ids = ("search_retrieval_v1",)
            schema_id = None
            schema_hash = None
            mapping_id = discovery.role_mapping_id
            mapping_hash = discovery.role_mapping_hash
            adapter_id = discovery.adapter_id
            adapter_hash = discovery.adapter_hash
        else:
            selection = select_pilot_request_configuration(
                configurations,
                candidate_id=candidate_id,
                workload_stage=stage,
            )
            config = selection.configuration
            provider = config.provider
            model = config.model
            api_family = config.api_family
            topology = config.topology_id
            config_id = config.configuration_id
            config_hash = config.semantic_hash
            prompt_ids = {
                "text_analysis": ("text_system_v1", "text_input_v1"),
                "visual_inspection": ("visual_system_v1", "visual_context_v1"),
                "search_synthesis": ("search_synthesis_v1",),
            }[stage]
            schema_id = config.output_schema_id
            schema_hash = config.output_schema_hash
            mapping_id = config.role_mapping_id
            mapping_hash = config.role_mapping_hash
            adapter_id = config.adapter_id
            adapter_hash = config.adapter_hash
        call = PlannedProviderCall(
            call_id=f"call-{len(calls) + 1:04d}",
            logical_run_id=logical_run_id,
            evaluation_id=_EVALUATION_ID,
            experiment_version=_EXPERIMENT_VERSION,
            fixture_id=fixture_id,
            fixture_version="v1",
            candidate_id=candidate_id,
            provider=provider,
            model=model,
            api_family=api_family,
            workload_stage=stage,
            topology_id=topology,
            request_configuration_id=config_id,
            request_configuration_hash=config_hash,
            prompt_ids=prompt_ids,
            prompt_hashes=tuple(prompt_hashes[item] for item in prompt_ids),
            schema_id=schema_id,
            schema_hash=schema_hash,
            role_mapping_id=mapping_id,
            role_mapping_hash=mapping_hash,
            adapter_id=adapter_id,
            adapter_hash=adapter_hash,
            retry_policy_id="retry_policy_v1",
            retry_policy_hash=_RETRY_POLICY_HASH,
            resource_policy_id=_RESOURCE_POLICY_ID,
            resource_policy_hash=_RESOURCE_POLICY_HASH,
            privacy_policy_id=PRIVACY_POLICY_ID,
            privacy_policy_hash=PRIVACY_POLICY_HASH,
            budget_policy_id=budget_policy_id,
            budget_policy_hash=budget_policy_hash,
            region_binding_id="pilot_region_binding_v1",
            region_binding_hash=REGION_BINDING_HASH,
            result_record_policy_id=result_policy_id,
            result_record_policy_hash=result_policy_hash,
            run_number=1,
            timeout_seconds=120,
            maximum_physical_attempts=2,
        )
        calls.append(call)
        return call

    candidates = (
        "openai_unified_premium_v1",
        "openai_unified_balanced_v1",
        "gemini_unified_v1",
        "groq_split_v1",
        "baseline_current_text_v1",
    )
    for candidate in candidates:
        for fixture_id in ("PT1", "PT2"):
            logical_id = f"{candidate}-{fixture_id}"
            call = add_call(
                candidate_id=candidate,
                fixture_id=fixture_id,
                stage="text_analysis",
                logical_run_id=logical_id,
            )
            logical_runs.append(PlannedLogicalRun(logical_id, fixture_id, candidate, (call,)))
    for candidate in candidates[:-1]:
        for fixture_id in ("PV1", "PV2"):
            logical_id = f"{candidate}-{fixture_id}"
            call = add_call(
                candidate_id=candidate,
                fixture_id=fixture_id,
                stage="visual_inspection",
                logical_run_id=logical_id,
            )
            logical_runs.append(PlannedLogicalRun(logical_id, fixture_id, candidate, (call,)))
    for candidate in candidates[:2]:
        logical_id = f"{candidate}-PS1"
        discovery = add_call(
            candidate_id=candidate,
            fixture_id="PS1",
            stage="provider_native_url_discovery",
            logical_run_id=logical_id,
        )
        synthesis = add_call(
            candidate_id=candidate,
            fixture_id="PS1",
            stage="search_synthesis",
            logical_run_id=logical_id,
        )
        logical_runs.append(
            PlannedLogicalRun(logical_id, "PS1", candidate, (discovery, synthesis))
        )
    logical_runs.append(PlannedLogicalRun("provider-free-PF1", "PF1", None, (), True))
    by_workload = {
        "text_analysis": sum(call.workload_stage == "text_analysis" for call in calls),
        "visual_inspection": sum(call.workload_stage == "visual_inspection" for call in calls),
        "openai_url_discovery": sum(
            call.workload_stage == "provider_native_url_discovery" for call in calls
        ),
        "openai_search_synthesis": sum(call.workload_stage == "search_synthesis" for call in calls),
    }
    by_provider = {
        provider: sum(call.provider == provider for call in calls)
        for provider in CREDENTIAL_VARIABLE_BY_PROVIDER
    }
    if by_workload != {
        "text_analysis": 10,
        "visual_inspection": 8,
        "openai_url_discovery": 2,
        "openai_search_synthesis": 2,
    } or len(calls) != 22:
        raise _fail("pilot_plan")
    return PilotPlan(
        logical_runs=tuple(logical_runs),
        provider_calls=tuple(calls),
        maximum_real_physical_attempts=44,
        pf1_no_call_count=1,
        breakdown_by_workload=MappingProxyType(by_workload),
        breakdown_by_provider=MappingProxyType(by_provider),
    )


def _template_record(prompt_artifact: Mapping[str, Any], template_id: str) -> dict[str, Any]:
    matches = tuple(
        item for item in prompt_artifact["templates"]
        if item.get("template_id") == template_id
    )
    if len(matches) != 1:
        raise _fail("prompt_identity")
    return matches[0]


def _template_text(prompt_artifact: Mapping[str, Any], template_id: str) -> str:
    template = _template_record(prompt_artifact, template_id)
    content = template.get("canonical_content")
    if type(content) is not list or any(type(item) is not str for item in content):
        raise _fail("prompt_content")
    return "\n".join(content)


def _render_template(
    prompt_artifact: Mapping[str, Any],
    template_id: str,
    values: Mapping[str, Any],
) -> str:
    template = _template_record(prompt_artifact, template_id)
    allowlist = tuple(template.get("placeholder_allowlist", ()))
    if set(values) != set(allowlist):
        raise _fail("prompt_rendering")
    rendered = _template_text(prompt_artifact, template_id)
    for name in allowlist:
        rendered = rendered.replace(
            "{{" + name + "}}",
            _canonical(values[name]).decode("utf-8"),
        )
    if "{{" in rendered or "}}" in rendered:
        raise _fail("prompt_rendering")
    return rendered


def _schema_document(schema_artifact: Mapping[str, Any], schema_id: str) -> dict[str, Any]:
    matches = tuple(
        item for item in schema_artifact["schemas"] if item.get("schema_id") == schema_id
    )
    if len(matches) != 1:
        raise _fail("schema_identity")
    return _json_copy(matches[0]["schema"])


def _render_search_target(fixture: Mapping[str, Any]) -> str:
    return _canonical(
        {
            "currency": fixture["currency"],
            "exact_variant_or_sku": fixture["exact_variant"],
            "product_identity": fixture["product_identity"],
            "region": fixture["region"],
        }
    ).decode("utf-8")


def _synthetic_text_semantic(fixture: Mapping[str, Any]) -> dict[str, Any]:
    high = fixture.get("id") == "PT2"
    return {
        "summary": (
            "Irreversible prepayment is a material supplied risk signal."
            if high
            else "No material risk signal is present in the supplied listing."
        ),
        "risk_level": "high" if high else "low",
        "risk_indicators": (
            [
                {
                    "category": "irreversible_payment",
                    "severity": "high",
                    "explanation": "The listing requires cryptocurrency before inspection.",
                }
            ]
            if high
            else []
        ),
        "price_assessment": "Current pricing was not verified.",
        "price_plausibility": "plausible",
        "seller_questions": ["Can the item be inspected before payment?"],
        "recommendation": "avoid" if high else "buy",
    }


def _synthetic_visual_semantic(fixture: Mapping[str, Any]) -> dict[str, Any]:
    if fixture.get("id") == "PV2":
        observation = "A visible dent appears on the blue storage case."
        category = "visible_damage"
    else:
        observation = "The calculator and DEMO UNIT label are clearly visible."
        category = "visible_detail"
    return {
        "findings": [
            {
                "category": category,
                "observation": observation,
                "photo_numbers": [1],
            }
        ]
    }


def _synthetic_search_semantic(evidence: Ps1AssemblyResult) -> dict[str, Any]:
    bundle = evidence.canonical_bundle
    source = bundle["sources"][0]
    source_projection = {
        key: source[key]
        for key in ("source_id", "name", "url", "source_type", "retrieved_at")
    }
    return {
        "identity_resolution": {
            "status": "resolved",
            "current_status": "current",
            "resolved_product_identity": "Logitech MX Master 3S Graphite",
            "source_ids": [source["source_id"]],
        },
        "comparison_status": "established",
        "claims": [
            {
                "claim_id": "claim-1",
                "claim_type": "specification",
                "statement": "The Graphite right-handed package includes a Logi Bolt receiver.",
                "source_ids": [source["source_id"]],
            }
        ],
        "price_evidence": [],
        "sources": [source_projection],
        "uncertainties": [],
        "conflicts": [],
    }


def _synthetic_discovery_url(call: PlannedProviderCall):
    return record_ps1_discovery_url(
        candidate_id=call.candidate_id,
        provider=call.provider,
        discovery_ordinal=1,
        exact_url=_PS1_URL,
    )


def _synthetic_provider_envelope(request: NativeProviderRequest) -> bytes:
    if request.call.workload_stage == "provider_native_url_discovery":
        return _synthetic_discovery_envelope((_PS1_URL,))
    semantic_text = request.synthetic_semantic_json.decode("utf-8")
    provider = request.call.provider
    if provider == "OpenAI":
        return _canonical(
            {
                "id": "synthetic-provider-id",
                "model": request.call.model,
                "status": "completed",
                "error": None,
                "incomplete_details": None,
                "output": [
                    {"type": "reasoning", "summary": []},
                    {
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": semantic_text, "annotations": []}
                        ],
                    },
                ],
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 7,
                    "output_tokens_details": {"reasoning_tokens": 3},
                    "total_tokens": 19,
                },
            }
        )
    if provider == "Google Gemini":
        return _canonical(
            {
                "id": "synthetic-provider-id",
                "model": request.call.model,
                "status": "completed",
                "errors": None,
                "steps": [
                    {"type": "thought", "summary": []},
                    {"type": "model_output", "content": [{"type": "text", "text": semantic_text}]},
                ],
                "usage": {
                    "input_tokens_by_modality": [
                        {"modality": "text", "tokens": 10},
                        {"modality": "image", "tokens": 258},
                    ],
                    "total_input_tokens": 268,
                    "total_output_tokens": 20,
                    "total_thought_tokens": 4,
                    "total_tokens": 292,
                },
            }
        )
    if provider == "Groq":
        return _canonical(
            {
                "id": "synthetic-provider-id",
                "model": request.call.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": semantic_text},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 18,
                    "completion_tokens": 9,
                    "total_tokens": 27,
                },
            }
        )
    raise _fail("provider")


def _synthetic_discovery_envelope(urls: tuple[str, ...]) -> bytes:
    return _canonical(
        {
            "id": "synthetic-discovery-response",
            "status": "completed",
            "output": [
                {
                    "type": "web_search_call",
                    "status": "completed",
                    "action": {
                        "type": "search",
                        "sources": [{"url": url} for url in urls],
                    },
                }
            ],
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
            },
        }
    )


def _capture(payload: bytes) -> RawResponseCapture:
    accumulator = CanonicalRawResponseAccumulator("non_streaming_http")
    accumulator.append(payload)
    return accumulator.finish_response()


def _branch_for_call(call: PlannedProviderCall) -> str:
    return {
        "text_analysis": "text_final",
        "visual_inspection": "visual_final",
        "provider_native_url_discovery": "search_retrieval",
        "search_synthesis": "search_synthesis_final",
    }[call.workload_stage]


def _accepted_state(branch: str, *, raw_hash: str, accepted_hash: str):
    events = [
        StageEvent(
            event_ordinal=index,
            event_type="major_stage",
            stage_or_event_id=stage,
            applicability="applicable",
            result="completed",
        )
        for index, stage in enumerate(HIGHEST_COMPLETED_STAGES[1:], start=1)
    ]
    events.append(
        StageEvent(
            event_ordinal=len(events) + 1,
            event_type="acceptance_finalization",
            stage_or_event_id="all_required_processing_and_finalization_completed",
            applicability="applicable",
            result="completed",
            policy_identity_if_applicable=_ATTEMPT_POLICY_IDENTITY,
        )
    )
    return derive_attempt_state(
        workload_branch=branch,
        normalized_presemantic_state="ordinary_semantic_path",
        ledger=AttemptStageEventLedger(tuple(events)),
        normalization_actions=(),
        raw_provider_response_hash=raw_hash,
        accepted_artifact_hash=accepted_hash,
    )


def _failure_state(
    branch: str,
    *,
    failure_code: str,
    raw_hash: str | None,
    adapter_identity: tuple[str, str, str],
):
    presemantic = {
        "provider_connection_error": "provider_connection_error",
        "provider_timeout": "provider_timeout",
        "http_provider_error": "http_provider_error",
        "provider_native_refusal": "provider_native_refusal",
    }
    events: list[StageEvent] = []
    normalization_actions: tuple[NormalizationActionRecord, ...] = ()
    if raw_hash is not None and failure_code != "provider_connection_error":
        events.append(
            StageEvent(
                event_ordinal=1,
                event_type="major_stage",
                stage_or_event_id="raw_transport_captured",
                applicability="applicable",
                result="completed",
            )
        )
    if failure_code in presemantic:
        state_name = presemantic[failure_code]
        events.append(
            StageEvent(
                event_ordinal=len(events) + 1,
                event_type="normalized_presemantic_state",
                stage_or_event_id=state_name,
                applicability="applicable",
                result="failed",
                policy_identity_if_applicable=_ATTEMPT_POLICY_IDENTITY,
                adapter_identity_if_applicable=adapter_identity,
            )
        )
        normalized = state_name
    else:
        normalized = "ordinary_semantic_path"
        if failure_code == "failed_transport_extraction":
            event_id, event_type, completed = (
                "transport_extraction_failed",
                "normalization_action",
                (),
            )
            normalization_actions = (
                NormalizationActionRecord(
                    ordinal=1,
                    action="extract_native_structured_object",
                    policy_id=adapter_identity[0],
                    policy_version=adapter_identity[1],
                    policy_hash=adapter_identity[2],
                    adapter_id_if_applicable=adapter_identity[0],
                    adapter_version_if_applicable=adapter_identity[1],
                    adapter_hash_if_applicable=adapter_identity[2],
                    input_hash=raw_hash or hashlib.sha256(b"").hexdigest(),
                    output_hash=None,
                    trace_references=(),
                    deterministic_parameters=(),
                    action_result="failed",
                ),
            )
        elif failure_code == "failed_canonical_validation":
            event_id, event_type, completed = (
                "canonical_schema_validation_failed",
                "validator",
                (
                    "semantic_representation_extracted",
                    "strict_semantic_payload_parsed",
                    "canonical_candidate_constructed",
                ),
            )
        elif failure_code == "failed_strict_parse":
            event_id, event_type, completed = (
                "strict_json_syntax_failed",
                "normalization_action",
                ("semantic_representation_extracted",),
            )
        elif failure_code == "failed_trace_validation":
            event_id, event_type, completed = (
                "search_cross_reference_validator_failed",
                "validator",
                (
                    "semantic_representation_extracted",
                    "strict_semantic_payload_parsed",
                    "canonical_candidate_constructed",
                    "canonical_schema_validated",
                ),
            )
        elif failure_code == "failed_cross_field_validation":
            event_id = (
                "visual_photo_reference_validator_failed"
                if branch == "visual_final"
                else "text_cross_field_validator_failed"
            )
            event_type = "validator"
            completed = (
                "semantic_representation_extracted",
                "strict_semantic_payload_parsed",
                "canonical_candidate_constructed",
                "canonical_schema_validated",
            )
        else:
            event_id, event_type, completed = (
                "evidence_policy_validation_failed",
                "validator",
                (
                    "semantic_representation_extracted",
                    "strict_semantic_payload_parsed",
                    "canonical_candidate_constructed",
                    "canonical_schema_validated",
                ),
            )
        already = {item.stage_or_event_id for item in events}
        for stage in completed:
            if stage in already:
                continue
            events.append(
                StageEvent(
                    event_ordinal=len(events) + 1,
                    event_type="major_stage",
                    stage_or_event_id=stage,
                    applicability="applicable",
                    result="completed",
                )
            )
        events.append(
            StageEvent(
                event_ordinal=len(events) + 1,
                event_type=event_type,
                stage_or_event_id=event_id,
                applicability="applicable",
                result="failed",
                policy_identity_if_applicable=_ATTEMPT_POLICY_IDENTITY,
                adapter_identity_if_applicable=(
                    adapter_identity if event_type == "normalization_action" else None
                ),
            )
        )
    return (
        derive_attempt_state(
            workload_branch=branch,
            normalized_presemantic_state=normalized,
            ledger=AttemptStageEventLedger(tuple(events)),
            normalization_actions=normalization_actions,
            raw_provider_response_hash=raw_hash,
            accepted_artifact_hash=None,
        ),
        normalization_actions,
    )


def _map_transport_result(
    response: TransportResponse,
    deadline: AttemptDeadline,
) -> tuple[str, str | None] | None:
    if not isinstance(response, TransportResponse):
        raise _fail("transport_response")
    if response.failure_signal == "connection":
        return "provider_connection_error", "transient_provider_connection_error"
    if deadline.expired(response.elapsed_seconds):
        return "provider_timeout", "provider_attempt_timeout"
    if response.failure_signal == "rate_limit":
        return "http_provider_error", "provider_rate_limited"
    if response.failure_signal == "service_unavailable":
        return "http_provider_error", "provider_service_unavailable"
    if response.failure_signal == "http_failure":
        return "http_provider_error", None
    if response.failure_signal == "malformed":
        return "failed_transport_extraction", None
    if response.failure_signal == "refusal":
        return "provider_native_refusal", None
    return None


def _safe_transport_metadata(
    call: PlannedProviderCall,
    *,
    state: Any,
    attempt_number: int,
    adapted: AdaptedProviderResponse | None,
) -> dict[str, Any]:
    usage = adapted.usage if adapted is not None else None
    metadata = {
        "provider": call.provider,
        "model": call.model,
        "model_version_or_snapshot": call.model,
        "http_or_result_status": {
            "kind": "terminal_outcome",
            "value": state.terminal_outcome,
        },
        "started_at": _FIXED_STARTED,
        "completed_at": _FIXED_COMPLETED,
        "latency_measurements": {
            "end_to_end_latency_ms": 1000,
            "provider_latency_ms": 1000,
        },
        "finish_or_stop_reason": state.terminal_outcome,
        "attempt_number": attempt_number,
        "retry_count": attempt_number - 1,
    }
    if usage is not None:
        metadata.update(
            {
                "input_token_usage": usage.input_token_usage,
                "output_token_usage": usage.output_token_usage,
            }
        )
        if usage.reasoning_usage_if_exposed is not None:
            metadata["reasoning_usage_if_exposed"] = usage.reasoning_usage_if_exposed
        if usage.image_usage_if_exposed is not None:
            metadata["image_usage_if_exposed"] = usage.image_usage_if_exposed
    return metadata


def _prompt_schema_ids(branch: str) -> tuple[str, ...]:
    return {
        "text_final": ("text_system_v1", "text_input_v1", "text_output_schema_v1"),
        "visual_final": ("visual_system_v1", "visual_context_v1", "visual_output_schema_v1"),
        "search_retrieval": ("search_retrieval_v1", "retrieval_evidence_bundle_v1"),
        "search_synthesis_final": ("search_synthesis_v1", "search_output_schema_v1"),
    }[branch]
