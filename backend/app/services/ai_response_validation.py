"""Provider-neutral validation primitives for structured AI responses.

The current runtime does not import this module yet.  It is a small production
extraction of the bounded parser and text-result invariants proven by the
provider evaluation work, ready for provider adapters to consume separately.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from app.schemas.schemas import AIAnalysisResult, RiskIndicatorOut


AI_RESPONSE_RESOURCE_LIMITS = MappingProxyType(
    {
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
)


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


class ResourceLimitExceededError(ValueError):
    """One response ceiling was exceeded; no partial value is usable."""

    category = "failed_resource_limit"

    def __init__(self, limit_name: str) -> None:
        if limit_name not in AI_RESPONSE_RESOURCE_LIMITS:
            raise ValueError("unknown_resource_limit")
        super().__init__(self.category)
        self.limit_name = limit_name
        self.maximum = AI_RESPONSE_RESOURCE_LIMITS[limit_name]


class AnalysisStructureError(ValueError):
    """The provider result does not have the exact production object shape."""


class DeterministicValidationError(ValueError):
    """A schema-valid result violates deterministic domain relationships."""

    def __init__(
        self,
        *,
        validator_id: str,
        terminal_outcome: str,
        reason: str,
    ) -> None:
        super().__init__(f"{validator_id}:{reason}")
        self.validator_id = validator_id
        self.terminal_outcome = terminal_outcome
        self.reason = reason


@dataclass(frozen=True)
class ExactJsonNumber:
    """One JSON number with both lexical and exact mathematical identity."""

    lexeme: str
    exact_decimal: Decimal


@dataclass(frozen=True)
class StrictParsedJson:
    """Opaque strict-parsing result before schema validation."""

    value: Any


@dataclass(frozen=True)
class _NumericToken:
    lexeme: str


@dataclass(frozen=True)
class _ObjectPairs:
    pairs: tuple[tuple[str, Any], ...]


def _raise_if_exceeded(limit_name: str, observed: int) -> None:
    if observed > AI_RESPONSE_RESOURCE_LIMITS[limit_name]:
        raise ResourceLimitExceededError(limit_name)


def _utf8_scalar_length(character: str) -> int:
    codepoint = ord(character)
    if codepoint <= 0x7F:
        return 1
    if codepoint <= 0x7FF:
        return 2
    if 0xD800 <= codepoint <= 0xDFFF:
        raise StrictJsonSyntaxError("Unpaired Unicode surrogate is forbidden")
    if codepoint <= 0xFFFF:
        return 3
    return 4


def _raise_if_decimal_exponent_exceeded(exponent_digits: str) -> None:
    exponent_magnitude = 0
    maximum = AI_RESPONSE_RESOURCE_LIMITS[
        "maximum_absolute_decimal_exponent_magnitude"
    ]
    for digit in exponent_digits:
        exponent_magnitude = min(maximum + 1, exponent_magnitude * 10 + int(digit))
    _raise_if_exceeded(
        "maximum_absolute_decimal_exponent_magnitude",
        exponent_magnitude,
    )


def _validate_numeric_lexeme(lexeme: str) -> None:
    _raise_if_exceeded("maximum_numeric_lexeme_length", len(lexeme))

    index = int(lexeme.startswith("-"))
    coefficient_digits = 0
    while index < len(lexeme) and lexeme[index] in "0123456789":
        coefficient_digits += 1
        index += 1
    if index < len(lexeme) and lexeme[index] == ".":
        index += 1
        while index < len(lexeme) and lexeme[index] in "0123456789":
            coefficient_digits += 1
            index += 1
    _raise_if_exceeded(
        "maximum_numeric_significand_or_coefficient_digits",
        coefficient_digits,
    )

    exponent_magnitude = 0
    if index < len(lexeme) and lexeme[index] in "eE":
        index += 1
        if index < len(lexeme) and lexeme[index] in "+-":
            index += 1
        while index < len(lexeme):
            exponent_magnitude = min(
                AI_RESPONSE_RESOURCE_LIMITS[
                    "maximum_absolute_decimal_exponent_magnitude"
                ]
                + 1,
                exponent_magnitude * 10 + int(lexeme[index]),
            )
            index += 1
    _raise_if_exceeded(
        "maximum_absolute_decimal_exponent_magnitude",
        exponent_magnitude,
    )


class _JsonResourceScanner:
    """Single-pass strict JSON syntax and bounded-resource preflight."""

    _WHITESPACE = " \t\r\n"
    _HEX = frozenset("0123456789abcdefABCDEF")

    def __init__(self, text: str) -> None:
        self.text = text
        self.index = 0
        self.maximum_depth = 0
        self.total_object_members = 0
        self.total_array_elements = 0
        self.total_string_bytes = 0

    def scan(self) -> None:
        self._skip_whitespace()
        self._parse_value(0)
        self._skip_whitespace()
        if self.index != len(self.text):
            raise StrictJsonSyntaxError("extracted_payload is not strict JSON")

    def _skip_whitespace(self) -> None:
        while self.index < len(self.text) and self.text[self.index] in self._WHITESPACE:
            self.index += 1

    def _parse_value(self, parent_depth: int) -> None:
        self._skip_whitespace()
        if self.index >= len(self.text):
            raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
        character = self.text[self.index]
        if character == "{":
            self._parse_object(parent_depth + 1)
        elif character == "[":
            self._parse_array(parent_depth + 1)
        elif character == '"':
            self._parse_string()
        elif character == "t":
            self._parse_literal("true")
        elif character == "f":
            self._parse_literal("false")
        elif character == "n":
            self._parse_literal("null")
        elif character == "-" or character in "0123456789":
            self._parse_number()
        else:
            raise StrictJsonSyntaxError("extracted_payload is not strict JSON")

    def _enter_container(self, depth: int) -> None:
        _raise_if_exceeded("maximum_json_nesting_depth", depth)
        self.maximum_depth = max(self.maximum_depth, depth)

    def _parse_object(self, depth: int) -> None:
        self._enter_container(depth)
        self.index += 1
        self._skip_whitespace()
        if self._consume("}"):
            return
        member_count = 0
        while True:
            if self.index >= len(self.text) or self.text[self.index] != '"':
                raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
            self._parse_string()
            self._skip_whitespace()
            if not self._consume(":"):
                raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
            self._parse_value(depth)
            member_count += 1
            _raise_if_exceeded("maximum_object_members", member_count)
            self.total_object_members += 1
            _raise_if_exceeded(
                "maximum_total_object_members",
                self.total_object_members,
            )
            self._skip_whitespace()
            if self._consume("}"):
                return
            if not self._consume(","):
                raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
            self._skip_whitespace()

    def _parse_array(self, depth: int) -> None:
        self._enter_container(depth)
        self.index += 1
        self._skip_whitespace()
        if self._consume("]"):
            return
        element_count = 0
        while True:
            self._parse_value(depth)
            element_count += 1
            _raise_if_exceeded("maximum_array_elements", element_count)
            self.total_array_elements += 1
            _raise_if_exceeded(
                "maximum_total_array_elements",
                self.total_array_elements,
            )
            self._skip_whitespace()
            if self._consume("]"):
                return
            if not self._consume(","):
                raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
            self._skip_whitespace()

    def _consume(self, expected: str) -> bool:
        if self.index < len(self.text) and self.text[self.index] == expected:
            self.index += 1
            return True
        return False

    def _parse_string(self) -> None:
        self.index += 1
        decoded_bytes = 0
        while self.index < len(self.text):
            character = self.text[self.index]
            self.index += 1
            if character == '"':
                _raise_if_exceeded("maximum_single_string_bytes", decoded_bytes)
                self.total_string_bytes += decoded_bytes
                _raise_if_exceeded(
                    "maximum_total_string_bytes",
                    self.total_string_bytes,
                )
                return
            if ord(character) <= 0x1F:
                raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
            if character != "\\":
                decoded_bytes += _utf8_scalar_length(character)
                _raise_if_exceeded("maximum_single_string_bytes", decoded_bytes)
                continue
            if self.index >= len(self.text):
                raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
            escape = self.text[self.index]
            self.index += 1
            if escape in '"\\/':
                decoded_bytes += 1
            elif escape in "bfnrt":
                decoded_bytes += 1
            elif escape == "u":
                scalar = self._parse_unicode_escape()
                decoded_bytes += _utf8_scalar_length(chr(scalar))
            else:
                raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
            _raise_if_exceeded("maximum_single_string_bytes", decoded_bytes)
        raise StrictJsonSyntaxError("extracted_payload is not strict JSON")

    def _parse_unicode_escape(self) -> int:
        if self.index + 4 > len(self.text):
            raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
        digits = self.text[self.index : self.index + 4]
        if any(character not in self._HEX for character in digits):
            raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
        self.index += 4
        scalar = int(digits, 16)
        if 0xD800 <= scalar <= 0xDBFF:
            if self.text[self.index : self.index + 2] != "\\u":
                raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
            self.index += 2
            if self.index + 4 > len(self.text):
                raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
            low_digits = self.text[self.index : self.index + 4]
            if any(character not in self._HEX for character in low_digits):
                raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
            self.index += 4
            low = int(low_digits, 16)
            if not 0xDC00 <= low <= 0xDFFF:
                raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
            return 0x10000 + ((scalar - 0xD800) << 10) + (low - 0xDC00)
        if 0xDC00 <= scalar <= 0xDFFF:
            raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
        return scalar

    def _parse_literal(self, literal: str) -> None:
        if not self.text.startswith(literal, self.index):
            raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
        self.index += len(literal)

    def _parse_number(self) -> None:
        start = self.index
        token_end = start
        while (
            token_end < len(self.text)
            and self.text[token_end] not in ",]} \t\r\n"
        ):
            token_end += 1
        token = self.text[start:token_end]
        if token and all(character in "+-.eE0123456789" for character in token):
            _raise_if_exceeded("maximum_numeric_lexeme_length", len(token))
            exponent_offset = next(
                (
                    offset
                    for offset, character in enumerate(token)
                    if character in "eE"
                ),
                len(token),
            )
            coefficient_digits = sum(
                character in "0123456789" for character in token[:exponent_offset]
            )
            _raise_if_exceeded(
                "maximum_numeric_significand_or_coefficient_digits",
                coefficient_digits,
            )
            if exponent_offset < len(token):
                exponent = token[exponent_offset + 1 :]
                if exponent[:1] in "+-":
                    exponent = exponent[1:]
                if exponent and all(
                    character in "0123456789" for character in exponent
                ):
                    _raise_if_decimal_exponent_exceeded(exponent)
        if self._consume("-") and self.index >= len(self.text):
            raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
        if self._consume("0"):
            if self.index < len(self.text) and self.text[self.index] in "0123456789":
                raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
        else:
            if self.index >= len(self.text) or self.text[self.index] not in "123456789":
                raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
            while self.index < len(self.text) and self.text[self.index] in "0123456789":
                self.index += 1
        if self._consume("."):
            fraction_start = self.index
            while self.index < len(self.text) and self.text[self.index] in "0123456789":
                self.index += 1
            if self.index == fraction_start:
                raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
        if self.index < len(self.text) and self.text[self.index] in "eE":
            self.index += 1
            if self.index < len(self.text) and self.text[self.index] in "+-":
                self.index += 1
            exponent_start = self.index
            while self.index < len(self.text) and self.text[self.index] in "0123456789":
                self.index += 1
            if self.index == exponent_start:
                raise StrictJsonSyntaxError("extracted_payload is not strict JSON")
        _validate_numeric_lexeme(self.text[start : self.index])


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


def parse_strict_json_payload(extracted_payload: bytes) -> StrictParsedJson:
    """Parse bounded UTF-8 JSON without losing numeric or object identity."""
    if not isinstance(extracted_payload, bytes):
        raise TypeError("extracted_payload must be bytes")

    _raise_if_exceeded(
        "maximum_extracted_semantic_bytes",
        len(extracted_payload),
    )
    try:
        decoded_text = extracted_payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise StrictUtf8DecodeError("extracted_payload is not strict UTF-8") from exc

    if decoded_text.startswith("\ufeff"):
        raise StrictJsonSyntaxError("UTF-8 byte-order mark is forbidden")

    _JsonResourceScanner(decoded_text).scan()
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
    return StrictParsedJson(value=_materialize_exact_tree(temporary_tree))


_ANALYSIS_FIELDS = frozenset(AIAnalysisResult.model_fields)
_INDICATOR_FIELDS = frozenset(RiskIndicatorOut.model_fields)


def require_exact_analysis_shape(candidate: Any) -> dict[str, Any]:
    """Reject missing or unexpected model-owned fields before Pydantic."""
    if type(candidate) is not dict or set(candidate) != _ANALYSIS_FIELDS:
        raise AnalysisStructureError("analysis_result_shape")
    indicators = candidate.get("risk_indicators")
    if type(indicators) is not list:
        raise AnalysisStructureError("analysis_result_shape")
    if any(
        type(item) is not dict or set(item) != _INDICATOR_FIELDS
        for item in indicators
    ):
        raise AnalysisStructureError("analysis_result_shape")
    return candidate


def _reject_cross_field(reason: str) -> None:
    raise DeterministicValidationError(
        validator_id="text_cross_field_validator_v1",
        terminal_outcome="failed_cross_field_validation",
        reason=reason,
    )


def validate_analysis_cross_fields(candidate: dict[str, Any]) -> None:
    """Accept or reject the frozen indicator/risk/recommendation relationship."""
    severities = tuple(
        indicator["severity"] for indicator in candidate["risk_indicators"]
    )
    if "high" in severities:
        expected_risk = "high"
    elif "medium" in severities:
        expected_risk = "medium"
    else:
        expected_risk = "low"

    if candidate["risk_level"] != expected_risk:
        _reject_cross_field("risk_level_indicator_mismatch")

    expected_recommendation = {
        "low": "buy",
        "medium": "caution",
        "high": "avoid",
    }[candidate["risk_level"]]
    if candidate["recommendation"] != expected_recommendation:
        _reject_cross_field("risk_recommendation_mismatch")
