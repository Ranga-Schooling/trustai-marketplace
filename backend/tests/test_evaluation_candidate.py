"""Tests for unfiltered model-owned canonical candidate construction."""

from __future__ import annotations

from app.services.normalization_parser import (
    ExactJsonNumber,
    admit_canonical_validation_candidate,
    canonicalize_semantic_json,
    construct_unfiltered_canonical_validation_candidate,
    normalize_semantic_json,
    parse_strict_json_payload,
)


def test_candidate_preserves_complete_unfiltered_semantic_tree():
    parsed = parse_strict_json_payload(
        '{"known":"value","unknown":{"keep":true},"items":[null,1," é "]}'.encode()
    )

    candidate = construct_unfiltered_canonical_validation_candidate(parsed)

    assert candidate.value == parsed.value
    assert candidate.value is not parsed.value
    assert candidate.value["unknown"] is not parsed.value["unknown"]
    assert candidate.value["items"] is not parsed.value["items"]
    assert candidate.value["items"][0] is None
    assert isinstance(candidate.value["items"][1], ExactJsonNumber)
    assert candidate.value["items"][2] == " é "


def test_candidate_snapshot_is_not_changed_by_later_parsed_tree_mutation():
    parsed = parse_strict_json_payload(b'{"nested":{"value":"original"}}')
    candidate = construct_unfiltered_canonical_validation_candidate(parsed)

    parsed.value["nested"]["value"] = "mutated"

    assert candidate.value["nested"]["value"] == "original"


def test_candidate_numeric_admission_and_hash_match_integrated_pipeline():
    payload = b'{"z":1.0,"a":[0.1,true,null],"unknown":"preserved"}'
    parsed = parse_strict_json_payload(payload)
    candidate = construct_unfiltered_canonical_validation_candidate(parsed)

    admitted = admit_canonical_validation_candidate(candidate)
    canonical = canonicalize_semantic_json(admitted)
    integrated = normalize_semantic_json(payload)

    assert canonical.canonical_bytes == integrated.canonical_bytes
    assert canonical.strict_parsed_semantic_payload_hash == (
        integrated.strict_parsed_semantic_payload_hash
    )


def test_candidate_constructor_requires_strict_parser_result():
    try:
        construct_unfiltered_canonical_validation_candidate({"value": 1})
    except TypeError as exc:
        assert "StrictParsedJson" in str(exc)
    else:
        raise AssertionError("non-strict input was admitted")
