"""Exact, provider-free pilot budget-control tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.evaluation_pilot_budget import (
    ActiveAttemptReservation,
    CompletedAttemptCost,
    PilotBudgetError,
    PilotBudgetLedger,
    commit_provider_attempt_cost,
    empty_pilot_budget_ledger,
    reserve_provider_attempt,
    verify_pilot_budget_control,
)


ROOT = Path(__file__).resolve().parents[2]


def test_budget_contract_binds_the_approved_ceiling_and_current_call_plan():
    budget = verify_pilot_budget_control()

    assert budget.artifact_id == "pilot_budget_control_v1"
    assert budget.artifact_version == "v1"
    assert budget.approved_ceiling_usd == Decimal("5.00")
    assert budget.currency == "USD"
    assert budget.planned_nominal_calls == 26
    assert budget.planned_maximum_physical_attempts == 52
    assert budget.currently_eligible_nominal_calls == 22
    assert budget.currently_eligible_maximum_physical_attempts == 44
    assert budget.known_charge_subtotal_two_attempts_usd == Decimal("2.73434880")
    assert budget.remaining_headroom_over_known_subtotal_usd == Decimal("2.26565120")
    assert budget.conservative_maximum_total_cost_usd is None
    assert budget.provider_calls_allowed is False
    assert budget.pilot_calls_allowed is False
    assert budget.provider_calls_completed == 0
    assert budget.winner_selected is False

    with pytest.raises(FrozenInstanceError):
        budget.provider_calls_allowed = True  # type: ignore[misc]


def test_attempt_reservation_uses_exact_decimal_and_includes_active_reservations():
    ledger = empty_pilot_budget_ledger()
    ledger = reserve_provider_attempt(
        ledger,
        attempt_id="eval-1:PT1:openai:run-1:attempt-1",
        conservative_upper_bound_usd="2.73434880",
    )
    ledger = reserve_provider_attempt(
        ledger,
        attempt_id="eval-1:PT2:openai:run-1:attempt-1",
        conservative_upper_bound_usd="2.26565120",
    )

    assert ledger.committed_cost_usd == Decimal("0.00")
    assert ledger.reserved_cost_usd == Decimal("5.00000000")
    assert ledger.remaining_unreserved_usd == Decimal("0E-8")
    assert ledger.provider_calls_completed == 0
    assert ledger.active_attempt_ids == (
        "eval-1:PT1:openai:run-1:attempt-1",
        "eval-1:PT2:openai:run-1:attempt-1",
    )


@pytest.mark.parametrize("value", [None, 0.1, 1, True, "", "1", "NaN", "Infinity"])
def test_attempt_reservation_rejects_missing_float_or_noncanonical_money(value):
    ledger = empty_pilot_budget_ledger()

    with pytest.raises(PilotBudgetError, match="conservative_upper_bound_usd"):
        reserve_provider_attempt(
            ledger,
            attempt_id="eval-1:PT1:openai:run-1:attempt-1",
            conservative_upper_bound_usd=value,
        )

    assert ledger.provider_calls_completed == 0
    assert ledger.active_attempt_ids == ()


def test_attempt_is_blocked_before_invocation_when_ceiling_cannot_accommodate_it():
    ledger = reserve_provider_attempt(
        empty_pilot_budget_ledger(),
        attempt_id="eval-1:PT1:openai:run-1:attempt-1",
        conservative_upper_bound_usd="4.99999999",
    )

    with pytest.raises(PilotBudgetError, match="pilot_budget_ceiling_exhausted") as exc:
        reserve_provider_attempt(
            ledger,
            attempt_id="eval-1:PT2:openai:run-1:attempt-1",
            conservative_upper_bound_usd="0.00000002",
        )

    assert exc.value.provider_call_incremented is False
    assert ledger.provider_calls_completed == 0
    assert ledger.active_attempt_ids == (
        "eval-1:PT1:openai:run-1:attempt-1",
    )


def test_duplicate_attempt_identity_cannot_be_reserved_or_committed_twice():
    attempt_id = "eval-1:PT1:openai:run-1:attempt-1"
    ledger = reserve_provider_attempt(
        empty_pilot_budget_ledger(),
        attempt_id=attempt_id,
        conservative_upper_bound_usd="0.20",
    )
    with pytest.raises(PilotBudgetError, match="attempt_id_not_unique"):
        reserve_provider_attempt(
            ledger,
            attempt_id=attempt_id,
            conservative_upper_bound_usd="0.20",
        )

    ledger = commit_provider_attempt_cost(
        ledger,
        attempt_id=attempt_id,
        actual_cost_usd="0.18",
        outcome="failed_retryable",
    )
    with pytest.raises(PilotBudgetError, match="attempt_not_reserved"):
        commit_provider_attempt_cost(
            ledger,
            attempt_id=attempt_id,
            actual_cost_usd="0.18",
            outcome="failed_retryable",
        )


def test_failed_attempt_cost_is_preserved_when_a_retry_is_reserved_and_completed():
    first = "eval-1:PT1:openai:run-1:attempt-1"
    second = "eval-1:PT1:openai:run-1:attempt-2"
    ledger = reserve_provider_attempt(
        empty_pilot_budget_ledger(),
        attempt_id=first,
        conservative_upper_bound_usd="0.50",
    )
    ledger = commit_provider_attempt_cost(
        ledger,
        attempt_id=first,
        actual_cost_usd="0.40",
        outcome="failed_retryable",
    )
    ledger = reserve_provider_attempt(
        ledger,
        attempt_id=second,
        conservative_upper_bound_usd="0.50",
    )
    ledger = commit_provider_attempt_cost(
        ledger,
        attempt_id=second,
        actual_cost_usd="0.35",
        outcome="succeeded",
    )

    assert tuple(
        (item.attempt_id, item.actual_cost_usd, item.outcome)
        for item in ledger.completed_attempts
    ) == (
        (first, Decimal("0.40"), "failed_retryable"),
        (second, Decimal("0.35"), "succeeded"),
    )
    assert ledger.committed_cost_usd == Decimal("0.75")
    assert ledger.provider_calls_completed == 2
    assert ledger.active_attempt_ids == ()


def test_actual_cost_cannot_exceed_its_pre_attempt_reservation():
    attempt_id = "eval-1:PT1:openai:run-1:attempt-1"
    ledger = reserve_provider_attempt(
        empty_pilot_budget_ledger(),
        attempt_id=attempt_id,
        conservative_upper_bound_usd="0.50",
    )

    with pytest.raises(PilotBudgetError, match="actual_cost_exceeds_reservation"):
        commit_provider_attempt_cost(
            ledger,
            attempt_id=attempt_id,
            actual_cost_usd="0.50000001",
            outcome="succeeded",
        )

    assert ledger.provider_calls_completed == 0
    assert ledger.active_attempt_ids == (attempt_id,)


@pytest.mark.parametrize("outcome", ["", "timeout", "retry", None, False])
def test_attempt_completion_has_a_closed_safe_outcome_vocabulary(outcome):
    attempt_id = "eval-1:PT1:openai:run-1:attempt-1"
    ledger = reserve_provider_attempt(
        empty_pilot_budget_ledger(),
        attempt_id=attempt_id,
        conservative_upper_bound_usd="0.50",
    )

    with pytest.raises(PilotBudgetError, match="attempt_outcome"):
        commit_provider_attempt_cost(
            ledger,
            attempt_id=attempt_id,
            actual_cost_usd="0.10",
            outcome=outcome,
        )


@pytest.mark.parametrize(
    "ledger",
    [
        PilotBudgetLedger(approved_ceiling_usd=Decimal("5.01")),
        PilotBudgetLedger(active_reservations=("not-a-reservation",)),
        PilotBudgetLedger(
            active_reservations=(
                ActiveAttemptReservation("attempt-1", Decimal("NaN")),
            )
        ),
        PilotBudgetLedger(
            completed_attempts=(
                CompletedAttemptCost(
                    "attempt-1",
                    Decimal("0.10"),
                    Decimal("0.11"),
                    "succeeded",
                ),
            )
        ),
        PilotBudgetLedger(
            completed_attempts=(
                CompletedAttemptCost(
                    "attempt-1",
                    Decimal("0.10"),
                    Decimal("0.09"),
                    "invented_outcome",
                ),
            )
        ),
    ],
)
def test_malformed_ledger_state_fails_closed_without_an_attempt(ledger):
    with pytest.raises(PilotBudgetError, match="ledger"):
        reserve_provider_attempt(
            ledger,
            attempt_id="eval-1:PT1:openai:run-1:attempt-1",
            conservative_upper_bound_usd="0.10",
        )


def test_budget_module_is_provider_free_and_has_no_float_money_authority():
    source = (
        ROOT / "backend" / "app" / "services" / "evaluation_pilot_budget.py"
    ).read_text(encoding="utf-8")

    assert "requests" not in source
    assert "httpx" not in source
    assert "urllib" not in source
    assert "os.environ" not in source
    assert "float(" not in source
    assert "Decimal" in source
