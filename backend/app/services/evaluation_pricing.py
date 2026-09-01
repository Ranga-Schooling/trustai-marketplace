"""Exact provider-neutral evaluation pricing calculation.

The pricing snapshot is dated evidence, not execution authority.  This module
accepts only complete frozen schedules and explicit provider-billing units; it
does not infer usage, select a provider configuration, access billing state, or
perform network requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from app.services.evaluation_contract_identity import load_strict_contract_json


_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SNAPSHOT = (
    _ROOT / "docs" / "testing" / "ai-evaluation" / "pricing-snapshot.v1.json"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+@\-]{0,255}\Z")
_TOP_LEVEL_KEYS = {
    "artifact_id",
    "artifact_version",
    "status",
    "purpose",
    "provider_neutral",
    "currency",
    "observed_on",
    "source_protocol",
    "official_sources",
    "schedules",
    "candidate_bindings",
    "incomplete_official_facts",
    "calculation_contract",
    "execution_boundary",
    "provider_calls_completed",
    "winner_selected",
    "specification_identity",
}
_SOURCE_KEYS = {"source_id", "provider", "url", "observed_on", "facts_used"}
_SCHEDULE_KEYS = {
    "schedule_id",
    "provider",
    "model",
    "billing_mode",
    "context_regime",
    "complete",
    "source_ids",
    "rates",
    "billing_state_requirements",
    "missing_facts",
    "notes",
}
_RATE_KEYS = {"component", "unit", "usd_per_unit"}
_BINDING_KEYS = {
    "candidate_id",
    "workload_schedules",
    "selection_rule_status",
    "status",
    "blockers",
}
_ALLOWED_UNITS = {"token", "call", "query", "second"}
_EXPECTED_SNAPSHOT_HASH = (
    "0467643eafbe55e6e2215c9ad0e0576dac2d0d157a94418eef23382b0ec09282"
)
_SNAPSHOT_TOKEN = object()
_ESTIMATED_COST_KEYS = {
    "pricing_snapshot_id",
    "pricing_snapshot_version",
    "pricing_snapshot_hash",
    "pricing_observed_on",
    "schedule_id",
    "provider",
    "model",
    "billing_mode",
    "context_regime",
    "currency",
    "usage",
    "component_costs",
    "total_usd",
    "calculation_id",
}


class PricingContractError(ValueError):
    """A pricing snapshot or calculation violated the frozen boundary."""


def _fail(code: str) -> PricingContractError:
    return PricingContractError(code)


@dataclass(frozen=True, slots=True)
class PricingSchedule:
    schedule_id: str
    provider: str
    model: str
    billing_mode: str
    context_regime: str
    complete: bool
    rates: tuple[tuple[str, Decimal], ...]
    source_ids: tuple[str, ...]
    missing_facts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PricingSnapshot:
    artifact_id: str
    artifact_version: str
    status: str
    currency: str
    observed_on: str
    semantic_hash: str
    schedules: tuple[PricingSchedule, ...]
    provider_calls_allowed: bool
    pilot_calls_allowed: bool
    scored_calls_allowed: bool
    provider_calls_completed: int
    winner_selected: bool
    _token: object | None = None

    def __post_init__(self) -> None:
        if self._token is not _SNAPSHOT_TOKEN:
            raise _fail("pricing_snapshot_factory_required")


@dataclass(frozen=True, slots=True)
class EstimatedCostRecord:
    pricing_snapshot_id: str
    pricing_snapshot_version: str
    pricing_snapshot_hash: str
    pricing_observed_on: str
    schedule_id: str
    provider: str
    model: str
    billing_mode: str
    context_regime: str
    currency: str
    usage: tuple[tuple[str, int], ...]
    component_costs: tuple[tuple[str, str], ...]
    total_usd: str
    calculation_id: str = "exact_decimal_cost_calculation_v1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "pricing_snapshot_id": self.pricing_snapshot_id,
            "pricing_snapshot_version": self.pricing_snapshot_version,
            "pricing_snapshot_hash": self.pricing_snapshot_hash,
            "pricing_observed_on": self.pricing_observed_on,
            "schedule_id": self.schedule_id,
            "provider": self.provider,
            "model": self.model,
            "billing_mode": self.billing_mode,
            "context_regime": self.context_regime,
            "currency": self.currency,
            "usage": dict(self.usage),
            "component_costs": dict(self.component_costs),
            "total_usd": self.total_usd,
            "calculation_id": self.calculation_id,
        }


def _identifier(name: str, value: Any) -> str:
    if type(value) is not str or _SAFE_ID.fullmatch(value) is None:
        raise _fail(f"pricing_identifier:{name}")
    return value


def _label(name: str, value: Any) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > 128
        or not value.isascii()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise _fail(f"pricing_label:{name}")
    return value


def _exact_keys(name: str, value: Any, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise _fail(f"pricing_fields:{name}")
    return value


def _canonical_without_identity(raw: dict[str, Any]) -> bytes:
    detached = json.loads(json.dumps(raw))
    detached["specification_identity"]["semantic_hash"] = None
    return json.dumps(
        detached,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _decimal_rate(value: Any) -> Decimal:
    if type(value) is not str:
        raise _fail("pricing_rate_type")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise _fail("pricing_rate_value") from None
    if not result.is_finite() or result <= 0 or format(result, "f") != value:
        raise _fail("pricing_rate_value")
    return result


def _validate_source(raw: Any, observed_on: str) -> str:
    source = _exact_keys("official_source", raw, _SOURCE_KEYS)
    source_id = _identifier("source_id", source["source_id"])
    _label("source_provider", source["provider"])
    if (
        type(source["url"]) is not str
        or not source["url"].startswith("https://")
        or source["observed_on"] != observed_on
        or type(source["facts_used"]) is not list
        or not source["facts_used"]
        or any(type(item) is not str or not item for item in source["facts_used"])
    ):
        raise _fail("pricing_official_source")
    return source_id


def _validate_schedule(raw: Any, source_ids: set[str]) -> PricingSchedule:
    schedule = _exact_keys("schedule", raw, _SCHEDULE_KEYS)
    schedule_id = _identifier("schedule_id", schedule["schedule_id"])
    provider = _label("provider", schedule["provider"])
    model = _identifier("model", schedule["model"])
    billing_mode = _identifier("billing_mode", schedule["billing_mode"])
    context_regime = _identifier("context_regime", schedule["context_regime"])
    if type(schedule["complete"]) is not bool:
        raise _fail("pricing_schedule_complete_type")
    if (
        type(schedule["source_ids"]) is not list
        or not schedule["source_ids"]
        or any(item not in source_ids for item in schedule["source_ids"])
    ):
        raise _fail("pricing_schedule_source")
    if type(schedule["rates"]) is not list or not schedule["rates"]:
        raise _fail("pricing_schedule_rates")
    rates: list[tuple[str, Decimal]] = []
    for item in schedule["rates"]:
        rate = _exact_keys("rate", item, _RATE_KEYS)
        component = _identifier("rate_component", rate["component"])
        if rate["unit"] not in _ALLOWED_UNITS:
            raise _fail("pricing_rate_unit")
        rates.append((component, _decimal_rate(rate["usd_per_unit"])))
    if len({component for component, _ in rates}) != len(rates):
        raise _fail("pricing_rate_duplicate")
    if (
        type(schedule["billing_state_requirements"]) is not list
        or any(
            type(item) is not str or not item
            for item in schedule["billing_state_requirements"]
        )
        or type(schedule["missing_facts"]) is not list
        or any(type(item) is not str or not item for item in schedule["missing_facts"])
        or type(schedule["notes"]) is not list
        or any(type(item) is not str or not item for item in schedule["notes"])
    ):
        raise _fail("pricing_schedule_metadata")
    if schedule["complete"] and schedule["missing_facts"]:
        raise _fail("pricing_complete_with_missing_facts")
    if not schedule["complete"] and not schedule["missing_facts"]:
        raise _fail("pricing_incomplete_without_missing_facts")
    return PricingSchedule(
        schedule_id=schedule_id,
        provider=provider,
        model=model,
        billing_mode=billing_mode,
        context_regime=context_regime,
        complete=schedule["complete"],
        rates=tuple(rates),
        source_ids=tuple(schedule["source_ids"]),
        missing_facts=tuple(schedule["missing_facts"]),
    )


def verify_pricing_snapshot(
    path: str | Path = _DEFAULT_SNAPSHOT,
) -> PricingSnapshot:
    """Load and verify the dated pricing snapshot and its semantic identity."""
    try:
        raw = load_strict_contract_json(Path(path))
    except (OSError, TypeError, ValueError) as exc:
        raise _fail("pricing_snapshot_parse") from exc
    raw = _exact_keys("snapshot", raw, _TOP_LEVEL_KEYS)
    if (
        raw["artifact_id"] != "pricing_snapshot_v1"
        or raw["artifact_version"] != "v1"
        or raw["status"] != "blocked_incomplete_candidate_binding"
        or raw["provider_neutral"] is not True
        or raw["currency"] != "USD"
        or raw["observed_on"] != "2026-08-31"
    ):
        raise _fail("pricing_snapshot_header")
    identity = _exact_keys(
        "specification_identity",
        raw["specification_identity"],
        {"hash_algorithm", "hash_input", "semantic_hash"},
    )
    if (
        identity["hash_algorithm"] != "SHA-256"
        or identity["hash_input"]
        != "canonical_compact_utf8_json_with_semantic_hash_replaced_by_null"
        or type(identity["semantic_hash"]) is not str
        or _SHA256.fullmatch(identity["semantic_hash"]) is None
    ):
        raise _fail("pricing_snapshot_identity")
    expected_hash = hashlib.sha256(_canonical_without_identity(raw)).hexdigest()
    if (
        identity["semantic_hash"] != expected_hash
        or identity["semantic_hash"] != _EXPECTED_SNAPSHOT_HASH
    ):
        raise _fail("pricing_snapshot_identity")

    if type(raw["official_sources"]) is not list or not raw["official_sources"]:
        raise _fail("pricing_official_sources")
    source_ids = tuple(
        _validate_source(item, raw["observed_on"])
        for item in raw["official_sources"]
    )
    if len(set(source_ids)) != len(source_ids):
        raise _fail("pricing_source_duplicate")

    if type(raw["schedules"]) is not list or not raw["schedules"]:
        raise _fail("pricing_schedules")
    schedules = tuple(
        _validate_schedule(item, set(source_ids)) for item in raw["schedules"]
    )
    if len({item.schedule_id for item in schedules}) != len(schedules):
        raise _fail("pricing_schedule_duplicate")

    if type(raw["candidate_bindings"]) is not list:
        raise _fail("pricing_candidate_bindings")
    known_schedules = {item.schedule_id for item in schedules}
    candidate_ids: list[str] = []
    for item in raw["candidate_bindings"]:
        binding = _exact_keys("candidate_binding", item, _BINDING_KEYS)
        candidate_ids.append(_identifier("candidate_id", binding["candidate_id"]))
        if (
            type(binding["workload_schedules"]) is not dict
            or any(
                type(value) is not list
                or any(schedule_id not in known_schedules for schedule_id in value)
                for value in binding["workload_schedules"].values()
            )
            or type(binding["selection_rule_status"]) is not str
            or not binding["selection_rule_status"].startswith("blocked_")
            or type(binding["status"]) is not str
            or not binding["status"].startswith("blocked_")
            or type(binding["blockers"]) is not list
            or not binding["blockers"]
        ):
            raise _fail("pricing_candidate_binding")
    if len(set(candidate_ids)) != len(candidate_ids):
        raise _fail("pricing_candidate_duplicate")

    boundary = _exact_keys(
        "execution_boundary",
        raw["execution_boundary"],
        {
            "authoritative_execution_gate",
            "execution_state",
            "provider_calls_allowed",
            "pilot_calls_allowed",
            "scored_calls_allowed",
            "this_artifact_independently_authorizes_execution",
        },
    )
    if (
        boundary["execution_state"] != "blocked_pre_execution"
        or boundary["provider_calls_allowed"] is not False
        or boundary["pilot_calls_allowed"] is not False
        or boundary["scored_calls_allowed"] is not False
        or boundary["this_artifact_independently_authorizes_execution"] is not False
        or raw["provider_calls_completed"] != 0
        or raw["winner_selected"] is not False
    ):
        raise _fail("pricing_execution_boundary")

    return PricingSnapshot(
        artifact_id=raw["artifact_id"],
        artifact_version=raw["artifact_version"],
        status=raw["status"],
        currency=raw["currency"],
        observed_on=raw["observed_on"],
        semantic_hash=identity["semantic_hash"],
        schedules=schedules,
        provider_calls_allowed=boundary["provider_calls_allowed"],
        pilot_calls_allowed=boundary["pilot_calls_allowed"],
        scored_calls_allowed=boundary["scored_calls_allowed"],
        provider_calls_completed=raw["provider_calls_completed"],
        winner_selected=raw["winner_selected"],
        _token=_SNAPSHOT_TOKEN,
    )


def _render_decimal(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def calculate_estimated_cost(
    snapshot: PricingSnapshot,
    *,
    schedule_id: str,
    usage: Mapping[str, Any],
) -> EstimatedCostRecord:
    """Calculate exact USD cost from explicit chargeable provider units."""
    if not isinstance(snapshot, PricingSnapshot):
        raise _fail("pricing_snapshot_required")
    if type(schedule_id) is not str:
        raise _fail("pricing_schedule_id")
    matching = tuple(
        item for item in snapshot.schedules if item.schedule_id == schedule_id
    )
    if len(matching) != 1:
        raise _fail("pricing_schedule_unknown")
    schedule = matching[0]
    if not schedule.complete:
        raise _fail("pricing_schedule_incomplete")
    if type(usage) is not dict:
        raise _fail("usage_container_type")
    components = tuple(component for component, _ in schedule.rates)
    if set(usage) != set(components) or len(usage) != len(components):
        raise _fail("usage_component_set")

    validated_units: list[tuple[str, int, Decimal]] = []
    for component, rate in schedule.rates:
        units = usage[component]
        if type(units) is not int:
            raise _fail(f"usage_unit_type:{component}")
        if units < 0:
            raise _fail(f"usage_unit_negative:{component}")
        validated_units.append((component, units, rate))

    precision = max(
        50,
        max(
            len(str(units)) + len(rate.as_tuple().digits) + 20
            for _, units, rate in validated_units
        ),
    )
    ordered_usage: list[tuple[str, int]] = []
    component_costs: list[tuple[str, str]] = []
    with localcontext() as context:
        context.prec = precision
        total = Decimal(0)
        for component, units, rate in validated_units:
            amount = rate * units
            ordered_usage.append((component, units))
            component_costs.append((component, _render_decimal(amount)))
            total += amount
        total_usd = _render_decimal(total)

    return EstimatedCostRecord(
        pricing_snapshot_id=snapshot.artifact_id,
        pricing_snapshot_version=snapshot.artifact_version,
        pricing_snapshot_hash=snapshot.semantic_hash,
        pricing_observed_on=snapshot.observed_on,
        schedule_id=schedule.schedule_id,
        provider=schedule.provider,
        model=schedule.model,
        billing_mode=schedule.billing_mode,
        context_regime=schedule.context_regime,
        currency=snapshot.currency,
        usage=tuple(ordered_usage),
        component_costs=tuple(component_costs),
        total_usd=total_usd,
    )


def verify_estimated_cost_record(
    value: Any,
    *,
    snapshot: PricingSnapshot | None = None,
) -> EstimatedCostRecord:
    """Recompute one ordinary estimated-cost record from its frozen schedule."""
    record = _exact_keys("estimated_cost_record", value, _ESTIMATED_COST_KEYS)
    snapshot = snapshot or verify_pricing_snapshot()
    if not isinstance(snapshot, PricingSnapshot):
        raise _fail("pricing_snapshot_required")
    if (
        record["pricing_snapshot_id"] != snapshot.artifact_id
        or record["pricing_snapshot_version"] != snapshot.artifact_version
        or record["pricing_snapshot_hash"] != snapshot.semantic_hash
        or record["pricing_observed_on"] != snapshot.observed_on
        or record["currency"] != snapshot.currency
        or record["calculation_id"] != "exact_decimal_cost_calculation_v1"
        or type(record["usage"]) is not dict
        or type(record["component_costs"]) is not dict
    ):
        raise _fail("estimated_cost_identity")
    expected = calculate_estimated_cost(
        snapshot,
        schedule_id=record["schedule_id"],
        usage=record["usage"],
    )
    if record != expected.as_dict():
        raise _fail("estimated_cost_recalculation")
    return expected
