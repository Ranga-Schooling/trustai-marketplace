"""Adversarial boundary tests for frozen normalization resource limits."""

from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest

from app.services.evaluation_resource_limits import (
    RESOURCE_LIMIT_VALUES,
    ResourceLimitExceededError,
    account_raw_response_chunk,
    enforce_extracted_semantic_bytes,
    enforce_native_json_resource_limits,
)
from app.services.normalization_parser import (
    NumericDomainAdmission,
    canonicalize_semantic_json,
    compare_independent_native_payloads,
    hash_raw_provider_response,
    parse_strict_json_payload,
)


pytestmark = pytest.mark.contract


LIMITS = {
    "maximum_raw_response_bytes": 2_097_152,
    "maximum_extracted_semantic_bytes": 1_048_576,
    "maximum_json_nesting_depth": 32,
    "maximum_object_members": 64,
    "maximum_total_object_members": 16_384,
    "maximum_array_elements": 1_024,
    "maximum_total_array_elements": 4_096,
    "maximum_single_string_bytes": 131_072,
    "maximum_total_string_bytes": 524_288,
    "maximum_canonical_payload_bytes": 2_097_152,
    "maximum_numeric_lexeme_length": 16_384,
    "maximum_numeric_significand_or_coefficient_digits": 8_192,
    "maximum_absolute_decimal_exponent_magnitude": 32_768,
}


def _assert_resource_failure(call, limit_name: str) -> None:
    with pytest.raises(ResourceLimitExceededError) as caught:
        call()

    assert caught.value.category == "failed_resource_limit"
    assert caught.value.limit_name == limit_name
    assert str(caught.value) == "failed_resource_limit"


def _array(element_count: int) -> bytes:
    return ("[" + ",".join("0" for _ in range(element_count)) + "]").encode()


def _object(member_count: int, *, duplicate: bool = False) -> str:
    if duplicate:
        members = ('"a":0' for _ in range(member_count))
    else:
        members = (f'"k{index}":0' for index in range(member_count))
    return "{" + ",".join(members) + "}"


def _objects_with_total_members(total: int) -> bytes:
    complete, remainder = divmod(total, LIMITS["maximum_object_members"])
    objects = [_object(LIMITS["maximum_object_members"])] * complete
    if remainder:
        objects.append(_object(remainder))
    return ("[" + ",".join(objects) + "]").encode()


def _arrays_with_total_elements(total: int) -> bytes:
    complete, remainder = divmod(total, LIMITS["maximum_array_elements"])
    members = [
        f'"a{index}":{_array(LIMITS["maximum_array_elements"]).decode()}'
        for index in range(complete)
    ]
    if remainder:
        members.append(f'"a{complete}":{_array(remainder).decode()}')
    return ("{" + ",".join(members) + "}").encode()


def _strings_with_total_decoded_bytes(total: int) -> bytes:
    maximum = LIMITS["maximum_single_string_bytes"]
    complete, remainder = divmod(total, maximum)
    values = ["a" * maximum] * complete
    if remainder:
        values.append("b" * remainder)
    return ("[" + ",".join(f'"{value}"' for value in values) + "]").encode()


def _keys_with_total_decoded_bytes(total: int) -> bytes:
    maximum = LIMITS["maximum_single_string_bytes"]
    complete, remainder = divmod(total, maximum)
    members = []
    for index in range(complete):
        key = chr(ord("a") + index) + ("x" * (maximum - 1))
        members.append(f'"{key}":null')
    if remainder:
        key = chr(ord("a") + complete) + ("x" * (remainder - 1))
        members.append(f'"{key}":null')
    return ("{" + ",".join(members) + "}").encode()


def _numeric_lexeme(length: int) -> bytes:
    assert length >= 2
    return ("1e" + ("0" * (length - 2))).encode()


def _coefficient(digit_count: int) -> bytes:
    assert digit_count >= 1
    return ("0." + ("0" * (digit_count - 1))).encode()


