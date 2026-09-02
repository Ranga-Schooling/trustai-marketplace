"""Focused tests for provider-neutral structured AI response validation."""

from __future__ import annotations

import copy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.schemas import AIAnalysisResult, Recommendation, RiskLevel
from app.services.ai_response_validation import (
    AI_RESPONSE_RESOURCE_LIMITS,
    AnalysisStructureError,
    DeterministicValidationError,
    DuplicateJsonKeyError,
    ExactJsonNumber,
    ResourceLimitExceededError,
    StrictJsonPayloadError,
    StrictJsonSyntaxError,
    StrictUtf8DecodeError,
    parse_strict_json_payload,
    require_exact_analysis_shape,
    validate_analysis_cross_fields,
)


pytestmark = pytest.mark.contract


EXPECTED_RESOURCE_LIMITS = {
    "maximum_extracted_semantic_bytes": 1_048_576,
    "maximum_json_nesting_depth": 32,
    "maximum_object_members": 64,
    "maximum_total_object_members": 16_384,
    "maximum_array_elements": 1_024,
    "maximum_total_array_elements": 4_096,
    "maximum_single_string_bytes": 131_072,
    "maximum_total_string_bytes": 524_288,
    "maximum_numeric_lexeme_length": 16_384,
    "maximum_numeric_significand_or_coefficient_digits": 8_192,
    "maximum_absolute_decimal_exponent_magnitude": 32_768,
}


def _analysis_payload(
    *severities: str,
    risk_level: str = "low",
    recommendation: str = "buy",
    price_plausibility: str = "plausible",
) -> dict:
    return {
        "summary": "Synthetic assessment.",
        "risk_level": risk_level,
        "risk_indicators": [
            {
                "category": f"indicator_{index}",
                "severity": severity,
                "explanation": "Synthetic listing evidence.",
            }
            for index, severity in enumerate(severities, start=1)
        ],
        "price_assessment": "Current pricing was not independently verified.",
        "price_plausibility": price_plausibility,
        "seller_questions": ["Can I inspect the item before paying?"],
        "recommendation": recommendation,
    }


def _schema_validate(candidate: dict) -> AIAnalysisResult:
    exact = require_exact_analysis_shape(candidate)
    result = AIAnalysisResult.model_validate(exact)
    validate_analysis_cross_fields(result.model_dump(mode="json"))
    return result


def test_strict_parser_accepts_utf8_json_without_losing_number_identity():
    parsed = parse_strict_json_payload(
        '{"label":"café","count":1.50,"enabled":true}'.encode()
    )

    assert parsed.value == {
        "label": "café",
        "count": ExactJsonNumber("1.50", Decimal("1.50")),
        "enabled": True,
    }


def test_response_resource_limit_inventory_matches_proven_subset():
    assert AI_RESPONSE_RESOURCE_LIMITS == EXPECTED_RESOURCE_LIMITS


def test_strict_parser_rejects_invalid_utf8():
    with pytest.raises(StrictUtf8DecodeError, match="strict UTF-8"):
        parse_strict_json_payload(b'{"summary":"\xff"}')


@pytest.mark.parametrize("payload", (b"{", b'{"a":}', b"[1,]"))
def test_strict_parser_rejects_malformed_json(payload):
    with pytest.raises(StrictJsonSyntaxError, match="strict JSON"):
        parse_strict_json_payload(payload)


def test_strict_parser_rejects_duplicate_decoded_keys():
    with pytest.raises(DuplicateJsonKeyError, match="Duplicate JSON object key"):
        parse_strict_json_payload(b'{"risk_level":"low","risk_level":"high"}')


def test_strict_parser_rejects_trailing_json_content():
    with pytest.raises(StrictJsonSyntaxError, match="strict JSON"):
        parse_strict_json_payload(b'{"ok":true}{"extra":true}')


@pytest.mark.parametrize(
    ("payload", "expected"),
    (
        (b"{}", {}),
        (b"[]", []),
        (b" true ", True),
        (b"false", False),
        (b"null", None),
        (b'"\\u00e9\\ud83d\\ude00"', "é😀"),
    ),
)
def test_strict_parser_accepts_json_scalar_and_empty_container_forms(
    payload,
    expected,
):
    assert parse_strict_json_payload(payload).value == expected


