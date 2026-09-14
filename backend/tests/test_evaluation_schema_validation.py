"""Conformance tests for the frozen canonical output-schema boundary."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

import app.services.evaluation_schema_validation as schema_validation
from app.services.evaluation_contract_identity import load_strict_contract_json
from app.services.evaluation_schema_validation import (
    OUTPUT_SCHEMA_IDS,
    OUTPUT_SCHEMA_SET_SHA256,
    WORKLOAD_SCHEMA_IDS,
    CanonicalOutputSchemaRegistry,
    CanonicalSchemaValidationError,
    SchemaContractError,
    SchemaValidatedCandidate,
)
from app.services.evaluation_resource_limits import RESOURCE_LIMIT_VALUES
from app.services.normalization_parser import (
    CanonicalSemanticJson,
    NumericDomainAdmission,
    canonicalize_semantic_json,
    normalize_semantic_json,
    replay_canonical_semantic_json,
)


ARTIFACT_PATH = (
    Path(__file__).parents[2]
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "output-schemas.v1.json"
)
ARTIFACT = load_strict_contract_json(ARTIFACT_PATH)


def _canonical(value):
    return normalize_semantic_json(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    )


def _registry():
    return CanonicalOutputSchemaRegistry.from_path(ARTIFACT_PATH)


def _text():
    return {
        "summary": "No obvious scam signal.",
        "risk_level": "low",
        "risk_indicators": [],
        "price_assessment": "Plausible from listing evidence.",
        "price_plausibility": "plausible",
        "seller_questions": ["Can I inspect it?"],
        "recommendation": "buy",
    }


def _retrieval():
    return {
        "retrieval_status": "completed",
        "sources": [
            {
                "source_id": "source-1",
                "name": "Example Manufacturer",
                "url": "https://example.com/products/item?region=us",
                "source_type": "manufacturer",
                "retrieved_at": "2026-08-30T12:34:56.789Z",
                "evidence_items": [
                    {
                        "evidence_id": "evidence-1",
                        "evidence_type": "identity",
                        "content": "Model X, Graphite",
                    }
                ],
            }
        ],
    }


def _search():
    source = {
        "source_id": "source-1",
        "name": "Example Manufacturer",
        "url": "https://example.com/products/item?region=us",
        "source_type": "manufacturer",
        "retrieved_at": "2026-08-30T12:34:56.789Z",
    }
    return {
        "identity_resolution": {
            "status": "resolved",
            "current_status": "current",
            "resolved_product_identity": "Model X",
            "source_ids": ["source-1"],
        },
        "comparison_status": "established",
        "claims": [
            {
                "claim_id": "claim-1",
                "claim_type": "specification",
                "statement": "Graphite finish",
                "source_ids": ["source-1"],
            }
        ],
        "price_evidence": [
            {
                "price_evidence_id": "price-1",
                "source_id": "source-1",
                "price_value": {"kind": "exact", "amount": 99.99},
                "currency": "USD",
                "price_type": "manufacturer_direct_offer",
                "region": "US",
                "condition": "new",
                "availability": "in_stock",
                "seller_type": "manufacturer",
                "tax_inclusion": "unknown",
                "import_status": "domestic",
            }
        ],
        "sources": [source],
        "uncertainties": [],
        "conflicts": [],
    }


def _search_not_established():
    return {
        "identity_resolution": {
            "status": "unresolved",
            "current_status": "not_established",
            "source_ids": [],
        },
        "comparison_status": "not_established",
        "claims": [],
        "price_evidence": [],
        "sources": [],
        "uncertainties": [
            {
                "uncertainty_id": "uncertainty-1",
                "uncertainty_type": "insufficient_evidence",
                "statement": "No reliable current evidence.",
                "source_ids": [],
            }
        ],
        "conflicts": [],
    }


def _visual():
    return {
        "findings": [
            {
                "category": "visible_condition",
                "observation": "Small scratch on the left edge.",
                "photo_numbers": [1],
            }
        ]
    }


def _assert_invalid(schema_id, value, keyword=None):
    with pytest.raises(CanonicalSchemaValidationError) as caught:
        _registry().validate(schema_id, _canonical(value))
    assert caught.value.validator_id == "canonical_schema_validation"
    assert caught.value.terminal_outcome == "failed_canonical_validation"
    if keyword is not None:
        assert caught.value.keyword == keyword
    return caught.value


def test_registry_pins_exact_frozen_schema_identity_and_inventory():
    registry = _registry()

    assert registry.schema_set_sha256 == OUTPUT_SCHEMA_SET_SHA256
    assert registry.schema_ids == OUTPUT_SCHEMA_IDS == (
        "text_output_schema_v1",
        "retrieval_evidence_bundle_v1",
        "search_output_schema_v1",
        "visual_output_schema_v1",
    )
    assert dict(WORKLOAD_SCHEMA_IDS) == {
        "text_risk_analysis": "text_output_schema_v1",
        "grounded_product_price_research_retrieval": (
            "retrieval_evidence_bundle_v1"
        ),
        "grounded_product_price_research_synthesis": "search_output_schema_v1",
        "visual_inspection": "visual_output_schema_v1",
    }


def test_registry_rejects_hash_dialect_and_inventory_drift():
    for mutation in (
        lambda value: value.__setitem__("json_schema_dialect", "other"),
        lambda value: value["schemas"][0]["schema"].__setitem__("unknown", True),
        lambda value: value["schema_order"].reverse(),
    ):
        artifact = deepcopy(ARTIFACT)
        mutation(artifact)
        with pytest.raises(SchemaContractError):
            CanonicalOutputSchemaRegistry.from_artifact(artifact)


def test_registry_path_loader_rejects_duplicate_keys(tmp_path):
    artifact_path = tmp_path / "duplicate.json"
    artifact_path.write_text('{"schema_version":"1","schema_version":"1"}')

    with pytest.raises(SchemaContractError, match="output_schema_artifact_load"):
        CanonicalOutputSchemaRegistry.from_path(artifact_path)


def test_registry_uses_one_detached_artifact_snapshot(monkeypatch):
    artifact = deepcopy(ARTIFACT)
    original_policy_check = CanonicalOutputSchemaRegistry._validate_format_policy

    def mutate_caller_after_identity(snapshot):
        artifact["schemas"][3]["schema"]["properties"]["findings"]["items"][
            "properties"
        ]["photo_numbers"]["items"]["maximum"] = 999
        original_policy_check(snapshot)

    monkeypatch.setattr(
        CanonicalOutputSchemaRegistry,
        "_validate_format_policy",
        staticmethod(mutate_caller_after_identity),
    )
    registry = CanonicalOutputSchemaRegistry.from_artifact(artifact)
    visual = _visual()
    visual["findings"][0]["photo_numbers"] = [4]

    with pytest.raises(CanonicalSchemaValidationError) as caught:
        registry.validate("visual_output_schema_v1", _canonical(visual))

    assert caught.value.keyword == "maximum"


@pytest.mark.parametrize(
    ("schema_id", "factory"),
    (
        ("text_output_schema_v1", _text),
        ("retrieval_evidence_bundle_v1", _retrieval),
        ("search_output_schema_v1", _search),
        ("search_output_schema_v1", _search_not_established),
        ("visual_output_schema_v1", _visual),
    ),
)
def test_each_frozen_schema_accepts_valid_canonical_candidate(schema_id, factory):
    canonical = _canonical(factory())

    validated = _registry().validate(schema_id, canonical)

    assert validated.schema_id == schema_id
    assert validated.canonical_semantic_json is not canonical
    assert (
        validated.canonical_semantic_json.canonical_bytes
        == canonical.canonical_bytes
    )
    assert validated.schema_set_sha256 == OUTPUT_SCHEMA_SET_SHA256


def test_unknown_schema_id_is_contract_error_not_provider_output_failure():
    with pytest.raises(SchemaContractError, match="unknown_schema_id"):
        _registry().validate("unknown", _canonical(_text()))

    with pytest.raises(SchemaContractError, match="unknown_workload_or_stage"):
        _registry().validate_workload("unknown", _canonical(_text()))


def test_workload_mapping_selects_schema_and_result_cannot_bypass_registry():
    canonical = _canonical(_text())
    validated = _registry().validate_workload("text_risk_analysis", canonical)
    assert validated.schema_id == "text_output_schema_v1"
    with pytest.raises(AttributeError, match="immutable"):
        validated.schema_id = "visual_output_schema_v1"

    with pytest.raises(TypeError, match="requires registry validation"):
        SchemaValidatedCandidate(
            schema_id="text_output_schema_v1",
            schema_sha256="0" * 64,
            schema_set_sha256=OUTPUT_SCHEMA_SET_SHA256,
            canonical_semantic_json=canonical,
        )


def test_registry_and_nested_verified_schema_records_are_immutable():
    registry = _registry()

    with pytest.raises(AttributeError, match="immutable"):
        registry.schema_set_sha256 = "0" * 64
    with pytest.raises(TypeError):
        registry._schemas["text_output_schema_v1"]["schema"]["properties"][
            "risk_level"
        ]["enum"] = ("invalid",)


def test_validation_rejects_fabricated_canonical_identity():
    canonical = _canonical(_text())
    fabricated = CanonicalSemanticJson(
        admitted=canonical.admitted,
        canonical_bytes=b"not-canonical",
        strict_parsed_semantic_payload_hash="0" * 64,
    )

    with pytest.raises(
        SchemaContractError,
        match="canonical_semantic_json_identity",
    ):
        _registry().validate("text_output_schema_v1", fabricated)


def test_validation_rejects_fabricated_admitted_number_identity():
    canonical = _canonical(_visual())
    number = canonical.admitted.value["findings"][0]["photo_numbers"][0]
    canonical.admitted.value["findings"][0]["photo_numbers"][0] = replace(
        number,
        mathematical_integer=False,
    )

    with pytest.raises(
        SchemaContractError,
        match="canonical_semantic_json_identity",
    ):
        _registry().validate("visual_output_schema_v1", canonical)


def test_fabricated_cycle_fails_closed_before_identity_walk():
    canonical = _canonical(_text())
    cycle = []
    cycle.append(cycle)
    canonical.admitted.value["risk_indicators"] = cycle

    with pytest.raises(
        SchemaContractError,
        match="canonical_semantic_json_identity",
    ):
        _registry().validate("text_output_schema_v1", canonical)


def test_validated_candidate_does_not_expose_mutable_canonical_alias():
    canonical = _canonical(_text())
    validated = _registry().validate("text_output_schema_v1", canonical)

    exposed = validated.canonical_semantic_json
    exposed.admitted.value["risk_level"] = "invalid"

    assert canonical.admitted.value["risk_level"] == "low"
    assert validated.canonical_semantic_json.admitted.value["risk_level"] == "low"


def test_validated_snapshot_does_not_reapply_extracted_byte_limit():
    value = _retrieval()
    value["sources"][0]["evidence_items"] = [
        {
            "evidence_id": f"evidence-{index}",
            "evidence_type": "identity",
            "content": "\x00" * 12_000,
        }
        for index in range(23)
    ]
    canonical = canonicalize_semantic_json(NumericDomainAdmission(value))
    assert (
        len(canonical.canonical_bytes)
        > RESOURCE_LIMIT_VALUES["maximum_extracted_semantic_bytes"]
    )
    assert (
        len(canonical.canonical_bytes)
        <= RESOURCE_LIMIT_VALUES["maximum_canonical_payload_bytes"]
    )

    validated = _registry().validate(
        "retrieval_evidence_bundle_v1",
        canonical,
    )

    assert (
        validated.canonical_semantic_json.canonical_bytes
        == canonical.canonical_bytes
    )


def test_canonical_replay_rejects_noncanonical_json_bytes():
    with pytest.raises(ValueError, match="not exact canonical JSON"):
        replay_canonical_semantic_json(b'{"b":1,"a":2}')


def test_mutation_between_identity_and_schema_check_cannot_change_snapshot(
    monkeypatch,
):
    value = _text()
    value["summary"] = ""
    canonical = _canonical(value)
    original_validator = schema_validation._validate_instance
    mutated = False

    def mutate_caller_then_validate(instance, schema, path):
        nonlocal mutated
        if not mutated:
            canonical.admitted.value["summary"] = "made valid too late"
            mutated = True
        return original_validator(instance, schema, path)

    monkeypatch.setattr(
        schema_validation,
        "_validate_instance",
        mutate_caller_then_validate,
    )

    with pytest.raises(CanonicalSchemaValidationError) as caught:
        _registry().validate("text_output_schema_v1", canonical)

    assert caught.value.keyword == "minLength"


@pytest.mark.parametrize(
    ("mutation", "keyword"),
    (
        (lambda value: value.pop("summary"), "required"),
        (lambda value: value.__setitem__("extra", "sentinel"), "additionalProperties"),
        (lambda value: value.__setitem__("summary", 1), "type"),
        (lambda value: value.__setitem__("summary", ""), "minLength"),
        (lambda value: value.__setitem__("risk_level", "LOW"), "enum"),
        (lambda value: value.__setitem__("seller_questions", []), "minItems"),
        (
            lambda value: value.__setitem__("seller_questions", ["x"] * 9),
            "maxItems",
        ),
    ),
)
def test_text_schema_rejects_core_keyword_mutations(mutation, keyword):
    value = _text()
    mutation(value)
    _assert_invalid("text_output_schema_v1", value, keyword)


def test_nested_properties_pattern_and_array_uniqueness_are_enforced():
    retrieval = _retrieval()
    retrieval["sources"][0]["source_id"] = "-bad"
    _assert_invalid("retrieval_evidence_bundle_v1", retrieval, "pattern")

    visual = _visual()
    visual["findings"][0]["observation"] = "   "
    _assert_invalid("visual_output_schema_v1", visual, "pattern")

    visual = _visual()
    visual["findings"][0]["photo_numbers"] = [1, 1]
    _assert_invalid("visual_output_schema_v1", visual, "uniqueItems")

    retrieval = _retrieval()
    retrieval["sources"][0]["evidence_items"][0]["unexpected"] = True
    _assert_invalid(
        "retrieval_evidence_bundle_v1",
        retrieval,
        "additionalProperties",
    )


def test_exact_admitted_numeric_semantics_drive_number_integer_and_minimum():
    visual = _visual()
    raw_visual = json.dumps(visual, separators=(",", ":")).replace("[1]", "[1.0]")
    assert _registry().validate(
        "visual_output_schema_v1",
        normalize_semantic_json(raw_visual.encode()),
    )

    visual["findings"][0]["photo_numbers"] = [1.5]
    _assert_invalid("visual_output_schema_v1", visual, "type")

    search = _search()
    search["price_evidence"][0]["price_value"]["amount"] = -0.01
    _assert_invalid("search_output_schema_v1", search, "oneOf")

    search = _search()
    search["price_evidence"][0]["price_value"]["amount"] = True
    _assert_invalid("search_output_schema_v1", search, "oneOf")


def test_numeric_mathematical_equality_applies_to_unique_items():
    visual = _visual()
    raw = json.dumps(visual, separators=(",", ":")).replace("[1]", "[1,1.0]")

    with pytest.raises(CanonicalSchemaValidationError) as caught:
        _registry().validate(
            "visual_output_schema_v1",
            normalize_semantic_json(raw.encode()),
        )

    assert caught.value.keyword == "uniqueItems"


def test_one_of_const_and_search_conditionals_are_enforced():
    search = _search()
    search["price_evidence"][0]["price_value"] = {
        "kind": "range",
        "minimum": 1,
    }
    _assert_invalid("search_output_schema_v1", search, "oneOf")

    search = _search()
    search["price_evidence"][0]["price_value"] = {
        "kind": "other",
        "amount": 1,
    }
    _assert_invalid("search_output_schema_v1", search, "oneOf")

    established = _search()
    established["claims"] = []
    established["price_evidence"] = []
    _assert_invalid("search_output_schema_v1", established, "anyOf")

    unresolved = _search_not_established()
    unresolved["identity_resolution"]["resolved_product_identity"] = "Invented"
    _assert_invalid("search_output_schema_v1", unresolved, "not")

    missing_reason = _search_not_established()
    missing_reason["uncertainties"][0]["uncertainty_type"] = "regional_ambiguity"
    _assert_invalid("search_output_schema_v1", missing_reason, "contains")


def test_retrieval_status_conditionals_and_string_bounds_are_enforced():
    for status in ("completed", "partial"):
        value = _retrieval()
        value["retrieval_status"] = status
        value["sources"] = []
        _assert_invalid("retrieval_evidence_bundle_v1", value, "minItems")

    no_evidence = _retrieval()
    no_evidence["retrieval_status"] = "no_reliable_evidence"
    no_evidence["sources"] = []
    assert _registry().validate(
        "retrieval_evidence_bundle_v1",
        _canonical(no_evidence),
    )

    at_limit = _retrieval()
    at_limit["sources"][0]["name"] = "x" * 500
    assert _registry().validate(
        "retrieval_evidence_bundle_v1",
        _canonical(at_limit),
    )
    over_limit = _retrieval()
    over_limit["sources"][0]["name"] = "x" * 501
    failure = _assert_invalid(
        "retrieval_evidence_bundle_v1",
        over_limit,
        "maxLength",
    )
    assert failure.path == ("sources", 0, "name")


def test_search_identity_and_partial_comparison_conditionals_are_enforced():
    resolved_without_identity = _search()
    resolved_without_identity["identity_resolution"].pop(
        "resolved_product_identity"
    )
    _assert_invalid("search_output_schema_v1", resolved_without_identity, "required")

    resolved_without_source = _search()
    resolved_without_source["identity_resolution"]["source_ids"] = []
    _assert_invalid("search_output_schema_v1", resolved_without_source, "minItems")

    conflicting_identity = _search_not_established()
    conflicting_identity["identity_resolution"]["status"] = "conflicting"
    conflicting_identity["identity_resolution"]["source_ids"] = ["source-1"]
    _assert_invalid("search_output_schema_v1", conflicting_identity, "minItems")

    conflicting_current = _search()
    conflicting_current["identity_resolution"]["current_status"] = "conflicting"
    _assert_invalid("search_output_schema_v1", conflicting_current, "minItems")

    partial = _search()
    partial["comparison_status"] = "partially_established"
    _assert_invalid("search_output_schema_v1", partial, "anyOf")
    partial["uncertainties"] = [
        {
            "uncertainty_id": "uncertainty-1",
            "uncertainty_type": "regional_ambiguity",
            "statement": "Region remains uncertain.",
            "source_ids": ["source-1"],
        }
    ]
    assert _registry().validate("search_output_schema_v1", _canonical(partial))

    partial["claims"] = []
    partial["price_evidence"] = []
    _assert_invalid("search_output_schema_v1", partial, "anyOf")


def test_valid_price_range_and_photo_number_maximum_boundary():
    search = _search()
    search["price_evidence"][0]["price_value"] = {
        "kind": "range",
        "minimum": 19.99,
        "maximum": 24.99,
    }
    assert _registry().validate("search_output_schema_v1", _canonical(search))

    visual = _visual()
    visual["findings"][0]["photo_numbers"] = [3]
    assert _registry().validate("visual_output_schema_v1", _canonical(visual))
    visual["findings"][0]["photo_numbers"] = [4]
    _assert_invalid("visual_output_schema_v1", visual, "maximum")


@pytest.mark.parametrize(
    "url",
    (
        "https://example.com/path",
        "http://127.0.0.1:8080/path?x=1#fragment",
        "https://[2001:db8::1]/item",
        "https://[v1.alpha:beta]/item",
        "HTTPS://[Vf.alpha:beta]/item",
        "https://[::ffff:192.0.2.128]/item",
        "https://user:pass@example.com:99999/a%20b?q=caf%C3%A9#x%2Fy",
        "https://example.com/a%2Fb",
    ),
)
def test_uri_format_accepts_rfc3986_absolute_http_and_https(url):
    value = _retrieval()
    value["sources"][0]["url"] = url
    assert _registry().validate("retrieval_evidence_bundle_v1", _canonical(value))


@pytest.mark.parametrize(
    "url",
    (
        "/relative/path",
        "ftp://example.com/item",
        "https:///missing-host",
        "https://example.com/%ZZ",
        "https://exa mple.com/item",
        "https://example.com:port/item",
        "https://a@b@example.com/path",
        "https://example.com/[bad]",
        "https://example.com/has|pipe",
        "https://example.com/a^b",
        "https://example.com/?q={x}",
        "https://example.com/café",
        "httpſ://example.com/item",
        "https://[fe80::1%eth0]/item",
        "https://[fe80::1%25eth0]/item",
    ),
)
def test_uri_format_rejects_non_rfc3986_or_non_http_urls(url):
    value = _retrieval()
    value["sources"][0]["url"] = url
    _assert_invalid("retrieval_evidence_bundle_v1", value, "format")


@pytest.mark.parametrize(
    "timestamp",
    (
        "2024-02-29T23:59:59.000Z",
        "2026-08-30T12:34:56.789Z",
        "2016-12-31T23:59:60.999Z",
    ),
)
def test_datetime_format_accepts_canonical_utc_rfc3339_milliseconds(timestamp):
    value = _retrieval()
    value["sources"][0]["retrieved_at"] = timestamp
    assert _registry().validate("retrieval_evidence_bundle_v1", _canonical(value))


@pytest.mark.parametrize(
    "timestamp",
    (
        "2023-02-29T12:34:56.789Z",
        "2026-08-30T24:00:00.000Z",
        "2026-08-30T12:34:56Z",
        "2026-08-30T12:34:56.7890Z",
        "2026-08-30T12:34:56.789z",
        "2026-08-30T12:34:56.789+00:00",
        "2026-06-29T23:59:60.000Z",
    ),
)
def test_datetime_format_rejects_noncanonical_or_invalid_values(timestamp):
    value = _retrieval()
    value["sources"][0]["retrieved_at"] = timestamp
    _assert_invalid("retrieval_evidence_bundle_v1", value, "format")


def test_validation_never_repairs_mutates_or_leaks_provider_values():
    value = _text()
    before = deepcopy(value)
    canonical = _canonical(value)
    validated = _registry().validate("text_output_schema_v1", canonical)

    assert value == before
    assert validated.canonical_semantic_json is not canonical
    assert (
        validated.canonical_semantic_json.canonical_bytes
        == canonical.canonical_bytes
    )

    secret = "provider-secret-do-not-log"
    invalid = _text()
    invalid["summary"] = secret
    invalid[secret] = secret
    failure = _assert_invalid("text_output_schema_v1", invalid)
    assert secret not in str(failure)
    assert secret not in repr(failure)
