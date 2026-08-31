"""Provider-free tests for frozen retrieval trace positions and identifiers."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from app.services.evaluation_contract_identity import load_strict_normalization_spec
from app.services.evaluation_retrieval_trace import (
    RetrievalCanonicalValidationError,
    RetrievalEvidenceObservation,
    PublicSafeDeduplicationKey,
    TRACE_POSITION_FIELDS,
    RetrievalSourceObservation,
    RetrievalIdentifierLimitError,
    RetrievalTraceValidationError,
    RetrievalUrlSecurityValidationError,
    allocate_retrieval_observations,
    derive_public_safe_deduplication_key,
    evidence_observation_key,
    render_evidence_id,
    render_source_id,
    source_observation_key,
    validate_trace_position_inventory,
    validate_trace_ordinal_scope,
)


SPEC_PATH = (
    Path(__file__).parents[2]
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "normalization-parser.v1.json"
)
SPEC = load_strict_normalization_spec(SPEC_PATH)

EXPECTED_POSITION_FIELDS = (
    "retrieval_attempt_ordinal",
    "tool_call_ordinal",
    "result_ordinal",
    "evidence_observation_ordinal",
)


def _origin_rule(
    *,
    scheme: str,
    host_kind: str,
    host: str,
    effective_port: int,
    path: str,
    query_present: bool,
    query: str,
    fragment_present: bool,
    fragment: str,
) -> dict:
    rule = {
        "status": "matched_positive_rule",
        "rule_id": "retrieval-allocation-test-rule",
        "rule_version": "v1",
        "origin_identity": {
            "scheme": scheme,
            "host_kind": host_kind,
            "host": host,
            "effective_port": effective_port,
        },
        "path_match": {"type": "exact_raw_allowlist", "values": [path]},
        "query_match": {
            "type": "exact_presence_and_raw_allowlist",
            "values": [{"present": query_present, "raw": query}],
        },
        "fragment_match": {
            "type": "exact_presence_and_raw_allowlist",
            "values": [{"present": fragment_present, "raw": fragment}],
        },
        "public_shareability_established": True,
        "exact_url_disclosure_grants_access": False,
    }
    envelope = {
        "identity_domain": "trustai.url_origin_rule.v1",
        "rule_id": rule["rule_id"],
        "rule_version": rule["rule_version"],
        "content": rule,
    }
    rule["rule_hash"] = hashlib.sha256(
        json.dumps(
            envelope,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return rule


def _public_safe_inputs(
    exact_url: str,
    *,
    scheme: str = "https",
    host_kind: str = "dns",
    host: str = "catalog.public.example",
    effective_port: int = 443,
    path: str = "/product/widget",
    query_present: bool = False,
    query: str = "",
    fragment_present: bool = False,
    fragment: str = "",
    restricted_reference: str = "rtr-allocation-test",
) -> dict:
    rule = _origin_rule(
        scheme=scheme,
        host_kind=host_kind,
        host=host,
        effective_port=effective_port,
        path=path,
        query_present=query_present,
        query=query,
        fragment_present=fragment_present,
        fragment=fragment,
    )
    member = {
        "position": 0,
        "url_role": "final_url",
        "exact_url": exact_url,
        "retrieval_auth_context": "public_unauthenticated",
        "origin_rule": copy.deepcopy(rule),
        "restricted_trace_reference": restricted_reference,
    }
    return {
        "exact_url": exact_url,
        "url_role": "final_url",
        "retrieval_auth_context": "public_unauthenticated",
        "redirect_context": {
            "capture_status": "no_redirect",
            "current_position": 0,
            "requested_position": 0,
            "final_position": 0,
            "members": [member],
        },
        "origin_rule": rule,
        "restricted_trace_reference": restricted_reference,
    }


def _complete_redirect_inputs(requested_inputs: dict, final_inputs: dict) -> dict:
    requested_member = copy.deepcopy(
        requested_inputs["redirect_context"]["members"][0]
    )
    requested_member.update(position=0, url_role="requested_url")
    final_member = copy.deepcopy(final_inputs["redirect_context"]["members"][0])
    final_member.update(position=1, url_role="final_url")
    return {
        "capture_status": "complete",
        "current_position": 1,
        "requested_position": 0,
        "final_position": 1,
        "members": [requested_member, final_member],
    }


def test_trace_position_inventory_matches_the_frozen_contract():
    policy = SPEC["retrieval_trace_ordering_policy"]

    assert TRACE_POSITION_FIELDS == EXPECTED_POSITION_FIELDS
    assert tuple(policy["position_fields"]) == EXPECTED_POSITION_FIELDS
    assert tuple(policy["source_observation_key"]) == EXPECTED_POSITION_FIELDS[:3]
    assert tuple(policy["evidence_observation_key"]) == EXPECTED_POSITION_FIELDS
    assert policy["ordering"] == (
        "lexicographic ascending over the applicable canonical trace-position tuple"
    )


def test_failure_and_identifier_rules_match_the_frozen_contract():
    trace_policy = SPEC["retrieval_trace_ordering_policy"]
    source_policy = SPEC["source_id_policy"]
    evidence_policy = SPEC["evidence_id_policy"]

    assert trace_policy["common_validation"]["runtime_violation_result"] == (
        RetrievalTraceValidationError.outcome
    )
    assert source_policy["identifier_over_schema_max_length_result"] == (
        RetrievalIdentifierLimitError.outcome
    )
    assert evidence_policy["identifier_over_schema_max_length_result"] == (
        RetrievalIdentifierLimitError.outcome
    )
    assert source_policy["schema_contract"]["maxLength"] == 64
    assert source_policy["schema_contract"]["maximum_decimal_component_digits"] == 60
    assert evidence_policy["schema_contract"]["maxLength"] == 64
    assert evidence_policy["schema_contract"]["maximum_component_digit_sum"] == 60
    assert source_policy["operational_source_count_dependency"].startswith("pending ")
    assert evidence_policy["operational_source_and_evidence_limits"].startswith(
        "pending "
    )


def test_frozen_ordinal_vectors_keep_mapping_and_topology_checks_separate():
    vectors = SPEC["retrieval_trace_ordinal_invariant_test_vectors"]

    assert vectors["provider_calls_required"] is False
    assert vectors["expected_case_count"] == 9
    assert tuple(case["id"] for case in vectors["cases"]) == tuple(
        f"O{index}" for index in range(1, 10)
    )
    assert tuple(case["expected"] for case in vectors["cases"][:8]) == (
        "failed_trace_validation",
    ) * 8
    assert vectors["cases"][8]["expected"] == "topology_preflight_failure"


def test_failed_observations_consume_positions_without_receiving_ids():
    failed_observations = SPEC["retrieval_trace_ordering_policy"][
        "failed_observations"
    ]

    assert failed_observations == {
        "remain_in_retrieval_trace": True,
        "consume_actual_trace_position": True,
        "become_canonical_source": False,
        "receive_source_id": False,
        "become_canonical_evidence": False,
        "receive_evidence_id": False,
        "trace_positions_may_be_recycled_or_renumbered": False,
        "canonical_ids_remain_contiguous_over_successful_canonical_objects": True,
    }


def test_allocation_rules_and_vector_inventories_match_the_frozen_contract():
    key_policy = SPEC["url_policy"]["concepts"]["deduplication_url_key"]
    deduplication_policy = SPEC["source_deduplication_policy"]
    name_policy = SPEC["source_display_name_policy"]
    time_policy = SPEC["retrieved_at_policy"]

    assert key_policy == {
        "allowed_schemes": ["http", "https"],
        "absolute_url_required": True,
        "lowercase_scheme": True,
        "lowercase_host": True,
        "remove_default_port": True,
        "remove_fragment": True,
        "preserve_path_exactly": True,
        "preserve_trailing_slash": True,
        "preserve_query_string_exactly": True,
        "preserve_query_ordering": True,
        "preserve_tracking_parameters": True,
        "preserve_percent_encoding": True,
        "independent_redirect_resolution_allowed": False,
        "relative_url_without_authoritative_captured_base_allowed": False,
        "input_must_be_public_safe": True,
        "sensitive_or_indeterminate_input_allowed": False,
    }
    assert deduplication_policy["same_canonical_key_result"] == (
        "one canonical source"
    )
    assert deduplication_policy["canonical_source_order"] == (
        "ascending earliest_successful_observation source_observation_key"
    )
    assert name_policy["schema_contract"] == {
        "type": "string",
        "minLength": 1,
        "maxLength": 500,
    }
    assert time_policy["timezone"] == "UTC"
    assert time_policy["precision"] == "exactly milliseconds"
    assert time_policy["higher_precision_conversion"] == (
        "truncate toward the earlier millisecond; never round"
    )

    for key, count, prefix in (
        ("retrieval_source_order_test_vectors", 10, "S"),
        ("retrieval_evidence_order_test_vectors", 8, "E"),
        ("retrieval_source_name_time_test_vectors", 8, "N"),
    ):
        vector_set = SPEC[key]
        assert vector_set["provider_calls_required"] is False
        assert vector_set["expected_case_count"] == count
        assert tuple(case["id"] for case in vector_set["cases"]) == tuple(
            f"{prefix}{index}" for index in range(1, count + 1)
        )


@pytest.mark.parametrize("field", EXPECTED_POSITION_FIELDS)
def test_trace_scope_accepts_unique_contiguous_positive_integer_ordinals(field):
    ordinals = [3, 1, 2]

    assert validate_trace_ordinal_scope(field, ordinals) == (3, 1, 2)
    assert ordinals == [3, 1, 2]


@pytest.mark.parametrize("field", EXPECTED_POSITION_FIELDS)
def test_empty_trace_scope_is_vacuously_contiguous(field):
    assert validate_trace_ordinal_scope(field, []) == ()


@pytest.mark.parametrize("value", (0, -1, True, False, 1.0, "1", None))
def test_trace_scope_rejects_non_positive_or_non_integer_ordinals(value):
    with pytest.raises(
        RetrievalTraceValidationError,
        match="failed_trace_validation",
    ):
        validate_trace_ordinal_scope("result_ordinal", [value])


@pytest.mark.parametrize("ordinals", ([1, 1], [1, 3], [2], [1, 2, 4]))
def test_trace_scope_rejects_duplicate_or_gapped_ordinals(ordinals):
    with pytest.raises(
        RetrievalTraceValidationError,
        match="failed_trace_validation",
    ):
        validate_trace_ordinal_scope("result_ordinal", ordinals)


def test_trace_scope_rejects_unknown_field_or_non_sequence_shape():
    with pytest.raises(RetrievalTraceValidationError, match="failed_trace_validation"):
        validate_trace_ordinal_scope("provider_native_id", [1])
    with pytest.raises(RetrievalTraceValidationError, match="failed_trace_validation"):
        validate_trace_ordinal_scope("result_ordinal", None)


def test_source_observation_keys_are_frozen_lexicographic_tuples():
    keys = [
        source_observation_key(2, 1, 1),
        source_observation_key(1, 2, 1),
        source_observation_key(1, 1, 2),
        source_observation_key(1, 1, 1),
    ]

    assert sorted(keys) == [
        (1, 1, 1),
        (1, 1, 2),
        (1, 2, 1),
        (2, 1, 1),
    ]


def test_evidence_observation_keys_are_frozen_lexicographic_tuples():
    keys = [
        evidence_observation_key(1, 1, 1, 2),
        evidence_observation_key(1, 1, 2, 1),
        evidence_observation_key(1, 1, 1, 1),
    ]

    assert sorted(keys) == [
        (1, 1, 1, 1),
        (1, 1, 1, 2),
        (1, 1, 2, 1),
    ]


@pytest.mark.parametrize(
    ("ordinal", "expected"),
    ((1, "src-0001"), (9999, "src-9999"), (10000, "src-10000")),
)
def test_source_id_rendering_uses_minimum_width_four_without_truncation(
    ordinal,
    expected,
):
    assert render_source_id(ordinal) == expected


def test_source_id_enforces_frozen_64_character_representational_capacity():
    sixty_digit_ordinal = 10**59
    assert len(render_source_id(sixty_digit_ordinal)) == 64

    with pytest.raises(
        RetrievalIdentifierLimitError,
        match="failed_resource_limit",
    ):
        render_source_id(10**60)


@pytest.mark.parametrize(
    ("source_ordinal", "evidence_ordinal", "expected"),
    (
        (1, 1, "ev-0001-0001"),
        (10000, 1, "ev-10000-0001"),
        (10000, 10000, "ev-10000-10000"),
    ),
)
def test_evidence_id_rendering_uses_each_canonical_ordinal(
    source_ordinal,
    evidence_ordinal,
    expected,
):
    assert render_evidence_id(source_ordinal, evidence_ordinal) == expected


def test_evidence_id_enforces_frozen_combined_64_character_capacity():
    thirty_digit = 10**29
    assert len(render_evidence_id(thirty_digit, thirty_digit)) == 64

    with pytest.raises(
        RetrievalIdentifierLimitError,
        match="failed_resource_limit",
    ):
        render_evidence_id(10**30, thirty_digit)


@pytest.mark.parametrize("value", (0, -1, True, False, 1.0, "1", None))
def test_identifier_rendering_rejects_non_positive_or_non_integer_ordinals(value):
    with pytest.raises(
        RetrievalTraceValidationError,
        match="failed_trace_validation",
    ):
        render_source_id(value)
    with pytest.raises(
        RetrievalTraceValidationError,
        match="failed_trace_validation",
    ):
        render_evidence_id(1, value)


def test_representational_capacity_does_not_impose_an_operational_count_cap():
    assert render_source_id(10000) == "src-10000"
    assert render_evidence_id(10000, 10000) == "ev-10000-10000"


def test_public_safe_deduplication_key_applies_only_the_frozen_transformations():
    inputs = _public_safe_inputs(
        "HTTPS://CATALOG.PUBLIC.EXAMPLE:443/product/%7ewidget"
        "?b=2&a=1&utm_source=search#section",
        path="/product/%7ewidget",
        query_present=True,
        query="b=2&a=1&utm_source=search",
        fragment_present=True,
        fragment="section",
    )

    key = derive_public_safe_deduplication_key(**inputs)

    assert key.value == (
        "https://catalog.public.example/product/%7ewidget"
        "?b=2&a=1&utm_source=search"
    )


def test_deduplication_key_preserves_empty_path_query_presence_and_nondefault_port():
    absent_query = derive_public_safe_deduplication_key(
        **_public_safe_inputs(
            "https://catalog.public.example:8443",
            effective_port=8443,
            path="",
        )
    )
    empty_query = derive_public_safe_deduplication_key(
        **_public_safe_inputs(
            "https://catalog.public.example:8443?",
            effective_port=8443,
            path="",
            query_present=True,
        )
    )

    assert absent_query.value == "https://catalog.public.example:8443"
    assert empty_query.value == "https://catalog.public.example:8443?"
    assert absent_query != empty_query


def test_deduplication_key_preserves_ipv6_spelling_except_ascii_case():
    key = derive_public_safe_deduplication_key(
        **_public_safe_inputs(
            "HTTPS://[2001:0DB8:0:0:0:0:0:1]:443/product/widget",
            host_kind="ipv6",
            host="2001:db8::1",
        )
    )

    assert key.value == "https://[2001:0db8:0:0:0:0:0:1]/product/widget"


def test_complete_redirect_key_is_bound_to_the_public_safe_final_member():
    requested = _public_safe_inputs(
        "https://catalog.public.example/product/widget?ref=requested",
        query_present=True,
        query="ref=requested",
        restricted_reference="rtr-requested",
    )
    final = _public_safe_inputs(
        "https://catalog.public.example/product/widget?offer=final",
        query_present=True,
        query="offer=final",
        restricted_reference="rtr-final",
    )
    redirect_context = _complete_redirect_inputs(requested, final)
    final["redirect_context"] = redirect_context

    key = derive_public_safe_deduplication_key(**final)

    assert key.value == (
        "https://catalog.public.example/product/widget?offer=final"
    )
    assert key.safe_canonical_url == final["exact_url"]
    assert key.restricted_trace_reference == "rtr-final"

    requested["redirect_context"] = redirect_context
    requested["url_role"] = "requested_url"
    with pytest.raises(
        RetrievalUrlSecurityValidationError,
        match="failed_url_security_validation",
    ):
        derive_public_safe_deduplication_key(**requested)


def test_deduplication_key_fails_closed_without_public_safe_classification():
    inputs = _public_safe_inputs(
        "https://catalog.public.example/product/widget?sig=SYNTHETIC",
        query_present=True,
        query="sig=SYNTHETIC",
    )

    with pytest.raises(
        RetrievalUrlSecurityValidationError,
        match="failed_url_security_validation",
    ):
        derive_public_safe_deduplication_key(**inputs)

    assert RetrievalUrlSecurityValidationError.outcome == (
        "failed_url_security_validation"
    )


def test_public_safe_key_cannot_be_constructed_through_the_normal_api():
    with pytest.raises(
        RetrievalUrlSecurityValidationError,
        match="failed_url_security_validation",
    ):
        PublicSafeDeduplicationKey("https://catalog.public.example/product/widget")


def test_validated_deduplication_key_is_immutable_and_hash_stable():
    key = derive_public_safe_deduplication_key(
        **_public_safe_inputs("https://catalog.public.example/product/widget")
    )
    original_hash = hash(key)

    with pytest.raises(
        AttributeError,
        match="public_safe_deduplication_key_is_immutable",
    ):
        key._value = "https://attacker.invalid/"  # type: ignore[misc]
    with pytest.raises(
        AttributeError,
        match="public_safe_deduplication_key_is_immutable",
    ):
        del key._value

    assert key.value == "https://catalog.public.example/product/widget"
    assert hash(key) == original_hash


def _source(
    key,
    trace_key,
    *,
    name,
    captured_at,
    successful=True,
):
    return RetrievalSourceObservation(
        retrieval_attempt_ordinal=trace_key[0],
        tool_call_ordinal=trace_key[1],
        result_ordinal=trace_key[2],
        successful=successful,
        deduplication_key=key,
        name=name,
        captured_at=captured_at,
    )


def _evidence(key, trace_key, *, successful=True):
    return RetrievalEvidenceObservation(
        retrieval_attempt_ordinal=trace_key[0],
        tool_call_ordinal=trace_key[1],
        result_ordinal=trace_key[2],
        evidence_observation_ordinal=trace_key[3],
        successful=successful,
        source_deduplication_key=key,
    )


def _allocate(sources, evidence):
    attempts = sorted({item.retrieval_attempt_ordinal for item in sources})
    tools_by_attempt = {
        attempt: sorted(
            {
                item.tool_call_ordinal
                for item in sources
                if item.retrieval_attempt_ordinal == attempt
            }
        )
        for attempt in attempts
    }
    results_by_tool_call = {
        (attempt, tool): sorted(
            {
                item.result_ordinal
                for item in sources
                if item.retrieval_attempt_ordinal == attempt
                and item.tool_call_ordinal == tool
            }
        )
        for attempt in attempts
        for tool in tools_by_attempt[attempt]
    }
    evidence_by_result = {
        (
            source.retrieval_attempt_ordinal,
            source.tool_call_ordinal,
            source.result_ordinal,
        ): sorted(
            {
                item.evidence_observation_ordinal
                for item in evidence
                if item.retrieval_attempt_ordinal
                == source.retrieval_attempt_ordinal
                and item.tool_call_ordinal == source.tool_call_ordinal
                and item.result_ordinal == source.result_ordinal
            }
        )
        for source in sources
    }
    inventory = validate_trace_position_inventory(
        retrieval_attempt_ordinals=attempts,
        tool_call_ordinals_by_attempt=tools_by_attempt,
        result_ordinals_by_tool_call=results_by_tool_call,
        evidence_ordinals_by_result=evidence_by_result,
    )
    return allocate_retrieval_observations(inventory, sources, evidence)


def test_trace_inventory_rejects_gaps_and_boolean_parent_keys():
    with pytest.raises(RetrievalTraceValidationError, match="failed_trace_validation"):
        validate_trace_position_inventory(
            retrieval_attempt_ordinals=[1],
            tool_call_ordinals_by_attempt={1: [1]},
            result_ordinals_by_tool_call={(1, 1): [2]},
            evidence_ordinals_by_result={(1, 1, 2): []},
        )

    with pytest.raises(RetrievalTraceValidationError, match="failed_trace_validation"):
        validate_trace_position_inventory(
            retrieval_attempt_ordinals=[1],
            tool_call_ordinals_by_attempt={True: [1]},
            result_ordinals_by_tool_call={(1, 1): [1]},
            evidence_ordinals_by_result={(1, 1, 1): []},
        )


def test_allocation_filters_failed_observations_only_after_complete_trace_validation():
    key = derive_public_safe_deduplication_key(
        **_public_safe_inputs("https://catalog.public.example/product/widget")
    )
    sources = (
        _source(
            None,
            (1, 1, 1),
            name=None,
            captured_at=None,
            successful=False,
        ),
        _source(
            key,
            (1, 1, 2),
            name="Example",
            captured_at=datetime(2026, 8, 30, tzinfo=UTC),
        ),
    )
    evidence = (
        _evidence(None, (1, 1, 1, 1), successful=False),
        _evidence(key, (1, 1, 2, 1)),
    )

    plan = _allocate(sources, evidence)

    assert tuple(source.source_id for source in plan.sources) == ("src-0001",)
    assert plan.sources[0].earliest_observation_key == (1, 1, 2)
    assert tuple(item.evidence_id for item in plan.evidence) == ("ev-0001-0001",)
    assert plan.evidence[0].observation_key == (1, 1, 2, 1)


def test_failed_observations_require_absent_canonical_url_keys():
    invalid_failed_source = _source(
        "caller-asserted-key",
        (1, 1, 1),
        name=None,
        captured_at=None,
        successful=False,
    )
    with pytest.raises(RetrievalTraceValidationError, match="failed_trace_validation"):
        _allocate((invalid_failed_source,), ())

    failed_source = _source(
        None,
        (1, 1, 1),
        name=None,
        captured_at=None,
        successful=False,
    )
    invalid_failed_evidence = _evidence(
        "caller-asserted-key",
        (1, 1, 1, 1),
        successful=False,
    )
    with pytest.raises(RetrievalTraceValidationError, match="failed_trace_validation"):
        _allocate((failed_source,), (invalid_failed_evidence,))


def test_allocation_requires_exact_observation_coverage_for_validated_inventory():
    inventory = validate_trace_position_inventory(
        retrieval_attempt_ordinals=[1],
        tool_call_ordinals_by_attempt={1: [1]},
        result_ordinals_by_tool_call={(1, 1): [1, 2]},
        evidence_ordinals_by_result={(1, 1, 1): [], (1, 1, 2): []},
    )
    key = derive_public_safe_deduplication_key(
        **_public_safe_inputs("https://catalog.public.example/product/widget")
    )
    incomplete = (
        _source(
            key,
            (1, 1, 2),
            name="Example",
            captured_at=datetime(2026, 8, 30, tzinfo=UTC),
        ),
    )

    with pytest.raises(RetrievalTraceValidationError, match="failed_trace_validation"):
        allocate_retrieval_observations(inventory, incomplete, ())


def test_allocation_deduplicates_orders_and_assigns_contiguous_ids():
    key_a = derive_public_safe_deduplication_key(
        **_public_safe_inputs("https://catalog.public.example/product/widget")
    )
    key_b = derive_public_safe_deduplication_key(
        **_public_safe_inputs(
            "https://catalog.public.example/product/widget?offer=2",
            query_present=True,
            query="offer=2",
        )
    )
    earliest_a = datetime(
        2026,
        8,
        30,
        12,
        34,
        56,
        789987,
        tzinfo=UTC,
    )
    sources = (
        _source(
            key_a,
            (2, 1, 1),
            name="Later qualifying name",
            captured_at=datetime(2026, 8, 30, 13, tzinfo=UTC),
        ),
        _source(
            key_b,
            (1, 1, 1),
            name="  Exact Store  ",
            captured_at=datetime(2026, 8, 30, 14, tzinfo=UTC),
        ),
        _source(
            key_a,
            (1, 2, 1),
            name="",
            captured_at=earliest_a,
        ),
    )
    evidence = (
        _evidence(key_a, (2, 1, 1, 2)),
        _evidence(key_b, (1, 1, 1, 1)),
        _evidence(key_a, (1, 2, 1, 1)),
        _evidence(key_a, (2, 1, 1, 1)),
    )

    plan = _allocate(sources, evidence)

    assert tuple(source.source_id for source in plan.sources) == (
        "src-0001",
        "src-0002",
    )
    assert plan.sources[0].deduplication_url_key == key_b.value
    assert plan.sources[0].display_name == "  Exact Store  "
    assert plan.sources[1].deduplication_url_key == key_a.value
    assert plan.sources[1].earliest_observation_key == (1, 2, 1)
    assert plan.sources[1].display_name == "Later qualifying name"
    assert plan.sources[1].selected_name_observation_key == (2, 1, 1)
    assert plan.sources[1].retrieved_at == "2026-08-30T12:34:56.789Z"
    assert tuple(item.evidence_id for item in plan.evidence) == (
        "ev-0001-0001",
        "ev-0002-0001",
        "ev-0002-0002",
        "ev-0002-0003",
    )
    assert tuple(item.observation_key for item in plan.evidence) == (
        (1, 1, 1, 1),
        (1, 2, 1, 1),
        (2, 1, 1, 1),
        (2, 1, 1, 2),
    )


def test_earliest_trace_context_is_independent_of_input_iteration_order():
    earliest_key = derive_public_safe_deduplication_key(
        **_public_safe_inputs(
            "https://catalog.public.example/product/widget",
            restricted_reference="rtr-earliest",
        )
    )
    later_key = derive_public_safe_deduplication_key(
        **_public_safe_inputs(
            "https://catalog.public.example/product/widget#later",
            fragment_present=True,
            fragment="later",
            restricted_reference="rtr-later",
        )
    )
    assert earliest_key == later_key
    sources = (
        _source(
            later_key,
            (1, 1, 2),
            name="Selected Later Name",
            captured_at=datetime(2026, 8, 30, 13, tzinfo=UTC),
        ),
        _source(
            earliest_key,
            (1, 1, 1),
            name="",
            captured_at=datetime(2026, 8, 30, 12, tzinfo=UTC),
        ),
    )

    plan = _allocate(sources, ())

    assert plan.sources[0].url_trace_reference == "rtr-earliest"
    assert plan.sources[0].safe_canonical_url == (
        "https://catalog.public.example/product/widget"
    )
    assert plan.sources[0].selected_name_observation_key == (1, 1, 2)
    assert plan.sources[0].display_name == "Selected Later Name"
    assert plan.sources[0].url_security_policy_identity == (
        "url_security_policy_v1",
        "v1",
        "fcc37b299f84cccb7522c2db150022e3e92f04430c50e01b94bb7f7fa6e5b44e",
    )


def test_retrieved_at_converts_to_utc_and_truncates_toward_earlier_millisecond():
    key = derive_public_safe_deduplication_key(
        **_public_safe_inputs("https://catalog.public.example/product/widget")
    )
    east = timezone(timedelta(hours=5, minutes=30))
    plan = _allocate(
        (
            _source(
                key,
                (1, 1, 1),
                name="Example",
                captured_at=datetime(
                    2026,
                    8,
                    30,
                    18,
                    4,
                    56,
                    789987,
                    tzinfo=east,
                ),
            ),
        ),
        (_evidence(key, (1, 1, 1, 1)),),
    )

    assert plan.sources[0].retrieved_at == "2026-08-30T12:34:56.789Z"


def test_allocation_rejects_duplicate_source_and_evidence_trace_keys():
    key = derive_public_safe_deduplication_key(
        **_public_safe_inputs("https://catalog.public.example/product/widget")
    )
    source = _source(
        key,
        (1, 1, 1),
        name="Example",
        captured_at=datetime(2026, 8, 30, tzinfo=UTC),
    )
    evidence = _evidence(key, (1, 1, 1, 1))

    with pytest.raises(RetrievalTraceValidationError, match="failed_trace_validation"):
        _allocate((source, source), (evidence,))
    with pytest.raises(RetrievalTraceValidationError, match="failed_trace_validation"):
        _allocate((source,), (evidence, evidence))


def test_allocation_rejects_evidence_not_backed_by_a_matching_source_observation():
    key_a = derive_public_safe_deduplication_key(
        **_public_safe_inputs("https://catalog.public.example/product/widget")
    )
    key_b = derive_public_safe_deduplication_key(
        **_public_safe_inputs(
            "https://catalog.public.example/product/widget?offer=2",
            query_present=True,
            query="offer=2",
        )
    )
    source = _source(
        key_a,
        (1, 1, 1),
        name="Example",
        captured_at=datetime(2026, 8, 30, tzinfo=UTC),
    )

    with pytest.raises(RetrievalTraceValidationError, match="failed_trace_validation"):
        _allocate(
            (source,),
            (_evidence(key_b, (1, 1, 1, 1)),),
        )
    with pytest.raises(RetrievalTraceValidationError, match="failed_trace_validation"):
        _allocate(
            (source,),
            (_evidence(key_a, (1, 1, 2, 1)),),
        )


def test_allocation_fails_when_no_successful_observation_has_a_schema_valid_name():
    key = derive_public_safe_deduplication_key(
        **_public_safe_inputs("https://catalog.public.example/product/widget")
    )
    observations = (
        _source(
            key,
            (1, 1, 1),
            name="",
            captured_at=datetime(2026, 8, 30, tzinfo=UTC),
        ),
        _source(
            key,
            (1, 1, 2),
            name="x" * 501,
            captured_at=datetime(2026, 8, 30, tzinfo=UTC),
        ),
    )

    with pytest.raises(
        RetrievalCanonicalValidationError,
        match="failed_canonical_validation",
    ):
        _allocate(
            observations,
            (_evidence(key, (1, 1, 1, 1)),),
        )


def test_allocation_rejects_naive_or_non_datetime_harness_capture_instants():
    key = derive_public_safe_deduplication_key(
        **_public_safe_inputs("https://catalog.public.example/product/widget")
    )
    for value in (datetime(2026, 8, 30), "2026-08-30T00:00:00.000Z"):
        with pytest.raises(
            RetrievalTraceValidationError,
            match="failed_trace_validation",
        ):
            _allocate(
                (
                    _source(
                        key,
                        (1, 1, 1),
                        name="Example",
                        captured_at=value,
                    ),
                ),
                (_evidence(key, (1, 1, 1, 1)),),
            )