@pytest.mark.parametrize(
    "payload",
    (
        b'"raw\x01control"',
        b'"\\x"',
        b'"\\u12"',
        b'"\\u12xz"',
        b'"\\ud800"',
        b'"\\ud800\\u0041"',
        b'"\\udc00"',
        b"01",
        b"-",
        b"1.",
        b"1e",
    ),
)
def test_strict_parser_rejects_additional_rfc8259_violations(payload):
    with pytest.raises(StrictJsonSyntaxError):
        parse_strict_json_payload(payload)


@pytest.mark.parametrize("constant", (b"NaN", b"Infinity", b"-Infinity"))
def test_strict_parser_rejects_nonfinite_numbers(constant):
    with pytest.raises(StrictJsonSyntaxError):
        parse_strict_json_payload(b'{"value":' + constant + b"}")


def test_strict_parser_rejects_payload_over_byte_limit():
    limit = AI_RESPONSE_RESOURCE_LIMITS["maximum_extracted_semantic_bytes"]

    with pytest.raises(ResourceLimitExceededError) as caught:
        parse_strict_json_payload(b" " * (limit + 1))

    assert caught.value.limit_name == "maximum_extracted_semantic_bytes"
    assert str(caught.value) == "failed_resource_limit"


def test_strict_parser_accepts_maximum_nesting_depth():
    depth = AI_RESPONSE_RESOURCE_LIMITS["maximum_json_nesting_depth"]

    assert parse_strict_json_payload(("[" * depth + "]" * depth).encode()).value


def test_strict_parser_rejects_excessive_nesting_before_materialization():
    depth = AI_RESPONSE_RESOURCE_LIMITS["maximum_json_nesting_depth"] + 1

    with pytest.raises(ResourceLimitExceededError) as caught:
        parse_strict_json_payload(("[" * depth + "]" * depth).encode())

    assert caught.value.limit_name == "maximum_json_nesting_depth"


@pytest.mark.parametrize(
    ("payload", "limit_name"),
    (
        (
            b"{" + b",".join(f'\"k{i}\":0'.encode() for i in range(65)) + b"}",
            "maximum_object_members",
        ),
        (b"[" + b",".join(b"0" for _ in range(1_025)) + b"]", "maximum_array_elements"),
        (b'"' + b"a" * 131_073 + b'"', "maximum_single_string_bytes"),
        (b"1e" + b"0" * 16_383, "maximum_numeric_lexeme_length"),
    ),
    ids=("object-members", "array-elements", "single-string", "numeric-lexeme"),
)
def test_strict_parser_enforces_proven_structural_limits(payload, limit_name):
    with pytest.raises(ResourceLimitExceededError) as caught:
        parse_strict_json_payload(payload)

    assert caught.value.limit_name == limit_name


@pytest.mark.parametrize(
    ("payload", "limit_name"),
    (
        (
            (
                "["
                + ",".join(
                    "{" + ",".join(f'\"k{i}\":0' for i in range(64)) + "}"
                    for _ in range(257)
                )
                + "]"
            ).encode(),
            "maximum_total_object_members",
        ),
        (
            (
                "{"
                + ",".join(
                    f'\"a{i}\":[' + ",".join("0" for _ in range(1_024)) + "]"
                    for i in range(5)
                )
                + "}"
            ).encode(),
            "maximum_total_array_elements",
        ),
        (
            (
                "["
                + ",".join(
                    f'\"{character * 131_072}\"' for character in "abcde"
                )
                + "]"
            ).encode(),
            "maximum_total_string_bytes",
        ),
        (b"0." + b"0" * 8_192, "maximum_numeric_significand_or_coefficient_digits"),
        (b"1e32769", "maximum_absolute_decimal_exponent_magnitude"),
    ),
    ids=(
        "total-object-members",
        "total-array-elements",
        "total-string-bytes",
        "numeric-coefficient",
        "decimal-exponent",
    ),
)
def test_strict_parser_enforces_proven_aggregate_and_numeric_limits(
    payload,
    limit_name,
):
    with pytest.raises(ResourceLimitExceededError) as caught:
        parse_strict_json_payload(payload)

    assert caught.value.limit_name == limit_name


