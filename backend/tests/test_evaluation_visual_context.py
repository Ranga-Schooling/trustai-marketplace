"""Provider-free tests for the frozen pilot visual-context projection."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from app.services.evaluation_contract_identity import load_strict_contract_json
from app.services.evaluation_visual_context import (
    VisualContextContractError,
    bind_visual_context_contract,
    render_pilot_visual_context,
)


ROOT = Path(__file__).parents[2]
ARTIFACTS = ROOT / "docs" / "testing" / "ai-evaluation"
CONTRACT_PATH = ARTIFACTS / "visual-context.v1.json"
PILOT_PATH = ARTIFACTS / "pilot-fixtures.v1.json"
PROMPT_PATH = ARTIFACTS / "prompt-templates.v1.json"


def _raw():
    return (
        load_strict_contract_json(CONTRACT_PATH),
        load_strict_contract_json(PILOT_PATH),
        load_strict_contract_json(PROMPT_PATH),
    )


def _bound():
    return bind_visual_context_contract(*_raw())


def test_exact_provider_visible_shape_and_execution_boundary_are_frozen():
    bound = _bound()

    assert bound.context_keys == ("title", "description")
    assert bound.fixture_ids == ("PV1", "PV2")
    assert bound.rendering_policy_id == "canonical_untrusted_json_v1"
    assert bound.rendering_policy_version == "v1"
    assert bound.provider_calls_allowed is False
    assert bound.pilot_calls_allowed is False
    assert bound.provider_calls_completed == 0
    assert bound.independently_authorizes_execution is False


@pytest.mark.parametrize(("fixture_id", "expected"), (
    (
        "PV1",
        '{"description":"Synthetic demonstration object photographed in a neutral controlled setting.","title":"Desktop calculator with demonstration label"}',
    ),
    (
        "PV2",
        '{"description":"Synthetic demonstration object photographed in a neutral controlled setting.","title":"Blue storage case with demonstration card"}',
    ),
))
def test_context_is_canonical_untrusted_json_with_exact_fixture_values(
    fixture_id, expected
):
    rendered = render_pilot_visual_context(_bound(), fixture_id=fixture_id)

    assert rendered.canonical_json == expected
    assert rendered.provider_visible_context == {
        "title": (
            "Desktop calculator with demonstration label"
            if fixture_id == "PV1"
            else "Blue storage case with demonstration card"
        ),
        "description": (
            "Synthetic demonstration object photographed in a neutral controlled setting."
        ),
    }
    assert rendered.authority_class == "untrusted_context"
    assert rendered.provider_attempt_created is False
    assert rendered.provider_call_incremented is False


@pytest.mark.parametrize("mutation", (
    lambda raw: raw[1]["pilot_fixtures"][3]["sanitized_listing_context"].__setitem__(
        "fixture_id", "PV1"
    ),
    lambda raw: raw[1]["pilot_fixtures"][3]["sanitized_listing_context"].pop(
        "description"
    ),
    lambda raw: raw[1]["pilot_fixtures"][3]["sanitized_listing_context"].__setitem__(
        "title", ""
    ),
    lambda raw: raw[0]["provider_visible_shape"].__setitem__(
        "keys_in_allowlist_order", ["description", "title"]
    ),
))
def test_shape_or_fixture_mutations_fail_closed(mutation):
    raw = list(_raw())
    mutation(raw)

    with pytest.raises(VisualContextContractError):
        bind_visual_context_contract(*raw)


def test_evaluator_truth_and_asset_metadata_never_enter_projection():
    bound = _bound()
    rendered = render_pilot_visual_context(bound, fixture_id="PV2")

    assert set(rendered.provider_visible_context) == {"title", "description"}
    assert "prompt_injection" not in rendered.canonical_json
    assert "asset_hash" not in rendered.canonical_json
    assert "truth" not in rendered.canonical_json
    assert "fixture" not in rendered.canonical_json


def test_unknown_fixture_fails_before_attempt():
    with pytest.raises(VisualContextContractError, match="fixture_selection"):
        render_pilot_visual_context(_bound(), fixture_id="V1")


def test_binding_does_not_mutate_frozen_inputs():
    raw = _raw()
    originals = copy.deepcopy(raw)

    bind_visual_context_contract(*raw)

    assert raw == originals
