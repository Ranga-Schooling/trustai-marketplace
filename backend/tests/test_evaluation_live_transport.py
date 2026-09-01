"""No-network tests for the concrete pilot HTTP boundary."""

from __future__ import annotations

from datetime import timedelta
import json
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from app.services.evaluation_pilot_runner import (
    LiveGateBinding,
    PilotRunnerError,
    SyntheticCredentialResolver,
    _synthetic_provider_envelope,
    build_provider_free_pilot_runner,
)
from app.services.evaluation_pilot_budget import empty_pilot_budget_ledger
from app.services.evaluation_retry_policy import AttemptDeadline
from app.services.evaluation_live_transport import (
    ConcreteLivePilotTransport,
    HttpConnectionFailure,
    HttpRequest,
    HttpResponse,
    HttpxSender,
    HttpTimeoutFailure,
    LazyEnvironmentCredentialResolver,
    LiveTransportError,
)


ROOT = Path(__file__).resolve().parents[2]
CANARY = "synthetic-live-canary-94ac2fc5a41945f9b90f2d111fdb2d19"


@pytest.fixture(scope="module")
def runner():
    return build_provider_free_pilot_runner(
        repository_root=ROOT,
        repository_harness_commit_sha="ccf26a2710c55ff94972c2af52d95bd971aa1796",
    )


def _call(runner, *, provider: str, stage: str, candidate: str | None = None):
    return next(
        item
        for item in runner.plan.provider_calls
        if item.provider == provider
        and item.workload_stage == stage
        and (candidate is None or item.candidate_id == candidate)
    )


class RecordingSender:
    def __init__(self, response=None, failure=None):
        self.requests = []
        self.response = response
        self.failure = failure

    def send(self, request):
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return self.response