def _canonical_payload(byte_count: int) -> NumericDomainAdmission:
    string_count = 4
    syntax_bytes = 2 + (string_count - 1) + (2 * string_count)
    maximum_total = LIMITS["maximum_total_string_bytes"]
    decoded_total = maximum_total
    while (byte_count - syntax_bytes - decoded_total) % 5:
        decoded_total -= 1
    control_count = (byte_count - syntax_bytes - decoded_total) // 5
    assert 0 <= control_count <= decoded_total

    values = []
    remaining_decoded = decoded_total
    remaining_controls = control_count
    for _ in range(string_count):
        length = min(
            LIMITS["maximum_single_string_bytes"],
            remaining_decoded,
        )
        controls = min(length, remaining_controls)
        values.append(("\x00" * controls) + ("a" * (length - controls)))
        remaining_decoded -= length
        remaining_controls -= controls
    assert remaining_decoded == 0
    assert remaining_controls == 0
    return NumericDomainAdmission(values)


def test_runtime_limit_inventory_is_exactly_the_governance_decision():
    assert RESOURCE_LIMIT_VALUES == LIMITS


@pytest.mark.parametrize("delta", (-1, 0))
def test_raw_response_boundary_accepts_limit_and_below(delta):
    limit = LIMITS["maximum_raw_response_bytes"]
    payload = b"x" * (limit + delta)

    assert account_raw_response_chunk(0, payload) == len(payload)
    assert hash_raw_provider_response(payload) == hashlib.sha256(payload).hexdigest()


def test_raw_response_boundary_rejects_limit_plus_one_before_hash(monkeypatch):
    limit = LIMITS["maximum_raw_response_bytes"]
    payload = b"x" * (limit + 1)
    monkeypatch.setattr(hashlib, "sha256", lambda *_args, **_kwargs: pytest.fail("hashed"))

    _assert_resource_failure(
        lambda: hash_raw_provider_response(payload),
        "maximum_raw_response_bytes",
    )


def test_raw_transport_counter_rejects_before_next_chunk_is_accumulated():
    limit = LIMITS["maximum_raw_response_bytes"]
    current = account_raw_response_chunk(0, b"x" * (limit - 1))
    current = account_raw_response_chunk(current, b"x")
    assert current == limit
    _assert_resource_failure(
        lambda: account_raw_response_chunk(current, b"x"),
        "maximum_raw_response_bytes",
    )


@pytest.mark.parametrize("delta", (-1, 0))
def test_extracted_semantic_boundary_accepts_limit_and_below(delta):
    limit = LIMITS["maximum_extracted_semantic_bytes"]
    payload = b"x" * (limit + delta)
    assert enforce_extracted_semantic_bytes(payload) is None


def test_extracted_semantic_boundary_rejects_limit_plus_one():
    limit = LIMITS["maximum_extracted_semantic_bytes"]
    _assert_resource_failure(
        lambda: enforce_extracted_semantic_bytes(b"x" * (limit + 1)),
        "maximum_extracted_semantic_bytes",
    )


@pytest.mark.parametrize("depth", (31, 32))
def test_nesting_depth_accepts_limit_and_below(depth):
    parsed = parse_strict_json_payload(("[" * depth + "]" * depth).encode())
    assert parsed.value is not None


def test_nesting_depth_rejects_limit_plus_one_before_json_loads(monkeypatch):
    import app.services.normalization_parser as parser

    monkeypatch.setattr(parser.json, "loads", lambda *_args, **_kwargs: pytest.fail("loaded"))
    _assert_resource_failure(
        lambda: parse_strict_json_payload(b"[" * 33 + b"]" * 33),
        "maximum_json_nesting_depth",
    )


@pytest.mark.parametrize("member_count", (63, 64))
def test_object_member_boundary_accepts_limit_and_below(member_count):
    assert len(parse_strict_json_payload(_object(member_count).encode()).value) == member_count


def test_object_member_boundary_rejects_limit_plus_one():
    _assert_resource_failure(
        lambda: parse_strict_json_payload(_object(65).encode()),
        "maximum_object_members",
    )


@pytest.mark.parametrize("total", (16_383, 16_384))
def test_total_object_member_boundary_accepts_limit_and_below(total):
    parse_strict_json_payload(_objects_with_total_members(total))


