"""Minimal Sol/PT1 and Gemini/PT1 Capstone live-validation extension.

Everything except ``execute_one`` is provider-free.  The extension consumes
the accepted Terra V2 record as immutable history, preserves its conservative
exposure, and remains mechanically separate from strict pilot/scored state.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from app.services.evaluation_capstone_live_validation import (
    CapstoneLiveValidationError,
    _artifact_hash,
    _canonical,
    _file_sha256,
    _finish_record,
    _hash,
    _load_immutable_state_record,
    _money,
    _now,
    _repository_head,
    _require_clean_repository,
    _runtime_identity,
    _semantic_hash,
    _timestamp,
    _validate_runtime_identity,
    _write_exclusive,
    build_capstone_live_validation,
)
from app.services.evaluation_contract_identity import load_strict_contract_json
from app.services.evaluation_live_cost import (
    LiveCostBindingError,
    calculate_live_success_cost,
)
from app.services.evaluation_live_transport import (
    ConcreteLivePilotTransport,
    LazyEnvironmentCredentialResolver,
)
from app.services.evaluation_pilot_runner import (
    NativeProviderRequest,
    PilotTransport,
    TransportResponse,
)
from app.services.evaluation_post_schema_validation import (
    validate_text_post_schema_candidate,
)
from app.services.evaluation_provider_adapters import (
    ProviderAdapterResponseError,
    adapt_provider_response,
)
from app.services.evaluation_resource_limits import ResourceLimitExceededError
from app.services.evaluation_retry_policy import AttemptDeadline
from app.services.evaluation_schema_validation import (
    CanonicalSchemaValidationError,
    SchemaContractError,
)
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


CAPSTONE_CROSS_PROVIDER_TEXT_VALIDATION_STATUS = (
    "CAPSTONE_CROSS_PROVIDER_TEXT_VALIDATION_READY_AWAITING_USER"
)
_CONTRACT_FILE = "capstone-live-validation.v3.json"
_CONTRACT_HASH = "fa141065f8fe374d4b43409cefb2fec58e66f3f949d733ea4bf9cdc254635617"
_EXECUTION_CLASS = "capstone_live_validation"
_STATE_DIRECTORY = "capstone-cross-provider-text-validation-v3"
_SOL_CASE_ID = "capval-openai-sol-pt1-v1"
_GEMINI_CASE_ID = "capval-gemini-flash-pt1-v1"
_CASE_ORDER = (_SOL_CASE_ID, _GEMINI_CASE_ID)
_HEAD = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_AUTHORIZATION_KEYS = {
    "authorization_id",
    "authorization_version",
    "status",
    "execution_class",
    "repository_head",
    "contract_hash",
    "validation_case_id",
    "historical_predecessor_validation_case_id",
    "terra_v1_reservation_record_hash",
    "terra_v1_result_record_hash",
    "terra_v2_reservation_record_hash",
    "terra_v2_result_record_hash",
    "historical_conservative_exposure_usd",
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
    "billing_context",
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


def _fail(code: str) -> CapstoneLiveValidationError:
    return CapstoneLiveValidationError(code)


@dataclass(frozen=True, slots=True)
class HistoricalStateBinding:
    case_id: str
    repository_head: str
    contract_hash: str
    authorization_hash: str
    reservation_record_hash: str
    result_record_hash: str
    request_hash: str
    exposure_usd: str
    state_directory: str


@dataclass(frozen=True, slots=True)
class CrossProviderValidationCase:
    case_id: str
    historical_predecessor_case_id: str
    historical_predecessor_result_record_hash: str
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
    prompt_ids: tuple[str, ...]
    prompt_hashes: tuple[str, ...]
    schema_id: str
    schema_hash: str
    role_mapping_id: str
    role_mapping_hash: str
    adapter_id: str
    adapter_hash: str
    maximum_output_tokens: int
    reasoning: str
    temperature: str | None
    input_token_bound_kind: str
    input_token_bound: int
    billing_context: str
    conservative_reservation_usd: str
    committed_before_usd: str
    cumulative_exposure_usd: str
    remaining_after_reservation_usd: str
    credential_environment_variable: str
    transport_binding_id: str
    provider_limits: Mapping[str, int] | None


@dataclass(frozen=True, slots=True)
class CrossProviderValidationContract:
    artifact_id: str
    artifact_version: str
    semantic_hash: str
    total_spend_ceiling_usd: str
    historical_exposure_usd: str
    transport_binding_id: str
    transport_implementation_sha256: str
    transport_requirements_sha256: str
    historical_states: tuple[HistoricalStateBinding, ...]
    cases: tuple[CrossProviderValidationCase, ...]


@dataclass(frozen=True, slots=True)
class CrossProviderAuthorization:
    semantic_hash: str
    repository_head: str
    case_id: str
    runtime_identity_hash: str
    maximum_provider_calls: int
    retry_count: int


@dataclass(frozen=True, slots=True)
class CrossProviderCredentialReference:
    provider: str
    environment_variable_name: str


def _history(raw: Mapping[str, Any]) -> tuple[HistoricalStateBinding, ...]:
    items = raw.get("historical_state_bindings")
    if type(items) is not list or len(items) != 2:
        raise _fail("historical_state_bindings")
    expected = (
        (
            "capval-openai-terra-pt1-v1",
            "b5f191655e071bb98b74568dc02def32a14f5138",
            "389c8e4c693fc9bcff353f9704c104f8ec64ba98de05c3a6d9c0cd7e6eec7564",
            "ed5dd5718b4a60fd208240bf6ea54b9870fa52264bc118b4ba7faf1bc781f051",
            "a9d604c30f16ecd4525d533955f9701ea15ed78c35cb7fff703c3e3761cd1bab",
            "554fdf1685a4b766698d9af255fd7921e3500a7390915957831eab440582d24e",
            "0.05169700",
            "capstone-live-validation-v1",
        ),
        (
            "capval-openai-terra-pt1-v2",
            "440880ac85dd371a3dbe44b9e364d7df3c13c3ff",
            "48831c6dfafcdd00ab7e8a525d448574526ffefbfbf9c6d1bf9c105299af13be",
            "9a84b4b07b81b503376a23cccdc0b953963fe4299b5f705279c348f173f9c277",
            "6a66fa758fa20d231a02649263fddcdb53da314b2a1f6a9c9853b10e58610ed3",
            "1c4b25beb71569d68642e9f6d554b7473d042c779b8f26c930ca63caa9959386",
            "0.05169700",
            "capstone-live-validation-v2",
        ),
    )
    result = []
    for item, values in zip(items, expected, strict=True):
        case, head, contract, authorization, reservation, record, exposure, directory = values
        actual_exposure = item.get(
            "unresolved_exposure_usd"
            if case.endswith("v1")
            else "conservative_exposure_usd"
        )
        if (
            item.get("validation_case_id") != case
            or item.get("repository_head") != head
            or item.get("contract_hash") != contract
            or item.get("authorization_hash") != authorization
            or item.get("reservation_record_hash") != reservation
            or item.get("result_record_hash") != record
            or item.get("request_hash")
            != "97f8752bb33994a00018a15ff62d79419069397b223cc5f60770def973ebc266"
            or actual_exposure != exposure
            or item.get("live_state_directory")
            != f".capstone-live-validation/{directory}"
        ):
            raise _fail("historical_state_binding")
        result.append(
            HistoricalStateBinding(
                case,
                head,
                contract,
                authorization,
                reservation,
                record,
                item["request_hash"],
                exposure,
                directory,
            )
        )
    return tuple(result)


def _cases(raw: Mapping[str, Any]) -> tuple[CrossProviderValidationCase, ...]:
    items = raw.get("cases")
    if type(items) is not list or len(items) != 2:
        raise _fail("cases")
    result = []
    for item in items:
        case_id = item.get("validation_case_id")
        if case_id not in _CASE_ORDER or item.get("live_eligible") is not True:
            raise _fail("case_identity")
        committed_before = (
            "0.10339400" if case_id == _SOL_CASE_ID else "0.21030200"
        )
        result.append(
            CrossProviderValidationCase(
                case_id=case_id,
                historical_predecessor_case_id=item[
                    "historical_predecessor_validation_case_id"
                ],
                historical_predecessor_result_record_hash=item[
                    "historical_predecessor_result_record_hash"
                ],
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
                prompt_ids=tuple(item["prompt_ids"]),
                prompt_hashes=tuple(item["prompt_hashes"]),
                schema_id=item["schema_id"],
                schema_hash=item["schema_hash"],
                role_mapping_id=item["role_mapping_id"],
                role_mapping_hash=item["role_mapping_hash"],
                adapter_id=item["adapter_id"],
                adapter_hash=item["adapter_hash"],
                maximum_output_tokens=item["maximum_output_tokens"],
                reasoning=item["reasoning"],
                temperature=item["temperature"],
                input_token_bound_kind=item["input_token_bound_kind"],
                input_token_bound=item["input_token_bound"],
                billing_context=item["billing_context"],
                conservative_reservation_usd=item[
                    "conservative_reservation_usd"
                ],
                committed_before_usd=committed_before,
                cumulative_exposure_usd=item[
                    "cumulative_worst_case_validation_exposure_usd"
                ],
                remaining_after_reservation_usd=item[
                    "remaining_after_reservation_usd"
                ],
                credential_environment_variable=item[
                    "credential_environment_variable"
                ],
                transport_binding_id=item["transport_binding_id"],
                provider_limits=item.get("provider_limits"),
            )
        )
    if tuple(case.case_id for case in result) != _CASE_ORDER:
        raise _fail("case_order")
    return tuple(result)


def _load_contract(root: Path) -> CrossProviderValidationContract:
    raw = load_strict_contract_json(
        root / "docs/testing/ai-evaluation" / _CONTRACT_FILE
    )
    if (
        raw.get("artifact_id") != "capstone_cross_provider_text_validation_v3"
        or raw.get("artifact_version") != "v3"
        or raw.get("status") != "ready_awaiting_explicit_user_authorization"
        or raw.get("execution_class") != _EXECUTION_CLASS
        or raw.get("case_order") != list(_CASE_ORDER)
        or raw.get("specification_identity", {}).get("semantic_hash")
        != _CONTRACT_HASH
        or _artifact_hash(raw) != _CONTRACT_HASH
        or any(value is not False for value in raw.get("strict_separation", {}).values())
    ):
        raise _fail("contract_identity")
    boundary = raw.get("execution_boundary")
    execution = raw.get("execution_policy")
    spend = raw.get("spend_guard")
    transport = raw.get("transport_binding")
    if (
        type(boundary) is not dict
        or boundary.get("provider_calls_allowed_by_artifact") is not False
        or boundary.get("pilot_calls_allowed") is not False
        or boundary.get("scored_calls_allowed") is not False
        or boundary.get("provider_calls_completed") != 0
        or boundary.get("winner_selected") is not False
        or type(execution) is not dict
        or execution.get("maximum_provider_calls_per_authorization") != 1
        or execution.get("maximum_lifetime_provider_calls_per_case") != 1
        or execution.get("maximum_new_provider_calls") != 2
        or execution.get("automatic_retry_count") != 0
        or execution.get("automatic_next_case_allowed") is not False
        or execution.get("separate_authorization_per_case_required") is not True
        or type(spend) is not dict
        or type(transport) is not dict
    ):
        raise _fail("contract_boundary")
    ceiling = _money(spend.get("total_validation_spend_ceiling_usd"), code="ceiling")
    historical = _money(spend.get("historical_conservative_exposure_usd"), code="historical")
    sol = _money(spend.get("sol_conservative_reservation_usd"), code="sol")
    gemini = _money(spend.get("gemini_external_monetary_exposure_usd"), code="gemini")
    if (
        ceiling != Decimal("1.00000000")
        or historical != Decimal("0.10339400")
        or sol != Decimal(6247) * Decimal("0.000004")
        + Decimal(4096) * Decimal("0.00002")
        or gemini != Decimal("0.00000000")
        or _money(spend.get("cumulative_after_minimum_set_usd"), code="cumulative")
        != historical + sol + gemini
        or _money(spend.get("remaining_after_minimum_set_usd"), code="remaining")
        != ceiling - historical - sol - gemini
        or spend.get("free_tier_zero_is_capstone_external_exposure_only") is not True
        or spend.get("strict_gemini_pricing_binding_mutation_allowed") is not False
    ):
        raise _fail("spend_guard")
    transport_path = root / transport.get("implementation_path", "")
    requirements_path = root / transport.get("requirements_path", "")
    if (
        transport.get("binding_id") != "capstone_cross_provider_httpx_transport_v1"
        or transport.get("http_client_package") != "httpx"
        or transport.get("http_client_requirement") != "httpx>=0.27"
        or transport.get("redirects_allowed") is not False
        or transport.get("automatic_retry_count") != 0
        or _file_sha256(transport_path) != transport.get("implementation_sha256")
        or _file_sha256(requirements_path) != transport.get("requirements_sha256")
    ):
        raise _fail("transport_binding")
    cases = _cases(raw)
    expected = {
        _SOL_CASE_ID: (
            "call-0001", "openai_unified_premium_v1", "OpenAI", "gpt-5.6-sol",
            "9ddf9c22ab28c69987944c1a77043cb7ed64aed0f81c283444be4129ad47c47f",
            6247, 6247, "0.10690800", "0.21030200", "0.78969800",
        ),
        _GEMINI_CASE_ID: (
            "call-0005", "gemini_unified_v1", "Google Gemini", "gemini-3.7-flash",
            "00f29bb98c9840ffb6d1e61fc080c607aa54a2b20ca862c58f862d08ed013584",
            6229, 6229, "0.00000000", "0.21030200", "0.78969800",
        ),
    }
    for case in cases:
        values = expected[case.case_id]
        if (
            (case.source_call_id, case.candidate_id, case.provider, case.model,
             case.request_hash, case.request_body_bytes, case.input_token_bound,
             case.conservative_reservation_usd, case.cumulative_exposure_usd,
             case.remaining_after_reservation_usd) != values
            or case.maximum_output_tokens != 4096
            or case.fixture_id != "PT1"
            or case.workload_stage != "text_analysis"
            or case.historical_predecessor_case_id != "capval-openai-terra-pt1-v2"
            or case.historical_predecessor_result_record_hash
            != "1c4b25beb71569d68642e9f6d554b7473d042c779b8f26c930ca63caa9959386"
        ):
            raise _fail("case_binding")
    return CrossProviderValidationContract(
        artifact_id=raw["artifact_id"],
        artifact_version=raw["artifact_version"],
        semantic_hash=_CONTRACT_HASH,
        total_spend_ceiling_usd=spend["total_validation_spend_ceiling_usd"],
        historical_exposure_usd=spend["historical_conservative_exposure_usd"],
        transport_binding_id=transport["binding_id"],
        transport_implementation_sha256=transport["implementation_sha256"],
        transport_requirements_sha256=transport["requirements_sha256"],
        historical_states=_history(raw),
        cases=cases,
    )


class CapstoneCrossProviderValidation:
    def __init__(
        self,
        *,
        repository_root: Path,
        repository_head: str,
        contract: CrossProviderValidationContract,
        runner: Any,
        adapters: Any,
        schema_registry: Any,
        require_clean_repository_on_execute: bool,
    ) -> None:
        self.repository_root = repository_root
        self.repository_head = repository_head
        self.contract = contract
        self._runner = runner
        self._adapters = adapters
        self._schema_registry = schema_registry
        self._require_clean_repository_on_execute = require_clean_repository_on_execute
        for case_id in _CASE_ORDER:
            self.build_request(case_id)

    def readiness_projection(self) -> dict[str, Any]:
        return {
            "status": CAPSTONE_CROSS_PROVIDER_TEXT_VALIDATION_STATUS,
            "execution_class": _EXECUTION_CLASS,
            "execution": "blocked_awaiting_explicit_user_authorization",
            "prepared_cases": list(_CASE_ORDER),
            "provider_calls": 0,
            "strict_pilot_calls": 0,
            "scored_calls": 0,
            "winner_selected": False,
            "credentials_accessed": 0,
        }

    def case(self, case_id: str) -> CrossProviderValidationCase:
        matches = tuple(case for case in self.contract.cases if case.case_id == case_id)
        if len(matches) != 1:
            raise _fail("validation_case_id")
        return matches[0]

    def build_request(self, case_id: str) -> NativeProviderRequest:
        case = self.case(case_id)
        calls = tuple(
            call for call in self._runner.plan.provider_calls
            if call.call_id == case.source_call_id
        )
        if len(calls) != 1:
            raise _fail("source_call_identity")
        call = calls[0]
        request = self._runner.build_native_request(call)
        configuration = request.request_configuration_selection.configuration
        try:
            payload = json.loads(request.payload_json.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _fail("frozen_request_payload") from exc
        expected_temperature = (
            None if case.temperature is None else Decimal(case.temperature)
        )
        if (
            call.candidate_id != case.candidate_id
            or call.provider != case.provider
            or call.model != case.model
            or call.api_family != case.api_family
            or call.fixture_id != case.fixture_id
            or call.workload_stage != case.workload_stage
            or call.request_configuration_id != case.request_configuration_id
            or call.request_configuration_hash != case.request_configuration_hash
            or call.prompt_ids != case.prompt_ids
            or call.prompt_hashes != case.prompt_hashes
            or call.schema_id != case.schema_id
            or call.schema_hash != case.schema_hash
            or call.role_mapping_id != case.role_mapping_id
            or call.role_mapping_hash != case.role_mapping_hash
            or call.adapter_id != case.adapter_id
            or call.adapter_hash != case.adapter_hash
            or request.payload_hash != case.request_hash
            or len(request.payload_json) != case.request_body_bytes
            or configuration.maximum_output_tokens != case.maximum_output_tokens
            or configuration.reasoning != case.reasoning
            or (
                None
                if configuration.temperature is None
                else Decimal(str(configuration.temperature))
            )
            != expected_temperature
            or configuration.streaming_enabled is not False
            or configuration.storage_configuration.get("value") is not False
            or payload.get("model") != case.model
            or payload.get("store") is not False
            or payload.get("stream") is not False
        ):
            raise _fail("frozen_request_identity")
        if case.provider == "OpenAI" and (
            payload.get("max_output_tokens") != case.maximum_output_tokens
            or payload.get("reasoning") != {"effort": case.reasoning}
            or Decimal(str(payload.get("temperature"))) != expected_temperature
            or set(payload)
            != {
                "input",
                "instructions",
                "max_output_tokens",
                "model",
                "reasoning",
                "store",
                "stream",
                "temperature",
                "text",
            }
        ):
            raise _fail("frozen_request_payload")
        if case.provider == "Google Gemini" and (
            payload.get("generation_config")
            != {
                "max_output_tokens": case.maximum_output_tokens,
                "thinking_level": case.reasoning,
            }
            or payload.get("response_format", {}).get("mime_type")
            != "application/json"
            or type(payload.get("response_format", {}).get("schema")) is not dict
            or set(payload)
            != {
                "generation_config",
                "input",
                "model",
                "response_format",
                "store",
                "stream",
                "system_instruction",
            }
        ):
            raise _fail("frozen_request_payload")
        return request

    def validate_historical_state(self, operational_root: str | Path) -> dict[str, Any]:
        root = Path(operational_root).resolve()
        loaded = []
        for binding in self.contract.historical_states:
            directory = root / binding.state_directory
            reservation = _load_immutable_state_record(
                directory / "reservation.json", binding.reservation_record_hash
            )
            result = _load_immutable_state_record(
                directory / "result.json", binding.result_record_hash
            )
            if (
                reservation.get("validation_case_id") != binding.case_id
                or result.get("validation_case_id") != binding.case_id
                or reservation.get("repository_head") != binding.repository_head
                or result.get("repository_head") != binding.repository_head
                or reservation.get("contract_hash") != binding.contract_hash
                or result.get("contract_hash") != binding.contract_hash
                or reservation.get("authorization_hash") != binding.authorization_hash
                or result.get("authorization_hash") != binding.authorization_hash
                or reservation.get("request_hash") != binding.request_hash
                or result.get("request_hash") != binding.request_hash
                or reservation.get("conservative_reservation_usd") != binding.exposure_usd
                or result.get("conservative_reservation_usd") != binding.exposure_usd
                or result.get("strict_pilot_record") is not False
                or result.get("scored_record") is not False
                or result.get("winner_selection") is not False
                or result.get("production_deployment") is not False
            ):
                raise _fail("historical_state_binding")
            if binding.case_id.endswith("v1"):
                if result.get("result_status") != "stopped" or result.get(
                    "safe_failure_classification"
                ) != "connection":
                    raise _fail("historical_state_binding")
            else:
                if (
                    result.get("result_status") != "accepted"
                    or result.get("safe_failure_classification") is not None
                    or result.get("parser_result") != "passed"
                    or result.get("schema_result") != "passed"
                    or result.get("validator_result") != "passed"
                    or result.get("physical_provider_attempts") != 1
                    or result.get("retry_count") != 0
                ):
                    raise _fail("historical_state_binding")
            loaded.append(
                {
                    "validation_case_id": binding.case_id,
                    "reservation_record_hash": reservation["record_hash"],
                    "result_record_hash": result["record_hash"],
                    "conservative_exposure_usd": binding.exposure_usd,
                }
            )
        return {
            "states": loaded,
            "historical_conservative_exposure_usd": (
                self.contract.historical_exposure_usd
            ),
        }

    def _state_paths(self, case_id: str, operational_root: str | Path) -> tuple[Path, Path, Path]:
        self.case(case_id)
        root = Path(operational_root).resolve() / _STATE_DIRECTORY / case_id
        return root, root / "reservation.json", root / "result.json"

    def validate_case_availability(self, case_id: str, operational_root: str | Path) -> None:
        state, reservation, result = self._state_paths(case_id, operational_root)
        if reservation.exists() or result.exists():
            raise _fail("case_already_reserved")
        if state.exists() and not state.is_dir():
            raise _fail("operational_state_path")

    def dry_run(
        self,
        case_id: str,
        *,
        operational_root: str | Path,
        transport: ConcreteLivePilotTransport,
    ) -> dict[str, Any]:
        case = self.case(case_id)
        request = self.build_request(case_id)
        history = self.validate_historical_state(operational_root)
        self.validate_case_availability(case_id, operational_root)
        runtime = _runtime_identity(transport)
        projection = transport.offline_request_projection(request)
        if projection["url"] != case.endpoint:
            raise _fail("transport_endpoint")
        pending = self._authorization_values(
            case,
            runtime_identity=runtime,
            authorized_at_utc="2000-01-01T00:00:00Z",
            status="pending_explicit_human_authorization",
        )
        pending["semantic_hash"] = _semantic_hash(pending, "semantic_hash")
        if set(pending) != _AUTHORIZATION_KEYS:
            raise _fail("authorization_shape")
        return {
            "status": "offline_dry_run_passed",
            "validation_case_id": case.case_id,
            "provider": case.provider,
            "model": case.model,
            "source_call_id": case.source_call_id,
            "request_configuration_id": case.request_configuration_id,
            "request_configuration_hash": case.request_configuration_hash,
            "request_hash": request.payload_hash,
            "request_body_bytes": len(request.payload_json),
            "input_token_bound_kind": case.input_token_bound_kind,
            "input_token_bound": case.input_token_bound,
            "transport_projection": projection,
            "runtime_identity": runtime,
            "runtime_identity_hash": _hash(runtime),
            "historical_state": history,
            "billing_context": case.billing_context,
            "conservative_reservation_usd": case.conservative_reservation_usd,
            "cumulative_worst_case_validation_exposure_usd": case.cumulative_exposure_usd,
            "validation_spend_remaining_after_reservation_usd": case.remaining_after_reservation_usd,
            "authorization_shape": "validated_pending_human_authorization",
            "credentials_accessed": 0,
            "provider_calls": 0,
        }

    def _provider_control(self, case: CrossProviderValidationCase) -> dict[str, Any]:
        if case.provider == "OpenAI":
            return {
                "provider": "OpenAI",
                "status": "confirmed",
                "external_prepaid_balance_usd": "5.00000000",
                "external_organization_spend_limit_usd": "5.00000000",
                "auto_reload": False,
                "endpoint_permission": "Responses (/v1/responses): Write",
            }
        if case.provider == "Google Gemini":
            return {
                "provider": "Google Gemini",
                "status": "confirmed",
                "billing_enabled": False,
                "tier": "free",
                "requests_per_minute": 5,
                "tokens_per_minute": 250000,
                "usage_at_setup": 0,
                "endpoint_permission": "Gemini Interactions API v1beta",
            }
        raise _fail("provider")

    def _authorization_values(
        self,
        case: CrossProviderValidationCase,
        *,
        runtime_identity: Mapping[str, Any],
        authorized_at_utc: str,
        status: str,
    ) -> dict[str, Any]:
        runtime = _validate_runtime_identity(runtime_identity)
        v1, v2 = self.contract.historical_states
        return {
            "authorization_id": f"human-{case.case_id}-authorization-v3",
            "authorization_version": "v3",
            "status": status,
            "execution_class": _EXECUTION_CLASS,
            "repository_head": self.repository_head,
            "contract_hash": self.contract.semantic_hash,
            "validation_case_id": case.case_id,
            "historical_predecessor_validation_case_id": case.historical_predecessor_case_id,
            "terra_v1_reservation_record_hash": v1.reservation_record_hash,
            "terra_v1_result_record_hash": v1.result_record_hash,
            "terra_v2_reservation_record_hash": v2.reservation_record_hash,
            "terra_v2_result_record_hash": v2.result_record_hash,
            "historical_conservative_exposure_usd": self.contract.historical_exposure_usd,
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
            "transport_implementation_sha256": self.contract.transport_implementation_sha256,
            "runtime_identity": runtime,
            "runtime_identity_hash": _hash(runtime),
            "maximum_provider_calls": 1,
            "retry_count": 0,
            "validation_spend_ceiling_usd": self.contract.total_spend_ceiling_usd,
            "conservative_reservation_usd": case.conservative_reservation_usd,
            "validation_spend_committed_before_usd": case.committed_before_usd,
            "cumulative_worst_case_validation_exposure_usd": case.cumulative_exposure_usd,
            "validation_spend_remaining_after_reservation_usd": case.remaining_after_reservation_usd,
            "billing_context": case.billing_context,
            "credential_readiness": {
                "environment_variable_name": case.credential_environment_variable,
                "status": "privately_confirmed",
            },
            "provider_control_confirmation": self._provider_control(case),
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
        case = self.case(case_id)
        values = self._authorization_values(
            case,
            runtime_identity=runtime_identity,
            authorized_at_utc=_timestamp(authorized_at_utc, code="authorization_timestamp"),
            status="approved",
        )
        values["semantic_hash"] = _semantic_hash(values, "semantic_hash")
        return values

    def validate_authorization(self, document: Mapping[str, Any]) -> CrossProviderAuthorization:
        if type(document) is not dict or set(document) != _AUTHORIZATION_KEYS:
            raise _fail("authorization_shape")
        stored = document.get("semantic_hash")
        if (
            type(stored) is not str
            or _SHA256.fullmatch(stored) is None
            or _semantic_hash(document, "semantic_hash") != stored
        ):
            raise _fail("authorization_hash")
        case = self.case(document.get("validation_case_id"))
        runtime = _validate_runtime_identity(document.get("runtime_identity"))
        expected = self._authorization_values(
            case,
            runtime_identity=runtime,
            authorized_at_utc=_timestamp(document.get("authorized_at_utc"), code="authorization_timestamp"),
            status="approved",
        )
        expected["semantic_hash"] = stored
        if _canonical(document) != _canonical(expected):
            raise _fail("authorization_binding")
        return CrossProviderAuthorization(
            stored,
            document["repository_head"],
            case.case_id,
            document["runtime_identity_hash"],
            document["maximum_provider_calls"],
            document["retry_count"],
        )

    def validate_offline_preflight(
        self,
        *,
        authorization_document: Mapping[str, Any],
        operational_root: str | Path,
        transport: ConcreteLivePilotTransport,
    ) -> tuple[CrossProviderAuthorization, dict[str, str], dict[str, Any]]:
        authorization = self.validate_authorization(authorization_document)
        case = self.case(authorization.case_id)
        request = self.build_request(case.case_id)
        self.validate_historical_state(operational_root)
        self.validate_case_availability(case.case_id, operational_root)
        runtime = _runtime_identity(transport)
        projection = transport.offline_request_projection(request)
        if projection["url"] != case.endpoint or _hash(runtime) != authorization.runtime_identity_hash:
            raise _fail("runtime_or_transport_binding")
        return authorization, runtime, projection

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
        self.validate_historical_state(operational_root)
        self.validate_case_availability(case.case_id, operational_root)
        _state, reservation_path, result_path = self._state_paths(
            case.case_id, operational_root
        )
        if getattr(transport, "invocation_count", None) != 0:
            raise _fail("physical_provider_attempt_count")
        credential = credential_resolver.resolve(
            CrossProviderCredentialReference(
                case.provider, case.credential_environment_variable
            )
        )
        started_at = _now(clock)
        v1, v2 = self.contract.historical_states
        reservation = {
            "record_type": "capstone_live_validation_reservation",
            "record_version": "v3",
            "execution_class": _EXECUTION_CLASS,
            "validation_case_id": case.case_id,
            "historical_predecessor_validation_case_id": case.historical_predecessor_case_id,
            "terra_v1_reservation_record_hash": v1.reservation_record_hash,
            "terra_v1_result_record_hash": v1.result_record_hash,
            "terra_v2_reservation_record_hash": v2.reservation_record_hash,
            "terra_v2_result_record_hash": v2.result_record_hash,
            "historical_conservative_exposure_usd": self.contract.historical_exposure_usd,
            "repository_head": self.repository_head,
            "contract_hash": self.contract.semantic_hash,
            "authorization_hash": authorization.semantic_hash,
            "runtime_identity_hash": authorization.runtime_identity_hash,
            "request_hash": request.payload_hash,
            "billing_context": case.billing_context,
            "conservative_reservation_usd": case.conservative_reservation_usd,
            "cumulative_worst_case_validation_exposure_usd": case.cumulative_exposure_usd,
            "validation_spend_ceiling_usd": self.contract.total_spend_ceiling_usd,
            "validation_spend_remaining_after_reservation_usd": case.remaining_after_reservation_usd,
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
        record = self._record_for_response(
            case=case,
            request=request,
            authorization=authorization,
            response=response,
            started_at=started_at,
            completed_at=_now(clock),
        )
        _write_exclusive(result_path, record)
        return record

    def _record_for_response(
        self,
        *,
        case: CrossProviderValidationCase,
        request: NativeProviderRequest,
        authorization: CrossProviderAuthorization,
        response: TransportResponse,
        started_at: str,
        completed_at: str,
    ) -> dict[str, Any]:
        if type(response) is not TransportResponse:
            raise _fail("transport_response")
        v1, v2 = self.contract.historical_states
        raw_hash = hashlib.sha256(response.response_bytes).hexdigest() if response.response_bytes else None
        base = {
            "record_type": "capstone_live_validation_result",
            "record_version": "v3",
            "execution_class": _EXECUTION_CLASS,
            "validation_id": f"{case.case_id}-attempt-1",
            "validation_case_id": case.case_id,
            "historical_predecessor_validation_case_id": case.historical_predecessor_case_id,
            "terra_v1_reservation_record_hash": v1.reservation_record_hash,
            "terra_v1_result_record_hash": v1.result_record_hash,
            "terra_v2_reservation_record_hash": v2.reservation_record_hash,
            "terra_v2_result_record_hash": v2.result_record_hash,
            "historical_conservative_exposure_usd": self.contract.historical_exposure_usd,
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
            "billing_context": case.billing_context,
            "conservative_reservation_usd": case.conservative_reservation_usd,
            "cumulative_worst_case_validation_exposure_usd": case.cumulative_exposure_usd,
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
            base["safe_failure_classification"] = response.failure_signal or "http_failure"
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
            base["normalized_semantic_hash"] = semantic.strict_parsed_semantic_payload_hash
            candidate = self._schema_registry.validate(case.schema_id, semantic)
            base["schema_result"] = "passed"
            validate_text_post_schema_candidate(candidate, schema_registry=self._schema_registry)
            base["validator_result"] = "passed"
            semantic_value = candidate.canonical_semantic_json.admitted.value
            base["semantic_summary"] = {
                "schema_id": case.schema_id,
                "canonical_top_level_fields": sorted(semantic_value),
            }
            if case.provider == "Google Gemini":
                base["estimated_validation_cost"] = {
                    "calculation_id": "capstone_free_tier_external_monetary_exposure_v1",
                    "provider": case.provider,
                    "model": case.model,
                    "billing_context": case.billing_context,
                    "currency": "USD",
                    "total_usd": "0.00000000",
                    "provider_usage": base["provider_usage"],
                    "strict_pricing_record": False,
                }
                base["cost_observation_status"] = (
                    "capstone_free_tier_no_billing_external_monetary_exposure_zero"
                )
            else:
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
                    if Decimal(estimate.total_usd) > Decimal(case.conservative_reservation_usd):
                        base["safe_failure_classification"] = "estimated_cost_exceeds_reservation"
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

    def inspect_result(self, case_id: str, operational_root: str | Path) -> dict[str, Any]:
        case = self.case(case_id)
        _state, _reservation, result_path = self._state_paths(case_id, operational_root)
        try:
            result = load_strict_contract_json(result_path)
        except (OSError, TypeError, ValueError) as exc:
            raise _fail("result_unavailable") from exc
        stored = result.get("record_hash")
        if (
            type(stored) is not str
            or _SHA256.fullmatch(stored) is None
            or _semantic_hash(result, "record_hash") != stored
            or result.get("record_version") != "v3"
            or result.get("validation_case_id") != case.case_id
            or result.get("repository_head") != self.repository_head
            or result.get("contract_hash") != self.contract.semantic_hash
            or result.get("request_hash") != case.request_hash
            or result.get("conservative_reservation_usd") != case.conservative_reservation_usd
            or result.get("cumulative_worst_case_validation_exposure_usd") != case.cumulative_exposure_usd
            or result.get("validation_spend_remaining_usd") != case.remaining_after_reservation_usd
            or result.get("physical_provider_attempts") != 1
            or result.get("retry_count") != 0
            or result.get("strict_pilot_record") is not False
            or result.get("scored_record") is not False
            or result.get("winner_selection") is not False
            or result.get("production_deployment") is not False
        ):
            raise _fail("result_binding")
        return {
            key: result[key]
            for key in (
                "validation_case_id",
                "provider",
                "model",
                "fixture_id",
                "result_status",
                "safe_finish_reason",
                "provider_response_received",
                "latency_seconds",
                "provider_usage",
                "estimated_validation_cost",
                "observed_validation_cost_usd",
                "cost_observation_status",
                "billing_context",
                "parser_result",
                "schema_result",
                "validator_result",
                "semantic_summary",
                "raw_response_hash",
                "normalized_semantic_hash",
                "record_hash",
            )
        }


def build_capstone_cross_provider_validation(
    *,
    repository_root: str | Path,
    repository_head: str,
    require_clean_repository: bool = True,
) -> CapstoneCrossProviderValidation:
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
    legacy = build_capstone_live_validation(
        repository_root=root,
        repository_head=repository_head,
        require_clean_repository=require_clean_repository,
    )
    if (
        legacy.readiness_projection()["provider_calls"] != 0
        or legacy._runner.readiness_projection()["provider_calls_allowed"] is not False
        or legacy._runner.readiness_projection()["pilot_calls_allowed"] is not False
        or legacy._runner.readiness_projection()["scored_calls_allowed"] is not False
    ):
        raise _fail("strict_runner_boundary")
    return CapstoneCrossProviderValidation(
        repository_root=root,
        repository_head=repository_head,
        contract=contract,
        runner=legacy._runner,
        adapters=legacy._adapters,
        schema_registry=legacy._schema_registry,
        require_clean_repository_on_execute=require_clean_repository,
    )
