"""Exact provider-free enforcement of the approved pilot spending ceiling.

The reservation ledger is immutable and application-owned.  It does not
inspect billing accounts, access credentials, invoke providers, or authorize
execution.  A caller must supply a conservative upper bound before an attempt
can be admitted; an absent or unbounded estimate fails before invocation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import copy
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from app.services.evaluation_contract_identity import load_strict_contract_json


_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_ARTIFACT = (
    _ROOT / "docs" / "testing" / "ai-evaluation" / "pilot-budget-control.v2.json"
)
_EXPECTED_HASH = "7e4065dd69809f581ca475a3a9da8d4669b5961274da0c43574b844f3c12f824"
_EXPECTED_COST_ENVELOPE_HASH = (
    "40899a9b6a8b94928bb52947da1f040699cbee7f7f13be0902c17a7db25b2942"
)
_PRICING_SNAPSHOT_ID = "pricing_snapshot_v1"
_PRICING_SNAPSHOT_HASH = (
    "0467643eafbe55e6e2215c9ad0e0576dac2d0d157a94418eef23382b0ec09282"
)
_RECONCILIATION_POLICY_ID = "pending_cost_reconciliation_policy_v1"
_RECONCILIATION_POLICY_VERSION = "v1"
_RECONCILIATION_POLICY_HASH = (
    "9d0598ad72f4b3da7b76b349081bae7f61aeb195a852c32c8ec863df4555a0c6"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ATTEMPT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+@\-]{0,255}\Z")
_SAFE_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+@\- ]{0,255}\Z")
_UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z\Z"
)
_MONEY = re.compile(r"(?:0|[1-9][0-9]*)\.[0-9]{2,8}\Z")
_OUTCOMES = frozenset({"succeeded", "failed_retryable", "failed_nonretryable"})
_PENDING_BILLING_STATE = "pending_cost_reconciliation"
_AUTHORITATIVE_EVIDENCE_TYPES = frozenset(
    {
        "provider_usage_metadata",
        "provider_usage_record",
        "provider_billing_record",
    }
)
_CEILING = Decimal("5.00")


class PilotBudgetError(ValueError):
    """Budget state or an attempted reservation failed closed."""

    provider_call_incremented = False


def _fail(code: str) -> PilotBudgetError:
    return PilotBudgetError(code)


def _canonical_without_hash(raw: dict[str, Any]) -> bytes:
    detached = copy.deepcopy(raw)
    detached["specification_identity"]["semantic_hash"] = None
    return json.dumps(
        detached,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _money(name: str, value: Any, *, positive: bool) -> Decimal:
    if type(value) is not str or _MONEY.fullmatch(value) is None:
        raise _fail(name)
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise _fail(name) from None
    if not result.is_finite() or (positive and result <= 0) or result < 0:
        raise _fail(name)
    return result


def _attempt_id(value: Any) -> str:
    if type(value) is not str or _SAFE_ATTEMPT_ID.fullmatch(value) is None:
        raise _fail("attempt_id")
    return value


def _utc_timestamp(value: Any) -> str:
    if type(value) is not str or _UTC_TIMESTAMP.fullmatch(value) is None:
        raise _fail("reconciled_at")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise _fail("reconciled_at") from None
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise _fail("reconciled_at")
    return value


def _valid_utc_timestamp(value: Any) -> bool:
    try:
        _utc_timestamp(value)
    except PilotBudgetError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class PilotBudgetControl:
    artifact_id: str
    artifact_version: str
    semantic_hash: str
    currency: str
    approved_ceiling_usd: Decimal
    planned_nominal_calls: int
    planned_maximum_physical_attempts: int
    currently_eligible_nominal_calls: int
    currently_eligible_maximum_physical_attempts: int
    known_charge_subtotal_two_attempts_usd: Decimal
    remaining_headroom_over_known_subtotal_usd: Decimal
    conservative_maximum_total_cost_usd: None
    provider_calls_allowed: bool
    pilot_calls_allowed: bool
    scored_calls_allowed: bool
    provider_calls_completed: int
    winner_selected: bool


@dataclass(frozen=True, slots=True)
class ActiveAttemptReservation:
    attempt_id: str
    conservative_upper_bound_usd: Decimal


@dataclass(frozen=True, slots=True)
class CompletedAttemptCost:
    attempt_id: str
    reserved_upper_bound_usd: Decimal
    actual_cost_usd: Decimal
    outcome: str


@dataclass(frozen=True, slots=True)
class PendingAttemptCost:
    attempt_id: str
    provider: str
    candidate_id: str
    model: str
    reserved_upper_bound_usd: Decimal
    outcome: str
    billing_state: str
    pending_state_reference: str

    @property
    def actual_cost_usd(self) -> None:
        return None


@dataclass(frozen=True, slots=True)
class CostReconciliationRecord:
    reconciliation_id: str
    attempt_id: str
    provider: str
    candidate_id: str
    model: str
    reserved_upper_bound_usd: Decimal
    actual_cost_usd: Decimal
    released_reservation_usd: Decimal
    authoritative_evidence_type: str
    authoritative_evidence_reference: str
    reconciled_at: str
    pricing_snapshot_id: str
    pricing_snapshot_hash: str
    reconciliation_policy_id: str
    reconciliation_policy_version: str
    reconciliation_policy_hash: str
    prior_pending_state_reference: str
    reconciliation_record_hash: str


@dataclass(frozen=True, slots=True)
class PilotBudgetLedger:
    approved_ceiling_usd: Decimal = _CEILING
    active_reservations: tuple[ActiveAttemptReservation, ...] = ()
    completed_attempts: tuple[CompletedAttemptCost, ...] = ()
    pending_attempts: tuple[PendingAttemptCost, ...] = ()
    reconciliations: tuple[CostReconciliationRecord, ...] = ()

    @property
    def committed_cost_usd(self) -> Decimal:
        return sum(
            (item.actual_cost_usd for item in self.completed_attempts),
            Decimal("0.00"),
        )

    @property
    def reserved_cost_usd(self) -> Decimal:
        return sum(
            (item.conservative_upper_bound_usd for item in self.active_reservations),
            Decimal("0.00"),
        )

    @property
    def unresolved_pending_attempts(self) -> tuple[PendingAttemptCost, ...]:
        reconciled_ids = {item.attempt_id for item in self.reconciliations}
        return tuple(
            item for item in self.pending_attempts if item.attempt_id not in reconciled_ids
        )

    @property
    def unresolved_pending_attempt_ids(self) -> tuple[str, ...]:
        return tuple(item.attempt_id for item in self.unresolved_pending_attempts)

    @property
    def pending_encumbered_cost_usd(self) -> Decimal:
        return sum(
            (
                item.reserved_upper_bound_usd
                for item in self.unresolved_pending_attempts
            ),
            Decimal("0.00"),
        )

    @property
    def total_encumbered_cost_usd(self) -> Decimal:
        return self.reserved_cost_usd + self.pending_encumbered_cost_usd

    @property
    def remaining_unreserved_usd(self) -> Decimal:
        return (
            self.approved_ceiling_usd
            - self.committed_cost_usd
            - self.total_encumbered_cost_usd
        )

    @property
    def provider_calls_completed(self) -> int:
        return len(
            {
                *(item.attempt_id for item in self.completed_attempts),
                *(item.attempt_id for item in self.pending_attempts),
            }
        )

    @property
    def active_attempt_ids(self) -> tuple[str, ...]:
        return tuple(item.attempt_id for item in self.active_reservations)


def verify_pilot_budget_control(
    path: str | Path = _DEFAULT_ARTIFACT,
) -> PilotBudgetControl:
    """Verify the immutable contract without authorizing provider execution."""
    try:
        raw = load_strict_contract_json(Path(path))
    except (OSError, TypeError, ValueError) as exc:
        raise _fail("contract_parse") from exc
    if (
        type(raw) is not dict
        or raw.get("artifact_id") != "pilot_budget_control_v2"
        or raw.get("artifact_version") != "v2"
        or raw.get("status") != "frozen_operator_ceiling_pre_execution"
    ):
        raise _fail("contract_shape")
    identity = raw.get("specification_identity")
    if (
        type(identity) is not dict
        or identity.get("hash_algorithm") != "SHA-256"
        or identity.get("hash_input")
        != "canonical_compact_utf8_json_with_semantic_hash_replaced_by_null"
        or type(identity.get("semantic_hash")) is not str
        or _SHA256.fullmatch(identity["semantic_hash"]) is None
        or hashlib.sha256(_canonical_without_hash(raw)).hexdigest() != _EXPECTED_HASH
        or identity["semantic_hash"] != _EXPECTED_HASH
    ):
        raise _fail("semantic_hash")
    sources = raw.get("source_bindings")
    if (
        type(sources) is not dict
        or sources.get("pilot_cost_envelope_hash") != _EXPECTED_COST_ENVELOPE_HASH
        or sources.get("url_discovery_hash")
        != "c8c0c6280e665677ad211aa1240c42418b851a7537fbde7030200eec119d5145"
        or sources.get("retry_policy_hash")
        != "a4e08ef3b92232cbbf1542aa37b30c87697da60c42bcf72d71876098d0251c4b"
        or sources.get("pricing_snapshot_id") != _PRICING_SNAPSHOT_ID
        or sources.get("pricing_snapshot_hash") != _PRICING_SNAPSHOT_HASH
        or sources.get("result_record_id") != "pilot_result_record_v1"
        or sources.get("result_record_hash")
        != "2dd0ccdc09ce7e3944843bb0e189deacd7750641be8d64a4325778801e9f33d1"
    ):
        raise _fail("source_bindings")
    ceiling = raw.get("approved_ceiling")
    if (
        type(ceiling) is not dict
        or ceiling.get("currency") != "USD"
        or _money("approved_ceiling_usd", ceiling.get("amount"), positive=True)
        != _CEILING
        or ceiling.get("authorization_status") != "approved_operator_ceiling"
        or ceiling.get("spend_or_provider_execution_authority") is not False
        or ceiling.get("binary_floating_point_money_authority") is not False
        or ceiling.get("arithmetic") != "exact_decimal"
    ):
        raise _fail("approved_ceiling")
    plan = raw.get("call_plan")
    if (
        type(plan) is not dict
        or plan.get("planned_nominal_calls") != 26
        or plan.get("planned_maximum_physical_attempts") != 52
        or plan.get("currently_eligible_nominal_calls") != 22
        or plan.get("currently_eligible_maximum_physical_attempts") != 44
        or plan.get("retry_attempts_assumed_free") is not False
    ):
        raise _fail("call_plan")
    costs = raw.get("known_cost_state")
    known_two = _money(
        "known_two_attempt_cost",
        costs.get("known_charge_subtotal_two_attempts_usd")
        if type(costs) is dict
        else None,
        positive=True,
    )
    headroom = _money(
        "remaining_headroom",
        costs.get("remaining_headroom_over_known_subtotal_usd")
        if type(costs) is dict
        else None,
        positive=True,
    )
    if (
        known_two != Decimal("2.73434880")
        or headroom != _CEILING - known_two
        or costs.get("conservative_maximum_total_cost_usd") is not None
        or costs.get("all_planned_costs_finalized") is not False
        or costs.get("known_subtotal_is_attempt_reservation_authority") is not False
    ):
        raise _fail("known_cost_state")
    reservation = raw.get("pre_attempt_reservation")
    if (
        type(reservation) is not dict
        or reservation.get("required_before_provider_invocation") is not True
        or reservation.get("reservation_must_be_conservative_upper_bound") is not True
        or reservation.get("reservation_input_type") != "canonical_decimal_string"
        or reservation.get("maximum_fraction_digits") != 8
        or reservation.get("maximum_fraction_digits_derivation")
        != (
            "maximum fractional precision of the frozen pricing_snapshot_v1 "
            "usd_per_unit rates"
        )
        or reservation.get("block_occurs_before_provider_invocation") is not True
        or reservation.get("blocked_reservation_creates_attempt") is not False
        or reservation.get("blocked_reservation_increments_provider_call_count")
        is not False
        or reservation.get("pending_reconciliation_result")
        != _PENDING_BILLING_STATE
    ):
        raise _fail("pre_attempt_reservation")
    pending = raw.get("pending_cost_reconciliation_policy")
    if (
        type(pending) is not dict
        or pending.get("policy_id") != _RECONCILIATION_POLICY_ID
        or pending.get("policy_version") != _RECONCILIATION_POLICY_VERSION
        or pending.get("policy_hash_algorithm") != "SHA-256"
        or pending.get("policy_hash_input")
        != "canonical_compact_utf8_json_of_this_object_with_policy_hash_replaced_by_null"
        or pending.get("policy_hash") != _RECONCILIATION_POLICY_HASH
        or hashlib.sha256(
            json.dumps(
                {**pending, "policy_hash": None},
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        != _RECONCILIATION_POLICY_HASH
        or pending.get("billing_state") != _PENDING_BILLING_STATE
        or pending.get("actual_cost_usd") is not None
        or pending.get("full_reservation_remains_encumbered") is not True
        or pending.get("physical_provider_attempt_counted_exactly_once") is not True
        or pending.get("retry_blocked_until_reconciliation") is not True
        or pending.get("all_provider_invocation_blocked") is not True
        or pending.get("scored_execution_blocked") is not True
        or pending.get("closed_authoritative_evidence_types")
        != [
            "provider_usage_metadata",
            "provider_usage_record",
            "provider_billing_record",
        ]
        or pending.get("multiple_unresolved_pending_attempts_result")
        != "fail_closed"
    ):
        raise _fail("pending_cost_reconciliation_policy")
    boundary = raw.get("execution_boundary")
    if boundary != {
        "authoritative_execution_gate": "experiment.v1.json execution_gate",
        "execution_state": "blocked_pre_execution",
        "provider_calls_allowed": False,
        "pilot_calls_allowed": False,
        "scored_calls_allowed": False,
        "pending_cost_reconciliation_is_independent_hard_blocker": True,
        "this_artifact_independently_authorizes_execution": False,
    } or any(
        raw.get(name) != 0
        for name in (
            "provider_calls_completed",
            "pilot_calls_completed",
            "scored_calls_completed",
        )
    ) or raw.get("winner_selected") is not False:
        raise _fail("execution_boundary")
    return PilotBudgetControl(
        artifact_id=raw["artifact_id"],
        artifact_version=raw["artifact_version"],
        semantic_hash=identity["semantic_hash"],
        currency=ceiling["currency"],
        approved_ceiling_usd=_CEILING,
        planned_nominal_calls=plan["planned_nominal_calls"],
        planned_maximum_physical_attempts=plan["planned_maximum_physical_attempts"],
        currently_eligible_nominal_calls=plan["currently_eligible_nominal_calls"],
        currently_eligible_maximum_physical_attempts=plan[
            "currently_eligible_maximum_physical_attempts"
        ],
        known_charge_subtotal_two_attempts_usd=known_two,
        remaining_headroom_over_known_subtotal_usd=headroom,
        conservative_maximum_total_cost_usd=None,
        provider_calls_allowed=False,
        pilot_calls_allowed=False,
        scored_calls_allowed=False,
        provider_calls_completed=raw["provider_calls_completed"],
        winner_selected=raw["winner_selected"],
    )


def empty_pilot_budget_ledger() -> PilotBudgetLedger:
    """Return a new zero-cost immutable ledger."""
    return PilotBudgetLedger()


def _validated_ledger(ledger: Any) -> PilotBudgetLedger:
    if (
        type(ledger) is not PilotBudgetLedger
        or type(ledger.approved_ceiling_usd) is not Decimal
        or not ledger.approved_ceiling_usd.is_finite()
        or ledger.approved_ceiling_usd != _CEILING
        or type(ledger.active_reservations) is not tuple
        or type(ledger.completed_attempts) is not tuple
        or type(ledger.pending_attempts) is not tuple
        or type(ledger.reconciliations) is not tuple
    ):
        raise _fail("ledger")
    for item in ledger.active_reservations:
        if (
            type(item) is not ActiveAttemptReservation
            or type(item.conservative_upper_bound_usd) is not Decimal
            or not item.conservative_upper_bound_usd.is_finite()
            or item.conservative_upper_bound_usd <= 0
            or type(item.attempt_id) is not str
            or _SAFE_ATTEMPT_ID.fullmatch(item.attempt_id) is None
        ):
            raise _fail("ledger")
    for item in ledger.completed_attempts:
        if (
            type(item) is not CompletedAttemptCost
            or type(item.reserved_upper_bound_usd) is not Decimal
            or type(item.actual_cost_usd) is not Decimal
            or not item.reserved_upper_bound_usd.is_finite()
            or not item.actual_cost_usd.is_finite()
            or item.reserved_upper_bound_usd <= 0
            or item.actual_cost_usd < 0
            or item.actual_cost_usd > item.reserved_upper_bound_usd
            or type(item.outcome) is not str
            or item.outcome not in _OUTCOMES
            or type(item.attempt_id) is not str
            or _SAFE_ATTEMPT_ID.fullmatch(item.attempt_id) is None
        ):
            raise _fail("ledger")
    for item in ledger.pending_attempts:
        if (
            type(item) is not PendingAttemptCost
            or type(item.reserved_upper_bound_usd) is not Decimal
            or not item.reserved_upper_bound_usd.is_finite()
            or item.reserved_upper_bound_usd <= 0
            or type(item.attempt_id) is not str
            or _SAFE_ATTEMPT_ID.fullmatch(item.attempt_id) is None
            or type(item.provider) is not str
            or _SAFE_IDENTITY.fullmatch(item.provider) is None
            or type(item.candidate_id) is not str
            or _SAFE_IDENTITY.fullmatch(item.candidate_id) is None
            or type(item.model) is not str
            or _SAFE_IDENTITY.fullmatch(item.model) is None
            or item.outcome not in _OUTCOMES
            or item.billing_state != _PENDING_BILLING_STATE
            or item.pending_state_reference != _pending_state_reference(item)
        ):
            raise _fail("ledger")
    for item in ledger.reconciliations:
        if (
            type(item) is not CostReconciliationRecord
            or type(item.reserved_upper_bound_usd) is not Decimal
            or type(item.actual_cost_usd) is not Decimal
            or type(item.released_reservation_usd) is not Decimal
            or not item.reserved_upper_bound_usd.is_finite()
            or not item.actual_cost_usd.is_finite()
            or not item.released_reservation_usd.is_finite()
            or item.reserved_upper_bound_usd <= 0
            or item.actual_cost_usd < 0
            or item.actual_cost_usd > item.reserved_upper_bound_usd
            or item.released_reservation_usd
            != item.reserved_upper_bound_usd - item.actual_cost_usd
            or _SAFE_ATTEMPT_ID.fullmatch(item.reconciliation_id) is None
            or _SAFE_ATTEMPT_ID.fullmatch(item.attempt_id) is None
            or _SAFE_IDENTITY.fullmatch(item.provider) is None
            or _SAFE_IDENTITY.fullmatch(item.candidate_id) is None
            or _SAFE_IDENTITY.fullmatch(item.model) is None
            or item.authoritative_evidence_type not in _AUTHORITATIVE_EVIDENCE_TYPES
            or _SHA256.fullmatch(item.authoritative_evidence_reference) is None
            or _valid_utc_timestamp(item.reconciled_at) is False
            or item.pricing_snapshot_id != _PRICING_SNAPSHOT_ID
            or item.pricing_snapshot_hash != _PRICING_SNAPSHOT_HASH
            or item.reconciliation_policy_id != _RECONCILIATION_POLICY_ID
            or item.reconciliation_policy_version != _RECONCILIATION_POLICY_VERSION
            or item.reconciliation_policy_hash != _RECONCILIATION_POLICY_HASH
            or _SHA256.fullmatch(item.prior_pending_state_reference) is None
            or item.reconciliation_record_hash != _reconciliation_record_hash(item)
        ):
            raise _fail("ledger")
    ids = [item.attempt_id for item in ledger.active_reservations]
    if len(ids) != len(set(ids)):
        raise _fail("ledger")
    completed_ids = [item.attempt_id for item in ledger.completed_attempts]
    pending_ids = [item.attempt_id for item in ledger.pending_attempts]
    reconciliation_ids = [item.reconciliation_id for item in ledger.reconciliations]
    reconciled_attempt_ids = [item.attempt_id for item in ledger.reconciliations]
    if (
        len(completed_ids) != len(set(completed_ids))
        or len(pending_ids) != len(set(pending_ids))
        or len(reconciliation_ids) != len(set(reconciliation_ids))
        or len(reconciled_attempt_ids) != len(set(reconciled_attempt_ids))
        or set(ids) & (set(completed_ids) | set(pending_ids))
        or (set(completed_ids) & set(pending_ids)) != set(reconciled_attempt_ids)
    ):
        raise _fail("ledger")
    pending_by_id = {item.attempt_id: item for item in ledger.pending_attempts}
    completed_by_id = {item.attempt_id: item for item in ledger.completed_attempts}
    for record in ledger.reconciliations:
        pending = pending_by_id.get(record.attempt_id)
        completed = completed_by_id.get(record.attempt_id)
        if (
            pending is None
            or completed is None
            or record.provider != pending.provider
            or record.candidate_id != pending.candidate_id
            or record.model != pending.model
            or record.reserved_upper_bound_usd != pending.reserved_upper_bound_usd
            or record.prior_pending_state_reference != pending.pending_state_reference
            or completed.reserved_upper_bound_usd != record.reserved_upper_bound_usd
            or completed.actual_cost_usd != record.actual_cost_usd
            or completed.outcome != pending.outcome
        ):
            raise _fail("ledger")
    unresolved_count = len(ledger.unresolved_pending_attempts)
    if unresolved_count > 1:
        raise _fail("multiple_pending_cost_reconciliation")
    if ledger.committed_cost_usd + ledger.total_encumbered_cost_usd > _CEILING:
        raise _fail("ledger")
    return ledger


def reserve_provider_attempt(
    ledger: PilotBudgetLedger,
    *,
    attempt_id: Any,
    conservative_upper_bound_usd: Any,
) -> PilotBudgetLedger:
    """Admit one future physical attempt only when its maximum fits."""
    ledger = _validated_ledger(ledger)
    assert_no_pending_cost_reconciliation(ledger)
    safe_attempt_id = _attempt_id(attempt_id)
    bound = _money(
        "conservative_upper_bound_usd",
        conservative_upper_bound_usd,
        positive=True,
    )
    known_ids = {
        item.attempt_id
        for item in (
            *ledger.active_reservations,
            *ledger.completed_attempts,
            *ledger.pending_attempts,
        )
    }
    if safe_attempt_id in known_ids:
        raise _fail("attempt_id_not_unique")
    if ledger.committed_cost_usd + ledger.total_encumbered_cost_usd + bound > _CEILING:
        raise _fail("pilot_budget_ceiling_exhausted")
    return PilotBudgetLedger(
        active_reservations=(
            *ledger.active_reservations,
            ActiveAttemptReservation(safe_attempt_id, bound),
        ),
        completed_attempts=ledger.completed_attempts,
        pending_attempts=ledger.pending_attempts,
        reconciliations=ledger.reconciliations,
    )


def commit_provider_attempt_cost(
    ledger: PilotBudgetLedger,
    *,
    attempt_id: Any,
    actual_cost_usd: Any,
    outcome: Any,
) -> PilotBudgetLedger:
    """Preserve the exact cost of one completed physical provider attempt."""
    ledger = _validated_ledger(ledger)
    safe_attempt_id = _attempt_id(attempt_id)
    actual = _money("actual_cost_usd", actual_cost_usd, positive=False)
    if type(outcome) is not str or outcome not in _OUTCOMES:
        raise _fail("attempt_outcome")
    matches = tuple(
        item for item in ledger.active_reservations if item.attempt_id == safe_attempt_id
    )
    if len(matches) != 1:
        raise _fail("attempt_not_reserved")
    reservation = matches[0]
    if actual > reservation.conservative_upper_bound_usd:
        raise _fail("actual_cost_exceeds_reservation")
    return PilotBudgetLedger(
        active_reservations=tuple(
            item
            for item in ledger.active_reservations
            if item.attempt_id != safe_attempt_id
        ),
        completed_attempts=(
            *ledger.completed_attempts,
            CompletedAttemptCost(
                attempt_id=safe_attempt_id,
                reserved_upper_bound_usd=reservation.conservative_upper_bound_usd,
                actual_cost_usd=actual,
                outcome=outcome,
            ),
        ),
        pending_attempts=ledger.pending_attempts,
        reconciliations=ledger.reconciliations,
    )


def _identity(name: str, value: Any) -> str:
    if type(value) is not str or _SAFE_IDENTITY.fullmatch(value) is None:
        raise _fail(name)
    return value


def _pending_state_reference(item: PendingAttemptCost) -> str:
    document = {
        "attempt_id": item.attempt_id,
        "billing_state": item.billing_state,
        "candidate_id": item.candidate_id,
        "model": item.model,
        "outcome": item.outcome,
        "provider": item.provider,
        "reserved_upper_bound_usd": str(item.reserved_upper_bound_usd),
    }
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _reconciliation_record_hash(item: CostReconciliationRecord) -> str:
    document = {
        name: (str(value) if isinstance(value, Decimal) else value)
        for name, value in (
            ("actual_cost_usd", item.actual_cost_usd),
            ("attempt_id", item.attempt_id),
            ("authoritative_evidence_reference", item.authoritative_evidence_reference),
            ("authoritative_evidence_type", item.authoritative_evidence_type),
            ("candidate_id", item.candidate_id),
            ("model", item.model),
            ("pricing_snapshot_hash", item.pricing_snapshot_hash),
            ("pricing_snapshot_id", item.pricing_snapshot_id),
            ("prior_pending_state_reference", item.prior_pending_state_reference),
            ("provider", item.provider),
            ("reconciled_at", item.reconciled_at),
            ("reconciliation_id", item.reconciliation_id),
            ("reconciliation_policy_hash", item.reconciliation_policy_hash),
            ("reconciliation_policy_id", item.reconciliation_policy_id),
            ("reconciliation_policy_version", item.reconciliation_policy_version),
            ("released_reservation_usd", item.released_reservation_usd),
            ("reserved_upper_bound_usd", item.reserved_upper_bound_usd),
        )
    }
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def assert_no_pending_cost_reconciliation(
    ledger: PilotBudgetLedger,
) -> PilotBudgetLedger:
    """Fail closed before any further live operation while cost is unresolved."""
    ledger = _validated_ledger(ledger)
    if ledger.unresolved_pending_attempts:
        raise _fail(_PENDING_BILLING_STATE)
    return ledger


def mark_attempt_pending_reconciliation(
    ledger: PilotBudgetLedger,
    *,
    attempt_id: Any,
    provider: Any,
    candidate_id: Any,
    model: Any,
    outcome: Any,
) -> PilotBudgetLedger:
    """Preserve an invoked attempt with unknown exact cost and encumber full R."""
    ledger = _validated_ledger(ledger)
    assert_no_pending_cost_reconciliation(ledger)
    safe_attempt_id = _attempt_id(attempt_id)
    if type(outcome) is not str or outcome not in _OUTCOMES:
        raise _fail("attempt_outcome")
    matches = tuple(
        item for item in ledger.active_reservations if item.attempt_id == safe_attempt_id
    )
    if len(matches) != 1:
        raise _fail("attempt_not_reserved")
    reservation = matches[0]
    unreferenced = PendingAttemptCost(
        attempt_id=safe_attempt_id,
        provider=_identity("provider", provider),
        candidate_id=_identity("candidate_id", candidate_id),
        model=_identity("model", model),
        reserved_upper_bound_usd=reservation.conservative_upper_bound_usd,
        outcome=outcome,
        billing_state=_PENDING_BILLING_STATE,
        pending_state_reference="",
    )
    pending = PendingAttemptCost(
        attempt_id=unreferenced.attempt_id,
        provider=unreferenced.provider,
        candidate_id=unreferenced.candidate_id,
        model=unreferenced.model,
        reserved_upper_bound_usd=unreferenced.reserved_upper_bound_usd,
        outcome=unreferenced.outcome,
        billing_state=unreferenced.billing_state,
        pending_state_reference=_pending_state_reference(unreferenced),
    )
    return _validated_ledger(
        PilotBudgetLedger(
            active_reservations=tuple(
                item
                for item in ledger.active_reservations
                if item.attempt_id != safe_attempt_id
            ),
            completed_attempts=ledger.completed_attempts,
            pending_attempts=(*ledger.pending_attempts, pending),
            reconciliations=ledger.reconciliations,
        )
    )


def reconcile_pending_attempt_cost(
    ledger: PilotBudgetLedger,
    *,
    reconciliation_id: Any,
    attempt_id: Any,
    actual_cost_usd: Any,
    authoritative_evidence_type: Any,
    authoritative_evidence_reference: Any,
    reconciled_at: Any,
) -> PilotBudgetLedger:
    """Append exact authoritative reconciliation without mutating pending history."""
    ledger = _validated_ledger(ledger)
    safe_attempt_id = _attempt_id(attempt_id)
    safe_reconciliation_id = _attempt_id(reconciliation_id)
    if any(
        item.reconciliation_id == safe_reconciliation_id
        for item in ledger.reconciliations
    ):
        raise _fail("reconciliation_id_not_unique")
    pending_matches = tuple(
        item
        for item in ledger.unresolved_pending_attempts
        if item.attempt_id == safe_attempt_id
    )
    if len(pending_matches) != 1:
        raise _fail("pending_attempt_not_found")
    pending = pending_matches[0]
    actual = _money("actual_cost_usd", actual_cost_usd, positive=False)
    if actual > pending.reserved_upper_bound_usd:
        raise _fail("actual_cost_exceeds_reservation")
    if (
        type(authoritative_evidence_type) is not str
        or authoritative_evidence_type not in _AUTHORITATIVE_EVIDENCE_TYPES
        or type(authoritative_evidence_reference) is not str
        or _SHA256.fullmatch(authoritative_evidence_reference) is None
    ):
        raise _fail("authoritative_cost_evidence")
    safe_reconciled_at = _utc_timestamp(reconciled_at)
    unreferenced = CostReconciliationRecord(
        reconciliation_id=safe_reconciliation_id,
        attempt_id=safe_attempt_id,
        provider=pending.provider,
        candidate_id=pending.candidate_id,
        model=pending.model,
        reserved_upper_bound_usd=pending.reserved_upper_bound_usd,
        actual_cost_usd=actual,
        released_reservation_usd=pending.reserved_upper_bound_usd - actual,
        authoritative_evidence_type=authoritative_evidence_type,
        authoritative_evidence_reference=authoritative_evidence_reference,
        reconciled_at=safe_reconciled_at,
        pricing_snapshot_id=_PRICING_SNAPSHOT_ID,
        pricing_snapshot_hash=_PRICING_SNAPSHOT_HASH,
        reconciliation_policy_id=_RECONCILIATION_POLICY_ID,
        reconciliation_policy_version=_RECONCILIATION_POLICY_VERSION,
        reconciliation_policy_hash=_RECONCILIATION_POLICY_HASH,
        prior_pending_state_reference=pending.pending_state_reference,
        reconciliation_record_hash="",
    )
    record = CostReconciliationRecord(
        **{
            name: getattr(unreferenced, name)
            for name in CostReconciliationRecord.__slots__
            if name != "reconciliation_record_hash"
        },
        reconciliation_record_hash=_reconciliation_record_hash(unreferenced),
    )
    return _validated_ledger(
        PilotBudgetLedger(
            active_reservations=ledger.active_reservations,
            completed_attempts=(
                *ledger.completed_attempts,
                CompletedAttemptCost(
                    attempt_id=safe_attempt_id,
                    reserved_upper_bound_usd=pending.reserved_upper_bound_usd,
                    actual_cost_usd=actual,
                    outcome=pending.outcome,
                ),
            ),
            pending_attempts=ledger.pending_attempts,
            reconciliations=(*ledger.reconciliations, record),
        )
    )


def pilot_budget_ledger_to_json(ledger: PilotBudgetLedger) -> bytes:
    """Serialize only the closed safe immutable ledger projection."""
    ledger = _validated_ledger(ledger)
    value = {
        "active_reservations": [
            {
                "attempt_id": item.attempt_id,
                "conservative_upper_bound_usd": str(
                    item.conservative_upper_bound_usd
                ),
            }
            for item in ledger.active_reservations
        ],
        "approved_ceiling_usd": str(ledger.approved_ceiling_usd),
        "completed_attempts": [
            {
                "actual_cost_usd": str(item.actual_cost_usd),
                "attempt_id": item.attempt_id,
                "outcome": item.outcome,
                "reserved_upper_bound_usd": str(item.reserved_upper_bound_usd),
            }
            for item in ledger.completed_attempts
        ],
        "ledger_version": "v2",
        "pending_attempts": [
            {
                "attempt_id": item.attempt_id,
                "billing_state": item.billing_state,
                "candidate_id": item.candidate_id,
                "model": item.model,
                "outcome": item.outcome,
                "pending_state_reference": item.pending_state_reference,
                "provider": item.provider,
                "reserved_upper_bound_usd": str(item.reserved_upper_bound_usd),
            }
            for item in ledger.pending_attempts
        ],
        "reconciliations": [
            {
                name: (str(value) if isinstance(value, Decimal) else value)
                for name in CostReconciliationRecord.__slots__
                for value in (getattr(item, name),)
            }
            for item in ledger.reconciliations
        ],
    }
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _strict_json_object(payload: bytes) -> dict[str, Any]:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise _fail("ledger_json_duplicate_key")
            value[key] = item
        return value

    def invalid_constant(_: str) -> None:
        raise _fail("ledger_json_number")

    if type(payload) is not bytes:
        raise _fail("ledger_json")
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs_hook,
            parse_constant=invalid_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail("ledger_json") from exc
    if type(value) is not dict:
        raise _fail("ledger_json")
    return value


def _exact_keys(value: Any, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise _fail("ledger_json_shape")
    return value


def pilot_budget_ledger_from_json(payload: bytes) -> PilotBudgetLedger:
    """Load the safe ledger projection and validate every identity/hash."""
    value = _exact_keys(
        _strict_json_object(payload),
        {
            "active_reservations",
            "approved_ceiling_usd",
            "completed_attempts",
            "ledger_version",
            "pending_attempts",
            "reconciliations",
        },
    )
    if value["ledger_version"] != "v2":
        raise _fail("ledger_json_shape")
    approved = _money(
        "approved_ceiling_usd",
        value["approved_ceiling_usd"],
        positive=True,
    )
    if approved != _CEILING:
        raise _fail("ledger_json_shape")
    if any(type(value[name]) is not list for name in (
        "active_reservations", "completed_attempts", "pending_attempts", "reconciliations"
    )):
        raise _fail("ledger_json_shape")
    active = tuple(
        ActiveAttemptReservation(
            _attempt_id(item["attempt_id"]),
            _money(
                "conservative_upper_bound_usd",
                item["conservative_upper_bound_usd"],
                positive=True,
            ),
        )
        for raw in value["active_reservations"]
        for item in (
            _exact_keys(raw, {"attempt_id", "conservative_upper_bound_usd"}),
        )
    )
    completed = tuple(
        CompletedAttemptCost(
            _attempt_id(item["attempt_id"]),
            _money(
                "reserved_upper_bound_usd",
                item["reserved_upper_bound_usd"],
                positive=True,
            ),
            _money("actual_cost_usd", item["actual_cost_usd"], positive=False),
            item["outcome"],
        )
        for raw in value["completed_attempts"]
        for item in (
            _exact_keys(
                raw,
                {
                    "actual_cost_usd",
                    "attempt_id",
                    "outcome",
                    "reserved_upper_bound_usd",
                },
            ),
        )
    )
    pending = tuple(
        PendingAttemptCost(
            attempt_id=item["attempt_id"],
            provider=item["provider"],
            candidate_id=item["candidate_id"],
            model=item["model"],
            reserved_upper_bound_usd=_money(
                "reserved_upper_bound_usd",
                item["reserved_upper_bound_usd"],
                positive=True,
            ),
            outcome=item["outcome"],
            billing_state=item["billing_state"],
            pending_state_reference=item["pending_state_reference"],
        )
        for raw in value["pending_attempts"]
        for item in (
            _exact_keys(
                raw,
                {
                    "attempt_id",
                    "billing_state",
                    "candidate_id",
                    "model",
                    "outcome",
                    "pending_state_reference",
                    "provider",
                    "reserved_upper_bound_usd",
                },
            ),
        )
    )
    reconciliation_keys = set(CostReconciliationRecord.__slots__)
    reconciliations = tuple(
        CostReconciliationRecord(
            **{
                **item,
                "reserved_upper_bound_usd": _money(
                    "reserved_upper_bound_usd",
                    item["reserved_upper_bound_usd"],
                    positive=True,
                ),
                "actual_cost_usd": _money(
                    "actual_cost_usd", item["actual_cost_usd"], positive=False
                ),
                "released_reservation_usd": _money(
                    "released_reservation_usd",
                    item["released_reservation_usd"],
                    positive=False,
                ),
            }
        )
        for raw in value["reconciliations"]
        for item in (_exact_keys(raw, reconciliation_keys),)
    )
    return _validated_ledger(
        PilotBudgetLedger(
            approved_ceiling_usd=approved,
            active_reservations=active,
            completed_attempts=completed,
            pending_attempts=pending,
            reconciliations=reconciliations,
        )
    )
