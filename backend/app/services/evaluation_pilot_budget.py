"""Exact provider-free enforcement of the approved pilot spending ceiling.

The reservation ledger is immutable and application-owned.  It does not
inspect billing accounts, access credentials, invoke providers, or authorize
execution.  A caller must supply a conservative upper bound before an attempt
can be admitted; an absent or unbounded estimate fails before invocation.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    _ROOT / "docs" / "testing" / "ai-evaluation" / "pilot-budget-control.v1.json"
)
_EXPECTED_HASH = "2a6d8fdfdd39efcf8ddc027734988a557d222885f736ddc60d8162dd059b7b23"
_EXPECTED_COST_ENVELOPE_HASH = (
    "40899a9b6a8b94928bb52947da1f040699cbee7f7f13be0902c17a7db25b2942"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ATTEMPT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+@\-]{0,255}\Z")
_MONEY = re.compile(r"(?:0|[1-9][0-9]*)\.[0-9]{2,8}\Z")
_OUTCOMES = frozenset({"succeeded", "failed_retryable", "failed_nonretryable"})
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
class PilotBudgetLedger:
    approved_ceiling_usd: Decimal = _CEILING
    active_reservations: tuple[ActiveAttemptReservation, ...] = ()
    completed_attempts: tuple[CompletedAttemptCost, ...] = ()

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
    def remaining_unreserved_usd(self) -> Decimal:
        return self.approved_ceiling_usd - self.committed_cost_usd - self.reserved_cost_usd

    @property
    def provider_calls_completed(self) -> int:
        return len(self.completed_attempts)

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
        or raw.get("artifact_id") != "pilot_budget_control_v1"
        or raw.get("artifact_version") != "v1"
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
    ):
        raise _fail("pre_attempt_reservation")
    boundary = raw.get("execution_boundary")
    if boundary != {
        "authoritative_execution_gate": "experiment.v1.json execution_gate",
        "execution_state": "blocked_pre_execution",
        "provider_calls_allowed": False,
        "pilot_calls_allowed": False,
        "scored_calls_allowed": False,
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
    ids = [item.attempt_id for item in ledger.active_reservations]
    ids.extend(item.attempt_id for item in ledger.completed_attempts)
    if len(ids) != len(set(ids)):
        raise _fail("ledger")
    if ledger.committed_cost_usd + ledger.reserved_cost_usd > _CEILING:
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
    safe_attempt_id = _attempt_id(attempt_id)
    bound = _money(
        "conservative_upper_bound_usd",
        conservative_upper_bound_usd,
        positive=True,
    )
    known_ids = {
        item.attempt_id
        for item in (*ledger.active_reservations, *ledger.completed_attempts)
    }
    if safe_attempt_id in known_ids:
        raise _fail("attempt_id_not_unique")
    if ledger.committed_cost_usd + ledger.reserved_cost_usd + bound > _CEILING:
        raise _fail("pilot_budget_ceiling_exhausted")
    return PilotBudgetLedger(
        active_reservations=(
            *ledger.active_reservations,
            ActiveAttemptReservation(safe_attempt_id, bound),
        ),
        completed_attempts=ledger.completed_attempts,
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
    )
