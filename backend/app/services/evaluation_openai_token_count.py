"""One-shot OpenAI input-token preflight for frozen pilot call-0003.

This module is deliberately separate from the pilot generation transport.  Its
only live capability is one ``POST /v1/responses/input_tokens`` invocation
after a same-day, hash-bound, externally supplied authorization validates.  It
cannot call ``/v1/responses``, retry, generate a model response, or authorize a
pilot/scored run.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
import copy
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Protocol

from app.services.evaluation_contract_identity import load_strict_contract_json
from app.services.evaluation_live_gate import (
    SameDayCertification,
    load_same_day_certification,
)
from app.services.evaluation_live_transport import LazyEnvironmentCredentialResolver
from app.services.evaluation_pilot_runner import (
    CredentialReference,
    NativeProviderRequest,
    ProviderFreePilotRunner,
    _ResolvedCredential,
    _TRANSPORT_SECRET_TOKEN,
    build_provider_free_pilot_runner,
)
from app.services.evaluation_transport_capture import CanonicalRawResponseAccumulator


OPENAI_TOKEN_COUNT_PATH = "/v1/responses/input_tokens"
OPENAI_TOKEN_COUNT_ENDPOINT = f"https://api.openai.com{OPENAI_TOKEN_COUNT_PATH}"
_ROOT = Path(__file__).resolve().parents[3]
_CALL_ID = "call-0003"
_EXPECTED = {
    "candidate_id": "openai_unified_balanced_v1",
    "provider": "OpenAI",
    "model": "gpt-5.6-terra",
    "fixture_id": "PT1",
    "workload_stage": "text_analysis",
    "topology_id": "single_call_text",
    "request_configuration_id": "openai_terra_text_pilot_v1",
    "request_configuration_hash": (
        "0eca58d264b7af9e48af182f8d3ce8a0a417db8201328b70fdab77b6a4bae893"
    ),
}
_EXPECTED_ORIGINAL_REQUEST_HASH = (
    "97f8752bb33994a00018a15ff62d79419069397b223cc5f60770def973ebc266"
)
_EXPECTED_ORIGINAL_REQUEST_BYTES = 6249
_EXPECTED_ORIGINAL_FIELDS = frozenset(
    {
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
)
_COUNT_ENDPOINT_FIELDS = frozenset(
    {
        "conversation",
        "input",
        "instructions",
        "model",
        "parallel_tool_calls",
        "personality",
        "previous_response_id",
        "reasoning",
        "text",
        "tool_choice",
        "tools",
        "truncation",
    }
)
_GENERATION_ONLY_FIELDS = frozenset(
    {"max_output_tokens", "store", "stream", "temperature"}
)
_REQUIRED_COUNT_FIELDS = frozenset({"input", "instructions", "model"})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_UTC_SECONDS = re.compile(
    r"(?:19|20)[0-9]{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z\Z"
)
_MONEY = re.compile(r"(?:0|[1-9][0-9]*)\.[0-9]{2,8}\Z")
_CEILING = Decimal("5.00")
_SHORT_THRESHOLD = 272_000
_SHORT_INPUT_RATE = Decimal("0.0000025")
_SHORT_OUTPUT_RESERVATION = Decimal("0.04915200")
_LONG_INPUT_RATE = Decimal("0.000005")
_LONG_OUTPUT_RESERVATION = Decimal("0.07372800")
_PRICING_SNAPSHOT_ID = "pricing_snapshot_v1"
_EXPECTED_CERTIFICATION_HASH = (
    "b3ac44da808b84bee117e1146aa01acd2d4debedcaf844d539a4b9854ce9ee34"
)
_EXPECTED_PRICING_HASH = (
    "0467643eafbe55e6e2215c9ad0e0576dac2d0d157a94418eef23382b0ec09282"
)
_EXPECTED_BUDGET_HASH = (
    "7e4065dd69809f581ca475a3a9da8d4669b5961274da0c43574b844f3c12f824"
)
_EXPECTED_REGION_HASH = (
    "0c79df332d87bfdf1c902df26df9701bf531100f691650286eb7d5dd38627555"
)
_EVIDENCE_ID = "openai_input_token_count_call_0003_v1"
_EVIDENCE_VERSION = "v1"
_AUTHORIZATION_ID = "openai_token_count_call_0003_v1"
_AUTHORIZATION_VERSION = "v1"
_AUTHORIZATION_SCOPE = "openai_token_count_preflight_only"
_RATE_LIMIT_STATE = "unresolved_provider_accounting_semantics"
_AUTHORIZATION_BILLING_STATUS = "unknown_charge_requires_reconciliation"
_EVIDENCE_BILLING_STATE = "pending_cost_reconciliation"
_PERMISSION_STATE = "unconfirmed_fail_closed"
_REDACTED_HEADERS = frozenset({"authorization"})
_VALIDATED_AUTHORIZATION_TOKEN = object()


class OpenAITokenCountError(ValueError):
    """A safe token-count preflight invariant failed closed."""

    provider_call_incremented = False
    pilot_call_incremented = False


def _fail(code: str) -> OpenAITokenCountError:
    return OpenAITokenCountError(code)


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


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_document(document: Mapping[str, Any]) -> str:
    detached = copy.deepcopy(dict(document))
    if "semantic_hash" not in detached:
        raise _fail("identity")
    detached["semantic_hash"] = None
    return _hash_bytes(_canonical(detached))


def _utc(value: Any, *, code: str) -> str:
    if type(value) is not str or _UTC_SECONDS.fullmatch(value) is None:
        raise _fail(code)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise _fail(code) from None
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise _fail(code)
    return value


def _money(value: Any, *, code: str) -> Decimal:
    if type(value) is not str or _MONEY.fullmatch(value) is None:
        raise _fail(code)
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise _fail(code) from None
    if not result.is_finite() or result <= 0 or result > _CEILING:
        raise _fail(code)
    return result


def _assert_certification(
    certification: Any,
) -> SameDayCertification:
    if (
        not isinstance(certification, SameDayCertification)
        or certification.semantic_hash != _EXPECTED_CERTIFICATION_HASH
        or certification.pricing_snapshot_hash != _EXPECTED_PRICING_HASH
        or certification.budget_control_hash != _EXPECTED_BUDGET_HASH
        or certification.region_binding_hash != _EXPECTED_REGION_HASH
        or _CALL_ID not in certification.documentation_compatible_call_ids
        or certification.pricing_unchanged is not True
        or certification.provider_calls_completed != 0
        or certification.independently_authorizes_execution is not False
    ):
        raise _fail("certification_binding")
    return certification


def project_openai_token_count_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Retain every documented count surface and only known generation controls."""
    if type(payload) is not dict:
        raise _fail("request_payload")
    keys = set(payload)
    unsupported = keys - _COUNT_ENDPOINT_FIELDS - _GENERATION_ONLY_FIELDS
    if unsupported:
        raise _fail("unsupported_request_field")
    if not _REQUIRED_COUNT_FIELDS <= keys:
        raise _fail("required_request_field")
    return {
        key: copy.deepcopy(payload[key])
        for key in payload
        if key in _COUNT_ENDPOINT_FIELDS
    }


