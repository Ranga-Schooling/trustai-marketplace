"""One-call Capstone live validation, mechanically separate from the strict pilot.

The module reuses frozen request, adapter, parser, schema, validator, pricing,
credential, and transport primitives.  It does not import or call the strict
pilot's execution authorization, budget-ledger, attempt-record, or completion
APIs.  Artifact loading, request construction, dry-run, authorization
validation, and result inspection are provider-free.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from app.services.evaluation_contract_identity import (
    load_strict_contract_json,
    load_strict_normalization_spec,
)
from app.services.evaluation_live_cost import (
    LiveCostBindingError,
    calculate_live_success_cost,
)
from app.services.evaluation_live_transport import (
    ConcreteLivePilotTransport,
    LazyEnvironmentCredentialResolver,
)
from app.services.evaluation_openai_token_count import (
    calculate_call_0003_reservation,
)
from app.services.evaluation_pilot_runner import (
    NativeProviderRequest,
    PilotTransport,
    TransportResponse,
    build_provider_free_pilot_runner,
)
from app.services.evaluation_post_schema_validation import (
    validate_text_post_schema_candidate,
)
from app.services.evaluation_provider_adapters import (
    ProviderAdapterResponseError,
    adapt_provider_response,
    bind_provider_adapters,
)
from app.services.evaluation_provider_role_mappings import (
    bind_provider_role_mappings,
)
from app.services.evaluation_retry_policy import AttemptDeadline
from app.services.evaluation_resource_limits import ResourceLimitExceededError
from app.services.evaluation_schema_validation import (
    CanonicalOutputSchemaRegistry,
    CanonicalSchemaValidationError,
    SchemaContractError,
)
from app.services.evaluation_search_authority import bind_search_authority_v2
from app.services.evaluation_transport_capture import (
    CanonicalRawResponseAccumulator,
    TransportCaptureStateError,
)
from app.services.evaluation_validators import DeterministicValidationError
from app.services.normalization_parser import (
    DuplicateJsonKeyError,
    NumericDomainError,
    StrictJsonPayloadError,
    normalize_semantic_json,
)


CAPSTONE_LIVE_VALIDATION_STATUS = (
    "CAPSTONE_LIVE_VALIDATION_V2_READY_AWAITING_USER"
)
_CONTRACT_FILE = "capstone-live-validation.v2.json"
_CONTRACT_HASH = "48831c6dfafcdd00ab7e8a525d448574526ffefbfbf9c6d1bf9c105299af13be"
_EXECUTION_CLASS = "capstone_live_validation"
_CASE_ID = "capval-openai-terra-pt1-v2"
_PREDECESSOR_CASE_ID = "capval-openai-terra-pt1-v1"
_PREDECESSOR_STATE_DIRECTORY = "capstone-live-validation-v1"
_STATE_DIRECTORY = "capstone-live-validation-v2"
_RESERVATION_FILE = "reservation.json"
_RESULT_FILE = "result.json"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_HEAD = re.compile(r"[0-9a-f]{40}\Z")
_UTC_SECONDS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_AUTHORIZATION_KEYS = {
    "authorization_id",
    "authorization_version",
    "status",
    "execution_class",
    "repository_head",
    "contract_hash",
    "validation_case_id",
    "predecessor_validation_case_id",
    "predecessor_contract_hash",
    "predecessor_reservation_record_hash",
    "predecessor_result_record_hash",
    "predecessor_unresolved_exposure_usd",
    "source_call_id",
    "candidate_id",
    "provider",
    "model",
    "fixture_id",
    "workload_stage",
    "request_configuration_id",
    "request_configuration_hash",
    "request_hash",
    "transport_binding_id",
    "transport_implementation_sha256",
    "runtime_identity",
    "runtime_identity_hash",
    "maximum_provider_calls",
    "retry_count",
    "validation_spend_ceiling_usd",
    "conservative_reservation_usd",
    "validation_spend_committed_before_usd",
    "cumulative_worst_case_validation_exposure_usd",
    "validation_spend_remaining_after_reservation_usd",
    "credential_readiness",
    "provider_control_confirmation",
    "authorized_at_utc",
    "strict_pending_cost_reconciliation_preserved",
    "strict_pilot_execution_authorized",
    "scored_execution_authorized",
    "winner_selection_authorized",
    "production_deployment_authorized",
    "semantic_hash",
}
_RUNTIME_IDENTITY_KEYS = {
    "python_executable",
    "python_implementation",
    "python_version",
    "http_client_package",
    "http_client_version",
    "http_client_requirement",
}


class CapstoneLiveValidationError(ValueError):
    """A Capstone validation invariant failed without creating authority."""


def _fail(code: str) -> CapstoneLiveValidationError:
    return CapstoneLiveValidationError(code)


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


def _semantic_hash(document: Mapping[str, Any], field: str) -> str:
    detached = json.loads(_canonical(document).decode("utf-8"))
    detached[field] = None
    return _hash(detached)


def _artifact_hash(document: Mapping[str, Any]) -> str:
    detached = json.loads(_canonical(document).decode("utf-8"))
    detached["specification_identity"]["semantic_hash"] = None
    return _hash(detached)


def _money(value: Any, *, code: str) -> Decimal:
    if type(value) is not str:
        raise _fail(code)
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise _fail(code) from None
    if (
        not result.is_finite()
        or result < 0
        or format(result, ".8f") != value
    ):
        raise _fail(code)
    return result


def _exact_nonnegative_decimal(value: Any, *, code: str) -> Decimal:
    if type(value) is not str:
        raise _fail(code)
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise _fail(code) from None
    if not result.is_finite() or result < 0 or format(result, "f") != value:
        raise _fail(code)
    return result


def _timestamp(value: Any, *, code: str) -> str:
    if type(value) is not str or _UTC_SECONDS.fullmatch(value) is None:
        raise _fail(code)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        raise _fail(code) from None
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise _fail(code)
    return value


def _now(clock: Callable[[], datetime] | None) -> str:
    value = clock() if clock is not None else datetime.now(UTC)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise _fail("clock")
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_output(repository_root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository_root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _fail("repository_state_unavailable") from exc
    if result.stderr:
        raise _fail("repository_state_unavailable")
    return result.stdout


def _repository_head(repository_root: Path) -> str:
    value = _git_output(repository_root, "rev-parse", "HEAD").strip()
    if _HEAD.fullmatch(value) is None:
        raise _fail("repository_head_unavailable")
    return value


def _require_clean_repository(repository_root: Path) -> None:
    status = _git_output(
        repository_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if status:
        raise _fail("repository_not_clean")


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise _fail("transport_binding") from exc


def _validate_runtime_identity(value: Any) -> dict[str, str]:
    if (
        type(value) is not dict
        or set(value) != _RUNTIME_IDENTITY_KEYS
        or any(type(item) is not str or not item for item in value.values())
        or value.get("http_client_package") != "httpx"
        or value.get("http_client_requirement") != "httpx>=0.27"
        or not Path(value.get("python_executable", "")).is_absolute()
    ):
        raise _fail("runtime_identity")
    return dict(value)


def _runtime_identity(transport: ConcreteLivePilotTransport) -> dict[str, str]:
    if not isinstance(transport, ConcreteLivePilotTransport):
        raise _fail("live_transport")
    return _validate_runtime_identity(transport.validate_runtime())


def _load_immutable_state_record(path: Path, expected_hash: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise _fail("predecessor_state_unavailable")
    if (path.stat().st_mode & 0o777) != 0o600:
        raise _fail("predecessor_state_permissions")
    try:
        record = load_strict_contract_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise _fail("predecessor_state_unavailable") from exc
    if (
        type(record) is not dict
        or record.get("record_hash") != expected_hash
        or _semantic_hash(record, "record_hash") != expected_hash
    ):
        raise _fail("predecessor_state_hash")
    return record


@dataclass(frozen=True, slots=True)
class CapstoneValidationCase:
    case_id: str
    predecessor_case_id: str
    predecessor_result_record_hash: str
    source_call_id: str
    candidate_id: str
    provider: str
    model: str
    api_family: str
    endpoint: str
    fixture_id: str
    workload_stage: str
    request_configuration_id: str
    request_configuration_hash: str
    request_hash: str
    request_body_bytes: int
    schema_id: str
    schema_hash: str
    role_mapping_id: str
    adapter_id: str
    input_tokens: int
    conservative_reservation_usd: str
    cumulative_exposure_usd: str
    remaining_after_reservation_usd: str
    transport_binding_id: str


@dataclass(frozen=True, slots=True)
class CapstoneValidationContract:
    artifact_id: str
    artifact_version: str
    semantic_hash: str
    total_spend_ceiling_usd: str
    maximum_lifetime_provider_calls: int
    cases: tuple[CapstoneValidationCase, ...]
    predecessor_repository_head: str
    predecessor_contract_hash: str
    predecessor_authorization_hash: str
    predecessor_reservation_record_hash: str
    predecessor_result_record_hash: str
    predecessor_request_hash: str
    predecessor_unresolved_exposure_usd: str
    transport_binding_id: str
    transport_implementation_sha256: str
    transport_requirements_sha256: str
    transport_reviewed_base_head: str
    prior_unresolved_exposure_usd: str
    cumulative_exposure_usd: str
    strict_pilot_authorization_api_allowed: bool
    strict_pilot_ledger_interaction_allowed: bool
    strict_pilot_record_creation_allowed: bool
    scored_record_creation_allowed: bool


@dataclass(frozen=True, slots=True)
class CapstoneValidationAuthorization:
    semantic_hash: str
    execution_class: str
    repository_head: str
    case_id: str
    runtime_identity_hash: str
    maximum_provider_calls: int
    retry_count: int
    strict_pilot_execution_authorized: bool
    scored_execution_authorized: bool
    winner_selection_authorized: bool
    production_deployment_authorized: bool


@dataclass(frozen=True, slots=True)
class CapstoneCredentialReference:
    """A runtime-only credential name without strict-pilot readiness semantics."""

    provider: str
    environment_variable_name: str

    def __post_init__(self) -> None:
        if self.provider != "OpenAI" or self.environment_variable_name != "OPENAI_API_KEY":
            raise _fail("credential_reference")


def _load_contract(repository_root: Path) -> CapstoneValidationContract:
    path = repository_root / "docs" / "testing" / "ai-evaluation" / _CONTRACT_FILE
    raw = load_strict_contract_json(path)
    identity = raw.get("specification_identity")
    if (
        type(identity) is not dict
        or identity.get("semantic_hash") != _CONTRACT_HASH
        or _artifact_hash(raw) != _CONTRACT_HASH
        or raw.get("artifact_id") != "capstone_live_validation_v2"
        or raw.get("artifact_version") != "v2"
        or raw.get("status") != "ready_awaiting_explicit_user_authorization"
        or raw.get("execution_class") != _EXECUTION_CLASS
        or raw.get("provider_neutral_frozen_primitives_reused") is not True
    ):
        raise _fail("contract_identity")
    separation = raw.get("strict_separation")
    execution = raw.get("execution_policy")
    spend = raw.get("spend_guard")
    predecessor = raw.get("predecessor_binding")
    transport_binding = raw.get("transport_binding")
    boundary = raw.get("execution_boundary")
    cases = raw.get("cases")
    if (
        type(separation) is not dict
        or any(value is not False for value in separation.values())
        or type(execution) is not dict
        or execution.get("maximum_provider_calls_per_authorization") != 1
        or execution.get("maximum_lifetime_provider_calls") != 1
        or execution.get("automatic_retry_count") != 0
        or execution.get("stop_after_every_provider_call") is not True
        or execution.get("automatic_next_case_allowed") is not False
        or execution.get("explicit_live_confirmation_flag") != "--confirm-live"
        or execution.get("reservation_marker_must_precede_provider_invocation") is not True
        or execution.get("existing_reservation_marker_blocks_execution") is not True
        or execution.get("predecessor_state_validation_required") is not True
        or type(spend) is not dict
        or spend.get("currency") != "USD"
        or spend.get("arithmetic") != "exact_decimal"
        or spend.get("maximum_fraction_digits") != 8
        or type(boundary) is not dict
        or boundary.get("provider_calls_allowed_by_artifact") is not False
        or boundary.get("pilot_calls_allowed") is not False
        or boundary.get("scored_calls_allowed") is not False
        or boundary.get("provider_calls_completed") != 0
        or boundary.get("winner_selected") is not False
        or type(cases) is not list
        or raw.get("case_order") != [_CASE_ID]
        or len(cases) != 1
    ):
        raise _fail("contract_boundary")
    ceiling = spend.get("total_validation_spend_ceiling_usd")
    ceiling_value = _money(ceiling, code="contract_ceiling")
    prior_exposure = _money(
        spend.get("prior_v1_unresolved_exposure_usd"),
        code="predecessor_exposure",
    )
    contract_reservation = _money(
        spend.get("v2_conservative_reservation_usd"),
        code="case_reservation",
    )
    cumulative = _money(
        spend.get("cumulative_worst_case_validation_exposure_usd"),
        code="cumulative_exposure",
    )
    remaining = _money(
        spend.get("remaining_after_v2_reservation_usd"),
        code="case_remaining",
    )
    if (
        spend.get("strict_pilot_budget_is_not_a_source_or_sink") is not True
        or spend.get("unknown_provider_billing_must_not_be_reconciled_to_zero")
        is not True
        or spend.get("predecessor_exposure_release_allowed") is not False
        or spend.get("conservative_reservations_remain_the_capstone_exposure_bound")
        is not True
        or prior_exposure != Decimal("0.05169700")
        or contract_reservation != Decimal("0.05169700")
        or cumulative != prior_exposure + contract_reservation
        or remaining != ceiling_value - cumulative
        or cumulative > ceiling_value
    ):
        raise _fail("spend_guard")
    if (
        type(predecessor) is not dict
        or predecessor.get("validation_case_id") != _PREDECESSOR_CASE_ID
        or predecessor.get("repository_head")
        != "b5f191655e071bb98b74568dc02def32a14f5138"
        or predecessor.get("contract_hash")
        != "389c8e4c693fc9bcff353f9704c104f8ec64ba98de05c3a6d9c0cd7e6eec7564"
        or predecessor.get("authorization_hash")
        != "ed5dd5718b4a60fd208240bf6ea54b9870fa52264bc118b4ba7faf1bc781f051"
        or predecessor.get("reservation_record_hash")
        != "a9d604c30f16ecd4525d533955f9701ea15ed78c35cb7fff703c3e3761cd1bab"
        or predecessor.get("result_record_hash")
        != "554fdf1685a4b766698d9af255fd7921e3500a7390915957831eab440582d24e"
        or predecessor.get("request_hash")
        != "97f8752bb33994a00018a15ff62d79419069397b223cc5f60770def973ebc266"
        or predecessor.get("result_status") != "stopped"
        or predecessor.get("safe_failure_classification") != "connection"
        or predecessor.get("cost_observation_status") != "not_determinable"
        or predecessor.get("observed_validation_cost_usd") is not None
        or _money(
            predecessor.get("unresolved_exposure_usd"),
            code="predecessor_exposure",
        )
        != prior_exposure
        or predecessor.get("live_state_directory")
        != ".capstone-live-validation/capstone-live-validation-v1"
    ):
        raise _fail("predecessor_binding")
    transport_path = repository_root / "backend/app/services/evaluation_live_transport.py"
    requirements_path = repository_root / "backend/requirements.txt"
    if (
        type(transport_binding) is not dict
        or transport_binding.get("binding_id")
        != "capstone_openai_httpx_transport_after_f420af3_v1"
        or transport_binding.get("reviewed_base_repository_head")
        != "f420af3eea0694feb5b0290d1383c2340af43a8f"
        or transport_binding.get("required_correction_commits")
        != [
            "e39967fb3afbbb44f96029b03efbfb19b4f91a12",
            "f420af3eea0694feb5b0290d1383c2340af43a8f",
        ]
        or transport_binding.get("implementation_path")
        != "backend/app/services/evaluation_live_transport.py"
        or transport_binding.get("requirements_path") != "backend/requirements.txt"
        or transport_binding.get("http_client_package") != "httpx"
        or transport_binding.get("http_client_requirement") != "httpx>=0.27"
        or transport_binding.get("same_runtime_identity_required") is not True
        or transport_binding.get("redirects_allowed") is not False
        or transport_binding.get("automatic_retry_count") != 0
        or any(
            transport_binding.get(field) is not True
            for field in (
                "dependency_preflight_required_for_dry_run",
                "dependency_preflight_required_for_authorization",
                "dependency_preflight_required_for_preflight",
                "dependency_preflight_required_for_execution",
            )
        )
        or _file_sha256(transport_path)
        != transport_binding.get("implementation_sha256")
        or _file_sha256(requirements_path)
        != transport_binding.get("requirements_sha256")
    ):
        raise _fail("transport_binding")
    _git_output(
        repository_root,
        "merge-base",
        "--is-ancestor",
        transport_binding["reviewed_base_repository_head"],
        "HEAD",
    )
    for correction_commit in transport_binding["required_correction_commits"]:
        _git_output(
            repository_root,
            "merge-base",
            "--is-ancestor",
            correction_commit,
            "HEAD",
        )
    predecessor_contract = load_strict_contract_json(
        repository_root
        / "docs/testing/ai-evaluation/capstone-live-validation.v1.json"
    )
    if (
        _artifact_hash(predecessor_contract) != predecessor["contract_hash"]
        or predecessor_contract.get("artifact_id") != "capstone_live_validation_v1"
    ):
        raise _fail("predecessor_contract")
    item = cases[0]
    expected_fields = {
        "validation_case_id",
        "predecessor_validation_case_id",
        "predecessor_result_record_hash",
        "source_call_id",
        "candidate_id",
        "provider",
        "model",
        "api_family",
        "endpoint",
        "fixture_id",
        "workload_stage",
        "request_configuration_id",
        "request_configuration_hash",
        "request_hash",
        "request_body_bytes",
        "schema_id",
        "schema_hash",
        "role_mapping_id",
        "adapter_id",
        "observed_input_tokens",
        "conservative_reservation_usd",
        "cumulative_worst_case_validation_exposure_usd",
        "remaining_after_reservation_usd",
        "transport_binding_id",
        "live_eligible",
    }
    if type(item) is not dict or set(item) != expected_fields:
        raise _fail("case_fields")
    reservation = _money(
        item["conservative_reservation_usd"],
        code="case_reservation",
    )
    case_remaining = _money(
        item["remaining_after_reservation_usd"],
        code="case_remaining",
    )
    if (
        item["validation_case_id"] != _CASE_ID
        or item["predecessor_validation_case_id"] != _PREDECESSOR_CASE_ID
        or item["predecessor_result_record_hash"]
        != predecessor["result_record_hash"]
        or item["source_call_id"] != "call-0003"
        or item["candidate_id"] != "openai_unified_balanced_v1"
        or item["provider"] != "OpenAI"
        or item["model"] != "gpt-5.6-terra"
        or item["api_family"] != "Responses API"
        or item["endpoint"] != "https://api.openai.com/v1/responses"
        or item["fixture_id"] != "PT1"
        or item["workload_stage"] != "text_analysis"
        or item["observed_input_tokens"] != 1018
        or item["live_eligible"] is not True
        or calculate_call_0003_reservation(item["observed_input_tokens"])
        != reservation
        or reservation != contract_reservation
        or reservation <= 0
        or reservation > ceiling_value
        or _money(
            item["cumulative_worst_case_validation_exposure_usd"],
            code="cumulative_exposure",
        )
        != cumulative
        or case_remaining != remaining
        or item["transport_binding_id"] != transport_binding["binding_id"]
        or item["request_hash"] != predecessor["request_hash"]
        or _SHA256.fullmatch(item["request_configuration_hash"]) is None
        or _SHA256.fullmatch(item["request_hash"]) is None
        or _SHA256.fullmatch(item["schema_hash"]) is None
    ):
        raise _fail("case_contract")
    case = CapstoneValidationCase(
        case_id=item["validation_case_id"],
        predecessor_case_id=item["predecessor_validation_case_id"],
        predecessor_result_record_hash=item["predecessor_result_record_hash"],
        source_call_id=item["source_call_id"],
        candidate_id=item["candidate_id"],
        provider=item["provider"],
        model=item["model"],
        api_family=item["api_family"],
        endpoint=item["endpoint"],
        fixture_id=item["fixture_id"],
        workload_stage=item["workload_stage"],
        request_configuration_id=item["request_configuration_id"],
        request_configuration_hash=item["request_configuration_hash"],
        request_hash=item["request_hash"],
        request_body_bytes=item["request_body_bytes"],
        schema_id=item["schema_id"],
        schema_hash=item["schema_hash"],
        role_mapping_id=item["role_mapping_id"],
        adapter_id=item["adapter_id"],
        input_tokens=item["observed_input_tokens"],
        conservative_reservation_usd=item["conservative_reservation_usd"],
        cumulative_exposure_usd=item[
            "cumulative_worst_case_validation_exposure_usd"
        ],
        remaining_after_reservation_usd=item["remaining_after_reservation_usd"],
        transport_binding_id=item["transport_binding_id"],
    )
    return CapstoneValidationContract(
        artifact_id=raw["artifact_id"],
        artifact_version=raw["artifact_version"],
        semantic_hash=_CONTRACT_HASH,
        total_spend_ceiling_usd=ceiling,
        maximum_lifetime_provider_calls=execution["maximum_lifetime_provider_calls"],
        cases=(case,),
        predecessor_repository_head=predecessor["repository_head"],
        predecessor_contract_hash=predecessor["contract_hash"],
        predecessor_authorization_hash=predecessor["authorization_hash"],
        predecessor_reservation_record_hash=predecessor[
            "reservation_record_hash"
        ],
        predecessor_result_record_hash=predecessor["result_record_hash"],
        predecessor_request_hash=predecessor["request_hash"],
        predecessor_unresolved_exposure_usd=predecessor[
            "unresolved_exposure_usd"
        ],
        transport_binding_id=transport_binding["binding_id"],
        transport_implementation_sha256=transport_binding[
            "implementation_sha256"
        ],
        transport_requirements_sha256=transport_binding["requirements_sha256"],
        transport_reviewed_base_head=transport_binding[
            "reviewed_base_repository_head"
        ],
        prior_unresolved_exposure_usd=spend[
            "prior_v1_unresolved_exposure_usd"
        ],
        cumulative_exposure_usd=spend[
            "cumulative_worst_case_validation_exposure_usd"
        ],
        strict_pilot_authorization_api_allowed=separation[
            "strict_pilot_authorization_api_allowed"
        ],
        strict_pilot_ledger_interaction_allowed=separation[
            "strict_pilot_ledger_interaction_allowed"
        ],
        strict_pilot_record_creation_allowed=separation[
            "strict_pilot_record_creation_allowed"
        ],
        scored_record_creation_allowed=separation["scored_record_creation_allowed"],
    )


class CapstoneLiveValidation:
    """Verified one-case composition root with no embedded execution authority."""

    __slots__ = (
        "repository_root",
        "repository_head",
        "contract",
        "_runner",
        "_adapters",
        "_schema_registry",
        "_require_clean_repository_on_execute",
    )

    def __init__(
        self,
        *,
        repository_root: Path,
        repository_head: str,
        contract: CapstoneValidationContract,
        runner: Any,
        adapters: Any,
        schema_registry: CanonicalOutputSchemaRegistry,
        require_clean_repository_on_execute: bool,
    ) -> None:
        self.repository_root = repository_root
        self.repository_head = repository_head
        self.contract = contract
        self._runner = runner
        self._adapters = adapters
        self._schema_registry = schema_registry
        self._require_clean_repository_on_execute = require_clean_repository_on_execute
        self.build_request(_CASE_ID)

    def readiness_projection(self) -> dict[str, Any]:
        return {
            "status": CAPSTONE_LIVE_VALIDATION_STATUS,
            "execution_class": _EXECUTION_CLASS,
            "execution": "blocked_awaiting_explicit_user_authorization",
            "provider_calls": 0,
            "strict_pilot_calls": 0,
            "scored_calls": 0,
            "winner_selected": False,
            "credentials_accessed": 0,
        }

    def case(self, case_id: str) -> CapstoneValidationCase:
        matches = tuple(case for case in self.contract.cases if case.case_id == case_id)
        if len(matches) != 1:
            raise _fail("validation_case_id")
        return matches[0]

    def build_request(self, case_id: str) -> NativeProviderRequest:
        case = self.case(case_id)
        calls = tuple(
            call
            for call in self._runner.plan.provider_calls
            if call.call_id == case.source_call_id
        )
        if len(calls) != 1:
            raise _fail("source_call_identity")
        call = calls[0]
        request = self._runner.build_native_request(call)
        if (
            call.candidate_id != case.candidate_id
            or call.provider != case.provider
            or call.model != case.model
            or call.api_family != case.api_family
            or call.fixture_id != case.fixture_id
            or call.workload_stage != case.workload_stage
            or call.request_configuration_id != case.request_configuration_id
            or call.request_configuration_hash != case.request_configuration_hash
            or call.schema_id != case.schema_id
            or call.schema_hash != case.schema_hash
            or call.role_mapping_id != case.role_mapping_id
            or call.adapter_id != case.adapter_id
            or request.payload_hash != case.request_hash
            or len(request.payload_json) != case.request_body_bytes
        ):
            raise _fail("frozen_request_identity")
        return request

    def dry_run(
        self,
        case_id: str,
        *,
        operational_root: str | Path,
        transport: ConcreteLivePilotTransport,
    ) -> dict[str, Any]:
        case = self.case(case_id)
        request = self.build_request(case_id)
        runtime_identity = _runtime_identity(transport)
        transport_projection = transport.offline_request_projection(request)
        if transport_projection["url"] != case.endpoint:
            raise _fail("transport_endpoint")
        predecessor = self.validate_predecessor_state(operational_root)
        self.validate_case_availability(case_id, operational_root)
        pending = self._authorization_values(
            case,
            runtime_identity=runtime_identity,
            authorized_at_utc="2000-01-01T00:00:00Z",
            status="pending_explicit_human_authorization",
        )
        pending["semantic_hash"] = _semantic_hash(pending, "semantic_hash")
        if set(pending) != _AUTHORIZATION_KEYS:
            raise _fail("authorization_shape")
        return {
            "status": "offline_dry_run_passed",
            "execution_class": _EXECUTION_CLASS,
            "validation_case_id": case.case_id,
            "source_call_id": case.source_call_id,
            "provider": case.provider,
            "model": case.model,
            "fixture_id": case.fixture_id,
            "request_configuration_id": case.request_configuration_id,
            "request_configuration_hash": case.request_configuration_hash,
            "request_hash": request.payload_hash,
            "request_body_bytes": len(request.payload_json),
            "transport_projection": transport_projection,
            "predecessor_validation_case_id": predecessor[
                "validation_case_id"
            ],
            "predecessor_result_record_hash": predecessor[
                "result_record_hash"
            ],
            "predecessor_unresolved_exposure_usd": (
                self.contract.predecessor_unresolved_exposure_usd
            ),
            "transport_binding_id": self.contract.transport_binding_id,
            "runtime_identity": runtime_identity,
            "runtime_identity_hash": _hash(runtime_identity),
            "schema_binding": "validated",
            "authorization_shape": "validated_pending_human_authorization",
            "spend_reservation": "validated",
            "conservative_reservation_usd": case.conservative_reservation_usd,
            "cumulative_worst_case_validation_exposure_usd": (
                case.cumulative_exposure_usd
            ),
            "validation_spend_ceiling_usd": self.contract.total_spend_ceiling_usd,
            "validation_spend_remaining_after_reservation_usd": (
                case.remaining_after_reservation_usd
            ),
            "credentials_accessed": 0,
            "provider_calls": 0,
        }

    def _authorization_values(
        self,
        case: CapstoneValidationCase,
        *,
        runtime_identity: Mapping[str, Any],
        authorized_at_utc: str,
        status: str,
    ) -> dict[str, Any]:
        runtime = _validate_runtime_identity(runtime_identity)
        return {
            "authorization_id": f"human-{case.case_id}-authorization-v2",
            "authorization_version": "v2",
            "status": status,
            "execution_class": _EXECUTION_CLASS,
            "repository_head": self.repository_head,
            "contract_hash": self.contract.semantic_hash,
            "validation_case_id": case.case_id,
            "predecessor_validation_case_id": case.predecessor_case_id,
            "predecessor_contract_hash": self.contract.predecessor_contract_hash,
            "predecessor_reservation_record_hash": (
                self.contract.predecessor_reservation_record_hash
            ),
            "predecessor_result_record_hash": (
                self.contract.predecessor_result_record_hash
            ),
            "predecessor_unresolved_exposure_usd": (
                self.contract.predecessor_unresolved_exposure_usd
            ),
            "source_call_id": case.source_call_id,
            "candidate_id": case.candidate_id,
            "provider": case.provider,
            "model": case.model,
            "fixture_id": case.fixture_id,
            "workload_stage": case.workload_stage,
            "request_configuration_id": case.request_configuration_id,
            "request_configuration_hash": case.request_configuration_hash,
            "request_hash": case.request_hash,
            "transport_binding_id": self.contract.transport_binding_id,
            "transport_implementation_sha256": (
                self.contract.transport_implementation_sha256
            ),
            "runtime_identity": runtime,
            "runtime_identity_hash": _hash(runtime),
            "maximum_provider_calls": 1,
            "retry_count": 0,
            "validation_spend_ceiling_usd": self.contract.total_spend_ceiling_usd,
            "conservative_reservation_usd": case.conservative_reservation_usd,
            "validation_spend_committed_before_usd": (
                self.contract.prior_unresolved_exposure_usd
            ),
            "cumulative_worst_case_validation_exposure_usd": (
                case.cumulative_exposure_usd
            ),
            "validation_spend_remaining_after_reservation_usd": (
                case.remaining_after_reservation_usd
            ),
            "credential_readiness": {
                "environment_variable_name": "OPENAI_API_KEY",
                "status": "privately_confirmed",
            },
            "provider_control_confirmation": {
                "provider": "OpenAI",
                "status": "confirmed",
                "external_prepaid_balance_usd": "5.00000000",
                "external_organization_spend_limit_usd": "5.00000000",
                "auto_reload": False,
                "endpoint_permission": "Responses (/v1/responses): Write",
            },
            "authorized_at_utc": authorized_at_utc,
            "strict_pending_cost_reconciliation_preserved": True,
            "strict_pilot_execution_authorized": False,
            "scored_execution_authorized": False,
            "winner_selection_authorized": False,
            "production_deployment_authorized": False,
            "semantic_hash": None,
        }

    def build_authorization_document(
        self,
        *,
        case_id: str,
        runtime_identity: Mapping[str, Any],
        authorized_at_utc: str,
    ) -> dict[str, Any]:
        """Build the exact record only after an external human authorization."""
        _timestamp(authorized_at_utc, code="authorization_timestamp")
        document = self._authorization_values(
            self.case(case_id),
            runtime_identity=runtime_identity,
            authorized_at_utc=authorized_at_utc,
            status="approved",
        )
        document["semantic_hash"] = _semantic_hash(document, "semantic_hash")
        self.validate_authorization(document)
        return document

    def validate_authorization(
        self,
        document: Mapping[str, Any],
    ) -> CapstoneValidationAuthorization:
        if type(document) is not dict or set(document) != _AUTHORIZATION_KEYS:
            raise _fail("authorization_shape")
        stored_hash = document.get("semantic_hash")
        if (
            type(stored_hash) is not str
            or _SHA256.fullmatch(stored_hash) is None
            or _semantic_hash(document, "semantic_hash") != stored_hash
        ):
            raise _fail("authorization_hash")
        case = self.case(document.get("validation_case_id"))
        runtime_identity = _validate_runtime_identity(document.get("runtime_identity"))
        runtime_identity_hash = document.get("runtime_identity_hash")
        if (
            type(runtime_identity_hash) is not str
            or _SHA256.fullmatch(runtime_identity_hash) is None
            or _hash(runtime_identity) != runtime_identity_hash
        ):
            raise _fail("runtime_identity_hash")
        expected = self._authorization_values(
            case,
            runtime_identity=runtime_identity,
            authorized_at_utc=_timestamp(
                document.get("authorized_at_utc"),
                code="authorization_timestamp",
            ),
            status="approved",
        )
        expected["semantic_hash"] = stored_hash
        if _canonical(document) != _canonical(expected):
            raise _fail("authorization_binding")
        return CapstoneValidationAuthorization(
            semantic_hash=stored_hash,
            execution_class=document["execution_class"],
            repository_head=document["repository_head"],
            case_id=case.case_id,
            runtime_identity_hash=runtime_identity_hash,
            maximum_provider_calls=document["maximum_provider_calls"],
            retry_count=document["retry_count"],
            strict_pilot_execution_authorized=document[
                "strict_pilot_execution_authorized"
            ],
            scored_execution_authorized=document["scored_execution_authorized"],
            winner_selection_authorized=document["winner_selection_authorized"],
            production_deployment_authorized=document[
                "production_deployment_authorized"
            ],
        )

    def _state_paths(self, operational_root: str | Path) -> tuple[Path, Path, Path]:
        root = Path(operational_root).resolve() / _STATE_DIRECTORY
        return root, root / _RESERVATION_FILE, root / _RESULT_FILE

    def validate_predecessor_state(
        self,
        operational_root: str | Path,
    ) -> dict[str, Any]:
        root = Path(operational_root).resolve() / _PREDECESSOR_STATE_DIRECTORY
        reservation = _load_immutable_state_record(
            root / _RESERVATION_FILE,
            self.contract.predecessor_reservation_record_hash,
        )
        result = _load_immutable_state_record(
            root / _RESULT_FILE,
            self.contract.predecessor_result_record_hash,
        )
        if (
            reservation.get("record_type")
            != "capstone_live_validation_reservation"
            or reservation.get("record_version") != "v1"
            or reservation.get("validation_case_id") != _PREDECESSOR_CASE_ID
            or reservation.get("repository_head")
            != self.contract.predecessor_repository_head
            or reservation.get("contract_hash")
            != self.contract.predecessor_contract_hash
            or reservation.get("authorization_hash")
            != self.contract.predecessor_authorization_hash
            or reservation.get("request_hash")
            != self.contract.predecessor_request_hash
            or reservation.get("conservative_reservation_usd")
            != self.contract.predecessor_unresolved_exposure_usd
            or result.get("record_type") != "capstone_live_validation_result"
            or result.get("record_version") != "v1"
            or result.get("validation_case_id") != _PREDECESSOR_CASE_ID
            or result.get("repository_head")
            != self.contract.predecessor_repository_head
            or result.get("contract_hash")
            != self.contract.predecessor_contract_hash
            or result.get("authorization_hash")
            != self.contract.predecessor_authorization_hash
            or result.get("request_hash")
            != self.contract.predecessor_request_hash
            or result.get("result_status") != "stopped"
            or result.get("safe_failure_classification") != "connection"
            or result.get("cost_observation_status") != "not_determinable"
            or result.get("observed_validation_cost_usd") is not None
            or result.get("conservative_reservation_usd")
            != self.contract.predecessor_unresolved_exposure_usd
            or result.get("physical_provider_attempts") != 1
            or result.get("retry_count") != 0
            or result.get("strict_pilot_record") is not False
            or result.get("scored_record") is not False
        ):
            raise _fail("predecessor_state_binding")
        return {
            "validation_case_id": _PREDECESSOR_CASE_ID,
            "reservation_record_hash": reservation["record_hash"],
            "result_record_hash": result["record_hash"],
            "unresolved_exposure_usd": (
                self.contract.predecessor_unresolved_exposure_usd
            ),
            "state": "consumed_preserved_unresolved",
        }

    def validate_offline_preflight(
        self,
        *,
        authorization_document: Mapping[str, Any],
        operational_root: str | Path,
        transport: ConcreteLivePilotTransport,
    ) -> tuple[
        CapstoneValidationAuthorization,
        dict[str, str],
        dict[str, Any],
    ]:
        authorization = self.validate_authorization(authorization_document)
        case = self.case(authorization.case_id)
        request = self.build_request(case.case_id)
        self.validate_predecessor_state(operational_root)
        self.validate_case_availability(case.case_id, operational_root)
        runtime = _runtime_identity(transport)
        transport_projection = transport.offline_request_projection(request)
        if transport_projection["url"] != case.endpoint:
            raise _fail("transport_endpoint")
        if _hash(runtime) != authorization.runtime_identity_hash:
            raise _fail("runtime_identity_mismatch")
        return authorization, runtime, transport_projection

    def validate_case_availability(
        self,
        case_id: str,
        operational_root: str | Path,
    ) -> None:
        """Fail offline when an immutable reservation already consumed the case."""
        self.case(case_id)
        state_root, reservation_path, result_path = self._state_paths(operational_root)
        if reservation_path.exists() or result_path.exists():
            raise _fail("case_already_reserved")
        if state_root.exists() and not state_root.is_dir():
            raise _fail("operational_state_path")

    def execute_one(
        self,
        *,
        authorization_document: Mapping[str, Any],
        confirm_live: bool,
        credential_resolver: Any,
        transport: PilotTransport,
        operational_root: str | Path,
        clock: Callable[[], datetime] | None = None,
    ) -> dict[str, Any]:
        """Execute exactly one physical call after every separate gate passes."""
        if confirm_live is not True:
            raise _fail("explicit_live_confirmation_required")
        authorization = self.validate_authorization(authorization_document)
        case = self.case(authorization.case_id)
        request = self.build_request(case.case_id)
        if not isinstance(credential_resolver, LazyEnvironmentCredentialResolver):
            raise _fail("credential_resolver")
        if not isinstance(transport, ConcreteLivePilotTransport):
            raise _fail("live_transport")
        runtime = _runtime_identity(transport)
        if _hash(runtime) != authorization.runtime_identity_hash:
            raise _fail("runtime_identity_mismatch")
        if _repository_head(self.repository_root) != self.repository_head:
            raise _fail("repository_head_mismatch")
        if self._require_clean_repository_on_execute:
            _require_clean_repository(self.repository_root)
        self.validate_predecessor_state(operational_root)
        self.validate_case_availability(case.case_id, operational_root)
        state_root, reservation_path, result_path = self._state_paths(operational_root)
        if getattr(transport, "invocation_count", None) != 0:
            raise _fail("physical_provider_attempt_count")
        credential = credential_resolver.resolve(
            CapstoneCredentialReference(
                case.provider,
                "OPENAI_API_KEY",
            )
        )
        started_at = _now(clock)
        reservation = {
            "record_type": "capstone_live_validation_reservation",
            "record_version": "v2",
            "execution_class": _EXECUTION_CLASS,
            "validation_case_id": case.case_id,
            "predecessor_validation_case_id": case.predecessor_case_id,
            "predecessor_reservation_record_hash": (
                self.contract.predecessor_reservation_record_hash
            ),
            "predecessor_result_record_hash": (
                self.contract.predecessor_result_record_hash
            ),
            "predecessor_unresolved_exposure_usd": (
                self.contract.predecessor_unresolved_exposure_usd
            ),
            "repository_head": self.repository_head,
            "contract_hash": self.contract.semantic_hash,
            "authorization_hash": authorization.semantic_hash,
            "runtime_identity_hash": authorization.runtime_identity_hash,
            "request_hash": request.payload_hash,
            "conservative_reservation_usd": case.conservative_reservation_usd,
            "cumulative_worst_case_validation_exposure_usd": (
                case.cumulative_exposure_usd
            ),
            "validation_spend_ceiling_usd": self.contract.total_spend_ceiling_usd,
            "validation_spend_remaining_after_reservation_usd": (
                case.remaining_after_reservation_usd
            ),
            "provider_invocation_count_at_reservation": 0,
            "started_at": started_at,
            "record_hash": None,
        }
        reservation["record_hash"] = _semantic_hash(reservation, "record_hash")
        _write_exclusive(reservation_path, reservation)
        response = transport.invoke(request, credential, AttemptDeadline(0.0))
        del credential
        if getattr(transport, "invocation_count", None) != 1:
            raise _fail("physical_provider_attempt_count")
        completed_at = _now(clock)
        record = self._record_for_response(
            case=case,
            request=request,
            authorization=authorization,
            response=response,
            started_at=started_at,
            completed_at=completed_at,
        )
        _write_exclusive(result_path, record)
        return record

    def _record_for_response(
        self,
        *,
        case: CapstoneValidationCase,
        request: NativeProviderRequest,
        authorization: CapstoneValidationAuthorization,
        response: TransportResponse,
        started_at: str,
        completed_at: str,
    ) -> dict[str, Any]:
        if type(response) is not TransportResponse:
            raise _fail("transport_response")
        raw_hash = (
            hashlib.sha256(response.response_bytes).hexdigest()
            if response.response_bytes
            else None
        )
        base: dict[str, Any] = {
            "record_type": "capstone_live_validation_result",
            "record_version": "v2",
            "execution_class": _EXECUTION_CLASS,
            "validation_id": f"{case.case_id}-attempt-1",
            "validation_case_id": case.case_id,
            "predecessor_validation_case_id": case.predecessor_case_id,
            "predecessor_reservation_record_hash": (
                self.contract.predecessor_reservation_record_hash
            ),
            "predecessor_result_record_hash": (
                self.contract.predecessor_result_record_hash
            ),
            "predecessor_unresolved_exposure_usd": (
                self.contract.predecessor_unresolved_exposure_usd
            ),
            "source_call_id": case.source_call_id,
            "repository_head": self.repository_head,
            "contract_hash": self.contract.semantic_hash,
            "authorization_hash": authorization.semantic_hash,
            "runtime_identity_hash": authorization.runtime_identity_hash,
            "candidate_id": case.candidate_id,
            "provider": case.provider,
            "model": case.model,
            "fixture_id": case.fixture_id,
            "workload_stage": case.workload_stage,
            "request_configuration_id": case.request_configuration_id,
            "request_configuration_hash": case.request_configuration_hash,
            "request_hash": request.payload_hash,
            "started_at": started_at,
            "completed_at": completed_at,
            "http_status": response.status_code,
            "provider_response_received": response.status_code != 0,
            "result_status": "stopped",
            "safe_finish_reason": None,
            "latency_seconds": format(Decimal(str(response.elapsed_seconds)), "f"),
            "provider_usage": None,
            "provider_request_id": None,
            "raw_response_hash": raw_hash,
            "normalized_semantic_hash": None,
            "parser_result": "not_reached",
            "schema_result": "not_reached",
            "validator_result": "not_reached",
            "semantic_summary": None,
            "safe_failure_classification": response.failure_signal,
            "estimated_validation_cost": None,
            "observed_validation_cost_usd": None,
            "cost_observation_status": "not_determinable",
            "conservative_reservation_usd": case.conservative_reservation_usd,
            "cumulative_worst_case_validation_exposure_usd": (
                case.cumulative_exposure_usd
            ),
            "validation_spend_ceiling_usd": self.contract.total_spend_ceiling_usd,
            "validation_spend_remaining_usd": case.remaining_after_reservation_usd,
            "physical_provider_attempts": 1,
            "retry_count": 0,
            "strict_pilot_record": False,
            "scored_record": False,
            "winner_selection": False,
            "production_deployment": False,
            "record_hash": None,
        }
        if response.failure_signal is not None or response.status_code != 200:
            base["safe_finish_reason"] = response.failure_signal or "http_failure"
            base["safe_failure_classification"] = (
                response.failure_signal or "http_failure"
            )
            return _finish_record(base)
        capture = CanonicalRawResponseAccumulator("non_streaming_http")
        try:
            capture.append(response.response_bytes)
            adapted = adapt_provider_response(
                self._adapters,
                request.role_selection,
                capture.finish_response(),
                http_status=response.status_code,
            )
            base["safe_finish_reason"] = adapted.documented_finish_state
            base["provider_usage"] = {
                "input_tokens": adapted.usage.input_token_usage,
                "output_tokens": adapted.usage.output_token_usage,
                "reasoning_tokens": adapted.usage.reasoning_usage_if_exposed,
                "image_usage": adapted.usage.image_usage_if_exposed,
            }
            base["raw_response_hash"] = adapted.raw_provider_response_hash
            semantic = normalize_semantic_json(adapted.semantic_content_bytes)
            base["parser_result"] = "passed"
            base["normalized_semantic_hash"] = (
                semantic.strict_parsed_semantic_payload_hash
            )
            candidate = self._schema_registry.validate(case.schema_id, semantic)
            base["schema_result"] = "passed"
            validate_text_post_schema_candidate(
                candidate,
                schema_registry=self._schema_registry,
            )
            base["validator_result"] = "passed"
            semantic_value = candidate.canonical_semantic_json.admitted.value
            base["semantic_summary"] = {
                "schema_id": case.schema_id,
                "canonical_top_level_fields": sorted(semantic_value),
            }
            try:
                estimate = calculate_live_success_cost(
                    provider=case.provider,
                    model=case.model,
                    workload_stage=case.workload_stage,
                    response_bytes=response.response_bytes,
                )
            except LiveCostBindingError:
                base["cost_observation_status"] = "usage_not_cost_bindable"
            else:
                estimate_value = _exact_nonnegative_decimal(
                    estimate.total_usd,
                    code="estimated_cost",
                )
                if estimate_value > _money(
                    case.conservative_reservation_usd,
                    code="case_reservation",
                ):
                    base["safe_failure_classification"] = (
                        "estimated_cost_exceeds_reservation"
                    )
                    base["safe_finish_reason"] = "estimated_cost_exceeds_reservation"
                    return _finish_record(base)
                base["estimated_validation_cost"] = estimate.as_dict()
                base["cost_observation_status"] = (
                    "frozen_estimate_from_provider_usage_not_provider_billing"
                )
            base["result_status"] = "accepted"
            base["safe_failure_classification"] = None
            return _finish_record(base)
        except (DuplicateJsonKeyError, NumericDomainError, StrictJsonPayloadError):
            base["safe_failure_classification"] = "failed_strict_parse"
        except CanonicalSchemaValidationError:
            base["safe_failure_classification"] = "failed_canonical_validation"
        except DeterministicValidationError:
            base["safe_failure_classification"] = "failed_cross_field_validation"
        except (
            ProviderAdapterResponseError,
            ResourceLimitExceededError,
            TransportCaptureStateError,
            SchemaContractError,
        ):
            base["safe_failure_classification"] = "failed_transport_extraction"
        base["safe_finish_reason"] = base["safe_failure_classification"]
        return _finish_record(base)

    def inspect_result(self, operational_root: str | Path) -> dict[str, Any]:
        _root, _reservation_path, result_path = self._state_paths(operational_root)
        try:
            result = load_strict_contract_json(result_path)
        except (OSError, TypeError, ValueError) as exc:
            raise _fail("result_unavailable") from exc
        stored_hash = result.get("record_hash")
        if (
            type(stored_hash) is not str
            or _SHA256.fullmatch(stored_hash) is None
            or _semantic_hash(result, "record_hash") != stored_hash
        ):
            raise _fail("result_hash")
        case = self.case(result.get("validation_case_id"))
        if (
            result.get("record_type") != "capstone_live_validation_result"
            or result.get("record_version") != "v2"
            or result.get("execution_class") != _EXECUTION_CLASS
            or result.get("predecessor_validation_case_id")
            != case.predecessor_case_id
            or result.get("predecessor_reservation_record_hash")
            != self.contract.predecessor_reservation_record_hash
            or result.get("predecessor_result_record_hash")
            != self.contract.predecessor_result_record_hash
            or result.get("predecessor_unresolved_exposure_usd")
            != self.contract.predecessor_unresolved_exposure_usd
            or result.get("repository_head") != self.repository_head
            or result.get("contract_hash") != self.contract.semantic_hash
            or result.get("source_call_id") != case.source_call_id
            or result.get("candidate_id") != case.candidate_id
            or result.get("provider") != case.provider
            or result.get("model") != case.model
            or result.get("fixture_id") != case.fixture_id
            or result.get("workload_stage") != case.workload_stage
            or result.get("request_configuration_id")
            != case.request_configuration_id
            or result.get("request_configuration_hash")
            != case.request_configuration_hash
            or result.get("request_hash") != case.request_hash
            or result.get("conservative_reservation_usd")
            != case.conservative_reservation_usd
            or result.get("cumulative_worst_case_validation_exposure_usd")
            != case.cumulative_exposure_usd
            or result.get("validation_spend_ceiling_usd")
            != self.contract.total_spend_ceiling_usd
            or result.get("validation_spend_remaining_usd")
            != case.remaining_after_reservation_usd
            or result.get("physical_provider_attempts") != 1
            or result.get("retry_count") != 0
            or result.get("strict_pilot_record") is not False
            or result.get("scored_record") is not False
            or result.get("winner_selection") is not False
            or result.get("production_deployment") is not False
            or type(result.get("provider_response_received")) is not bool
            or result.get("provider_response_received")
            is not (result.get("http_status") != 0)
            or type(result.get("runtime_identity_hash")) is not str
            or _SHA256.fullmatch(result["runtime_identity_hash"]) is None
        ):
            raise _fail("result_binding")
        return {
            "execution_class": result["execution_class"],
            "validation_case_id": result["validation_case_id"],
            "provider": result["provider"],
            "model": result["model"],
            "fixture_id": result["fixture_id"],
            "predecessor_validation_case_id": result[
                "predecessor_validation_case_id"
            ],
            "predecessor_result_record_hash": result[
                "predecessor_result_record_hash"
            ],
            "result_status": result["result_status"],
            "safe_finish_reason": result["safe_finish_reason"],
            "provider_response_received": result["provider_response_received"],
            "latency_seconds": result["latency_seconds"],
            "provider_usage": result["provider_usage"],
            "estimated_validation_cost": result["estimated_validation_cost"],
            "observed_validation_cost_usd": result[
                "observed_validation_cost_usd"
            ],
            "validation_spend_remaining_usd": result[
                "validation_spend_remaining_usd"
            ],
            "cumulative_worst_case_validation_exposure_usd": result[
                "cumulative_worst_case_validation_exposure_usd"
            ],
            "parser_result": result["parser_result"],
            "schema_result": result["schema_result"],
            "validator_result": result["validator_result"],
            "semantic_summary": result["semantic_summary"],
            "raw_response_hash": result["raw_response_hash"],
            "normalized_semantic_hash": result["normalized_semantic_hash"],
            "record_hash": stored_hash,
        }


def _finish_record(record: dict[str, Any]) -> dict[str, Any]:
    record["record_hash"] = _semantic_hash(record, "record_hash")
    return record


def _write_exclusive(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = _canonical(document) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        raise _fail("case_already_reserved") from None
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        # Do not remove a possibly written reservation after authority crossed
        # into an operational state; its existence preserves fail-closed replay.
        raise


def build_capstone_live_validation(
    *,
    repository_root: str | Path,
    repository_head: str,
    require_clean_repository: bool = True,
) -> CapstoneLiveValidation:
    root = Path(repository_root).resolve()
    if type(repository_head) is not str or _HEAD.fullmatch(repository_head) is None:
        raise _fail("repository_head")
    if _repository_head(root) != repository_head:
        raise _fail("repository_head_mismatch")
    if type(require_clean_repository) is not bool:
        raise _fail("require_clean_repository")
    if require_clean_repository:
        _require_clean_repository(root)
    contract = _load_contract(root)
    runner = build_provider_free_pilot_runner(
        repository_root=root,
        repository_harness_commit_sha=repository_head,
    )
    artifacts_root = root / "docs" / "testing" / "ai-evaluation"
    prompts = load_strict_contract_json(artifacts_root / "prompt-templates.v1.json")
    parser = load_strict_normalization_spec(
        artifacts_root / "normalization-parser.v1.json"
    )
    authority = bind_search_authority_v2(
        load_strict_contract_json(artifacts_root / "search-authority.v2.json"),
        prompts,
        parser,
    )
    mappings = bind_provider_role_mappings(
        load_strict_contract_json(artifacts_root / "provider-role-mappings.v1.json"),
        authority,
    )
    adapters = bind_provider_adapters(
        load_strict_contract_json(artifacts_root / "provider-adapters.v1.json"),
        mappings,
    )
    schema_registry = CanonicalOutputSchemaRegistry.from_artifact(
        load_strict_contract_json(artifacts_root / "output-schemas.v1.json")
    )
    if (
        runner.readiness_projection()["provider_calls_allowed"] is not False
        or runner.readiness_projection()["pilot_calls_allowed"] is not False
        or runner.readiness_projection()["scored_calls_allowed"] is not False
    ):
        raise _fail("strict_runner_boundary")
    return CapstoneLiveValidation(
        repository_root=root,
        repository_head=repository_head,
        contract=contract,
        runner=runner,
        adapters=adapters,
        schema_registry=schema_registry,
        require_clean_repository_on_execute=require_clean_repository,
    )
