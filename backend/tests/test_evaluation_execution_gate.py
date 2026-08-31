"""Provider-free tests for the frozen experiment execution gate."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from app.services.evaluation_contract_identity import load_strict_contract_json
from app.services.evaluation_execution_gate import (
    ExecutionGateError,
    FrozenDiagnosticState,
    assess_execution_gate,
)


EXPERIMENT_PATH = (
    Path(__file__).parents[2]
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "experiment.v1.json"
)


def _experiment():
    return load_strict_contract_json(EXPERIMENT_PATH)


_FROZEN_NON_NULL_VALID_VALUES = {
    "cost_controls.pilot_cost_ceiling_usd": 1.0,
    "pending_versioned_artifacts.harness_version.value": "v1",
    "pending_versioned_artifacts.pilot_fixture_set_version.value": "v1",
    "pending_versioned_artifacts.truth_sheet_version.value": "v1",
    "pending_versioned_artifacts.visual_asset_set_version.value": "v1",
    "pending_versioned_artifacts.grading_anchor_set_version.value": "v1",
    (
        "pending_versioned_artifacts."
        "operational_maturity_anchor_set_version.value"
    ): "v1",
    (
        "pending_versioned_artifacts."
        "latency_normalization_bands_version.value"
    ): "v1",
    (
        "pending_versioned_artifacts."
        "cost_normalization_bands_version.value"
    ): "v1",
    "cost_controls.scored_experiment_cost_ceiling_usd": 1.0,
    "execution_order_policy.execution_seed": 0,
}


def _set_status_source(artifact, path, value):
    current = artifact
    parts = path.split(".")
    for segment in parts[:-1]:
        current = current[segment]
    current[parts[-1]] = value


def _set_prerequisites_to_required(artifact, inventory_name):
    for prerequisite in artifact["execution_gate"][inventory_name]:
        source = prerequisite.get("status_source")
        if source is None:
            continue
        required = prerequisite["required_state"]
        value = (
            _FROZEN_NON_NULL_VALID_VALUES[source]
            if required == "frozen_non_null"
            else required
        )
        _set_status_source(artifact, source, value)


def _authorized_experiment(phase):
    artifact = _experiment()
    gate = artifact["execution_gate"]
    artifact["status"] = phase
    gate["provider_calls_allowed"] = True
    gate["pilot_calls_allowed"] = phase == "pilot_authorized"
    gate["scored_calls_allowed"] = phase == "scored_authorized"
    _set_prerequisites_to_required(
        artifact,
        "universal_provider_call_prerequisites",
    )
    if phase == "pilot_authorized":
        _set_prerequisites_to_required(artifact, "pilot_specific_prerequisites")
    else:
        _set_prerequisites_to_required(artifact, "scored_call_prerequisites")
    return artifact


def test_current_frozen_experiment_is_deterministically_blocked():
    artifact = _experiment()

    result = assess_execution_gate(artifact)

    assert result.phase == "pre_execution"
    assert result.overall_status == "blocked_pre_execution"
    assert result.provider_calls_allowed is False
    assert result.pilot_calls_allowed is False
    assert result.scored_calls_allowed is False
    assert result.provider_calls_completed == 0
    assert result.scored_provider_calls_completed == 0
    assert result.winner_selected is False
    assert len(result.universal_blockers) == 17
    assert len(result.pilot_blockers) == 3
    assert len(result.scored_blockers) == 21
    assert result.universal_blockers[0].prerequisite_id == (
        "candidate_lifecycle_preflight_complete"
    )
    assert result.universal_blockers[-1].prerequisite_id == (
        "no_unresolved_execution_blocking_prerequisite"
    )


def test_all_pass_aggregate_clears_only_after_every_universal_requirement():
    artifact = _experiment()
    for prerequisite in artifact["execution_gate"][
        "universal_provider_call_prerequisites"
    ]:
        current = artifact
        parts = prerequisite["status_source"].split(".")
        for segment in parts[:-1]:
            current = current[segment]
        current[parts[-1]] = (
            _FROZEN_NON_NULL_VALID_VALUES[prerequisite["status_source"]]
            if prerequisite["required_state"] == "frozen_non_null"
            else prerequisite["required_state"]
        )

    result = assess_execution_gate(artifact)

    assert result.universal_blockers == ()
    assert tuple(item.prerequisite_id for item in result.pilot_blockers) == (
        "explicit_pilot_authorization_recorded",
    )
    assert all(
        item.prerequisite_id != "all_universal_provider_call_prerequisites_pass"
        for item in result.scored_blockers
    )


def test_assessment_does_not_mutate_the_frozen_artifact():
    artifact = _experiment()
    original = copy.deepcopy(artifact)

    assess_execution_gate(artifact)

    assert artifact == original


@pytest.mark.parametrize(
    ("phase", "provider", "pilot", "scored"),
    (
        ("pre_execution", True, False, False),
        ("pre_execution", False, True, False),
        ("pre_execution", False, False, True),
    ),
)
def test_declared_phase_flags_must_match_frozen_phase_state(
    phase, provider, pilot, scored
):
    artifact = _experiment()
    artifact["status"] = phase
    gate = artifact["execution_gate"]
    gate["provider_calls_allowed"] = provider
    gate["pilot_calls_allowed"] = pilot
    gate["scored_calls_allowed"] = scored

    with pytest.raises(ExecutionGateError, match="phase_flags"):
        assess_execution_gate(artifact)


@pytest.mark.parametrize(
    ("phase", "provider", "pilot", "scored", "error"),
    (
        ("pilot_authorized", True, True, False, "pilot_prerequisites"),
        ("scored_authorized", True, False, True, "scored_prerequisites"),
    ),
)
def test_authorized_phase_fails_closed_while_prerequisites_are_pending(
    phase, provider, pilot, scored, error
):
    artifact = _experiment()
    artifact["status"] = phase
    gate = artifact["execution_gate"]
    gate["provider_calls_allowed"] = provider
    gate["pilot_calls_allowed"] = pilot
    gate["scored_calls_allowed"] = scored

    with pytest.raises(ExecutionGateError, match=error):
        assess_execution_gate(artifact)


def test_frozen_prerequisite_source_path_cannot_be_rewritten():
    artifact = _experiment()
    prerequisite = artifact["execution_gate"][
        "universal_provider_call_prerequisites"
    ][0]
    prerequisite["status_source"] = "missing.path"

    with pytest.raises(ExecutionGateError, match="prerequisite_contract"):
        assess_execution_gate(artifact)


def test_missing_declared_prerequisite_source_path_fails_closed():
    artifact = _experiment()
    del artifact["lifecycle_preflight"]

    with pytest.raises(ExecutionGateError, match="status_source"):
        assess_execution_gate(artifact)


def test_duplicate_prerequisite_identity_fails_closed():
    artifact = _experiment()
    prerequisites = artifact["execution_gate"][
        "universal_provider_call_prerequisites"
    ]
    prerequisites[1]["id"] = prerequisites[0]["id"]

    with pytest.raises(ExecutionGateError, match="prerequisite_inventory"):
        assess_execution_gate(artifact)


def test_missing_or_rewritten_frozen_prerequisite_fails_closed():
    artifact = _experiment()
    prerequisites = artifact["execution_gate"][
        "universal_provider_call_prerequisites"
    ]
    prerequisites.pop()
    with pytest.raises(ExecutionGateError, match="prerequisite_contract"):
        assess_execution_gate(artifact)


def test_unknown_prerequisite_cannot_enter_the_frozen_inventory():
    artifact = _experiment()
    artifact["execution_gate"]["pilot_specific_prerequisites"].append(
        {
            "id": "unknown_prerequisite",
            "required_state": "approved",
            "status_source": "execution_gate.pilot_authorization_status",
        }
    )

    with pytest.raises(ExecutionGateError, match="prerequisite_contract"):
        assess_execution_gate(artifact)

    artifact = _experiment()
    prerequisite = artifact["execution_gate"][
        "universal_provider_call_prerequisites"
    ][0]
    prerequisite["required_state"] = "pending"
    with pytest.raises(ExecutionGateError, match="prerequisite_contract"):
        assess_execution_gate(artifact)


def test_mutating_declared_phase_table_cannot_create_authority():
    artifact = _experiment()
    artifact["execution_gate"]["phase_states"]["pre_execution"][
        "provider_calls_allowed"
    ] = True
    artifact["execution_gate"]["provider_calls_allowed"] = True

    with pytest.raises(ExecutionGateError, match="phase_contract"):
        assess_execution_gate(artifact)


def test_phase_contract_uses_exact_json_scalar_types_for_every_phase():
    artifact = _experiment()
    artifact["execution_gate"]["phase_states"]["pilot_authorized"][
        "provider_calls_allowed"
    ] = 1

    with pytest.raises(ExecutionGateError, match="phase_contract"):
        assess_execution_gate(artifact)


def test_frozen_non_null_never_treats_null_as_ready():
    artifact = _experiment()
    artifact["cost_controls"]["pilot_cost_ceiling_usd"] = None

    result = assess_execution_gate(artifact)
    blocker = next(
        item
        for item in result.universal_blockers
        if item.prerequisite_id == "pilot_cost_ceiling_frozen"
    )

    assert blocker.actual_state is None
    assert blocker.required_state == "frozen_non_null"


def test_execution_flags_and_counters_have_exact_scalar_types():
    artifact = _experiment()
    artifact["execution_gate"]["provider_calls_allowed"] = 0
    with pytest.raises(ExecutionGateError, match="provider_calls_allowed"):
        assess_execution_gate(artifact)

    artifact = _experiment()
    artifact["provider_calls_completed"] = False
    with pytest.raises(ExecutionGateError, match="provider_calls_completed"):
        assess_execution_gate(artifact)


def test_pre_execution_counters_and_winner_cannot_claim_execution():
    artifact = _experiment()
    artifact["provider_calls_completed"] = 1
    with pytest.raises(ExecutionGateError, match="pre_execution_state"):
        assess_execution_gate(artifact)

    artifact = _experiment()
    artifact["winner_selected"] = True
    with pytest.raises(ExecutionGateError, match="pre_execution_state"):
        assess_execution_gate(artifact)


_VERSION_SOURCES = tuple(
    source
    for source in _FROZEN_NON_NULL_VALID_VALUES
    if source.startswith("pending_versioned_artifacts.")
)
_COST_SOURCES = (
    "cost_controls.pilot_cost_ceiling_usd",
    "cost_controls.scored_experiment_cost_ceiling_usd",
)
_VERSION_INVALID_VALUES = (
    False,
    True,
    0,
    1,
    0.0,
    1.0,
    "",
    " ",
    [],
    [1],
    {},
    {"x": 1},
    None,
)
_COST_INVALID_VALUES = (
    False,
    True,
    0,
    0.0,
    -1,
    -1.0,
    float("inf"),
    float("-inf"),
    float("nan"),
    "",
    " ",
    "0",
    "1",
    "false",
    [],
    [1],
    {},
    {"x": 1},
    None,
)
_SEED_INVALID_VALUES = (
    False,
    True,
    -1,
    0.0,
    1.0,
    "",
    " ",
    "0",
    "1",
    "false",
    [],
    [1],
    {},
    {"x": 1},
    None,
)
_INVALID_FROZEN_NON_NULL_CASES = (
    tuple(
        (source, value)
        for source in _VERSION_SOURCES
        for value in _VERSION_INVALID_VALUES
    )
    + tuple(
        (source, value)
        for source in _COST_SOURCES
        for value in _COST_INVALID_VALUES
    )
    + tuple(
        ("execution_order_policy.execution_seed", value)
        for value in _SEED_INVALID_VALUES
    )
)


def _all_blockers(result):
    return (
        result.universal_blockers
        + result.pilot_blockers
        + result.scored_blockers
    )


@pytest.mark.parametrize(
    ("source", "value"),
    _INVALID_FROZEN_NON_NULL_CASES,
)
def test_frozen_non_null_prerequisites_reject_source_specific_invalid_values(
    source,
    value,
):
    artifact = _experiment()
    _set_status_source(artifact, source, copy.deepcopy(value))

    result = assess_execution_gate(artifact)

    assert any(
        blocker.status_source == source for blocker in _all_blockers(result)
    )


@pytest.mark.parametrize(
    ("source", "value"),
    _INVALID_FROZEN_NON_NULL_CASES,
)
def test_malformed_frozen_non_null_never_allows_an_authorized_phase(
    source,
    value,
):
    phase = (
        "pilot_authorized"
        if source
        in {
            "cost_controls.pilot_cost_ceiling_usd",
            "pending_versioned_artifacts.harness_version.value",
            "pending_versioned_artifacts.pilot_fixture_set_version.value",
        }
        else "scored_authorized"
    )
    artifact = _authorized_experiment(phase)
    _set_status_source(artifact, source, copy.deepcopy(value))

    with pytest.raises(
        ExecutionGateError,
        match=(
            "pilot_prerequisites"
            if phase == "pilot_authorized"
            else "scored_prerequisites"
        ),
    ):
        assess_execution_gate(artifact)


@pytest.mark.parametrize(
    ("source", "value"),
    tuple(_FROZEN_NON_NULL_VALID_VALUES.items())
    + (
        ("cost_controls.pilot_cost_ceiling_usd", 1),
        ("cost_controls.pilot_cost_ceiling_usd", 10**1000),
        ("cost_controls.scored_experiment_cost_ceiling_usd", 1),
        ("cost_controls.scored_experiment_cost_ceiling_usd", 10**1000),
        ("execution_order_policy.execution_seed", 1),
        ("pending_versioned_artifacts.harness_version.value", "0"),
        ("pending_versioned_artifacts.harness_version.value", "false"),
    ),
)
def test_frozen_non_null_accepts_only_exact_valid_source_shapes(source, value):
    artifact = _experiment()
    _set_status_source(artifact, source, value)

    result = assess_execution_gate(artifact)

    assert all(
        blocker.status_source != source for blocker in _all_blockers(result)
    )


def test_valid_source_specific_values_allow_synthetic_authorized_phases():
    pilot = assess_execution_gate(_authorized_experiment("pilot_authorized"))
    scored = assess_execution_gate(_authorized_experiment("scored_authorized"))

    assert pilot.provider_calls_allowed is True
    assert pilot.pilot_calls_allowed is True
    assert pilot.universal_blockers == ()
    assert pilot.pilot_blockers == ()
    assert scored.provider_calls_allowed is True
    assert scored.scored_calls_allowed is True
    assert scored.universal_blockers == ()
    assert scored.scored_blockers == ()


@pytest.mark.parametrize(
    ("value", "mutation"),
    (
        ([1], lambda item: item.append(2)),
        ({"x": 1}, lambda item: item.update({"y": 2})),
        ([[1]], lambda item: item[0].append(2)),
        ({"x": {"y": 1}}, lambda item: item["x"].update({"z": 2})),
        (
            {"x": [{"y": [1]}]},
            lambda item: item["x"][0]["y"].append(2),
        ),
    ),
)
def test_blocker_evidence_is_deeply_isolated_from_caller_mutation(
    value,
    mutation,
):
    artifact = _experiment()
    source = "pending_versioned_artifacts.harness_version.value"
    caller_value = copy.deepcopy(value)
    _set_status_source(artifact, source, caller_value)

    result = assess_execution_gate(artifact)
    blocker = next(
        item
        for item in result.universal_blockers
        if item.status_source == source
    )
    snapshot = copy.deepcopy(blocker.actual_state)

    mutation(caller_value)

    assert blocker.actual_state == snapshot
    assert blocker.actual_state is not caller_value


_EXACT_STATE_ATTACK_VALUES = (
    None,
    False,
    True,
    0,
    1,
    0.0,
    1.0,
    "",
    " ",
    "unexpected",
    [],
    [1],
    {},
    {"x": 1},
)


def _exact_state_attack_cases():
    artifact = _experiment()
    cases = []
    inventories = (
        ("pilot_authorized", "universal_provider_call_prerequisites"),
        ("pilot_authorized", "pilot_specific_prerequisites"),
        ("scored_authorized", "scored_call_prerequisites"),
    )
    for phase, inventory_name in inventories:
        for prerequisite in artifact["execution_gate"][inventory_name]:
            source = prerequisite.get("status_source")
            required = prerequisite["required_state"]
            if source is None or required == "frozen_non_null":
                continue
            for value in _EXACT_STATE_ATTACK_VALUES:
                matches = (
                    type(value) is bool
                    and type(required) is bool
                    and value is required
                ) or (
                    type(value) is str
                    and type(required) is str
                    and value == required
                )
                if not matches:
                    cases.append(
                        (
                            phase,
                            inventory_name,
                            prerequisite["id"],
                            source,
                            copy.deepcopy(value),
                        )
                    )
    return tuple(cases)


_EXACT_STATE_ATTACK_CASES = _exact_state_attack_cases()


@pytest.mark.parametrize(
    ("phase", "inventory_name", "prerequisite_id", "source", "value"),
    _EXACT_STATE_ATTACK_CASES,
)
def test_exact_state_adversarial_matrix_never_fails_open(
    phase,
    inventory_name,
    prerequisite_id,
    source,
    value,
):
    del inventory_name, prerequisite_id
    artifact = _authorized_experiment(phase)
    _set_status_source(artifact, source, copy.deepcopy(value))

    with pytest.raises(
        ExecutionGateError,
        match=(
            "pilot_prerequisites"
            if phase == "pilot_authorized"
            else "scored_prerequisites"
        ),
    ):
        assess_execution_gate(artifact)


class _EqualToEveryString:
    def __eq__(self, other):
        return isinstance(other, str)


def test_non_json_object_cannot_impersonate_an_exact_required_state():
    artifact = _authorized_experiment("pilot_authorized")
    artifact["lifecycle_preflight"]["status"] = _EqualToEveryString()

    with pytest.raises(ExecutionGateError, match="pilot_prerequisites"):
        assess_execution_gate(artifact)


def test_cyclic_malformed_blocker_evidence_is_bounded_and_immutable():
    artifact = _experiment()
    source = "pending_versioned_artifacts.harness_version.value"
    caller_value = []
    caller_value.append(caller_value)
    _set_status_source(artifact, source, caller_value)

    result = assess_execution_gate(artifact)
    blocker = next(
        item
        for item in result.universal_blockers
        if item.status_source == source
    )
    snapshot = blocker.actual_state

    caller_value.append("later")

    assert blocker.actual_state == snapshot
    assert blocker.actual_state is not caller_value


def test_reassessment_never_trusts_stale_blocker_evidence():
    artifact = _experiment()
    source = "pending_versioned_artifacts.harness_version.value"

    blocked = assess_execution_gate(artifact)
    _set_status_source(artifact, source, "v1")
    refreshed = assess_execution_gate(artifact)

    assert any(
        blocker.status_source == source
        for blocker in blocked.universal_blockers
    )
    assert all(
        blocker.status_source != source
        for blocker in refreshed.universal_blockers
    )


@pytest.mark.parametrize("container_kind", ("array", "object"))
def test_deep_malformed_blocker_evidence_is_bounded(container_kind):
    artifact = _experiment()
    source = "pending_versioned_artifacts.harness_version.value"
    root = [] if container_kind == "array" else {}
    current = root
    for index in range(2000):
        child = [] if container_kind == "array" else {}
        if container_kind == "array":
            current.append(child)
        else:
            current[str(index)] = child
        current = child
    _set_status_source(artifact, source, root)

    result = assess_execution_gate(artifact)
    blocker = next(
        item
        for item in result.universal_blockers
        if item.status_source == source
    )

    assert isinstance(blocker.actual_state, FrozenDiagnosticState)
    assert blocker.actual_state.value == ()
    assert blocker.actual_state is not root
