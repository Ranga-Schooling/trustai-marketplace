import hashlib
import json
import os
import sys
from decimal import Decimal

import httpx
import pytest

from app.schemas.schemas import AIAnalysisResult
from app.services.ai import GPTAnalysisObservation
from scripts.terra_text_smoke import (
    RESULT_CONTRACT_ID,
    RESULT_FILE,
    SMOKE_ID,
    SmokeAuthorizationError,
    _load_authorization,
    build_result_record,
    build_smoke_descriptor,
    build_smoke_request_bytes,
    claim_smoke_attempt,
    initialize_packet,
    inspect_result,
    main,
    run_authorized_smoke,
    validate_authorization,
    write_result_record,
)


HEAD = "a" * 40

VALID_RESULT = {
    "summary": "No obvious risk indicators were found.",
    "risk_level": "low",
    "risk_indicators": [],
    "price_assessment": "Current pricing was not verified.",
    "price_plausibility": "plausible",
    "seller_questions": ["Can I inspect the item before paying?"],
    "recommendation": "buy",
}


class FakeResponse:
    def __init__(self, *, status_code=200, result=None, usage=None):
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}
        self.body = {
            "model": "gpt-5.6-terra",
            "status": "completed",
            "error": None,
            "incomplete_details": None,
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                VALID_RESULT if result is None else result
                            ),
                        }
                    ],
                }
            ],
            "usage": usage
            if usage is not None
            else {
                "input_tokens": 1000,
                "input_tokens_details": {"cached_tokens": 100},
                "output_tokens": 100,
                "output_tokens_details": {"reasoning_tokens": 20},
                "total_tokens": 1100,
            },
        }
        self.content = json.dumps(self.body, sort_keys=True).encode()


def _authorization(descriptor):
    return {
        **descriptor,
        "authorization_scope": "production_text_smoke",
        "authorized": True,
    }


def test_descriptor_binds_actual_production_request_and_small_cost_ceiling():
    descriptor = build_smoke_descriptor(HEAD)

    assert descriptor["smoke_id"] == SMOKE_ID
    assert descriptor["smoke_id"] == "terra-production-text-smoke-v2"
    assert descriptor["repository_head"] == HEAD
    assert descriptor["provider"] == "OpenAI"
    assert descriptor["model"] == "gpt-5.6-terra"
    assert descriptor["endpoint"] == "https://api.openai.com/v1/responses"
    assert descriptor["maximum_physical_attempts"] == 1
    assert descriptor["retries"] == 0
    assert descriptor["timeout_seconds"] == 30
    assert descriptor["maximum_output_tokens"] == 2048
    assert descriptor["store"] is False
    assert descriptor["stream"] is False
    assert descriptor["tools_enabled"] is False
    assert descriptor["fixture_id"] == "terra-production-text-smoke-synthetic-v1"
    assert descriptor["prompt_version"] == "v4"
    assert descriptor["fixture_hash"] == (
        "e858ae15b124170e099d547a6b0ae2c9dbee768ee5b49476af4f4afaecee8c2d"
    )
    assert descriptor["prompt_hash"] == (
        "70851206a144be2393267c0dc5fc2de6ed16f07cdf11972b16072fc72080a0dd"
    )
    assert descriptor["schema_hash"] == (
        "414d408587675813d3af8d3df20d3e992a844aa195cc41b256a9d3c561ea1a00"
    )
    assert descriptor["request_configuration_hash"] == (
        "c12d9adfcaafd90e06b9d25f2417373bc68888c90cf4706612bef4b502ea5cbf"
    )
    assert descriptor["request_hash"] == (
        "e887d64a0ecbead51f9f90b6a24c1db78524351840ff65d2269d0a9b1b3af100"
    )
    assert descriptor["request_bytes"] == 6392
    assert descriptor["cost_ceiling_usd"] == "0.03736000"

    request_bytes = build_smoke_request_bytes()
    assert hashlib.sha256(request_bytes).hexdigest() == descriptor["request_hash"]
    request = json.loads(request_bytes)
    assert request["model"] == descriptor["model"]
    assert request["max_output_tokens"] == descriptor["maximum_output_tokens"]
    assert "tools" not in request


