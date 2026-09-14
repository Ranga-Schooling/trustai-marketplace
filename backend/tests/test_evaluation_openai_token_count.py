"""Socket-free tests for the one-call OpenAI input-token preflight."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import sys

import pytest

from app.services.evaluation_live_gate import load_same_day_certification
from app.services.evaluation_live_transport import LazyEnvironmentCredentialResolver
from app.services.evaluation_openai_token_count import (
    OPENAI_TOKEN_COUNT_ENDPOINT,
    OPENAI_TOKEN_COUNT_PATH,
    OpenAITokenCountHttpxSender,
    OpenAITokenCountError,
    OpenAITokenCountPreflight,
    TokenCountHttpRequest,
    TokenCountHttpResponse,
    build_call_0003_token_count_plan,
    build_token_count_authorization,
    calculate_call_0003_reservation,
    project_openai_token_count_payload,
    run_cli,
    validate_token_count_authorization,
    validate_token_count_evidence,
)
from app.services.evaluation_pilot_runner import build_provider_free_pilot_runner


ROOT = Path(__file__).resolve().parents[2]
HEAD = "c149946394d493097f8d4961c4cb7070b5a66dfd"
CERTIFICATION = (
    ROOT / "docs/testing/ai-evaluation/live-provider-certification.2026-09-01.json"
)
CANARY = "synthetic-token-count-secret-5ecb4f8cdb6e4e4bb1b792156c564b29"


@pytest.fixture(scope="module")
def runner():
    return build_provider_free_pilot_runner(
        repository_root=ROOT,
        repository_harness_commit_sha=HEAD,
    )


@pytest.fixture(scope="module")
def certification():
    return load_same_day_certification(
        CERTIFICATION,
        current_date="2026-09-01",
    )


@pytest.fixture(scope="module")
def plan(runner):
    return build_call_0003_token_count_plan(runner)


def _authorization(plan, certification, **changes):
    values = {
        "plan": plan,
        "certification": certification,
        "authorized_at_utc": "2026-09-01T12:00:00Z",
        "credential_readiness": "PRESENT",
        "provider_hard_spend_cap_usd": "5.00",
        "explicit_human_approval": True,
    }
    values.update(changes)
    return build_token_count_authorization(**values)


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


def _invoke(plan, certification, response):
    sender = RecordingSender(response)
    reads = []
    resolver = LazyEnvironmentCredentialResolver(
        lambda name: reads.append(name) or CANARY
    )
    preflight = OpenAITokenCountPreflight(sender)
    authorization = validate_token_count_authorization(
        _authorization(plan, certification),
        plan=plan,
        certification=certification,
        current_date="2026-09-01",
    )
    evidence = preflight.invoke(
        plan=plan,
        authorization=authorization,
        credential_resolver=resolver,
        observed_at_utc="2026-09-01T12:01:00Z",
    )
    return evidence, sender, reads, preflight, resolver


def test_call_0003_projection_preserves_every_supported_token_surface(plan):
    original = json.loads(plan.original_request_body.decode("utf-8"))
    projection = json.loads(plan.token_count_request_body.decode("utf-8"))

    assert plan.call_id == "call-0003"
    assert plan.candidate_id == "openai_unified_balanced_v1"
    assert plan.provider == "OpenAI"
    assert plan.model == "gpt-5.6-terra"
    assert plan.fixture_id == "PT1"
    assert plan.workload_stage == "text_analysis"
    assert plan.topology_id == "single_call_text"
    assert plan.request_configuration_id == "openai_terra_text_pilot_v1"
    assert plan.request_configuration_hash == (
        "0eca58d264b7af9e48af182f8d3ce8a0a417db8201328b70fdab77b6a4bae893"
    )
    assert plan.original_request_hash == (
        "97f8752bb33994a00018a15ff62d79419069397b223cc5f60770def973ebc266"
    )
    assert len(plan.original_request_body) == 6249
    assert set(projection) == {"input", "instructions", "model", "reasoning", "text"}
    for field in projection:
        assert projection[field] == original[field]
    assert projection["text"]["format"] == original["text"]["format"]
    assert plan.removed_generation_fields == (
        "max_output_tokens",
        "store",
        "stream",
        "temperature",
    )
    assert plan.method == "POST"
    assert plan.path == OPENAI_TOKEN_COUNT_PATH
    assert plan.endpoint == OPENAI_TOKEN_COUNT_ENDPOINT


@pytest.mark.parametrize(
    "field",
    (
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
    ),
)
def test_documented_count_fields_are_never_silently_omitted(field):
    payload = {
        "model": "gpt-5.6-terra",
        "input": "input",
        "instructions": "instructions",
        field: (
            {"value": field}
            if field not in {"model", "input", "instructions"}
            else field
        ),
    }

    projection = project_openai_token_count_payload(payload)

    assert field in projection
    assert projection[field] == payload[field]


def test_unknown_or_missing_token_surface_fails_closed():
    with pytest.raises(OpenAITokenCountError, match="unsupported_request_field"):
        project_openai_token_count_payload(
            {"model": "gpt-5.6-terra", "input": "x", "instructions": "y", "future": "z"}
        )
    with pytest.raises(OpenAITokenCountError, match="required_request_field"):
        project_openai_token_count_payload({"model": "gpt-5.6-terra", "input": "x"})


def test_plan_rejects_model_or_original_request_hash_mutation(runner, monkeypatch):
    call = next(
        item for item in runner.plan.provider_calls if item.call_id == "call-0003"
    )
    native = runner.build_native_request(call)
    payload = native.payload
    payload["model"] = "gpt-5.6-sol"
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    mutated = replace(native, payload_json=body, payload_hash=native.payload_hash)
    monkeypatch.setattr(
        type(runner),
        "build_native_request",
        lambda self, selected: mutated,
    )

    with pytest.raises(OpenAITokenCountError, match="original_request_identity"):
        build_call_0003_token_count_plan(runner)


def test_exact_decimal_reservation_has_short_and_long_context_branches():
    short = calculate_call_0003_reservation(1000)
    threshold = calculate_call_0003_reservation(272000)
    long = calculate_call_0003_reservation(272001)

    assert short == Decimal("0.05165200")
    assert threshold == Decimal("0.72915200")
    assert long == Decimal("1.43373300")
    assert calculate_call_0003_reservation(True) is None
    assert calculate_call_0003_reservation(-1) is None


def test_authorization_is_hash_bound_and_preserves_unknown_billing_permission(
    plan, certification
):
    document = _authorization(plan, certification)
    authorization = validate_token_count_authorization(
        document,
        plan=plan,
        certification=certification,
        current_date="2026-09-01",
    )

    assert authorization.scope == "openai_token_count_preflight_only"
    assert authorization.maximum_invocations == 1
    assert authorization.retry_count == 0
    assert authorization.operational_reservation_usd == Decimal("5.00")
    assert authorization.provider_permission_status == "unconfirmed_fail_closed"
    assert authorization.billing_status == "unknown_charge_requires_reconciliation"
    assert authorization.model_response_generation_authorized is False
    assert authorization.pilot_execution_authorized is False
    assert authorization.scored_execution_authorized is False

    document["request_hash"] = "0" * 64
    with pytest.raises(OpenAITokenCountError, match="authorization_hash"):
        validate_token_count_authorization(
            document,
            plan=plan,
            certification=certification,
            current_date="2026-09-01",
        )


def test_authorization_cannot_be_constructed_implicitly_or_mutated_after_validation(
    plan, certification
):
    with pytest.raises(OpenAITokenCountError, match="explicit_human_approval_required"):
        build_token_count_authorization(
            plan=plan,
            certification=certification,
            authorized_at_utc="2026-09-01T12:00:00Z",
            credential_readiness="PRESENT",
            provider_hard_spend_cap_usd="5.00",
        )
    authorization = validate_token_count_authorization(
        _authorization(plan, certification),
        plan=plan,
        certification=certification,
        current_date="2026-09-01",
    )
    with pytest.raises(OpenAITokenCountError, match="authorization_factory_required"):
        replace(authorization, scope="full_authorized_pilot")


def test_authorization_rejects_mismatched_certification_binding(plan, certification):
    with pytest.raises(OpenAITokenCountError, match="certification_binding"):
        _authorization(
            plan,
            replace(certification, budget_control_hash="0" * 64),
        )


@pytest.mark.parametrize(
    ("change", "error"),
    (
        ({"provider_hard_spend_cap_usd": "5.01"}, "spend_control"),
        ({"credential_readiness": "MISSING"}, "credential_readiness"),
        ({"authorized_at_utc": "2026-09-02T00:00:00Z"}, "authorization_freshness"),
    ),
)
def test_authorization_gates_fail_before_credential_resolution(
    plan, certification, change, error
):
    with pytest.raises(OpenAITokenCountError, match=error):
        _authorization(plan, certification, **change)


def test_exact_single_token_count_request_isolated_from_generation_transport(
    plan, certification
):
    response = TokenCountHttpResponse(
        200,
        (b'{"object":"response.input_tokens","input_tokens":1234}',),
        {"content-type": "application/json"},
        0.25,
    )

    evidence, sender, reads, preflight, resolver = _invoke(
        plan, certification, response
    )

    assert evidence.input_tokens == 1234
    assert evidence.invocation_count == 1
    assert evidence.retry_count == 0
    assert evidence.model_response_generated is False
    assert evidence.billing_state == "pending_cost_reconciliation"
    assert evidence.call_reservation_usd == "0.05223700"
    assert evidence.operational_reservation_usd == "5.00"
    assert evidence.rate_limit_compatibility == (
        "unresolved_provider_accounting_semantics"
    )
    assert reads == ["OPENAI_API_KEY"]
    assert resolver.resolution_count == 1
    assert preflight.invocation_count == 1
    assert len(sender.requests) == 1
    request = sender.requests[0]
    assert request.method == "POST"
    assert request.url == OPENAI_TOKEN_COUNT_ENDPOINT
    assert request.url != "https://api.openai.com/v1/responses"
    assert request.timeout_seconds == 120
    assert request.follow_redirects is False
    assert request.body == plan.token_count_request_body
    assert CANARY not in repr(request)
    assert CANARY not in json.dumps(request.safe_projection(), sort_keys=True)
    assert CANARY not in repr(preflight)
    assert CANARY not in repr(resolver)
    assert CANARY not in repr(evidence)

    with pytest.raises(OpenAITokenCountError, match="invocation_already_consumed"):
        preflight.invoke(
            plan=plan,
            authorization=validate_token_count_authorization(
                _authorization(plan, certification),
                plan=plan,
                certification=certification,
                current_date="2026-09-01",
            ),
            credential_resolver=resolver,
            observed_at_utc="2026-09-01T12:02:00Z",
        )
    assert len(sender.requests) == 1


@pytest.mark.parametrize("status", (301, 302, 307, 308))
def test_redirects_are_rejected_without_retry(plan, certification, status):
    sender = RecordingSender(
        TokenCountHttpResponse(
            status,
            (b"",),
            {"location": "https://api.openai.com/v1/responses"},
            0.1,
        )
    )
    preflight = OpenAITokenCountPreflight(sender)
    resolver = LazyEnvironmentCredentialResolver(lambda name: CANARY)

    with pytest.raises(OpenAITokenCountError, match="redirect_rejected"):
        preflight.invoke(
            plan=plan,
            authorization=validate_token_count_authorization(
                _authorization(plan, certification),
                plan=plan,
                certification=certification,
                current_date="2026-09-01",
            ),
            credential_resolver=resolver,
            observed_at_utc="2026-09-01T12:01:00Z",
        )

    assert len(sender.requests) == 1
    assert preflight.invocation_count == 1


@pytest.mark.parametrize(
    ("status", "error"),
    ((401, "permission_denied"), (403, "permission_denied"), (429, "http_failure")),
)
def test_http_failure_is_safe_and_never_retried(
    plan, certification, status, error
):
    sender = RecordingSender(
        TokenCountHttpResponse(
            status,
            ((f'{{"error":"{CANARY}"}}').encode(),),
            {"content-type": "application/json"},
            0.1,
        )
    )
    preflight = OpenAITokenCountPreflight(sender)

    with pytest.raises(OpenAITokenCountError, match=error) as captured:
        preflight.invoke(
            plan=plan,
            authorization=validate_token_count_authorization(
                _authorization(plan, certification),
                plan=plan,
                certification=certification,
                current_date="2026-09-01",
            ),
            credential_resolver=LazyEnvironmentCredentialResolver(lambda name: CANARY),
            observed_at_utc="2026-09-01T12:01:00Z",
        )

    assert len(sender.requests) == 1
    assert CANARY not in str(captured.value)


@pytest.mark.parametrize(
    "body",
    (
        b"not-json",
        b'{"object":"response.input_tokens"}',
        b'{"object":"response.input_tokens","input_tokens":-1}',
        b'{"object":"response.input_tokens","input_tokens":1.5}',
        b'{"object":"response.input_tokens","input_tokens":true}',
        b'{"object":"wrong","input_tokens":1}',
        b'{"object":"response.input_tokens","input_tokens":1,"input_tokens":2}',
    ),
)
def test_malformed_or_non_integer_count_response_fails_closed(
    plan, certification, body
):
    sender = RecordingSender(
        TokenCountHttpResponse(
            200,
            (body,),
            {"content-type": "application/json"},
            0.1,
        )
    )

    with pytest.raises(OpenAITokenCountError, match="count_response"):
        OpenAITokenCountPreflight(sender).invoke(
            plan=plan,
            authorization=validate_token_count_authorization(
                _authorization(plan, certification),
                plan=plan,
                certification=certification,
                current_date="2026-09-01",
            ),
            credential_resolver=LazyEnvironmentCredentialResolver(lambda name: CANARY),
            observed_at_utc="2026-09-01T12:01:00Z",
        )
    assert len(sender.requests) == 1


def test_evidence_is_hash_bound_and_cannot_be_reused_stale(plan, certification):
    evidence, _, _, _, _ = _invoke(
        plan,
        certification,
        TokenCountHttpResponse(
            200,
            (b'{"object":"response.input_tokens","input_tokens":1234}',),
            {"content-type": "application/json"},
            0.25,
        ),
    )

    validated = validate_token_count_evidence(
        evidence.as_dict(),
        plan=plan,
        certification=certification,
        authorization=validate_token_count_authorization(
            _authorization(plan, certification),
            plan=plan,
            certification=certification,
            current_date="2026-09-01",
        ),
        current_date="2026-09-01",
    )
    assert validated == evidence
    with pytest.raises(OpenAITokenCountError, match="evidence_freshness"):
        validate_token_count_evidence(
            evidence.as_dict(),
            plan=plan,
            certification=certification,
            authorization=validate_token_count_authorization(
                _authorization(plan, certification),
                plan=plan,
                certification=certification,
                current_date="2026-09-01",
            ),
            current_date="2026-09-02",
        )
    mutated = evidence.as_dict()
    mutated["model"] = "gpt-5.6-sol"
    with pytest.raises(OpenAITokenCountError, match="evidence_hash"):
        validate_token_count_evidence(
            mutated,
            plan=plan,
            certification=certification,
            authorization=validate_token_count_authorization(
                _authorization(plan, certification),
                plan=plan,
                certification=certification,
                current_date="2026-09-01",
            ),
            current_date="2026-09-01",
        )


def test_preflight_validation_failure_never_reads_the_credential(plan, certification):
    reads = []
    sender = RecordingSender()
    authorization = validate_token_count_authorization(
        _authorization(plan, certification),
        plan=plan,
        certification=certification,
        current_date="2026-09-01",
    )
    wrong = replace(plan, model="gpt-5.6-sol")

    with pytest.raises(OpenAITokenCountError, match="plan_identity"):
        OpenAITokenCountPreflight(sender).invoke(
            plan=wrong,
            authorization=authorization,
            credential_resolver=LazyEnvironmentCredentialResolver(
                lambda name: reads.append(name) or CANARY
            ),
            observed_at_utc="2026-09-01T12:01:00Z",
        )

    assert reads == []
    assert sender.requests == []


def test_httpx_sender_hard_codes_redirects_off_and_exact_endpoint(monkeypatch, plan):
    observed = {}

    class Elapsed:
        @staticmethod
        def total_seconds():
            return 0.25

    class Response:
        status_code = 200
        headers = {"content-type": "application/json"}
        elapsed = Elapsed()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @staticmethod
        def iter_bytes():
            return iter((b'{"object":"response.input_tokens","input_tokens":1}',))

    class Client:
        def __init__(self, *, timeout, follow_redirects):
            observed["timeout"] = timeout
            observed["follow_redirects"] = follow_redirects

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url, *, headers, content):
            observed.update(
                method=method,
                url=url,
                headers=headers,
                content=content,
            )
            return Response()

    class FakeHttpx:
        TimeoutException = type("TimeoutException", (Exception,), {})
        TransportError = type("TransportError", (Exception,), {})

        @staticmethod
        def Timeout(seconds):
            return seconds

    FakeHttpx.Client = Client

    monkeypatch.setitem(sys.modules, "httpx", FakeHttpx)
    request = TokenCountHttpRequest(
        "POST",
        OPENAI_TOKEN_COUNT_ENDPOINT,
        (("authorization", f"Bearer {CANARY}"),),
        plan.token_count_request_body,
    )

    response = OpenAITokenCountHttpxSender().send(request)

    assert response.status_code == 200
    assert observed["follow_redirects"] is False
    assert observed["method"] == "POST"
    assert observed["url"] == OPENAI_TOKEN_COUNT_ENDPOINT
    assert observed["url"] != "https://api.openai.com/v1/responses"
    assert observed["content"] == plan.token_count_request_body


def test_offline_cli_dry_run_never_reads_credentials_or_uses_sender(capsys):
    reads = []
    sender_calls = []

    code = run_cli(
        ["dry-run", "--repository-head", HEAD],
        repository_root=ROOT,
        environment_getter=lambda name: reads.append(name),
        sender_factory=lambda: sender_calls.append(True),
        utc_now_getter=lambda: "2026-09-01T12:00:00Z",
    )

    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["status"] == "token_count_dry_run_only"
    assert output["call_id"] == "call-0003"
    assert output["token_count_request_hash"]
    assert output["provider_calls"] == 0
    assert output["pilot_calls"] == 0
    assert output["credentials_accessed"] == 0
    assert reads == []
    assert sender_calls == []


def test_offline_cli_authorization_template_is_exact_and_credential_free(
    capsys,
    plan,
):
    reads = []
    sender_calls = []

    code = run_cli(
        [
            "authorization-template",
            "--repository-head",
            HEAD,
            "--certification",
            str(CERTIFICATION),
            "--authorized-at-utc",
            "2026-09-01T12:00:00Z",
            "--provider-hard-spend-cap-usd",
            "5.00",
            "--confirm-credential-present",
            "--confirm-single-token-count-only",
        ],
        repository_root=ROOT,
        environment_getter=lambda name: reads.append(name),
        sender_factory=lambda: sender_calls.append(True),
        utc_now_getter=lambda: "2026-09-01T12:00:00Z",
    )

    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["status"] == "approved"
    assert output["scope"] == "openai_token_count_preflight_only"
    assert output["request_hash"] == plan.original_request_hash
    assert output["token_count_request_hash"] == plan.token_count_request_hash
    assert output["maximum_invocations"] == 1
    assert output["retry_count"] == 0
    assert output["model_response_generation_authorized"] is False
    assert output["pilot_execution_authorized"] is False
    assert reads == []
    assert sender_calls == []


def test_cli_requires_explicit_network_confirmation_before_credentials(
    capsys, tmp_path, plan, certification
):
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text(
        json.dumps(_authorization(plan, certification)), encoding="utf-8"
    )
    reads = []

    code = run_cli(
        [
            "execute",
            "--repository-head",
            HEAD,
            "--certification",
            str(CERTIFICATION),
            "--authorization",
            str(authorization_path),
        ],
        repository_root=ROOT,
        environment_getter=lambda name: reads.append(name) or CANARY,
        sender_factory=lambda: RecordingSender(),
        utc_now_getter=lambda: "2026-09-01T12:01:00Z",
    )

    assert code == 2
    assert json.loads(capsys.readouterr().out) == {
        "status": "blocked",
        "reason": "explicit_network_confirmation_required",
    }
    assert reads == []


def test_cli_mock_execute_emits_evidence_without_secret_or_generation_call(
    capsys, tmp_path, plan, certification
):
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text(
        json.dumps(_authorization(plan, certification)), encoding="utf-8"
    )
    sender = RecordingSender(
        TokenCountHttpResponse(
            200,
            (b'{"object":"response.input_tokens","input_tokens":1234}',),
            {"content-type": "application/json"},
            0.25,
        )
    )
    reads = []

    code = run_cli(
        [
            "execute",
            "--repository-head",
            HEAD,
            "--certification",
            str(CERTIFICATION),
            "--authorization",
            str(authorization_path),
            "--confirm-network",
        ],
        repository_root=ROOT,
        environment_getter=lambda name: reads.append(name) or CANARY,
        sender_factory=lambda: sender,
        utc_now_getter=lambda: "2026-09-01T12:01:00Z",
    )

    output_text = capsys.readouterr().out
    output = json.loads(output_text)
    assert code == 0
    assert output["input_tokens"] == 1234
    assert output["invocation_count"] == 1
    assert output["retry_count"] == 0
    assert output["model_response_generated"] is False
    assert reads == ["OPENAI_API_KEY"]
    assert len(sender.requests) == 1
    assert sender.requests[0].url == OPENAI_TOKEN_COUNT_ENDPOINT
    assert CANARY not in output_text


def test_cli_invoked_failure_encumbers_operational_reservation(
    capsys, tmp_path, plan, certification
):
    authorization = _authorization(plan, certification)
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")
    sender = RecordingSender(
        TokenCountHttpResponse(
            403,
            ((f'{{"error":"{CANARY}"}}').encode(),),
            {"content-type": "application/json"},
            0.25,
        )
    )

    code = run_cli(
        [
            "execute",
            "--repository-head",
            HEAD,
            "--certification",
            str(CERTIFICATION),
            "--authorization",
            str(authorization_path),
            "--confirm-network",
        ],
        repository_root=ROOT,
        environment_getter=lambda name: CANARY,
        sender_factory=lambda: sender,
        utc_now_getter=lambda: "2026-09-01T12:01:00Z",
    )

    output_text = capsys.readouterr().out
    output = json.loads(output_text)
    assert code == 3
    assert output == {
        "status": "BLOCKED_PENDING_COST_RECONCILIATION",
        "reason": "permission_denied",
        "call_id": "call-0003",
        "authorization_hash": authorization["semantic_hash"],
        "billing_state": "pending_cost_reconciliation",
        "operational_reservation_usd": "5.00",
        "invocation_count": 1,
        "retry_count": 0,
        "model_response_generated": False,
    }
    assert len(sender.requests) == 1
    assert CANARY not in output_text
