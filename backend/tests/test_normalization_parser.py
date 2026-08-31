"""Executable boundary for the frozen normalization semantic core.

The committed parser artifact is the semantic authority.  Structural tests
remain useful before implementation exists; functional cases invoke the
provider-neutral production primitives without provider or network access.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from decimal import Decimal, ROUND_CEILING, localcontext
from pathlib import Path
import socket
import struct
import urllib.request

import pytest


pytestmark = pytest.mark.contract

SPEC_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "testing"
    / "ai-evaluation"
    / "normalization-parser.v1.json"
)
SPEC_ID = "normalization_parser_spec_v1"
SPEC_VERSION = "v1"
HASHER_MODULE = "app.services.normalization_parser"
HASHER_NAME = "hash_raw_provider_response"
STRICT_PARSER_NAME = "parse_strict_json_payload"
NUMBER_ADMITTER_NAME = "admit_exact_json_number"
DOMAIN_ADMITTER_NAME = "admit_semantic_numeric_domain"
CANONICALIZER_NAME = "canonicalize_semantic_json"
PIPELINE_NAME = "normalize_semantic_json"
EMPTY_SHA256 = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def _load_spec() -> dict:
    return json.loads(
        SPEC_PATH.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite,
    )


SPEC = _load_spec()
RAW_HASH_VECTORS = tuple(SPEC["raw_hash_nullability_test_vectors"]["cases"])
TRANSPORT_VECTORS = tuple(SPEC["transport_boundary_test_vectors"]["cases"])


def _load_hasher():
    try:
        module = importlib.import_module(HASHER_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name == HASHER_MODULE:
            pytest.fail(
                "Missing raw-response hash implementation: expected "
                f"{HASHER_MODULE}.{HASHER_NAME}",
                pytrace=False,
            )
        raise
    hasher = getattr(module, HASHER_NAME, None)
    if not callable(hasher):
        pytest.fail(
            "Missing raw-response hash callable: expected "
            f"{HASHER_MODULE}.{HASHER_NAME}",
            pytrace=False,
        )
    return hasher


def _load_strict_parser():
    module = importlib.import_module(HASHER_MODULE)
    parser = getattr(module, STRICT_PARSER_NAME, None)
    if not callable(parser):
        pytest.fail(
            "Missing strict JSON parser callable:\n"
            f"{HASHER_MODULE}.{STRICT_PARSER_NAME}",
            pytrace=False,
        )
    return parser


def _load_semantic_core():
    module = importlib.import_module(HASHER_MODULE)
    names = (
        NUMBER_ADMITTER_NAME,
        DOMAIN_ADMITTER_NAME,
        CANONICALIZER_NAME,
        PIPELINE_NAME,
    )
    callables = tuple(getattr(module, name, None) for name in names)
    missing = [name for name, value in zip(names, callables) if not callable(value)]
    if missing:
        pytest.fail(
            "Missing normalization semantic-core callables: " + ", ".join(missing),
            pytrace=False,
        )
    return module, *callables


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*_args, **_kwargs):
        pytest.fail("Raw-response hashing attempted external access", pytrace=False)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket, "getaddrinfo", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    monkeypatch.setattr(socket.socket, "connect_ex", fail_network)
    monkeypatch.setattr(urllib.request, "urlopen", fail_network)

    original_getenv = os.getenv

    def guarded_getenv(key, default=None):
        if any(
            token in key.upper()
            for token in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
        ):
            pytest.fail(
                f"Raw-response hashing attempted secret environment discovery: {key}",
                pytrace=False,
            )
        return original_getenv(key, default)

    monkeypatch.setattr(os, "getenv", guarded_getenv)


def _invoke_hasher(raw_response: bytes, monkeypatch: pytest.MonkeyPatch) -> str:
    _deny_external_access(monkeypatch)
    hasher = _load_hasher()
    return hasher(raw_response)


def _invoke_strict_parser(payload: bytes, monkeypatch: pytest.MonkeyPatch):
    _deny_external_access(monkeypatch)
    return _load_strict_parser()(payload)


def _strict_value(parsed):
    return getattr(parsed, "value", parsed)


def _number_field(number, name):
    if isinstance(number, dict) and name in number:
        return number[name]
    return getattr(number, name, None)


def _assert_exact_number(parsed, expected_lexeme: str):
    number = _strict_value(parsed)
    lexeme = _number_field(number, "lexeme")
    exact_decimal = _number_field(number, "exact_decimal")

    assert lexeme == expected_lexeme
    assert isinstance(exact_decimal, Decimal)
    assert exact_decimal == Decimal(expected_lexeme)
    return exact_decimal


PARSER_FAILURE_IDENTITIES = {
    "utf8": ({"utf8", "failed_utf8_decode"}, "StrictUtf8DecodeError"),
    "json_syntax": (
        {"json_syntax", "failed_strict_parse"},
        "StrictJsonSyntaxError",
    ),
    "duplicate_key": (
        {"duplicate_key", "failed_duplicate_key"},
        "DuplicateJsonKeyError",
    ),
}


def _assert_parser_failure(payload, expected_category, monkeypatch):
    parser = _load_strict_parser()
    _deny_external_access(monkeypatch)

    with pytest.raises(Exception) as caught:
        parser(payload)

    accepted_categories, accepted_class_name = PARSER_FAILURE_IDENTITIES[
        expected_category
    ]
    category = getattr(caught.value, "category", None)
    if category is None:
        assert type(caught.value).__name__ == accepted_class_name
    else:
        assert category in accepted_categories


def test_strict_parser_policy_identity_is_frozen():
    assert SPEC["artifact_id"] == SPEC_ID
    assert SPEC["normalization_spec_version"] == SPEC_VERSION
    assert SPEC["strict_json_policy"]["policy_id"] == "strict_json_policy_v1"
    assert (
        SPEC["semantic_numeric_domain_policy"]["policy_id"]
        == "semantic_numeric_domain_policy_v1"
    )


def test_strict_parser_stage_order_is_frozen():
    assert SPEC["semantic_numeric_domain_policy"]["canonicalization_order"] == [
        "capture raw provider response identity under P1 #2",
        "extract designated semantic representation",
        "enforce applicable pre-parse resource limits",
        "strict UTF-8 decode",
        "strict JSON syntax validation and duplicate-key detection",
        "build lexeme-preserving exact semantic parse tree",
        "construct unfiltered canonical-validation candidate",
        "validate every numeric lexeme and value under semantic_numeric_domain_policy_v1",
        "only after all numbers pass generate RFC 8785/JCS semantic representation",
        "compute strict-parsed and candidate semantic hashes as applicable",
        "apply Draft 2020-12 JSON Schema and active format assertions",
        "apply deterministic cross-field, trace, and evidence validators",
        "finalize accepted semantic or bundle hash",
    ]


def test_strict_parsing_actions_are_observation_validation_only():
    actions = SPEC["normalization_action_vocabulary"]

    assert actions["disposition_classification"]["decode_strict_utf8"] == (
        "observation_validation_only"
    )
    assert actions["disposition_classification"]["parse_strict_json_text"] == (
        "observation_validation_only"
    )
    assert actions["semantic_repair_action_allowed"] is False


def test_duplicate_detection_requires_complete_valid_syntax_first():
    strict_policy = SPEC["strict_json_policy"]
    reducer = SPEC["first_terminal_condition_reducer"]

    assert strict_policy["duplicate_key_policy"] == "reject_at_every_object_depth"
    assert strict_policy["duplicate_detection_timing"] == (
        "before ordinary object construction can collapse duplicate values"
    )
    assert reducer["duplicate_detection_requires_syntactically_valid_document"] is True
    assert reducer["strict_json_error_precedence"] == {
        "invalid_utf8": "failed_utf8_decode",
        "syntactically_invalid_json": "failed_strict_parse",
        "syntactically_valid_json_with_duplicate_member_names": (
            "failed_duplicate_key"
        ),
        "valid_duplicate_free_json": "continue",
    }


def test_exact_numeric_parse_requires_lexeme_and_decimal_value():
    numeric_policy = SPEC["semantic_numeric_domain_policy"]
    terms = numeric_policy["terminology"]
    exact_parse = numeric_policy["lexeme_preserving_exact_parse"]

    assert "exact RFC 8259 JSON token" in terms["numeric_lexeme"]
    assert "exact mathematical base-10 value" in terms["exact_decimal_value"]
    assert exact_parse["required"] is True
    assert exact_parse["result"] == "exact_decimal_value"
    assert exact_parse["rounding_allowed"] is False
    assert exact_parse["exact_components"] == [
        "sign",
        "integer coefficient",
        "fraction",
        "base-10 exponent",
    ]


def test_numeric_admission_jcs_and_schema_remain_later_stages():
    numeric_policy = SPEC["semantic_numeric_domain_policy"]
    integration = numeric_policy["canonical_validation_integration"]
    parsed_term = SPEC["terminology"]["terms"]["strict_parsed_semantic_payload"]

    assert integration["subphase_order"] == [
        "numeric-domain validation",
        "JCS semantic canonicalization availability",
        "Draft 2020-12 JSON Schema validation",
        "active format assertions",
    ]
    assert integration["numeric_failure_strict_parse_state"] == "completed"
    assert "before numeric-domain admission" in parsed_term["definition"]
    assert "only after every contained number passes" in parsed_term["hash_requirement"]


def test_parser_resource_thresholds_remain_pending_and_execution_blocking():
    resource_policy = SPEC["resource_limit_policy"]
    required_limits = resource_policy["required_limits"]

    assert resource_policy["status"] == "pending_numeric_freeze"
    assert resource_policy["provider_calls_blocked_while_pending"] is True
    assert resource_policy["numeric_limit_thresholds_frozen_here"] is False
    assert required_limits
    assert all(value is None for value in required_limits.values())


UTF8_CASES = (
    pytest.param(b"{}", "pass", {}, id="ascii-json"),
    pytest.param('"caf\u00e9"'.encode(), "pass", "caf\u00e9", id="multibyte"),
    pytest.param(
        '"\ufffd"'.encode(),
        "pass",
        "\ufffd",
        id="legitimate-replacement-scalar",
    ),
    pytest.param(b'"\xe2(\xa1"', "utf8", None, id="invalid-continuation"),
    pytest.param(b'"\xe2\x82', "utf8", None, id="truncated-multibyte"),
    pytest.param(b'"\xc0\xaf"', "utf8", None, id="overlong-encoding"),
    pytest.param(b'"\xed\xa0\x80"', "utf8", None, id="encoded-surrogate"),
    pytest.param(b"\xef\xbb\xbf{}", "json_syntax", None, id="utf8-bom"),
    pytest.param(b'"a\x00b"', "json_syntax", None, id="raw-nul"),
)


@pytest.mark.parametrize(("payload", "expected", "expected_value"), UTF8_CASES)
def test_parse_strict_json_payload_utf8_boundaries(
    payload,
    expected,
    expected_value,
    monkeypatch,
):
    if expected == "pass":
        parsed = _invoke_strict_parser(payload, monkeypatch)
        assert _strict_value(parsed) == expected_value
    else:
        _assert_parser_failure(payload, expected, monkeypatch)


JSON_GRAMMAR_CASES = (
    pytest.param(b"{}", "pass", {}, id="object"),
    pytest.param(b"[]", "pass", [], id="array"),
    pytest.param(b'"string"', "pass", "string", id="string"),
    pytest.param(b"123", "number", "123", id="number"),
    pytest.param(b"true", "pass", True, id="true"),
    pytest.param(b"false", "pass", False, id="false"),
    pytest.param(b"null", "pass", None, id="null"),
    pytest.param(b" \t\r\n{} \t\r\n", "pass", {}, id="allowed-whitespace"),
    pytest.param(
        b'"line\\nquote\\\"slash\\\\tab\\t"',
        "pass",
        'line\nquote"slash\\tab\t',
        id="valid-escapes",
    ),
    pytest.param(
        b'"\\uD834\\uDD1E"',
        "pass",
        "\U0001d11e",
        id="valid-surrogate-pair",
    ),
    pytest.param(b"", "json_syntax", None, id="empty"),
    pytest.param(b" \t\r\n", "json_syntax", None, id="whitespace-only"),
    pytest.param(b"/* comment */ {}", "json_syntax", None, id="comment"),
    pytest.param(b'{"a":1,}', "json_syntax", None, id="trailing-comma"),
    pytest.param(b"{'a':1}", "json_syntax", None, id="single-quotes"),
    pytest.param(b"{} []", "json_syntax", None, id="multiple-values"),
    pytest.param(b"{} trailing", "json_syntax", None, id="trailing-content"),
    pytest.param(b"+1", "json_syntax", None, id="leading-plus"),
    pytest.param(b"01", "json_syntax", None, id="leading-zero"),
    pytest.param(b"0x10", "json_syntax", None, id="hexadecimal"),
    pytest.param(b"1_000", "json_syntax", None, id="numeric-separator"),
    pytest.param(b"NaN", "json_syntax", None, id="nan"),
    pytest.param(b"Infinity", "json_syntax", None, id="infinity"),
    pytest.param(b"-Infinity", "json_syntax", None, id="negative-infinity"),
    pytest.param(b'{"a":', "json_syntax", None, id="incomplete-object"),
    pytest.param(b"[1,", "json_syntax", None, id="incomplete-array"),
    pytest.param(b'"\\x20"', "json_syntax", None, id="invalid-escape"),
    pytest.param(b'"line\nbreak"', "json_syntax", None, id="raw-control"),
)


@pytest.mark.parametrize(
    ("payload", "expected", "expected_value"), JSON_GRAMMAR_CASES
)
def test_parse_strict_json_payload_rfc8259_grammar(
    payload,
    expected,
    expected_value,
    monkeypatch,
):
    if expected == "pass":
        parsed = _invoke_strict_parser(payload, monkeypatch)
        assert _strict_value(parsed) == expected_value
    elif expected == "number":
        parsed = _invoke_strict_parser(payload, monkeypatch)
        _assert_exact_number(parsed, expected_value)
    else:
        _assert_parser_failure(payload, expected, monkeypatch)


DUPLICATE_CASES = (
    pytest.param(b'{"a":1,"a":2}', "duplicate_key", id="simple"),
    pytest.param(
        b'{"a":1,"\\u0061":2}',
        "duplicate_key",
        id="escaped-equivalent",
    ),
    pytest.param(
        b'{"outer":{"a":1,"a":2}}',
        "duplicate_key",
        id="nested",
    ),
    pytest.param(
        '{"\u00e9":1,"e\\u0301":2}'.encode(),
        "distinct_keys",
        id="composed-decomposed-distinct",
    ),
    pytest.param(
        b'{"x":{"a":1,"a":2},"bad":}',
        "json_syntax",
        id="syntax-precedes-duplicate",
    ),
    pytest.param(
        b'{"a":1,"a":1e309}',
        "duplicate_key",
        id="duplicate-precedes-numeric-domain",
    ),
)


@pytest.mark.parametrize(("payload", "expected"), DUPLICATE_CASES)
def test_parse_strict_json_payload_duplicate_keys(payload, expected, monkeypatch):
    if expected == "distinct_keys":
        parsed = _invoke_strict_parser(payload, monkeypatch)
        value = _strict_value(parsed)
        assert list(value) == ["\u00e9", "e\u0301"]
        assert list(value)[0] != list(value)[1]
    else:
        _assert_parser_failure(payload, expected, monkeypatch)


NUMBER_VECTORS = tuple(
    pytest.param(case["input_lexeme"], id=case["id"])
    for case in SPEC["semantic_numeric_domain_test_vectors"]["suites"][
        "number_vectors"
    ]["cases"]
)
NEGATIVE_ZERO_VECTORS = tuple(
    pytest.param(case["input_lexeme"], id=case["id"])
    for case in SPEC["semantic_numeric_domain_test_vectors"]["suites"][
        "negative_zero_vectors"
    ]["cases"]
)
EXTRA_LEXEME_VECTORS = (
    pytest.param("1E+0", id="exact-uppercase-positive-exponent"),
    pytest.param("19.990", id="exact-trailing-zero-price"),
)
NUMERIC_EXACTNESS_CASES = (
    *NUMBER_VECTORS,
    *NEGATIVE_ZERO_VECTORS,
    *EXTRA_LEXEME_VECTORS,
)


@pytest.mark.parametrize("lexeme", NUMERIC_EXACTNESS_CASES)
def test_parse_strict_json_payload_preserves_exact_numbers(lexeme, monkeypatch):
    parsed = _invoke_strict_parser(lexeme.encode("ascii"), monkeypatch)
    exact_decimal = _assert_exact_number(parsed, lexeme)

    assert exact_decimal.is_finite()
    if lexeme in {"1e-324", "1e-400"}:
        assert exact_decimal != 0


@pytest.mark.parametrize("lexeme", ("-0", "-0.0", "-0e0", "-0E+10"))
def test_parse_strict_json_payload_retains_negative_zero(lexeme, monkeypatch):
    parsed = _invoke_strict_parser(lexeme.encode("ascii"), monkeypatch)
    exact_decimal = _assert_exact_number(parsed, lexeme)

    assert exact_decimal.is_zero()
    assert exact_decimal.is_signed()


@pytest.mark.parametrize("lexeme", ("1e309", "1e-400"))
def test_parse_strict_json_payload_retains_extreme_exponents(lexeme, monkeypatch):
    parsed = _invoke_strict_parser(lexeme.encode("ascii"), monkeypatch)
    exact_decimal = _assert_exact_number(parsed, lexeme)

    assert exact_decimal.is_finite()
    assert exact_decimal != 0


UNICODE_CASES = (
    pytest.param(
        b'{"value":"\\uD834\\uDD1E"}',
        "pass_pair",
        id="valid-pair-value",
    ),
    pytest.param(
        b'{"value":"\\uD800"}',
        "json_syntax",
        id="unpaired-high-value",
    ),
    pytest.param(
        b'{"value":"\\uDC00"}',
        "json_syntax",
        id="unpaired-low-value",
    ),
    pytest.param(
        b'{"\\uD800":"value"}',
        "json_syntax",
        id="unpaired-high-key",
    ),
    pytest.param(
        '["\u00e9","e\\u0301"]'.encode(),
        "distinct_strings",
        id="no-unicode-normalization",
    ),
)


@pytest.mark.parametrize(("payload", "expected"), UNICODE_CASES)
def test_parse_strict_json_payload_unicode_scalars(payload, expected, monkeypatch):
    if expected == "pass_pair":
        parsed = _invoke_strict_parser(payload, monkeypatch)
        assert _strict_value(parsed) == {"value": "\U0001d11e"}
    elif expected == "distinct_strings":
        parsed = _invoke_strict_parser(payload, monkeypatch)
        assert _strict_value(parsed) == ["\u00e9", "e\u0301"]
        assert _strict_value(parsed)[0] != _strict_value(parsed)[1]
    else:
        _assert_parser_failure(payload, expected, monkeypatch)


FIRST_FAILURE_CASES = (
    pytest.param(
        b'{"a":1,"a":2,\xff',
        "utf8",
        None,
        id="utf8-before-json",
    ),
    pytest.param(
        b'{"x":{"a":1,"a":2},"bad":}',
        "json_syntax",
        None,
        id="syntax-before-duplicate",
    ),
    pytest.param(
        b'{"a":1,"a":1e309}',
        "duplicate_key",
        None,
        id="duplicate-before-numeric-domain",
    ),
    pytest.param(b"-0", "pass_number", "-0", id="negative-zero-parses"),
    pytest.param(b"1e309", "pass_number", "1e309", id="overflow-parses"),
)


@pytest.mark.parametrize(("payload", "expected", "lexeme"), FIRST_FAILURE_CASES)
def test_parse_strict_json_payload_first_failure_precedence(
    payload,
    expected,
    lexeme,
    monkeypatch,
):
    if expected == "pass_number":
        parsed = _invoke_strict_parser(payload, monkeypatch)
        _assert_exact_number(parsed, lexeme)
    else:
        _assert_parser_failure(payload, expected, monkeypatch)


@pytest.mark.parametrize(
    "payload",
    (
        pytest.param("{}", id="str"),
        pytest.param(bytearray(b"{}"), id="bytearray"),
        pytest.param(memoryview(b"{}"), id="memoryview"),
        pytest.param(None, id="none"),
    ),
)
def test_parse_strict_json_payload_requires_exact_bytes(payload, monkeypatch):
    parser = _load_strict_parser()
    _deny_external_access(monkeypatch)

    with pytest.raises(TypeError):
        parser(payload)


def test_raw_response_hash_policy_identity_is_frozen():
    raw_policy = SPEC["raw_response_policy"]
    hashing_policy = SPEC["hashing_policy"]

    assert SPEC["artifact_id"] == SPEC_ID
    assert SPEC["normalization_spec_version"] == SPEC_VERSION
    assert SPEC["provider_neutral"] is True
    assert raw_policy["hash_algorithm"] == "SHA-256"
    assert raw_policy["canonical_raw_hash"] == "SHA-256 of raw_provider_response"
    assert hashing_policy["algorithm"] == "SHA-256"
    assert hashing_policy["encoding"] == "lowercase hexadecimal"
    assert hashing_policy["hashes"]["raw_provider_response_hash"]["input"].startswith(
        "exact raw_provider_response:"
    )


def test_raw_hash_vector_inventory_is_frozen():
    vector_set = SPEC["raw_hash_nullability_test_vectors"]
    ids = [vector["id"] for vector in RAW_HASH_VECTORS]

    assert vector_set["test_vector_set_id"] == "raw_hash_nullability_vectors_v1"
    assert vector_set["provider_calls_required"] is False
    assert vector_set["expected_case_count"] == 10
    assert len(RAW_HASH_VECTORS) == 10
    assert ids == [f"RH{number}" for number in range(1, 11)]
    assert len(ids) == len(set(ids))


def test_transport_boundary_inventory_supports_raw_hash_contract():
    vector_set = SPEC["transport_boundary_test_vectors"]
    by_id = {vector["id"]: vector for vector in TRANSPORT_VECTORS}

    assert vector_set["test_vector_set_id"] == "transport_to_semantic_boundary_vectors_v1"
    assert vector_set["provider_calls_required"] is False
    assert vector_set["expected_case_count"] == 14
    assert len(TRANSPORT_VECTORS) == 14
    assert len(by_id) == 14
    assert "raw_provider_response_hash are identical" in by_id["T1"]["expected"]
    assert "raw_provider_response_hash matches" in by_id["T2"]["expected"]
    assert "raw_provider_response_hash are identical" in by_id["T3"]["expected"]
    assert by_id["T11"]["expected"] == "failed_strict_parse"
    assert by_id["T12"]["expected"] == "failed_strict_parse"


def test_empty_body_vector_freezes_sha256_digest():
    rh2 = next(vector for vector in RAW_HASH_VECTORS if vector["id"] == "RH2")

    assert "zero-length byte sequence" in rh2["case"]
    assert EMPTY_SHA256 in rh2["expected"]
    assert "raw_provider_response_hash is required" in rh2["expected"]


EXACT_BYTE_CASES = (
    pytest.param(b"", EMPTY_SHA256, id="empty-rh2"),
    pytest.param(b"a", hashlib.sha256(b"a").hexdigest(), id="ascii-byte"),
    pytest.param(b"\x00", hashlib.sha256(b"\x00").hexdigest(), id="nul-byte"),
    pytest.param(b"\xff", hashlib.sha256(b"\xff").hexdigest(), id="non-utf8-byte"),
    pytest.param(
        b"\xef\xbf\xbd",
        hashlib.sha256(b"\xef\xbf\xbd").hexdigest(),
        id="utf8-replacement-character-bytes",
    ),
    pytest.param(
        "café".encode("utf-8"),
        hashlib.sha256("café".encode("utf-8")).hexdigest(),
        id="utf8-textual-bytes",
    ),
)


@pytest.mark.parametrize(("raw_response", "expected_digest"), EXACT_BYTE_CASES)
def test_hash_raw_provider_response_hashes_exact_bytes(
    raw_response,
    expected_digest,
    monkeypatch,
):
    result = _invoke_hasher(raw_response, monkeypatch)

    assert result == expected_digest
    assert len(result) == 64
    assert result == result.lower()
    assert set(result) <= set("0123456789abcdef")


def test_hash_raw_provider_response_does_not_silently_encode_text(monkeypatch):
    _deny_external_access(monkeypatch)
    hasher = _load_hasher()

    with pytest.raises(TypeError):
        hasher("a")


SEMANTIC_VECTOR_SUITES = SPEC["semantic_numeric_domain_test_vectors"]["suites"]
NUMBER_DOMAIN_CASES = tuple(
    pytest.param(case, id=case["id"])
    for suite_name in ("number_vectors", "negative_zero_vectors")
    for case in SEMANTIC_VECTOR_SUITES[suite_name]["cases"]
)
PRICE_AMOUNT_CASES = tuple(
    pytest.param(case, id=case["id"])
    for case in SEMANTIC_VECTOR_SUITES["price_vectors"]["cases"]
    if case["id"] in {"P1", "P2", "P3", "P4", "P7", "P8"}
)


def _parse_number(lexeme: str, monkeypatch: pytest.MonkeyPatch):
    parsed = _invoke_strict_parser(lexeme.encode("ascii"), monkeypatch)
    number = _strict_value(parsed)
    assert _number_field(number, "lexeme") == lexeme
    return number


def _assert_numeric_failure(call, expected_reason: str):
    with pytest.raises(Exception) as caught:
        call()

    assert type(caught.value).__name__ == "NumericDomainError"
    assert getattr(caught.value, "category", None) == "numeric_domain_ineligible"
    assert getattr(caught.value, "reason", None) == expected_reason


def _price_lexeme(case: dict) -> str:
    return case["input"].removeprefix("exact amount ")


def test_semantic_numeric_vector_inventory_is_frozen():
    vector_set = SPEC["semantic_numeric_domain_test_vectors"]
    expected_counts = {
        "number_vectors": 19,
        "negative_zero_vectors": 7,
        "price_vectors": 8,
        "hash_equality_vectors": 8,
        "native_sdk_numeric_vectors": 8,
        "integer_boolean_vectors": 8,
        "json_numeric_syntax_vectors": 10,
    }

    assert vector_set["expected_total_case_count"] == 68
    assert set(SEMANTIC_VECTOR_SUITES) == set(expected_counts)
    assert sum(expected_counts.values()) == 68
    for name, count in expected_counts.items():
        suite = SEMANTIC_VECTOR_SUITES[name]
        assert suite["expected_case_count"] == count
        assert len(suite["cases"]) == count

    assert SPEC["semantic_numeric_domain_policy"]["failure_mapping"][
        "safe_subordinate_reasons"
    ] == [
        "negative_zero",
        "binary64_overflow_nonfinite",
        "nonzero_underflow_to_zero",
        "decimal_round_trip_changed",
    ]


@pytest.mark.parametrize("case", NUMBER_DOMAIN_CASES)
def test_admit_exact_json_number_matches_frozen_number_vectors(case, monkeypatch):
    module, admit_number, *_rest = _load_semantic_core()
    _deny_external_access(monkeypatch)
    number = _parse_number(case["input_lexeme"], monkeypatch)

    if case["numeric_domain_eligible"]:
        admitted = admit_number(number)
        assert isinstance(admitted, module.AdmittedJsonNumber)
        assert admitted.lexeme == case["input_lexeme"]
        assert admitted.exact_decimal == Decimal(case["input_lexeme"])
        assert admitted.jcs_numeric_representation == case[
            "jcs_numeric_representation"
        ]
        assert admitted.jcs_reparsed_decimal == Decimal(
            case["jcs_numeric_representation"]
        )
    else:
        _assert_numeric_failure(
            lambda: admit_number(number),
            case["safe_reason"],
        )


@pytest.mark.parametrize("case", PRICE_AMOUNT_CASES)
def test_admit_exact_json_number_matches_frozen_price_vectors(case, monkeypatch):
    _module, admit_number, *_rest = _load_semantic_core()
    _deny_external_access(monkeypatch)
    lexeme = _price_lexeme(case)
    number = _parse_number(lexeme, monkeypatch)

    if case["numeric_domain_eligible"]:
        admitted = admit_number(number)
        assert admitted.jcs_numeric_representation == case[
            "jcs_numeric_representation"
        ]
    else:
        _assert_numeric_failure(lambda: admit_number(number), case["safe_reason"])


def test_numeric_domain_range_comparison_uses_exact_admitted_decimals(monkeypatch):
    _module, admit_number, *_rest = _load_semantic_core()
    _deny_external_access(monkeypatch)

    minimum = admit_number(_parse_number("19.99", monkeypatch)).exact_decimal
    maximum = admit_number(_parse_number("24.99", monkeypatch)).exact_decimal

    assert minimum < maximum
    assert not maximum < minimum


BINARY64_CASES = (
    pytest.param("0", 0x0000000000000000, id="positive-zero"),
    pytest.param("1", 0x3FF0000000000000, id="one"),
    pytest.param("-1.5", 0xBFF8000000000000, id="negative"),
    pytest.param(
        "1.00000000000000011102230246251565404236316680908203125",
        0x3FF0000000000000,
        id="halfway-ties-to-even-lower",
    ),
    pytest.param(
        "1.00000000000000033306690738754696212708950042724609375",
        0x3FF0000000000002,
        id="halfway-ties-to-even-upper",
    ),
    pytest.param("5e-324", 0x0000000000000001, id="minimum-subnormal"),
    pytest.param(
        "1.7976931348623157e308",
        0x7FEFFFFFFFFFFFFF,
        id="maximum-finite",
    ),
    pytest.param("1e309", 0x7FF0000000000000, id="positive-overflow"),
)


@pytest.mark.parametrize(("lexeme", "expected_bits"), BINARY64_CASES)
def test_binary64_conversion_is_exact_round_to_nearest_ties_to_even(
    lexeme,
    expected_bits,
):
    module = importlib.import_module(HASHER_MODULE)
    converter = getattr(module, "convert_exact_decimal_to_binary64", None)
    assert callable(converter)

    result = converter(Decimal(lexeme))

    assert result.bits == expected_bits
    assert struct.unpack(">Q", struct.pack(">d", result.value))[0] == expected_bits


def test_binary64_conversion_is_independent_of_decimal_context():
    module = importlib.import_module(HASHER_MODULE)
    exact_midpoint = Decimal(
        "1.00000000000000011102230246251565404236316680908203125"
    )

    baseline = module.convert_exact_decimal_to_binary64(exact_midpoint)
    with localcontext() as context:
        context.prec = 3
        context.rounding = ROUND_CEILING
        context.Emin = -2
        context.Emax = 2
        changed_context = module.convert_exact_decimal_to_binary64(exact_midpoint)

    assert baseline.bits == 0x3FF0000000000000
    assert changed_context == baseline


def _exact_dyadic_decimal(numerator: int, denominator_power: int) -> Decimal:
    coefficient = numerator * (5**denominator_power)
    digits = tuple(int(digit) for digit in str(coefficient))
    return Decimal((0, digits, -denominator_power))


def test_binary64_conversion_handles_subnormal_to_normal_rounding_boundary():
    module = importlib.import_module(HASHER_MODULE)
    exact_midpoint = _exact_dyadic_decimal((1 << 53) - 1, 1075)

    result = module.convert_exact_decimal_to_binary64(exact_midpoint)

    assert result.bits == 0x0010000000000000


def test_binary64_conversion_handles_finite_to_infinity_rounding_boundary():
    module = importlib.import_module(HASHER_MODULE)
    overflow_midpoint_integer = ((1 << 54) - 1) * (1 << 970)
    overflow_midpoint = Decimal(overflow_midpoint_integer)
    immediately_below = Decimal(overflow_midpoint_integer - 1)

    assert module.convert_exact_decimal_to_binary64(immediately_below).bits == (
        0x7FEFFFFFFFFFFFFF
    )
    assert module.convert_exact_decimal_to_binary64(overflow_midpoint).bits == (
        0x7FF0000000000000
    )


def test_numeric_failure_precedence_is_frozen_per_number(monkeypatch):
    _module, admit_number, *_rest = _load_semantic_core()
    _deny_external_access(monkeypatch)
    cases = (
        ("-0E+9999", "negative_zero"),
        ("1e309", "binary64_overflow_nonfinite"),
        ("1e-400", "nonzero_underflow_to_zero"),
        ("9007199254740993", "decimal_round_trip_changed"),
    )

    for lexeme, reason in cases:
        _assert_numeric_failure(
            lambda lexeme=lexeme: admit_number(_parse_number(lexeme, monkeypatch)),
            reason,
        )


def test_numeric_domain_error_message_exposes_only_the_safe_reason(monkeypatch):
    _module, admit_number, *_rest = _load_semantic_core()
    _deny_external_access(monkeypatch)
    sensitive_lexeme = "9007199254740993"

    with pytest.raises(Exception) as caught:
        admit_number(_parse_number(sensitive_lexeme, monkeypatch))

    assert str(caught.value) == "Numeric domain rejected: decimal_round_trip_changed"
    assert sensitive_lexeme not in str(caught.value)


@pytest.mark.parametrize(
    ("lexeme", "expected_jcs"),
    (
        pytest.param("1e20", "100000000000000000000", id="plain-upper-edge"),
        pytest.param("1e21", "1e+21", id="exponent-upper-edge"),
        pytest.param("1e-6", "0.000001", id="plain-lower-edge"),
        pytest.param("1e-7", "1e-7", id="exponent-lower-edge"),
        pytest.param("333333333.3333333", "333333333.3333333", id="fraction"),
        pytest.param("0.002", "0.002", id="small-plain"),
        pytest.param("1e-27", "1e-27", id="small-exponent"),
        pytest.param(
            "1.2345678901234567e30",
            "1.2345678901234567e+30",
            id="multi-digit-coefficient-exponent",
        ),
        pytest.param("9007199254740992", "9007199254740992", id="large-int"),
    ),
)
def test_jcs_number_formatting_boundaries(lexeme, expected_jcs, monkeypatch):
    _module, admit_number, *_rest = _load_semantic_core()
    _deny_external_access(monkeypatch)

    admitted = admit_number(_parse_number(lexeme, monkeypatch))

    assert admitted.jcs_numeric_representation == expected_jcs


def test_semantic_domain_admission_preserves_types_and_array_order(monkeypatch):
    module, _admit_number, admit_tree, *_rest = _load_semantic_core()
    _deny_external_access(monkeypatch)
    parsed = _invoke_strict_parser(
        b'{"values":[true,false,null,"19.99",1.0,2e-3]}',
        monkeypatch,
    )

    admitted = admit_tree(parsed)
    values = admitted.value["values"]

    assert values[:4] == [True, False, None, "19.99"]
    assert type(values[0]) is bool
    assert type(values[1]) is bool
    assert isinstance(values[4], module.AdmittedJsonNumber)
    assert isinstance(values[5], module.AdmittedJsonNumber)
    assert [values[4].jcs_numeric_representation, values[5].jcs_numeric_representation] == [
        "1",
        "0.002",
    ]


def test_jcs_serialization_uses_utf16_key_order_and_exact_string_escaping(
    monkeypatch,
):
    _module, _admit_number, admit_tree, canonicalize, _pipeline = (
        _load_semantic_core()
    )
    _deny_external_access(monkeypatch)
    payload = (
        '{"\\ue000":"line\\n","\\ud800\\udc00":"slash/\\b",'
        '"a":"\\\"\\\\\\u0001"}'
    ).encode("ascii")
    parsed = _invoke_strict_parser(payload, monkeypatch)

    result = canonicalize(admit_tree(parsed))

    assert result.canonical_bytes == (
        '{"a":"\\\"\\\\\\u0001","\U00010000":"slash/\\b",'
        '"\ue000":"line\\n"}'
    ).encode("utf-8")
    assert result.strict_parsed_semantic_payload_hash == hashlib.sha256(
        result.canonical_bytes
    ).hexdigest()


def test_jcs_object_order_is_not_host_integer_key_enumeration(monkeypatch):
    _module, _admit_number, _admit_tree, _canonicalize, pipeline = (
        _load_semantic_core()
    )
    _deny_external_access(monkeypatch)

    result = pipeline(b'{"2":"two","10":"ten","1":"one"}')

    assert result.canonical_bytes == b'{"1":"one","10":"ten","2":"two"}'


def test_jcs_serialization_preserves_array_order_and_collapses_escape_equivalence(
    monkeypatch,
):
    _module, _admit_number, _admit_tree, _canonicalize, pipeline = (
        _load_semantic_core()
    )
    _deny_external_access(monkeypatch)

    left = pipeline(b'["a",1.0,"\\u00e9",false]')
    right = pipeline('["a",1e0,"\u00e9",false]'.encode("utf-8"))

    assert left.canonical_bytes == b'["a",1,"\xc3\xa9",false]'
    assert left.canonical_bytes == right.canonical_bytes
    assert (
        left.strict_parsed_semantic_payload_hash
        == right.strict_parsed_semantic_payload_hash
    )


def test_semantic_jcs_preserves_composed_and_decomposed_string_values(monkeypatch):
    _module, _admit_number, _admit_tree, _canonicalize, pipeline = (
        _load_semantic_core()
    )
    _deny_external_access(monkeypatch)
    composed_bytes = '"\u00e9"'.encode("utf-8")
    decomposed_bytes = '"e\u0301"'.encode("utf-8")

    composed = pipeline(composed_bytes)
    decomposed = pipeline(decomposed_bytes)

    assert composed.admitted.value == "\u00e9"
    assert decomposed.admitted.value == "e\u0301"
    assert composed.admitted.value != decomposed.admitted.value
    assert composed.canonical_bytes == b'"\xc3\xa9"'
    assert decomposed.canonical_bytes == b'"e\xcc\x81"'
    assert composed.canonical_bytes != decomposed.canonical_bytes
    assert composed.strict_parsed_semantic_payload_hash == hashlib.sha256(
        b'"\xc3\xa9"'
    ).hexdigest()
    assert decomposed.strict_parsed_semantic_payload_hash == hashlib.sha256(
        b'"e\xcc\x81"'
    ).hexdigest()
    assert (
        composed.strict_parsed_semantic_payload_hash
        != decomposed.strict_parsed_semantic_payload_hash
    )


def test_semantic_jcs_preserves_composed_and_decomposed_object_keys(monkeypatch):
    _module, _admit_number, _admit_tree, _canonicalize, pipeline = (
        _load_semantic_core()
    )
    _deny_external_access(monkeypatch)
    payload = '{"\u00e9":"composed","e\u0301":"decomposed"}'.encode("utf-8")
    expected = b'{"e\xcc\x81":"decomposed","\xc3\xa9":"composed"}'

    result = pipeline(payload)

    assert tuple(result.admitted.value) == ("\u00e9", "e\u0301")
    assert len(result.admitted.value) == 2
    assert result.admitted.value["\u00e9"] == "composed"
    assert result.admitted.value["e\u0301"] == "decomposed"
    assert result.canonical_bytes == expected
    assert result.strict_parsed_semantic_payload_hash == hashlib.sha256(
        expected
    ).hexdigest()


@pytest.mark.parametrize(
    ("payload", "expected"),
    (
        pytest.param(b"null", b"null", id="null"),
        pytest.param(b'"text"', b'"text"', id="string"),
        pytest.param(b"true", b"true", id="true"),
        pytest.param(b"false", b"false", id="false"),
        pytest.param(b"[]", b"[]", id="empty-array"),
        pytest.param(b"{}", b"{}", id="empty-object"),
    ),
)
def test_jcs_top_level_non_numeric_values(payload, expected, monkeypatch):
    _module, _admit_number, _admit_tree, _canonicalize, pipeline = (
        _load_semantic_core()
    )
    _deny_external_access(monkeypatch)

    assert pipeline(payload).canonical_bytes == expected


def test_semantic_pipeline_handles_bounded_deep_arrays_iteratively(monkeypatch):
    _module, _admit_number, _admit_tree, _canonicalize, pipeline = (
        _load_semantic_core()
    )
    _deny_external_access(monkeypatch)
    depth = 500
    payload = (b"[" * depth) + b"1" + (b"]" * depth)

    result = pipeline(payload)

    assert result.canonical_bytes == payload


HASH_EQUALITY_CASES = tuple(
    pytest.param(case, id=case["id"])
    for case in SEMANTIC_VECTOR_SUITES["hash_equality_vectors"]["cases"]
)


@pytest.mark.parametrize("case", HASH_EQUALITY_CASES)
def test_frozen_hash_equality_vectors(case, monkeypatch):
    _module, _admit_number, _admit_tree, _canonicalize, pipeline = (
        _load_semantic_core()
    )
    _deny_external_access(monkeypatch)

    def result_for(lexeme):
        try:
            return pipeline(lexeme.encode("ascii"))
        except Exception as exc:
            assert type(exc).__name__ == "NumericDomainError"
            return None

    left = result_for(case["left_lexeme"])
    right = result_for(case["right_lexeme"])

    if case.get("semantic_hashes_equal"):
        assert left is not None and right is not None
        assert left.canonical_bytes == right.canonical_bytes
        assert (
            left.strict_parsed_semantic_payload_hash
            == right.strict_parsed_semantic_payload_hash
        )
    else:
        assert case.get("accepted_semantic_hash_equality_result") is None
        assert left is None or right is None


def test_numeric_domain_failure_never_hashes_partial_tree(monkeypatch):
    module, _admit_number, _admit_tree, _canonicalize, pipeline = (
        _load_semantic_core()
    )
    _deny_external_access(monkeypatch)

    def fail_hash(*_args, **_kwargs):
        pytest.fail("numeric-domain failure reached semantic hashing", pytrace=False)

    monkeypatch.setattr(module.hashlib, "sha256", fail_hash)

    _assert_numeric_failure(
        lambda: pipeline(b'{"ok":19.99,"bad":9007199254740993}'),
        "decimal_round_trip_changed",
    )


def test_raw_and_semantic_hash_domains_remain_distinct(monkeypatch):
    _module, _admit_number, _admit_tree, _canonicalize, pipeline = (
        _load_semantic_core()
    )
    _deny_external_access(monkeypatch)
    raw_left = b"1"
    raw_right = b"1.0"

    assert _invoke_hasher(raw_left, monkeypatch) != _invoke_hasher(
        raw_right, monkeypatch
    )
    assert (
        pipeline(raw_left).strict_parsed_semantic_payload_hash
        == pipeline(raw_right).strict_parsed_semantic_payload_hash
    )


def _numeric_descriptor_result(descriptor, monkeypatch):
    if descriptor["type"] == "string":
        return ("string", descriptor["value"], None)

    lexeme = descriptor.get("lexeme") or descriptor.get("canonical_lexeme")
    lexeme = lexeme or descriptor["jcs_numeric_representation"]
    _module, admit_number, *_rest = _load_semantic_core()
    number = _parse_number(lexeme, monkeypatch)
    try:
        admitted = admit_number(number)
    except Exception as exc:
        assert type(exc).__name__ == "NumericDomainError"
        admitted = None
    return ("number", number.exact_decimal, admitted)


@pytest.mark.parametrize(
    "case",
    tuple(
        pytest.param(case, id=case["id"])
        for case in SEMANTIC_VECTOR_SUITES["native_sdk_numeric_vectors"]["cases"]
    ),
)
def test_native_sdk_vectors_follow_exact_type_and_decimal_identity(case, monkeypatch):
    _deny_external_access(monkeypatch)
    raw_type, raw_value, raw_admitted = _numeric_descriptor_result(
        case["raw"], monkeypatch
    )
    native_type, native_value, native_admitted = _numeric_descriptor_result(
        case["native"], monkeypatch
    )

    if raw_type != native_type or raw_value != native_value:
        result = "proven_unequal"
    elif raw_admitted is None or native_admitted is None:
        result = None
    else:
        result = "proven_equal"

    expected = case.get("expected_equivalence", case.get("expected_equivalence_result"))
    assert result == expected


@pytest.mark.parametrize(
    "case",
    tuple(
        pytest.param(case, id=case["id"])
        for case in SEMANTIC_VECTOR_SUITES["integer_boolean_vectors"]["cases"]
    ),
)
def test_integer_boolean_vectors_use_mathematical_semantics(case, monkeypatch):
    module, admit_number, _admit_tree, _canonicalize, pipeline = (
        _load_semantic_core()
    )
    _deny_external_access(monkeypatch)

    if "input_json" in case:
        result = pipeline(case["input_json"].encode("ascii"))
        assert type(result.admitted.value) is bool
        assert not isinstance(result.admitted.value, module.AdmittedJsonNumber)
        assert case["numeric_domain_validator_applicable"] is False
        return

    number = _parse_number(case["input_lexeme"], monkeypatch)
    if not case["numeric_domain_eligible"]:
        _assert_numeric_failure(lambda: admit_number(number), "negative_zero")
        return

    admitted = admit_number(number)
    if "mathematical_integer" in case:
        assert admitted.mathematical_integer is case["mathematical_integer"]
    if "schema_maximum_3_valid" in case:
        assert (admitted.exact_decimal <= Decimal(3)) is case[
            "schema_maximum_3_valid"
        ]


def test_mathematical_integer_semantics_are_decimal_context_independent(
    monkeypatch,
):
    _module, admit_number, *_rest = _load_semantic_core()
    _deny_external_access(monkeypatch)
    integer = _parse_number("1000.000", monkeypatch)
    fraction = _parse_number("1000.001", monkeypatch)

    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_CEILING
        context.Emin = -2
        context.Emax = 2
        integer_result = admit_number(integer)
        fraction_result = admit_number(fraction)

    assert integer_result.mathematical_integer is True
    assert fraction_result.mathematical_integer is False


@pytest.mark.parametrize(
    "case",
    tuple(
        pytest.param(case, id=case["id"])
        for case in SEMANTIC_VECTOR_SUITES["json_numeric_syntax_vectors"]["cases"]
    ),
)
def test_json_numeric_syntax_vectors_remain_separate_from_admission(
    case,
    monkeypatch,
):
    if case["id"] == "J10":
        parsed = _invoke_strict_parser(case["input"].encode("ascii"), monkeypatch)
        assert _strict_value(parsed) == "19.99"
        return

    _assert_parser_failure(
        case["input"].encode("ascii"),
        "json_syntax",
        monkeypatch,
    )


@pytest.mark.parametrize(
    "payload",
    (
        pytest.param("{}", id="str"),
        pytest.param(bytearray(b"{}"), id="bytearray"),
        pytest.param(memoryview(b"{}"), id="memoryview"),
        pytest.param(None, id="none"),
    ),
)
def test_normalize_semantic_json_requires_exact_bytes(payload):
    _module, _admit_number, _admit_tree, _canonicalize, pipeline = (
        _load_semantic_core()
    )

    with pytest.raises(TypeError):
        pipeline(payload)


def test_semantic_core_public_boundaries_fail_closed():
    module = importlib.import_module(HASHER_MODULE)

    with pytest.raises(ValueError):
        module._jcs_number_from_binary64(float("inf"))
    with pytest.raises(TypeError):
        module.convert_exact_decimal_to_binary64("1")
    with pytest.raises(ValueError):
        module.convert_exact_decimal_to_binary64(Decimal("Infinity"))
    with pytest.raises(TypeError):
        module.admit_exact_json_number(Decimal(1))
    with pytest.raises(TypeError):
        module.admit_semantic_numeric_domain({"value": 1})
    with pytest.raises(TypeError):
        module.admit_semantic_numeric_domain(module.StrictParsedJson({1: "value"}))
    with pytest.raises(TypeError):
        module.admit_semantic_numeric_domain(module.StrictParsedJson(1))
    with pytest.raises(TypeError):
        module.canonicalize_semantic_json({"value": 1})
    with pytest.raises(TypeError):
        module.canonicalize_semantic_json(
            module.NumericDomainAdmission(value=module.ExactJsonNumber("1", Decimal(1)))
        )
    with pytest.raises(ValueError):
        module.canonicalize_semantic_json(
            module.NumericDomainAdmission(value="\ud800")
        )