def test_authorization_requires_an_exact_closed_identity():
    descriptor = build_smoke_descriptor(HEAD)
    authorization = _authorization(descriptor)

    validate_authorization(authorization, descriptor)

    for mutation in (
        lambda value: value.__setitem__("request_hash", "0" * 64),
        lambda value: value.__setitem__("maximum_physical_attempts", 2),
        lambda value: value.__setitem__("retries", 1),
        lambda value: value.__setitem__("unexpected", True),
        lambda value: value.__setitem__("authorized", False),
    ):
        changed = dict(authorization)
        mutation(changed)
        with pytest.raises(SmokeAuthorizationError):
            validate_authorization(changed, descriptor)


def test_authorization_file_must_be_private_regular_file(tmp_path):
    descriptor = build_smoke_descriptor(HEAD)
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text(json.dumps(_authorization(descriptor)))
    authorization_path.chmod(0o644)
    with pytest.raises(SmokeAuthorizationError):
        _load_authorization(authorization_path)

    authorization_path.chmod(0o600)
    assert _load_authorization(authorization_path) == _authorization(descriptor)

    symlink = tmp_path / "authorization-link.json"
    symlink.symlink_to(authorization_path)
    with pytest.raises(SmokeAuthorizationError):
        _load_authorization(symlink)


def test_authorized_smoke_uses_production_adapter_once_with_retries_disabled():
    descriptor = build_smoke_descriptor(HEAD)
    observed = {"factory_calls": 0, "analyze_calls": 0}

    class FakeProvider:
        def __init__(self, *, maximum_attempts, observation_callback):
            observed["factory_calls"] += 1
            observed["maximum_attempts"] = maximum_attempts
            self.model_name = "gpt-5.6-terra"
            self.observation_callback = observation_callback

        def request_payload(self, listing):
            from app.services.ai import build_openai_responses_payload

            return build_openai_responses_payload(listing, self.model_name)

        def analyze(self, listing):
            observed["analyze_calls"] += 1
            result = AIAnalysisResult(**VALID_RESULT)
            self.observation_callback(
                GPTAnalysisObservation(
                    safe_finish_reason="completed",
                    physical_provider_attempts=1,
                    retry_count=0,
                    http_status=200,
                    latency_seconds=0.25,
                    provider_usage={
                        "input_tokens": 1000,
                        "output_tokens": 100,
                        "cached_input_tokens": 100,
                        "reasoning_tokens": 20,
                    },
                    parser_result="passed",
                    schema_result="passed",
                    validator_result="passed",
                    evidence_policy_result="passed",
                    ai_analysis_result_mapping_result="passed",
                    raw_response_hash="b" * 64,
                )
            )
            return result, result.model_dump_json()

    record = run_authorized_smoke(
        _authorization(descriptor),
        repository_head=HEAD,
        provider_factory=FakeProvider,
    )

    assert observed == {
        "factory_calls": 1,
        "maximum_attempts": 1,
        "analyze_calls": 1,
    }
    assert record["smoke_id"] == SMOKE_ID
    assert record["result_status"] == "accepted"
    assert record["safe_finish_reason"] == "completed"
    assert record["physical_provider_attempts"] == 1
    assert record["retry_count"] == 0
    assert record["http_status"] == 200
    assert record["latency_seconds"] == 0.25
    assert record["provider_usage"] == {
        "input_tokens": 1000,
        "output_tokens": 100,
        "cached_input_tokens": 100,
        "reasoning_tokens": 20,
    }
    assert record["estimated_cost_usd"] == "0.00302000"
    assert record["parser_result"] == "passed"
    assert record["schema_result"] == "passed"
    assert record["validator_result"] == "passed"
    assert record["evidence_policy_result"] == "passed"
    assert record["ai_analysis_result_mapping_result"] == "passed"
    assert record["raw_provider_content_exposed"] is False
    assert record["repository_mutated"] is False
    assert record["raw_response_hash"] == "b" * 64
    assert record["normalized_semantic_hash"]
    assert record["record_hash"]
    assert set(record) == {
        "ai_analysis_result_mapping_result",
        "certified_cost_ceiling_usd",
        "configuration_hash",
        "endpoint_identity",
        "estimated_cost_usd",
        "evidence_policy_result",
        "fixture_hash",
        "fixture_id",
        "http_status",
        "latency_seconds",
        "model",
        "normalized_semantic_hash",
        "parser_result",
        "physical_provider_attempts",
        "prompt_hash",
        "prompt_version",
        "provider",
        "provider_usage",
        "raw_provider_content_exposed",
        "raw_response_hash",
        "record_hash",
        "repository_head",
        "repository_mutated",
        "request_configuration_id",
        "request_hash",
        "result_contract_id",
        "result_contract_version",
        "result_status",
        "retry_count",
        "safe_finish_reason",
        "schema_hash",
        "schema_result",
        "smoke_id",
        "validator_result",
    }


