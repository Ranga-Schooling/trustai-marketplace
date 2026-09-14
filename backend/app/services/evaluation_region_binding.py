"""Approved provider-neutral pilot operation and restricted-storage binding.

This module validates a frozen governance decision.  It performs no storage,
network, provider, credential, persistence, deletion, or execution operation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from app.services.evaluation_contract_identity import (
    ContractIdentityError,
    load_strict_contract_json,
)
from app.services.evaluation_data_handling import (
    verify_provider_data_handling_artifact,
)
from app.services.evaluation_search_tool_record import (
    verify_safe_search_tool_record_contract,
)


_ROOT = Path(__file__).resolve().parents[3]
_ARTIFACTS = _ROOT / "docs" / "testing" / "ai-evaluation"
_DEFAULT_CONTRACT = _ARTIFACTS / "pilot-region-binding.v1.json"
POLICY_HASH = "0c79df332d87bfdf1c902df26df9701bf531100f691650286eb7d5dd38627555"
_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_EXECUTION_BOUNDARY = {
    "execution_state": "blocked_pre_execution",
    "provider_calls_allowed": False,
    "pilot_calls_allowed": False,
    "scored_calls_allowed": False,
    "provider_calls_completed": 0,
    "pilot_calls_completed": 0,
    "scored_calls_completed": 0,
    "winner_selected": False,
    "this_artifact_independently_authorizes_execution": False,
}
_TOP_LEVEL_KEYS = {
    "artifact_id",
    "artifact_version",
    "status",
    "purpose",
    "provider_neutral",
    "source_contracts",
    "operation_binding",
    "storage_binding",
    "retention_binding",
    "validation",
    "execution_boundary",
    "specification_identity",
}


class RegionBindingError(ValueError):
    """The region contract or a proposed placement failed closed."""


def _fail(code: str) -> RegionBindingError:
    return RegionBindingError(code)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise _fail("region_binding_identity") from exc


def _semantic_hash(artifact: dict[str, Any]) -> str:
    detached = json.loads(_canonical_bytes(artifact).decode("utf-8"))
    try:
        detached["specification_identity"]["semantic_hash"] = None
    except (KeyError, TypeError) as exc:
        raise _fail("region_binding_identity") from exc
    return hashlib.sha256(_canonical_bytes(detached)).hexdigest()


@dataclass(frozen=True, slots=True)
class PilotRegionBinding:
    policy_id: str
    policy_version: str
    policy_hash: str
    operation_country_code: str
    provider_service_mode: str
    restricted_storage_country_code: str
    restricted_storage_topology: str
    cross_region_replication_allowed: bool
    restricted_retention_days: int
    retention_clock_starts_at: str
    cloud_infrastructure_required: bool
    provider_processing_location_asserted: bool
    provider_calls_allowed: bool = False
    pilot_calls_allowed: bool = False
    scored_calls_allowed: bool = False
    provider_calls_completed: int = 0
    pilot_calls_completed: int = 0
    scored_calls_completed: int = 0
    winner_selected: bool = False


def verify_pilot_region_binding(
    path: str | Path = _DEFAULT_CONTRACT,
) -> PilotRegionBinding:
    """Verify the exact approved region decision and its source contracts."""
    try:
        artifact = load_strict_contract_json(path)
        data_handling = load_strict_contract_json(
            _ARTIFACTS / "provider-data-handling-review.v1.json"
        )
        verify_provider_data_handling_artifact(
            _ARTIFACTS / "provider-data-handling-review.v1.json"
        )
        verify_safe_search_tool_record_contract(
            _ARTIFACTS / "safe-search-tool-record.v1.json"
        )
    except (ContractIdentityError, OSError, TypeError, ValueError) as exc:
        raise _fail("region_binding_source_contract") from exc
    identity = artifact.get("specification_identity", {})
    stored_hash = identity.get("semantic_hash")
    operation = artifact.get("operation_binding", {})
    storage = artifact.get("storage_binding", {})
    retention = artifact.get("retention_binding", {})
    validation = artifact.get("validation", {})
    if (
        set(artifact) != _TOP_LEVEL_KEYS
        or artifact.get("artifact_id") != "pilot_region_binding_v1"
        or artifact.get("artifact_version") != "v1"
        or artifact.get("status") != "frozen"
        or artifact.get("provider_neutral") is not True
        or identity.get("semantic_hash_excluded_json_pointers")
        != ["/specification_identity/semantic_hash"]
        or type(stored_hash) is not str
        or _LOWER_SHA256.fullmatch(stored_hash) is None
        or _semantic_hash(artifact) != stored_hash
        or stored_hash != POLICY_HASH
    ):
        raise _fail("region_binding_identity")
    if operation != {
        "operator_country_code": "US",
        "provider_service_mode": "standard_global",
        "provider_processing_location_asserted": False,
        "provider_processing_location_requirement": (
            "not_asserted_in_standard_global_mode"
        ),
        "provider_residency_guarantee_claimed": False,
    }:
        raise _fail("operation_binding")
    if storage != {
        "restricted_storage_country_code": "US",
        "restricted_storage_topology": "local_operator_controlled",
        "local_us_storage_allowed": True,
        "cloud_infrastructure_required": False,
        "cross_region_replication_allowed": False,
        "replication_country_code_allowlist": [],
        "restricted_evidence_must_remain_within_approved_storage_country": True,
        "ordinary_sanitized_records_are_outside_this_restricted_storage_binding": True,
    }:
        raise _fail("storage_binding")
    if retention != {
        "restricted_retention_days": 30,
        "retention_clock_starts_at": "final_model_selection_decision_at",
        "delete_as_one_lifecycle_group": True,
        "longer_independent_retention_allowed": False,
    } or data_handling.get("retention_policy", {}).get(
        "restricted_retention_days"
    ) != retention["restricted_retention_days"]:
        raise _fail("retention_binding")
    if (
        validation.get("unknown_or_unbound_storage_location_result")
        != "preflight_failure"
        or validation.get(
            "provider_processing_location_must_not_be_inferred_from_operator_or_storage_country"
        )
        is not True
        or artifact.get("execution_boundary") != _EXECUTION_BOUNDARY
    ):
        raise _fail("region_binding_boundary")
    return PilotRegionBinding(
        policy_id=artifact["artifact_id"],
        policy_version=artifact["artifact_version"],
        policy_hash=stored_hash,
        operation_country_code=operation["operator_country_code"],
        provider_service_mode=operation["provider_service_mode"],
        restricted_storage_country_code=storage[
            "restricted_storage_country_code"
        ],
        restricted_storage_topology=storage["restricted_storage_topology"],
        cross_region_replication_allowed=storage[
            "cross_region_replication_allowed"
        ],
        restricted_retention_days=retention["restricted_retention_days"],
        retention_clock_starts_at=retention["retention_clock_starts_at"],
        cloud_infrastructure_required=storage["cloud_infrastructure_required"],
        provider_processing_location_asserted=operation[
            "provider_processing_location_asserted"
        ],
    )


def validate_restricted_storage_placement(
    binding: PilotRegionBinding,
    *,
    storage_country_code: Any,
    storage_topology: Any,
    replication_country_codes: Any,
) -> None:
    """Fail closed unless an actual placement exactly matches the binding."""
    if not isinstance(binding, PilotRegionBinding):
        raise _fail("region_binding_required")
    if storage_country_code != binding.restricted_storage_country_code:
        raise _fail("restricted_storage_region")
    if storage_topology != binding.restricted_storage_topology:
        raise _fail("restricted_storage_topology")
    if type(replication_country_codes) is not tuple:
        raise _fail("replication_inventory")
    if replication_country_codes:
        raise _fail("cross_region_replication")
