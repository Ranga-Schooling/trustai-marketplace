"""Provider-neutral normalization primitives."""

from __future__ import annotations

import hashlib
import json
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
class _NumericToken:
    lexeme: str


@dataclass(frozen=True)
class _ObjectPairs:
    pairs: tuple[tuple[str, Any], ...]


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