def test_smoke_stops_before_provider_construction_on_head_mismatch():
    descriptor = build_smoke_descriptor(HEAD)
    calls = 0

    def provider_factory(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be constructed")

    with pytest.raises(SmokeAuthorizationError):
        run_authorized_smoke(
            _authorization(descriptor),
            repository_head="b" * 40,
            provider_factory=provider_factory,
        )

    assert calls == 0


def test_attempt_claim_is_atomic_and_single_use(tmp_path):
    descriptor = build_smoke_descriptor(HEAD)
    packet = tmp_path / "packet"
    initialize_packet(packet)

    claim_smoke_attempt(packet, descriptor)

    marker = json.loads((packet / "attempt-started.json").read_text())
    assert marker == {
        "smoke_id": SMOKE_ID,
        "repository_head": HEAD,
        "request_hash": descriptor["request_hash"],
        "maximum_physical_attempts": 1,
        "retries": 0,
    }
    with pytest.raises(SmokeAuthorizationError):
        claim_smoke_attempt(packet, descriptor)

    assert oct((packet / "attempt-started.json").stat().st_mode & 0o777) == "0o600"


def _observation(**overrides):
    values = {
        "safe_finish_reason": "completed",
        "physical_provider_attempts": 1,
        "retry_count": 0,
        "http_status": 200,
        "latency_seconds": 0.5,
        "provider_usage": {
            "input_tokens": 1000,
            "output_tokens": 100,
            "cached_input_tokens": 100,
            "reasoning_tokens": 20,
        },
        "parser_result": "passed",
        "schema_result": "passed",
        "validator_result": "passed",
        "evidence_policy_result": "passed",
        "ai_analysis_result_mapping_result": "passed",
        "raw_response_hash": "c" * 64,
    }
    values.update(overrides)
    return GPTAnalysisObservation(**values)


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        (
            {
                "input_tokens": 1000,
                "output_tokens": 100,
                "cached_input_tokens": 100,
                "reasoning_tokens": 20,
            },
            "0.00302000",
        ),
        (
            {
                "input_tokens": 1000,
                "output_tokens": 100,
                "cached_input_tokens": None,
                "reasoning_tokens": None,
            },
            "0.00320000",
        ),
    ],
)
def test_exact_cost_uses_cached_discount_and_never_double_counts_reasoning(
    usage,
    expected,
):
    record = build_result_record(
        build_smoke_descriptor(HEAD),
        _observation(provider_usage=usage),
        AIAnalysisResult(**VALID_RESULT),
    )

    assert record["estimated_cost_usd"] == expected


@pytest.mark.parametrize(
    ("usage", "expected_status"),
    [
        (None, "rejected"),
        (
            {
                "input_tokens": 6392,
                "output_tokens": 2048,
                "cached_input_tokens": 0,
                "reasoning_tokens": 0,
            },
            "accepted",
        ),
        (
            {
                "input_tokens": 6393,
                "output_tokens": 2048,
                "cached_input_tokens": 0,
                "reasoning_tokens": 0,
            },
            "rejected",
        ),
    ],
)
def test_usage_and_cost_gate_missing_equal_and_above_ceiling(usage, expected_status):
    record = build_result_record(
        build_smoke_descriptor(HEAD),
        _observation(provider_usage=usage),
        AIAnalysisResult(**VALID_RESULT),
    )

    assert record["result_status"] == expected_status
    if usage is None:
        assert record["estimated_cost_usd"] is None
        assert record["safe_finish_reason"] == "usage_unavailable"
    elif expected_status == "rejected":
        assert record["safe_finish_reason"] == "cost_ceiling_exceeded"


