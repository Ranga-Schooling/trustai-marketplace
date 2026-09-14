"""Provider-free tests for the frozen pilot retry policy."""

from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest

from app.services.evaluation_attempt_state import TERMINAL_OUTCOMES
from app.services.evaluation_retry_policy import (
    MAXIMUM_PHYSICAL_ATTEMPTS,
    PER_ATTEMPT_TIMEOUT_SECONDS,
    RETRY_REASONS_BY_OUTCOME,
    SAFE_RETRY_REASONS,
    AttemptDeadline,
    RetryPolicyError,
    decide_retry,
    load_retry_policy,
)


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    ROOT / "docs" / "testing" / "ai-evaluation" / "retry-policy.v1.json"
)
MODULE_PATH = (
    ROOT / "backend" / "app" / "services" / "evaluation_retry_policy.py"
)


def test_policy_freezes_the_approved_attempt_and_timeout_limits():
    policy = load_retry_policy(POLICY_PATH)

    assert policy.artifact_id == "retry_policy_v1"
    assert policy.artifact_version == "v1"
    assert policy.status == "frozen"
    assert policy.maximum_physical_attempts == MAXIMUM_PHYSICAL_ATTEMPTS == 2
    assert policy.per_attempt_timeout_seconds == PER_ATTEMPT_TIMEOUT_SECONDS == 120
    assert policy.maximum_retries == 1
    assert policy.provider_calls_allowed is False
    assert policy.provider_calls_completed == 0


def test_retry_reason_vocabulary_is_closed_safe_and_application_owned():
    policy = load_retry_policy(POLICY_PATH)

    assert SAFE_RETRY_REASONS == (
        "transient_provider_connection_error",
        "provider_attempt_timeout",
        "provider_rate_limited",
        "provider_service_unavailable",
    )
    assert RETRY_REASONS_BY_OUTCOME == {
        "provider_connection_error": ("transient_provider_connection_error",),
        "provider_timeout": ("provider_attempt_timeout",),
        "http_provider_error": (
            "provider_rate_limited",
            "provider_service_unavailable",
        ),
    }
    assert policy.safe_retry_reasons == SAFE_RETRY_REASONS
    assert policy.retry_reasons_by_outcome == tuple(RETRY_REASONS_BY_OUTCOME.items())


@pytest.mark.parametrize("outcome", TERMINAL_OUTCOMES)
def test_attempt_outcome_alone_never_authorizes_retry(outcome):
    decision = decide_retry(attempt_number=1, attempt_outcome=outcome)

    assert decision.retry_allowed is False
    assert decision.retry_reason is None
    assert decision.next_attempt_number is None
    assert decision.run_terminal is True


@pytest.mark.parametrize(
    ("outcome", "reason"),
    tuple(
        (outcome, reason)
        for outcome, reasons in RETRY_REASONS_BY_OUTCOME.items()
        for reason in reasons
    ),
)
def test_first_attempt_retries_only_with_an_exact_safe_transient_classification(
    outcome,
    reason,
):
    decision = decide_retry(
        attempt_number=1,
        attempt_outcome=outcome,
        transient_retry_reason=reason,
    )

    assert decision.retry_allowed is True
    assert decision.retry_reason == reason
    assert decision.next_attempt_number == 2
    assert decision.run_terminal is False


@pytest.mark.parametrize("outcome", TERMINAL_OUTCOMES)
def test_second_attempt_always_exhausts_the_run_budget(outcome):
    decision = decide_retry(attempt_number=2, attempt_outcome=outcome)

    assert decision.retry_allowed is False
    assert decision.retry_reason is None
    assert decision.next_attempt_number is None
    assert decision.run_terminal is True
    assert decision.budget_exhausted is True


@pytest.mark.parametrize(
    "outcome",
    (
        "http_provider_error",
        "provider_safety_block",
        "provider_native_refusal",
        "tool_error",
        "tool_timeout",
        "failed_transport_extraction",
        "failed_resource_limit",
        "failed_utf8_decode",
        "failed_duplicate_key",
        "failed_strict_parse",
        "failed_canonical_validation",
        "failed_cross_field_validation",
        "failed_evidence_trace_coherence",
        "failed_trace_validation",
        "failed_url_security_validation",
        "failed_retrieval_coherence",
        "failed_evidence_policy",
        "internal_harness_error",
    ),
)
def test_semantic_security_contract_configuration_and_ambiguous_failures_never_retry(
    outcome,
):
    assert decide_retry(
        attempt_number=1,
        attempt_outcome=outcome,
    ).retry_allowed is False


