"""Frozen provider-neutral retrieval trace position and identifier primitives.

This module implements only the representational rules that are already exact
in ``normalization-parser.v1.json``.  It does not map provider-native IDs,
attest provider ordering, choose operational source/evidence count limits,
construct retrieval bundles, or authorize provider execution.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


TRACE_POSITION_FIELDS = (
    "retrieval_attempt_ordinal",
    "tool_call_ordinal",
    "result_ordinal",
    "evidence_observation_ordinal",
)

_MAX_IDENTIFIER_LENGTH = 64
_MAX_IDENTIFIER_DECIMAL_DIGITS = 60


class RetrievalTraceValidationError(ValueError):
    """Canonical trace positions violate the frozen ordinal contract."""

    outcome = "failed_trace_validation"


class RetrievalIdentifierLimitError(ValueError):
    """A canonical source/evidence ID exceeds frozen schema capacity."""

    outcome = "failed_resource_limit"


def _trace_failure() -> RetrievalTraceValidationError:
    return RetrievalTraceValidationError("failed_trace_validation")


def _require_positive_integer(value: Any) -> int:
    if type(value) is not int or value < 1:
        raise _trace_failure()
    return value


def validate_trace_ordinal_scope(
    field_name: str,
    ordinals: Sequence[Any],
) -> tuple[int, ...]:
    """Validate one frozen parent scope without sorting, defaulting, or repair."""
    if field_name not in TRACE_POSITION_FIELDS or isinstance(
        ordinals,
        (str, bytes, bytearray),
    ) or not isinstance(ordinals, Sequence):
        raise _trace_failure()

    validated = tuple(_require_positive_integer(value) for value in ordinals)
    if len(set(validated)) != len(validated) or set(validated) != set(
        range(1, len(validated) + 1)
    ):
        raise _trace_failure()
    return validated


def source_observation_key(
    retrieval_attempt_ordinal: Any,
    tool_call_ordinal: Any,
    result_ordinal: Any,
) -> tuple[int, int, int]:
    """Return the frozen lexicographic source-observation key."""
    return (
        _require_positive_integer(retrieval_attempt_ordinal),
        _require_positive_integer(tool_call_ordinal),
        _require_positive_integer(result_ordinal),
    )


def evidence_observation_key(
    retrieval_attempt_ordinal: Any,
    tool_call_ordinal: Any,
    result_ordinal: Any,
    evidence_observation_ordinal: Any,
) -> tuple[int, int, int, int]:
    """Return the frozen lexicographic evidence-observation key."""
    return source_observation_key(
        retrieval_attempt_ordinal,
        tool_call_ordinal,
        result_ordinal,
    ) + (_require_positive_integer(evidence_observation_ordinal),)


def _decimal_component(ordinal: Any) -> str:
    value = _require_positive_integer(ordinal)
    if value >= 10**_MAX_IDENTIFIER_DECIMAL_DIGITS:
        raise RetrievalIdentifierLimitError("failed_resource_limit")
    return str(value).zfill(4)


def render_source_id(source_ordinal: Any) -> str:
    """Render one contiguous canonical source ordinal as ``src-...``."""
    return f"src-{_decimal_component(source_ordinal)}"


def render_evidence_id(source_ordinal: Any, evidence_ordinal: Any) -> str:
    """Render one source-linked canonical evidence identifier."""
    source_component = _decimal_component(source_ordinal)
    evidence_component = _decimal_component(evidence_ordinal)
    identifier = f"ev-{source_component}-{evidence_component}"
    if len(identifier) > _MAX_IDENTIFIER_LENGTH:
        raise RetrievalIdentifierLimitError("failed_resource_limit")
    return identifier