def _run_real_adapter(monkeypatch, response_or_error):
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        if isinstance(response_or_error, Exception):
            raise response_or_error
        return response_or_error

    monkeypatch.setattr("app.services.ai.httpx.post", fake_post)
    monkeypatch.setattr(
        "app.services.ai.settings.openai_api_key",
        "test-only-placeholder",
    )
    monkeypatch.setattr("app.services.ai.settings.openai_model", "gpt-5.6-terra")
    descriptor = build_smoke_descriptor(HEAD)
    record = run_authorized_smoke(_authorization(descriptor), repository_head=HEAD)
    return record, calls


def test_real_adapter_success_retains_safe_usage_latency_hashes_and_no_prose(
    monkeypatch,
):
    response = FakeResponse()
    ticks = iter((10.0, 10.25))
    monkeypatch.setattr("app.services.ai.time.monotonic", lambda: next(ticks))

    record, calls = _run_real_adapter(monkeypatch, response)

    assert calls == 1
    assert record["result_status"] == "accepted"
    assert record["latency_seconds"] == 0.25
    assert record["raw_response_hash"] == hashlib.sha256(response.content).hexdigest()
    serialized = json.dumps(record, sort_keys=True)
    assert json.dumps(VALID_RESULT) not in serialized
    assert "test-only-placeholder" not in serialized
    assert "Authorization" not in serialized


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {"input_tokens": "100", "output_tokens": 20},
        {"input_tokens": 100, "output_tokens": -1},
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "input_tokens_details": {"cached_tokens": 101},
        },
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "output_tokens_details": {"reasoning_tokens": 21},
        },
    ],
)
def test_missing_or_malformed_usage_fails_smoke_certification(monkeypatch, usage):
    response = FakeResponse(usage={})
    response.body["usage"] = usage
    response.content = json.dumps(response.body, sort_keys=True).encode()

    record, calls = _run_real_adapter(monkeypatch, response)

    assert calls == 1
    assert record["result_status"] == "rejected"
    assert record["safe_finish_reason"] == "usage_unavailable"
    assert record["provider_usage"] is None


def test_optional_usage_detail_objects_may_omit_optional_counters(monkeypatch):
    response = FakeResponse(
        usage={
            "input_tokens": 1000,
            "input_tokens_details": {},
            "output_tokens": 100,
            "output_tokens_details": {},
        }
    )

    record, calls = _run_real_adapter(monkeypatch, response)

    assert calls == 1
    assert record["result_status"] == "accepted"
    assert record["provider_usage"]["cached_input_tokens"] is None
    assert record["provider_usage"]["reasoning_tokens"] is None
    assert record["estimated_cost_usd"] == "0.00320000"


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 409, 422, 429, 500])
def test_every_http_failure_consumes_exactly_one_smoke_attempt(
    monkeypatch,
    status_code,
):
    record, calls = _run_real_adapter(
        monkeypatch,
        FakeResponse(status_code=status_code),
    )

    assert calls == 1
    assert record["result_status"] == "rejected"
    assert record["safe_finish_reason"] == "http_error"
    assert record["http_status"] == status_code
    assert record["physical_provider_attempts"] == 1
    assert record["retry_count"] == 0
    assert record["parser_result"] == "not_reached"