@dataclass(frozen=True, slots=True)
class TokenCountPlan:
    repository_head: str
    call_id: str
    candidate_id: str
    provider: str
    model: str
    fixture_id: str
    workload_stage: str
    topology_id: str
    request_configuration_id: str
    request_configuration_hash: str
    original_request_hash: str
    original_request_body: bytes = field(repr=False)
    token_count_request_hash: str = ""
    token_count_request_body: bytes = field(default=b"", repr=False)
    removed_generation_fields: tuple[str, ...] = ()
    method: str = "POST"
    path: str = OPENAI_TOKEN_COUNT_PATH
    endpoint: str = OPENAI_TOKEN_COUNT_ENDPOINT
    maximum_output_tokens: int = 4096

    def safe_projection(self) -> dict[str, Any]:
        return {
            "repository_head": self.repository_head,
            "call_id": self.call_id,
            "candidate_id": self.candidate_id,
            "provider": self.provider,
            "model": self.model,
            "fixture_id": self.fixture_id,
            "workload_stage": self.workload_stage,
            "topology_id": self.topology_id,
            "request_configuration_id": self.request_configuration_id,
            "request_configuration_hash": self.request_configuration_hash,
            "original_request_hash": self.original_request_hash,
            "original_request_body_bytes": len(self.original_request_body),
            "token_count_request_hash": self.token_count_request_hash,
            "token_count_request_body_bytes": len(self.token_count_request_body),
            "retained_fields": sorted(
                json.loads(self.token_count_request_body.decode("utf-8"))
            ),
            "removed_generation_fields": list(self.removed_generation_fields),
            "method": self.method,
            "path": self.path,
            "endpoint": self.endpoint,
            "maximum_output_tokens": self.maximum_output_tokens,
        }