@pytest.mark.parametrize(
    ("outcome", "reason"),
    (
        ("provider_connection_error", "provider_attempt_timeout"),
        ("provider_timeout", "transient_provider_connection_error"),
        ("http_provider_error", "provider_attempt_timeout"),
        ("tool_timeout", "provider_service_unavailable"),
        ("failed_strict_parse", "provider_rate_limited"),
    ),
)
def test_safe_reason_must_be_compatible_with_the_exact_attempt_outcome(outcome, reason):
    with pytest.raises(RetryPolicyError, match="transient_retry_reason"):
        decide_retry(
            attempt_number=1,
            attempt_outcome=outcome,
            transient_retry_reason=reason,
        )


@pytest.mark.parametrize(
    ("attempt_number", "outcome", "error"),
    (
        (0, "provider_timeout", "attempt_number"),
        (3, "provider_timeout", "attempt_number"),
        (True, "provider_timeout", "attempt_number"),
        (1, "unknown", "attempt_outcome"),
        (1, None, "attempt_outcome"),
    ),
)
def test_unknown_or_out_of_budget_inputs_fail_closed(attempt_number, outcome, error):
    with pytest.raises(RetryPolicyError, match=error):
        decide_retry(attempt_number=attempt_number, attempt_outcome=outcome)


def test_timeout_boundary_is_exact_and_uses_monotonic_elapsed_time():
    deadline = AttemptDeadline(started_monotonic=10.0)

    assert deadline.timeout_seconds == 120
    assert deadline.remaining_seconds(129.999) == pytest.approx(0.001)
    assert deadline.expired(129.999) is False
    assert deadline.remaining_seconds(130.0) == 0.0
    assert deadline.expired(130.0) is True
    assert deadline.remaining_seconds(999.0) == 0.0
    assert deadline.expired(999.0) is True


@pytest.mark.parametrize("value", (-1.0, math.inf, -math.inf, math.nan, True, "1"))
def test_timeout_clock_inputs_fail_closed(value):
    with pytest.raises(RetryPolicyError, match="monotonic"):
        AttemptDeadline(started_monotonic=value)

    deadline = AttemptDeadline(started_monotonic=1.0)
    with pytest.raises(RetryPolicyError, match="monotonic"):
        deadline.remaining_seconds(value)


def test_timeout_clock_cannot_move_backwards():
    deadline = AttemptDeadline(started_monotonic=10.0)
    with pytest.raises(RetryPolicyError, match="monotonic_order"):
        deadline.remaining_seconds(9.999)


def test_contract_rejects_any_mutation_to_the_frozen_policy(tmp_path):
    raw = POLICY_PATH.read_text(encoding="utf-8")
    mutated = raw.replace(
        '"maximum_physical_attempts_per_run": 2',
        '"maximum_physical_attempts_per_run": 3',
        1,
    )
    path = tmp_path / "retry-policy.v1.json"
    path.write_text(mutated, encoding="utf-8")

    with pytest.raises(RetryPolicyError):
        load_retry_policy(path)


def test_policy_loader_detaches_immutable_state_from_source(tmp_path):
    policy = load_retry_policy(POLICY_PATH)
    original = copy.deepcopy(policy)
    path = tmp_path / "retry-policy.v1.json"
    path.write_bytes(POLICY_PATH.read_bytes())

    assert load_retry_policy(path) == original
    assert isinstance(policy.safe_retry_reasons, tuple)
    assert isinstance(policy.retry_reasons_by_outcome, tuple)


def test_runtime_module_has_no_provider_network_persistence_or_sleep_authority():
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert "httpx" not in source
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source
    assert "sleep(" not in source
    assert "api_key" not in source.lower()
    assert "database" not in source.lower()
