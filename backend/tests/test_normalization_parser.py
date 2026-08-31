"""Executable boundary for the frozen normalization-parser raw hash.

The committed parser artifact is the semantic authority.  Structural tests
remain useful before implementation exists; functional cases deliberately use
a deferred import so the initial RED result identifies only the missing
``hash_raw_provider_response`` callable.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from decimal import Decimal
from pathlib import Path
import socket
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