def test_strict_parser_requires_bytes_and_known_resource_limit_names():
    with pytest.raises(TypeError, match="must be bytes"):
        parse_strict_json_payload("{}")
    with pytest.raises(ValueError, match="unknown_resource_limit"):
        ResourceLimitExceededError("not_a_limit")


@pytest.mark.parametrize(
    "payload",
    (
        b'{"private-provider-prose":',
        b'{"private-provider-prose":"one","private-provider-prose":"two"}',
    ),
)
def test_strict_parser_errors_do_not_echo_provider_content(payload):
    with pytest.raises(StrictJsonPayloadError) as caught:
        parse_strict_json_payload(payload)

    assert "private-provider-prose" not in str(caught.value)


def test_exact_analysis_shape_accepts_pydantic_contract():
    result = _schema_validate(_analysis_payload())

    assert result.risk_level is RiskLevel.low
    assert result.recommendation is Recommendation.buy


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload.update({"unexpected": "provider-owned"}),
        lambda payload: payload.pop("summary"),
        lambda payload: payload.update({"risk_indicators": "not-a-list"}),
        lambda payload: payload["risk_indicators"][0].update(
            {"unexpected": "provider-owned"}
        ),
    ),
)
def test_exact_analysis_shape_rejects_missing_extra_or_wrong_structure(mutation):
    payload = _analysis_payload("low")
    mutation(payload)

    with pytest.raises(AnalysisStructureError, match="analysis_result_shape"):
        require_exact_analysis_shape(payload)


def test_pydantic_contract_rejects_unsupported_price_relation():
    payload = require_exact_analysis_shape(
        _analysis_payload(price_plausibility="approximately_plausible")
    )

    with pytest.raises(ValidationError):
        AIAnalysisResult.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    (
        _analysis_payload(),
        _analysis_payload("low", "low"),
        _analysis_payload("medium", risk_level="medium", recommendation="caution"),
        _analysis_payload("low", "high", risk_level="high", recommendation="avoid"),
    ),
)
def test_cross_field_validator_accepts_consistent_results(payload):
    original = copy.deepcopy(payload)

    assert validate_analysis_cross_fields(payload) is None
    assert payload == original


@pytest.mark.parametrize(
    ("payload", "reason"),
    (
        (_analysis_payload("medium"), "risk_level_indicator_mismatch"),
        (
            _analysis_payload("high", risk_level="medium", recommendation="caution"),
            "risk_level_indicator_mismatch",
        ),
        (
            _analysis_payload("low", risk_level="low", recommendation="avoid"),
            "risk_recommendation_mismatch",
        ),
    ),
)
def test_cross_field_validator_rejects_contradictions_without_repair(payload, reason):
    original = copy.deepcopy(payload)

    with pytest.raises(DeterministicValidationError, match=reason) as caught:
        validate_analysis_cross_fields(payload)

    assert caught.value.validator_id == "text_cross_field_validator_v1"
    assert caught.value.terminal_outcome == "failed_cross_field_validation"
    assert payload == original


def test_valid_benign_and_scam_results_are_accepted():
    benign = _schema_validate(_analysis_payload())
    scam = _schema_validate(
        _analysis_payload("high", risk_level="high", recommendation="avoid")
    )

    assert benign.risk_level is RiskLevel.low
    assert scam.risk_level is RiskLevel.high


def test_validation_is_deterministic_and_never_returns_partial_success():
    malformed = b'{"summary":"private-provider-prose"'
    failures = []

    for _ in range(3):
        with pytest.raises(StrictJsonSyntaxError) as caught:
            parse_strict_json_payload(malformed)
        failures.append((type(caught.value), str(caught.value)))

    assert failures == [failures[0]] * 3
    assert "private-provider-prose" not in failures[0][1]
