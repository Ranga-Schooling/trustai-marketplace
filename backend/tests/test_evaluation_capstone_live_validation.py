"""Offline safety tests for the separate Capstone live-validation path."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import stat
import subprocess

import pytest

from app.services.evaluation_capstone_live_validation import (
    CAPSTONE_LIVE_VALIDATION_STATUS,
    CapstoneLiveValidationError,
    build_capstone_live_validation,
)
from app.services.evaluation_live_transport import (
    ConcreteLivePilotTransport,
    HttpResponse,
    LazyEnvironmentCredentialResolver,
)
from app.services.evaluation_pilot_runner import _synthetic_provider_envelope


ROOT = Path(__file__).resolve().parents[2]
HEAD = subprocess.run(
    ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
CASE_ID = "capval-openai-terra-pt1-v1"
CANARY = "capstone-live-secret-canary-fd449f99"


class _Sender:
    def __init__(self, response_bytes: bytes, *, status_code: int = 200) -> None:
        self.response_bytes = response_bytes
        self.status_code = status_code
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        return HttpResponse(
            self.status_code,
            (self.response_bytes,),
            {"content-type": "application/json"},
            0.25,
        )


def _validator():
    return build_capstone_live_validation(
        repository_root=ROOT,
        repository_head=HEAD,
        require_clean_repository=False,
    )


def _authorization(validator):
    return validator.build_authorization_document(
        case_id=CASE_ID,
        authorized_at_utc="2026-09-01T21:00:00Z",
    )


def _successful_openai_response(validator) -> bytes:
    request = validator.build_request(CASE_ID)
    value = json.loads(_synthetic_provider_envelope(request).decode("utf-8"))
    value["usage"]["input_tokens"] = 1018
    value["usage"]["input_tokens_details"] = {
        "cached_tokens": 0,
        "cache_write_tokens": 0,
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def test_contract_reuses_exact_frozen_terra_pt1_request_and_is_separate():
    validator = _validator()
    contract = validator.contract
    case = validator.case(CASE_ID)
    request = validator.build_request(CASE_ID)

    assert validator.readiness_projection() == {
        "status": CAPSTONE_LIVE_VALIDATION_STATUS,
        "execution_class": "capstone_live_validation",
        "execution": "blocked_awaiting_explicit_user_authorization",
        "provider_calls": 0,
        "strict_pilot_calls": 0,
        "scored_calls": 0,
        "winner_selected": False,
        "credentials_accessed": 0,
    }
    assert contract.total_spend_ceiling_usd == "1.00000000"
    assert contract.maximum_lifetime_provider_calls == 1
    assert tuple(item.case_id for item in contract.cases) == (CASE_ID,)
    assert case.source_call_id == "call-0003"
    assert case.candidate_id == "openai_unified_balanced_v1"
    assert case.provider == "OpenAI"
    assert case.model == "gpt-5.6-terra"
    assert case.fixture_id == "PT1"
    assert case.request_configuration_id == "openai_terra_text_pilot_v1"
    assert case.request_configuration_hash == (
        "0eca58d264b7af9e48af182f8d3ce8a0a417db8201328b70fdab77b6a4bae893"
    )
    assert case.request_hash == (
        "97f8752bb33994a00018a15ff62d79419069397b223cc5f60770def973ebc266"
    )
    assert request.payload_hash == case.request_hash
    assert case.input_tokens == 1018
    assert case.conservative_reservation_usd == "0.05169700"
    assert case.remaining_after_reservation_usd == "0.94830300"
    assert contract.strict_pilot_ledger_interaction_allowed is False
    assert contract.strict_pilot_authorization_api_allowed is False
    assert contract.strict_pilot_record_creation_allowed is False
    assert contract.scored_record_creation_allowed is False


def test_repository_head_binding_fails_closed_before_contract_use():
    with pytest.raises(CapstoneLiveValidationError, match="repository_head_mismatch"):
        build_capstone_live_validation(
            repository_root=ROOT,
            repository_head="0" * 40,
            require_clean_repository=False,
        )


def test_offline_dry_run_builds_exact_request_without_credentials_or_network():
    validator = _validator()

    result = validator.dry_run(CASE_ID)

    assert result["status"] == "offline_dry_run_passed"
    assert result["request_hash"] == (
        "97f8752bb33994a00018a15ff62d79419069397b223cc5f60770def973ebc266"
    )
    assert result["request_body_bytes"] == 6249
    assert result["schema_binding"] == "validated"
    assert result["authorization_shape"] == "validated_pending_human_authorization"
    assert result["spend_reservation"] == "validated"
    assert result["credentials_accessed"] == 0
    assert result["provider_calls"] == 0


def test_hash_bound_authorization_rejects_scope_or_identity_mutation():
    validator = _validator()
    authorization = _authorization(validator)

    validated = validator.validate_authorization(authorization)
    assert validated.case_id == CASE_ID
    assert validated.maximum_provider_calls == 1
    assert validated.retry_count == 0
    assert validated.execution_class == "capstone_live_validation"
    assert validated.strict_pilot_execution_authorized is False
    assert validated.scored_execution_authorized is False
    assert validated.winner_selection_authorized is False
    assert validated.production_deployment_authorized is False

    for field, value in (
        ("repository_head", "0" * 40),
        ("request_hash", "0" * 64),
        ("maximum_provider_calls", 2),
        ("retry_count", 1),
        ("scored_execution_authorized", True),
        ("production_deployment_authorized", True),
    ):
        changed = dict(authorization)
        changed[field] = value
        with pytest.raises(CapstoneLiveValidationError):
            validator.validate_authorization(changed)


def test_execute_requires_confirmation_before_state_credentials_or_transport(tmp_path):
    validator = _validator()
    reads = []
    resolver = LazyEnvironmentCredentialResolver(
        lambda name: reads.append(name) or CANARY
    )
    sender = _Sender(_successful_openai_response(validator))
    transport = ConcreteLivePilotTransport(sender)

    with pytest.raises(
        CapstoneLiveValidationError,
        match="explicit_live_confirmation_required",
    ):
        validator.execute_one(
            authorization_document=_authorization(validator),
            confirm_live=False,
            credential_resolver=resolver,
            transport=transport,
            operational_root=tmp_path,
        )

    assert reads == []
    assert sender.requests == []
    assert tuple(tmp_path.iterdir()) == ()


def test_one_successful_mock_attempt_is_safe_bounded_and_not_a_pilot_record(tmp_path):
    validator = _validator()
    reads = []
    resolver = LazyEnvironmentCredentialResolver(
        lambda name: reads.append(name) or CANARY
    )
    sender = _Sender(_successful_openai_response(validator))
    transport = ConcreteLivePilotTransport(sender)

    record = validator.execute_one(
        authorization_document=_authorization(validator),
        confirm_live=True,
        credential_resolver=resolver,
        transport=transport,
        operational_root=tmp_path,
        clock=lambda: datetime(2026, 9, 1, 21, 1, tzinfo=UTC),
    )

    assert reads == ["OPENAI_API_KEY"]
    assert transport.invocation_count == 1
    assert len(sender.requests) == 1
    assert sender.requests[0].url == "https://api.openai.com/v1/responses"
    assert record["record_type"] == "capstone_live_validation_result"
    assert record["execution_class"] == "capstone_live_validation"
    assert record["validation_case_id"] == CASE_ID
    assert record["source_call_id"] == "call-0003"
    assert record["result_status"] == "accepted"
    assert record["parser_result"] == "passed"
    assert record["schema_result"] == "passed"
    assert record["validator_result"] == "passed"
    assert record["provider_usage"] == {
        "input_tokens": 1018,
        "output_tokens": 7,
        "reasoning_tokens": 3,
        "image_usage": None,
    }
    assert record["estimated_validation_cost"]["total_usd"] == "0.00212"
    assert record["conservative_reservation_usd"] == "0.05169700"
    assert record["validation_spend_remaining_usd"] == "0.94830300"
    assert record["strict_pilot_record"] is False
    assert record["scored_record"] is False
    assert "semantic_output" not in record
    state_bytes = b"".join(path.read_bytes() for path in tmp_path.rglob("*.json"))
    assert CANARY.encode() not in state_bytes
    assert b"Authorization" not in state_bytes
    assert b"Bearer" not in state_bytes
    for path in tmp_path.rglob("*.json"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    inspection = validator.inspect_result(tmp_path)
    assert inspection["record_hash"] == record["record_hash"]
    assert inspection["result_status"] == "accepted"
    assert "semantic_output" not in inspection


def test_reserved_case_cannot_be_invoked_twice_even_with_fresh_authorization(tmp_path):
    validator = _validator()
    resolver = LazyEnvironmentCredentialResolver(lambda _name: CANARY)
    sender = _Sender(_successful_openai_response(validator))
    transport = ConcreteLivePilotTransport(sender)
    validator.execute_one(
        authorization_document=_authorization(validator),
        confirm_live=True,
        credential_resolver=resolver,
        transport=transport,
        operational_root=tmp_path,
    )

    with pytest.raises(CapstoneLiveValidationError, match="case_already_reserved"):
        validator.execute_one(
            authorization_document=_authorization(validator),
            confirm_live=True,
            credential_resolver=resolver,
            transport=transport,
            operational_root=tmp_path,
        )

    assert transport.invocation_count == 1
    assert resolver.resolution_count == 1


def test_provider_failure_stops_after_one_attempt_and_records_only_safe_data(tmp_path):
    validator = _validator()
    resolver = LazyEnvironmentCredentialResolver(lambda _name: CANARY)
    sender = _Sender(b'{"error":{"message":"restricted provider prose"}}', status_code=503)
    transport = ConcreteLivePilotTransport(sender)

    record = validator.execute_one(
        authorization_document=_authorization(validator),
        confirm_live=True,
        credential_resolver=resolver,
        transport=transport,
        operational_root=tmp_path,
    )

    assert transport.invocation_count == 1
    assert record["result_status"] == "stopped"
    assert record["safe_failure_classification"] == "service_unavailable"
    assert record["retry_count"] == 0
    assert record["parser_result"] == "not_reached"
    serialized = json.dumps(record, sort_keys=True)
    assert "restricted provider prose" not in serialized
    assert CANARY not in serialized


def test_mock_execution_does_not_mutate_strict_evaluator_contracts(tmp_path):
    strict_paths = (
        ROOT / "docs/testing/ai-evaluation/experiment.v1.json",
        ROOT / "docs/testing/ai-evaluation/pilot-budget-control.v2.json",
        ROOT / "docs/testing/ai-evaluation/result-record.v1.json",
    )
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in strict_paths}
    validator = _validator()
    validator.execute_one(
        authorization_document=_authorization(validator),
        confirm_live=True,
        credential_resolver=LazyEnvironmentCredentialResolver(lambda _name: CANARY),
        transport=ConcreteLivePilotTransport(
            _Sender(_successful_openai_response(validator))
        ),
        operational_root=tmp_path,
    )

    assert {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in strict_paths
    } == before


def test_authorization_and_result_hashes_fail_closed_on_mutation(tmp_path):
    validator = _validator()
    authorization = _authorization(validator)
    changed = dict(authorization)
    changed["conservative_reservation_usd"] = "0.05169701"
    with pytest.raises(CapstoneLiveValidationError, match="authorization_hash"):
        validator.validate_authorization(changed)

    resolver = LazyEnvironmentCredentialResolver(lambda _name: CANARY)
    transport = ConcreteLivePilotTransport(_Sender(_successful_openai_response(validator)))
    validator.execute_one(
        authorization_document=authorization,
        confirm_live=True,
        credential_resolver=resolver,
        transport=transport,
        operational_root=tmp_path,
    )
    result_path = tmp_path / "capstone-live-validation-v1" / "result.json"
    changed_result = json.loads(result_path.read_text(encoding="utf-8"))
    changed_result["result_status"] = "stopped"
    result_path.write_text(json.dumps(changed_result), encoding="utf-8")
    with pytest.raises(CapstoneLiveValidationError, match="result_hash"):
        validator.inspect_result(tmp_path)