def _assert_plan(plan: Any) -> TokenCountPlan:
    if type(plan) is not TokenCountPlan:
        raise _fail("plan_identity")
    expected_values = {
        "call_id": _CALL_ID,
        **_EXPECTED,
        "original_request_hash": _EXPECTED_ORIGINAL_REQUEST_HASH,
        "method": "POST",
        "path": OPENAI_TOKEN_COUNT_PATH,
        "endpoint": OPENAI_TOKEN_COUNT_ENDPOINT,
        "maximum_output_tokens": 4096,
    }
    if (
        _GIT_SHA.fullmatch(plan.repository_head) is None
        or any(getattr(plan, key) != value for key, value in expected_values.items())
        or type(plan.original_request_body) is not bytes
        or len(plan.original_request_body) != _EXPECTED_ORIGINAL_REQUEST_BYTES
        or _hash_bytes(plan.original_request_body) != plan.original_request_hash
        or type(plan.token_count_request_body) is not bytes
        or _hash_bytes(plan.token_count_request_body) != plan.token_count_request_hash
        or plan.removed_generation_fields
        != tuple(sorted(_GENERATION_ONLY_FIELDS))
    ):
        raise _fail("plan_identity")
    try:
        original = json.loads(plan.original_request_body.decode("utf-8"))
        projected = json.loads(plan.token_count_request_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail("plan_identity") from exc
    if (
        type(original) is not dict
        or set(original) != _EXPECTED_ORIGINAL_FIELDS
        or original.get("model") != plan.model
        or original.get("max_output_tokens") != 4096
        or project_openai_token_count_payload(original) != projected
    ):
        raise _fail("plan_identity")
    return plan


def build_call_0003_token_count_plan(
    runner: ProviderFreePilotRunner,
) -> TokenCountPlan:
    """Bind the exact committed call-0003 native request to a count projection."""
    if not isinstance(runner, ProviderFreePilotRunner):
        raise _fail("runner")
    calls = tuple(
        item for item in runner.plan.provider_calls if item.call_id == _CALL_ID
    )
    if len(calls) != 1:
        raise _fail("call_inventory")
    call = calls[0]
    if any(getattr(call, key) != value for key, value in _EXPECTED.items()):
        raise _fail("call_identity")
    native = runner.build_native_request(call)
    if not isinstance(native, NativeProviderRequest):
        raise _fail("original_request_identity")
    original_hash = _hash_bytes(native.payload_json)
    if (
        native.payload_hash != original_hash
        or original_hash != _EXPECTED_ORIGINAL_REQUEST_HASH
        or len(native.payload_json) != _EXPECTED_ORIGINAL_REQUEST_BYTES
    ):
        raise _fail("original_request_identity")
    try:
        payload = json.loads(native.payload_json.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail("original_request_identity") from exc
    if type(payload) is not dict or set(payload) != _EXPECTED_ORIGINAL_FIELDS:
        raise _fail("original_request_identity")
    projection = project_openai_token_count_payload(payload)
    count_body = _canonical(projection)
    plan = TokenCountPlan(
        repository_head=runner.repository_harness_commit_sha,
        call_id=call.call_id,
        candidate_id=call.candidate_id,
        provider=call.provider,
        model=call.model,
        fixture_id=call.fixture_id,
        workload_stage=call.workload_stage,
        topology_id=call.topology_id,
        request_configuration_id=call.request_configuration_id or "",
        request_configuration_hash=call.request_configuration_hash or "",
        original_request_hash=original_hash,
        original_request_body=native.payload_json,
        token_count_request_hash=_hash_bytes(count_body),
        token_count_request_body=count_body,
        removed_generation_fields=tuple(
            sorted(set(payload) & _GENERATION_ONLY_FIELDS)
        ),
    )
    return _assert_plan(plan)


def calculate_call_0003_reservation(input_tokens: Any) -> Decimal | None:
    """Return the exact conservative model-attempt reservation, never a float."""
    if type(input_tokens) is not int or input_tokens < 0:
        return None
    if input_tokens <= _SHORT_THRESHOLD:
        return Decimal(input_tokens) * _SHORT_INPUT_RATE + _SHORT_OUTPUT_RESERVATION
    return Decimal(input_tokens) * _LONG_INPUT_RATE + _LONG_OUTPUT_RESERVATION


_AUTHORIZATION_FIELDS = frozenset(
    {
        "authorization_id",
        "authorization_version",
        "status",
        "scope",
        "repository_head",
        "call_id",
        "candidate_id",
        "provider",
        "model",
        "fixture_id",
        "workload_stage",
        "topology_id",
        "request_configuration_id",
        "request_configuration_hash",
        "request_hash",
        "token_count_request_hash",
        "method",
        "path",
        "endpoint",
        "same_day_certification_hash",
        "pricing_snapshot_hash",
        "budget_control_hash",
        "region_binding_hash",
        "credential_variable_name",
        "credential_readiness",
        "provider_permission_status",
        "provider_hard_spend_cap_usd",
        "billing_status",
        "operational_reservation_usd",
        "maximum_invocations",
        "retry_count",
        "model_response_generation_authorized",
        "pilot_execution_authorized",
        "scored_execution_authorized",
        "production_deployment_authorized",
        "authorized_at_utc",
        "semantic_hash",
    }
)


@dataclass(frozen=True, slots=True)
class ValidatedTokenCountAuthorization:
    semantic_hash: str
    scope: str
    repository_head: str
    call_id: str
    token_count_request_hash: str
    certification_hash: str
    pricing_snapshot_hash: str
    budget_control_hash: str
    region_binding_hash: str
    credential_variable_name: str
    provider_permission_status: str
    provider_hard_spend_cap_usd: Decimal
    billing_status: str
    operational_reservation_usd: Decimal
    maximum_invocations: int
    retry_count: int
    model_response_generation_authorized: bool
    pilot_execution_authorized: bool
    scored_execution_authorized: bool
    authorized_at_utc: str
    binding_integrity_hash: str
    _construction_token: object | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if (
            self._construction_token is not _VALIDATED_AUTHORIZATION_TOKEN
            or self.binding_integrity_hash
            != _authorization_binding_integrity_hash(self)
        ):
            raise _fail("authorization_factory_required")


def _authorization_binding_values(
    authorization: ValidatedTokenCountAuthorization,
) -> dict[str, Any]:
    return {
        "semantic_hash": authorization.semantic_hash,
        "scope": authorization.scope,
        "repository_head": authorization.repository_head,
        "call_id": authorization.call_id,
        "token_count_request_hash": authorization.token_count_request_hash,
        "certification_hash": authorization.certification_hash,
        "pricing_snapshot_hash": authorization.pricing_snapshot_hash,
        "budget_control_hash": authorization.budget_control_hash,
        "region_binding_hash": authorization.region_binding_hash,
        "credential_variable_name": authorization.credential_variable_name,
        "provider_permission_status": authorization.provider_permission_status,
        "provider_hard_spend_cap_usd": format(
            authorization.provider_hard_spend_cap_usd,
            "f",
        ),
        "billing_status": authorization.billing_status,
        "operational_reservation_usd": format(
            authorization.operational_reservation_usd,
            "f",
        ),
        "maximum_invocations": authorization.maximum_invocations,
        "retry_count": authorization.retry_count,
        "model_response_generation_authorized": (
            authorization.model_response_generation_authorized
        ),
        "pilot_execution_authorized": authorization.pilot_execution_authorized,
        "scored_execution_authorized": authorization.scored_execution_authorized,
        "authorized_at_utc": authorization.authorized_at_utc,
    }


def _authorization_binding_integrity_hash(
    authorization: ValidatedTokenCountAuthorization,
) -> str:
    return _hash_bytes(_canonical(_authorization_binding_values(authorization)))


def build_token_count_authorization(
    *,
    plan: TokenCountPlan,
    certification: SameDayCertification,
    authorized_at_utc: str,
    credential_readiness: str,
    provider_hard_spend_cap_usd: str,
    explicit_human_approval: bool = False,
) -> dict[str, Any]:
    """Build a hash-bound document only after an explicit external approval."""
    _assert_plan(plan)
    _assert_certification(certification)
    if explicit_human_approval is not True:
        raise _fail("explicit_human_approval_required")
    if credential_readiness != "PRESENT":
        raise _fail("credential_readiness")
    cap = _money(provider_hard_spend_cap_usd, code="spend_control")
    timestamp = _utc(authorized_at_utc, code="authorization_timestamp")
    if (
        timestamp[:10] != certification.observation_date
        or timestamp < certification.observed_at_utc
    ):
        raise _fail("authorization_freshness")
    document = {
        "authorization_id": _AUTHORIZATION_ID,
        "authorization_version": _AUTHORIZATION_VERSION,
        "status": "approved",
        "scope": _AUTHORIZATION_SCOPE,
        "repository_head": plan.repository_head,
        "call_id": plan.call_id,
        "candidate_id": plan.candidate_id,
        "provider": plan.provider,
        "model": plan.model,
        "fixture_id": plan.fixture_id,
        "workload_stage": plan.workload_stage,
        "topology_id": plan.topology_id,
        "request_configuration_id": plan.request_configuration_id,
        "request_configuration_hash": plan.request_configuration_hash,
        "request_hash": plan.original_request_hash,
        "token_count_request_hash": plan.token_count_request_hash,
        "method": plan.method,
        "path": plan.path,
        "endpoint": plan.endpoint,
        "same_day_certification_hash": certification.semantic_hash,
        "pricing_snapshot_hash": certification.pricing_snapshot_hash,
        "budget_control_hash": certification.budget_control_hash,
        "region_binding_hash": certification.region_binding_hash,
        "credential_variable_name": "OPENAI_API_KEY",
        "credential_readiness": credential_readiness,
        "provider_permission_status": _PERMISSION_STATE,
        "provider_hard_spend_cap_usd": format(cap, "f"),
        "billing_status": _AUTHORIZATION_BILLING_STATUS,
        "operational_reservation_usd": format(cap, "f"),
        "maximum_invocations": 1,
        "retry_count": 0,
        "model_response_generation_authorized": False,
        "pilot_execution_authorized": False,
        "scored_execution_authorized": False,
        "production_deployment_authorized": False,
        "authorized_at_utc": timestamp,
        "semantic_hash": None,
    }
    document["semantic_hash"] = _hash_document(document)
    return document


def validate_token_count_authorization(
    document: Mapping[str, Any],
    *,
    plan: TokenCountPlan,
    certification: SameDayCertification,
    current_date: str,
) -> ValidatedTokenCountAuthorization:
    """Validate an externally supplied, same-day, count-only authorization."""
    _assert_plan(plan)
    _assert_certification(certification)
    if type(document) is not dict or set(document) != _AUTHORIZATION_FIELDS:
        raise _fail("authorization_shape")
    stored_hash = document.get("semantic_hash")
    if (
        type(stored_hash) is not str
        or _SHA256.fullmatch(stored_hash) is None
        or _hash_document(document) != stored_hash
    ):
        raise _fail("authorization_hash")
    timestamp = _utc(document.get("authorized_at_utc"), code="authorization_timestamp")
    if (
        current_date != certification.observation_date
        or timestamp[:10] != current_date
        or timestamp < certification.observed_at_utc
    ):
        raise _fail("authorization_freshness")
    cap = _money(document.get("provider_hard_spend_cap_usd"), code="spend_control")
    reservation = _money(
        document.get("operational_reservation_usd"), code="operational_reservation"
    )
    bindings = {
        "authorization_id": _AUTHORIZATION_ID,
        "authorization_version": _AUTHORIZATION_VERSION,
        "status": "approved",
        "scope": _AUTHORIZATION_SCOPE,
        "repository_head": plan.repository_head,
        "call_id": plan.call_id,
        "candidate_id": plan.candidate_id,
        "provider": plan.provider,
        "model": plan.model,
        "fixture_id": plan.fixture_id,
        "workload_stage": plan.workload_stage,
        "topology_id": plan.topology_id,
        "request_configuration_id": plan.request_configuration_id,
        "request_configuration_hash": plan.request_configuration_hash,
        "request_hash": plan.original_request_hash,
        "token_count_request_hash": plan.token_count_request_hash,
        "method": "POST",
        "path": OPENAI_TOKEN_COUNT_PATH,
        "endpoint": OPENAI_TOKEN_COUNT_ENDPOINT,
        "same_day_certification_hash": certification.semantic_hash,
        "pricing_snapshot_hash": certification.pricing_snapshot_hash,
        "budget_control_hash": certification.budget_control_hash,
        "region_binding_hash": certification.region_binding_hash,
        "credential_variable_name": "OPENAI_API_KEY",
        "credential_readiness": "PRESENT",
        "provider_permission_status": _PERMISSION_STATE,
        "billing_status": _AUTHORIZATION_BILLING_STATUS,
        "maximum_invocations": 1,
        "retry_count": 0,
        "model_response_generation_authorized": False,
        "pilot_execution_authorized": False,
        "scored_execution_authorized": False,
        "production_deployment_authorized": False,
    }
    if (
        any(document.get(key) != value for key, value in bindings.items())
        or reservation != cap
    ):
        raise _fail("authorization_binding")
    values = dict(
        semantic_hash=stored_hash,
        scope=document["scope"],
        repository_head=document["repository_head"],
        call_id=document["call_id"],
        token_count_request_hash=document["token_count_request_hash"],
        certification_hash=document["same_day_certification_hash"],
        pricing_snapshot_hash=document["pricing_snapshot_hash"],
        budget_control_hash=document["budget_control_hash"],
        region_binding_hash=document["region_binding_hash"],
        credential_variable_name=document["credential_variable_name"],
        provider_permission_status=document["provider_permission_status"],
        provider_hard_spend_cap_usd=cap,
        billing_status=document["billing_status"],
        operational_reservation_usd=reservation,
        maximum_invocations=document["maximum_invocations"],
        retry_count=document["retry_count"],
        model_response_generation_authorized=False,
        pilot_execution_authorized=False,
        scored_execution_authorized=False,
        authorized_at_utc=timestamp,
    )
    integrity_values = dict(values)
    integrity_values["provider_hard_spend_cap_usd"] = format(cap, "f")
    integrity_values["operational_reservation_usd"] = format(reservation, "f")
    return ValidatedTokenCountAuthorization(
        **values,
        binding_integrity_hash=_hash_bytes(_canonical(integrity_values)),
        _construction_token=_VALIDATED_AUTHORIZATION_TOKEN,
    )


@dataclass(frozen=True, slots=True)
class TokenCountHttpRequest:
    method: str
    url: str
    headers: tuple[tuple[str, str], ...] = field(repr=False)
    body: bytes = field(repr=False)
    timeout_seconds: int = 120
    follow_redirects: bool = False

    def __post_init__(self) -> None:
        if (
            self.method != "POST"
            or self.url != OPENAI_TOKEN_COUNT_ENDPOINT
            or type(self.body) is not bytes
            or self.timeout_seconds != 120
            or self.follow_redirects is not False
            or type(self.headers) is not tuple
            or any(
                type(item) is not tuple
                or len(item) != 2
                or any(type(value) is not str or not value for value in item)
                for item in self.headers
            )
        ):
            raise _fail("http_request")

    def safe_projection(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "url": self.url,
            "headers": {
                name: "<redacted>" if name.lower() in _REDACTED_HEADERS else value
                for name, value in self.headers
            },
            "body_bytes": len(self.body),
            "body_hash": _hash_bytes(self.body),
            "timeout_seconds": self.timeout_seconds,
            "follow_redirects": self.follow_redirects,
        }

    def __repr__(self) -> str:
        return f"TokenCountHttpRequest({self.safe_projection()!r})"


@dataclass(frozen=True, slots=True)
class TokenCountHttpResponse:
    status_code: int
    body_chunks: tuple[bytes, ...] = field(repr=False)
    headers: Mapping[str, str] = field(repr=False)
    elapsed_seconds: float

    def __post_init__(self) -> None:
        if (
            type(self.status_code) is not int
            or not 100 <= self.status_code <= 599
            or type(self.body_chunks) is not tuple
            or any(type(chunk) is not bytes for chunk in self.body_chunks)
            or not isinstance(self.headers, Mapping)
            or any(
                type(name) is not str or type(value) is not str
                for name, value in self.headers.items()
            )
            or type(self.elapsed_seconds) not in (int, float)
            or self.elapsed_seconds < 0
        ):
            raise _fail("http_response")


class TokenCountHttpSender(Protocol):
    def send(self, request: TokenCountHttpRequest) -> TokenCountHttpResponse: ...


class OpenAITokenCountHttpxSender:
    """One physical count request, with redirect following disabled."""

    __slots__ = ()

    def send(self, request: TokenCountHttpRequest) -> TokenCountHttpResponse:
        if not isinstance(request, TokenCountHttpRequest):
            raise _fail("http_request")
        import httpx

        accumulator = CanonicalRawResponseAccumulator("non_streaming_http")
        try:
            with httpx.Client(
                timeout=httpx.Timeout(request.timeout_seconds),
                follow_redirects=False,
            ) as client:
                with client.stream(
                    request.method,
                    request.url,
                    headers=dict(request.headers),
                    content=request.body,
                ) as response:
                    for chunk in response.iter_bytes():
                        accumulator.append(chunk)
                    capture = accumulator.finish_response()
                    body = capture.raw_provider_response
                    if body is None:
                        raise _fail("http_body")
                    return TokenCountHttpResponse(
                        response.status_code,
                        (body,),
                        {"content-type": response.headers.get("content-type", "")},
                        response.elapsed.total_seconds(),
                    )
        except httpx.TimeoutException as exc:
            raise _fail("connection_failure") from exc
        except httpx.TransportError as exc:
            raise _fail("connection_failure") from exc

    def __repr__(self) -> str:
        return "OpenAITokenCountHttpxSender(endpoint=input_tokens,retries=0)"


def _strict_response(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise _fail("count_response")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(_fail("count_response")),
        )
    except OpenAITokenCountError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise _fail("count_response") from exc
    if (
        type(value) is not dict
        or set(value) != {"object", "input_tokens"}
        or value.get("object") != "response.input_tokens"
        or type(value.get("input_tokens")) is not int
        or value["input_tokens"] < 0
    ):
        raise _fail("count_response")
    return value


_EVIDENCE_FIELDS = frozenset(
    {
        "evidence_id",
        "evidence_version",
        "repository_head",
        "call_id",
        "candidate_id",
        "provider",
        "model",
        "fixture_id",
        "workload_stage",
        "topology_id",
        "request_configuration_id",
        "request_configuration_hash",
        "original_request_hash",
        "token_count_request_hash",
        "method",
        "path",
        "endpoint",
        "input_tokens",
        "raw_response_hash",
        "observed_at_utc",
        "same_day_certification_hash",
        "pricing_snapshot_id",
        "pricing_snapshot_hash",
        "budget_control_hash",
        "region_binding_hash",
        "authorization_hash",
        "operational_reservation_usd",
        "billing_state",
        "call_reservation_usd",
        "pricing_context_regime",
        "rate_limit_compatibility",
        "invocation_count",
        "retry_count",
        "model_response_generated",
        "semantic_hash",
    }
)


@dataclass(frozen=True, slots=True)
class OpenAITokenCountEvidence:
    evidence_id: str
    evidence_version: str
    repository_head: str
    call_id: str
    candidate_id: str
    provider: str
    model: str
    fixture_id: str
    workload_stage: str
    topology_id: str
    request_configuration_id: str
    request_configuration_hash: str
    original_request_hash: str
    token_count_request_hash: str
    method: str
    path: str
    endpoint: str
    input_tokens: int
    raw_response_hash: str
    observed_at_utc: str
    same_day_certification_hash: str
    pricing_snapshot_id: str
    pricing_snapshot_hash: str
    budget_control_hash: str
    region_binding_hash: str
    authorization_hash: str
    operational_reservation_usd: str
    billing_state: str
    call_reservation_usd: str
    pricing_context_regime: str
    rate_limit_compatibility: str
    invocation_count: int
    retry_count: int
    model_response_generated: bool
    semantic_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


def _evidence_document(
    *,
    plan: TokenCountPlan,
    authorization: ValidatedTokenCountAuthorization,
    input_tokens: int,
    raw_response_hash: str,
    observed_at_utc: str,
) -> dict[str, Any]:
    reservation = calculate_call_0003_reservation(input_tokens)
    if reservation is None:
        raise _fail("count_response")
    regime = (
        "input_tokens_at_most_272000"
        if input_tokens <= _SHORT_THRESHOLD
        else "input_tokens_above_272000"
    )
    document = {
        "evidence_id": _EVIDENCE_ID,
        "evidence_version": _EVIDENCE_VERSION,
        "repository_head": plan.repository_head,
        "call_id": plan.call_id,
        "candidate_id": plan.candidate_id,
        "provider": plan.provider,
        "model": plan.model,
        "fixture_id": plan.fixture_id,
        "workload_stage": plan.workload_stage,
        "topology_id": plan.topology_id,
        "request_configuration_id": plan.request_configuration_id,
        "request_configuration_hash": plan.request_configuration_hash,
        "original_request_hash": plan.original_request_hash,
        "token_count_request_hash": plan.token_count_request_hash,
        "method": plan.method,
        "path": plan.path,
        "endpoint": plan.endpoint,
        "input_tokens": input_tokens,
        "raw_response_hash": raw_response_hash,
        "observed_at_utc": observed_at_utc,
        "same_day_certification_hash": authorization.certification_hash,
        "pricing_snapshot_id": _PRICING_SNAPSHOT_ID,
        "pricing_snapshot_hash": authorization.pricing_snapshot_hash,
        "budget_control_hash": authorization.budget_control_hash,
        "region_binding_hash": authorization.region_binding_hash,
        "authorization_hash": authorization.semantic_hash,
        "operational_reservation_usd": format(
            authorization.operational_reservation_usd, "f"
        ),
        "billing_state": _EVIDENCE_BILLING_STATE,
        "call_reservation_usd": format(reservation, "f"),
        "pricing_context_regime": regime,
        "rate_limit_compatibility": _RATE_LIMIT_STATE,
        "invocation_count": 1,
        "retry_count": 0,
        "model_response_generated": False,
        "semantic_hash": None,
    }
    document["semantic_hash"] = _hash_document(document)
    return document


class OpenAITokenCountPreflight:
    """Consume exactly one token-count invocation and emit immutable evidence."""

    __slots__ = ("_sender", "_invocation_count")

    def __init__(self, sender: TokenCountHttpSender) -> None:
        if not hasattr(sender, "send"):
            raise _fail("http_sender")
        self._sender = sender
        self._invocation_count = 0

    @property
    def invocation_count(self) -> int:
        return self._invocation_count

    def invoke(
        self,
        *,
        plan: TokenCountPlan,
        authorization: ValidatedTokenCountAuthorization,
        credential_resolver: LazyEnvironmentCredentialResolver,
        observed_at_utc: str,
    ) -> OpenAITokenCountEvidence:
        _assert_plan(plan)
        if (
            type(authorization) is not ValidatedTokenCountAuthorization
            or authorization.repository_head != plan.repository_head
            or authorization.call_id != plan.call_id
            or authorization.token_count_request_hash != plan.token_count_request_hash
            or authorization.maximum_invocations != 1
            or authorization.retry_count != 0
            or authorization.model_response_generation_authorized is not False
            or authorization.pilot_execution_authorized is not False
            or authorization.scored_execution_authorized is not False
        ):
            raise _fail("authorization_binding")
        timestamp = _utc(observed_at_utc, code="evidence_timestamp")
        if (
            timestamp[:10] != authorization.authorized_at_utc[:10]
            or timestamp < authorization.authorized_at_utc
        ):
            raise _fail("evidence_freshness")
        if self._invocation_count != 0:
            raise _fail("invocation_already_consumed")
        reference = CredentialReference(
            "OpenAI",
            authorization.credential_variable_name,
            "externally_confirmed_for_live_pilot",
        )
        credential = credential_resolver.resolve(reference)
        if not isinstance(credential, _ResolvedCredential):
            raise _fail("credential_resolution")
        secret = credential._transport_value(_TRANSPORT_SECRET_TOKEN)
        request = TokenCountHttpRequest(
            method="POST",
            url=OPENAI_TOKEN_COUNT_ENDPOINT,
            headers=(
                ("content-type", "application/json"),
                ("accept", "application/json"),
                ("authorization", f"Bearer {secret}"),
            ),
            body=plan.token_count_request_body,
        )
        self._invocation_count += 1
        try:
            response = self._sender.send(request)
        except OpenAITokenCountError:
            raise
        except Exception as exc:
            raise _fail("connection_failure") from exc
        if not isinstance(response, TokenCountHttpResponse):
            raise _fail("http_response")
        if 300 <= response.status_code <= 399:
            raise _fail("redirect_rejected")
        if response.status_code in {401, 403}:
            raise _fail("permission_denied")
        if not 200 <= response.status_code <= 299:
            raise _fail("http_failure")
        content_type = next(
            (
                value
                for name, value in response.headers.items()
                if name.lower() == "content-type"
            ),
            "",
        )
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            raise _fail("count_response")
        accumulator = CanonicalRawResponseAccumulator("non_streaming_http")
        try:
            for chunk in response.body_chunks:
                accumulator.append(chunk)
            capture = accumulator.finish_response()
        except Exception as exc:
            raise _fail("count_response") from exc
        raw = capture.raw_provider_response
        if raw is None:
            raise _fail("count_response")
        value = _strict_response(raw)
        document = _evidence_document(
            plan=plan,
            authorization=authorization,
            input_tokens=value["input_tokens"],
            raw_response_hash=_hash_bytes(raw),
            observed_at_utc=timestamp,
        )
        return OpenAITokenCountEvidence(**document)

    def __repr__(self) -> str:
        return (
            "OpenAITokenCountPreflight("
            "endpoint=input_tokens,"
            f"invocation_count={self._invocation_count},retries=0)"
        )


def validate_token_count_evidence(
    document: Mapping[str, Any],
    *,
    plan: TokenCountPlan,
    certification: SameDayCertification,
    authorization: ValidatedTokenCountAuthorization,
    current_date: str,
) -> OpenAITokenCountEvidence:
    """Reject stale or identity-mutated count evidence before pilot use."""
    _assert_plan(plan)
    _assert_certification(certification)
    if type(document) is not dict or set(document) != _EVIDENCE_FIELDS:
        raise _fail("evidence_shape")
    stored_hash = document.get("semantic_hash")
    if (
        type(stored_hash) is not str
        or _SHA256.fullmatch(stored_hash) is None
        or _hash_document(document) != stored_hash
    ):
        raise _fail("evidence_hash")
    timestamp = _utc(document.get("observed_at_utc"), code="evidence_timestamp")
    if (
        current_date != certification.observation_date
        or timestamp[:10] != current_date
    ):
        raise _fail("evidence_freshness")
    if (
        type(authorization) is not ValidatedTokenCountAuthorization
        or document.get("authorization_hash") != authorization.semantic_hash
    ):
        raise _fail("evidence_authorization")
    count = document.get("input_tokens")
    reservation = calculate_call_0003_reservation(count)
    if reservation is None:
        raise _fail("evidence_contract")
    expected = {
        "evidence_id": _EVIDENCE_ID,
        "evidence_version": _EVIDENCE_VERSION,
        "repository_head": plan.repository_head,
        "call_id": plan.call_id,
        "candidate_id": plan.candidate_id,
        "provider": plan.provider,
        "model": plan.model,
        "fixture_id": plan.fixture_id,
        "workload_stage": plan.workload_stage,
        "topology_id": plan.topology_id,
        "request_configuration_id": plan.request_configuration_id,
        "request_configuration_hash": plan.request_configuration_hash,
        "original_request_hash": plan.original_request_hash,
        "token_count_request_hash": plan.token_count_request_hash,
        "method": "POST",
        "path": OPENAI_TOKEN_COUNT_PATH,
        "endpoint": OPENAI_TOKEN_COUNT_ENDPOINT,
        "same_day_certification_hash": certification.semantic_hash,
        "pricing_snapshot_id": _PRICING_SNAPSHOT_ID,
        "pricing_snapshot_hash": certification.pricing_snapshot_hash,
        "budget_control_hash": certification.budget_control_hash,
        "region_binding_hash": certification.region_binding_hash,
        "billing_state": _EVIDENCE_BILLING_STATE,
        "call_reservation_usd": format(reservation, "f"),
        "pricing_context_regime": (
            "input_tokens_at_most_272000"
            if count <= _SHORT_THRESHOLD
            else "input_tokens_above_272000"
        ),
        "rate_limit_compatibility": _RATE_LIMIT_STATE,
        "invocation_count": 1,
        "retry_count": 0,
        "model_response_generated": False,
    }
    if (
        any(document.get(key) != value for key, value in expected.items())
        or _SHA256.fullmatch(document.get("raw_response_hash", "")) is None
        or _SHA256.fullmatch(document.get("authorization_hash", "")) is None
        or _money(
            document.get("operational_reservation_usd"),
            code="evidence_contract",
        )
        != authorization.operational_reservation_usd
    ):
        raise _fail("evidence_contract")
    return OpenAITokenCountEvidence(**document)


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    subparsers = parser.add_subparsers(dest="command")
    dry = subparsers.add_parser("dry-run")
    dry.add_argument("--repository-head", required=True)
    auth = subparsers.add_parser("authorization-template")
    auth.add_argument("--repository-head", required=True)
    auth.add_argument("--certification", required=True)
    auth.add_argument("--authorized-at-utc", required=True)
    auth.add_argument("--provider-hard-spend-cap-usd", required=True)
    auth.add_argument("--confirm-credential-present", action="store_true")
    auth.add_argument("--confirm-single-token-count-only", action="store_true")
    execute = subparsers.add_parser("execute")
    execute.add_argument("--repository-head", required=True)
    execute.add_argument("--certification", required=True)
    execute.add_argument("--authorization", required=True)
    execute.add_argument("--confirm-network", action="store_true")
    return parser


def run_cli(
    argv: list[str] | None = None,
    *,
    repository_root: str | Path = _ROOT,
    environment_getter: Callable[[str], str | None] | None = None,
    sender_factory: Callable[[], Any] = OpenAITokenCountHttpxSender,
    utc_now_getter: Callable[[], str] | None = None,
) -> int:
    """Run one operator action; only ``execute`` can reach the count endpoint."""
    try:
        options = _parser().parse_args(list(argv or []))
    except SystemExit:
        _emit({"status": "blocked", "reason": "invalid_arguments"})
        return 2
    if options.command is None:
        _emit(
            {
                "status": "TOKEN_COUNT_PREFLIGHT_READY_AWAITING_USER",
                "execution": "blocked",
                "provider_calls": 0,
                "pilot_calls": 0,
                "scored_calls": 0,
                "credentials_accessed": 0,
            }
        )
        return 0
    now = (
        utc_now_getter()
        if utc_now_getter is not None
        else datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    preflight: OpenAITokenCountPreflight | None = None
    authorization: ValidatedTokenCountAuthorization | None = None
    try:
        runner = build_provider_free_pilot_runner(
            repository_root=repository_root,
            repository_harness_commit_sha=options.repository_head,
        )
        plan = build_call_0003_token_count_plan(runner)
        if options.command == "dry-run":
            _emit(
                {
                    "status": "token_count_dry_run_only",
                    **plan.safe_projection(),
                    "credentials_accessed": 0,
                    "provider_calls": 0,
                    "pilot_calls": 0,
                }
            )
            return 0
        certification = load_same_day_certification(
            options.certification,
            current_date=now[:10],
        )
        if options.command == "authorization-template":
            if (
                options.confirm_credential_present is not True
                or options.confirm_single_token_count_only is not True
            ):
                raise _fail("explicit_human_approval_required")
            document = build_token_count_authorization(
                plan=plan,
                certification=certification,
                authorized_at_utc=options.authorized_at_utc,
                credential_readiness="PRESENT",
                provider_hard_spend_cap_usd=options.provider_hard_spend_cap_usd,
                explicit_human_approval=True,
            )
            _emit(document)
            return 0
        if options.command != "execute" or options.confirm_network is not True:
            raise _fail("explicit_network_confirmation_required")
        authorization_document = load_strict_contract_json(options.authorization)
        authorization = validate_token_count_authorization(
            authorization_document,
            plan=plan,
            certification=certification,
            current_date=now[:10],
        )
        resolver = LazyEnvironmentCredentialResolver(environment_getter)
        preflight = OpenAITokenCountPreflight(sender_factory())
        evidence = preflight.invoke(
            plan=plan,
            authorization=authorization,
            credential_resolver=resolver,
            observed_at_utc=now,
        )
        _emit(evidence.as_dict())
        return 0
    except (OpenAITokenCountError, OSError, TypeError, ValueError) as exc:
        reason = (
            str(exc)
            if isinstance(exc, OpenAITokenCountError)
            else "preflight_failed"
        )
        if (
            preflight is not None
            and preflight.invocation_count == 1
            and authorization is not None
        ):
            _emit(
                {
                    "status": "BLOCKED_PENDING_COST_RECONCILIATION",
                    "reason": reason,
                    "call_id": _CALL_ID,
                    "authorization_hash": authorization.semantic_hash,
                    "billing_state": _EVIDENCE_BILLING_STATE,
                    "operational_reservation_usd": format(
                        authorization.operational_reservation_usd,
                        "f",
                    ),
                    "invocation_count": 1,
                    "retry_count": 0,
                    "model_response_generated": False,
                }
            )
            return 3
        _emit({"status": "blocked", "reason": reason})
        return 2


def main() -> int:
    import sys

    return run_cli(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