@pytest.mark.parametrize(
    ("error", "finish_reason"),
    [
        (httpx.ReadTimeout("timeout"), "timeout"),
        (httpx.ConnectError("connection"), "transport_error"),
    ],
)
def test_transport_failures_consume_exactly_one_smoke_attempt(
    monkeypatch,
    error,
    finish_reason,
):
    record, calls = _run_real_adapter(monkeypatch, error)

    assert calls == 1
    assert record["result_status"] == "rejected"
    assert record["safe_finish_reason"] == finish_reason
    assert record["http_status"] is None
    assert record["physical_provider_attempts"] == 1


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ("not-json", ("failed", "not_reached", "not_reached", "not_reached")),
        (
            {"summary": "missing fields"},
            ("passed", "failed", "not_reached", "not_reached"),
        ),
        (
            {**VALID_RESULT, "recommendation": "avoid"},
            ("passed", "passed", "failed", "not_reached"),
        ),
        (
            {
                **VALID_RESULT,
                "summary": "This unknown product is counterfeit.",
            },
            ("passed", "passed", "passed", "failed"),
        ),
    ],
)
def test_validation_stage_evidence_is_fail_closed(monkeypatch, result, expected):
    response = FakeResponse()
    response.body["output"][0]["content"][0]["text"] = (
        result if isinstance(result, str) else json.dumps(result)
    )
    response.content = json.dumps(response.body, sort_keys=True).encode()

    record, calls = _run_real_adapter(monkeypatch, response)

    assert calls == 1
    assert record["result_status"] == "rejected"
    assert (
        record["parser_result"],
        record["schema_result"],
        record["validator_result"],
        record["evidence_policy_result"],
    ) == expected


def test_private_packet_record_is_immutable_hash_checked_and_offline_inspectable(
    tmp_path,
):
    packet = tmp_path / "packet"
    initialize_packet(packet)
    assert oct(packet.stat().st_mode & 0o777) == "0o700"

    descriptor = build_smoke_descriptor(HEAD)
    record = build_result_record(
        descriptor,
        _observation(),
        AIAnalysisResult(**VALID_RESULT),
    )
    write_result_record(packet, record)

    result_path = packet / RESULT_FILE
    assert oct(result_path.stat().st_mode & 0o777) == "0o600"
    assert (
        json.loads(result_path.read_text())["result_contract_id"]
        == RESULT_CONTRACT_ID
    )
    inspected = inspect_result(packet, descriptor)
    assert inspected == record
    assert json.dumps(VALID_RESULT) not in json.dumps(inspected)

    with pytest.raises(SmokeAuthorizationError):
        write_result_record(packet, record)
    with pytest.raises(SmokeAuthorizationError):
        initialize_packet(packet)

    corrupt = json.loads(result_path.read_text())
    corrupt["result_status"] = "rejected"
    os.chmod(result_path, 0o600)
    result_path.write_text(json.dumps(corrupt))
    with pytest.raises(SmokeAuthorizationError):
        inspect_result(packet, descriptor)


def test_cli_initializes_preflights_executes_once_and_inspects_offline(
    tmp_path,
    monkeypatch,
    capsys,
):
    packet = tmp_path / "packet"
    common = ["terra_text_smoke", "--repository-head", HEAD]
    monkeypatch.setattr(
        sys,
        "argv",
        [common[0], "initialize", *common[1:], "--packet-dir", str(packet)],
    )
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == (
        "initialized_not_authorized"
    )

    descriptor = build_smoke_descriptor(HEAD)
    authorization_path = packet / "authorization.json"
    authorization_path.write_text(json.dumps(_authorization(descriptor)))
    authorization_path.chmod(0o600)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            common[0],
            "preflight",
            *common[1:],
            "--authorization-file",
            str(authorization_path),
            "--packet-dir",
            str(packet),
        ],
    )
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == (
        "ready_for_one_authorized_invocation"
    )

    record = build_result_record(
        descriptor,
        _observation(),
        AIAnalysisResult(**VALID_RESULT),
    )
    monkeypatch.setattr(
        "scripts.terra_text_smoke.run_authorized_smoke",
        lambda *args, **kwargs: record,
    )
    execute_arguments = [
        common[0],
        "execute",
        *common[1:],
        "--authorization-file",
        str(authorization_path),
        "--packet-dir",
        str(packet),
    ]
    monkeypatch.setattr(sys, "argv", execute_arguments)
    assert main() == 0
    assert json.loads(capsys.readouterr().out) == record

    monkeypatch.setattr(
        sys,
        "argv",
        [common[0], "inspect", *common[1:], "--packet-dir", str(packet)],
    )
    assert main() == 0
    inspected_output = capsys.readouterr().out
    assert json.loads(inspected_output) == record
    assert json.dumps(VALID_RESULT) not in inspected_output

    monkeypatch.setattr(sys, "argv", execute_arguments)
    with pytest.raises(SmokeAuthorizationError):
        main()
