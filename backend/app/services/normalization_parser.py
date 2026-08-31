"""Provider-neutral normalization primitives."""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


class StrictJsonPayloadError(ValueError):
    """Base error for the strict semantic-payload parsing boundary."""


class StrictUtf8DecodeError(StrictJsonPayloadError):
    """The extracted semantic payload is not strict UTF-8."""

    category = "utf8"


class StrictJsonSyntaxError(StrictJsonPayloadError):
    """The decoded payload is not strict RFC 8259 JSON."""

    category = "json_syntax"


class DuplicateJsonKeyError(StrictJsonPayloadError):
    """A syntactically valid object contains a duplicate decoded key."""

    category = "duplicate_key"


class NumericDomainError(ValueError):
    """An exact JSON number is outside the frozen semantic numeric domain."""

    category = "numeric_domain_ineligible"

    def __init__(self, reason: str, lexeme: str) -> None:
        super().__init__(f"Numeric domain rejected: {reason}")
        self.reason = reason
        self.lexeme = lexeme


@dataclass(frozen=True)
class ExactJsonNumber:
    """One JSON number with both lexical and exact mathematical identity."""

    lexeme: str
    exact_decimal: Decimal


@dataclass(frozen=True)
class StrictParsedJson:
    """Opaque strict-parsing result before numeric-domain admission."""

    value: Any


@dataclass(frozen=True)
class Binary64Value:
    """One exact IEEE-754 binary64 conversion and its physical identity."""

    value: float
    bits: int


@dataclass(frozen=True)
class AdmittedJsonNumber:
    """A strict number admitted to the frozen semantic numeric domain."""

    lexeme: str
    exact_decimal: Decimal
    binary64_value: float
    binary64_bits: int
    jcs_numeric_representation: str
    jcs_reparsed_decimal: Decimal
    mathematical_integer: bool


@dataclass(frozen=True)
class NumericDomainAdmission:
    """A strict semantic tree after every contained number is admitted."""

    value: Any


@dataclass(frozen=True)
class CanonicalSemanticJson:
    """RFC 8785 bytes and hash for one completely admitted semantic tree."""

    admitted: NumericDomainAdmission
    canonical_bytes: bytes
    strict_parsed_semantic_payload_hash: str


@dataclass(frozen=True)
class _NumericToken:
    lexeme: str


@dataclass(frozen=True)
class _ObjectPairs:
    pairs: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class _JcsLiteral:
    value: str


def _preserve_numeric_lexeme(lexeme: str) -> _NumericToken:
    return _NumericToken(lexeme)


def _preserve_object_pairs(pairs: list[tuple[str, Any]]) -> _ObjectPairs:
    return _ObjectPairs(tuple(pairs))


def _reject_nonfinite_constant(value: str) -> None:
    raise StrictJsonSyntaxError(f"Non-finite JSON number is forbidden: {value}")


def _reject_duplicate_keys(value: Any) -> None:
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, _ObjectPairs):
            seen: set[str] = set()
            for key, child in current.pairs:
                if key in seen:
                    raise DuplicateJsonKeyError("Duplicate JSON object key")
                seen.add(key)
                stack.append(child)
        elif isinstance(current, list):
            stack.extend(current)


def _contains_surrogate(value: str) -> bool:
    return any("\ud800" <= character <= "\udfff" for character in value)


def _reject_unpaired_surrogates(value: Any) -> None:
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, str):
            if _contains_surrogate(current):
                raise StrictJsonSyntaxError(
                    "Unpaired Unicode surrogate is forbidden in JSON strings"
                )
        elif isinstance(current, _ObjectPairs):
            for key, child in current.pairs:
                if _contains_surrogate(key):
                    raise StrictJsonSyntaxError(
                        "Unpaired Unicode surrogate is forbidden in JSON object keys"
                    )
                stack.append(child)
        elif isinstance(current, list):
            stack.extend(current)


