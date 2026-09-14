"""Operator-entrypoint safety tests; every test is socket-free."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.evaluation_live_gate import (
    load_same_day_certification,
    validate_pilot_authorization,
)
from app.services.evaluation_live_transport import HttpResponse
from app.services.evaluation_pilot_cli import run_cli
from app.services.evaluation_pilot_runner import (
    _synthetic_provider_envelope,
    build_provider_free_pilot_runner,
)


ROOT = Path(__file__).resolve().parents[2]
CERTIFICATION = ROOT / "docs/testing/ai-evaluation/live-provider-certification.2026-09-01.json"
HEAD = "ccf26a2710c55ff94972c2af52d95bd971aa1796"
CANARY = "synthetic-cli-canary-f03441e8be5a4ba895854cf7b7b12ed0"


def _cost_complete_envelope(runner, call):
    if call.workload_stage == "search_synthesis":
        evidence, tool_data = runner._synthetic_ps1_material(call)
        native = runner._build_native_request(
            call,
            ps1_evidence=evidence,
            search_tool_data=tool_data,
        )
    else:
        native = runner.build_native_request(call)
    value = json.loads(_synthetic_provider_envelope(native).decode("utf-8"))
    if call.provider == "OpenAI":
        value["usage"]["input_tokens_details"] = {
            "cached_tokens": 0,
            "cache_write_tokens": 0,
        }
    elif call.provider == "Google Gemini":
        value["usage"]["total_cached_tokens"] = 0
    elif call.model == "openai/gpt-oss-120b":
        value["usage"]["prompt_tokens_details"] = {"cached_tokens": 0}
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _live_files(tmp_path, *, full=False):
    runner = build_provider_free_pilot_runner(
        repository_root=ROOT,
        repository_harness_commit_sha=HEAD,
    )
    certification = load_same_day_certification(
        CERTIFICATION,
        current_date="2026-09-01",
    )
    authorization = {
        "authorization_id": "external-human-pilot-authorization-1",
        "authorization_version": "v1",
        "status": "approved",
        "evaluation_id": runner.evaluation_id,
        "experiment_phase": "pilot",
        "repository_head": HEAD,
        "scope": "full_authorized_pilot" if full else "first_attempt_only",
        "authorized_call_ids": (
            [call.call_id for call in runner.plan.provider_calls]
            if full
            else ["call-0009"]
        ),
        "budget_control_hash": runner.budget_control_hash,
        "region_binding_hash": runner.region_binding_hash,
        "same_day_certification_hash": certification.semantic_hash,
        "credential_readiness": {
            "OPENAI_API_KEY": "PRESENT" if full else "MISSING",
            "GEMINI_API_KEY": "PRESENT" if full else "MISSING",
            "GROQ_API_KEY": "PRESENT",
        },
        "provider_control_confirmation": {
            "OpenAI": "confirmed" if full else "pending",
            "Google Gemini": "confirmed" if full else "pending",
            "Groq": "confirmed",
        },
        "authorized_at_utc": "2026-09-01T12:00:00Z",
        "scored_execution_authorized": False,
        "production_deployment_authorized": False,
        "semantic_hash": None,
    }
    authorization["semantic_hash"] = validate_pilot_authorization.compute_hash(
        authorization
    )
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")
    reservations_path = tmp_path / "reservations.json"
    reservations = {
        call_id: ("0.25" if full else "0.01")
        for call_id in authorization["authorized_call_ids"]
    }
    reservations_path.write_text(json.dumps(reservations), encoding="utf-8")
    calls = (
        runner.plan.provider_calls
        if full
        else (next(item for item in runner.plan.provider_calls if item.call_id == "call-0009"),)
    )
    responses = [_cost_complete_envelope(runner, call) for call in calls]
    return authorization_path, reservations_path, responses


class _Sender:
    def __init__(self, responses=None, failure=None, status_code=200):
        self.responses = list(responses or ())
        self.failure = failure
        self.status_code = status_code
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return HttpResponse(
            self.status_code,
            (self.responses.pop(0),),
            {"content-type": "application/json"},
            0.25,
        )


def test_no_arguments_is_blocked_and_does_not_read_credentials(capsys):
    reads = []

    code = run_cli([], environment_getter=lambda name: reads.append(name))

    assert code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "PILOT_LIVE_BOUNDARY_READY_AWAITING_USER"
    assert output["execution"] == "blocked"
    assert output["provider_calls"] == 0
    assert reads == []


def test_presence_check_prints_only_present_or_missing(capsys):
    values = {"OPENAI_API_KEY": "secret", "GEMINI_API_KEY": None, "GROQ_API_KEY": "secret"}

    code = run_cli(["credential-presence"], environment_getter=values.get)

    assert code == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "OPENAI_API_KEY=PRESENT",
        "GEMINI_API_KEY=MISSING",
        "GROQ_API_KEY=PRESENT",
    ]
    assert "secret" not in "\n".join(lines)


def test_live_mode_requires_independent_explicit_bindings(capsys):
    code = run_cli(
        [
            "execute",
            "--mode",
            "first-attempt-only",
            "--call-id",
            "call-0009",
            "--confirm-live",
        ]
    )

    assert code == 2
    output = json.loads(capsys.readouterr().out)
    assert output == {"status": "blocked", "reason": "live_bindings_required"}


def test_full_mode_requires_full_authorization_scope(capsys):
    code = run_cli(["execute", "--mode", "full-authorized-pilot"])

    assert code == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "blocked"
    assert output["reason"] == "explicit_live_confirmation_required"


def test_dry_run_builds_one_exact_request_without_credentials_or_network(capsys):
    reads = []

    code = run_cli(
        ["dry-run", "--call-id", "call-0009"],
        environment_getter=lambda name: reads.append(name),
        repository_root=ROOT,
    )

    assert code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "dry_run_only"
    assert output["call"]["fixture_id"] == "PT1"
    assert output["call"]["candidate_id"] == "baseline_current_text_v1"
    assert output["provider_calls"] == 0
    assert output["credentials_accessed"] == 0
    assert reads == []


def test_same_day_preflight_is_offline_and_rejects_later_date(capsys):
    reads = []

    green = run_cli(
        [
            "preflight",
            "--certification",
            str(CERTIFICATION),
            "--repository-head",
            HEAD,
        ],
        environment_getter=lambda name: reads.append(name),
        repository_root=ROOT,
        utc_date_getter=lambda: "2026-09-01",
    )
    green_output = json.loads(capsys.readouterr().out)
    stale = run_cli(
        [
            "preflight",
            "--certification",
            str(CERTIFICATION),
            "--repository-head",
            HEAD,
        ],
        environment_getter=lambda name: reads.append(name),
        repository_root=ROOT,
        utc_date_getter=lambda: "2026-09-02",
    )
    stale_output = json.loads(capsys.readouterr().out)

    assert green == 0
    assert green_output["status"] == "ready_awaiting_private_user_gates"
    assert green_output["nominal_provider_calls"] == 22
    assert green_output["maximum_physical_attempts"] == 44
    assert stale == 2
    assert stale_output == {"status": "blocked", "reason": "certification_freshness"}
    assert reads == []


def test_first_attempt_mode_executes_only_exact_authorized_mock_boundary(
    tmp_path, capsys
):
    authorization, reservations, responses = _live_files(tmp_path)
    sender = _Sender(responses=responses)
    reads = []

    code = run_cli(
        [
            "execute",
            "--mode",
            "first-attempt-only",
            "--call-id",
            "call-0009",
            "--confirm-live",
            "--certification",
            str(CERTIFICATION),
            "--authorization",
            str(authorization),
            "--reservations",
            str(reservations),
            "--repository-head",
            HEAD,
        ],
        environment_getter=lambda name: reads.append(name) or CANARY,
        repository_root=ROOT,
        sender_factory=lambda: sender,
        utc_date_getter=lambda: "2026-09-01",
    )

    assert code == 0
    output_text = capsys.readouterr().out
    output = json.loads(output_text)
    assert output == {
        "accepted": True,
        "call_id": "call-0009",
        "committed_cost_usd": "0.0000081",
        "physical_http_invocations": 1,
        "remaining_budget_usd": "4.9999919",
        "safe_failure_code": None,
        "status": "first_attempt_completed",
    }
    assert reads == ["GROQ_API_KEY"]
    assert len(sender.requests) == 1
    assert CANARY not in output_text


def test_arbitrary_sender_exception_after_invocation_becomes_safe_pending_cost(
    tmp_path, capsys
):
    authorization, reservations, _ = _live_files(tmp_path)
    sender = _Sender(failure=ValueError(CANARY))

    code = run_cli(
        [
            "execute",
            "--mode",
            "first-attempt-only",
            "--call-id",
            "call-0009",
            "--confirm-live",
            "--certification",
            str(CERTIFICATION),
            "--authorization",
            str(authorization),
            "--reservations",
            str(reservations),
            "--repository-head",
            HEAD,
        ],
        environment_getter=lambda name: CANARY,
        repository_root=ROOT,
        sender_factory=lambda: sender,
        utc_date_getter=lambda: "2026-09-01",
    )

    assert code == 3
    output_text = capsys.readouterr().out
    output = json.loads(output_text)
    assert output["status"] == "BLOCKED_PENDING_COST_RECONCILIATION"
    assert output["billing_state"] == "pending_cost_reconciliation"
    assert output["pending_attempt_ids"] == ["pa-0009-1"]
    assert output["physical_http_invocations"] == 1
    assert CANARY not in output_text


def test_full_mode_requires_and_consumes_full_authorized_scope_only(
    tmp_path, capsys
):
    authorization, reservations, responses = _live_files(tmp_path, full=True)
    sender = _Sender(responses=responses)
    reads = []

    code = run_cli(
        [
            "execute",
            "--mode",
            "full-authorized-pilot",
            "--confirm-live",
            "--certification",
            str(CERTIFICATION),
            "--authorization",
            str(authorization),
            "--reservations",
            str(reservations),
            "--repository-head",
            HEAD,
        ],
        environment_getter=lambda name: reads.append(name) or CANARY,
        repository_root=ROOT,
        sender_factory=lambda: sender,
        utc_date_getter=lambda: "2026-09-01",
    )

    assert code == 0
    output_text = capsys.readouterr().out
    output = json.loads(output_text)
    assert output["status"] == "authorized_pilot_completed"
    assert output["completed_logical_runs"] == 21
    assert output["physical_http_invocations"] == 22
    assert len(reads) == 22
    assert set(reads) == {"OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY"}
    assert sender.responses == []
    assert CANARY not in output_text


def test_first_attempt_unknown_live_cost_reports_safe_global_blocker(
    tmp_path, capsys
):
    authorization, reservations, _ = _live_files(tmp_path)
    diagnostic = b'{"error":"restricted provider diagnostic prose"}'
    sender = _Sender(responses=[diagnostic], status_code=503)

    code = run_cli(
        [
            "execute",
            "--mode",
            "first-attempt-only",
            "--call-id",
            "call-0009",
            "--confirm-live",
            "--certification",
            str(CERTIFICATION),
            "--authorization",
            str(authorization),
            "--reservations",
            str(reservations),
            "--repository-head",
            HEAD,
        ],
        environment_getter=lambda name: CANARY,
        repository_root=ROOT,
        sender_factory=lambda: sender,
        utc_date_getter=lambda: "2026-09-01",
    )

    assert code == 3
    output_text = capsys.readouterr().out
    assert json.loads(output_text) == {
        "accepted": False,
        "billing_state": "pending_cost_reconciliation",
        "call_id": "call-0009",
        "committed_cost_usd": "0.00",
        "pending_attempt_ids": ["pa-0009-1"],
        "pending_encumbered_cost_usd": "0.01",
        "physical_http_invocations": 1,
        "remaining_budget_usd": "4.99",
        "safe_failure_code": "http_provider_error",
        "status": "BLOCKED_PENDING_COST_RECONCILIATION",
    }
    assert "restricted provider diagnostic prose" not in output_text
    assert CANARY not in output_text


def test_first_attempt_semantic_success_with_unknown_cost_exits_blocked(
    tmp_path, capsys
):
    authorization, reservations, _ = _live_files(tmp_path)
    runner = build_provider_free_pilot_runner(
        repository_root=ROOT,
        repository_harness_commit_sha=HEAD,
    )
    call = next(
        item for item in runner.plan.provider_calls if item.call_id == "call-0009"
    )
    response_without_complete_usage = _synthetic_provider_envelope(
        runner.build_native_request(call)
    )
    sender = _Sender(responses=[response_without_complete_usage])

    code = run_cli(
        [
            "execute",
            "--mode",
            "first-attempt-only",
            "--call-id",
            "call-0009",
            "--confirm-live",
            "--certification",
            str(CERTIFICATION),
            "--authorization",
            str(authorization),
            "--reservations",
            str(reservations),
            "--repository-head",
            HEAD,
        ],
        environment_getter=lambda name: CANARY,
        repository_root=ROOT,
        sender_factory=lambda: sender,
        utc_date_getter=lambda: "2026-09-01",
    )

    output = json.loads(capsys.readouterr().out)
    assert code == 3
    assert output["status"] == "BLOCKED_PENDING_COST_RECONCILIATION"
    assert output["accepted"] is True
    assert output["billing_state"] == "pending_cost_reconciliation"
    assert output["physical_http_invocations"] == 1


def test_full_mode_stops_before_second_invocation_when_first_cost_is_pending(
    tmp_path, capsys
):
    authorization, reservations, _ = _live_files(tmp_path, full=True)
    sender = _Sender(responses=[b'{"error":"unavailable"}'], status_code=503)

    code = run_cli(
        [
            "execute",
            "--mode",
            "full-authorized-pilot",
            "--confirm-live",
            "--certification",
            str(CERTIFICATION),
            "--authorization",
            str(authorization),
            "--reservations",
            str(reservations),
            "--repository-head",
            HEAD,
        ],
        environment_getter=lambda name: CANARY,
        repository_root=ROOT,
        sender_factory=lambda: sender,
        utc_date_getter=lambda: "2026-09-01",
    )

    assert code == 3
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "BLOCKED_PENDING_COST_RECONCILIATION"
    assert output["completed_logical_runs"] == 0
    assert output["physical_http_invocations"] == 1
    assert output["pending_attempt_ids"] == ["pa-0001-1"]
    assert output["pending_encumbered_cost_usd"] == "0.25"
    assert len(sender.requests) == 1
