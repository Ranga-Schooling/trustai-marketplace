"""Cross-language conformance for the frozen semantic numeric domain."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from app.services.evaluation_resource_limits import ResourceLimitExceededError
from app.services.normalization_parser import (
    NumericDomainError,
    StrictJsonPayloadError,
    admit_exact_json_number,
    convert_exact_decimal_to_binary64,
    parse_strict_json_payload,
)
import app.services.normalization_parser as parser


pytestmark = pytest.mark.contract

ARTIFACT_DIRECTORY = (
    Path(__file__).parents[2] / "docs" / "testing" / "ai-evaluation"
)
SPEC_PATH = ARTIFACT_DIRECTORY / "normalization-parser.v1.json"
REFERENCE_PATH = (
    Path(__file__).parent / "reference" / "semantic_numeric_reference.mjs"
)
SPEC = json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _exact_decimal_key(value) -> str:
    representation = value.as_tuple()
    coefficient = int("".join(str(digit) for digit in representation.digits) or "0")
    exponent = representation.exponent
    if coefficient == 0:
        return "0e0"
    while coefficient % 10 == 0:
        coefficient //= 10
        exponent += 1
    sign = "-" if representation.sign else ""
    return f"{sign}{coefficient}e{exponent}"


def _python_analysis(lexeme: str) -> dict:
    try:
        parsed = parse_strict_json_payload(lexeme.encode("ascii"))
    except ResourceLimitExceededError as exc:
        return {
            "json_valid": None,
            "numeric_domain_eligible": False,
            "terminal_outcome": "failed_resource_limit",
            "resource_limit": exc.limit_name,
        }
    except StrictJsonPayloadError:
        return {
            "json_valid": False,
            "numeric_domain_eligible": False,
            "terminal_outcome": "failed_strict_parse",
        }

    number = parsed.value
    try:
        admitted = admit_exact_json_number(number)
    except NumericDomainError as exc:
        result = {
            "json_valid": True,
            "numeric_domain_eligible": False,
            "terminal_outcome": "failed_canonical_validation",
            "safe_reason": exc.reason,
            "exact_decimal_key": _exact_decimal_key(number.exact_decimal),
        }
        if exc.reason != "negative_zero":
            converted = convert_exact_decimal_to_binary64(number.exact_decimal)
            result["binary64_bits"] = f"{converted.bits:016x}"
            if exc.reason == "decimal_round_trip_changed":
                result["ordinary_jcs_representation"] = (
                    parser._jcs_number_from_binary64(converted.value)
                )
        return result

    return {
        "json_valid": True,
        "numeric_domain_eligible": True,
        "exact_decimal_key": _exact_decimal_key(admitted.exact_decimal),
        "binary64_bits": f"{admitted.binary64_bits:016x}",
        "jcs_numeric_representation": admitted.jcs_numeric_representation,
        "mathematical_integer": admitted.mathematical_integer,
    }


@pytest.fixture(scope="module")
def javascript_reference() -> dict:
    node = shutil.which("node")
    assert node is not None, "Node is required for the independent reference"
    completed = subprocess.run(
        (node, str(REFERENCE_PATH), str(SPEC_PATH)),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    return json.loads(completed.stdout)


def test_reference_is_independent_provider_free_and_covers_all_vectors(
    javascript_reference,
):
    source = REFERENCE_PATH.read_text(encoding="utf-8")
    assert javascript_reference["implementation_id"] == (
        "semantic_numeric_bigint_javascript_reference_v1"
    )
    suites = SPEC["semantic_numeric_domain_test_vectors"]["suites"]
    vector_results = javascript_reference["vector_results"]
    assert len(vector_results) == 68
    assert sum(suite["expected_case_count"] for suite in suites.values()) == 68
    assert {
        suite_name: sum(
            result["suite"] == suite_name for result in vector_results
        )
        for suite_name in suites
    } == {
        suite_name: suite["expected_case_count"]
        for suite_name, suite in suites.items()
    }
    identities = tuple((result["suite"], result["id"]) for result in vector_results)
    assert len(identities) == len(set(identities))
    assert SPEC["semantic_numeric_domain_policy"]["resource_limit_interface"][
        "exact_thresholds"
    ] == {
        name: SPEC["resource_limit_policy"]["required_limits"][name]
        for name in (
            "maximum_numeric_lexeme_length",
            "maximum_numeric_significand_or_coefficient_digits",
            "maximum_absolute_decimal_exponent_magnitude",
        )
    }
    assert "BigInt" in source
    assert "from app" not in source
    assert "fetch(" not in source
    assert "https://" not in source
    assert "Number(lexeme)" not in source
    assert "JSON.parse(lexeme)" not in source


def test_python_and_javascript_agree_on_every_frozen_numeric_lexeme(
    javascript_reference,
):
    javascript_results = javascript_reference["lexeme_results"]

    assert javascript_results
    assert {
        lexeme: _python_analysis(lexeme) for lexeme in javascript_results
    } == javascript_results


def test_javascript_results_match_all_68_frozen_vector_expectations(
    javascript_reference,
):
    results = {
        (item["suite"], item["id"]): item["result"]
        for item in javascript_reference["vector_results"]
    }
    suites = SPEC["semantic_numeric_domain_test_vectors"]["suites"]

    for suite_name, suite in suites.items():
        for case in suite["cases"]:
            result = results[(suite_name, case["id"])]
            if suite_name in {"number_vectors", "negative_zero_vectors"}:
                assert result["numeric_domain_eligible"] is case[
                    "numeric_domain_eligible"
                ]
                if case["numeric_domain_eligible"]:
                    assert result["jcs_numeric_representation"] == case[
                        "jcs_numeric_representation"
                    ]
                else:
                    assert result["safe_reason"] == case["safe_reason"]
                    assert result["terminal_outcome"] == (
                        "failed_canonical_validation"
                    )
            elif suite_name == "price_vectors":
                assert result["numeric_domain_eligible"] is case[
                    "numeric_domain_eligible"
                ]
                if "exact_decimal_ordering" in case:
                    assert result["exact_decimal_ordering"] == case[
                        "exact_decimal_ordering"
                    ]
                elif case["numeric_domain_eligible"]:
                    assert result["jcs_numeric_representation"] == case[
                        "jcs_numeric_representation"
                    ]
                else:
                    assert result["safe_reason"] == case["safe_reason"]
                    assert result["terminal_outcome"] == case["terminal_outcome"]
            elif suite_name == "hash_equality_vectors":
                expected = case.get(
                    "accepted_semantic_hash_equality_result",
                    case.get("semantic_hashes_equal"),
                )
                assert result["accepted_semantic_hash_equality_result"] is expected
            elif suite_name == "native_sdk_numeric_vectors":
                expected = case.get(
                    "expected_equivalence",
                    case.get("expected_equivalence_result"),
                )
                assert result["equivalence"] == expected
            elif suite_name == "integer_boolean_vectors":
                if "schema_integer_valid" in case:
                    assert result["schema_integer_valid"] is case[
                        "schema_integer_valid"
                    ]
                if "numeric_domain_eligible" in case:
                    assert result["numeric_domain_eligible"] is case[
                        "numeric_domain_eligible"
                    ]
                if "mathematical_integer" in case:
                    assert result["mathematical_integer"] is case[
                        "mathematical_integer"
                    ]
                if "schema_maximum_3_valid" in case:
                    assert result["schema_maximum_3_valid"] is case[
                        "schema_maximum_3_valid"
                    ]
                if "terminal_outcome" in case:
                    assert result["terminal_outcome"] == case["terminal_outcome"]
            elif case["id"] == "J10":
                assert result == {
                    "json_valid": True,
                    "json_type": "string",
                    "numeric_coercion_allowed": False,
                    "number_required_terminal_outcome": "failed_canonical_validation",
                }
            else:
                assert result["terminal_outcome"] == case[
                    "expected_terminal_outcome"
                ]


def test_both_references_enforce_frozen_numeric_resource_boundaries(
    javascript_reference,
):
    probes = javascript_reference["resource_probe_results"]
    expected = {
        "lexeme_limit": None,
        "lexeme_limit_plus_one": "maximum_numeric_lexeme_length",
        "coefficient_limit": None,
        "coefficient_limit_plus_one": (
            "maximum_numeric_significand_or_coefficient_digits"
        ),
        "exponent_limit": None,
        "exponent_limit_plus_one": (
            "maximum_absolute_decimal_exponent_magnitude"
        ),
        "invalid_leading_zero_coefficient_plus_one": (
            "maximum_numeric_significand_or_coefficient_digits"
        ),
        "invalid_nonnumeric_over_lexeme_limit": None,
        "malformed_coefficient_over_limit": (
            "maximum_numeric_significand_or_coefficient_digits"
        ),
        "malformed_lexeme_over_limit": "maximum_numeric_lexeme_length",
        "malformed_exponent_over_limit": (
            "maximum_absolute_decimal_exponent_magnitude"
        ),
        "malformed_double_sign_coefficient_over_limit": (
            "maximum_numeric_significand_or_coefficient_digits"
        ),
    }

    for probe_id, limit_name in expected.items():
        if limit_name is None:
            assert probes[probe_id].get("resource_limit") is None
        else:
            assert probes[probe_id]["resource_limit"] == limit_name

    python_probes = {
        "lexeme_limit": _python_analysis("1e" + ("0" * 16_382)),
        "lexeme_limit_plus_one": _python_analysis("1e" + ("0" * 16_383)),
        "coefficient_limit": _python_analysis("0." + ("0" * 8_191)),
        "coefficient_limit_plus_one": _python_analysis("0." + ("0" * 8_192)),
        "exponent_limit": _python_analysis("1e32768"),
        "exponent_limit_plus_one": _python_analysis("1e32769"),
        "invalid_leading_zero_coefficient_plus_one": _python_analysis("0" * 8_193),
        "invalid_nonnumeric_over_lexeme_limit": _python_analysis("x" * 16_385),
        "malformed_coefficient_over_limit": _python_analysis(
            ("0" * 8_193) + ".."
        ),
        "malformed_lexeme_over_limit": _python_analysis("1." * 9_000),
        "malformed_exponent_over_limit": _python_analysis("1e32769e"),
        "malformed_double_sign_coefficient_over_limit": _python_analysis(
            "--" + ("0" * 8_193)
        ),
    }
    assert python_probes == probes


def test_invalid_nonnumeric_input_does_not_become_a_numeric_resource_failure(
    javascript_reference,
):
    expected = {
        "json_valid": False,
        "numeric_domain_eligible": False,
        "terminal_outcome": "failed_strict_parse",
    }
    assert javascript_reference["resource_probe_results"][
        "invalid_nonnumeric_over_lexeme_limit"
    ] == expected
    assert _python_analysis("x" * 16_385) == expected


def test_javascript_binary64_rounding_handles_frozen_edge_classes(
    javascript_reference,
):
    probes = javascript_reference["binary64_probe_results"]
    expected_bits = {
        "positive_zero": "0000000000000000",
        "one": "3ff0000000000000",
        "negative": "bff8000000000000",
        "halfway_ties_to_even_lower": "3ff0000000000000",
        "halfway_ties_to_even_upper": "3ff0000000000002",
        "minimum_subnormal": "0000000000000001",
        "maximum_finite": "7fefffffffffffff",
        "positive_overflow": "7ff0000000000000",
        "subnormal_to_normal_midpoint": "0010000000000000",
        "finite_to_infinity_immediately_below": "7fefffffffffffff",
        "finite_to_infinity_midpoint": "7ff0000000000000",
    }

    assert set(probes) == set(expected_bits)
    for probe_id, expected in expected_bits.items():
        probe = probes[probe_id]
        assert probe["analysis"]["binary64_bits"] == expected
        assert probe["analysis"] == _python_analysis(probe["lexeme"])