def _materialize_exact_tree(value: Any) -> Any:
    root: list[Any] = [None]
    stack: list[tuple[Any, Any, Any]] = [(value, root, 0)]

    while stack:
        current, destination, position = stack.pop()
        if isinstance(current, _NumericToken):
            destination[position] = ExactJsonNumber(
                lexeme=current.lexeme,
                exact_decimal=Decimal(current.lexeme),
            )
        elif isinstance(current, _ObjectPairs):
            materialized_object: dict[str, Any] = {}
            destination[position] = materialized_object
            for key, child in reversed(current.pairs):
                stack.append((child, materialized_object, key))
        elif isinstance(current, list):
            materialized_array: list[Any] = [None] * len(current)
            destination[position] = materialized_array
            for index in range(len(current) - 1, -1, -1):
                stack.append((current[index], materialized_array, index))
        else:
            destination[position] = current

    return root[0]


def _round_ratio_ties_to_even(numerator: int, denominator: int) -> int:
    quotient, remainder = divmod(numerator, denominator)
    doubled_remainder = remainder * 2
    if doubled_remainder > denominator or (
        doubled_remainder == denominator and quotient & 1
    ):
        quotient += 1
    return quotient


def _floor_log2_ratio(numerator: int, denominator: int) -> int:
    exponent = numerator.bit_length() - denominator.bit_length()
    if exponent >= 0:
        if numerator < denominator << exponent:
            exponent -= 1
    elif numerator << -exponent < denominator:
        exponent -= 1
    return exponent


def convert_exact_decimal_to_binary64(exact_decimal: Decimal) -> Binary64Value:
    """Convert a finite Decimal to binary64 with exact ties-to-even rounding."""
    if not isinstance(exact_decimal, Decimal):
        raise TypeError("exact_decimal must be Decimal")
    if not exact_decimal.is_finite():
        raise ValueError("exact_decimal must be finite")

    negative = exact_decimal.is_signed()
    sign_bits = int(negative) << 63
    numerator, denominator = exact_decimal.copy_abs().as_integer_ratio()

    if numerator == 0:
        bits = sign_bits
    elif numerator << 1022 < denominator:
        significand = _round_ratio_ties_to_even(
            numerator << 1074,
            denominator,
        )
        if significand >= 1 << 52:
            bits = sign_bits | (1 << 52)
        else:
            bits = sign_bits | significand
    else:
        exponent = _floor_log2_ratio(numerator, denominator)
        if exponent > 1023:
            bits = sign_bits | (0x7FF << 52)
        else:
            shift = 52 - exponent
            if shift >= 0:
                significand = _round_ratio_ties_to_even(
                    numerator << shift,
                    denominator,
                )
            else:
                significand = _round_ratio_ties_to_even(
                    numerator,
                    denominator << -shift,
                )
            if significand == 1 << 53:
                significand = 1 << 52
                exponent += 1
            if exponent > 1023:
                bits = sign_bits | (0x7FF << 52)
            else:
                exponent_bits = exponent + 1023
                fraction_bits = significand - (1 << 52)
                bits = sign_bits | (exponent_bits << 52) | fraction_bits

    value = struct.unpack(">d", struct.pack(">Q", bits))[0]
    return Binary64Value(value=value, bits=bits)


