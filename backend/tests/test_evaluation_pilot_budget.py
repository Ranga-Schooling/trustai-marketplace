"""Exact, provider-free pilot budget-control tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
import copy
import hashlib
import json
from pathlib import Path

import pytest

from app.services.evaluation_pilot_budget import (
    ActiveAttemptReservation,
    CompletedAttemptCost,
    CostReconciliationRecord,
    PendingAttemptCost,
    PilotBudgetError,
    PilotBudgetLedger,
    assert_no_pending_cost_reconciliation,
    commit_provider_attempt_cost,
    empty_pilot_budget_ledger,
    mark_attempt_pending_reconciliation,
    pilot_budget_ledger_from_json,
    pilot_budget_ledger_to_json,
    reconcile_pending_attempt_cost,
    reserve_provider_attempt,
    verify_pilot_budget_control,
)


ROOT = Path(__file__).resolve().parents[2]


def test_budget_contract_binds_the_approved_ceiling_and_current_call_plan():
    budget = verify_pilot_budget_control()

    assert budget.artifact_id == "pilot_budget_control_v2"
    assert budget.artifact_version == "v2"
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


def test_v1_history_is_preserved_while_v2_has_new_frozen_identity():
    v1 = json.loads(
        (ROOT / "docs/testing/ai-evaluation/pilot-budget-control.v1.json").read_text()
    )
    v2 = json.loads(
        (ROOT / "docs/testing/ai-evaluation/pilot-budget-control.v2.json").read_text()
    )

    assert v1["specification_identity"]["semantic_hash"] == (
        "2a6d8fdfdd39efcf8ddc027734988a557d222885f736ddc60d8162dd059b7b23"
    )
    assert v2["supersession"]["supersedes_semantic_hash"] == (
        v1["specification_identity"]["semantic_hash"]
    )
    assert v2["specification_identity"]["semantic_hash"] == (
        "7e4065dd69809f581ca475a3a9da8d4669b5961274da0c43574b844f3c12f824"
    )


def test_budget_and_reconciliation_policy_hashes_recompute_independently():
    value = json.loads(
        (ROOT / "docs/testing/ai-evaluation/pilot-budget-control.v2.json").read_text()
    )
    detached = copy.deepcopy(value)
    detached["specification_identity"]["semantic_hash"] = None
    policy = copy.deepcopy(value["pending_cost_reconciliation_policy"])
    policy["policy_hash"] = None

    assert hashlib.sha256(
        json.dumps(detached, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest() == value["specification_identity"]["semantic_hash"]
    assert hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest() == value["pending_cost_reconciliation_policy"]["policy_hash"]


@pytest.mark.parametrize("mutation", ("old_artifact_hash", "tampered_policy"))
def test_old_identity_or_tampered_reconciliation_policy_fails_closed(
    tmp_path, mutation
):
    value = json.loads(
        (ROOT / "docs/testing/ai-evaluation/pilot-budget-control.v2.json").read_text()
    )
    if mutation == "old_artifact_hash":
        value["specification_identity"]["semantic_hash"] = (
            "2a6d8fdfdd39efcf8ddc027734988a557d222885f736ddc60d8162dd059b7b23"
        )
    else:
        value["pending_cost_reconciliation_policy"][
            "retry_blocked_until_reconciliation"
        ] = False
        detached = copy.deepcopy(value)
        detached["specification_identity"]["semantic_hash"] = None
        value["specification_identity"]["semantic_hash"] = hashlib.sha256(
            json.dumps(detached, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    path = tmp_path / "budget.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(PilotBudgetError, match="semantic_hash"):
        verify_pilot_budget_control(path)


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


def _reserved_pending_ledger(
    *,
    reservation: str = "0.50",
    outcome: str = "failed_retryable",
) -> tuple[PilotBudgetLedger, str]:
    attempt_id = "eval-1:PT1:groq:run-1:attempt-1"
    reserved = reserve_provider_attempt(
        empty_pilot_budget_ledger(),
        attempt_id=attempt_id,
        conservative_upper_bound_usd=reservation,
    )
    pending = mark_attempt_pending_reconciliation(
        reserved,
        attempt_id=attempt_id,
        provider="Groq",
        candidate_id="baseline_current_text_v1",
        model="openai/gpt-oss-120b",
        outcome=outcome,
    )
    return pending, attempt_id


def test_pending_cost_counts_attempt_and_preserves_full_reservation_without_zero():
    ledger, attempt_id = _reserved_pending_ledger(reservation="0.50000000")

    assert ledger.committed_cost_usd == Decimal("0.00")
    assert ledger.reserved_cost_usd == Decimal("0.00")
    assert ledger.pending_encumbered_cost_usd == Decimal("0.50000000")
    assert ledger.total_encumbered_cost_usd == Decimal("0.50000000")
    assert ledger.remaining_unreserved_usd == Decimal("4.50000000")
    assert ledger.provider_calls_completed == 1
    assert ledger.unresolved_pending_attempt_ids == (attempt_id,)
    assert ledger.pending_attempts[0].actual_cost_usd is None
    assert ledger.pending_attempts[0].outcome == "failed_retryable"


def test_pending_cost_is_a_global_execution_blocker():
    ledger, attempt_id = _reserved_pending_ledger()

    with pytest.raises(PilotBudgetError, match="pending_cost_reconciliation"):
        assert_no_pending_cost_reconciliation(ledger)
    with pytest.raises(PilotBudgetError, match="pending_cost_reconciliation"):
        reserve_provider_attempt(
            ledger,
            attempt_id="eval-1:PT2:groq:run-1:attempt-1",
            conservative_upper_bound_usd="0.01",
        )

    assert ledger.unresolved_pending_attempt_ids == (attempt_id,)
    assert ledger.provider_calls_completed == 1


def test_pending_cost_does_not_reclassify_the_terminal_attempt_outcome():
    ledger, _ = _reserved_pending_ledger(outcome="failed_nonretryable")

    assert ledger.pending_attempts[0].outcome == "failed_nonretryable"
    assert ledger.pending_attempts[0].billing_state == "pending_cost_reconciliation"


def test_reconciliation_commits_exact_cost_and_releases_only_unused_reservation():
    ledger, attempt_id = _reserved_pending_ledger(reservation="0.50")

    reconciled = reconcile_pending_attempt_cost(
        ledger,
        reconciliation_id="reconciliation-0001",
        attempt_id=attempt_id,
        actual_cost_usd="0.18",
        authoritative_evidence_type="provider_usage_record",
        authoritative_evidence_reference="a" * 64,
        reconciled_at="2026-09-01T20:00:00Z",
    )

    assert reconciled.committed_cost_usd == Decimal("0.18")
    assert reconciled.pending_encumbered_cost_usd == Decimal("0.00")
    assert reconciled.remaining_unreserved_usd == Decimal("4.82")
    assert reconciled.provider_calls_completed == 1
    assert reconciled.unresolved_pending_attempt_ids == ()
    assert len(reconciled.pending_attempts) == 1
    assert reconciled.pending_attempts[0].billing_state == "pending_cost_reconciliation"
    assert reconciled.completed_attempts[0].actual_cost_usd == Decimal("0.18")
    assert reconciled.reconciliations[0].released_reservation_usd == Decimal("0.32")
    assert (
        reconciled.reconciliations[0].prior_pending_state_reference
        == ledger.pending_attempts[0].pending_state_reference
    )
    assert_no_pending_cost_reconciliation(reconciled)


@pytest.mark.parametrize("actual", [0.1, 1, True, None, "", "NaN", "-0.01"])
def test_reconciliation_rejects_float_negative_or_noncanonical_actual_cost(actual):
    ledger, attempt_id = _reserved_pending_ledger()

    with pytest.raises(PilotBudgetError, match="actual_cost_usd"):
        reconcile_pending_attempt_cost(
            ledger,
            reconciliation_id="reconciliation-0001",
            attempt_id=attempt_id,
            actual_cost_usd=actual,
            authoritative_evidence_type="provider_usage_record",
            authoritative_evidence_reference="a" * 64,
            reconciled_at="2026-09-01T20:00:00Z",
        )

    assert ledger.unresolved_pending_attempt_ids == (attempt_id,)


def test_reconciliation_cannot_silently_exceed_reservation():
    ledger, attempt_id = _reserved_pending_ledger(reservation="0.50")

    with pytest.raises(PilotBudgetError, match="actual_cost_exceeds_reservation"):
        reconcile_pending_attempt_cost(
            ledger,
            reconciliation_id="reconciliation-0001",
            attempt_id=attempt_id,
            actual_cost_usd="0.50000001",
            authoritative_evidence_type="provider_billing_record",
            authoritative_evidence_reference="b" * 64,
            reconciled_at="2026-09-01T20:00:00Z",
        )

    assert ledger.unresolved_pending_attempt_ids == (attempt_id,)
    assert ledger.pending_encumbered_cost_usd == Decimal("0.50")


@pytest.mark.parametrize(
    ("evidence_type", "evidence_reference"),
    (
        (None, "a" * 64),
        ("", "a" * 64),
        ("operator_guess", "a" * 64),
        ("provider_usage_record", None),
        ("provider_usage_record", ""),
        ("provider_usage_record", "not-a-sha256"),
    ),
)
def test_reconciliation_requires_closed_authoritative_evidence(
    evidence_type, evidence_reference
):
    ledger, attempt_id = _reserved_pending_ledger()

    with pytest.raises(PilotBudgetError, match="authoritative_cost_evidence"):
        reconcile_pending_attempt_cost(
            ledger,
            reconciliation_id="reconciliation-0001",
            attempt_id=attempt_id,
            actual_cost_usd="0.10",
            authoritative_evidence_type=evidence_type,
            authoritative_evidence_reference=evidence_reference,
            reconciled_at="2026-09-01T20:00:00Z",
        )


@pytest.mark.parametrize(
    "timestamp",
    (None, "", "2026-09-01", "2026-02-30T20:00:00Z", "2026-09-01T20:00:00+00:00"),
)
def test_reconciliation_requires_exact_valid_utc_seconds(timestamp):
    ledger, attempt_id = _reserved_pending_ledger()

    with pytest.raises(PilotBudgetError, match="reconciled_at"):
        reconcile_pending_attempt_cost(
            ledger,
            reconciliation_id="reconciliation-0001",
            attempt_id=attempt_id,
            actual_cost_usd="0.10",
            authoritative_evidence_type="provider_usage_record",
            authoritative_evidence_reference="a" * 64,
            reconciled_at=timestamp,
        )


def test_reconciliation_record_is_immutable_and_binds_frozen_policy_and_pricing():
    ledger, attempt_id = _reserved_pending_ledger()
    reconciled = reconcile_pending_attempt_cost(
        ledger,
        reconciliation_id="reconciliation-0001",
        attempt_id=attempt_id,
        actual_cost_usd="0.10",
        authoritative_evidence_type="provider_usage_metadata",
        authoritative_evidence_reference="c" * 64,
        reconciled_at="2026-09-01T20:00:00Z",
    )
    record = reconciled.reconciliations[0]

    assert record.provider == "Groq"
    assert record.candidate_id == "baseline_current_text_v1"
    assert record.model == "openai/gpt-oss-120b"
    assert record.pricing_snapshot_id == "pricing_snapshot_v1"
    assert len(record.pricing_snapshot_hash) == 64
    assert record.reconciliation_policy_id == "pending_cost_reconciliation_policy_v1"
    assert record.reconciliation_policy_version == "v1"
    assert len(record.reconciliation_policy_hash) == 64
    assert len(record.reconciliation_record_hash) == 64
    with pytest.raises(FrozenInstanceError):
        record.actual_cost_usd = Decimal("0.00")  # type: ignore[misc]


def test_pending_ledger_round_trip_preserves_unresolved_fact_and_blocker():
    ledger, attempt_id = _reserved_pending_ledger(reservation="0.12345678")

    encoded = pilot_budget_ledger_to_json(ledger)
    restored = pilot_budget_ledger_from_json(encoded)

    assert restored == ledger
    assert restored.unresolved_pending_attempt_ids == (attempt_id,)
    assert restored.pending_encumbered_cost_usd == Decimal("0.12345678")
    with pytest.raises(PilotBudgetError, match="pending_cost_reconciliation"):
        assert_no_pending_cost_reconciliation(restored)


def test_reconciled_ledger_round_trip_preserves_pending_history_and_exact_cost():
    ledger, attempt_id = _reserved_pending_ledger()
    ledger = reconcile_pending_attempt_cost(
        ledger,
        reconciliation_id="reconciliation-0001",
        attempt_id=attempt_id,
        actual_cost_usd="0.10",
        authoritative_evidence_type="provider_billing_record",
        authoritative_evidence_reference="d" * 64,
        reconciled_at="2026-09-01T20:00:00Z",
    )

    assert pilot_budget_ledger_from_json(pilot_budget_ledger_to_json(ledger)) == ledger


def test_malformed_import_with_multiple_unresolved_pending_attempts_fails_closed():
    first, _ = _reserved_pending_ledger()
    second_attempt_id = "eval-1:PT2:groq:run-1:attempt-1"
    second = reserve_provider_attempt(
        empty_pilot_budget_ledger(),
        attempt_id=second_attempt_id,
        conservative_upper_bound_usd="0.10",
    )
    second = mark_attempt_pending_reconciliation(
        second,
        attempt_id=second_attempt_id,
        provider="Groq",
        candidate_id="baseline_current_text_v1",
        model="openai/gpt-oss-120b",
        outcome="failed_retryable",
    )
    malformed = PilotBudgetLedger(
        pending_attempts=(
            *first.pending_attempts,
            *second.pending_attempts,
        )
    )

    with pytest.raises(PilotBudgetError, match="multiple_pending_cost_reconciliation"):
        assert_no_pending_cost_reconciliation(malformed)
    with pytest.raises(PilotBudgetError, match="multiple_pending_cost_reconciliation"):
        reserve_provider_attempt(
            malformed,
            attempt_id="eval-1:PT3:groq:run-1:attempt-1",
            conservative_upper_bound_usd="0.10",
        )


@pytest.mark.parametrize(
    "mutation",
    (
        PilotBudgetLedger(
            pending_attempts=(
                PendingAttemptCost(
                    "attempt-1", "Groq", "candidate", "model", Decimal("0.10"),
                    "failed_retryable", "wrong", "f" * 64,
                ),
            )
        ),
        PilotBudgetLedger(
            reconciliations=(
                CostReconciliationRecord(
                    "reconciliation-1", "attempt-1", "Groq", "candidate", "model",
                    Decimal("0.10"), Decimal("0.09"), Decimal("0.01"),
                    "provider_usage_record", "a" * 64, "2026-09-01T20:00:00Z",
                    "pricing_snapshot_v1", "b" * 64,
                    "pending_cost_reconciliation_policy_v1", "v1", "c" * 64,
                    "d" * 64, "e" * 64,
                ),
            )
        ),
    ),
)
def test_tampered_pending_or_reconciliation_ledger_state_fails_closed(mutation):
    with pytest.raises(PilotBudgetError, match="ledger"):
        pilot_budget_ledger_to_json(mutation)


def test_pending_state_contains_no_provider_diagnostics_or_raw_evidence():
    ledger, _ = _reserved_pending_ledger()
    exposed = pilot_budget_ledger_to_json(ledger).decode("utf-8")

    assert "provider diagnostic prose" not in exposed
    assert "raw_response" not in exposed
    assert "credential" not in exposed.lower()
    assert "pending_cost_reconciliation" in exposed