def test_total_object_member_boundary_rejects_limit_plus_one():
    _assert_resource_failure(
        lambda: parse_strict_json_payload(_objects_with_total_members(16_385)),
        "maximum_total_object_members",
    )


@pytest.mark.parametrize("element_count", (1_023, 1_024))
def test_array_element_boundary_accepts_limit_and_below(element_count):
    assert len(parse_strict_json_payload(_array(element_count)).value) == element_count


def test_array_element_boundary_rejects_limit_plus_one():
    _assert_resource_failure(
        lambda: parse_strict_json_payload(_array(1_025)),
        "maximum_array_elements",
    )


@pytest.mark.parametrize("total", (4_095, 4_096))
def test_total_array_element_boundary_accepts_limit_and_below(total):
    parse_strict_json_payload(_arrays_with_total_elements(total))


def test_total_array_element_boundary_rejects_limit_plus_one():
    _assert_resource_failure(
        lambda: parse_strict_json_payload(_arrays_with_total_elements(4_097)),
        "maximum_total_array_elements",
    )


@pytest.mark.parametrize("byte_count", (131_071, 131_072))
def test_single_string_boundary_accepts_limit_and_below(byte_count):
    assert len(parse_strict_json_payload((f'"{"a" * byte_count}"').encode()).value) == byte_count


def test_single_string_boundary_rejects_limit_plus_one():
    _assert_resource_failure(
        lambda: parse_strict_json_payload((f'"{"a" * 131_073}"').encode()),
        "maximum_single_string_bytes",
    )


@pytest.mark.parametrize("total", (524_287, 524_288))
def test_total_string_boundary_accepts_limit_and_below(total):
    parse_strict_json_payload(_strings_with_total_decoded_bytes(total))


def test_total_string_boundary_rejects_limit_plus_one():
    _assert_resource_failure(
        lambda: parse_strict_json_payload(_strings_with_total_decoded_bytes(524_289)),
        "maximum_total_string_bytes",
    )


@pytest.mark.parametrize("byte_count", (2_097_151, 2_097_152))
def test_canonical_payload_boundary_accepts_limit_and_below(byte_count):
    result = canonicalize_semantic_json(_canonical_payload(byte_count))
    assert len(result.canonical_bytes) == byte_count


def test_canonical_payload_rejects_limit_plus_one_before_hash(monkeypatch):
    monkeypatch.setattr(hashlib, "sha256", lambda *_args, **_kwargs: pytest.fail("hashed"))
    _assert_resource_failure(
        lambda: canonicalize_semantic_json(_canonical_payload(2_097_153)),
        "maximum_canonical_payload_bytes",
    )


@pytest.mark.parametrize("length", (16_383, 16_384))
def test_numeric_lexeme_boundary_accepts_limit_and_below(length):
    number = parse_strict_json_payload(_numeric_lexeme(length)).value
    assert len(number.lexeme) == length


def test_numeric_lexeme_boundary_rejects_limit_plus_one_before_decimal(monkeypatch):
    import app.services.normalization_parser as parser

    monkeypatch.setattr(parser, "Decimal", lambda *_args, **_kwargs: pytest.fail("decimal"))
    _assert_resource_failure(
        lambda: parse_strict_json_payload(_numeric_lexeme(16_385)),
        "maximum_numeric_lexeme_length",
    )


@pytest.mark.parametrize("digit_count", (8_191, 8_192))
def test_numeric_coefficient_boundary_accepts_limit_and_below(digit_count):
    number = parse_strict_json_payload(_coefficient(digit_count)).value
    assert len(number.exact_decimal.as_tuple().digits) <= digit_count


def test_numeric_coefficient_boundary_rejects_limit_plus_one_before_decimal(monkeypatch):
    import app.services.normalization_parser as parser

    monkeypatch.setattr(parser, "Decimal", lambda *_args, **_kwargs: pytest.fail("decimal"))
    _assert_resource_failure(
        lambda: parse_strict_json_payload(_coefficient(8_193)),
        "maximum_numeric_significand_or_coefficient_digits",
    )


