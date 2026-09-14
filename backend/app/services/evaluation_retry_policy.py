"""Frozen provider-neutral pilot retry decisions and deadline arithmetic.

This module classifies already-normalized attempt outcomes.  It performs no
provider call, sleep, persistence, configuration inference, or retry itself.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any

from app.services.evaluation_attempt_state import TERMINAL_OUTCOMES
from app.services.evaluation_contract_identity import (
    ContractIdentityError,
    load_strict_contract_json,
)


_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_POLICY_PATH = (
    _ROOT / "docs" / "testing" / "ai-evaluation" / "retry-policy.v1.json"
)
_EXPECTED_SEMANTIC_HASH = (
    "a4e08ef3b92232cbbf1542aa37b30c87697da60c42bcf72d71876098d0251c4b"
)
_TOP_LEVEL_KEYS = {
    "artifact_id",
    "artifact_version",
    "status",
    "purpose",
    "provider_neutral",
    "governance_decision",
    "retry_series_identity",
    "attempt_budget",
    "per_attempt_timeout",
    "retryable_failures",
    "nonretryable_attempt_outcomes_in_order",
    "decision_model",
    "result_record_binding",
    "execution_boundary",
    "specification_identity",
}
_SERIES_IDENTITY_FIELDS = (
    "evaluation_id",
    "fixture_id",
    "candidate_id",
    "provider",
    "model",
    "component_topology",
    "workload",
    "run_number",
)

MAXIMUM_PHYSICAL_ATTEMPTS = 2
PER_ATTEMPT_TIMEOUT_SECONDS = 120
SAFE_RETRY_REASONS = (
    "transient_provider_connection_error",
    "provider_attempt_timeout",
    "provider_rate_limited",
    "provider_service_unavailable",
)
RETRY_REASONS_BY_OUTCOME = MappingProxyType(
    {
        "provider_connection_error": ("transient_provider_connection_error",),
        "provider_timeout": ("provider_attempt_timeout",),
        "http_provider_error": (
            "provider_rate_limited",
            "provider_service_unavailable",
        ),
    }
)
NONRETRYABLE_ATTEMPT_OUTCOMES = tuple(
    outcome
    for outcome in TERMINAL_OUTCOMES
    if outcome not in {"accepted", *RETRY_REASONS_BY_OUTCOME}
)


class RetryPolicyError(ValueError):
    """The retry contract or a requested decision is not valid."""


def _fail(code: str) -> RetryPolicyError:
    return RetryPolicyError(code)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    artifact_id: str
    artifact_version: str
    status: str
    semantic_hash: str
    maximum_physical_attempts: int
    maximum_retries: int
    per_attempt_timeout_seconds: int
    retry_series_identity_fields: tuple[str, ...]
    safe_retry_reasons: tuple[str, ...]
    retry_reasons_by_outcome: tuple[tuple[str, tuple[str, ...]], ...]
    nonretryable_attempt_outcomes: tuple[str, ...]
    provider_calls_allowed: bool
    pilot_calls_allowed: bool
    scored_calls_allowed: bool
    provider_calls_completed: int


@dataclass(frozen=True, slots=True)
class RetryDecision:
    attempt_number: int
    attempt_outcome: str
    retry_allowed: bool
    retry_reason: str | None
    next_attempt_number: int | None
    run_terminal: bool
    budget_exhausted: bool


@dataclass(frozen=True, slots=True)
class AttemptDeadline:
    """Pure monotonic deadline math; callers own clock reads and cancellation."""

    started_monotonic: float
    timeout_seconds: int = PER_ATTEMPT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        _require_monotonic("started_monotonic", self.started_monotonic)
        if self.timeout_seconds != PER_ATTEMPT_TIMEOUT_SECONDS:
            raise _fail("timeout_seconds")

    def remaining_seconds(self, current_monotonic: float) -> float:
        current = _require_monotonic("current_monotonic", current_monotonic)
        started = float(self.started_monotonic)
        if current < started:
            raise _fail("monotonic_order")
        return max(0.0, float(self.timeout_seconds) - (current - started))

    def expired(self, current_monotonic: float) -> bool:
        return self.remaining_seconds(current_monotonic) == 0.0


def _require_monotonic(name: str, value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise _fail(f"monotonic:{name}")
    return float(value)


def _semantic_hash(raw: dict[str, Any]) -> str:
    detached = copy.deepcopy(raw)
    detached["specification_identity"]["semantic_hash"] = None
    canonical = json.dumps(
        detached,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _require_exact(name: str, actual: Any, expected: Any) -> None:
    if actual != expected or type(actual) is not type(expected):
        raise _fail(name)


def load_retry_policy(path: str | Path = _DEFAULT_POLICY_PATH) -> RetryPolicy:
    """Load and verify the complete frozen retry contract."""

    try:
        raw = load_strict_contract_json(path)
    except ContractIdentityError as exc:
        raise _fail("retry_policy_json") from exc
    if set(raw) != _TOP_LEVEL_KEYS:
        raise _fail("retry_policy_inventory")

    _require_exact("artifact_id", raw["artifact_id"], "retry_policy_v1")
    _require_exact("artifact_version", raw["artifact_version"], "v1")
    _require_exact("status", raw["status"], "frozen")
    _require_exact("provider_neutral", raw["provider_neutral"], True)

    governance = raw["governance_decision"]
    _require_exact(
        "governance_maximum_attempts",
        governance["maximum_physical_attempts_per_run"],
        MAXIMUM_PHYSICAL_ATTEMPTS,
    )
    _require_exact(
        "governance_timeout",
        governance["timeout_seconds_per_physical_attempt"],
        PER_ATTEMPT_TIMEOUT_SECONDS,
    )
    _require_exact(
        "governance_retry_scope",
        governance["retry_scope"],
        "transient_infrastructure_or_provider_availability_only",
    )
    _require_exact(
        "governance_never_retry_scope",
        governance["never_retry_scope"],
        "semantic_security_contract_configuration_or_preflight_failures",
    )
    _require_exact("governance_reason_owner", governance["retry_reason_owner"], "application")
    _require_exact("governance_reason_closed", governance["retry_reason_vocabulary_closed"], True)

    series = raw["retry_series_identity"]
    _require_exact(
        "retry_series_identity",
        series["fields_in_order"],
        list(_SERIES_IDENTITY_FIELDS),
    )
    _require_exact(
        "retry_series_attempt_exclusion",
        series["attempt_number_excluded_from_series_identity"],
        True,
    )

    budget = raw["attempt_budget"]
    _require_exact(
        "attempt_budget",
        budget["maximum_physical_attempts_per_run"],
        MAXIMUM_PHYSICAL_ATTEMPTS,
    )
    _require_exact("maximum_retries", budget["maximum_retries_per_run"], 1)
    _require_exact("attempt_numbers", budget["attempt_numbers"], [1, 2])
    for field in (
        "every_started_physical_attempt_consumes_one_attempt",
        "third_attempt_forbidden",
    ):
        _require_exact(f"attempt_budget:{field}", budget[field], True)
    for field in (
        "preflight_failure_creates_attempt",
        "preflight_failure_consumes_attempt",
    ):
        _require_exact(f"attempt_budget:{field}", budget[field], False)

    timeout = raw["per_attempt_timeout"]
    _require_exact(
        "per_attempt_timeout",
        timeout["timeout_seconds"],
        PER_ATTEMPT_TIMEOUT_SECONDS,
    )
    _require_exact("timeout_clock", timeout["clock"], "monotonic_elapsed_time")
    _require_exact("timeout_terminal", timeout["timeout_terminal_outcome"], "provider_timeout")
    _require_exact("timeout_reason", timeout["timeout_retry_reason"], "provider_timeout")
    _require_exact("timeout_longer", timeout["provider_specific_longer_timeout_allowed"], False)
    _require_exact("timeout_shorter", timeout["provider_specific_shorter_timeout_allowed"], False)

    retryable = raw["retryable_failures"]
    _require_exact(
        "retryable_outcomes",
        retryable["attempt_outcomes_in_order"],
        list(RETRY_REASONS_BY_OUTCOME),
    )
    _require_exact(
        "retry_reason_inventory",
        retryable["safe_retry_reasons_in_order"],
        list(SAFE_RETRY_REASONS),
    )
    _require_exact(
        "retry_reason_mapping",
        retryable["allowed_retry_reasons_by_attempt_outcome"],
        {
            outcome: list(reasons)
            for outcome, reasons in RETRY_REASONS_BY_OUTCOME.items()
        },
    )
    _require_exact(
        "nonretryable_outcomes",
        raw["nonretryable_attempt_outcomes_in_order"],
        list(NONRETRYABLE_ATTEMPT_OUTCOMES),
    )

    boundary = raw["execution_boundary"]
    for field in (
        "contract_grants_provider_execution_authority",
        "provider_calls_allowed",
        "pilot_calls_allowed",
        "scored_calls_allowed",
        "winner_selected",
    ):
        _require_exact(f"execution_boundary:{field}", boundary[field], False)
    _require_exact(
        "provider_calls_completed", boundary["provider_calls_completed"], 0
    )

    identity = raw["specification_identity"]
    _require_exact("hash_algorithm", identity["hash_algorithm"], "sha256")
    _require_exact(
        "hash_input",
        identity["hash_input"],
        "canonical_compact_utf8_json_with_semantic_hash_replaced_by_null",
    )
    _require_exact("semantic_hash", identity["semantic_hash"], _EXPECTED_SEMANTIC_HASH)
    if _semantic_hash(raw) != _EXPECTED_SEMANTIC_HASH:
        raise _fail("retry_policy_semantic_hash")

    return RetryPolicy(
        artifact_id=raw["artifact_id"],
        artifact_version=raw["artifact_version"],
        status=raw["status"],
        semantic_hash=identity["semantic_hash"],
        maximum_physical_attempts=budget["maximum_physical_attempts_per_run"],
        maximum_retries=budget["maximum_retries_per_run"],
        per_attempt_timeout_seconds=timeout["timeout_seconds"],
        retry_series_identity_fields=tuple(series["fields_in_order"]),
        safe_retry_reasons=tuple(retryable["safe_retry_reasons_in_order"]),
        retry_reasons_by_outcome=tuple(
            (outcome, tuple(reasons))
            for outcome, reasons in retryable[
                "allowed_retry_reasons_by_attempt_outcome"
            ].items()
        ),
        nonretryable_attempt_outcomes=tuple(
            raw["nonretryable_attempt_outcomes_in_order"]
        ),
        provider_calls_allowed=boundary["provider_calls_allowed"],
        pilot_calls_allowed=boundary["pilot_calls_allowed"],
        scored_calls_allowed=boundary["scored_calls_allowed"],
        provider_calls_completed=boundary["provider_calls_completed"],
    )


def decide_retry(
    *,
    attempt_number: int,
    attempt_outcome: str,
    transient_retry_reason: str | None = None,
) -> RetryDecision:
    """Return the unique policy decision for one completed physical attempt."""

    if type(attempt_number) is not int or not 1 <= attempt_number <= 2:
        raise _fail("attempt_number")
    if type(attempt_outcome) is not str or attempt_outcome not in TERMINAL_OUTCOMES:
        raise _fail("attempt_outcome")
    if transient_retry_reason is not None:
        if (
            type(transient_retry_reason) is not str
            or transient_retry_reason not in SAFE_RETRY_REASONS
            or transient_retry_reason
            not in RETRY_REASONS_BY_OUTCOME.get(attempt_outcome, ())
        ):
            raise _fail("transient_retry_reason")

    if attempt_number == 1 and transient_retry_reason is not None:
        return RetryDecision(
            attempt_number=attempt_number,
            attempt_outcome=attempt_outcome,
            retry_allowed=True,
            retry_reason=transient_retry_reason,
            next_attempt_number=2,
            run_terminal=False,
            budget_exhausted=False,
        )
    return RetryDecision(
        attempt_number=attempt_number,
        attempt_outcome=attempt_outcome,
        retry_allowed=False,
        retry_reason=None,
        next_attempt_number=None,
        run_terminal=True,
        budget_exhausted=attempt_number == MAXIMUM_PHYSICAL_ATTEMPTS,
    )


def validate_retry_linkage(
    *,
    previous_attempt_outcome: str | None,
    attempt_number: int,
    retry_reason: str | None,
) -> None:
    """Validate a candidate attempt against its immutable predecessor."""

    if type(attempt_number) is not int or not 1 <= attempt_number <= 2:
        raise _fail("attempt_number")
    if attempt_number == 1:
        if previous_attempt_outcome is not None or retry_reason is not None:
            raise _fail("first_attempt_linkage")
        return
    if previous_attempt_outcome is None:
        raise _fail("missing_previous_attempt")
    if previous_attempt_outcome not in RETRY_REASONS_BY_OUTCOME:
        raise _fail("previous_attempt_nonretryable")
    if retry_reason not in RETRY_REASONS_BY_OUTCOME[previous_attempt_outcome]:
        raise _fail("retry_reason")
    decision = decide_retry(
        attempt_number=1,
        attempt_outcome=previous_attempt_outcome,
        transient_retry_reason=retry_reason,
    )
    if not decision.retry_allowed:
        raise _fail("previous_attempt_nonretryable")
    if retry_reason != decision.retry_reason:
        raise _fail("retry_reason")
