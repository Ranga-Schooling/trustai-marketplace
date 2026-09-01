"""CLI safety tests for the separate Capstone live-validation entrypoint."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from app.services.evaluation_capstone_live_validation import (
    build_capstone_live_validation,
)
from app.services.evaluation_capstone_live_validation_cli import run_cli
from app.services.evaluation_live_transport import HttpResponse
from app.services.evaluation_pilot_runner import _synthetic_provider_envelope
from tests.test_evaluation_capstone_live_validation import (
    RUNTIME_IDENTITY,
    _seed_v1_state,
)


ROOT = Path(__file__).resolve().parents[2]
HEAD = subprocess.run(
    ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
CASE_ID = "capval-openai-terra-pt1-v2"
CANARY = "capstone-cli-canary-bd44a29c"


class _Sender:
    def __init__(self, response_bytes):
        self.response_bytes = response_bytes
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        return HttpResponse(
            200,
            (self.response_bytes,),
            {"content-type": "application/json"},
            0.25,
        )

    def validate_runtime(self):
        return dict(RUNTIME_IDENTITY)


def _response_bytes():
    validator = build_capstone_live_validation(
        repository_root=ROOT,
        repository_head=HEAD,
        require_clean_repository=False,
    )
    request = validator.build_request(CASE_ID)
    value = json.loads(_synthetic_provider_envelope(request))
    value["usage"]["input_tokens"] = 1018
    value["usage"]["input_tokens_details"] = {
        "cached_tokens": 0,
        "cache_write_tokens": 0,
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def test_status_and_dry_run_are_offline_and_do_not_read_credentials(
    capsys,
    tmp_path,
):
    reads = []
    state_root = _seed_v1_state(tmp_path / "state")
    sender = _Sender(b"{}")

    assert run_cli(
        [],
        repository_root=ROOT,
        environment_getter=lambda name: reads.append(name),
        require_clean_repository=False,
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "CAPSTONE_LIVE_VALIDATION_V2_READY_AWAITING_USER"

    assert run_cli(
        ["dry-run", "--repository-head", HEAD, "--case-id", CASE_ID],
        repository_root=ROOT,
        operational_root=state_root,
        environment_getter=lambda name: reads.append(name),
        sender_factory=lambda: sender,
        require_clean_repository=False,
    ) == 0
    dry_run = json.loads(capsys.readouterr().out)
    assert dry_run["status"] == "offline_dry_run_passed"
    assert dry_run["provider_calls"] == 0
    assert dry_run["credentials_accessed"] == 0
    assert dry_run["cumulative_worst_case_validation_exposure_usd"] == (
        "0.10339400"
    )
    assert reads == []


def test_live_command_is_blocked_without_unmistakable_confirmation(capsys, tmp_path):
    reads = []

    assert run_cli(
        [
            "execute",
            "--repository-head",
            HEAD,
            "--case-id",
            CASE_ID,
            "--authorization",
            str(tmp_path / "missing.json"),
        ],
        repository_root=ROOT,
        operational_root=tmp_path,
        environment_getter=lambda name: reads.append(name),
        require_clean_repository=False,
    ) == 2

    output = json.loads(capsys.readouterr().out)
    assert output == {
        "reason": "explicit_live_confirmation_required",
        "status": "blocked",
    }
    assert reads == []
    assert tuple(tmp_path.iterdir()) == ()


def test_missing_http_client_blocks_preflight_and_execute_before_state_or_credentials(
    capsys,
    monkeypatch,
    tmp_path,
):
    validator = build_capstone_live_validation(
        repository_root=ROOT,
        repository_head=HEAD,
        require_clean_repository=False,
    )
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text(
        json.dumps(
            validator.build_authorization_document(
                case_id=CASE_ID,
                runtime_identity=RUNTIME_IDENTITY,
                authorized_at_utc="2026-09-01T21:00:00Z",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(sys.modules, "httpx", None)
    reads = []
    state_root = tmp_path / "state"
    _seed_v1_state(state_root)

    for arguments in (
        ["dry-run", "--repository-head", HEAD, "--case-id", CASE_ID],
        [
            "authorization",
            "--repository-head",
            HEAD,
            "--case-id",
            CASE_ID,
            "--authorized-at-utc",
            "2026-09-01T21:00:00Z",
            "--confirm-explicit-user-authorization",
        ],
    ):
        assert run_cli(
            arguments,
            repository_root=ROOT,
            operational_root=state_root,
            environment_getter=lambda name: reads.append(name) or CANARY,
            require_clean_repository=False,
        ) == 2
        assert json.loads(capsys.readouterr().out) == {
            "reason": "http_client_unavailable",
            "status": "blocked",
        }

    assert run_cli(
        [
            "preflight",
            "--repository-head",
            HEAD,
            "--authorization",
            str(authorization_path),
        ],
        repository_root=ROOT,
        operational_root=state_root,
        require_clean_repository=False,
    ) == 2
    assert json.loads(capsys.readouterr().out) == {
        "reason": "http_client_unavailable",
        "status": "blocked",
    }

    assert run_cli(
        [
            "execute",
            "--repository-head",
            HEAD,
            "--case-id",
            CASE_ID,
            "--authorization",
            str(authorization_path),
            "--confirm-live",
        ],
        repository_root=ROOT,
        operational_root=state_root,
        environment_getter=lambda name: reads.append(name) or CANARY,
        require_clean_repository=False,
    ) == 2
    assert json.loads(capsys.readouterr().out) == {
        "reason": "http_client_unavailable",
        "status": "blocked",
    }
    assert reads == []
    assert not (state_root / "capstone-live-validation-v2").exists()


def test_authorization_preflight_execute_and_inspect_are_one_call_only(capsys, tmp_path):
    authorization_path = tmp_path / "authorization.json"
    state_root = tmp_path / "state"
    sender = _Sender(_response_bytes())
    reads = []
    _seed_v1_state(state_root)

    assert run_cli(
        [
            "authorization",
            "--repository-head",
            HEAD,
            "--case-id",
            CASE_ID,
            "--authorized-at-utc",
            "2026-09-01T21:00:00Z",
            "--confirm-explicit-user-authorization",
        ],
        repository_root=ROOT,
        operational_root=state_root,
        sender_factory=lambda: sender,
        require_clean_repository=False,
    ) == 0
    authorization = json.loads(capsys.readouterr().out)
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")

    assert run_cli(
        [
            "preflight",
            "--repository-head",
            HEAD,
            "--authorization",
            str(authorization_path),
        ],
        repository_root=ROOT,
        operational_root=state_root,
        sender_factory=lambda: sender,
        require_clean_repository=False,
    ) == 0
    preflight = json.loads(capsys.readouterr().out)
    assert preflight["status"] == "ready_for_one_explicitly_confirmed_live_call"
    assert preflight["credentials_accessed"] == 0
    assert preflight["provider_calls"] == 0
    assert preflight["transport_projection"] == {
        "method": "POST",
        "url": "https://api.openai.com/v1/responses",
        "timeout_seconds": 120,
        "redirects_allowed": False,
        "automatic_retry_count": 0,
    }
    assert preflight["cumulative_worst_case_validation_exposure_usd"] == (
        "0.10339400"
    )
    assert preflight["validation_spend_remaining_after_reservation_usd"] == (
        "0.89660600"
    )

    assert run_cli(
        [
            "execute",
            "--repository-head",
            HEAD,
            "--case-id",
            CASE_ID,
            "--authorization",
            str(authorization_path),
            "--confirm-live",
        ],
        repository_root=ROOT,
        operational_root=state_root,
        environment_getter=lambda name: reads.append(name) or CANARY,
        sender_factory=lambda: sender,
        require_clean_repository=False,
    ) == 0
    execution = json.loads(capsys.readouterr().out)
    assert execution["status"] == "one_provider_call_completed_then_stopped"
    assert execution["physical_provider_attempts"] == 1
    assert sender.requests and len(sender.requests) == 1
    assert reads == ["OPENAI_API_KEY"]
    assert CANARY not in json.dumps(execution)

    assert run_cli(
        ["inspect", "--repository-head", HEAD],
        repository_root=ROOT,
        operational_root=state_root,
        require_clean_repository=False,
    ) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["result_status"] == "accepted"
    assert inspection["provider"] == "OpenAI"
    assert CANARY not in json.dumps(inspection)

    assert run_cli(
        [
            "preflight",
            "--repository-head",
            HEAD,
            "--authorization",
            str(authorization_path),
        ],
        repository_root=ROOT,
        operational_root=state_root,
        sender_factory=lambda: sender,
        require_clean_repository=False,
    ) == 2
    assert json.loads(capsys.readouterr().out) == {
        "reason": "case_already_reserved",
        "status": "blocked",
    }
