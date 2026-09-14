"""Offline CLI coverage for the cross-provider Capstone extension."""

from __future__ import annotations

import json

import pytest

from app.services.evaluation_capstone_cross_provider_validation_cli import run_cli
from tests.test_evaluation_capstone_cross_provider_validation import (
    GEMINI_CASE_ID,
    HEAD,
    SOL_CASE_ID,
    _Sender,
    _seed_history,
)


@pytest.mark.parametrize("case_id", (SOL_CASE_ID, GEMINI_CASE_ID))
def test_cli_dry_run_authorization_and_preflight_are_offline(
    tmp_path,
    capsys,
    case_id,
):
    operational_root = _seed_history(tmp_path / "state")
    sender = _Sender()
    factory = lambda: sender

    assert run_cli(
        [
            "dry-run",
            "--repository-head",
            HEAD,
            "--case-id",
            case_id,
        ],
        operational_root=operational_root,
        sender_factory=factory,
        require_clean_repository=False,
    ) == 0
    dry_run = json.loads(capsys.readouterr().out)
    assert dry_run["status"] == "offline_dry_run_passed"
    assert dry_run["credentials_accessed"] == 0
    assert dry_run["provider_calls"] == 0
    assert sender.requests == []

    assert run_cli(
        [
            "authorization",
            "--repository-head",
            HEAD,
            "--case-id",
            case_id,
            "--authorized-at-utc",
            "2026-09-01T23:30:00Z",
        ],
        operational_root=operational_root,
        sender_factory=factory,
        require_clean_repository=False,
    ) == 2
    assert json.loads(capsys.readouterr().out) == {
        "reason": "explicit_user_authorization_confirmation_required",
        "status": "blocked",
    }

    assert run_cli(
        [
            "authorization",
            "--repository-head",
            HEAD,
            "--case-id",
            case_id,
            "--authorized-at-utc",
            "2026-09-01T23:30:00Z",
            "--confirm-explicit-user-authorization",
        ],
        operational_root=operational_root,
        sender_factory=factory,
        require_clean_repository=False,
    ) == 0
    authorization = json.loads(capsys.readouterr().out)
    authorization_path = tmp_path / f"{case_id}.authorization.json"
    authorization_path.write_text(json.dumps(authorization), encoding="utf-8")

    assert run_cli(
        [
            "preflight",
            "--repository-head",
            HEAD,
            "--case-id",
            case_id,
            "--authorization",
            str(authorization_path),
        ],
        operational_root=operational_root,
        sender_factory=factory,
        require_clean_repository=False,
    ) == 0
    preflight = json.loads(capsys.readouterr().out)
    assert preflight["status"] == "ready_for_one_explicitly_confirmed_live_call"
    assert preflight["maximum_provider_calls"] == 1
    assert preflight["retry_count"] == 0
    assert preflight["credentials_accessed"] == 0
    assert preflight["provider_calls"] == 0
    assert sender.requests == []


def test_cli_live_command_requires_confirmation_before_credentials_or_sender(
    tmp_path,
    capsys,
):
    operational_root = _seed_history(tmp_path / "state")
    sender = _Sender()
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text("{}", encoding="utf-8")
    reads = []

    assert run_cli(
        [
            "execute",
            "--repository-head",
            HEAD,
            "--case-id",
            SOL_CASE_ID,
            "--authorization",
            str(authorization_path),
        ],
        operational_root=operational_root,
        environment_getter=lambda name: reads.append(name) or "not-used",
        sender_factory=lambda: sender,
        require_clean_repository=False,
    ) == 2
    assert json.loads(capsys.readouterr().out) == {
        "reason": "explicit_live_confirmation_required",
        "status": "blocked",
    }
    assert reads == []
    assert sender.requests == []
