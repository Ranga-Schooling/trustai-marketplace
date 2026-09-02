"""Tests for provider-free prompt/schema contract identity preflight."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from app.services.evaluation_contract_identity import (
    ContractIdentityError,
    load_strict_contract_json,
    load_strict_normalization_spec,
    verify_normalization_parser_artifact,
    verify_output_schema_artifact,
    verify_prompt_template_artifact,
)


ARTIFACT_DIRECTORY = (
    Path(__file__).parents[2] / "docs" / "testing" / "ai-evaluation"
)
SCHEMA_PATH = ARTIFACT_DIRECTORY / "output-schemas.v1.json"
PROMPT_PATH = ARTIFACT_DIRECTORY / "prompt-templates.v1.json"
PARSER_PATH = ARTIFACT_DIRECTORY / "normalization-parser.v1.json"


def test_frozen_output_schema_child_and_set_hashes_recompute():
    artifact = load_strict_contract_json(SCHEMA_PATH)

    result = verify_output_schema_artifact(artifact)

    assert result.set_hash == (
        "125809d08e911d51b4619002f02a969b03b8da5866bfab1b8346758c0bb9a6f4"
    )
    assert result.child_hashes == (
        (
            "text_output_schema_v1",
            "baec020db56ab334659a9f278a7383d7b3b4860275ae7276ad6a39bb1c26d37d",
        ),
        (
            "retrieval_evidence_bundle_v1",
            "a823c58173370aa2eb5e87bf96decec6c5b3a413e96aefc41783968181932201",
        ),
        (
            "search_output_schema_v1",
            "d66cc128a778577c2860b74cf7670eb8fb7f9d7b144df52e7258276169142c05",
        ),
        (
            "visual_output_schema_v1",
            "f085eb944710362f18add95bd9b64af8088edaa55cf1838ff4ec995ee0f3f5e3",
        ),
    )


def test_frozen_prompt_child_and_set_hashes_recompute():
    artifact = load_strict_contract_json(PROMPT_PATH)

    result = verify_prompt_template_artifact(artifact)

    assert result.set_hash == (
        "9d6c5e43acb971b3ffb2a47b69f0def142d21c971717541e007f711404603df2"
    )
    assert tuple(identifier for identifier, _ in result.child_hashes) == tuple(
        artifact["template_order"]
    )


def test_frozen_normalization_spec_and_all_child_hashes_recompute():
    artifact = load_strict_normalization_spec(PARSER_PATH)

    result = verify_normalization_parser_artifact(artifact)

    assert result.semantic_hash == (
        "023ad80eeb6e08e9279c22b7955ebe5d04ec9ab3cd88626ceaccc4962c41b343"
    )
    assert dict(result.child_hashes)["normalization_parser_resource_limits_v1"] == (
        "9269950928ddf05e6b691623c57e6b60797c1131ee96f893e4977d5f223b2d16"
    )
    assert len(result.child_hashes) == 49
    assert dict(result.child_hashes)["provider_role_mapping_contract_v1"] == (
        "e745dbb1a4b67a7c2d0bf2bdb069b27a36aa59278e2c515d1637ab840e671976"
    )
    assert dict(result.child_hashes)["semantic_numeric_domain_policy_v1"] == (
        "7b672830ea04e1c0cd2df19d2c52f72ff4aec4c76c88365afff149074d2f49cd"
    )


@pytest.mark.parametrize("kind", ("schema", "prompt"))
def test_semantic_child_mutation_fails_closed(kind):
    if kind == "schema":
        artifact = load_strict_contract_json(SCHEMA_PATH)
        artifact["schemas"][0]["schema"]["properties"]["summary"][
            "minLength"
        ] = 2
        verifier = verify_output_schema_artifact
    else:
        artifact = load_strict_contract_json(PROMPT_PATH)
        artifact["templates"][0]["canonical_content"][0] += " mutated"
        verifier = verify_prompt_template_artifact

    with pytest.raises(ContractIdentityError, match="child_hash_mismatch"):
        verifier(artifact)


@pytest.mark.parametrize("kind", ("schema", "prompt"))
def test_cached_set_hash_mutation_fails_closed(kind):
    if kind == "schema":
        artifact = load_strict_contract_json(SCHEMA_PATH)
        artifact["schema_set_sha256"] = "0" * 64
        verifier = verify_output_schema_artifact
    else:
        artifact = load_strict_contract_json(PROMPT_PATH)
        artifact["prompt_template_set_hash"] = "0" * 64
        verifier = verify_prompt_template_artifact

    with pytest.raises(ContractIdentityError, match="set_hash_mismatch"):
        verifier(artifact)


@pytest.mark.parametrize("kind", ("schema", "prompt"))
def test_declared_order_must_match_exact_child_inventory(kind):
    if kind == "schema":
        artifact = load_strict_contract_json(SCHEMA_PATH)
        artifact["schema_order"] = list(reversed(artifact["schema_order"]))
        verifier = verify_output_schema_artifact
    else:
        artifact = load_strict_contract_json(PROMPT_PATH)
        artifact["template_order"] = list(reversed(artifact["template_order"]))
        verifier = verify_prompt_template_artifact

    with pytest.raises(ContractIdentityError, match="ordered_inventory"):
        verifier(artifact)


def test_nonsemantic_lifecycle_and_counter_fields_do_not_change_set_identity():
    schema = load_strict_contract_json(SCHEMA_PATH)
    prompt = load_strict_contract_json(PROMPT_PATH)
    schema_expected = verify_output_schema_artifact(schema)
    prompt_expected = verify_prompt_template_artifact(prompt)

    schema["status"] = "test-only-mutated-lifecycle"
    schema["provider_calls_completed"] = 999
    prompt["status"] = "test-only-mutated-lifecycle"
    prompt["provider_calls_completed"] = 999

    assert verify_output_schema_artifact(schema) == schema_expected
    assert verify_prompt_template_artifact(prompt) == prompt_expected


def test_normalization_spec_lifecycle_and_counter_exclusions_are_exact():
    artifact = load_strict_normalization_spec(PARSER_PATH)
    expected = verify_normalization_parser_artifact(artifact)

    artifact["status"] = "test-only-mutated-lifecycle"
    artifact["provider_calls_completed"] = 999

    assert verify_normalization_parser_artifact(artifact) == expected


def test_normalization_child_or_central_semantic_mutation_fails_closed():
    child_mutation = load_strict_normalization_spec(PARSER_PATH)
    child_mutation["attempt_stage_event_ledger"]["immutable"] = False
    with pytest.raises(ContractIdentityError, match="child_hash_mismatch"):
        verify_normalization_parser_artifact(child_mutation)

    central_mutation = load_strict_normalization_spec(PARSER_PATH)
    central_mutation["purpose"] += " mutated"
    with pytest.raises(ContractIdentityError, match="spec_hash_mismatch"):
        verify_normalization_parser_artifact(central_mutation)


def test_object_member_insertion_order_does_not_change_canonical_identity():
    artifact = load_strict_contract_json(SCHEMA_PATH)
    reordered = copy.deepcopy(artifact)
    reordered["schemas"][0] = dict(reversed(tuple(reordered["schemas"][0].items())))

    assert verify_output_schema_artifact(reordered) == verify_output_schema_artifact(
        artifact
    )


@pytest.mark.parametrize(
    "payload",
    (
        b'{"a":1,"a":2}',
        b'{"value":NaN}',
        b'\xff',
        b'{"value":"\\ud800"}',
    ),
)
def test_strict_contract_loader_rejects_ambiguous_json(tmp_path, payload):
    path = tmp_path / "invalid.json"
    path.write_bytes(payload)

    with pytest.raises(ContractIdentityError, match="strict_contract_json"):
        load_strict_contract_json(path)
