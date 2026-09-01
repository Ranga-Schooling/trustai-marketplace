"""Single-use corrected Gemini/PT1 V2 Capstone validation.

Everything except :meth:`CapstoneGeminiV2Validation.execute_one` is
provider-free.  The V1 HTTP-400 observation and all earlier Capstone state are
immutable predecessors; this module cannot mutate strict pilot or scored state.
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

from app.services.evaluation_capstone_cross_provider_validation import (
    build_capstone_cross_provider_validation,
)
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
)
from app.services.evaluation_contract_identity import load_strict_contract_json
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


CAPSTONE_GEMINI_V2_VALIDATION_STATUS = (
    "CAPSTONE_GEMINI_V2_VALIDATION_READY_AWAITING_USER"
)
_CONTRACT_FILE = "capstone-gemini-text-validation.v4.json"
_CONTRACT_HASH = "8a9632559202da1849f83afc4cd38e5a20d4cb29b2cff7c57f9705c528722a7a"
_EXECUTION_CLASS = "capstone_live_validation"
_STATE_DIRECTORY = "capstone-gemini-text-validation-v4"
_V3_STATE_DIRECTORY = "capstone-cross-provider-text-validation-v3"
_CASE_ID = "capval-gemini-flash-pt1-v2"
_V1_CASE_ID = "capval-gemini-flash-pt1-v1"
_SOL_CASE_ID = "capval-openai-sol-pt1-v1"
_HEAD = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _fail(code: str) -> CapstoneLiveValidationError:
    return CapstoneLiveValidationError(code)


@dataclass(frozen=True, slots=True)
class GeminiV2Case:
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
    temperature: None
    input_token_bound_kind: str
    input_token_bound: int
    billing_context: str
    conservative_reservation_usd: str
    cumulative_exposure_usd: str
    remaining_after_reservation_usd: str
    credential_environment_variable: str
    transport_binding_id: str
    provider_limits: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class GeminiV2Contract:
    artifact_id: str
    artifact_version: str
    semantic_hash: str
    total_spend_ceiling_usd: str
    historical_exposure_usd: str
    remaining_after_reservation_usd: str
    transport_binding_id: str
    transport_implementation_sha256: str
    request_builder_sha256: str
    requirements_sha256: str
    predecessor_bindings: Mapping[str, Any]
    case: GeminiV2Case


@dataclass(frozen=True, slots=True)
class GeminiV2Authorization:
    semantic_hash: str
    case_id: str
    runtime_identity_hash: str


@dataclass(frozen=True, slots=True)
class GeminiV2CredentialReference:
    provider: str
    environment_variable_name: str

    def __post_init__(self) -> None:
        if (
            self.provider != "Google Gemini"
            or self.environment_variable_name != "GEMINI_API_KEY"
        ):
            raise _fail("credential_reference")


def _load_contract(root: Path) -> GeminiV2Contract:
    raw = load_strict_contract_json(
        root / "docs/testing/ai-evaluation" / _CONTRACT_FILE
    )
    identity = raw.get("specification_identity")
    if (
        raw.get("artifact_id") != "capstone_gemini_text_validation_v4"
        or raw.get("artifact_version") != "v4"
        or raw.get("status") != "ready_awaiting_explicit_user_authorization"
        or raw.get("execution_class") != _EXECUTION_CLASS
        or raw.get("case_order") != [_CASE_ID]
        or type(identity) is not dict
        or identity.get("semantic_hash") != _CONTRACT_HASH
        or _artifact_hash(raw) != _CONTRACT_HASH
        or any(value is not False for value in raw.get("strict_separation", {}).values())
    ):
        raise _fail("contract_identity")
    execution = raw.get("execution_policy")
    boundary = raw.get("execution_boundary")
    spend = raw.get("spend_guard")
    transport = raw.get("transport_binding")
    predecessor = raw.get("predecessor_bindings")
    correction = raw.get("correction")
    cases = raw.get("cases")
    if (
        type(execution) is not dict
        or execution.get("maximum_provider_calls_per_authorization") != 1
        or execution.get("maximum_lifetime_provider_calls_per_case") != 1
        or execution.get("maximum_new_provider_calls") != 1
        or execution.get("automatic_retry_count") != 0
        or execution.get("automatic_next_case_allowed") is not False
        or execution.get("stop_after_provider_call") is not True
        or execution.get("reservation_marker_must_precede_provider_invocation") is not True
        or execution.get("existing_case_reservation_or_result_blocks_execution") is not True
        or type(boundary) is not dict
        or boundary.get("provider_calls_allowed_by_artifact") is not False
        or boundary.get("pilot_calls_allowed") is not False
        or boundary.get("scored_calls_allowed") is not False
        or boundary.get("provider_calls_completed") != 0
        or boundary.get("winner_selected") is not False
        or boundary.get("production_deployment_authorized") is not False
        or type(spend) is not dict
        or type(transport) is not dict
        or type(predecessor) is not dict
        or type(correction) is not dict
        or type(cases) is not list
        or len(cases) != 1
    ):
        raise _fail("contract_boundary")
    ceiling = _money(spend.get("total_validation_spend_ceiling_usd"), code="ceiling")
    historical = _money(
        spend.get("historical_conservative_exposure_usd"), code="historical"
    )
    reservation = _money(
        spend.get("gemini_v2_external_monetary_exposure_usd"),
        code="reservation",
    )
    cumulative = _money(
        spend.get("cumulative_after_gemini_v2_reservation_usd"),
        code="cumulative",
    )
    remaining = _money(
        spend.get("remaining_after_gemini_v2_reservation_usd"),
        code="remaining",
    )
    if (
        ceiling != Decimal("1.00000000")
        or historical != Decimal("0.21030200")
        or reservation != Decimal("0.00000000")
        or cumulative != historical + reservation
        or remaining != ceiling - cumulative
        or spend.get("strict_pilot_budget_is_not_a_source_or_sink") is not True
        or spend.get("historical_exposure_release_allowed") is not False
        or spend.get("free_tier_zero_is_capstone_external_exposure_only") is not True
        or spend.get("strict_gemini_pricing_binding_mutation_allowed") is not False
    ):
        raise _fail("spend_guard")
    if (
        correction.get("classification") != "small_proven_integration_defect"
        or correction.get("scope")
        != "gemini_interactions_user_input_step_discriminator_only"
        or correction.get("fixture_meaning_changed") is not False
        or correction.get("prompt_meaning_changed") is not False
        or correction.get("canonical_output_schema_changed") is not False
        or correction.get("request_configuration_changed") is not False
        or correction.get("model_changed") is not False
        or correction.get("v1_outer_input_object")
        != {"role": "user", "content": "unchanged"}
        or correction.get("v2_outer_input_object")
        != {"type": "user_input", "content": "unchanged"}
    ):
        raise _fail("correction_scope")
    if (
        transport.get("binding_id") != "capstone_gemini_v2_httpx_transport_v1"
        or transport.get("http_client_package") != "httpx"
        or transport.get("http_client_requirement") != "httpx>=0.27"
        or transport.get("redirects_allowed") is not False
        or transport.get("automatic_retry_count") != 0
        or _file_sha256(root / transport.get("implementation_path", ""))
        != transport.get("implementation_sha256")
        or _file_sha256(root / transport.get("request_builder_path", ""))
        != transport.get("request_builder_sha256")
        or _file_sha256(root / transport.get("requirements_path", ""))
        != transport.get("requirements_sha256")
    ):
        raise _fail("transport_binding")
    required_predecessor = {
        "v3_contract_hash": "fa141065f8fe374d4b43409cefb2fec58e66f3f949d733ea4bf9cdc254635617",
        "terra_v1_reservation_record_hash": "a9d604c30f16ecd4525d533955f9701ea15ed78c35cb7fff703c3e3761cd1bab",
        "terra_v1_result_record_hash": "554fdf1685a4b766698d9af255fd7921e3500a7390915957831eab440582d24e",
        "terra_v2_reservation_record_hash": "6a66fa758fa20d231a02649263fddcdb53da314b2a1f6a9c9853b10e58610ed3",
        "terra_v2_result_record_hash": "1c4b25beb71569d68642e9f6d554b7473d042c779b8f26c930ca63caa9959386",
        "sol_v1_reservation_record_hash": "115405478d45a6cedfb406bf774dfd9a7f47df186f01513f557797c1e815be2a",
        "sol_v1_result_record_hash": "352beabadd1ee86c0bc51f7b4c20dcfc66d2fd1574a947f1ef64660e43b4e167",
        "gemini_v1_repository_head": "6f271faa7405c3f6ecf7fc5f81f874a295a01601",
        "gemini_v1_authorization_hash": "84a0ccbf16292ed774a32e7d9640481e868488336c35533af22a4afe5b2cf022",
        "gemini_v1_reservation_record_hash": "a891cb4fb77d86c073ff204fbdaffd0ff5d05d3e05a9c88d778e273a3b6e4c01",
        "gemini_v1_result_record_hash": "222a10f499873278a526e12bd1c44b62d104a07f477162b1bba75860db488da8",
        "gemini_v1_request_hash": "00f29bb98c9840ffb6d1e61fc080c607aa54a2b20ca862c58f862d08ed013584",
        "gemini_v1_http_status": 400,
        "gemini_v1_safe_failure_classification": "http_failure",
        "gemini_v1_physical_provider_attempts": 1,
        "gemini_v1_retry_count": 0,
        "v3_state_directory": ".capstone-live-validation/capstone-cross-provider-text-validation-v3",
    }
    if predecessor != required_predecessor:
        raise _fail("predecessor_binding")
    item = cases[0]
    if type(item) is not dict:
        raise _fail("case_contract")
    case = GeminiV2Case(
        case_id=item.get("validation_case_id"),
        predecessor_case_id=item.get("predecessor_validation_case_id"),
        predecessor_result_record_hash=item.get("predecessor_result_record_hash"),
        source_call_id=item.get("source_call_id"),
        candidate_id=item.get("candidate_id"),
        provider=item.get("provider"),
        model=item.get("model"),
        api_family=item.get("api_family"),
        endpoint=item.get("endpoint"),
        fixture_id=item.get("fixture_id"),
        workload_stage=item.get("workload_stage"),
        request_configuration_id=item.get("request_configuration_id"),
        request_configuration_hash=item.get("request_configuration_hash"),
        request_hash=item.get("request_hash"),
        request_body_bytes=item.get("request_body_bytes"),
        prompt_ids=tuple(item.get("prompt_ids", ())),
        prompt_hashes=tuple(item.get("prompt_hashes", ())),
        schema_id=item.get("schema_id"),
        schema_hash=item.get("schema_hash"),
        role_mapping_id=item.get("role_mapping_id"),
        role_mapping_hash=item.get("role_mapping_hash"),
        adapter_id=item.get("adapter_id"),
        adapter_hash=item.get("adapter_hash"),
        maximum_output_tokens=item.get("maximum_output_tokens"),
        reasoning=item.get("reasoning"),
        temperature=item.get("temperature"),
        input_token_bound_kind=item.get("input_token_bound_kind"),
        input_token_bound=item.get("input_token_bound"),
        billing_context=item.get("billing_context"),
        conservative_reservation_usd=item.get("conservative_reservation_usd"),
        cumulative_exposure_usd=item.get(
            "cumulative_worst_case_validation_exposure_usd"
        ),
        remaining_after_reservation_usd=item.get("remaining_after_reservation_usd"),
        credential_environment_variable=item.get("credential_environment_variable"),
        transport_binding_id=item.get("transport_binding_id"),
        provider_limits=item.get("provider_limits"),
    )
    expected = (
        _CASE_ID,
        _V1_CASE_ID,
        predecessor["gemini_v1_result_record_hash"],
        "call-0005",
        "gemini_unified_v1",
        "Google Gemini",
        "gemini-3.7-flash",
        "Gemini Interactions API v1beta with Api-Revision 2026-05-20",
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        "PT1",
        "text_analysis",
        "gemini_flash_text_pilot_v1",
        "8644e02a24cff69f6619f744e02c6b55648e9463f76b30453b81dc04edbe466b",
        "7ba77e1a55b8171d55d95aff39a7ffb171f8ba4eaf91a3dba342754ec4f57640",
        6235,
    )
    actual = (
        case.case_id,
        case.predecessor_case_id,
        case.predecessor_result_record_hash,
        case.source_call_id,
        case.candidate_id,
        case.provider,
        case.model,
        case.api_family,
        case.endpoint,
        case.fixture_id,
        case.workload_stage,
        case.request_configuration_id,
        case.request_configuration_hash,
        case.request_hash,
        case.request_body_bytes,
    )
    if (
        actual != expected
        or case.prompt_ids != ("text_system_v1", "text_input_v1")
        or len(case.prompt_hashes) != 2
        or case.schema_id != "text_output_schema_v1"
        or case.role_mapping_id != "gemini_interactions_flash_v1"
        or case.adapter_id != "gemini_interactions_adapter_v1"
        or case.maximum_output_tokens != 4096
        or case.reasoning != "medium"
        or case.temperature is not None
        or case.input_token_bound != 6235
        or case.billing_context != "provider_free_tier_no_billing_enabled"
        or case.conservative_reservation_usd != "0.00000000"
        or case.cumulative_exposure_usd != "0.21030200"
        or case.remaining_after_reservation_usd != "0.78969800"
        or case.credential_environment_variable != "GEMINI_API_KEY"
        or case.transport_binding_id != transport["binding_id"]
        or case.provider_limits
        != {"requests_per_minute": 5, "tokens_per_minute": 250000, "usage_at_setup": 0}
    ):
        raise _fail("case_contract")
    return GeminiV2Contract(
        artifact_id=raw["artifact_id"],
        artifact_version=raw["artifact_version"],
        semantic_hash=_CONTRACT_HASH,
        total_spend_ceiling_usd=spend["total_validation_spend_ceiling_usd"],
        historical_exposure_usd=spend["historical_conservative_exposure_usd"],
        remaining_after_reservation_usd=spend[
            "remaining_after_gemini_v2_reservation_usd"
        ],
        transport_binding_id=transport["binding_id"],
        transport_implementation_sha256=transport["implementation_sha256"],
        request_builder_sha256=transport["request_builder_sha256"],
        requirements_sha256=transport["requirements_sha256"],
        predecessor_bindings=predecessor,
        case=case,
    )


class CapstoneGeminiV2Validation:
    def __init__(
        self,
        *,
        repository_root: Path,
        repository_head: str,
        contract: GeminiV2Contract,
        legacy: Any,
        require_clean_repository_on_execute: bool,
    ) -> None:
        self.repository_root = repository_root
        self.repository_head = repository_head
        self.contract = contract
        self._legacy = legacy
        self._runner = legacy._runner
        self._adapters = legacy._adapters
        self._schema_registry = legacy._schema_registry
        self._require_clean_repository_on_execute = require_clean_repository_on_execute
        self.build_request(_CASE_ID)

    def readiness_projection(self) -> dict[str, Any]:
        return {
            "status": CAPSTONE_GEMINI_V2_VALIDATION_STATUS,
            "execution_class": _EXECUTION_CLASS,
            "execution": "blocked_awaiting_explicit_user_authorization",
            "prepared_cases": [_CASE_ID],
            "provider_calls": 0,
            "strict_pilot_calls": 0,
            "scored_calls": 0,
            "winner_selected": False,
            "credentials_accessed": 0,
        }

    def case(self, case_id: str) -> GeminiV2Case:
        if case_id != self.contract.case.case_id:
            raise _fail("validation_case_id")
        return self.contract.case

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
        payload = request.payload
        provider_input = payload.get("input")
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
            or configuration.temperature is not None
            or configuration.streaming_enabled is not False
            or configuration.storage_configuration.get("value") is not False
            or payload.get("model") != case.model
            or payload.get("system_instruction") is None
            or payload.get("store") is not False
            or payload.get("stream") is not False
            or payload.get("generation_config")
            != {"max_output_tokens": 4096, "thinking_level": "medium"}
            or payload.get("response_format", {}).get("type") != "text"
            or payload.get("response_format", {}).get("mime_type")
            != "application/json"
            or type(payload.get("response_format", {}).get("schema")) is not dict
            or type(provider_input) is not list
            or len(provider_input) != 1
            or set(provider_input[0]) != {"type", "content"}
            or provider_input[0].get("type") != "user_input"
            or type(provider_input[0].get("content")) is not list
            or "role" in provider_input[0]
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
            raise _fail("corrected_request_identity")
        return request

    def _state_paths(
        self, case_id: str, operational_root: str | Path
    ) -> tuple[Path, Path, Path]:
        self.case(case_id)
        root = Path(operational_root).resolve() / _STATE_DIRECTORY / case_id
        return root, root / "reservation.json", root / "result.json"

    def validate_case_availability(
        self, case_id: str, operational_root: str | Path
    ) -> None:
        state, reservation, result = self._state_paths(case_id, operational_root)
        if reservation.exists() or result.exists():
            raise _fail("case_already_reserved")
        if state.exists() and not state.is_dir():
            raise _fail("operational_state_path")

    def validate_historical_state(self, operational_root: str | Path) -> dict[str, Any]:
        root = Path(operational_root).resolve()
        terra = self._legacy.validate_historical_state(root)
        v3_root = root / _V3_STATE_DIRECTORY
        bindings = self.contract.predecessor_bindings
        sol_reservation = _load_immutable_state_record(
            v3_root / _SOL_CASE_ID / "reservation.json",
            bindings["sol_v1_reservation_record_hash"],
        )
        sol_result = _load_immutable_state_record(
            v3_root / _SOL_CASE_ID / "result.json",
            bindings["sol_v1_result_record_hash"],
        )
        gemini_reservation = _load_immutable_state_record(
            v3_root / _V1_CASE_ID / "reservation.json",
            bindings["gemini_v1_reservation_record_hash"],
        )
        gemini_result = _load_immutable_state_record(
            v3_root / _V1_CASE_ID / "result.json",
            bindings["gemini_v1_result_record_hash"],
        )
        if (
            sol_reservation.get("validation_case_id") != _SOL_CASE_ID
            or sol_result.get("validation_case_id") != _SOL_CASE_ID
            or sol_result.get("result_status") != "accepted"
            or sol_result.get("parser_result") != "passed"
            or sol_result.get("schema_result") != "passed"
            or sol_result.get("validator_result") != "passed"
            or sol_result.get("physical_provider_attempts") != 1
            or sol_result.get("retry_count") != 0
            or gemini_reservation.get("validation_case_id") != _V1_CASE_ID
            or gemini_result.get("validation_case_id") != _V1_CASE_ID
            or gemini_reservation.get("repository_head")
            != bindings["gemini_v1_repository_head"]
            or gemini_result.get("repository_head")
            != bindings["gemini_v1_repository_head"]
            or gemini_reservation.get("authorization_hash")
            != bindings["gemini_v1_authorization_hash"]
            or gemini_result.get("authorization_hash")
            != bindings["gemini_v1_authorization_hash"]
            or gemini_reservation.get("request_hash")
            != bindings["gemini_v1_request_hash"]
            or gemini_result.get("request_hash") != bindings["gemini_v1_request_hash"]
            or gemini_result.get("result_status") != "stopped"
            or gemini_result.get("http_status") != bindings["gemini_v1_http_status"]
            or gemini_result.get("safe_failure_classification")
            != bindings["gemini_v1_safe_failure_classification"]
            or gemini_result.get("physical_provider_attempts")
            != bindings["gemini_v1_physical_provider_attempts"]
            or gemini_result.get("retry_count") != bindings["gemini_v1_retry_count"]
            or gemini_result.get("parser_result") != "not_reached"
            or gemini_result.get("schema_result") != "not_reached"
            or gemini_result.get("validator_result") != "not_reached"
            or any(
                record.get(field) is not False
                for record in (sol_result, gemini_result)
                for field in (
                    "strict_pilot_record",
                    "scored_record",
                    "winner_selection",
                    "production_deployment",
                )
            )
        ):
            raise _fail("historical_state_binding")
        return {
            "terra": terra,
            "sol": {
                "validation_case_id": _SOL_CASE_ID,
                "reservation_record_hash": sol_reservation["record_hash"],
                "result_record_hash": sol_result["record_hash"],
                "result_status": "accepted",
            },
            "gemini_v1": {
                "validation_case_id": _V1_CASE_ID,
                "reservation_record_hash": gemini_reservation["record_hash"],
                "result_record_hash": gemini_result["record_hash"],
                "result_status": "stopped",
                "http_status": 400,
                "safe_failure_classification": "http_failure",
            },
        }

    def _authorization_values(
        self,
        case: GeminiV2Case,
        *,
        runtime_identity: Mapping[str, Any],
        authorized_at_utc: str,
        status: str,
    ) -> dict[str, Any]:
        runtime = _validate_runtime_identity(runtime_identity)
        binding = self.contract.predecessor_bindings
        return {
            "authorization_id": f"human-{case.case_id}-authorization-v4",
            "authorization_version": "v4",
            "status": status,
            "execution_class": _EXECUTION_CLASS,
            "repository_head": self.repository_head,
            "contract_hash": self.contract.semantic_hash,
            "validation_case_id": case.case_id,
            "predecessor_validation_case_id": case.predecessor_case_id,
            "predecessor_reservation_record_hash": binding[
                "gemini_v1_reservation_record_hash"
            ],
            "predecessor_result_record_hash": binding["gemini_v1_result_record_hash"],
            "predecessor_http_status": binding["gemini_v1_http_status"],
            "sol_result_record_hash": binding["sol_v1_result_record_hash"],
            "source_call_id": case.source_call_id,
            "candidate_id": case.candidate_id,
            "provider": case.provider,
            "model": case.model,
            "fixture_id": case.fixture_id,
            "workload_stage": case.workload_stage,
            "request_configuration_id": case.request_configuration_id,
            "request_configuration_hash": case.request_configuration_hash,
            "request_hash": case.request_hash,
            "request_builder_sha256": self.contract.request_builder_sha256,
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
                self.contract.historical_exposure_usd
            ),
            "cumulative_worst_case_validation_exposure_usd": (
                case.cumulative_exposure_usd
            ),
            "validation_spend_remaining_after_reservation_usd": (
                case.remaining_after_reservation_usd
            ),
            "billing_context": case.billing_context,
            "credential_readiness": {
                "environment_variable_name": case.credential_environment_variable,
                "status": "privately_confirmed",
            },
            "provider_control_confirmation": {
                "provider": "Google Gemini",
                "status": "confirmed",
                "billing_enabled": False,
                "tier": "free",
                "requests_per_minute": 5,
                "tokens_per_minute": 250000,
                "usage_at_setup": 0,
                "endpoint_permission": "Gemini Interactions API v1beta",
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
        values = self._authorization_values(
            self.case(case_id),
            runtime_identity=runtime_identity,
            authorized_at_utc=_timestamp(
                authorized_at_utc, code="authorization_timestamp"
            ),
            status="approved",
        )
        values["semantic_hash"] = _semantic_hash(values, "semantic_hash")
        self.validate_authorization(values)
        return values

    def validate_authorization(
        self, document: Mapping[str, Any]
    ) -> GeminiV2Authorization:
        if type(document) is not dict:
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
            authorized_at_utc=_timestamp(
                document.get("authorized_at_utc"), code="authorization_timestamp"
            ),
            status="approved",
        )
        expected["semantic_hash"] = stored
        if set(document) != set(expected) or _canonical(document) != _canonical(expected):
            raise _fail("authorization_binding")
        return GeminiV2Authorization(
            semantic_hash=stored,
            case_id=case.case_id,
            runtime_identity_hash=document["runtime_identity_hash"],
        )

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
        return {
            "status": "offline_dry_run_passed",
            "validation_case_id": case.case_id,
            "source_call_id": case.source_call_id,
            "provider": case.provider,
            "model": case.model,
            "fixture_id": case.fixture_id,
            "request_configuration_id": case.request_configuration_id,
            "request_configuration_hash": case.request_configuration_hash,
            "request_hash": request.payload_hash,
            "request_body_bytes": len(request.payload_json),
            "input_envelope": "user_input_step",
            "transport_projection": projection,
            "runtime_identity": runtime,
            "runtime_identity_hash": _hash(runtime),
            "historical_state": history,
            "billing_context": case.billing_context,
            "conservative_reservation_usd": case.conservative_reservation_usd,
            "cumulative_worst_case_validation_exposure_usd": (
                case.cumulative_exposure_usd
            ),
            "validation_spend_remaining_after_reservation_usd": (
                case.remaining_after_reservation_usd
            ),
            "authorization_shape": "validated_pending_human_authorization",
            "credentials_accessed": 0,
            "provider_calls": 0,
        }

    def validate_offline_preflight(
        self,
        *,
        authorization_document: Mapping[str, Any],
        operational_root: str | Path,
        transport: ConcreteLivePilotTransport,
    ) -> tuple[GeminiV2Authorization, dict[str, str], dict[str, Any]]:
        authorization = self.validate_authorization(authorization_document)
        case = self.case(authorization.case_id)
        request = self.build_request(case.case_id)
        self.validate_historical_state(operational_root)
        self.validate_case_availability(case.case_id, operational_root)
        runtime = _runtime_identity(transport)
        projection = transport.offline_request_projection(request)
        if (
            projection["url"] != case.endpoint
            or _hash(runtime) != authorization.runtime_identity_hash
        ):
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
            GeminiV2CredentialReference(
                case.provider, case.credential_environment_variable
            )
        )
        started_at = _now(clock)
        binding = self.contract.predecessor_bindings
        reservation = {
            "record_type": "capstone_live_validation_reservation",
            "record_version": "v4",
            "execution_class": _EXECUTION_CLASS,
            "validation_case_id": case.case_id,
            "predecessor_validation_case_id": case.predecessor_case_id,
            "predecessor_reservation_record_hash": binding[
                "gemini_v1_reservation_record_hash"
            ],
            "predecessor_result_record_hash": binding["gemini_v1_result_record_hash"],
            "repository_head": self.repository_head,
            "contract_hash": self.contract.semantic_hash,
            "authorization_hash": authorization.semantic_hash,
            "runtime_identity_hash": authorization.runtime_identity_hash,
            "request_hash": request.payload_hash,
            "billing_context": case.billing_context,
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
        case: GeminiV2Case,
        request: NativeProviderRequest,
        authorization: GeminiV2Authorization,
        response: TransportResponse,
        started_at: str,
        completed_at: str,
    ) -> dict[str, Any]:
        if type(response) is not TransportResponse:
            raise _fail("transport_response")
        binding = self.contract.predecessor_bindings
        raw_hash = (
            hashlib.sha256(response.response_bytes).hexdigest()
            if response.response_bytes
            else None
        )
        base = {
            "record_type": "capstone_live_validation_result",
            "record_version": "v4",
            "execution_class": _EXECUTION_CLASS,
            "validation_id": f"{case.case_id}-attempt-1",
            "validation_case_id": case.case_id,
            "predecessor_validation_case_id": case.predecessor_case_id,
            "predecessor_reservation_record_hash": binding[
                "gemini_v1_reservation_record_hash"
            ],
            "predecessor_result_record_hash": binding["gemini_v1_result_record_hash"],
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
                candidate, schema_registry=self._schema_registry
            )
            base["validator_result"] = "passed"
            semantic_value = candidate.canonical_semantic_json.admitted.value
            base["semantic_summary"] = {
                "schema_id": case.schema_id,
                "canonical_top_level_fields": sorted(semantic_value),
            }
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

    def inspect_result(
        self, case_id: str, operational_root: str | Path
    ) -> dict[str, Any]:
        case = self.case(case_id)
        _state, _reservation, result_path = self._state_paths(
            case_id, operational_root
        )
        try:
            result = load_strict_contract_json(result_path)
        except (OSError, TypeError, ValueError) as exc:
            raise _fail("result_unavailable") from exc
        stored = result.get("record_hash")
        if (
            type(stored) is not str
            or _SHA256.fullmatch(stored) is None
            or _semantic_hash(result, "record_hash") != stored
            or result.get("record_version") != "v4"
            or result.get("validation_case_id") != case.case_id
            or result.get("repository_head") != self.repository_head
            or result.get("contract_hash") != self.contract.semantic_hash
            or result.get("request_hash") != case.request_hash
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


def build_capstone_gemini_v2_validation(
    *,
    repository_root: str | Path,
    repository_head: str,
    require_clean_repository: bool = True,
) -> CapstoneGeminiV2Validation:
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
    legacy = build_capstone_cross_provider_validation(
        repository_root=root,
        repository_head=repository_head,
        require_clean_repository=require_clean_repository,
    )
    strict = legacy._runner.readiness_projection()
    if (
        legacy.readiness_projection()["provider_calls"] != 0
        or strict["provider_calls_allowed"] is not False
        or strict["pilot_calls_allowed"] is not False
        or strict["scored_calls_allowed"] is not False
    ):
        raise _fail("strict_runner_boundary")
    return CapstoneGeminiV2Validation(
        repository_root=root,
        repository_head=repository_head,
        contract=contract,
        legacy=legacy,
        require_clean_repository_on_execute=require_clean_repository,
    )
