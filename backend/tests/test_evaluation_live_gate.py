"""Fail-closed same-day certification and human authorization tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.evaluation_live_gate import (
    LiveBoundaryGateError,
    build_live_gate_binding,
    load_same_day_certification,
    validate_pilot_authorization,
)
from app.services.evaluation_pilot_runner import build_provider_free_pilot_runner


ROOT = Path(__file__).resolve().parents[2]
CERTIFICATION = ROOT / "docs/testing/ai-evaluation/live-provider-certification.2026-09-01.json"


@pytest.fixture(scope="module")
def runner():
    return build_provider_free_pilot_runner(
        repository_root=ROOT,
        repository_harness_commit_sha="ccf26a2710c55ff94972c2af52d95bd971aa1796",
    )


def _authorization(runner, certification, **changes):
    base = {
        "authorization_id": "external-human-pilot-authorization-1",
        "authorization_version": "v1",
        "status": "approved",
        "evaluation_id": runner.evaluation_id,
        "experiment_phase": "pilot",
        "repository_head": runner.repository_harness_commit_sha,
        "scope": "first_attempt_only",
        "authorized_call_ids": ["call-0009"],
        "budget_control_hash": runner.budget_control_hash,
        "region_binding_hash": runner.region_binding_hash,
        "same_day_certification_hash": certification.semantic_hash,
        "credential_readiness": {
            "OPENAI_API_KEY": "MISSING",
            "GEMINI_API_KEY": "MISSING",
            "GROQ_API_KEY": "PRESENT",
        },
        "provider_control_confirmation": {
            "OpenAI": "pending",
            "Google Gemini": "pending",
            "Groq": "confirmed",
        },
        "authorized_at_utc": "2026-09-01T12:00:00Z",
        "scored_execution_authorized": False,
        "production_deployment_authorized": False,
        "semantic_hash": None,
    }
    base.update(changes)
    return base


def test_same_day_certification_is_hash_bound_current_and_non_authorizing():
    certification = load_same_day_certification(CERTIFICATION, current_date="2026-09-01")

    assert certification.observation_date == "2026-09-01"
    assert certification.provider_calls_completed == 0
    assert certification.independently_authorizes_execution is False
    assert certification.pricing_unchanged is True
    assert certification.documentation_compatible_call_ids == tuple(
        f"call-{index:04d}" for index in range(1, 23)
    )


def test_certification_is_rejected_on_later_date():
    with pytest.raises(LiveBoundaryGateError, match="certification_freshness"):
        load_same_day_certification(CERTIFICATION, current_date="2026-09-02")


def test_live_binding_requires_external_human_authorization_and_ready_provider(runner):
    certification = load_same_day_certification(CERTIFICATION, current_date="2026-09-01")
    authorization = _authorization(runner, certification)
    authorization["semantic_hash"] = validate_pilot_authorization.compute_hash(authorization)

    gate = build_live_gate_binding(
        runner=runner,
        certification=certification,
        authorization_document=authorization,
        current_date="2026-09-01",
    )

    assert gate.binding_mode == "live_pilot"
    assert gate.authorization_scope == "first_attempt_only"
    assert gate.authorized_call_ids == ("call-0009",)
    assert gate.credential_references[-1].readiness_state == "externally_confirmed_for_live_pilot"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("status", "pending"),
        ("experiment_phase", "scored"),
        ("evaluation_id", "wrong"),
        ("repository_head", "0" * 40),
        ("budget_control_hash", "0" * 64),
        ("region_binding_hash", "0" * 64),
        ("same_day_certification_hash", "0" * 64),
        ("scored_execution_authorized", True),
        ("production_deployment_authorized", True),
    ),
)
def test_authorization_mutations_fail_closed(runner, field, value):
    certification = load_same_day_certification(CERTIFICATION, current_date="2026-09-01")
    authorization = _authorization(runner, certification, **{field: value})
    authorization["semantic_hash"] = validate_pilot_authorization.compute_hash(authorization)

    with pytest.raises(LiveBoundaryGateError):
        build_live_gate_binding(
            runner=runner,
            certification=certification,
            authorization_document=authorization,
            current_date="2026-09-01",
        )


def test_tampering_after_hash_is_detected(runner):
    certification = load_same_day_certification(CERTIFICATION, current_date="2026-09-01")
    authorization = _authorization(runner, certification)
    authorization["semantic_hash"] = validate_pilot_authorization.compute_hash(authorization)
    authorization["authorized_call_ids"] = ["call-0001"]

    with pytest.raises(LiveBoundaryGateError, match="authorization_hash"):
        build_live_gate_binding(
            runner=runner,
            certification=certification,
            authorization_document=authorization,
            current_date="2026-09-01",
        )


@pytest.mark.parametrize(
    "authorized_at_utc",
    ("2026-08-31T23:59:59Z", "2026-09-01T11:00:00Z"),
)
def test_authorization_must_be_same_day_and_after_certification(
    runner, authorized_at_utc
):
    certification = load_same_day_certification(CERTIFICATION, current_date="2026-09-01")
    authorization = _authorization(
        runner,
        certification,
        authorized_at_utc=authorized_at_utc,
    )
    authorization["semantic_hash"] = validate_pilot_authorization.compute_hash(
        authorization
    )

    with pytest.raises(LiveBoundaryGateError, match="authorization_contract"):
        build_live_gate_binding(
            runner=runner,
            certification=certification,
            authorization_document=authorization,
            current_date="2026-09-01",
        )


def test_documentation_certification_base_head_does_not_replace_live_head_binding():
    runner_at_final_live_head = build_provider_free_pilot_runner(
        repository_root=ROOT,
        repository_harness_commit_sha="f" * 40,
    )
    certification = load_same_day_certification(CERTIFICATION, current_date="2026-09-01")
    authorization = _authorization(runner_at_final_live_head, certification)
    authorization["semantic_hash"] = validate_pilot_authorization.compute_hash(
        authorization
    )

    gate = build_live_gate_binding(
        runner=runner_at_final_live_head,
        certification=certification,
        authorization_document=authorization,
        current_date="2026-09-01",
    )

    assert certification.repository_head_reviewed == (
        "ccf26a2710c55ff94972c2af52d95bd971aa1796"
    )
    assert gate.repository_harness_commit_sha == "f" * 40