@pytest.mark.parametrize("magnitude", (32_767, 32_768))
def test_numeric_exponent_boundary_accepts_limit_and_below(magnitude):
    number = parse_strict_json_payload(f"1e{magnitude}".encode()).value
    assert number.exact_decimal.as_tuple().exponent == magnitude


def test_numeric_exponent_boundary_rejects_limit_plus_one_before_decimal(monkeypatch):
    import app.services.normalization_parser as parser

    monkeypatch.setattr(parser, "Decimal", lambda *_args, **_kwargs: pytest.fail("decimal"))
    _assert_resource_failure(
        lambda: parse_strict_json_payload(b"1e32769"),
        "maximum_absolute_decimal_exponent_magnitude",
    )


def test_depth_counting_conventions_cover_scalar_and_empty_roots():
    assert parse_strict_json_payload(b"null").value is None
    assert parse_strict_json_payload(b"{}").value == {}
    assert parse_strict_json_payload(b"[]").value == []
    assert parse_strict_json_payload(b'""').value == ""


def test_duplicate_members_are_counted_before_duplicate_key_disposition():
    with pytest.raises(Exception) as caught:
        parse_strict_json_payload(_object(64, duplicate=True).encode())
    assert type(caught.value).__name__ == "DuplicateJsonKeyError"

    _assert_resource_failure(
        lambda: parse_strict_json_payload(_object(65, duplicate=True).encode()),
        "maximum_object_members",
    )


def test_string_totals_include_keys_and_values():
    parse_strict_json_payload(_keys_with_total_decoded_bytes(524_288))
    _assert_resource_failure(
        lambda: parse_strict_json_payload(
            _keys_with_total_decoded_bytes(524_288)[:-1] + b',"z":"x"}'
        ),
        "maximum_total_string_bytes",
    )


@pytest.mark.parametrize(
    ("payload", "limit_name"),
    (
        ((('"' + ('\u20ac' * 43_690) + 'aa"').encode()), None),
        ((('"' + ('\u20ac' * 43_690) + 'aaa"').encode()), "maximum_single_string_bytes"),
        ((('"' + ('\U0001f642' * 32_768) + '"').encode()), None),
        ((('"' + ('\U0001f642' * 32_768) + 'a"').encode()), "maximum_single_string_bytes"),
        ((b'"' + (b"\\u0061" * 131_072) + b'"'), None),
        ((b'"' + (b"\\u0061" * 131_073) + b'"'), "maximum_single_string_bytes"),
    ),
)
def test_string_limits_count_decoded_utf8_bytes(payload, limit_name):
    if limit_name is None:
        parse_strict_json_payload(payload)
    else:
        _assert_resource_failure(lambda: parse_strict_json_payload(payload), limit_name)


@pytest.mark.parametrize(
    "payload",
    (b"0", b"000"[:1], b"1.2300", b"1e+0", b"1e-0", b"1"),
)
def test_numeric_counting_conventions_accept_zeros_signs_and_absent_exponent(payload):
    parse_strict_json_payload(payload)


def test_cross_limit_precedence_is_deterministic():
    _assert_resource_failure(
        lambda: parse_strict_json_payload((f'"{"a" * 131_073}"').encode()),
        "maximum_single_string_bytes",
    )
    at_total = _strings_with_total_decoded_bytes(524_288)
    _assert_resource_failure(
        lambda: parse_strict_json_payload(at_total[:-1] + b',"x"]'),
        "maximum_total_string_bytes",
    )


@pytest.mark.parametrize(
    ("payload", "expected_limit"),
    (
        (b"0" * 16_385, "maximum_numeric_lexeme_length"),
        (b"0" * 8_193, "maximum_numeric_significand_or_coefficient_digits"),
    ),
)
def test_lexically_detectable_numeric_limits_precede_strict_grammar(
    payload,
    expected_limit,
):
    _assert_resource_failure(
        lambda: parse_strict_json_payload(payload),
        expected_limit,
    )


def _nested_list(depth: int):
    value = None
    for _ in range(depth):
        value = [value]
    return value


def _failure_limit(call) -> str:
    with pytest.raises(ResourceLimitExceededError) as caught:
        call()
    return caught.value.limit_name


