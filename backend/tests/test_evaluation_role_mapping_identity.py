"""Provider-free tests for frozen role-mapping semantic identity."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.services.evaluation_contract_identity import load_strict_normalization_spec
from app.services.evaluation_role_mapping_identity import (
    ProviderRoleMappingIdentityError,
    compute_provider_role_mapping_identity,
    verify_provider_role_mapping_hash,
)


SPEC_PATH = (
    Path(__file__).parents[2]
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "normalization-parser.v1.json"
)
EXPECTED_BASE_HASH = (
    "867101c71ab1ec6f71945283a14bdd6a7ba27d442104a56e2683cf1727860914"
)


def _contract():
    return load_strict_normalization_spec(SPEC_PATH)[
        "provider_role_mapping_contract_v1"
    ]


def _base_envelope():
    return copy.deepcopy(_contract()["mapping_hash_test_vectors"]["base_envelope"])


def _json_bytes(value, **kwargs):
    return json.dumps(value, ensure_ascii=False, **kwargs).encode("utf-8")


def test_base_envelope_has_the_independently_derived_frozen_identity():
    identity = compute_provider_role_mapping_identity(_json_bytes(_base_envelope()))

    assert identity.mapping_id == "synthetic_mapping_a"
    assert identity.mapping_version == "v1"
    assert identity.semantic_hash == EXPECTED_BASE_HASH
    assert identity.identity_domain == "trustai.provider_role_mapping.v1"
    assert identity.independently_authorizes_execution is False


def test_formatting_and_object_member_order_do_not_change_semantic_identity():
    base = _base_envelope()
    compact = _json_bytes(base, sort_keys=True, separators=(",", ":"))
    reordered = {
        "provider_role_mapping_version": base["provider_role_mapping_version"],
        "content": {
            key: base["content"][key]
            for key in reversed(tuple(base["content"]))
        },
        "identity_domain": base["identity_domain"],
        "provider_role_mapping_id": base["provider_role_mapping_id"],
    }
    pretty = _json_bytes(reordered, indent=4)

    compact_identity = compute_provider_role_mapping_identity(compact)
    pretty_identity = compute_provider_role_mapping_identity(pretty)

    assert compact_identity.semantic_hash == EXPECTED_BASE_HASH
    assert pretty_identity.semantic_hash == EXPECTED_BASE_HASH
    assert compact_identity == pretty_identity


@pytest.mark.parametrize(
    ("mutation_path", "replacement"),
    (
        (("content", "ordered_template_ids"), ["text_input_v1", "text_system_v1"]),
        (
            ("content", "native_destination_semantics"),
            ["ordinary_input_surface", "highest_instruction_surface"],
        ),
        (
            ("content", "authority_destinations"),
            ["untrusted_input", "authoritative_instruction"],
        ),
        (
            ("content", "applicable_adapter", "adapter_id"),
            "synthetic_adapter_b",
        ),
        (
            ("content", "applicable_adapter", "adapter_version"),
            "v2",
        ),
        (("provider_role_mapping_id",), "synthetic_mapping_b"),
        (("provider_role_mapping_version",), "v2"),
        (
            ("content", "native_segment_grouping"),
            [["text_system_v1"], ["text_input_v1"]],
        ),
        (
            ("content", "split_boundary_rule"),
            "different_frozen_boundary",
        ),
        (
            ("content", "separator_ownership"),
            "different_separator_owner",
        ),
    ),
)
def test_every_frozen_semantic_mutation_changes_the_hash(
    mutation_path,
    replacement,
):
    mutated = _base_envelope()
    destination = mutated
    for key in mutation_path[:-1]:
        destination = destination[key]
    destination[mutation_path[-1]] = replacement

    identity = compute_provider_role_mapping_identity(_json_bytes(mutated))

    assert identity.semantic_hash != EXPECTED_BASE_HASH


def test_stored_hash_is_non_authoritative_and_must_match_recomputation():
    payload = _json_bytes(_base_envelope())

    assert (
        verify_provider_role_mapping_hash(payload, EXPECTED_BASE_HASH).semantic_hash
        == EXPECTED_BASE_HASH
    )
    with pytest.raises(
        ProviderRoleMappingIdentityError,
        match="provider_role_mapping_hash_mismatch",
    ):
        verify_provider_role_mapping_hash(payload, "0" * 64)


@pytest.mark.parametrize(
    "stored_hash",
    (
        None,
        False,
        0,
        "",
        "A" * 64,
        "g" * 64,
        "0" * 63,
        "0" * 65,
    ),
)
def test_stored_hash_requires_exact_lowercase_sha256(stored_hash):
    with pytest.raises(
        ProviderRoleMappingIdentityError,
        match="provider_role_mapping_hash_format",
    ):
        verify_provider_role_mapping_hash(_json_bytes(_base_envelope()), stored_hash)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("identity_domain", "other", "provider_role_mapping_identity_domain"),
        ("identity_domain", True, "provider_role_mapping_identity_domain"),
        ("provider_role_mapping_id", None, "provider_role_mapping_id"),
        ("provider_role_mapping_id", 1, "provider_role_mapping_id"),
        ("provider_role_mapping_version", None, "provider_role_mapping_version"),
        ("provider_role_mapping_version", False, "provider_role_mapping_version"),
        ("content", None, "provider_role_mapping_content"),
        ("content", [], "provider_role_mapping_content"),
    ),
)
def test_envelope_identity_and_content_types_are_exact(field, value, error):
    envelope = _base_envelope()
    envelope[field] = value

    with pytest.raises(ProviderRoleMappingIdentityError, match=error):
        compute_provider_role_mapping_identity(_json_bytes(envelope))


def test_envelope_keys_are_exact_and_cannot_include_runtime_companion_data():
    envelope = _base_envelope()
    envelope["runtime_request_id"] = "request-1"

    with pytest.raises(
        ProviderRoleMappingIdentityError,
        match="provider_role_mapping_envelope_keys",
    ):
        compute_provider_role_mapping_identity(_json_bytes(envelope))

    envelope = _base_envelope()
    envelope.pop("content")
    with pytest.raises(
        ProviderRoleMappingIdentityError,
        match="provider_role_mapping_envelope_keys",
    ):
        compute_provider_role_mapping_identity(_json_bytes(envelope))


@pytest.mark.parametrize(
    ("payload", "error"),
    (
        (b"[]", "provider_role_mapping_envelope"),
        (b"null", "provider_role_mapping_envelope"),
        (b'{"identity_domain":"x","identity_domain":"y"}', "strict_json"),
        (b'{"value":NaN}', "strict_json"),
        (b'{"value":"\\ud800"}', "strict_json"),
        (b"{", "strict_json"),
        (b"\xff", "strict_json"),
    ),
)
def test_envelope_uses_the_frozen_strict_json_boundary(payload, error):
    with pytest.raises(ProviderRoleMappingIdentityError, match=error):
        compute_provider_role_mapping_identity(payload)


@pytest.mark.parametrize("payload", (None, bytearray(b"{}"), "{}", {}, []))
def test_envelope_input_requires_exact_immutable_bytes(payload):
    with pytest.raises(
        ProviderRoleMappingIdentityError,
        match="provider_role_mapping_envelope_bytes",
    ):
        compute_provider_role_mapping_identity(payload)


def test_identity_result_is_immutable_and_detached_from_input_bytes():
    payload = _json_bytes(_base_envelope())
    identity = compute_provider_role_mapping_identity(payload)

    with pytest.raises((AttributeError, TypeError)):
        identity.semantic_hash = "0" * 64
    assert identity.semantic_hash == EXPECTED_BASE_HASH


def test_frozen_hash_vector_inventories_and_execution_boundary_are_preserved():
    contract = _contract()
    hash_vectors = contract["mapping_hash_test_vectors"]
    mixed_vectors = contract["mixed_authority_hash_relational_vectors"]

    assert len(hash_vectors["relational_vectors"]) == 10
    assert hash_vectors["expected_vector_count"] == 10
    assert hash_vectors["provider_calls_required"] is False
    assert len(mixed_vectors["vectors"]) == 4
    assert mixed_vectors["expected_vector_count"] == 4
    assert mixed_vectors["provider_calls_required"] is False
    assert contract["independently_authorizes_execution"] is False
    assert contract["future_external_dependency"]["status"] == "pending_creation"