def _jcs_number_from_binary64(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("JCS numbers must be finite")
    if value == 0:
        return "0"

    sign = "-" if value < 0 else ""
    rendered = repr(abs(value)).lower()
    if "e" in rendered:
        mantissa, exponent_text = rendered.split("e", 1)
        exponent = int(exponent_text)
    else:
        mantissa = rendered
        exponent = 0

    if "." in mantissa:
        integer_part, fractional_part = mantissa.split(".", 1)
    else:
        integer_part, fractional_part = mantissa, ""

    digits = (integer_part + fractional_part).lstrip("0") or "0"
    decimal_power = exponent - len(fractional_part)
    while len(digits) > 1 and digits.endswith("0"):
        digits = digits[:-1]
        decimal_power += 1

    decimal_point = len(digits) + decimal_power
    if len(digits) <= decimal_point <= 21:
        body = digits + ("0" * (decimal_point - len(digits)))
    elif 0 < decimal_point <= 21:
        body = digits[:decimal_point] + "." + digits[decimal_point:]
    elif -6 < decimal_point <= 0:
        body = "0." + ("0" * -decimal_point) + digits
    else:
        exponent_value = decimal_point - 1
        coefficient = digits[0]
        if len(digits) > 1:
            coefficient += "." + digits[1:]
        exponent_sign = "+" if exponent_value >= 0 else ""
        body = f"{coefficient}e{exponent_sign}{exponent_value}"
    return sign + body


def _is_mathematical_integer(value: Decimal) -> bool:
    representation = value.as_tuple()
    if representation.exponent >= 0:
        return True
    fractional_digits = -representation.exponent
    if fractional_digits > len(representation.digits):
        return all(digit == 0 for digit in representation.digits)
    return all(digit == 0 for digit in representation.digits[-fractional_digits:])


def admit_exact_json_number(number: ExactJsonNumber) -> AdmittedJsonNumber:
    """Apply the frozen ordered numeric-domain predicates to one number."""
    if not isinstance(number, ExactJsonNumber):
        raise TypeError("number must be ExactJsonNumber")

    exact_decimal = number.exact_decimal
    if exact_decimal.is_zero() and number.lexeme.startswith("-"):
        raise NumericDomainError("negative_zero", number.lexeme)

    converted = convert_exact_decimal_to_binary64(exact_decimal)
    if not math.isfinite(converted.value):
        raise NumericDomainError("binary64_overflow_nonfinite", number.lexeme)
    if not exact_decimal.is_zero() and converted.value == 0:
        raise NumericDomainError("nonzero_underflow_to_zero", number.lexeme)

    jcs_representation = _jcs_number_from_binary64(converted.value)
    jcs_reparsed_decimal = Decimal(jcs_representation)
    if jcs_reparsed_decimal != exact_decimal:
        raise NumericDomainError("decimal_round_trip_changed", number.lexeme)

    return AdmittedJsonNumber(
        lexeme=number.lexeme,
        exact_decimal=exact_decimal,
        binary64_value=converted.value,
        binary64_bits=converted.bits,
        jcs_numeric_representation=jcs_representation,
        jcs_reparsed_decimal=jcs_reparsed_decimal,
        mathematical_integer=_is_mathematical_integer(exact_decimal),
    )


def admit_semantic_numeric_domain(
    parsed: StrictParsedJson,
) -> NumericDomainAdmission:
    """Admit every exact number while preserving the strict semantic tree."""
    if not isinstance(parsed, StrictParsedJson):
        raise TypeError("parsed must be StrictParsedJson")

    root: list[Any] = [None]
    stack: list[tuple[Any, Any, Any]] = [(parsed.value, root, 0)]
    while stack:
        current, destination, position = stack.pop()
        if isinstance(current, ExactJsonNumber):
            destination[position] = admit_exact_json_number(current)
        elif isinstance(current, dict):
            admitted_object: dict[str, Any] = {}
            destination[position] = admitted_object
            for key, child in reversed(tuple(current.items())):
                if not isinstance(key, str):
                    raise TypeError("semantic object keys must be strings")
                stack.append((child, admitted_object, key))
        elif isinstance(current, list):
            admitted_array: list[Any] = [None] * len(current)
            destination[position] = admitted_array
            for index in range(len(current) - 1, -1, -1):
                stack.append((current[index], admitted_array, index))
        elif current is None or isinstance(current, (str, bool)):
            destination[position] = current
        else:
            raise TypeError("parsed tree contains a non-JSON semantic value")

    return NumericDomainAdmission(value=root[0])


def _serialize_jcs_string(value: str) -> str:
    output = ['"']
    short_escapes = {
        "\b": "\\b",
        "\t": "\\t",
        "\n": "\\n",
        "\f": "\\f",
        "\r": "\\r",
        '"': '\\"',
        "\\": "\\\\",
    }
    for character in value:
        if character in short_escapes:
            output.append(short_escapes[character])
        elif ord(character) <= 0x1F:
            output.append(f"\\u{ord(character):04x}")
        elif _contains_surrogate(character):
            raise ValueError("JCS strings must contain Unicode scalar values")
        else:
            output.append(character)
    output.append('"')
    return "".join(output)


def _utf16_sort_key(value: str) -> bytes:
    return value.encode("utf-16-be")


def _serialize_admitted_tree(value: Any) -> bytes:
    output: list[str] = []
    stack: list[Any] = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, _JcsLiteral):
            output.append(current.value)
        elif isinstance(current, AdmittedJsonNumber):
            output.append(current.jcs_numeric_representation)
        elif isinstance(current, str):
            output.append(_serialize_jcs_string(current))
        elif current is True:
            output.append("true")
        elif current is False:
            output.append("false")
        elif current is None:
            output.append("null")
        elif isinstance(current, list):
            sequence: list[Any] = [_JcsLiteral("[")]
            for index, child in enumerate(current):
                if index:
                    sequence.append(_JcsLiteral(","))
                sequence.append(child)
            sequence.append(_JcsLiteral("]"))
            stack.extend(reversed(sequence))
        elif isinstance(current, dict):
            sequence = [_JcsLiteral("{")]
            for index, (key, child) in enumerate(
                sorted(current.items(), key=lambda item: _utf16_sort_key(item[0]))
            ):
                if index:
                    sequence.append(_JcsLiteral(","))
                sequence.extend(
                    (
                        _JcsLiteral(_serialize_jcs_string(key)),
                        _JcsLiteral(":"),
                        child,
                    )
                )
            sequence.append(_JcsLiteral("}"))
            stack.extend(reversed(sequence))
        else:
            raise TypeError("admitted tree contains a non-JCS semantic value")
    return "".join(output).encode("utf-8")


