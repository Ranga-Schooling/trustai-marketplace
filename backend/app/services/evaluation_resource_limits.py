"""Frozen provider-neutral normalization resource limits and enforcement."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any


RESOURCE_LIMIT_NAMES = (
    "maximum_raw_response_bytes",
    "maximum_extracted_semantic_bytes",
    "maximum_json_nesting_depth",
    "maximum_object_members",
    "maximum_total_object_members",
    "maximum_array_elements",
    "maximum_total_array_elements",
    "maximum_single_string_bytes",
    "maximum_total_string_bytes",
    "maximum_canonical_payload_bytes",
    "maximum_numeric_lexeme_length",
    "maximum_numeric_significand_or_coefficient_digits",
    "maximum_absolute_decimal_exponent_magnitude",
)

RESOURCE_LIMIT_VALUES = MappingProxyType(
    {
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
)

COUNTING_CONVENTIONS = {
    "limits_are_inclusive": True,
    "byte_limits_count": "exact_bytes",
    "json_nesting_depth": {
        "root_object_or_array_depth": 1,
        "scalar_root_depth": 0,
    },
    "object_members": (
        "every_syntactically_encountered_key_value_pair_including_duplicates_"
        "before_duplicate_key_failure"
    ),
    "array_elements": "every_syntactically_encountered_element",
    "string_bytes": {
        "encoding": "decoded_utf8_bytes",
        "includes": ["object_keys", "string_values"],
    },
    "numeric_lexeme_length_includes": [
        "sign",
        "integer_digits",
        "decimal_point_and_fraction",
        "exponent_marker",
        "exponent_sign",
        "exponent_digits",
    ],
    "numeric_coefficient_digits": (
        "all_integer_and_fractional_digits_including_leading_and_trailing_zeros"
    ),
    "absolute_decimal_exponent_magnitude": {
        "meaning": "absolute_explicit_base_10_exponent",
        "absent_exponent": 0,
    },
    "canonical_payload_size": "exact_rfc8785_jcs_utf8_bytes",
}

ENFORCEMENT_STATUS = {
    "provider_neutral_parser_and_normalizer": "implemented_and_tested",
    "raw_transport_accumulation_primitive": "implemented_and_tested",
    "provider_adapter_use_of_raw_transport_primitive": (
        "pending_pre_pilot_and_execution_blocking"
    ),
}

RESOURCE_LIMIT_PRECEDENCE = {
    "stage_order": [
        "maximum_raw_response_bytes",
        "maximum_extracted_semantic_bytes",
        "single_pass_lexical_json_preflight_in_input_order",
        "maximum_canonical_payload_bytes",
    ],
    "lexical_traversal": "left_to_right_depth_first_json_token_order",
    "same_event_order": {
        "container_entry": ["maximum_json_nesting_depth"],
        "object_member_completion": [
            "maximum_object_members",
            "maximum_total_object_members",
        ],
        "array_element_completion": [
            "maximum_array_elements",
            "maximum_total_array_elements",
        ],
        "decoded_string_scalar": ["maximum_single_string_bytes"],
        "decoded_string_completion": [
            "maximum_single_string_bytes",
            "maximum_total_string_bytes",
        ],
        "numeric_lexeme_completion": [
            "maximum_numeric_lexeme_length",
            "maximum_numeric_significand_or_coefficient_digits",
            "maximum_absolute_decimal_exponent_magnitude",
        ],
    },
}

_NUMERIC_LIMIT_ORDER = (
    "Apply lexically detectable numeric resource limits before expensive "
    "arbitrary-precision conversion, then strict numeric grammar, exact decimal "
    "parsing, semantic_numeric_domain_policy_v1, and canonical schema validation."
)
_BYTE_SURFACE_APPLICATION = {
    "wire_response_bytes": (
        "A future optional diagnostic wire-byte limit may apply when wire bytes "
        "are captured; it does not replace canonical parser limits."
    ),
    "content_decoded_response_bytes": (
        "maximum_raw_response_bytes and applicable decoded-byte limits must be "
        "enforced before UTF-8 or JSON parsing."
    ),
    "assembled_stream_response_bytes": (
        "maximum_raw_response_bytes and maximum_extracted_semantic_bytes must "
        "cover accumulated semantic fragment bytes before UTF-8 or JSON parsing."
    ),
    "native_structured_object": (
        "maximum_canonical_payload_bytes and structural limits apply before "
        "admission and hashing."
    ),
}
_FREEZE_BASIS = [
    "canonical schema maximum structures",
    "provider output-token configurations",
    "transport-envelope overhead",
    "security margin justified by deterministic local tests",
]
_RESOURCE_POLICY_FIELDS = (
    "policy_id",
    "status",
    "provider_calls_blocked_while_pending",
    "required_limits",
    "counting_conventions",
    "deterministic_limit_precedence",
    "numeric_limit_order",
    "numeric_limit_thresholds_frozen_here",
    "numeric_limit_failure_terminal",
    "existing_schema_field_limits_still_apply",
    "byte_surface_application",
    "provider_request_configuration_also_requires_output_limits",
    "parser_limits_independent_of_provider_request_limits",
    "enforcement_status",
    "numeric_values_may_be_invented_without_evidence",
    "freeze_basis",
    "limit_exceeded_result",
)
_MAXIMUM_COEFFICIENT_INTEGER = 10 ** RESOURCE_LIMIT_VALUES[
    "maximum_numeric_significand_or_coefficient_digits"
]
_MAXIMUM_LEXEME_INTEGER = 10 ** RESOURCE_LIMIT_VALUES[
    "maximum_numeric_lexeme_length"
]


def _immutable_shape(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(
            (key, _immutable_shape(value[key])) for key in sorted(value)
        )
    if isinstance(value, list):
        return tuple(_immutable_shape(child) for child in value)
    return value


_FROZEN_COUNTING_CONVENTIONS = _immutable_shape(COUNTING_CONVENTIONS)
_FROZEN_ENFORCEMENT_STATUS = _immutable_shape(ENFORCEMENT_STATUS)
_FROZEN_RESOURCE_LIMIT_PRECEDENCE = _immutable_shape(RESOURCE_LIMIT_PRECEDENCE)


class ResourceLimitPolicyError(ValueError):
    """The frozen resource-limit policy is malformed or is not executable."""


class ResourceLimitExceededError(ValueError):
    """One frozen resource ceiling was exceeded; no partial value is usable."""

    category = "failed_resource_limit"

    def __init__(self, limit_name: str) -> None:
        if limit_name not in RESOURCE_LIMIT_VALUES:
            raise ValueError("unknown_resource_limit")
        super().__init__(self.category)
        self.limit_name = limit_name
        self.maximum = RESOURCE_LIMIT_VALUES[limit_name]


class JsonResourceSyntaxError(ValueError):
    """The bounded lexical preflight found invalid JSON syntax."""


class NativeResourceTopologyError(ValueError):
    """The native input is not an acyclic JSON-compatible semantic tree."""


@dataclass(frozen=True)
class ResourceLimitRequirement:
    """One immutable requirement from the frozen resource-limit inventory."""

    name: str
    value: int
    frozen: bool


@dataclass(frozen=True)
class ResourceLimitAssessment:
    """Immutable assessment of the frozen resource-limit policy."""

    policy_id: str
    status: str
    ready: bool
    provider_calls_blocked: bool
    failure_terminal: str
    requirements: tuple[ResourceLimitRequirement, ...]
    missing_limits: tuple[str, ...]


@dataclass(frozen=True)
class JsonResourceUsage:
    """Deterministic counts observed by the bounded lexical scanner."""

    maximum_depth: int
    total_object_members: int
    total_array_elements: int
    total_string_bytes: int


def _require_exact_field(
    policy: Mapping[str, Any],
    field: str,
    expected: Any,
    error: str,
) -> None:
    actual = policy.get(field)
    if type(actual) is not type(expected) or actual != expected:
        raise ResourceLimitPolicyError(error)


def assess_resource_limit_policy(
    policy: Mapping[str, Any],
) -> ResourceLimitAssessment:
    """Validate the exact frozen policy without granting execution authority."""
    if not isinstance(policy, Mapping):
        raise ResourceLimitPolicyError("resource_limit_policy")
    if set(policy) != set(_RESOURCE_POLICY_FIELDS):
        raise ResourceLimitPolicyError("resource_limit_policy_inventory")

    _require_exact_field(
        policy,
        "policy_id",
        "normalization_parser_resource_limits_v1",
        "resource_limit_policy_id",
    )
    _require_exact_field(
        policy,
        "status",
        "frozen",
        "unsupported_resource_limit_status",
    )
    _require_exact_field(
        policy,
        "provider_calls_blocked_while_pending",
        True,
        "pending_provider_call_boundary",
    )
    _require_exact_field(
        policy,
        "numeric_limit_thresholds_frozen_here",
        True,
        "frozen_threshold_authority",
    )
    _require_exact_field(
        policy,
        "numeric_limit_failure_terminal",
        "failed_resource_limit",
        "resource_limit_terminal",
    )
    _require_exact_field(
        policy,
        "limit_exceeded_result",
        "failed_resource_limit",
        "resource_limit_terminal",
    )
    counting_conventions = policy.get("counting_conventions")
    if not isinstance(counting_conventions, dict) or _immutable_shape(
        counting_conventions
    ) != _FROZEN_COUNTING_CONVENTIONS:
        raise ResourceLimitPolicyError("resource_limit_counting_conventions")
    precedence = policy.get("deterministic_limit_precedence")
    if not isinstance(precedence, dict) or _immutable_shape(
        precedence
    ) != _FROZEN_RESOURCE_LIMIT_PRECEDENCE:
        raise ResourceLimitPolicyError("resource_limit_precedence")
    enforcement_status = policy.get("enforcement_status")
    if not isinstance(enforcement_status, dict) or _immutable_shape(
        enforcement_status
    ) != _FROZEN_ENFORCEMENT_STATUS:
        raise ResourceLimitPolicyError("resource_limit_enforcement_status")
    _require_exact_field(
        policy,
        "numeric_limit_order",
        _NUMERIC_LIMIT_ORDER,
        "resource_limit_numeric_order",
    )
    _require_exact_field(
        policy,
        "existing_schema_field_limits_still_apply",
        True,
        "resource_limit_schema_boundary",
    )
    _require_exact_field(
        policy,
        "byte_surface_application",
        _BYTE_SURFACE_APPLICATION,
        "resource_limit_byte_surfaces",
    )
    _require_exact_field(
        policy,
        "provider_request_configuration_also_requires_output_limits",
        True,
        "resource_limit_provider_configuration_boundary",
    )
    _require_exact_field(
        policy,
        "parser_limits_independent_of_provider_request_limits",
        True,
        "resource_limit_parser_independence",
    )
    _require_exact_field(
        policy,
        "numeric_values_may_be_invented_without_evidence",
        False,
        "resource_limit_evidence_boundary",
    )
    _require_exact_field(
        policy,
        "freeze_basis",
        _FREEZE_BASIS,
        "resource_limit_freeze_basis",
    )

    required_limits = policy.get("required_limits")
    if not isinstance(required_limits, Mapping):
        raise ResourceLimitPolicyError("resource_limit_inventory")
    if set(required_limits) != set(RESOURCE_LIMIT_NAMES):
        raise ResourceLimitPolicyError("resource_limit_inventory")
    for name, expected in RESOURCE_LIMIT_VALUES.items():
        actual = required_limits[name]
        if isinstance(actual, bool) or type(actual) is not int or actual != expected:
            raise ResourceLimitPolicyError(f"resource_limit_value:{name}")

    requirements = tuple(
        ResourceLimitRequirement(name=name, value=RESOURCE_LIMIT_VALUES[name], frozen=True)
        for name in RESOURCE_LIMIT_NAMES
    )
    return ResourceLimitAssessment(
        policy_id="normalization_parser_resource_limits_v1",
        status="frozen",
        ready=True,
        provider_calls_blocked=False,
        failure_terminal="failed_resource_limit",
        requirements=requirements,
        missing_limits=(),
    )


def require_resource_limits_ready(assessment: ResourceLimitAssessment) -> None:
    """Require a validated frozen assessment without authorizing provider use."""
    if not isinstance(assessment, ResourceLimitAssessment):
        raise ResourceLimitPolicyError("resource_limit_assessment")
    if not assessment.ready or assessment.missing_limits:
        raise ResourceLimitPolicyError("resource_limits_pending")


def _raise_if_exceeded(limit_name: str, observed: int) -> None:
    if observed > RESOURCE_LIMIT_VALUES[limit_name]:
        raise ResourceLimitExceededError(limit_name)


def account_raw_response_chunk(accumulated_bytes: int, chunk: bytes) -> int:
    """Account one transport chunk before a caller appends it to raw storage."""
    if isinstance(accumulated_bytes, bool) or type(accumulated_bytes) is not int:
        raise TypeError("accumulated_bytes must be an integer")
    if accumulated_bytes < 0:
        raise ValueError("accumulated_bytes must be nonnegative")
    if not isinstance(chunk, bytes):
        raise TypeError("chunk must be bytes")
    total = accumulated_bytes + len(chunk)
    _raise_if_exceeded("maximum_raw_response_bytes", total)
    return total


def enforce_extracted_semantic_bytes(extracted_payload: bytes) -> None:
    """Reject oversized extracted bytes before UTF-8 decoding or JSON work."""
    if not isinstance(extracted_payload, bytes):
        raise TypeError("extracted_payload must be bytes")
    _raise_if_exceeded("maximum_extracted_semantic_bytes", len(extracted_payload))


def account_canonical_payload_fragment(
    accumulated_bytes: int,
    fragment: bytes,
) -> int:
    """Account JCS bytes before appending a fragment to canonical storage."""
    if isinstance(accumulated_bytes, bool) or type(accumulated_bytes) is not int:
        raise TypeError("accumulated_bytes must be an integer")
    if accumulated_bytes < 0:
        raise ValueError("accumulated_bytes must be nonnegative")
    if not isinstance(fragment, bytes):
        raise TypeError("fragment must be bytes")
    total = accumulated_bytes + len(fragment)
    _raise_if_exceeded("maximum_canonical_payload_bytes", total)
    return total


def _utf8_scalar_length(character: str) -> int:
    codepoint = ord(character)
    if codepoint <= 0x7F:
        return 1
    if codepoint <= 0x7FF:
        return 2
    if 0xD800 <= codepoint <= 0xDFFF:
        raise JsonResourceSyntaxError("unpaired_surrogate")
    if codepoint <= 0xFFFF:
        return 3
    return 4


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
                RESOURCE_LIMIT_VALUES[
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


def _raise_if_decimal_exponent_exceeded(exponent_digits: str) -> None:
    exponent_magnitude = 0
    maximum = RESOURCE_LIMIT_VALUES[
        "maximum_absolute_decimal_exponent_magnitude"
    ]
    for digit in exponent_digits:
        exponent_magnitude = min(maximum + 1, exponent_magnitude * 10 + int(digit))
    _raise_if_exceeded(
        "maximum_absolute_decimal_exponent_magnitude",
        exponent_magnitude,
    )


class _JsonResourceScanner:
    _WHITESPACE = " \t\r\n"
    _HEX = frozenset("0123456789abcdefABCDEF")

    def __init__(self, text: str) -> None:
        self.text = text
        self.index = 0
        self.maximum_depth = 0
        self.total_object_members = 0
        self.total_array_elements = 0
        self.total_string_bytes = 0

    def scan(self) -> JsonResourceUsage:
        self._skip_whitespace()
        self._parse_value(0)
        self._skip_whitespace()
        if self.index != len(self.text):
            raise JsonResourceSyntaxError("trailing_content")
        return JsonResourceUsage(
            maximum_depth=self.maximum_depth,
            total_object_members=self.total_object_members,
            total_array_elements=self.total_array_elements,
            total_string_bytes=self.total_string_bytes,
        )

    def _skip_whitespace(self) -> None:
        while self.index < len(self.text) and self.text[self.index] in self._WHITESPACE:
            self.index += 1

    def _parse_value(self, parent_depth: int) -> None:
        self._skip_whitespace()
        if self.index >= len(self.text):
            raise JsonResourceSyntaxError("missing_value")
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
            raise JsonResourceSyntaxError("invalid_value")

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
                raise JsonResourceSyntaxError("object_key")
            self._parse_string()
            self._skip_whitespace()
            if not self._consume(":"):
                raise JsonResourceSyntaxError("object_colon")
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
                raise JsonResourceSyntaxError("object_separator")
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
                raise JsonResourceSyntaxError("array_separator")
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
                raise JsonResourceSyntaxError("raw_control_character")
            if character != "\\":
                decoded_bytes += _utf8_scalar_length(character)
                _raise_if_exceeded("maximum_single_string_bytes", decoded_bytes)
                continue
            if self.index >= len(self.text):
                raise JsonResourceSyntaxError("truncated_escape")
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
                raise JsonResourceSyntaxError("invalid_escape")
            _raise_if_exceeded("maximum_single_string_bytes", decoded_bytes)
        raise JsonResourceSyntaxError("unterminated_string")

    def _parse_unicode_escape(self) -> int:
        if self.index + 4 > len(self.text):
            raise JsonResourceSyntaxError("truncated_unicode_escape")
        digits = self.text[self.index : self.index + 4]
        if any(character not in self._HEX for character in digits):
            raise JsonResourceSyntaxError("invalid_unicode_escape")
        self.index += 4
        scalar = int(digits, 16)
        if 0xD800 <= scalar <= 0xDBFF:
            if self.text[self.index : self.index + 2] != "\\u":
                raise JsonResourceSyntaxError("unpaired_high_surrogate")
            self.index += 2
            if self.index + 4 > len(self.text):
                raise JsonResourceSyntaxError("truncated_low_surrogate")
            low_digits = self.text[self.index : self.index + 4]
            if any(character not in self._HEX for character in low_digits):
                raise JsonResourceSyntaxError("invalid_low_surrogate")
            self.index += 4
            low = int(low_digits, 16)
            if not 0xDC00 <= low <= 0xDFFF:
                raise JsonResourceSyntaxError("unpaired_high_surrogate")
            return 0x10000 + ((scalar - 0xD800) << 10) + (low - 0xDC00)
        if 0xDC00 <= scalar <= 0xDFFF:
            raise JsonResourceSyntaxError("unpaired_low_surrogate")
        return scalar

    def _parse_literal(self, literal: str) -> None:
        if not self.text.startswith(literal, self.index):
            raise JsonResourceSyntaxError("invalid_literal")
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
                character in "0123456789"
                for character in token[:exponent_offset]
            )
            _raise_if_exceeded(
                "maximum_numeric_significand_or_coefficient_digits",
                coefficient_digits,
            )
            if exponent_offset < len(token):
                exponent = token[exponent_offset + 1 :]
                if exponent[:1] in "+-":
                    exponent = exponent[1:]
                if exponent and all(character in "0123456789" for character in exponent):
                    _raise_if_decimal_exponent_exceeded(exponent)
        if self._consume("-") and self.index >= len(self.text):
            raise JsonResourceSyntaxError("incomplete_number")
        if self._consume("0"):
            if self.index < len(self.text) and self.text[self.index] in "0123456789":
                raise JsonResourceSyntaxError("leading_zero")
        else:
            if self.index >= len(self.text) or self.text[self.index] not in "123456789":
                raise JsonResourceSyntaxError("integer_digits")
            while self.index < len(self.text) and self.text[self.index] in "0123456789":
                self.index += 1
        if self._consume("."):
            fraction_start = self.index
            while self.index < len(self.text) and self.text[self.index] in "0123456789":
                self.index += 1
            if self.index == fraction_start:
                raise JsonResourceSyntaxError("fraction_digits")
        if self.index < len(self.text) and self.text[self.index] in "eE":
            self.index += 1
            if self.index < len(self.text) and self.text[self.index] in "+-":
                self.index += 1
            exponent_start = self.index
            while self.index < len(self.text) and self.text[self.index] in "0123456789":
                self.index += 1
            if self.index == exponent_start:
                raise JsonResourceSyntaxError("exponent_digits")
        _validate_numeric_lexeme(self.text[start : self.index])


def scan_json_resource_limits(decoded_text: str) -> JsonResourceUsage:
    """Validate JSON lexically and enforce all pre-materialization ceilings."""
    if not isinstance(decoded_text, str):
        raise TypeError("decoded_text must be str")
    return _JsonResourceScanner(decoded_text).scan()


def _int_to_decimal_text(value: int) -> str:
    negative = value < 0
    remaining = -value if negative else value
    if remaining == 0:
        return "0"
    chunks: list[int] = []
    while remaining:
        remaining, chunk = divmod(remaining, 1_000_000_000)
        chunks.append(chunk)
    text = str(chunks.pop()) + "".join(f"{chunk:09d}" for chunk in reversed(chunks))
    return "-" + text if negative else text


def native_number_lexeme(value: int | float | Decimal) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        absolute = -value if value < 0 else value
        if absolute >= _MAXIMUM_LEXEME_INTEGER:
            raise ResourceLimitExceededError("maximum_numeric_lexeme_length")
        if absolute >= _MAXIMUM_COEFFICIENT_INTEGER:
            raise ResourceLimitExceededError(
                "maximum_numeric_significand_or_coefficient_digits"
            )
        return _int_to_decimal_text(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise NativeResourceTopologyError("nonfinite_native_number")
        return repr(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise NativeResourceTopologyError("nonfinite_native_number")
        digits = len(value.as_tuple().digits)
        _raise_if_exceeded("maximum_numeric_lexeme_length", digits)
        _raise_if_exceeded(
            "maximum_numeric_significand_or_coefficient_digits",
            digits,
        )
        return str(value)
    raise NativeResourceTopologyError("non_json_native_number")


def _enforce_materialized_json_resource_limits(
    value: Any,
    *,
    numeric_lexeme_resolver: Callable[[Any], str | None],
) -> None:
    """Bound one materialized tree in raw-JSON lexical event order."""
    total_object_members = 0
    total_array_elements = 0
    total_string_bytes = 0
    active_container_ids: set[int] = set()
    stack: list[tuple[str, Any, int, list[int] | None]] = [
        ("enter", value, 0, None)
    ]

    def account_string(text: str) -> None:
        nonlocal total_string_bytes
        byte_count = 0
        for character in text:
            codepoint = ord(character)
            if codepoint <= 0x7F:
                byte_count += 1
            elif codepoint <= 0x7FF:
                byte_count += 2
            elif 0xD800 <= codepoint <= 0xDFFF:
                raise NativeResourceTopologyError("non_scalar_native_string")
            elif codepoint <= 0xFFFF:
                byte_count += 3
            else:
                byte_count += 4
            _raise_if_exceeded("maximum_single_string_bytes", byte_count)
        total_string_bytes += byte_count
        _raise_if_exceeded("maximum_total_string_bytes", total_string_bytes)

    while stack:
        operation, current, parent_depth, frame = stack.pop()
        if operation == "account_string":
            account_string(current)
            continue
        if operation == "complete_object_member":
            assert frame is not None
            frame[0] += 1
            _raise_if_exceeded("maximum_object_members", frame[0])
            total_object_members += 1
            _raise_if_exceeded(
                "maximum_total_object_members",
                total_object_members,
            )
            continue
        if operation == "complete_array_element":
            assert frame is not None
            frame[0] += 1
            _raise_if_exceeded("maximum_array_elements", frame[0])
            total_array_elements += 1
            _raise_if_exceeded(
                "maximum_total_array_elements",
                total_array_elements,
            )
            continue
        if operation in {"next_object_member", "next_array_element"}:
            iterator, container = current
            try:
                child = next(iterator)
            except StopIteration:
                active_container_ids.remove(id(container))
                continue
            stack.append((operation, current, parent_depth, frame))
            if operation == "next_object_member":
                key, value_child = child
                if not isinstance(key, str):
                    raise NativeResourceTopologyError("non_string_native_key")
                stack.append(
                    ("complete_object_member", None, parent_depth, frame)
                )
                stack.append(("enter", value_child, parent_depth, None))
                stack.append(("account_string", key, parent_depth, None))
            else:
                stack.append(
                    ("complete_array_element", None, parent_depth, frame)
                )
                stack.append(("enter", child, parent_depth, None))
            continue
        if current is None or isinstance(current, bool):
            continue
        if isinstance(current, str):
            account_string(current)
            continue
        numeric_lexeme = numeric_lexeme_resolver(current)
        if numeric_lexeme is not None:
            _validate_numeric_lexeme(numeric_lexeme)
            continue
        if isinstance(current, dict):
            depth = parent_depth + 1
            _raise_if_exceeded("maximum_json_nesting_depth", depth)
            if id(current) in active_container_ids:
                raise NativeResourceTopologyError("native_container_cycle")
            active_container_ids.add(id(current))
            stack.append(
                (
                    "next_object_member",
                    (iter(current.items()), current),
                    depth,
                    [0],
                )
            )
            continue
        if isinstance(current, list):
            depth = parent_depth + 1
            _raise_if_exceeded("maximum_json_nesting_depth", depth)
            if id(current) in active_container_ids:
                raise NativeResourceTopologyError("native_container_cycle")
            active_container_ids.add(id(current))
            stack.append(
                (
                    "next_array_element",
                    (iter(current), current),
                    depth,
                    [0],
                )
            )
            continue
        raise NativeResourceTopologyError("non_json_native_value")


def enforce_materialized_json_resource_limits(
    value: Any,
    *,
    numeric_lexeme_resolver: Callable[[Any], str | None],
) -> None:
    """Bound an admitted/materialized JSON tree before canonical allocation."""
    if not callable(numeric_lexeme_resolver):
        raise TypeError("numeric_lexeme_resolver must be callable")
    _enforce_materialized_json_resource_limits(
        value,
        numeric_lexeme_resolver=numeric_lexeme_resolver,
    )


def enforce_native_json_resource_limits(value: Any) -> None:
    """Bound a native JSON-like tree before allocating a normalized copy."""

    def resolve_numeric_lexeme(current: Any) -> str | None:
        if isinstance(current, (int, float, Decimal)) and not isinstance(
            current,
            bool,
        ):
            return native_number_lexeme(current)
        return None

    _enforce_materialized_json_resource_limits(
        value,
        numeric_lexeme_resolver=resolve_numeric_lexeme,
    )
