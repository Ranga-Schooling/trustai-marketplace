"""Frozen provider-neutral retrieval trace position and identifier primitives.

This module implements only the representational rules that are already exact
in ``normalization-parser.v1.json``.  It does not map provider-native IDs,
attest provider ordering, choose operational source/evidence count limits,
construct retrieval bundles, or authorize provider execution.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.services.url_security import validate_url_security


TRACE_POSITION_FIELDS = (
    "retrieval_attempt_ordinal",
    "tool_call_ordinal",
    "result_ordinal",
    "evidence_observation_ordinal",
)

_MAX_IDENTIFIER_LENGTH = 64
_MAX_IDENTIFIER_DECIMAL_DIGITS = 60
_URL_SECURITY_POLICY_IDENTITY = (
    "url_security_policy_v1",
    "v1",
    "fcc37b299f84cccb7522c2db150022e3e92f04430c50e01b94bb7f7fa6e5b44e",
)


class RetrievalTraceValidationError(ValueError):
    """Canonical trace positions violate the frozen ordinal contract."""

    outcome = "failed_trace_validation"


class RetrievalIdentifierLimitError(ValueError):
    """A canonical source/evidence ID exceeds frozen schema capacity."""

    outcome = "failed_resource_limit"


class RetrievalUrlSecurityValidationError(ValueError):
    """A required exact URL was not accepted as public-safe."""

    outcome = "failed_url_security_validation"


class RetrievalCanonicalValidationError(ValueError):
    """Required canonical source data does not satisfy the frozen schema."""

    outcome = "failed_canonical_validation"


_PUBLIC_SAFE_KEY_TOKEN = object()


class PublicSafeDeduplicationKey:
    """A URL key derived only after application-owned security validation."""

    __slots__ = (
        "_policy_identity",
        "_restricted_trace_reference",
        "_safe_canonical_url",
        "_url_role",
        "_value",
    )

    def __init__(
        self,
        value: str,
        *,
        safe_canonical_url: str | None = None,
        url_role: str | None = None,
        restricted_trace_reference: str | None = None,
        policy_identity: tuple[str, str, str] | None = None,
        _token: object | None = None,
    ) -> None:
        if _token is not _PUBLIC_SAFE_KEY_TOKEN:
            raise RetrievalUrlSecurityValidationError(
                "failed_url_security_validation"
            )
        object.__setattr__(self, "_value", value)
        object.__setattr__(self, "_safe_canonical_url", safe_canonical_url)
        object.__setattr__(self, "_url_role", url_role)
        object.__setattr__(
            self,
            "_restricted_trace_reference",
            restricted_trace_reference,
        )
        object.__setattr__(self, "_policy_identity", policy_identity)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("public_safe_deduplication_key_is_immutable")

    def __delattr__(self, _name: str) -> None:
        raise AttributeError("public_safe_deduplication_key_is_immutable")

    @property
    def value(self) -> str:
        return self._value

    @property
    def url_role(self) -> str:
        return self._url_role  # type: ignore[return-value]

    @property
    def safe_canonical_url(self) -> str:
        return self._safe_canonical_url  # type: ignore[return-value]

    @property
    def restricted_trace_reference(self) -> str:
        return self._restricted_trace_reference  # type: ignore[return-value]

    @property
    def policy_identity(self) -> tuple[str, str, str]:
        return self._policy_identity  # type: ignore[return-value]

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, PublicSafeDeduplicationKey)
            and self._value == other._value
        )

    def __hash__(self) -> int:
        return hash(self._value)

    def __repr__(self) -> str:
        return "PublicSafeDeduplicationKey(<validated>)"


@dataclass(frozen=True)
class RetrievalSourceObservation:
    """One successful or failed atomic source observation from canonical trace."""

    retrieval_attempt_ordinal: Any
    tool_call_ordinal: Any
    result_ordinal: Any
    successful: Any
    deduplication_key: PublicSafeDeduplicationKey | None
    name: Any
    captured_at: Any


@dataclass(frozen=True)
class RetrievalEvidenceObservation:
    """One successful or failed evidence observation tied to an atomic result."""

    retrieval_attempt_ordinal: Any
    tool_call_ordinal: Any
    result_ordinal: Any
    evidence_observation_ordinal: Any
    successful: Any
    source_deduplication_key: PublicSafeDeduplicationKey | None


_TRACE_INVENTORY_TOKEN = object()


@dataclass(frozen=True)
class ValidatedTracePositionInventory:
    """Exact complete atomic-result/evidence positions for one mapped trace."""

    source_positions: frozenset[tuple[int, int, int]]
    evidence_positions: frozenset[tuple[int, int, int, int]]
    _token: object | None = None

    def __post_init__(self) -> None:
        if self._token is not _TRACE_INVENTORY_TOKEN:
            raise _trace_failure()


@dataclass(frozen=True)
class AllocatedCanonicalSource:
    source_id: str
    source_ordinal: int
    safe_canonical_url: str
    deduplication_url_key: str
    earliest_observation_key: tuple[int, int, int]
    display_name: str
    selected_name_observation_key: tuple[int, int, int]
    url_trace_reference: str
    url_security_policy_identity: tuple[str, str, str]
    retrieved_at: str
    observation_keys: tuple[tuple[int, int, int], ...]


@dataclass(frozen=True)
class AllocatedCanonicalEvidence:
    evidence_id: str
    source_id: str
    source_ordinal: int
    evidence_ordinal: int
    observation_key: tuple[int, int, int, int]


@dataclass(frozen=True)
class RetrievalAllocationPlan:
    """Provenance IDs and ordering only; never a canonical retrieval bundle."""

    sources: tuple[AllocatedCanonicalSource, ...]
    evidence: tuple[AllocatedCanonicalEvidence, ...]


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


def _render_deduplication_key(exact_url: str) -> str:
    """Apply only the transformations frozen by ``url_policy_v1``.

    This function is reached only after ``url_security_policy_v1`` returns
    ``public_safe`` for the same complete classifier input.  Consequently the
    scalar URL grammar, authority shape, and port syntax are already known to
    be valid; any impossible shape here is an internal trace failure.
    """
    before_fragment = exact_url.partition("#")[0]
    before_query, query_marker, query = before_fragment.partition("?")
    scheme_raw, separator, remainder = before_query.partition(":")
    if not separator or not remainder.startswith("//"):
        raise _trace_failure()

    authority_and_path = remainder[2:]
    slash = authority_and_path.find("/")
    if slash < 0:
        authority = authority_and_path
        path = ""
    else:
        authority = authority_and_path[:slash]
        path = authority_and_path[slash:]

    scheme = scheme_raw.lower()
    if authority.startswith("["):
        closing = authority.find("]")
        if closing < 0:
            raise _trace_failure()
        host = f"[{authority[1:closing].lower()}]"
        remainder_after_host = authority[closing + 1 :]
        if remainder_after_host and not remainder_after_host.startswith(":"):
            raise _trace_failure()
        port = remainder_after_host[1:] if remainder_after_host else None
    else:
        if authority.count(":") > 1:
            raise _trace_failure()
        host_raw, port_separator, port_raw = authority.partition(":")
        host = host_raw.lower()
        port = port_raw if port_separator else None

    default_port = "80" if scheme == "http" else "443"
    rendered_port = "" if port is None or port == default_port else f":{port}"
    rendered_query = f"?{query}" if query_marker else ""
    return f"{scheme}://{host}{rendered_port}{path}{rendered_query}"


def derive_public_safe_deduplication_key(
    *,
    exact_url: Any,
    url_role: Any,
    retrieval_auth_context: Any,
    redirect_context: Any,
    origin_rule: Any,
    restricted_trace_reference: Any,
) -> PublicSafeDeduplicationKey:
    """Validate a complete URL-security input and derive its frozen dedup key."""
    try:
        classifier_input = deepcopy(
            {
                "exact_url": exact_url,
                "url_role": url_role,
                "retrieval_auth_context": retrieval_auth_context,
                "redirect_context": redirect_context,
                "origin_rule": origin_rule,
                "restricted_trace_reference": restricted_trace_reference,
            }
        )
    except (TypeError, ValueError, RecursionError):
        raise RetrievalUrlSecurityValidationError(
            "failed_url_security_validation"
        ) from None
    exact_url = classifier_input["exact_url"]
    url_role = classifier_input["url_role"]
    retrieval_auth_context = classifier_input["retrieval_auth_context"]
    redirect_context = classifier_input["redirect_context"]
    origin_rule = classifier_input["origin_rule"]
    restricted_trace_reference = classifier_input[
        "restricted_trace_reference"
    ]
    if (
        not isinstance(redirect_context, dict)
        or redirect_context.get("capture_status") not in {"no_redirect", "complete"}
        or type(redirect_context.get("final_position")) is not int
        or not isinstance(redirect_context.get("members"), list)
        or not 0
        <= redirect_context["final_position"]
        < len(redirect_context["members"])
    ):
        raise RetrievalUrlSecurityValidationError(
            "failed_url_security_validation"
        )
    final_member = redirect_context["members"][redirect_context["final_position"]]
    supplied = {
        "exact_url": exact_url,
        "url_role": url_role,
        "retrieval_auth_context": retrieval_auth_context,
        "origin_rule": origin_rule,
        "restricted_trace_reference": restricted_trace_reference,
    }
    if (
        not isinstance(final_member, dict)
        or not _exact_value_equal(
            supplied,
            {key: final_member.get(key) for key in supplied},
        )
        or final_member.get("url_role") != "final_url"
    ):
        raise RetrievalUrlSecurityValidationError(
            "failed_url_security_validation"
        )
    try:
        result = validate_url_security(
            exact_url=exact_url,
            url_role=url_role,
            retrieval_auth_context=retrieval_auth_context,
            redirect_context=redirect_context,
            origin_rule=origin_rule,
            restricted_trace_reference=restricted_trace_reference,
        )
    except (KeyError, TypeError, ValueError, RecursionError):
        raise RetrievalUrlSecurityValidationError(
            "failed_url_security_validation"
        ) from None
    if result["classification"] != "public_safe" or not isinstance(exact_url, str):
        raise RetrievalUrlSecurityValidationError(
            "failed_url_security_validation"
        )
    return PublicSafeDeduplicationKey(
        _render_deduplication_key(exact_url),
        safe_canonical_url=exact_url,
        url_role=url_role,
        restricted_trace_reference=restricted_trace_reference,
        policy_identity=(
            result["policy_id"],
            result["policy_version"],
            result["policy_hash"],
        ),
        _token=_PUBLIC_SAFE_KEY_TOKEN,
    )


def _exact_value_equal(left: Any, right: Any) -> bool:
    pending = [(left, right)]
    seen_container_pairs: set[tuple[int, int]] = set()
    while pending:
        left_item, right_item = pending.pop()
        if type(left_item) is not type(right_item):
            return False
        if isinstance(left_item, (dict, list, tuple, set, frozenset)):
            identity = (id(left_item), id(right_item))
            if identity in seen_container_pairs:
                continue
            seen_container_pairs.add(identity)
        if isinstance(left_item, dict):
            if left_item.keys() != right_item.keys():
                return False
            pending.extend((left_item[key], right_item[key]) for key in left_item)
        elif isinstance(left_item, (list, tuple)):
            if len(left_item) != len(right_item):
                return False
            pending.extend(zip(left_item, right_item, strict=True))
        elif isinstance(left_item, (set, frozenset)):
            if len(left_item) != len(right_item):
                return False
            unmatched = list(right_item)
            for left_value in left_item:
                match_index = next(
                    (
                        index
                        for index, right_value in enumerate(unmatched)
                        if _exact_value_equal(left_value, right_value)
                    ),
                    None,
                )
                if match_index is None:
                    return False
                unmatched.pop(match_index)
        elif left_item != right_item:
            return False
    return True


def _source_key(observation: RetrievalSourceObservation) -> tuple[int, int, int]:
    if not isinstance(observation, RetrievalSourceObservation):
        raise _trace_failure()
    return source_observation_key(
        observation.retrieval_attempt_ordinal,
        observation.tool_call_ordinal,
        observation.result_ordinal,
    )


def _validate_public_safe_key(value: Any) -> PublicSafeDeduplicationKey:
    if (
        not isinstance(value, PublicSafeDeduplicationKey)
        or not isinstance(value.safe_canonical_url, str)
        or value.url_role != "final_url"
        or not isinstance(value.restricted_trace_reference, str)
        or not value.restricted_trace_reference
        or value.policy_identity != _URL_SECURITY_POLICY_IDENTITY
    ):
        raise RetrievalUrlSecurityValidationError(
            "failed_url_security_validation"
        )
    try:
        expected_key = _render_deduplication_key(value.safe_canonical_url)
    except RetrievalTraceValidationError:
        raise RetrievalUrlSecurityValidationError(
            "failed_url_security_validation"
        ) from None
    if value.value != expected_key:
        raise RetrievalUrlSecurityValidationError(
            "failed_url_security_validation"
        )
    return value


def _evidence_key(
    observation: RetrievalEvidenceObservation,
) -> tuple[int, int, int, int]:
    if not isinstance(observation, RetrievalEvidenceObservation):
        raise _trace_failure()
    return evidence_observation_key(
        observation.retrieval_attempt_ordinal,
        observation.tool_call_ordinal,
        observation.result_ordinal,
        observation.evidence_observation_ordinal,
    )


def _format_retrieved_at(value: Any) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise _trace_failure()
    try:
        offset = value.utcoffset()
    except (OverflowError, ValueError):
        raise _trace_failure() from None
    if offset is None:
        raise _trace_failure()
    try:
        utc_value = value.astimezone(UTC)
    except (OverflowError, ValueError):
        raise _trace_failure() from None
    milliseconds = utc_value.microsecond // 1000
    return utc_value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{milliseconds:03d}Z"


def _schema_valid_source_name(value: Any) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 500


def _as_sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise _trace_failure()
    return tuple(value)


def _validated_mapping(value: Any) -> Mapping[Any, tuple[Any, ...]]:
    if not isinstance(value, Mapping):
        raise _trace_failure()
    try:
        return {key: _as_sequence(child) for key, child in value.items()}
    except (RuntimeError, TypeError, ValueError):
        raise _trace_failure() from None


def _valid_position_tuple(value: Any, width: int) -> bool:
    return (
        isinstance(value, tuple)
        and len(value) == width
        and all(type(component) is int and component >= 1 for component in value)
    )


def validate_trace_position_inventory(
    *,
    retrieval_attempt_ordinals: Sequence[Any],
    tool_call_ordinals_by_attempt: Mapping[Any, Sequence[Any]],
    result_ordinals_by_tool_call: Mapping[Any, Sequence[Any]],
    evidence_ordinals_by_result: Mapping[Any, Sequence[Any]],
) -> ValidatedTracePositionInventory:
    """Validate every parent ordinal scope before any successful-item filtering."""
    attempts = validate_trace_ordinal_scope(
        "retrieval_attempt_ordinal",
        retrieval_attempt_ordinals,
    )
    tools_by_attempt = _validated_mapping(tool_call_ordinals_by_attempt)
    results_by_tool = _validated_mapping(result_ordinals_by_tool_call)
    evidence_by_result = _validated_mapping(evidence_ordinals_by_result)
    if any(type(key) is not int or key < 1 for key in tools_by_attempt) or set(
        tools_by_attempt
    ) != set(attempts):
        raise _trace_failure()

    tool_positions: list[tuple[int, int]] = []
    for attempt in attempts:
        tool_ordinals = validate_trace_ordinal_scope(
            "tool_call_ordinal",
            tools_by_attempt[attempt],
        )
        tool_positions.extend((attempt, tool) for tool in tool_ordinals)
    if any(not _valid_position_tuple(key, 2) for key in results_by_tool) or set(
        results_by_tool
    ) != set(tool_positions):
        raise _trace_failure()

    source_positions: list[tuple[int, int, int]] = []
    for attempt, tool in tool_positions:
        result_ordinals = validate_trace_ordinal_scope(
            "result_ordinal",
            results_by_tool[(attempt, tool)],
        )
        source_positions.extend(
            (attempt, tool, result) for result in result_ordinals
        )
    if any(
        not _valid_position_tuple(key, 3) for key in evidence_by_result
    ) or set(evidence_by_result) != set(source_positions):
        raise _trace_failure()

    evidence_positions: list[tuple[int, int, int, int]] = []
    for attempt, tool, result in source_positions:
        evidence_ordinals = validate_trace_ordinal_scope(
            "evidence_observation_ordinal",
            evidence_by_result[(attempt, tool, result)],
        )
        evidence_positions.extend(
            (attempt, tool, result, evidence_ordinal)
            for evidence_ordinal in evidence_ordinals
        )
    return ValidatedTracePositionInventory(
        source_positions=frozenset(source_positions),
        evidence_positions=frozenset(evidence_positions),
        _token=_TRACE_INVENTORY_TOKEN,
    )


def allocate_retrieval_observations(
    trace_inventory: ValidatedTracePositionInventory,
    source_observations: Sequence[RetrievalSourceObservation],
    evidence_observations: Sequence[RetrievalEvidenceObservation],
) -> RetrievalAllocationPlan:
    """Group successful observations and allocate frozen contiguous IDs.

    The caller supplies every successful and failed atomic observation covered
    by the validated complete-trace inventory.  Failed observations remain in
    the immutable trace, consume their positions, and are filtered only after
    exact coverage validation; this function never recycles or renumbers them.
    The result is an allocation plan, not a canonical retrieval bundle and not
    execution authorization.
    """
    if (
        not isinstance(trace_inventory, ValidatedTracePositionInventory)
        or trace_inventory._token is not _TRACE_INVENTORY_TOKEN
    ):
        raise _trace_failure()
    sources = _as_sequence(source_observations)
    evidence = _as_sequence(evidence_observations)

    keyed_sources = tuple((_source_key(item), item) for item in sources)
    source_keys = tuple(key for key, _ in keyed_sources)
    if (
        len(source_keys) != len(set(source_keys))
        or set(source_keys) != set(trace_inventory.source_positions)
    ):
        raise _trace_failure()

    for _, item in keyed_sources:
        if type(item.successful) is not bool:
            raise _trace_failure()
        if item.successful and not isinstance(
            item.deduplication_key, PublicSafeDeduplicationKey
        ):
            raise _trace_failure()
        if not item.successful and item.deduplication_key is not None:
            raise _trace_failure()
        if item.successful:
            _validate_public_safe_key(item.deduplication_key)

    source_by_observation_key = {
        key: item.deduplication_key
        for key, item in keyed_sources
        if item.successful
    }
    grouped_sources: dict[
        PublicSafeDeduplicationKey,
        list[tuple[tuple[int, int, int], RetrievalSourceObservation]],
    ] = {}
    for key, item in keyed_sources:
        if not item.successful:
            continue
        assert isinstance(item.deduplication_key, PublicSafeDeduplicationKey)
        grouped_sources.setdefault(item.deduplication_key, []).append((key, item))

    ordered_groups = sorted(
        (
            (min(key for key, _ in group), deduplication_key, group)
            for deduplication_key, group in grouped_sources.items()
        ),
        key=lambda value: value[0],
    )

    allocated_sources: list[AllocatedCanonicalSource] = []
    deduplication_key_by_ordinal: dict[int, PublicSafeDeduplicationKey] = {}
    for source_ordinal, (earliest_key, deduplication_key, group) in enumerate(
        ordered_groups,
        start=1,
    ):
        ordered_observations = sorted(group, key=lambda value: value[0])
        selected_name_record = next(
            (
                (key, item.name)
                for key, item in ordered_observations
                if _schema_valid_source_name(item.name)
            ),
            None,
        )
        if selected_name_record is None:
            raise RetrievalCanonicalValidationError("failed_canonical_validation")
        selected_name_key, selected_name = selected_name_record

        earliest_observation = ordered_observations[0][1]
        assert isinstance(
            earliest_observation.deduplication_key,
            PublicSafeDeduplicationKey,
        )
        authoritative_url_key = earliest_observation.deduplication_key
        source_id = render_source_id(source_ordinal)
        deduplication_key_by_ordinal[source_ordinal] = deduplication_key
        allocated_sources.append(
            AllocatedCanonicalSource(
                source_id=source_id,
                source_ordinal=source_ordinal,
                safe_canonical_url=authoritative_url_key.safe_canonical_url,
                deduplication_url_key=deduplication_key.value,
                earliest_observation_key=earliest_key,
                display_name=selected_name,
                selected_name_observation_key=selected_name_key,
                url_trace_reference=(
                    authoritative_url_key.restricted_trace_reference
                ),
                url_security_policy_identity=(
                    authoritative_url_key.policy_identity
                ),
                retrieved_at=_format_retrieved_at(earliest_observation.captured_at),
                observation_keys=tuple(key for key, _ in ordered_observations),
            )
        )

    keyed_evidence = tuple((_evidence_key(item), item) for item in evidence)
    evidence_keys = tuple(key for key, _ in keyed_evidence)
    if (
        len(evidence_keys) != len(set(evidence_keys))
        or set(evidence_keys) != set(trace_inventory.evidence_positions)
    ):
        raise _trace_failure()
    grouped_evidence: dict[
        PublicSafeDeduplicationKey,
        list[tuple[tuple[int, int, int, int], RetrievalEvidenceObservation]],
    ] = {}
    for key, item in keyed_evidence:
        if type(item.successful) is not bool:
            raise _trace_failure()
        if item.successful and not isinstance(
            item.source_deduplication_key, PublicSafeDeduplicationKey
        ):
            raise _trace_failure()
        if not item.successful and item.source_deduplication_key is not None:
            raise _trace_failure()
        if not item.successful:
            continue
        _validate_public_safe_key(item.source_deduplication_key)
        source_key = key[:3]
        if (
            source_by_observation_key.get(source_key)
            != item.source_deduplication_key
        ):
            raise _trace_failure()
        grouped_evidence.setdefault(item.source_deduplication_key, []).append(
            (key, item)
        )

    allocated_evidence: list[AllocatedCanonicalEvidence] = []
    for source in allocated_sources:
        deduplication_key = deduplication_key_by_ordinal[source.source_ordinal]
        ordered_evidence = sorted(
            grouped_evidence.get(deduplication_key, ()),
            key=lambda value: value[0],
        )
        for evidence_ordinal, (observation_key, _) in enumerate(
            ordered_evidence,
            start=1,
        ):
            allocated_evidence.append(
                AllocatedCanonicalEvidence(
                    evidence_id=render_evidence_id(
                        source.source_ordinal,
                        evidence_ordinal,
                    ),
                    source_id=source.source_id,
                    source_ordinal=source.source_ordinal,
                    evidence_ordinal=evidence_ordinal,
                    observation_key=observation_key,
                )
            )

    return RetrievalAllocationPlan(
        sources=tuple(allocated_sources),
        evidence=tuple(allocated_evidence),
    )
