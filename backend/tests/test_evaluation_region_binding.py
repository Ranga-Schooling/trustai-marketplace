"""Provider-free tests for the approved pilot region and storage binding."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.evaluation_region_binding import (
    RegionBindingError,
    validate_restricted_storage_placement,
    verify_pilot_region_binding,
)


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = (
    ROOT / "docs" / "testing" / "ai-evaluation" / "pilot-region-binding.v1.json"
)


def test_region_binding_freezes_only_the_approved_operational_decisions():
    binding = verify_pilot_region_binding()

    assert binding.policy_id == "pilot_region_binding_v1"
    assert binding.policy_version == "v1"
    assert binding.operation_country_code == "US"
    assert binding.provider_service_mode == "standard_global"
    assert binding.restricted_storage_country_code == "US"
    assert binding.restricted_storage_topology == "local_operator_controlled"
    assert binding.cross_region_replication_allowed is False
    assert binding.restricted_retention_days == 30
    assert binding.cloud_infrastructure_required is False
    assert binding.provider_processing_location_asserted is False


def test_local_us_storage_passes_and_non_us_or_replication_fails_closed():
    binding = verify_pilot_region_binding()

    validate_restricted_storage_placement(
        binding,
        storage_country_code="US",
        storage_topology="local_operator_controlled",
        replication_country_codes=(),
    )
    with pytest.raises(RegionBindingError, match="restricted_storage_region"):
        validate_restricted_storage_placement(
            binding,
            storage_country_code="CA",
            storage_topology="local_operator_controlled",
            replication_country_codes=(),
        )
    with pytest.raises(RegionBindingError, match="cross_region_replication"):
        validate_restricted_storage_placement(
            binding,
            storage_country_code="US",
            storage_topology="local_operator_controlled",
            replication_country_codes=("US", "CA"),
        )


def test_region_binding_preserves_retention_and_execution_boundaries():
    binding = verify_pilot_region_binding()

    assert binding.retention_clock_starts_at == "final_model_selection_decision_at"
    assert binding.provider_calls_allowed is False
    assert binding.pilot_calls_allowed is False
    assert binding.scored_calls_allowed is False
    assert binding.provider_calls_completed == 0
    assert binding.pilot_calls_completed == 0
    assert binding.scored_calls_completed == 0
    assert binding.winner_selected is False


def test_region_binding_identity_or_semantic_mutation_fails_closed(tmp_path):
    raw = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    raw["storage_binding"]["cross_region_replication_allowed"] = True
    path = tmp_path / "region.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(RegionBindingError, match="region_binding_identity"):
        verify_pilot_region_binding(path)