class SequenceSender:
    def __init__(self, responses):
        self.requests = []
        self.responses = list(responses)

    def send(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def test_httpx_runtime_identity_is_safe_dependency_proof():
    identity = HttpxSender().validate_runtime()

    assert set(identity) == {
        "python_executable",
        "python_implementation",
        "python_version",
        "http_client_package",
        "http_client_version",
        "http_client_requirement",
    }
    assert Path(identity["python_executable"]).is_absolute()
    assert identity["python_implementation"] == "CPython"
    assert identity["http_client_package"] == "httpx"
    assert identity["http_client_requirement"] == "httpx>=0.27"
    assert identity["http_client_version"]
    assert "key" not in json.dumps(identity).lower()


def test_live_transport_offline_projection_freezes_endpoint_without_credentials(
    runner,
):
    request = runner.build_native_request(
        _call(
            runner,
            provider="OpenAI",
            stage="text_analysis",
            candidate="openai_unified_balanced_v1",
        )
    )
    projection = ConcreteLivePilotTransport(
        RecordingSender()
    ).offline_request_projection(request)

    assert projection == {
        "method": "POST",
        "url": "https://api.openai.com/v1/responses",
        "timeout_seconds": 120,
        "redirects_allowed": False,
        "automatic_retry_count": 0,
    }


def test_httpx_sender_measures_elapsed_without_reading_open_response(monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        def __init__(self):
            self.closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.closed = True

        def iter_bytes(self):
            yield b'{"ok":true}'

        @property
        def elapsed(self):
            if not self.closed:
                raise RuntimeError("elapsed read before response close")
            return timedelta(seconds=0.25)

    response = FakeResponse()

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def stream(self, *_args, **_kwargs):
            return response

    class FakeTimeoutException(Exception):
        pass

    class FakeTransportError(Exception):
        pass

    monkeypatch.setitem(
        sys.modules,
        "httpx",
        SimpleNamespace(
            Client=FakeClient,
            Timeout=lambda seconds: seconds,
            TimeoutException=FakeTimeoutException,
            TransportError=FakeTransportError,
        ),
    )
    ticks = iter((10.0, 10.25))
    monkeypatch.setattr(
        "app.services.evaluation_live_transport.monotonic",
        lambda: next(ticks),
    )

    result = HttpxSender().send(
        HttpRequest(
            method="POST",
            url="https://api.openai.com/v1/responses",
            headers=(("content-type", "application/json"),),
            body=b"{}",
            timeout_seconds=120,
        )
    )

    assert response.closed is True
    assert result.status_code == 200
    assert result.body_chunks == (b'{"ok":true}',)
    assert result.elapsed_seconds == 0.25


@pytest.mark.parametrize(
    ("failure_kind", "expected_exception"),
    (
        ("dns", HttpConnectionFailure),
        ("tls", HttpConnectionFailure),
        ("refused", HttpConnectionFailure),
        ("timeout", HttpTimeoutFailure),
    ),
)
def test_httpx_sender_maps_transport_failures_without_network(
    monkeypatch,
    failure_kind,
    expected_exception,
):
    import httpx

    failure = (
        httpx.ReadTimeout("timeout")
        if failure_kind == "timeout"
        else httpx.ConnectError(failure_kind)
    )

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def stream(self, *_args, **_kwargs):
            raise failure

    monkeypatch.setattr(httpx, "Client", FakeClient)

    with pytest.raises(expected_exception):
        HttpxSender().send(
            HttpRequest(
                method="POST",
                url="https://api.openai.com/v1/responses",
                headers=(("content-type", "application/json"),),
                body=b"{}",
                timeout_seconds=120,
            )
        )


def test_malformed_provider_url_is_rejected_before_http_sender():
    with pytest.raises(LiveTransportError, match="http_request"):
        HttpRequest(
            method="POST",
            url="http://localhost:8000/v1/responses",
            headers=(("content-type", "application/json"),),
            body=b"{}",
            timeout_seconds=120,
        )


def _synthetic_gate(runner):
    return LiveGateBinding.synthetic_for_tests(
        evaluation_id=runner.evaluation_id,
        experiment_version=runner.experiment_version,
        request_configuration_set_hash=runner.request_configuration_set_hash,
        budget_control_hash=runner.budget_control_hash,
        region_binding_hash=runner.region_binding_hash,
        valid_on_date="2026-09-01",
        credential_references=runner.credential_references,
    )


def _native_for_rehearsal(runner, call):
    if call.workload_stage == "search_synthesis":
        evidence, tool_data = runner._synthetic_ps1_material(call)
        return runner._build_native_request(
            call,
            ps1_evidence=evidence,
            search_tool_data=tool_data,
        )
    return runner.build_native_request(call)


@pytest.mark.parametrize(
    ("provider", "stage", "expected_url", "credential_header"),
    (
        ("OpenAI", "text_analysis", "https://api.openai.com/v1/responses", "authorization"),
        (
            "Google Gemini",
            "text_analysis",
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            "x-goog-api-key",
        ),
        (
            "Groq",
            "text_analysis",
            "https://api.groq.com/openai/v1/chat/completions",
            "authorization",
        ),
    ),
)
def test_live_transport_injects_auth_only_at_one_mock_http_boundary(
    runner, provider, stage, expected_url, credential_header
):
    call = _call(runner, provider=provider, stage=stage)
    native = runner.build_native_request(call)
    body = _synthetic_provider_envelope(native)
    sender = RecordingSender(
        HttpResponse(200, (body,), {"content-type": "application/json"}, 0.25)
    )
    transport = ConcreteLivePilotTransport(sender)
    resolver = SyntheticCredentialResolver(
        {"OPENAI_API_KEY": CANARY, "GEMINI_API_KEY": CANARY, "GROQ_API_KEY": CANARY}
    )
    reference = next(item for item in runner.credential_references if item.provider == provider)

    result = transport.invoke(native, resolver.resolve(reference), AttemptDeadline(0.0))

    assert result.status_code == 200
    assert result.response_bytes == body
    assert len(sender.requests) == 1
    outgoing = sender.requests[0]
    assert outgoing.method == "POST"
    assert outgoing.url == expected_url
    assert outgoing.timeout_seconds == 120
    headers = dict(outgoing.headers)
    assert headers["content-type"] == "application/json"
    assert CANARY in headers[credential_header]
    assert CANARY not in repr(outgoing)
    assert CANARY not in json.dumps(outgoing.safe_projection(), sort_keys=True)
    assert CANARY not in repr(transport)


def test_live_environment_resolver_is_lazy_and_redacted(runner):
    reads = []

    def getter(name):
        reads.append(name)
        return CANARY

    resolver = LazyEnvironmentCredentialResolver(getter)
    assert reads == []
    assert CANARY not in repr(resolver)

    credential = resolver.resolve(runner.credential_references[0])

    assert reads == ["OPENAI_API_KEY"]
    assert CANARY not in repr(credential)
    assert CANARY not in repr(resolver)


def test_missing_live_credential_fails_before_sender(runner):
    resolver = LazyEnvironmentCredentialResolver(lambda _name: "")

    with pytest.raises(PilotRunnerError, match="credential_unavailable"):
        resolver.resolve(runner.credential_references[0])

    assert resolver.requested_environment_variable_names == ("OPENAI_API_KEY",)


def test_gemini_request_uses_current_documented_interactions_shapes(runner):
    text = runner.build_native_request(
        _call(runner, provider="Google Gemini", stage="text_analysis")
    ).payload
    visual = runner.build_native_request(
        _call(runner, provider="Google Gemini", stage="visual_inspection")
    ).payload

    assert text["response_format"] == {
        "type": "text",
        "mime_type": "application/json",
        "schema": text["response_format"]["schema"],
    }
    image = visual["input"][0]["content"][-1]
    assert set(image) == {"type", "data", "mime_type"}
    assert image["type"] == "image"
    assert image["mime_type"] == "image/png"
    assert not image["data"].startswith("data:")


@pytest.mark.parametrize(
    ("failure", "signal"),
    (
        (HttpConnectionFailure("safe"), "connection"),
        (HttpTimeoutFailure("safe"), "timeout"),
    ),
)
def test_transport_maps_safe_sender_failures_without_retries(runner, failure, signal):
    call = _call(runner, provider="OpenAI", stage="text_analysis")
    native = runner.build_native_request(call)
    sender = RecordingSender(failure=failure)
    transport = ConcreteLivePilotTransport(sender)
    resolver = SyntheticCredentialResolver(
        {"OPENAI_API_KEY": CANARY, "GEMINI_API_KEY": CANARY, "GROQ_API_KEY": CANARY}
    )

    result = transport.invoke(
        native,
        resolver.resolve(runner.credential_references[0]),
        AttemptDeadline(0.0),
    )

    assert result.failure_signal == signal
    assert len(sender.requests) == 1


def test_unexpected_sender_exception_after_invocation_maps_to_safe_connection_loss(
    runner,
):
    call = _call(runner, provider="OpenAI", stage="text_analysis")
    native = runner.build_native_request(call)
    sender = RecordingSender(failure=RuntimeError(CANARY))
    transport = ConcreteLivePilotTransport(sender)
    resolver = SyntheticCredentialResolver(
        {"OPENAI_API_KEY": CANARY, "GEMINI_API_KEY": CANARY, "GROQ_API_KEY": CANARY}
    )

    result = transport.invoke(
        native,
        resolver.resolve(runner.credential_references[0]),
        AttemptDeadline(0.0),
    )

    assert result.failure_signal == "connection"
    assert result.response_bytes == b""
    assert transport.invocation_count == 1
    assert CANARY not in repr(result)


@pytest.mark.parametrize(
    ("status", "expected"),
    (
        (401, "http_failure"),
        (403, "http_failure"),
        (404, "http_failure"),
        (429, "rate_limit"),
        (500, "service_unavailable"),
        (503, "service_unavailable"),
    ),
)
def test_transport_maps_http_failures_without_provider_prose(runner, status, expected):
    call = _call(runner, provider="Groq", stage="text_analysis")
    native = runner.build_native_request(call)
    sender = RecordingSender(
        HttpResponse(status, (b'{"error":"provider prose must not escape"}',), {"content-type": "application/json"}, 1.0)
    )
    transport = ConcreteLivePilotTransport(sender)
    resolver = SyntheticCredentialResolver(
        {"OPENAI_API_KEY": CANARY, "GEMINI_API_KEY": CANARY, "GROQ_API_KEY": CANARY}
    )
    reference = next(item for item in runner.credential_references if item.provider == "Groq")

    result = transport.invoke(native, resolver.resolve(reference), AttemptDeadline(0.0))

    assert result.failure_signal == expected
    assert len(sender.requests) == 1


def test_successful_non_json_content_type_fails_transport_extraction(runner):
    call = _call(runner, provider="OpenAI", stage="text_analysis")
    native = runner.build_native_request(call)
    sender = RecordingSender(HttpResponse(200, (b"not json",), {"content-type": "text/html"}, 1.0))
    transport = ConcreteLivePilotTransport(sender)
    resolver = SyntheticCredentialResolver(
        {"OPENAI_API_KEY": CANARY, "GEMINI_API_KEY": CANARY, "GROQ_API_KEY": CANARY}
    )

    result = transport.invoke(
        native, resolver.resolve(runner.credential_references[0]), AttemptDeadline(0.0)
    )

    assert result.failure_signal == "malformed"
    assert result.response_bytes == b"not json"


def test_wrong_frozen_model_is_rejected_before_mock_http_boundary(runner):
    call = _call(runner, provider="OpenAI", stage="text_analysis")
    native = runner.build_native_request(call)
    payload = native.payload
    payload["model"] = "application-default-model"
    mutated = replace(
        native,
        payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
    )
    sender = RecordingSender()
    transport = ConcreteLivePilotTransport(sender)
    resolver = SyntheticCredentialResolver(
        {"OPENAI_API_KEY": CANARY, "GEMINI_API_KEY": CANARY, "GROQ_API_KEY": CANARY}
    )

    with pytest.raises(ValueError, match="request_payload"):
        transport.invoke(
            mutated,
            resolver.resolve(runner.credential_references[0]),
            AttemptDeadline(0.0),
        )

    assert sender.requests == []


def test_oversized_response_fails_closed_at_bounded_live_capture(runner):
    call = _call(runner, provider="OpenAI", stage="text_analysis")
    native = runner.build_native_request(call)
    sender = RecordingSender(
        HttpResponse(
            200,
            (b"x" * 2_100_000,),
            {"content-type": "application/json"},
            1.0,
        )
    )
    transport = ConcreteLivePilotTransport(sender)
    resolver = SyntheticCredentialResolver(
        {"OPENAI_API_KEY": CANARY, "GEMINI_API_KEY": CANARY, "GROQ_API_KEY": CANARY}
    )

    result = transport.invoke(
        native,
        resolver.resolve(runner.credential_references[0]),
        AttemptDeadline(0.0),
    )

    assert result.failure_signal == "malformed"
    assert result.response_bytes == b""
    assert len(sender.requests) == 1


def test_budget_failure_precedes_lazy_secret_resolution_and_http(runner):
    reads = []
    resolver = LazyEnvironmentCredentialResolver(
        lambda name: reads.append(name) or CANARY
    )
    sender = RecordingSender()
    call = _call(
        runner,
        provider="Groq",
        stage="text_analysis",
        candidate="baseline_current_text_v1",
    )

    with pytest.raises(ValueError, match="pilot_budget_ceiling_exhausted"):
        runner.execute_one(
            call,
            gate=_synthetic_gate(runner),
            credential_resolver=resolver,
            transport=ConcreteLivePilotTransport(sender),
            budget_ledger=empty_pilot_budget_ledger(),
            conservative_reservation_usd="5.01",
            synthetic_today="2026-09-01",
        )

    assert reads == []
    assert sender.requests == []


def test_gate_failure_precedes_lazy_secret_resolution_and_http(runner):
    reads = []
    resolver = LazyEnvironmentCredentialResolver(
        lambda name: reads.append(name) or CANARY
    )
    sender = RecordingSender()
    call = _call(runner, provider="OpenAI", stage="text_analysis")

    with pytest.raises(ValueError, match="live_gate"):
        runner.execute_one(
            call,
            gate=replace(_synthetic_gate(runner), evaluation_id="wrong"),
            credential_resolver=resolver,
            transport=ConcreteLivePilotTransport(sender),
            budget_ledger=empty_pilot_budget_ledger(),
            conservative_reservation_usd="0.01",
            synthetic_today="2026-09-01",
        )

    assert reads == []
    assert sender.requests == []


def test_canary_secret_never_enters_records_ledger_serialization_or_repr(runner):
    call = _call(
        runner,
        provider="Groq",
        stage="text_analysis",
        candidate="baseline_current_text_v1",
    )
    native = runner.build_native_request(call)
    sender = RecordingSender(
        HttpResponse(
            200,
            (_synthetic_provider_envelope(native),),
            {"content-type": "application/json"},
            0.5,
        )
    )
    resolver = SyntheticCredentialResolver(
        {"OPENAI_API_KEY": CANARY, "GEMINI_API_KEY": CANARY, "GROQ_API_KEY": CANARY}
    )
    transport = ConcreteLivePilotTransport(sender)

    outcome = runner.execute_one(
        call,
        gate=_synthetic_gate(runner),
        credential_resolver=resolver,
        transport=transport,
        budget_ledger=empty_pilot_budget_ledger(),
        conservative_reservation_usd="0.01",
        synthetic_today="2026-09-01",
    )

    projections = (
        repr(outcome),
        repr(outcome.record),
        repr(outcome.budget_ledger),
        json.dumps(outcome.record.as_dict(), sort_keys=True),
        json.dumps(sender.requests[0].safe_projection(), sort_keys=True),
        repr(transport),
        repr(resolver),
    )
    assert outcome.accepted is True
    assert all(CANARY not in projection for projection in projections)


def test_full_pilot_rehearsal_uses_concrete_transports_and_mock_http_only(runner):
    responses = []
    for call in runner.plan.provider_calls:
        native = _native_for_rehearsal(runner, call)
        responses.append(
            HttpResponse(
                200,
                (_synthetic_provider_envelope(native),),
                {"content-type": "application/json"},
                0.25,
            )
        )
    # Exercise the frozen retry authority at the real transport boundary.
    responses.insert(
        0,
        HttpResponse(
            503,
            (b'{"error":"synthetic unavailable"}',),
            {"content-type": "application/json"},
            0.1,
        ),
    )
    sender = SequenceSender(responses)
    transport = ConcreteLivePilotTransport(sender)
    resolver = SyntheticCredentialResolver(
        {"OPENAI_API_KEY": CANARY, "GEMINI_API_KEY": CANARY, "GROQ_API_KEY": CANARY}
    )

    summary = runner.run_complete_synthetic_pilot(
        gate=_synthetic_gate(runner),
        credential_resolver=resolver,
        transport=transport,
        conservative_reservation_usd="0.01",
        synthetic_today="2026-09-01",
    )

    assert summary.completed_logical_runs == 21
    assert summary.failed_logical_runs == 0
    assert summary.synthetic_physical_attempts == 23
    assert summary.pf1_no_call_executions == 1
    assert len(sender.requests) == 23
    assert transport.invocation_count == 23
    assert resolver.resolution_count == 23
    assert sender.responses == []
    assert {request.url for request in sender.requests} == {
        "https://api.openai.com/v1/responses",
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        "https://api.groq.com/openai/v1/chat/completions",
    }