def canonicalize_semantic_json(
    admitted: NumericDomainAdmission,
) -> CanonicalSemanticJson:
    """Produce RFC 8785 semantic bytes and their domain-specific SHA-256."""
    if not isinstance(admitted, NumericDomainAdmission):
        raise TypeError("admitted must be NumericDomainAdmission")
    canonical_bytes = _serialize_admitted_tree(admitted.value)
    semantic_hash = hashlib.sha256(canonical_bytes).hexdigest()
    return CanonicalSemanticJson(
        admitted=admitted,
        canonical_bytes=canonical_bytes,
        strict_parsed_semantic_payload_hash=semantic_hash,
    )


def normalize_semantic_json(extracted_payload: bytes) -> CanonicalSemanticJson:
    """Run strict parsing, numeric admission, JCS, and semantic hashing."""
    parsed = parse_strict_json_payload(extracted_payload)
    admitted = admit_semantic_numeric_domain(parsed)
    return canonicalize_semantic_json(admitted)


def hash_raw_provider_response(raw_provider_response: bytes) -> str:
    """Return the SHA-256 identity of exact raw-provider-response bytes."""
    if not isinstance(raw_provider_response, bytes):
        raise TypeError("raw_provider_response must be bytes")
    return hashlib.sha256(raw_provider_response).hexdigest()


def parse_strict_json_payload(extracted_payload: bytes) -> StrictParsedJson:
    """Parse exact UTF-8 JSON bytes without losing numeric or object identity."""
    if not isinstance(extracted_payload, bytes):
        raise TypeError("extracted_payload must be bytes")

    try:
        decoded_text = extracted_payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise StrictUtf8DecodeError("extracted_payload is not strict UTF-8") from exc

    if decoded_text.startswith("\ufeff"):
        raise StrictJsonSyntaxError("UTF-8 byte-order mark is forbidden")

    try:
        temporary_tree = json.loads(
            decoded_text,
            parse_int=_preserve_numeric_lexeme,
            parse_float=_preserve_numeric_lexeme,
            parse_constant=_reject_nonfinite_constant,
            object_pairs_hook=_preserve_object_pairs,
        )
    except StrictJsonSyntaxError:
        raise
    except json.JSONDecodeError as exc:
        raise StrictJsonSyntaxError("extracted_payload is not strict JSON") from exc

    _reject_duplicate_keys(temporary_tree)
    _reject_unpaired_surrogates(temporary_tree)
    exact_tree = _materialize_exact_tree(temporary_tree)
    return StrictParsedJson(value=exact_tree)