def test_raw_and_native_object_precedence_are_identical():
    native = {"first": _nested_list(32)}
    native.update({f"k{index}": None for index in range(64)})
    raw = (
        '{"first":'
        + ("[" * 32)
        + "null"
        + ("]" * 32)
        + "".join(f',"k{index}":null' for index in range(64))
        + "}"
    ).encode()

    assert _failure_limit(
        lambda: parse_strict_json_payload(raw)
    ) == _failure_limit(lambda: enforce_native_json_resource_limits(native))
    assert _failure_limit(
        lambda: parse_strict_json_payload(raw)
    ) == "maximum_json_nesting_depth"


def test_raw_and_native_array_precedence_are_identical():
    native = [_nested_list(32), *([None] * 1_024)]
    raw = (
        "["
        + ("[" * 32)
        + "null"
        + ("]" * 32)
        + (",null" * 1_024)
        + "]"
    ).encode()

    assert _failure_limit(
        lambda: parse_strict_json_payload(raw)
    ) == _failure_limit(lambda: enforce_native_json_resource_limits(native))
    assert _failure_limit(
        lambda: parse_strict_json_payload(raw)
    ) == "maximum_json_nesting_depth"


def test_oversized_invalid_utf8_fails_at_extracted_byte_boundary_first():
    payload = b"\xff" + (b"x" * LIMITS["maximum_extracted_semantic_bytes"])
    _assert_resource_failure(
        lambda: parse_strict_json_payload(payload),
        "maximum_extracted_semantic_bytes",
    )


def test_non_ascii_digits_remain_json_syntax_not_numeric_resource_input():
    with pytest.raises(Exception) as caught:
        parse_strict_json_payload(("1" + ("\u0661" * 20_000)).encode())
    assert type(caught.value).__name__ == "StrictJsonSyntaxError"


def test_shared_native_references_cannot_bypass_semantic_occurrence_counts():
    shared = "x" * 131_072
    candidate = [shared, shared, shared, shared, "x"]
    reference = parse_strict_json_payload(b"[]")

    _assert_resource_failure(
        lambda: compare_independent_native_payloads(reference, candidate),
        "maximum_total_string_bytes",
    )


def test_shared_native_objects_count_each_semantic_occurrence():
    shared = {f"k{index}": None for index in range(64)}
    candidate = [shared] * 257

    _assert_resource_failure(
        lambda: enforce_native_json_resource_limits(candidate),
        "maximum_total_object_members",
    )


def test_shared_native_arrays_count_each_semantic_occurrence():
    shared = [None] * 1_024
    candidate = {f"k{index}": shared for index in range(5)}

    _assert_resource_failure(
        lambda: enforce_native_json_resource_limits(candidate),
        "maximum_total_array_elements",
    )


def test_direct_canonicalization_cannot_bypass_structural_or_string_limits():
    _assert_resource_failure(
        lambda: canonicalize_semantic_json(NumericDomainAdmission([None] * 1_025)),
        "maximum_array_elements",
    )
    _assert_resource_failure(
        lambda: canonicalize_semantic_json(NumericDomainAdmission("x" * 131_073)),
        "maximum_single_string_bytes",
    )


def test_native_multibyte_string_counts_without_encoding_copy(monkeypatch):
    import app.services.evaluation_resource_limits as limits

    monkeypatch.setattr(
        limits,
        "_utf8_scalar_length",
        lambda *_args, **_kwargs: pytest.fail("JSON-only counter used"),
    )
    reference = parse_strict_json_payload(b'""')
    candidate = "\U0001f642" * 32_769

    _assert_resource_failure(
        lambda: compare_independent_native_payloads(reference, candidate),
        "maximum_single_string_bytes",
    )


def test_native_candidate_structural_limits_apply_before_materialization():
    reference = parse_strict_json_payload(b"[]")
    _assert_resource_failure(
        lambda: compare_independent_native_payloads(reference, [None] * 1_025),
        "maximum_array_elements",
    )


def test_canonical_measurement_uses_utf8_bytes_not_character_count():
    value = "\U0001f642" * 100
    result = canonicalize_semantic_json(NumericDomainAdmission(value))
    assert len(result.canonical_bytes) == 402
